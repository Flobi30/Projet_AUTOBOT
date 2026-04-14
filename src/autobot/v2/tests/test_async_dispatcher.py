"""
Tests P3 — AsyncDispatcher

Coverage:
    Fonctionnelle:
        - subscribe() crée une InstanceQueue par instance
        - subscribe() crée un seul RingBufferReader par pair
        - subscribe() double → RuntimeError
        - unsubscribe() retire la queue
        - unsubscribe() du dernier subscriber → retire le reader ET cancel la task
        - get_queue() lookup O(1)
        - is_running() lifecycle

    Dispatch:
        - Les messages écrits dans le RingBuffer arrivent dans la queue
        - Fan-out: N instances sur la même pair reçoivent toutes le message
        - Isolation: un message XBT/EUR n'arrive pas dans la queue ETH/EUR
        - Backpressure: la queue full → drop_oldest, dispatcher ne plante pas

    Lifecycle:
        - start() idempotent
        - stop() cancel les tasks + drain les queues
        - subscribe() après start() → dispatch task démarrée immédiatement

    Intégration end-to-end:
        - RingBuffer write → AsyncDispatcher poll → InstanceQueue.get()
        - Batch de ticks → tous reçus dans l'ordre
        - Multi-pair × multi-instance

    Performance:
        - Dispatch throughput > 100K msgs/sec (smoke test)
"""

from __future__ import annotations

import asyncio
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, "/home/node/.openclaw/workspace/src")

from autobot.v2.ring_buffer import RingBuffer, RingBufferReader
from autobot.v2.instance_queue import InstanceQueue, DEFAULT_QUEUE_SIZE
from autobot.v2.async_dispatcher import AsyncDispatcher

# ===========================================================================
# Helpers / stubs
# ===========================================================================

@dataclass
class FakeTick:
    """Minimal TickerData substitute for tests — no external imports needed."""
    pair: str
    price: float


class FakeRingDispatcher:
    """
    Minimal stub for RingBufferDispatcher used by AsyncDispatcher.

    Holds real RingBuffer objects so dispatch actually works.
    Exposes write(pair, data) to simulate WebSocket inbound ticks.
    """

    def __init__(self, buffer_size: int = 256) -> None:
        self._buffer_size = buffer_size
        self._buffers: Dict[str, RingBuffer] = {}
        self._subscribed: Dict[str, RingBufferReader] = {}

    async def subscribe(self, pair: str, instance_id: str) -> RingBufferReader:
        """Create/get a ring buffer and return a reader for it."""
        if pair not in self._buffers:
            self._buffers[pair] = RingBuffer(self._buffer_size)
        reader = RingBufferReader(self._buffers[pair], start_at_tail=True)
        self._subscribed[instance_id] = reader
        return reader

    def unsubscribe(self, instance_id: str) -> None:
        self._subscribed.pop(instance_id, None)

    def write(self, pair: str, data: Any) -> None:
        """Simulate WebSocket producer writing to the ring buffer."""
        buf = self._buffers.get(pair)
        if buf is not None:
            buf.write(data)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ring() -> FakeRingDispatcher:
    return FakeRingDispatcher(buffer_size=256)


@pytest.fixture
def dispatcher(ring: FakeRingDispatcher) -> AsyncDispatcher:
    return AsyncDispatcher(ring, queue_maxsize=50, warn_every=10)


# ===========================================================================
# Construction
# ===========================================================================

class TestAsyncDispatcherInit:
    def test_initial_state(self, dispatcher: AsyncDispatcher) -> None:
        assert dispatcher.is_running() is False
        assert dispatcher._total_dispatched == 0
        assert dispatcher.stats["total_instances"] == 0
        assert dispatcher.stats["pairs"] == []

    def test_repr(self, dispatcher: AsyncDispatcher) -> None:
        r = repr(dispatcher)
        assert "AsyncDispatcher" in r
        assert "running=False" in r


# ===========================================================================
# subscribe()
# ===========================================================================

