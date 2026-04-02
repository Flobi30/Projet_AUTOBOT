"""
AsyncDispatcher — RingBuffer → per-instance asyncio.Queue
P3: Fully-decoupled async dispatch layer.

Architecture::

    KrakenWebSocketAsync
         │
    RingBufferDispatcher (P2) — per-pair RingBuffer
         │  one RingBufferReader per pair
         ▼
    AsyncDispatcher (P3)
         │  one _dispatch_loop Task per pair
         │  poll_batch → put_nowait_drop_oldest (non-blocking)
         │
    ┌────┴──────────────────────────────┐
    │  InstanceQueue   InstanceQueue ... │  ← one per instance
    └────────────────────────────────── ┘
         │  await queue.get()
         ▼
    TradingInstanceAsync._queue_consumer_loop()

Key invariants:
    - O(1) dispatch: ``pair → List[InstanceQueue]`` dict lookup, no scan.
    - Non-blocking hot path: ``put_nowait_drop_oldest`` never awaits.
    - One Task per pair (N_pairs, typically 5–20) not per instance (2000+).
    - Backpressure handled at queue level; dispatcher never stalls.
    - Graceful stop: all queues drained before shutdown completes.

Comparison with P2 (RingBufferDispatcher.run_consumer):

    P2: one asyncio.Task per instance (2000 tasks), each holds its own
        RingBufferReader cursor and calls ``instance.on_price_update`` directly.

    P3: one asyncio.Task per pair (≤ 20 tasks total).  Each dispatch loop
        reads one RingBufferReader, fans out via O(k) queue puts where k is
        the number of instances on that pair.  Instance tasks block on
        ``queue.get()`` (cheap await).

    Both approaches are correct.  P3 reduces the number of hot-loop tasks
    from O(N_instances) to O(N_pairs), improving CPU cache locality.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from .instance_queue import InstanceQueue, DEFAULT_QUEUE_SIZE
from .ring_buffer import RingBufferReader
from .ring_buffer_dispatcher import RingBufferDispatcher

logger = logging.getLogger(__name__)

__all__ = ["AsyncDispatcher"]

# Hot-path tuning — kept as module constants so tests can override via monkeypatch
_POLL_BATCH: int = 64
_SLEEP_EMPTY: float = 0.0        # asyncio.sleep(0) yields without wall-clock delay
_LAG_WARN_RATIO: float = 0.5     # Warn when reader.lag > 50% of buffer size


class AsyncDispatcher:
    """
    Routes ticks from per-pair ``RingBuffer`` s into per-instance
    :class:`~instance_queue.InstanceQueue` s.

    Usage::

        dispatcher = AsyncDispatcher(ring_dispatcher)

        # Before start() — subscribe instances
        queue = await dispatcher.subscribe("XBT/EUR", "inst-001")
        await instance.attach_queue(queue)   # hand queue to instance

        await dispatcher.start()             # spawns one Task per pair
        # ... trading ...
        await dispatcher.stop()              # cancel tasks + drain queues

    Thread safety:
        Single-threaded asyncio.  All public methods must be called from
        the same event loop that owns the underlying ``RingBufferDispatcher``.
    """

    def __init__(
        self,
        ring_dispatcher: RingBufferDispatcher,
        queue_maxsize: int = DEFAULT_QUEUE_SIZE,
        poll_batch: int = _POLL_BATCH,
        sleep_empty: float = _SLEEP_EMPTY,
        warn_every: int = 100,
    ) -> None:
        """
        Args:
            ring_dispatcher: P2 dispatcher that owns the WebSocket + ring buffers.
            queue_maxsize:   Per-instance queue capacity (number of ticks).
                             Default 1 000 — at 10 ticks/s per pair this gives
                             100 s of headroom before the oldest tick is dropped.
            poll_batch:      Max messages read from a ring buffer per iteration.
            sleep_empty:     Seconds to sleep when the ring buffer is empty.
                             Default ``0.0`` yields to the event loop without
                             introducing real latency.
            warn_every:      Log a WARNING every N drops per queue.
        """
        self._ring = ring_dispatcher
        self._queue_maxsize = queue_maxsize
        self._poll_batch = poll_batch
        self._sleep_empty = sleep_empty
        self._warn_every = warn_every

        # pair → synthetic reader instance_id (e.g. "_p3_XBT/EUR")
        self._pair_reader_ids: Dict[str, str] = {}

        # pair → RingBufferReader  (one reader per pair, shared across instances)
        self._pair_readers: Dict[str, RingBufferReader] = {}

        # pair → list of InstanceQueues for that pair  (hot-path routing table)
        self._pair_queues: Dict[str, List[InstanceQueue]] = {}

        # instance_id → InstanceQueue
        self._queues: Dict[str, InstanceQueue] = {}

        # instance_id → pair
        self._instance_pair: Dict[str, str] = {}

        # pair → running dispatch Task
        self._dispatch_tasks: Dict[str, asyncio.Task] = {}

        # Approximate counters — no lock needed (single-threaded asyncio)
        self._total_dispatched: int = 0

        self._running: bool = False

        logger.info(
            f"📬 AsyncDispatcher init "
            f"(queue_maxsize={queue_maxsize}, poll_batch={poll_batch})"
        )

    # ------------------------------------------------------------------
    # Subscription management
    # ------------------------------------------------------------------

    async def subscribe(self, pair: str, instance_id: str) -> InstanceQueue:
        """
        Subscribe *instance_id* to *pair*'s price feed.

        Creates:
            - An :class:`InstanceQueue` for the instance.
            - A shared :class:`RingBufferReader` for *pair* if this is the
              first instance subscribing to that pair.

        If the dispatcher is already running, the dispatch task for *pair* is
        started immediately; otherwise it will start on :meth:`start`.

        Args:
            pair:        Trading pair (e.g. ``"XBT/EUR"``).
            instance_id: Unique instance identifier.

        Returns:
            The :class:`InstanceQueue` for this instance.  Pass it to
            :meth:`TradingInstanceAsync.attach_queue`.

        Raises:
            RuntimeError: If *instance_id* is already subscribed.
        """
        if instance_id in self._queues:
            raise RuntimeError(
                f"Instance {instance_id!r} is already subscribed "
                f"(pair={self._instance_pair.get(instance_id)!r})"
            )

        # Create per-instance queue
        queue = InstanceQueue(instance_id, self._queue_maxsize, self._warn_every)
        self._queues[instance_id] = queue
        self._instance_pair[instance_id] = pair

        # Register queue in pair routing table
        if pair not in self._pair_queues:
            self._pair_queues[pair] = []
        self._pair_queues[pair].append(queue)

        # Register one ring reader per pair on first subscription
        if pair not in self._pair_readers:
            reader_id = f"_p3_{pair}"
            self._pair_reader_ids[pair] = reader_id
            reader = await self._ring.subscribe(pair, reader_id)
            self._pair_readers[pair] = reader
            logger.debug(f"📬 Nouveau reader pair créé: {pair}")

            # If already running, start the dispatch task for this new pair now
            if self._running:
                self._start_dispatch_task(pair)

        listener_count = len(self._pair_queues[pair])
        logger.debug(
            f"📬 subscribe: {instance_id} → {pair} "
            f"({listener_count} listener(s) total)"
        )
        return queue

    def unsubscribe(self, instance_id: str) -> None:
        """
        Remove *instance_id*'s queue subscription.

        The pair-level reader and dispatch task remain active as long as
        other instances are subscribed to the same pair.  When the last
        instance for a pair unsubscribes, the dispatch task is cancelled.

        Args:
            instance_id: Instance to remove.
        """
        pair = self._instance_pair.pop(instance_id, None)
        queue = self._queues.pop(instance_id, None)

        if pair is not None and queue is not None:
            pair_list = self._pair_queues.get(pair, [])
            try:
                pair_list.remove(queue)
            except ValueError:
                pass

            # Tear down pair infrastructure when last subscriber leaves
            if not pair_list:
                self._pair_queues.pop(pair, None)
                self._pair_readers.pop(pair, None)
                self._pair_reader_ids.pop(pair, None)
                task = self._dispatch_tasks.pop(pair, None)
                if task and not task.done():
                    task.cancel()
                # Also unsubscribe the synthetic reader from the ring dispatcher
                reader_id = f"_p3_{pair}"
                self._ring.unsubscribe(reader_id)
                logger.debug(f"📬 Pair reader supprimé (no more subscribers): {pair}")

        logger.debug(f"📬 unsubscribe: {instance_id}")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """
        Start one dispatch loop task for every already-subscribed pair.

        Idempotent: calling :meth:`start` twice has no effect.
        """
        if self._running:
            return
        self._running = True

        for pair in list(self._pair_readers.keys()):
            if pair not in self._dispatch_tasks:
                self._start_dispatch_task(pair)

        task_count = len(self._dispatch_tasks)
        logger.info(
            f"📬 AsyncDispatcher démarré "
            f"({task_count} tâche(s), {len(self._queues)} queue(s))"
        )

    async def stop(self) -> None:
        """
        Stop all dispatch tasks and drain all instance queues.

        After this call the dispatcher is quiescent: no tasks are running
        and all queues are empty.  Subscriptions remain intact so the
        dispatcher can be restarted via :meth:`start`.

        ROB-07: signal loops via _running=False and wait for current batch
        to complete (max 2s) before force-cancelling.
        """
        self._running = False  # ROB-07: signal loops to exit gracefully

        # Wait for dispatch tasks to complete their current batch (max 2s)
        tasks = list(self._dispatch_tasks.values())
        if tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=2.0,
                )
            except asyncio.TimeoutError:
                # Force cancel if not done within timeout
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
        self._dispatch_tasks.clear()

        # Drain all instance queues (graceful shutdown)
        total_drained = 0
        for queue in self._queues.values():
            total_drained += await queue.drain()

        logger.info(
            f"📬 AsyncDispatcher arrêté "
            f"(drained={total_drained} item(s) from {len(self._queues)} queue(s))"
        )

    # ------------------------------------------------------------------
    # Internal: dispatch task management
    # ------------------------------------------------------------------

    def _start_dispatch_task(self, pair: str) -> asyncio.Task:
        """Spawn the dispatch coroutine for *pair* as an asyncio Task."""
        task = asyncio.create_task(
            self._dispatch_loop(pair),
            name=f"p3-dispatch-{pair}",
        )
        self._dispatch_tasks[pair] = task
        logger.debug(f"📬 Task dispatch lancée: {pair}")
        return task

    # ------------------------------------------------------------------
    # Hot path: per-pair dispatch loop
    # ------------------------------------------------------------------

    async def _dispatch_loop(self, pair: str) -> None:
        """
        Core dispatch loop for *pair*.

        Runs as a dedicated ``asyncio.Task`` until cancelled.

        Algorithm per iteration::

            messages = reader.poll_batch(poll_batch)   # O(batch) ring reads
            if messages:
                queues = pair_queues[pair]              # O(1) dict lookup
                for msg in messages:
                    for q in queues:                    # O(k), k = instances/pair
                        q.put_nowait_drop_oldest(msg)   # O(1), never awaits
            else:
                await asyncio.sleep(0)                  # yield to event loop

        Total dispatch cost per tick per pair: O(k) put_nowait calls where
        k is the number of instances subscribed to that pair.  No global
        scan over all instances.
        """
        reader = self._pair_readers.get(pair)
        if reader is None:
            logger.error(f"❌ AsyncDispatcher: pas de reader pour pair '{pair}'")
            return

        buf_size = self._ring._buffer_size
        lag_warn_threshold = int(buf_size * _LAG_WARN_RATIO)
        poll_batch = reader.poll_batch      # Cache bound method — avoid attr lookup
        pair_queues = self._pair_queues    # Local ref — avoid repeated dict lookup

        logger.debug(f"📬 _dispatch_loop démarrée: {pair}")
        try:
            while self._running:  # ROB-07: exit naturally when stop() sets _running=False
                messages = poll_batch(self._poll_batch)

                if messages:
                    # Lag diagnostics (cheap — one int comparison)
                    lag = reader.lag
                    if lag > lag_warn_threshold:
                        logger.warning(
                            f"⚠️ Dispatcher {pair}: reader lag={lag:,} "
                            f"(>{lag_warn_threshold:,}, buffer={buf_size:,})"
                        )

                    queues = pair_queues.get(pair, ())
                    for msg in messages:
                        for q in queues:
                            q.put_nowait_drop_oldest(msg)   # Never awaits
                        self._total_dispatched += 1

                else:
                    # Ring buffer empty — yield without wall-clock delay
                    await asyncio.sleep(self._sleep_empty)

        except asyncio.CancelledError:
            logger.debug(f"📬 _dispatch_loop arrêtée: {pair}")
            raise

    # ------------------------------------------------------------------
    # Queries / diagnostics
    # ------------------------------------------------------------------

    def get_queue(self, instance_id: str) -> Optional[InstanceQueue]:
        """
        Return the :class:`InstanceQueue` for *instance_id*, or ``None``.
        """
        return self._queues.get(instance_id)

    def is_running(self) -> bool:
        """``True`` if the dispatcher has been started and not stopped."""
        return self._running

    @property
    def stats(self) -> Dict[str, Any]:
        """Runtime diagnostics snapshot (not on hot path)."""
        total_drops = sum(q.drop_count for q in self._queues.values())
        total_enqueued = sum(q.enqueue_count for q in self._queues.values())

        return {
            "running": self._running,
            "pairs": sorted(self._pair_readers.keys()),
            "dispatch_tasks": len(self._dispatch_tasks),
            "total_instances": len(self._queues),
            "total_dispatched": self._total_dispatched,
            "total_enqueued": total_enqueued,
            "total_dropped": total_drops,
            "drop_ratio": (
                round(total_drops / total_enqueued, 6)
                if total_enqueued > 0
                else 0.0
            ),
            "queues": {iid: q.stats for iid, q in self._queues.items()},
        }

    def __repr__(self) -> str:
        return (
            f"AsyncDispatcher("
            f"running={self._running}, "
            f"pairs={list(self._pair_readers.keys())}, "
            f"instances={len(self._queues)})"
        )
