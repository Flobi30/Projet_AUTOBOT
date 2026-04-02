"""
RingBufferDispatcher — WebSocket → RingBuffer → Instances
P2: High-performance drop-in replacement for WebSocketMultiplexerAsync.

Design goals:
    - O(1) write: WebSocket task writes each TickerData once to a per-pair
      ring buffer (no per-instance copy, no lock).
    - O(1) read: each instance task polls its own RingBufferReader cursor
      independently (no shared state, no lock).
    - Zero allocation on hot path: TickerData references stored by the
      ring buffer; readers return the same references (zero-copy).
    - No asyncio.Lock / threading.Lock anywhere in the dispatch chain.

Architecture::

    KrakenWebSocketAsync
         │  async callback (one per pair)
         ▼
    _write_ticker(pair, TickerData)          ← O(1) write, ~200–400 ns
         │
    RingBuffer[pair]._slots[seq & mask] = data
         │
    ┌────┴────────────────────────────────────────┐
    │  Per-instance asyncio.Task (run_consumer)   │
    │                                             │
    │  reader.poll_batch(64)                      │ ← O(1)/msg, ~50 ns/msg
    │  → await instance.on_price_update(msg)      │
    └─────────────────────────────────────────────┘

Comparison with WebSocketMultiplexerAsync::

    Old: 1 WS callback → sequential await for N instance callbacks
         Latency: O(N) per tick, contention at high instance counts.

    New: 1 WS callback → 1 ring write
         Each instance reads independently at its own pace (O(1) per write).
         Latency: O(1) for producer, O(lag) per consumer batch.

Public API mirrors WebSocketMultiplexerAsync so the orchestrator swap is
surgical (see orchestrator_async.py).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Coroutine, Dict, Optional, Set, Tuple

from .ring_buffer import RingBuffer, RingBufferReader, DEFAULT_BUFFER_SIZE
from .websocket_async import KrakenWebSocketAsync, TickerData

logger = logging.getLogger(__name__)

# Type alias matching websocket_async.AsyncCallback
AsyncCallback = Callable[[TickerData], Coroutine[Any, Any, None]]

# Hot-path tuning
_POLL_BATCH: int = 64        # Messages per poll_batch call
_SLEEP_EMPTY: float = 0.0    # asyncio.sleep(0) yields without real delay

__all__ = ["RingBufferDispatcher"]


class RingBufferDispatcher:
    """
    Lock-free WebSocket dispatcher backed by per-pair ring buffers.

    Drop-in replacement for :class:`WebSocketMultiplexerAsync`.  The
    orchestrator subscribes each instance via :meth:`subscribe`, receives a
    :class:`RingBufferReader`, and then spawns one
    :meth:`run_consumer` coroutine per instance.

    Thread safety:
        Designed for single-threaded asyncio.  All methods must be called
        from the same event loop that runs the WebSocket receive task.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        buffer_size: int = DEFAULT_BUFFER_SIZE,
    ) -> None:
        """
        Args:
            api_key:     Kraken API key (passed to KrakenWebSocketAsync).
            api_secret:  Kraken API secret.
            buffer_size: Slots per pair buffer.  Must be a power of 2.
                         Default: 65 536 — at 10 ticks/s per pair this
                         gives ~6 553 seconds of history before overwrite.
        """
        self._buffer_size = buffer_size
        self._ws = KrakenWebSocketAsync(api_key, api_secret)

        # Per-pair ring buffers — created lazily on first subscribe.
        self._buffers: Dict[str, RingBuffer] = {}

        # WS-level subscriptions already sent (one per pair).
        self._ws_subscribed: Set[str] = set()

        # Per-instance reader: instance_id → (pair, reader)
        self._readers: Dict[str, Tuple[str, RingBufferReader]] = {}

        # Approximate counters — no lock needed (single-threaded asyncio).
        self._write_count: int = 0
        self._overflow_skips: int = 0

        logger.info(
            "🔁 RingBufferDispatcher init "
            f"(buffer_size={buffer_size:,} slots/pair)"
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open the WebSocket connection."""
        await self._ws.connect()
        logger.info("🔁 RingBufferDispatcher connecté")

    async def disconnect(self) -> None:
        """Close the WebSocket connection."""
        await self._ws.disconnect()
        logger.info("🔁 RingBufferDispatcher déconnecté")

    # ------------------------------------------------------------------
    # Subscription management
    # ------------------------------------------------------------------

    def _get_or_create_buffer(self, pair: str) -> RingBuffer:
        """Return existing buffer for *pair*, or create a new one."""
        buf = self._buffers.get(pair)
        if buf is None:
            buf = RingBuffer(self._buffer_size)
            self._buffers[pair] = buf
            logger.debug(f"🆕 Ring buffer créé: {pair} ({self._buffer_size:,} slots)")
        return buf

    async def subscribe(self, pair: str, instance_id: str) -> RingBufferReader:
        """
        Subscribe *instance_id* to *pair*'s price feed.

        Creates the per-pair ring buffer on first call for a pair.
        Sends the WebSocket subscription once per pair.

        Args:
            pair:        Trading pair (e.g. ``"XBT/EUR"``).
            instance_id: Unique instance identifier.

        Returns:
            A :class:`RingBufferReader` starting at the current write
            position (no historical data).
        """
        buf = self._get_or_create_buffer(pair)
        reader = RingBufferReader(buf, start_at_tail=True)
        self._readers[instance_id] = (pair, reader)

        # One WS subscription per pair
        if pair not in self._ws_subscribed:
            self._ws_subscribed.add(pair)

            # Capture pair in default argument to avoid closure late-binding.
            async def _write_cb(data: TickerData, _pair: str = pair) -> None:
                self._write_ticker(_pair, data)

            self._ws.add_ticker_callback(pair, _write_cb)
            await self._ws.subscribe_ticker(pair)

        logger.debug(
            f"🔁 {instance_id} → {pair} "
            f"({sum(1 for p, _ in self._readers.values() if p == pair)} listeners)"
        )
        return reader

    def unsubscribe(self, instance_id: str) -> None:
        """
        Remove *instance_id*'s reader.

        The WS subscription for the pair is kept alive so other instances
        subscribed to the same pair continue receiving data.
        """
        self._readers.pop(instance_id, None)

    # ------------------------------------------------------------------
    # Hot path: producer write
    # ------------------------------------------------------------------

    def _write_ticker(self, pair: str, data: TickerData) -> None:
        """
        Write *data* to the pair's ring buffer.

        Called from the WebSocket receive task (the single producer).
        No locks.  O(1).  ~200–400 ns including Python call overhead.
        """
        buf = self._buffers.get(pair)
        if buf is None:
            return
        buf.write(data)           # O(1) — pre-allocated slot, atomic store
        self._write_count += 1    # Approximate (no lock needed in asyncio)

    # ------------------------------------------------------------------
    # Hot path: consumer loop
    # ------------------------------------------------------------------

    async def run_consumer(
        self,
        instance_id: str,
        callback: AsyncCallback,
        poll_interval: float = _SLEEP_EMPTY,
    ) -> None:
        """
        Run the dispatch loop for *instance_id*.

        Polls the ring buffer and calls *callback* for each new
        :class:`TickerData`.  Designed to run as one
        ``asyncio.Task`` per instance.

        The loop yields to the event loop (``asyncio.sleep(0)``) when
        the buffer is empty, preventing CPU spin.

        Args:
            instance_id:    Instance to serve.
            callback:       Async coroutine ``(TickerData) → None``.
            poll_interval:  Seconds to sleep when buffer is empty.
                            Default ``0.0`` yields without wall-clock delay.
        """
        entry = self._readers.get(instance_id)
        if entry is None:
            logger.error(f"❌ Pas de reader pour {instance_id}")
            return

        _, reader = entry
        poll_batch = reader.poll_batch  # Cache bound method (avoid attr lookup)

        logger.debug(f"🔁 Consumer démarré: {instance_id}")
        try:
            while True:
                messages = poll_batch(_POLL_BATCH)

                if messages:
                    # Warn if consumer is falling behind
                    lag = reader.lag
                    if lag > self._buffer_size >> 1:
                        logger.warning(
                            f"⚠️ {instance_id} lag={lag:,} "
                            f"(buffer={self._buffer_size:,})"
                        )

                    for msg in messages:
                        try:
                            await callback(msg)
                        except Exception as exc:
                            logger.error(
                                f"❌ Erreur callback {instance_id}: {exc}"
                            )
                else:
                    # Buffer empty — yield to event loop
                    await asyncio.sleep(poll_interval)

        except asyncio.CancelledError:
            logger.debug(f"🔁 Consumer arrêté: {instance_id}")
            raise

    # ------------------------------------------------------------------
    # Queries (mirrors WebSocketMultiplexerAsync interface)
    # ------------------------------------------------------------------

    def get_last_price(self, pair: str) -> Optional[TickerData]:
        """Return the last cached price for *pair*."""
        return self._ws.get_last_price(pair)

    def is_connected(self) -> bool:
        """Return ``True`` if the WebSocket is open."""
        return self._ws.is_connected()

    def is_data_fresh(self, max_age_seconds: float = 30.0) -> bool:
        """Return ``True`` if a message was received within *max_age_seconds*."""
        return self._ws.is_data_fresh(max_age_seconds)

    @property
    def stats(self) -> Dict[str, Any]:
        """Runtime diagnostics (not on hot path)."""
        total_lag = sum(r.lag for _, r in self._readers.values())
        pairs_listener_counts = {}
        for pair, _ in self._readers.values():
            pairs_listener_counts[pair] = pairs_listener_counts.get(pair, 0) + 1

        return {
            "pairs_subscribed": len(self._buffers),
            "total_listeners": len(self._readers),
            "write_count": self._write_count,
            "overflow_skips": self._overflow_skips,
            "total_lag": total_lag,
            "buffer_size": self._buffer_size,
            "ws_connected": self._ws.is_connected(),
            "connections": 1,
            "listeners_per_pair": pairs_listener_counts,
        }