class TestSubscribe:
    async def test_subscribe_returns_instance_queue(self, dispatcher: AsyncDispatcher) -> None:
        queue = await dispatcher.subscribe("XBT/EUR", "inst-1")
        assert isinstance(queue, InstanceQueue)
        assert queue.instance_id == "inst-1"

    async def test_subscribe_creates_one_reader_per_pair(self, dispatcher: AsyncDispatcher) -> None:
        await dispatcher.subscribe("XBT/EUR", "inst-1")
        await dispatcher.subscribe("XBT/EUR", "inst-2")
        await dispatcher.subscribe("XBT/EUR", "inst-3")
        # Only ONE reader per pair regardless of instance count
        assert len(dispatcher._pair_readers) == 1
        assert "XBT/EUR" in dispatcher._pair_readers

    async def test_subscribe_different_pairs_create_separate_readers(
        self, dispatcher: AsyncDispatcher
    ) -> None:
        await dispatcher.subscribe("XBT/EUR", "inst-1")
        await dispatcher.subscribe("ETH/EUR", "inst-2")
        assert len(dispatcher._pair_readers) == 2

    async def test_subscribe_duplicate_instance_raises(self, dispatcher: AsyncDispatcher) -> None:
        await dispatcher.subscribe("XBT/EUR", "inst-1")
        with pytest.raises(RuntimeError, match="already subscribed"):
            await dispatcher.subscribe("XBT/EUR", "inst-1")

    async def test_subscribe_registers_queue_in_pair_routing_table(
        self, dispatcher: AsyncDispatcher
    ) -> None:
        await dispatcher.subscribe("XBT/EUR", "inst-1")
        await dispatcher.subscribe("XBT/EUR", "inst-2")
        assert len(dispatcher._pair_queues["XBT/EUR"]) == 2

    async def test_subscribe_populates_queues_dict(self, dispatcher: AsyncDispatcher) -> None:
        q = await dispatcher.subscribe("XBT/EUR", "inst-1")
        assert dispatcher.get_queue("inst-1") is q

    async def test_get_queue_returns_none_for_unknown(self, dispatcher: AsyncDispatcher) -> None:
        assert dispatcher.get_queue("nonexistent") is None

    async def test_subscribe_after_start_auto_launches_task(
        self, dispatcher: AsyncDispatcher
    ) -> None:
        """If already running, subscribing a new pair starts its dispatch task immediately."""
        await dispatcher.start()
        await dispatcher.subscribe("XBT/EUR", "inst-1")
        # Dispatch task should exist
        assert "XBT/EUR" in dispatcher._dispatch_tasks
        await dispatcher.stop()


# ===========================================================================
# unsubscribe()
# ===========================================================================

class TestUnsubscribe:
    async def test_unsubscribe_removes_queue(self, dispatcher: AsyncDispatcher) -> None:
        await dispatcher.subscribe("XBT/EUR", "inst-1")
        dispatcher.unsubscribe("inst-1")
        assert dispatcher.get_queue("inst-1") is None

    async def test_unsubscribe_removes_from_pair_routing(
        self, dispatcher: AsyncDispatcher
    ) -> None:
        await dispatcher.subscribe("XBT/EUR", "inst-1")
        await dispatcher.subscribe("XBT/EUR", "inst-2")
        dispatcher.unsubscribe("inst-1")
        assert len(dispatcher._pair_queues.get("XBT/EUR", [])) == 1

    async def test_unsubscribe_last_subscriber_removes_pair(
        self, dispatcher: AsyncDispatcher
    ) -> None:
        await dispatcher.subscribe("XBT/EUR", "inst-1")
        dispatcher.unsubscribe("inst-1")
        assert "XBT/EUR" not in dispatcher._pair_queues
        assert "XBT/EUR" not in dispatcher._pair_readers

    async def test_unsubscribe_last_subscriber_cancels_task(
        self, dispatcher: AsyncDispatcher
    ) -> None:
        await dispatcher.subscribe("XBT/EUR", "inst-1")
        await dispatcher.start()
        task = dispatcher._dispatch_tasks.get("XBT/EUR")
        assert task is not None
        assert not task.done()

        dispatcher.unsubscribe("inst-1")
        # Give the event loop a chance to process the cancellation
        await asyncio.sleep(0)
        assert "XBT/EUR" not in dispatcher._dispatch_tasks

    async def test_unsubscribe_nonexistent_is_silent(
        self, dispatcher: AsyncDispatcher
    ) -> None:
        # Should not raise
        dispatcher.unsubscribe("ghost-instance")

    async def test_unsubscribe_partial_keeps_pair_reader(
        self, dispatcher: AsyncDispatcher
    ) -> None:
        """When there are still subscribers, pair reader must remain."""
        await dispatcher.subscribe("XBT/EUR", "inst-1")
        await dispatcher.subscribe("XBT/EUR", "inst-2")
        dispatcher.unsubscribe("inst-1")
        # inst-2 still active → reader must survive
        assert "XBT/EUR" in dispatcher._pair_readers


