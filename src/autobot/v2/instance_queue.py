"""
InstanceQueue — asyncio.Queue wrapper per trading instance.
P3: Decoupled buffer between AsyncDispatcher and TradingInstanceAsync.

Design:
    One asyncio.Queue per trading instance.  The AsyncDispatcher writes
    TickerData items via ``put_nowait_drop_oldest()`` — non-blocking, never
    awaits.  TradingInstanceAsync reads via ``get()`` in its own async task.

Backpressure policy (queue full):
    - Drop oldest: pop the front item (oldest price tick), push new at back.
    - Log a warning on every N-th drop (configurable, avoids log flooding).
    - Track ``drop_count`` and ``enqueue_count`` for observability.

Thread / task safety:
    Designed for single-threaded asyncio.  ``put_nowait`` and ``get_nowait``
    are non-blocking; all hot-path operations are O(1).

Performance:
    put_nowait_drop_oldest : ~200–400 ns (asyncio.Queue overhead)
    get()                  : coroutine suspend/resume (~1–3 µs)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

__all__ = ["InstanceQueue", "DEFAULT_QUEUE_SIZE"]

DEFAULT_QUEUE_SIZE: int = 1000


class InstanceQueue:
    """
    Fixed-size asyncio.Queue with drop-oldest backpressure.

    Non-blocking enqueue via :meth:`put_nowait_drop_oldest` drops the front
    (oldest) item when the queue is full — ensuring the consumer always
    receives the freshest possible data without ever blocking the producer.

    Metrics (cumulative, thread-safe under single asyncio loop):
        - ``enqueue_count``: items successfully enqueued.
        - ``drop_count``:    items dropped (oldest evicted).
        - ``fill_ratio``:    current fill level as a fraction 0.0–1.0.

    Example::

        q = InstanceQueue("inst-001", maxsize=500)

        # Dispatcher (hot path, non-blocking)
        q.put_nowait_drop_oldest(ticker_data)

        # Instance consumer (async)
        while True:
            data = await q.get()
            await process(data)
    """

    __slots__ = (
        "_instance_id",
        "_maxsize",
        "_queue",
        "_enqueue_count",
        "_drop_count",
        "_warn_every",
    )

    def __init__(
        self,
        instance_id: str,
        maxsize: int = DEFAULT_QUEUE_SIZE,
        warn_every: int = 100,
    ) -> None:
        """
        Args:
            instance_id: Owner instance identifier (used in log messages).
            maxsize:     Maximum number of items in the queue.  Must be > 0.
            warn_every:  Log a ``WARNING`` every N drops (throttles log spam).

        Raises:
            ValueError: If maxsize <= 0.
        """
        if maxsize <= 0:
            raise ValueError(f"maxsize must be > 0, got {maxsize}")

        self._instance_id = instance_id
        self._maxsize = maxsize
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._enqueue_count: int = 0
        self._drop_count: int = 0
        self._warn_every: int = max(1, warn_every)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def instance_id(self) -> str:
        """Owner instance identifier."""
        return self._instance_id

    @property
    def maxsize(self) -> int:
        """Maximum queue capacity (fixed at construction time)."""
        return self._maxsize

    @property
    def qsize(self) -> int:
        """Current number of items in the queue."""
        return self._queue.qsize()

    @property
    def empty(self) -> bool:
        """``True`` if the queue contains no items."""
        return self._queue.empty()

    @property
    def full(self) -> bool:
        """``True`` if the queue is at ``maxsize``."""
        return self._queue.full()

    @property
    def fill_ratio(self) -> float:
        """Current fill level as a fraction in [0.0, 1.0]."""
        return self._queue.qsize() / self._maxsize

    @property
    def enqueue_count(self) -> int:
        """Total items successfully enqueued (cumulative since creation)."""
        return self._enqueue_count

    @property
    def drop_count(self) -> int:
        """Total oldest items dropped due to backpressure (cumulative)."""
        return self._drop_count

    # ------------------------------------------------------------------
    # Hot path: non-blocking enqueue (called by AsyncDispatcher)
    # ------------------------------------------------------------------

    def put_nowait_drop_oldest(self, data: Any) -> bool:
        """
        Enqueue *data* without blocking.

        If the queue is full, the oldest (front) item is silently discarded
        to make room.  This ensures the consumer always receives the most
        recent data even under backpressure.

        This method **never awaits** — safe to call from the dispatcher loop
        without breaking O(1) non-blocking routing.

        Args:
            data: Item to enqueue (typically a ``TickerData`` instance).

        Returns:
            ``True``  if an oldest item was evicted (backpressure triggered).
            ``False`` if enqueued without any drop.
        """
        dropped = False

        if self._queue.full():
            # Evict oldest item to maintain data freshness
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                # Consumer drained the queue between our full() check and here
                pass
            else:
                dropped = True
                self._drop_count += 1
                if self._drop_count % self._warn_every == 1:
                    logger.warning(
                        f"⚠️ InstanceQueue {self._instance_id}: "
                        f"drop #{self._drop_count} "
                        f"(queue full, maxsize={self._maxsize})"
                    )

        try:
            self._queue.put_nowait(data)
            self._enqueue_count += 1
        except asyncio.QueueFull:
            # Extremely rare: consumer emptied + refilled the queue between
            # our get_nowait and put_nowait.  Skip this item (one miss is
            # acceptable; we never block).
            pass

        return dropped

    # ------------------------------------------------------------------
    # Consumer interface (called by TradingInstanceAsync)
    # ------------------------------------------------------------------

    async def get(self) -> Any:
        """
        Wait for the next item and return it.

        Blocks the caller coroutine until data is available.
        Intended for use in the instance's queue-consumer coroutine.
        """
        return await self._queue.get()

    def get_nowait(self) -> Any:
        """
        Non-blocking dequeue.

        Raises:
            asyncio.QueueEmpty: If the queue is currently empty.
        """
        return self._queue.get_nowait()

    def task_done(self) -> None:
        """Notify that a task produced by ``get()`` is complete.

        Required to unblock :meth:`asyncio.Queue.join` if used.
        """
        self._queue.task_done()

    # ------------------------------------------------------------------
    # Graceful shutdown
    # ------------------------------------------------------------------

    async def drain(self) -> int:
        """
        Discard all currently queued items.

        Non-blocking: does not await.  Returns immediately after emptying.

        Returns:
            Number of items discarded.
        """
        count = 0
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                count += 1
            except asyncio.QueueEmpty:
                break
        return count

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    @property
    def stats(self) -> Dict[str, Any]:
        """Return queue diagnostics (not on hot path)."""
        enq = self._enqueue_count
        drp = self._drop_count
        return {
            "instance_id": self._instance_id,
            "qsize": self._queue.qsize(),
            "maxsize": self._maxsize,
            "fill_ratio": round(self.fill_ratio, 4),
            "enqueue_count": enq,
            "drop_count": drp,
            "drop_ratio": round(drp / enq, 6) if enq > 0 else 0.0,
        }

    def __repr__(self) -> str:
        return (
            f"InstanceQueue(id={self._instance_id!r}, "
            f"qsize={self.qsize}/{self._maxsize}, "
            f"drops={self._drop_count})"
        )
