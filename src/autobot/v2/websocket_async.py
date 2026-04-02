"""
Kraken WebSocket Client — Full Async (websockets library)
MIGRATION P0: Replaces websocket_client.py (threading + websocket-client)

Uses:
- websockets (async) instead of websocket-client (sync)
- asyncio.Queue for dispatch instead of threading callbacks
- asyncio.Lock instead of threading.Lock
- Reconnection with exponential backoff (async)

Public API is identical to KrakenWebSocket / WebSocketMultiplexer.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from datetime import datetime
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set

import orjson

# Re-export TickerData unchanged (pure dataclass, no threading)
from .websocket_client import TickerData
from .os_tuning import get_os_tuner

logger = logging.getLogger(__name__)

# Type alias for async callbacks
AsyncCallback = Callable[[TickerData], Coroutine[Any, Any, None]]


class KrakenWebSocketAsync:
    """
    Async Kraken WebSocket client using the `websockets` library.

    Drop-in async replacement for KrakenWebSocket.
    """

    WS_PUBLIC = "wss://ws.kraken.com"
    WS_PRIVATE = "wss://ws-auth.kraken.com"

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret

        # Connection state
        self._ws: Any = None  # websockets.WebSocketClientProtocol
        self._running = False
        self._recv_task: Optional[asyncio.Task] = None

        # Callbacks (async)
        self._ticker_callbacks: Dict[str, List[AsyncCallback]] = {}

        # Cache
        self._last_prices: Dict[str, TickerData] = {}
        self._subscribed_pairs: Set[str] = set()

        # Heartbeat / staleness
        self._last_message_time: float = 0.0
        self._stale_threshold: float = 30.0
        self._heartbeat_task: Optional[asyncio.Task] = None

        # Reconnect backoff
        self._reconnect_backoff: float = 1.0
        self._max_reconnect_backoff: float = 60.0

        # ARCH-08: backpressure monitoring counters
        self._msg_count: int = 0
        self._msg_rate_window: float = 0.0

        # ROB-03: circuit breaker for runaway reconnects
        self._reconnect_attempts: int = 0
        self._max_reconnect_attempts: int = 20

        logger.info("📡 KrakenWebSocketAsync initialisé")

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open the WebSocket connection (async)."""
        if self._running:
            logger.warning("⚠️ WebSocket déjà connecté")
            return

        try:
            import websockets  # type: ignore[import-untyped]
        except ImportError:
            raise ImportError("pip install websockets  (async WS library)")

        self._running = True
        self._last_message_time = time.monotonic()

        try:
            self._ws = await websockets.connect(
                self.WS_PUBLIC,
                ping_interval=30,
                ping_timeout=10,
                close_timeout=5,
            )
            # P5: Apply TCP low-latency options (TCP_NODELAY, SO_BUSY_POLL, TCP_QUICKACK)
            get_os_tuner().tune_websocket(self._ws)
        except Exception as exc:
            self._running = False
            logger.error(f"❌ Échec connexion WS: {exc}")
            raise

        # Spawn receive loop
        self._recv_task = asyncio.create_task(self._recv_loop(), name="ws-recv")

        # Spawn heartbeat monitor
        self._heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(), name="ws-heartbeat"
        )

        # Re-subscribe to previously tracked pairs
        for pair in list(self._subscribed_pairs):
            await self._send_subscribe(pair)

        self._reconnect_backoff = 1.0
        logger.info("✅ WebSocket Kraken connecté (async)")

    async def disconnect(self) -> None:
        """Close the WebSocket connection."""
        self._running = False

        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        if self._recv_task and not self._recv_task.done():
            self._recv_task.cancel()
            try:
                await self._recv_task
            except asyncio.CancelledError:
                pass

        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

        logger.info("🔌 WebSocket déconnecté (async)")

    # ------------------------------------------------------------------
    # Receive loop
    # ------------------------------------------------------------------

    async def _recv_loop(self) -> None:
        """Main receive loop — runs as an asyncio Task."""
        assert self._ws is not None
        try:
            async for raw in self._ws:
                if not self._running:
                    break
                self._last_message_time = time.monotonic()
                self._msg_count += 1  # ARCH-08: backpressure counter
                try:
                    await self._on_message(raw)
                except Exception as exc:
                    logger.error(f"❌ Erreur traitement message WS: {exc}")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if self._running:
                logger.warning(f"🔌 WebSocket fermé: {exc}")
                asyncio.create_task(self._reconnect())

    async def _on_message(self, raw: str | bytes) -> None:
        """Parse a single WS message."""
        data = orjson.loads(raw)

        # Heartbeat
        if isinstance(data, dict):
            event = data.get("event")
            if event == "heartbeat":
                return
            if event == "systemStatus":
                logger.info(f"💚 Kraken WS Status: {data.get('status')}")
                return
            if event == "subscriptionStatus":
                pair = data.get("pair")
                status = data.get("status")
                logger.info(f"📡 Subscription {pair}: {status}")
                if status == "subscribed" and pair:
                    self._subscribed_pairs.add(pair)
                return

        # Channel data
        if isinstance(data, list) and len(data) >= 4:
            channel_data = data[1]
            channel_name = data[2]
            pair = data[3]

            if "ticker" in channel_name:
                await self._process_ticker(pair, channel_data)

    async def _process_ticker(self, pair: str, data: dict) -> None:
        """Process ticker update and dispatch to subscribers."""
        try:
            price = float(data.get("c", [0])[0])
            bid = float(data.get("b", [0])[0])
            ask = float(data.get("a", [0])[0])
            volume = float(data.get("v", [0, 0])[1])
        except (IndexError, TypeError, ValueError):
            return

        # C5 — reject malformed or impossible market data
        if not math.isfinite(price) or price <= 0:
            logger.warning("❌ Prix WS invalide %s: %s", pair, price)
            return
        if not math.isfinite(bid) or bid <= 0 or not math.isfinite(ask) or ask <= 0:
            logger.warning("❌ Bid/Ask WS invalides %s: bid=%s ask=%s", pair, bid, ask)
            return
        if bid >= ask:
            logger.warning("❌ Spread invalide %s: bid=%s >= ask=%s", pair, bid, ask)
            return

        ticker = TickerData(
            symbol=pair,
            price=price,
            bid=bid,
            ask=ask,
            volume_24h=volume,
            timestamp=datetime.now(),
        )

        self._last_prices[pair] = ticker

        # Dispatch to async callbacks
        callbacks = list(self._ticker_callbacks.get(pair, []))
        for cb in callbacks:
            try:
                await cb(ticker)
            except Exception as exc:
                logger.error(f"❌ Erreur callback ticker {pair}: {exc}")

    # ------------------------------------------------------------------
    # Subscriptions
    # ------------------------------------------------------------------

    async def _send_subscribe(self, pair: str) -> None:
        """Send subscribe message over WebSocket."""
        if not self._ws:
            return
        msg = orjson.dumps(
            {"event": "subscribe", "pair": [pair], "subscription": {"name": "ticker"}}
        )
        try:
            await self._ws.send(msg.decode("utf-8"))
            logger.info(f"📡 Subscription ticker: {pair}")
        except Exception as exc:
            logger.error(f"❌ Erreur subscription: {exc}")

    async def _send_unsubscribe(self, pair: str) -> None:
        if not self._ws:
            return
        msg = orjson.dumps(
            {
                "event": "unsubscribe",
                "pair": [pair],
                "subscription": {"name": "ticker"},
            }
        )
        try:
            await self._ws.send(msg.decode("utf-8"))
            self._subscribed_pairs.discard(pair)
            logger.info(f"📡 Unsubscribed: {pair}")
        except Exception as exc:
            logger.error(f"❌ Erreur unsubscribe: {exc}")

    async def subscribe_ticker(self, pair: str) -> None:
        self._subscribed_pairs.add(pair)
        await self._send_subscribe(pair)

    async def unsubscribe_ticker(self, pair: str) -> None:
        await self._send_unsubscribe(pair)

    def add_ticker_callback(self, pair: str, callback: AsyncCallback) -> None:
        """Register an async callback for a pair (no subscription sent)."""
        if pair not in self._ticker_callbacks:
            self._ticker_callbacks[pair] = []
        self._ticker_callbacks[pair].append(callback)

    def remove_ticker_callback(self, pair: str, callback: AsyncCallback) -> None:
        if pair in self._ticker_callbacks:
            try:
                self._ticker_callbacks[pair].remove(callback)
            except ValueError:
                pass
            if not self._ticker_callbacks[pair]:
                del self._ticker_callbacks[pair]

    # ------------------------------------------------------------------
    # Heartbeat / reconnect
    # ------------------------------------------------------------------

    async def _heartbeat_loop(self) -> None:
        logger.info("💓 Heartbeat monitoring démarré (async)")
        while self._running:
            await asyncio.sleep(10)
            if not self._running:
                break
            elapsed = time.monotonic() - self._last_message_time
            if elapsed > self._stale_threshold:
                logger.warning(
                    f"🚨 Prix stalé depuis {elapsed:.0f}s - Reconnexion nécessaire"
                )
                await self._reconnect()
            else:
                # ARCH-08: backpressure monitoring — warn if rate > 100 msg/s
                rate = self._msg_count / max(elapsed, 1)
                if rate > 100:
                    logger.warning("WS backpressure: %.0f msg/s", rate)
                self._msg_count = 0  # reset window
                if not self.is_connected():
                    logger.warning("🔌 WS déconnecté - Tentative reconnexion...")
                    await self._reconnect()
        logger.info("💓 Heartbeat monitoring arrêté (async)")

    async def _reconnect(self) -> None:
        # ROB-03: circuit breaker — abort after too many consecutive reconnects
        self._reconnect_attempts += 1
        if self._reconnect_attempts > self._max_reconnect_attempts:
            logger.error(
                "WS CIRCUIT BREAKER: %d tentatives de reconnexion -- abandon",
                self._reconnect_attempts,
            )
            self._running = False
            return

        logger.info(
            f"🔄 Reconnexion WS (backoff: {self._reconnect_backoff}s)..."
        )
        # Close existing
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

        if self._recv_task and not self._recv_task.done():
            self._recv_task.cancel()
            try:
                await self._recv_task
            except asyncio.CancelledError:
                pass

        await asyncio.sleep(self._reconnect_backoff)
        self._reconnect_backoff = min(
            self._reconnect_backoff * 2, self._max_reconnect_backoff
        )

        try:
            # Re-create connection
            import websockets  # type: ignore[import-untyped]

            self._ws = await websockets.connect(
                self.WS_PUBLIC, ping_interval=30, ping_timeout=10, close_timeout=5
            )
            # P5: Re-apply TCP options on reconnect
            get_os_tuner().tune_websocket(self._ws)
            self._recv_task = asyncio.create_task(self._recv_loop(), name="ws-recv")
            self._last_message_time = time.monotonic()

            # Re-subscribe
            for pair in list(self._subscribed_pairs):
                await self._send_subscribe(pair)

            self._reconnect_backoff = 1.0
            self._reconnect_attempts = 0  # ROB-03: reset circuit breaker on success
            logger.info("✅ Reconnexion réussie (async)")
        except Exception as exc:
            logger.error(f"❌ Échec reconnexion: {exc}")

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_last_price(self, pair: str) -> Optional[TickerData]:
        return self._last_prices.get(pair)

    def is_data_fresh(self, max_age_seconds: float = 30.0) -> bool:
        if self._last_message_time == 0:
            return False
        return (time.monotonic() - self._last_message_time) < max_age_seconds

    def is_connected(self) -> bool:
        return self._running and self._ws is not None and self._ws.open