# ===========================================================================
# Lifecycle (start / stop)
# ===========================================================================

class TestLifecycle:
    async def test_start_sets_running_true(self, dispatcher: AsyncDispatcher) -> None:
        await dispatcher.subscribe("XBT/EUR", "inst-1")
        await dispatcher.start()
        assert dispatcher.is_running() is True
        await dispatcher.stop()

    async def test_start_creates_dispatch_tasks(self, dispatcher: AsyncDispatcher) -> None:
        await dispatcher.subscribe("XBT/EUR", "inst-1")
        await dispatcher.subscribe("ETH/EUR", "inst-2")
        await dispatcher.start()
        assert "XBT/EUR" in dispatcher._dispatch_tasks
        assert "ETH/EUR" in dispatcher._dispatch_tasks
        await dispatcher.stop()

    async def test_start_idempotent(self, dispatcher: AsyncDispatcher) -> None:
        await dispatcher.subscribe("XBT/EUR", "inst-1")
        await dispatcher.start()
        await dispatcher.start()   # Second call must be no-op
        assert len(dispatcher._dispatch_tasks) == 1
        await dispatcher.stop()

    async def test_stop_sets_running_false(self, dispatcher: AsyncDispatcher) -> None:
        await dispatcher.subscribe("XBT/EUR", "inst-1")
        await dispatcher.start()
        await dispatcher.stop()
        assert dispatcher.is_running() is False

    async def test_stop_cancels_dispatch_tasks(self, dispatcher: AsyncDispatcher) -> None:
        await dispatcher.subscribe("XBT/EUR", "inst-1")
        await dispatcher.start()
        await dispatcher.stop()
        assert len(dispatcher._dispatch_tasks) == 0

    async def test_stop_drains_queues(self, dispatcher: AsyncDispatcher, ring: FakeRingDispatcher) -> None:
        """After stop(), all instance queues must be empty."""
        queue = await dispatcher.subscribe("XBT/EUR", "inst-1")

        # Manually pre-fill the queue to simulate backlog
        for i in range(20):
            queue.put_nowait_drop_oldest(FakeTick("XBT/EUR", float(i)))

        assert queue.qsize == 20
        await dispatcher.stop()
        assert queue.qsize == 0

    async def test_stop_no_subscribers_is_safe(self, dispatcher: AsyncDispatcher) -> None:
        """stop() on an idle dispatcher with no subscriptions must not crash."""
        await dispatcher.stop()  # No start(), no subscriptions


# ===========================================================================
# Dispatch correctness
# ===========================================================================

