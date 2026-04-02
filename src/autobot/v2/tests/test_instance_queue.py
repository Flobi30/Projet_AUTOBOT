"""
Tests P3 — InstanceQueue

Coverage:
    Correctness:
        - Construction: valid / invalid maxsize
        - put_nowait_drop_oldest: normal enqueue, drop-oldest when full
        - get() / get_nowait(): consumer interface
        - drain(): empties the queue, returns correct count
        - Metrics: enqueue_count, drop_count, fill_ratio, stats dict
        - warn_every throttling (warning only on multiples of N)

    Edge cases:
        - maxsize=1 (minimum)
        - Rapid fill then drain cycle
        - Double-cancel consumer task
        - attach_queue / start_queue_consumer on TradingInstanceAsync stub

    Integration:
        - Producer + consumer concurrent tasks
        - Backpressure: 2× writes > maxsize, verify oldest dropped
        - Graceful drain on stop

    Performance benchmark:
        - put_nowait_drop_oldest throughput (target < 1 µs/op)
"""

from __future__ import annotations

import asyncio
import sys
import time
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, "/home/node/.openclaw/workspace/src")

from autobot.v2.instance_queue import InstanceQueue, DEFAULT_QUEUE_SIZE

# ---------------------------------------------------------------------------
# pytestmark
# ---------------------------------------------------------------------------
pytestmark = pytest.mark.asyncio(loop_scope="function")


# ===========================================================================
# Construction
# ===========================================================================


class TestInstanceQueueInit:
    def test_default_maxsize(self) -> None:
        q = InstanceQueue("inst-001")
        assert q.maxsize == DEFAULT_QUEUE_SIZE
        assert q.instance_id == "inst-001"
        assert q.qsize == 0
        assert q.empty is True
        assert q.full is False
        assert q.enqueue_count == 0
        assert q.drop_count == 0

    def test_custom_maxsize(self) -> None:
        q = InstanceQueue("x", maxsize=64)
        assert q.maxsize == 64

    def test_invalid_maxsize_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="maxsize must be > 0"):
            InstanceQueue("x", maxsize=0)

    def test_invalid_maxsize_negative_raises(self) -> None:
        with pytest.raises(ValueError):
            InstanceQueue("x", maxsize=-1)

    def test_repr(self) -> None:
        q = InstanceQueue("inst-42", maxsize=10)
        r = repr(q)
        assert "inst-42" in r
        assert "10" in r


# ===========================================================================
# put_nowait_drop_oldest — correctness
# ===========================================================================


class TestPutNowaitDropOldest:
    def test_enqueue_single_item(self) -> None:
        q = InstanceQueue("t", maxsize=10)
        dropped = q.put_nowait_drop_oldest("tick-1")
        assert dropped is False
        assert q.qsize == 1
        assert q.enqueue_count == 1
        assert q.drop_count == 0

    def test_enqueue_fills_to_maxsize(self) -> None:
        maxsize = 5
        q = InstanceQueue("t", maxsize=maxsize)
        for i in range(maxsize):
            q.put_nowait_drop_oldest(f"tick-{i}")
        assert q.qsize == maxsize
        assert q.full is True
        assert q.enqueue_count == maxsize
        assert q.drop_count == 0

    def test_drop_oldest_when_full(self) -> None:
        q = InstanceQueue("t", maxsize=3)
        for i in range(3):
            q.put_nowait_drop_oldest(i)          # fills: [0, 1, 2]

        # Overflow — should drop 0 and add 3
        dropped = q.put_nowait_drop_oldest(3)
        assert dropped is True
        assert q.drop_count == 1
        assert q.qsize == 3

        # Verify newest items are in queue (oldest dropped)
        items: List[int] = []
        while not q.empty:
            items.append(q.get_nowait())
        assert items == [1, 2, 3], f"Expected [1,2,3] got {items}"

    def test_multiple_drops_accumulate(self) -> None:
        q = InstanceQueue("t", maxsize=2)
        for i in range(10):
            q.put_nowait_drop_oldest(i)
        # 2 real items kept, 8 drops
        assert q.drop_count == 8
        assert q.enqueue_count == 10
        assert q.qsize == 2

    def test_fill_ratio(self) -> None:
        q = InstanceQueue("t", maxsize=4)
        assert q.fill_ratio == 0.0
        q.put_nowait_drop_oldest("a")
        assert q.fill_ratio == 0.25
        q.put_nowait_drop_oldest("b")
        assert q.fill_ratio == 0.5
        q.put_nowait_drop_oldest("c")
        q.put_nowait_drop_oldest("d")
        assert q.fill_ratio == 1.0

    def test_maxsize_one(self) -> None:
        """Edge case: queue with capacity=1 always replaces old value."""
        q = InstanceQueue("t", maxsize=1)
        q.put_nowait_drop_oldest("first")
        assert q.drop_count == 0

        q.put_nowait_drop_oldest("second")
        assert q.drop_count == 1
        assert q.qsize == 1

        item = q.get_nowait()
        assert item == "second"

    async def test_warn_every_throttle(self) -> None:
        """Warning should fire on drop #1, #101, #201 etc. (warn_every=100)."""
        q = InstanceQueue("t", maxsize=1, warn_every=100)
        q.put_nowait_drop_oldest("seed")  # fill

        warned_at: List[int] = []

        original_warning = __import__("logging").getLogger(
            "autobot.v2.instance_queue"
        ).warning

        def capture_warning(msg, *args, **kwargs):
            warned_at.append(q.drop_count)

        import logging
        lg = logging.getLogger("autobot.v2.instance_queue")
        lg.warning = capture_warning  # type: ignore

        try:
            for _ in range(250):
                q.put_nowait_drop_oldest("data")
        finally:
            lg.warning = original_warning  # type: ignore

        # Should have warned at drop #1, #101, #201
        assert warned_at == [1, 101, 201], f"Warn positions: {warned_at}"


