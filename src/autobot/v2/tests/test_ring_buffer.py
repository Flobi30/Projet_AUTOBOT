"""
Tests P2 — RingBuffer + RingBufferDispatcher

Coverage:
    Correctness:
        - Single write / single read
        - Sequential ordering across N writes
        - Multiple independent readers
        - Overwrite (slow consumer) detection and auto-recovery
        - RingBufferReader.lag and skip_to_latest
        - poll_batch returns items in order
        - start_at_tail=False reads history

    Edge cases:
        - Buffer size 1 (minimum power-of-2)
        - Write exactly size times (full wrap)
        - Reader that never reads (full overflow recovery)
        - reset_to()

    Performance benchmarks:
        - write() latency (single, batch-amortised)
        - read_at() / poll() latency
        - poll_batch() amortised ns/msg
        - round-trip (write → poll)
        Reported as ns/op.  Targets:
            ring_buffer write : goal <1 µs  (CPython practical limit)
            ring_buffer read  : goal <500 ns
            poll_batch/msg    : goal <200 ns/msg (amortised)
"""

from __future__ import annotations

import asyncio
import sys
import time
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit

sys.path.insert(0, "/home/node/.openclaw/workspace/src")

from autobot.v2.ring_buffer import RingBuffer, RingBufferReader, DEFAULT_BUFFER_SIZE

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ticker(pair: str = "XBT/EUR", price: float = 50_000.0) -> Any:
    """Minimal stand-in for TickerData (avoids importing WS client in perf path)."""
    return {"pair": pair, "price": price}


# ---------------------------------------------------------------------------
# RingBuffer — correctness
# ---------------------------------------------------------------------------


class TestRingBufferInit:
    def test_default_size(self) -> None:
        ring = RingBuffer()
        assert ring.size == DEFAULT_BUFFER_SIZE
        assert ring.write_seq == 0

    def test_custom_power_of_two(self) -> None:
        for exp in range(0, 17):
            size = 1 << exp
            ring = RingBuffer(size)
            assert ring.size == size

    def test_non_power_of_two_raises(self) -> None:
        for bad in (0, -1, 3, 7, 100, 1000):
            with pytest.raises(ValueError):
                RingBuffer(bad)


class TestRingBufferWrite:
    def test_write_returns_seq(self) -> None:
        ring = RingBuffer(8)
        for i in range(8):
            assert ring.write(f"msg-{i}") == i

    def test_write_seq_advances(self) -> None:
        ring = RingBuffer(8)
        ring.write("a")
        ring.write("b")
        assert ring.write_seq == 2

    def test_slot_contains_latest_write(self) -> None:
        ring = RingBuffer(8)
        ring.write("first")
        ring.write("second")
        # Slot 0 should still hold "first"
        assert ring._slots[0] == "first"
        assert ring._slots[1] == "second"

    def test_wrap_overwrites_oldest(self) -> None:
        ring = RingBuffer(4)
        for i in range(4):
            ring.write(i)
        # Slot 0 currently holds 0; next write wraps to slot 0
        ring.write(99)
        assert ring._slots[0] == 99
        assert ring.write_seq == 5


class TestRingBufferReadAt:
    def test_read_empty(self) -> None:
        ring = RingBuffer(8)
        ok, data = ring.read_at(0)
        assert not ok
        assert data is None

    def test_read_written_slot(self) -> None:
        ring = RingBuffer(8)
        ring.write("hello")
        ok, data = ring.read_at(0)
        assert ok
        assert data == "hello"

    def test_read_sequential(self) -> None:
        ring = RingBuffer(8)
        items = ["a", "b", "c", "d"]
        for item in items:
            ring.write(item)
        for i, item in enumerate(items):
            ok, data = ring.read_at(i)
            assert ok
            assert data == item

    def test_read_overwritten_slot(self) -> None:
        ring = RingBuffer(4)
        for i in range(5):   # Writes seq 0-4; seq=0 overwritten at seq=4
            ring.write(i)
        # Slot 0 now holds seq=4 data; reading at seq=0 should fail (overwrite)
        ok, data = ring.read_at(0)
        assert not ok

    def test_read_future_seq_returns_false(self) -> None:
        ring = RingBuffer(8)
        ring.write("x")
        ok, _ = ring.read_at(1)  # seq=1 not written yet
        assert not ok