class TestDispatch:
    async def test_tick_reaches_queue(
        self, dispatcher: AsyncDispatcher, ring: FakeRingDispatcher
    ) -> None:
        """A tick written to the ring buffer arrives in the instance queue."""
        queue = await dispatcher.subscribe("XBT/EUR", "inst-1")
        await dispatcher.start()

        ring.write("XBT/EUR", FakeTick("XBT/EUR", 50_000.0))

        # Yield to the event loop so the dispatch loop can run
        for _ in range(3):
            await asyncio.sleep(0)

        assert queue.qsize >= 1
        msg = queue.get_nowait()
        assert msg.price == 50_000.0

        await dispatcher.stop()

    async def test_fan_out_multiple_instances_same_pair(
        self, dispatcher: AsyncDispatcher, ring: FakeRingDispatcher
    ) -> None:
        """One tick must be delivered to ALL instances on the same pair."""
        q1 = await dispatcher.subscribe("XBT/EUR", "inst-1")
        q2 = await dispatcher.subscribe("XBT/EUR", "inst-2")
        q3 = await dispatcher.subscribe("XBT/EUR", "inst-3")
        await dispatcher.start()

        ring.write("XBT/EUR", FakeTick("XBT/EUR", 51_000.0))
        for _ in range(3):
            await asyncio.sleep(0)

        assert q1.qsize >= 1
        assert q2.qsize >= 1
        assert q3.qsize >= 1

        await dispatcher.stop()

    async def test_pair_isolation(
        self, dispatcher: AsyncDispatcher, ring: FakeRingDispatcher
    ) -> None:
        """XBT/EUR tick must NOT reach ETH/EUR queue."""
        q_xbt = await dispatcher.subscribe("XBT/EUR", "inst-xbt")
        q_eth = await dispatcher.subscribe("ETH/EUR", "inst-eth")
        await dispatcher.start()

        ring.write("XBT/EUR", FakeTick("XBT/EUR", 50_000.0))
        for _ in range(3):
            await asyncio.sleep(0)

        assert q_xbt.qsize >= 1
        assert q_eth.qsize == 0  # No ETH tick written

        await dispatcher.stop()

    async def test_multiple_ticks_ordered(
        self, dispatcher: AsyncDispatcher, ring: FakeRingDispatcher
    ) -> None:
        """Multiple ticks must arrive in chronological order."""
        queue = await dispatcher.subscribe("XBT/EUR", "inst-1")
        await dispatcher.start()

        prices = [49_000.0, 49_001.0, 49_002.0, 49_003.0, 49_004.0]
        for p in prices:
            ring.write("XBT/EUR", FakeTick("XBT/EUR", p))

        # Let the dispatch loop drain the ring
        for _ in range(10):
            await asyncio.sleep(0)

        received = []
        while queue.qsize > 0:
            received.append(queue.get_nowait().price)

        assert received == prices

        await dispatcher.stop()

    async def test_backpressure_no_crash(
        self, dispatcher: AsyncDispatcher, ring: FakeRingDispatcher
    ) -> None:
        """Queue overflow must never crash the dispatcher (drop silently)."""
        queue = await dispatcher.subscribe("XBT/EUR", "inst-slow")
        await dispatcher.start()

        # Write 10× the queue capacity
        capacity = queue.maxsize
        for i in range(capacity * 10):
            ring.write("XBT/EUR", FakeTick("XBT/EUR", float(i)))

        # Let the dispatch loop run
        for _ in range(20):
            await asyncio.sleep(0)

        # Dispatcher must still be alive
        assert dispatcher.is_running() is True
        # Queue must not exceed its limit
        assert queue.qsize <= capacity
        # Some drops should have occurred
        assert queue.drop_count > 0

        await dispatcher.stop()

    async def test_total_dispatched_counter_increments(
        self, dispatcher: AsyncDispatcher, ring: FakeRingDispatcher
    ) -> None:
        await dispatcher.subscribe("XBT/EUR", "inst-1")
        await dispatcher.start()

        n_ticks = 5
        for i in range(n_ticks):
            ring.write("XBT/EUR", FakeTick("XBT/EUR", float(i)))

        for _ in range(10):
            await asyncio.sleep(0)

        assert dispatcher._total_dispatched >= n_ticks
        await dispatcher.stop()