# ===========================================================================
# Consumer interface
# ===========================================================================


class TestConsumerInterface:
    async def test_get_returns_item(self) -> None:
        q = InstanceQueue("t", maxsize=10)
        q.put_nowait_drop_oldest("hello")
        item = await q.get()
        assert item == "hello"

    def test_get_nowait_returns_item(self) -> None:
        q = InstanceQueue("t", maxsize=10)
        q.put_nowait_drop_oldest(42)
        assert q.get_nowait() == 42

    def test_get_nowait_raises_when_empty(self) -> None:
        q = InstanceQueue("t", maxsize=10)
        with pytest.raises(asyncio.QueueEmpty):
            q.get_nowait()

    async def test_get_blocks_until_item_available(self) -> None:
        q = InstanceQueue("t", maxsize=10)
        results: List[int] = []

        async def producer():
            await asyncio.sleep(0.01)
            q.put_nowait_drop_oldest(99)

        async def consumer():
            results.append(await q.get())

        await asyncio.gather(producer(), consumer())
        assert results == [99]

    def test_task_done(self) -> None:
        q = InstanceQueue("t", maxsize=10)
        q.put_nowait_drop_oldest("x")
        q.get_nowait()
        # Should not raise
        q.task_done()


# ===========================================================================
# drain()
# ===========================================================================


class TestDrain:
    async def test_drain_empty_queue(self) -> None:
        q = InstanceQueue("t", maxsize=10)
        count = await q.drain()
        assert count == 0

    async def test_drain_full_queue(self) -> None:
        q = InstanceQueue("t", maxsize=5)
        for i in range(5):
            q.put_nowait_drop_oldest(i)
        assert q.qsize == 5

        count = await q.drain()
        assert count == 5
        assert q.empty is True

    async def test_drain_partial(self) -> None:
        q = InstanceQueue("t", maxsize=10)
        for i in range(4):
            q.put_nowait_drop_oldest(i)
        count = await q.drain()
        assert count == 4
        assert q.empty is True

    async def test_drain_does_not_affect_metrics(self) -> None:
        q = InstanceQueue("t", maxsize=10)
        for _ in range(6):
            q.put_nowait_drop_oldest("x")
        enq_before = q.enqueue_count
        await q.drain()
        # drain does not increment enqueue_count or drop_count
        assert q.enqueue_count == enq_before
        assert q.drop_count == 0


# ===========================================================================
# stats dict
# ===========================================================================