# ---------------------------------------------------------------------------
# RingBufferReader — correctness
# ---------------------------------------------------------------------------


class TestRingBufferReaderPoll:
    def test_poll_empty_returns_none(self) -> None:
        ring = RingBuffer(8)
        reader = RingBufferReader(ring, start_at_tail=False)
        assert reader.poll() is None

    def test_poll_returns_item(self) -> None:
        ring = RingBuffer(8)
        reader = RingBufferReader(ring, start_at_tail=False)
        ring.write("hello")
        assert reader.poll() == "hello"
        assert reader.poll() is None  # Only one item

    def test_poll_sequential_ordering(self) -> None:
        ring = RingBuffer(16)
        reader = RingBufferReader(ring, start_at_tail=False)
        expected = list(range(10))
        for v in expected:
            ring.write(v)
        received = [reader.poll() for _ in range(10)]
        assert received == expected

    def test_start_at_tail_skips_history(self) -> None:
        ring = RingBuffer(8)
        ring.write("old")
        reader = RingBufferReader(ring, start_at_tail=True)
        assert reader.poll() is None  # "old" was written before reader attached

    def test_start_at_tail_false_reads_history(self) -> None:
        ring = RingBuffer(8)
        ring.write("history")
        reader = RingBufferReader(ring, start_at_tail=False)
        assert reader.poll() == "history"

    def test_poll_advances_cursor(self) -> None:
        ring = RingBuffer(8)
        reader = RingBufferReader(ring, start_at_tail=False)
        ring.write("a")
        ring.write("b")
        reader.poll()
        assert reader.read_seq == 1
        reader.poll()
        assert reader.read_seq == 2


class TestRingBufferReaderPollBatch:
    def test_batch_empty(self) -> None:
        ring = RingBuffer(8)
        reader = RingBufferReader(ring, start_at_tail=False)
        assert reader.poll_batch(16) == []

    def test_batch_all_items(self) -> None:
        ring = RingBuffer(16)
        reader = RingBufferReader(ring, start_at_tail=False)
        for i in range(10):
            ring.write(i)
        result = reader.poll_batch(16)
        assert result == list(range(10))

    def test_batch_respects_max(self) -> None:
        ring = RingBuffer(16)
        reader = RingBufferReader(ring, start_at_tail=False)
        for i in range(10):
            ring.write(i)
        result = reader.poll_batch(3)
        assert result == [0, 1, 2]
        assert reader.read_seq == 3

    def test_batch_cursor_advance(self) -> None:
        ring = RingBuffer(16)
        reader = RingBufferReader(ring, start_at_tail=False)
        for i in range(5):
            ring.write(i)
        reader.poll_batch(5)
        assert reader.read_seq == 5

    def test_batch_recovers_from_overflow(self) -> None:
        ring = RingBuffer(4)
        reader = RingBufferReader(ring, start_at_tail=False)
        # Fill buffer twice without reading (overflow)
        for i in range(8):
            ring.write(i)
        # Lag == 8, buffer.size == 4 → overflow
        assert reader.lag == 8
        result = reader.poll_batch(8)
        # Should recover: skip to seq 4, read seq 4-7
        assert len(result) == 4
        assert result == [4, 5, 6, 7]


class TestRingBufferReaderLag:
    def test_lag_zero_at_start(self) -> None:
        ring = RingBuffer(8)
        reader = RingBufferReader(ring, start_at_tail=True)
        assert reader.lag == 0

    def test_lag_increases_with_writes(self) -> None:
        ring = RingBuffer(8)
        reader = RingBufferReader(ring, start_at_tail=True)
        for i in range(5):
            ring.write(i)
        assert reader.lag == 5

    def test_lag_decreases_after_read(self) -> None:
        ring = RingBuffer(8)
        reader = RingBufferReader(ring, start_at_tail=False)
        for i in range(4):
            ring.write(i)
        reader.poll()
        assert reader.lag == 3