# ===========================================================================
# stats dict
# ===========================================================================

class TestStats:
    async def test_stats_structure(self, dispatcher: AsyncDispatcher) -> None:
        await dispatcher.subscribe("XBT/EUR", "inst-1")
        s = dispatcher.stats
        assert "running" in s
        assert "pairs" in s
        assert "dispatch_tasks" in s
        assert "total_instances" in s
        assert "total_dispatched" in s
        assert "total_enqueued" in s
        assert "total_dropped" in s
        assert "drop_ratio" in s
        assert "queues" in s

    async def test_stats_total_instances(self, dispatcher: AsyncDispatcher) -> None:
        await dispatcher.subscribe("XBT/EUR", "inst-1")
        await dispatcher.subscribe("ETH/EUR", "inst-2")
        assert dispatcher.stats["total_instances"] == 2

    async def test_stats_pairs_list(self, dispatcher: AsyncDispatcher) -> None:
        await dispatcher.subscribe("XBT/EUR", "inst-1")
        await dispatcher.subscribe("ETH/EUR", "inst-2")
        pairs = dispatcher.stats["pairs"]
        assert "XBT/EUR" in pairs
        assert "ETH/EUR" in pairs

    async def test_stats_running_false_before_start(self, dispatcher: AsyncDispatcher) -> None:
        assert dispatcher.stats["running"] is False

    async def test_stats_running_true_after_start(self, dispatcher: AsyncDispatcher) -> None:
        await dispatcher.subscribe("XBT/EUR", "inst-1")
        await dispatcher.start()
        assert dispatcher.stats["running"] is True
        await dispatcher.stop()


# ===========================================================================
# Integration: end-to-end with TradingInstanceAsync stub
# ===========================================================================

class FakeInstance:
    """Minimal stand-in for TradingInstanceAsync — records received ticks."""

    def __init__(self, instance_id: str) -> None:
        self.id = instance_id
        self._queue: Optional[InstanceQueue] = None
        self.received: List[FakeTick] = []
        self._consumer_task: Optional[asyncio.Task] = None

    def attach_queue(self, queue: InstanceQueue) -> None:
        self._queue = queue

    async def start_queue_consumer(self) -> None:
        self._consumer_task = asyncio.create_task(
            self._consume_loop(), name=f"consumer-{self.id}"
        )

    async def _consume_loop(self) -> None:
        assert self._queue is not None
        try:
            while True:
                data = await self._queue.get()
                self.received.append(data)
        except asyncio.CancelledError:
            pass

    async def stop(self) -> None:
        if self._consumer_task and not self._consumer_task.done():
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass


class TestEndToEnd:
    async def test_full_flow_single_instance(
        self, dispatcher: AsyncDispatcher, ring: FakeRingDispatcher
    ) -> None:
        """
        Complete flow: subscribe → attach_queue → start consumer →
        write ticks → consumer receives them.
        """
        instance = FakeInstance("e2e-1")

        queue = await dispatcher.subscribe("XBT/EUR", "e2e-1")
        instance.attach_queue(queue)
        await instance.start_queue_consumer()
        await dispatcher.start()

        ticks = [FakeTick("XBT/EUR", float(50_000 + i)) for i in range(5)]
        for t in ticks:
            ring.write("XBT/EUR", t)

        # Wait for consumer to process all ticks
        for _ in range(20):
            await asyncio.sleep(0)
            if len(instance.received) >= 5:
                break

        assert len(instance.received) == 5
        assert [t.price for t in instance.received] == [50_000.0 + i for i in range(5)]

        await instance.stop()
        await dispatcher.stop()

    async def test_full_flow_two_instances_same_pair(
        self, dispatcher: AsyncDispatcher, ring: FakeRingDispatcher
    ) -> None:
        """Both instances on XBT/EUR receive all ticks."""
        inst_a = FakeInstance("e2e-a")
        inst_b = FakeInstance("e2e-b")

        for inst in (inst_a, inst_b):
            q = await dispatcher.subscribe("XBT/EUR", inst.id)
            inst.attach_queue(q)
            await inst.start_queue_consumer()

        await dispatcher.start()

        n_ticks = 10
        for i in range(n_ticks):
            ring.write("XBT/EUR", FakeTick("XBT/EUR", float(i)))

        for _ in range(30):
            await asyncio.sleep(0)
            if len(inst_a.received) >= n_ticks and len(inst_b.received) >= n_ticks:
                break

        assert len(inst_a.received) == n_ticks
        assert len(inst_b.received) == n_ticks

        for inst in (inst_a, inst_b):
            await inst.stop()
        await dispatcher.stop()

    async def test_multi_pair_isolation_full_flow(
        self, dispatcher: AsyncDispatcher, ring: FakeRingDispatcher
    ) -> None:
        """XBT instance receives only XBT ticks; ETH instance receives only ETH ticks."""
        inst_xbt = FakeInstance("e2e-xbt")
        inst_eth = FakeInstance("e2e-eth")

        q_xbt = await dispatcher.subscribe("XBT/EUR", "e2e-xbt")
        q_eth = await dispatcher.subscribe("ETH/EUR", "e2e-eth")
        inst_xbt.attach_queue(q_xbt)
        inst_eth.attach_queue(q_eth)
        await inst_xbt.start_queue_consumer()
        await inst_eth.start_queue_consumer()
        await dispatcher.start()

        ring.write("XBT/EUR", FakeTick("XBT/EUR", 50_000.0))
        ring.write("ETH/EUR", FakeTick("ETH/EUR", 3_000.0))

        for _ in range(15):
            await asyncio.sleep(0)

        # Each instance received exactly its pair
        assert any(t.pair == "XBT/EUR" for t in inst_xbt.received)
        assert all(t.pair == "XBT/EUR" for t in inst_xbt.received)
        assert any(t.pair == "ETH/EUR" for t in inst_eth.received)
        assert all(t.pair == "ETH/EUR" for t in inst_eth.received)

        for inst in (inst_xbt, inst_eth):
            await inst.stop()
        await dispatcher.stop()

    async def test_graceful_shutdown_no_data_loss(
        self, dispatcher: AsyncDispatcher, ring: FakeRingDispatcher
    ) -> None:
        """
        After stop(), queue consumer is cancelled cleanly;
        dispatcher is quiescent (no running tasks).
        """
        queue = await dispatcher.subscribe("XBT/EUR", "e2e-shutdown")
        await dispatcher.start()

        # Write some ticks
        for i in range(5):
            ring.write("XBT/EUR", FakeTick("XBT/EUR", float(i)))

        await dispatcher.stop()

        # After stop: no running dispatch tasks
        assert not dispatcher._dispatch_tasks
        # Queues drained
        assert queue.qsize == 0


# ===========================================================================
# Performance (smoke)
# ===========================================================================

class TestDispatchPerformance:
    def test_put_nowait_throughput(self) -> None:
        """
        put_nowait_drop_oldest should handle at least 500K ops/sec.
        This tests the hot-path independently of the async dispatch loop.
        """
        q = InstanceQueue("perf", maxsize=65536)
        n = 100_000
        data = FakeTick("XBT/EUR", 50_000.0)

        t0 = time.perf_counter_ns()
        for _ in range(n):
            q.put_nowait_drop_oldest(data)
        elapsed_ns = time.perf_counter_ns() - t0

        ns_per_op = elapsed_ns / n
        ops_per_sec = 1e9 / ns_per_op if ns_per_op > 0 else float("inf")

        print(f"\n  put_nowait throughput: {ops_per_sec:,.0f} ops/sec "
              f"({ns_per_op:.0f} ns/op)")

        # Minimum bar: 500K ops/sec (generous for CI environments)
        assert ops_per_sec > 500_000, (
            f"Throughput too low: {ops_per_sec:,.0f} ops/sec (goal >500K)"
        )