class WebSocketMultiplexerAsync:
    """
    Async multiplexer — 1 connection for N pairs.

    Drop-in async replacement for WebSocketMultiplexer.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
    ) -> None:
        self._ws = KrakenWebSocketAsync(api_key, api_secret)
        self._callbacks: Dict[str, List[AsyncCallback]] = {}
        # Track which pairs we already subscribed on the WS level
        self._ws_subscribed: Set[str] = set()
        logger.info("🔀 WebSocketMultiplexerAsync initialisé")

    async def connect(self) -> None:
        await self._ws.connect()
        logger.info("🔀 Multiplexer connecté (async)")

    async def disconnect(self) -> None:
        await self._ws.disconnect()
        logger.info("🔀 Multiplexer déconnecté (async)")

    async def subscribe(self, pair: str, callback: AsyncCallback) -> None:
        """Subscribe an instance callback to a pair."""
        if pair not in self._callbacks:
            self._callbacks[pair] = []
        self._callbacks[pair].append(callback)

        # Only subscribe once on WS level per pair
        if pair not in self._ws_subscribed:
            self._ws_subscribed.add(pair)

            async def _dispatch(data: TickerData, _pair: str = pair) -> None:
                cbs = list(self._callbacks.get(_pair, []))
                for cb in cbs:
                    try:
                        await cb(data)
                    except Exception as exc:
                        logger.error(f"❌ Erreur dispatch {_pair}: {exc}")

            self._ws.add_ticker_callback(pair, _dispatch)
            await self._ws.subscribe_ticker(pair)

        logger.debug(
            f"🔀 Paire {pair} souscrite via multiplexer "
            f"({len(self._callbacks.get(pair, []))} listeners)"
        )

    def unsubscribe(self, pair: str, callback: AsyncCallback) -> None:
        """Remove a callback. If no listeners left, we keep the WS sub for simplicity."""
        if pair in self._callbacks:
            try:
                self._callbacks[pair].remove(callback)
            except ValueError:
                pass
            if not self._callbacks[pair]:
                del self._callbacks[pair]

    def get_last_price(self, pair: str) -> Optional[TickerData]:
        return self._ws.get_last_price(pair)

    def is_connected(self) -> bool:
        return self._ws.is_connected()

    def is_data_fresh(self, max_age_seconds: float = 30.0) -> bool:        return self._ws.is_data_fresh(max_age_seconds)

    @property
    def stats(self) -> Dict[str, int]:
        total_listeners = sum(len(cbs) for cbs in self._callbacks.values())
        return {
            "pairs_subscribed": len(self._callbacks),
            "total_listeners": total_listeners,
            "ws_connected": self._ws.is_connected(),
            "connections": 1,
        }