class TestRingBufferReaderSkip:
    def test_skip_to_latest(self) -> None:
        ring = RingBuffer(8)
        reader = RingBufferReader(ring, start_at_tail=False)
        for i in range(5):
            ring.write(i)
        skipped = reader.skip_to_latest()
        assert skipped == 5
        assert reader.lag == 0
        assert reader.poll() is None

    def test_reset_to(self) -> None:
        ring = RingBuffer(16)
        for i in range(8):
            ring.write(i)
        reader = RingBufferReader(ring, start_at_tail=True)
        reader.reset_to(3)
        assert reader.read_seq == 3
        result = reader.poll_batch(16)
        assert result == [3, 4, 5, 6, 7]


class TestMultipleReaders:
    def test_independent_cursors(self) -> None:
        ring = RingBuffer(16)
        r1 = RingBufferReader(ring, start_at_tail=False)
        r2 = RingBufferReader(ring, start_at_tail=False)
        for i in range(4):
            ring.write(i)
        # r1 reads 2, r2 reads all 4
        r1.poll_batch(2)
        assert r1.read_seq == 2
        assert r2.read_seq == 0

        r2_data = r2.poll_batch(4)
        assert r2_data == [0, 1, 2, 3]
        # r1 can still read the remaining 2
        r1_data = r1.poll_batch(4)
        assert r1_data == [2, 3]

    def test_readers_see_same_data(self) -> None:
        ring = RingBuffer(16)
        r1 = RingBufferReader(ring, start_at_tail=False)
        r2 = RingBufferReader(ring, start_at_tail=False)
        items = ["x", "y", "z"]
        for item in items:
            ring.write(item)
        assert r1.poll_batch(3) == items
        assert r2.poll_batch(3) == items

    def test_slow_reader_does_not_block_fast_reader(self) -> None:
        ring = RingBuffer(8)
        fast = RingBufferReader(ring, start_at_tail=False)
        _slow = RingBufferReader(ring, start_at_tail=False)  # noqa: never polled

        for i in range(8):
            ring.write(i)

        # Fast reader polls all; slow reader is stuck but doesn't affect fast
        fast_data = fast.poll_batch(8)
        assert fast_data == list(range(8))

    def test_n_readers_1000(self) -> None:
        ring = RingBuffer(64)
        readers = [RingBufferReader(ring, start_at_tail=False) for _ in range(1000)]
        for i in range(10):
            ring.write(i)
        for reader in readers:
            data = reader.poll_batch(10)
            assert data == list(range(10))


# ---------------------------------------------------------------------------
# Async integration: RingBufferDispatcher
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatcher_subscribe_and_read() -> None:
    """End-to-end: subscribe, write ticker, consumer reads it."""
    from autobot.v2.ring_buffer_dispatcher import RingBufferDispatcher
    from autobot.v2.websocket_async import TickerData

    dispatcher = RingBufferDispatcher(buffer_size=256)

    # Patch the WS client so no real connection is made
    dispatcher._ws = MagicMock()
    dispatcher._ws.add_ticker_callback = MagicMock()
    dispatcher._ws.subscribe_ticker = AsyncMock()
    dispatcher._ws.is_connected = MagicMock(return_value=True)

    reader = await dispatcher.subscribe("XBT/EUR", "inst-001")
    assert reader.lag == 0

    # Simulate WS tick
    ticker = TickerData(
        symbol="XBT/EUR",
        price=50_000.0,
        bid=49_990.0,
        ask=50_010.0,
        volume_24h=100.0,
        timestamp=datetime.now(timezone.utc),
    )
    dispatcher._write_ticker("XBT/EUR", ticker)

    data = reader.poll()
    assert data is ticker  # Zero-copy: same object reference