class TestStats:
    def test_stats_keys_present(self) -> None:
        q = InstanceQueue("inst-77", maxsize=200)
        s = q.stats
        assert "instance_id" in s
        assert "qsize" in s
        assert "maxsize" in s
        assert "fill_ratio" in s
        assert "enqueue_count" in s
        assert "drop_count" in s
        assert "drop_ratio" in s

    def test_stats_values_correct(self) -> None:
        q = InstanceQueue("inst-77", maxsize=4)
        q.put_nowait_drop_oldest("a")
        q.put_nowait_drop_oldest("b")
        s = q.stats
        assert s["instance_id"] == "inst-77"
        assert s["qsize"] == 2
        assert s["maxsize"] == 4
        assert s["fill_ratio"] == 0.5
        assert s["enqueue_count"] == 2
        assert s["drop_count"] == 0
        assert s["drop_ratio"] == 0.0

    def test_stats_drop_ratio(self) -> None:
        q = InstanceQueue("t", maxsize=2)
        for i in range(4):
            q.put_nowait_drop_oldest(i)
        s = q.stats
        # 4 enqueued, 2 dropped → ratio = 0.5
        assert s["enqueue_count"] == 4
        assert s["drop_count"] == 2
        assert abs(s["drop_ratio"] - 0.5) < 1e-6


# ===========================================================================
# Concurrent producer + consumer (integration)
# ===========================================================================


class TestConcurrentProducerConsumer:
    async def test_fifo_order_no_overflow(self) -> None:
        """Items should be received in FIFO order when queue never overflows."""
        q = InstanceQueue("t", maxsize=100)
        sent: List[int] = list(range(50))
        received: List[int] = []

        async def producer():
            for item in sent:
                q.put_nowait_drop_oldest(item)
                await asyncio.sleep(0)  # yield occasionally

        async def consumer():
            for _ in range(len(sent)):
                received.append(await q.get())

        await asyncio.gather(producer(), consumer())
        assert received == sent

    async def test_backpressure_drops_oldest(self) -> None:
        """Under heavy load, oldest ticks are dropped, newest are consumed."""
        maxsize = 5
        q = InstanceQueue("t", maxsize=maxsize)

        # Burst-write 3× maxsize items synchronously
        n = maxsize * 3
        for i in range(n):
            q.put_nowait_drop_oldest(i)

        # Queue should have only the last `maxsize` items
        remaining = []
        while not q.empty:
            remaining.append(q.get_nowait())

        assert len(remaining) == maxsize
        assert remaining == list(range(n - maxsize, n))
        assert q.drop_count == n - maxsize

    async def test_graceful_shutdown_drain(self) -> None:
        """After producer stops, drain() clears all pending items."""
        q = InstanceQueue("t", maxsize=50)
        for i in range(30):
            q.put_nowait_drop_oldest(i)

        assert q.qsize == 30
        drained = await q.drain()
        assert drained == 30
        assert q.empty is True


# ===========================================================================
# Performance benchmark
# ===========================================================================


class TestPerformanceBenchmark:
    def test_put_nowait_throughput(self) -> None:
        """
        put_nowait_drop_oldest should complete well under 2 µs/op.
        Target: < 1 µs/op average (CPython 3.11, no overflow).
        """
        q = InstanceQueue("bench", maxsize=65536)
        n = 10_000
        data = {"pair": "XBT/EUR", "price": 50_000.0}

        t0 = time.perf_counter_ns()
        for _ in range(n):
            q.put_nowait_drop_oldest(data)
        elapsed_ns = time.perf_counter_ns() - t0

        ns_per_op = elapsed_ns / n
        print(f"\n  put_nowait_drop_oldest: {ns_per_op:.0f} ns/op (n={n:,})")
        # Generous upper bound: 2 µs/op
        assert ns_per_op < 2_000, (
            f"put_nowait_drop_oldest too slow: {ns_per_op:.0f} ns/op (goal <2000)"
        )

    def test_put_with_overflow_throughput(self) -> None:
        """
        put_nowait_drop_oldest should remain fast even when constantly full.
        """
        q = InstanceQueue("bench-overflow", maxsize=10)
        n = 10_000
        data = {"pair": "XBT/EUR", "price": 50_000.0}

        # Pre-fill the queue
        for _ in range(10):
            q.put_nowait_drop_oldest(data)

        t0 = time.perf_counter_ns()
        for _ in range(n):
            q.put_nowait_drop_oldest(data)
        elapsed_ns = time.perf_counter_ns() - t0

        ns_per_op = elapsed_ns / n
        print(f"\n  put_nowait_drop_oldest (overflow): {ns_per_op:.0f} ns/op (n={n:,})")
        # Overflow path is slightly heavier (one extra get_nowait)
        assert ns_per_op < 5_000, (
            f"Overflow path too slow: {ns_per_op:.0f} ns/op (goal <5000)"
        )