@pytest.mark.asyncio
async def test_dispatcher_run_consumer() -> None:
    """run_consumer calls callback for each message then cancels cleanly."""
    from autobot.v2.ring_buffer_dispatcher import RingBufferDispatcher
    from autobot.v2.websocket_async import TickerData

    dispatcher = RingBufferDispatcher(buffer_size=256)
    dispatcher._ws = MagicMock()
    dispatcher._ws.add_ticker_callback = MagicMock()
    dispatcher._ws.subscribe_ticker = AsyncMock()

    received: list[TickerData] = []
    await dispatcher.subscribe("ETH/EUR", "inst-002")

    async def _cb(data: TickerData) -> None:
        received.append(data)
        if len(received) >= 3:
            raise asyncio.CancelledError  # Stop after 3 messages

    ticker = TickerData(
        symbol="ETH/EUR",
        price=3_000.0,
        bid=2_999.0,
        ask=3_001.0,
        volume_24h=50.0,
        timestamp=datetime.now(timezone.utc),
    )
    for _ in range(3):
        dispatcher._write_ticker("ETH/EUR", ticker)

    with pytest.raises(asyncio.CancelledError):
        await dispatcher.run_consumer("inst-002", _cb)

    assert len(received) == 3


@pytest.mark.asyncio
async def test_dispatcher_multiple_instances_same_pair() -> None:
    """2000 readers on the same pair all receive the same message."""
    from autobot.v2.ring_buffer_dispatcher import RingBufferDispatcher
    from autobot.v2.websocket_async import TickerData

    N = 2000
    dispatcher = RingBufferDispatcher(buffer_size=DEFAULT_BUFFER_SIZE)
    dispatcher._ws = MagicMock()
    dispatcher._ws.add_ticker_callback = MagicMock()
    dispatcher._ws.subscribe_ticker = AsyncMock()

    readers = []
    for i in range(N):
        r = await dispatcher.subscribe("XBT/EUR", f"inst-{i:04d}")
        readers.append(r)

    ticker = TickerData(
        symbol="XBT/EUR",
        price=60_000.0,
        bid=59_990.0,
        ask=60_010.0,
        volume_24h=200.0,
        timestamp=datetime.now(timezone.utc),
    )
    dispatcher._write_ticker("XBT/EUR", ticker)

    assert dispatcher._write_count == 1
    for reader in readers:
        data = reader.poll()
        assert data is ticker


@pytest.mark.asyncio
async def test_dispatcher_unsubscribe() -> None:
    """Unsubscribed instance no longer appears in readers."""
    from autobot.v2.ring_buffer_dispatcher import RingBufferDispatcher

    dispatcher = RingBufferDispatcher(buffer_size=16)
    dispatcher._ws = MagicMock()
    dispatcher._ws.add_ticker_callback = MagicMock()
    dispatcher._ws.subscribe_ticker = AsyncMock()

    await dispatcher.subscribe("SOL/EUR", "inst-x")
    assert "inst-x" in dispatcher._readers
    dispatcher.unsubscribe("inst-x")
    assert "inst-x" not in dispatcher._readers


# ---------------------------------------------------------------------------
# Performance benchmarks
# ---------------------------------------------------------------------------


def _bench(label: str, fn, iterations: int = 100_000) -> float:
    """Run *fn* for *iterations*, return ns/op and print result."""
    # Warm up
    for _ in range(min(1000, iterations // 10)):
        fn()

    t0 = time.perf_counter_ns()
    for _ in range(iterations):
        fn()
    elapsed_ns = time.perf_counter_ns() - t0
    ns_per_op = elapsed_ns / iterations
    print(f"  {label:<40s}  {ns_per_op:>8.1f} ns/op")
    return ns_per_op


class TestRingBufferPerformance:
    """
    Latency benchmarks — printed in verbose mode (pytest -v -s).

    CPython 3.11 indicative targets:
        write()                :  <500 ns
        read_at()              :  <300 ns
        poll() (hit)           :  <400 ns
        poll_batch(64)/msg     :  <200 ns/msg   (amortised)
        write + poll round-trip:  <800 ns
    """

    ITERATIONS = 200_000
    BATCH_SIZE = 64

    def test_write_latency(self) -> None:
        ring = RingBuffer(DEFAULT_BUFFER_SIZE)
        data = _make_ticker()
        ns = _bench("RingBuffer.write()", lambda: ring.write(data), self.ITERATIONS)
        # Practical Python limit — not enforcing <100 ns which is C territory
        assert ns < 10_000, f"write too slow: {ns:.0f} ns/op (expected <10 µs)"

    def test_read_at_latency(self) -> None:
        ring = RingBuffer(DEFAULT_BUFFER_SIZE)
        data = _make_ticker()
        for _ in range(self.ITERATIONS):
            ring.write(data)
        seq = 0

        def _read() -> None:
            nonlocal seq
            ring.read_at(seq % ring.write_seq)
            seq += 1

        ns = _bench("RingBuffer.read_at()", _read, self.ITERATIONS)
        assert ns < 10_000, f"read_at too slow: {ns:.0f} ns/op"

    def test_poll_hit_latency(self) -> None:
        ring = RingBuffer(DEFAULT_BUFFER_SIZE)
        data = _make_ticker()
        reader = RingBufferReader(ring, start_at_tail=False)

        # Keep writing ahead of reader so poll() always hits
        def _write_and_poll() -> None:
            ring.write(data)
            reader.poll()

        ns = _bench("write + poll() round-trip", _write_and_poll, self.ITERATIONS)
        assert ns < 20_000, f"round-trip too slow: {ns:.0f} ns/op"

    def test_poll_batch_amortised_latency(self) -> None:
        ring = RingBuffer(DEFAULT_BUFFER_SIZE)
        data = _make_ticker()
        reader = RingBufferReader(ring, start_at_tail=False)
        bs = self.BATCH_SIZE

        # Pre-fill the buffer
        for _ in range(bs):
            ring.write(data)

        total_ns = 0
        total_msgs = 0
        iterations = self.ITERATIONS // bs

        for _ in range(iterations):
            # Refill bs messages
            for _ in range(bs):
                ring.write(data)

            t0 = time.perf_counter_ns()
            msgs = reader.poll_batch(bs)
            total_ns += time.perf_counter_ns() - t0
            total_msgs += len(msgs)

        ns_per_msg = total_ns / total_msgs if total_msgs else float("inf")
        print(
            f"\n  {'poll_batch({bs})/msg':<40s}  {ns_per_msg:>8.1f} ns/msg "
            f"({total_msgs:,} msgs total)"
        )
        assert ns_per_msg < 10_000, f"poll_batch too slow: {ns_per_msg:.0f} ns/msg"

    def test_throughput_2000_readers(self) -> None:
        """Simulate 2000 instances polling 1 write per tick."""
        N_READERS = 2000
        N_TICKS = 1_000
        data = _make_ticker()
        ring = RingBuffer(DEFAULT_BUFFER_SIZE)
        readers = [RingBufferReader(ring, start_at_tail=True) for _ in range(N_READERS)]

        t0 = time.perf_counter_ns()
        for _ in range(N_TICKS):
            ring.write(data)
            for reader in readers:
                reader.poll()
        elapsed_ns = time.perf_counter_ns() - t0

        ticks_per_sec = N_TICKS * 1e9 / elapsed_ns
        ns_per_dispatch = elapsed_ns / (N_TICKS * N_READERS)
        print(
            f"\n  2000 readers × {N_TICKS} ticks:  "
            f"{ticks_per_sec:,.0f} ticks/s, "
            f"{ns_per_dispatch:.1f} ns/reader/tick"
        )
        # At 2000 readers × 1000 ticks, total latency should be reasonable
        assert elapsed_ns < 60_000_000_000, "2000-reader benchmark too slow"
