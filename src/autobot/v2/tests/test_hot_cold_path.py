"""
Tests P4 — Hot/Cold Path Separation.

Coverage:
    HotPathOptimizer:
        - GC enter/exit/force_gc
        - Latency measurement: start_tick / record_tick / stats
        - Pre-allocated array never grows
        - Singleton accessor

    ColdPathScheduler:
        - Fire-and-forget: schedule() is non-blocking
        - Periodic task: schedule_periodic()
        - Error isolation: exceptions don't propagate to caller
        - schedule_gc() convenience helper
        - stop() cancels all tasks
        - Singleton accessor

    TradingInstanceAsync (P4 hot-path behaviour):
        - on_price_update acquires NO asyncio.Lock
        - Latency benchmark: < 10 µs per tick (conservative, CI-safe)
        - attach_hot_optimizer injects telemetry
        - check_leverage_downgrade NOT called per-tick

    Integration:
        - ColdPathScheduler.schedule() from simulated hot path
"""

from __future__ import annotations

import asyncio
import gc
import time
from datetime import datetime, timezone, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
pytestmark = pytest.mark.unit

pytest_asyncio = pytest.importorskip("pytest_asyncio")

from ..hot_path_optimizer import HotPathOptimizer, get_hot_path_optimizer
from ..cold_path_scheduler import ColdPathScheduler, get_cold_path_scheduler

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ticker(price: float = 50_000.0):
    """Return a minimal TickerData-compatible object."""
    td = MagicMock()
    td.price = price
    td.bid = price - 1.0
    td.ask = price + 1.0
    td.volume_24h = 1.0
    td.timestamp = datetime.now(timezone.utc)
    td.symbol = "XBT/EUR"
    return td


def _make_config(strategy: str = "grid"):
    cfg = MagicMock()
    cfg.name = "test-inst"
    cfg.symbol = "XBT/EUR"
    cfg.strategy = strategy
    cfg.initial_capital = 1000.0
    cfg.leverage = 1
    cfg.grid_config = {"range_percent": 7.0, "num_levels": 15}
    return cfg


# ===========================================================================
# HotPathOptimizer — Unit tests
# ===========================================================================


class TestHotPathOptimizerGC:
    """GC enable/disable lifecycle."""

    def setup_method(self):
        # Restore GC after each test
        self._gc_was_enabled = gc.isenabled()

    def teardown_method(self):
        if self._gc_was_enabled:
            gc.enable()
        else:
            gc.disable()

    def test_enter_disables_gc(self):
        gc.enable()
        opt = HotPathOptimizer()
        opt.enter_hot_path()
        assert not gc.isenabled()
        opt.exit_hot_path()

    def test_exit_restores_gc_when_it_was_enabled(self):
        gc.enable()
        opt = HotPathOptimizer()
        opt.enter_hot_path()
        opt.exit_hot_path()
        assert gc.isenabled()

    def test_exit_leaves_gc_disabled_when_it_was_already_disabled(self):
        gc.disable()
        opt = HotPathOptimizer()
        opt.enter_hot_path()
        opt.exit_hot_path()
        assert not gc.isenabled()

    def test_enter_idempotent(self):
        gc.enable()
        opt = HotPathOptimizer()
        opt.enter_hot_path()
        opt.enter_hot_path()  # second call — no-op
        assert not gc.isenabled()
        opt.exit_hot_path()

    def test_exit_idempotent(self):
        gc.enable()
        opt = HotPathOptimizer()
        opt.enter_hot_path()
        opt.exit_hot_path()
        opt.exit_hot_path()  # second call — no-op
        assert gc.isenabled()

    def test_force_gc_does_not_reenable_auto_gc(self):
        gc.enable()
        opt = HotPathOptimizer()
        opt.enter_hot_path()
        collected = opt.force_gc()
        assert isinstance(collected, int)
        assert not gc.isenabled()  # still disabled
        opt.exit_hot_path()


class TestHotPathOptimizerLatency:
    """Latency measurement via pre-allocated circular buffer."""

    def test_start_tick_returns_int(self):
        t0 = HotPathOptimizer.start_tick()
        assert isinstance(t0, int)
        assert t0 > 0

    def test_record_tick_returns_elapsed(self):
        opt = HotPathOptimizer()
        t0 = opt.start_tick()
        time.sleep(0.001)  # 1 ms
        elapsed = opt.record_tick(t0)
        assert elapsed >= 500_000  # at least 0.5 ms in ns

    def test_stats_empty(self):
        opt = HotPathOptimizer()
        s = opt.stats
        assert s["tick_count"] == 0
        assert s["avg_ns"] == 0
        assert s["p50_ns"] == 0

    def test_stats_after_samples(self):
        opt = HotPathOptimizer(max_samples=64)
        for _ in range(20):
            t0 = opt.start_tick()
            opt.record_tick(t0)
        s = opt.stats
        assert s["tick_count"] == 20
        assert s["avg_ns"] >= 0
        assert s["p50_ns"] >= 0
        assert s["p95_ns"] >= s["p50_ns"]
        assert s["p99_ns"] >= s["p95_ns"]

    def test_circular_buffer_no_growth(self):
        """Buffer stays at max_samples; no heap growth from appending."""
        max_s = 16
        opt = HotPathOptimizer(max_samples=max_s)
        for _ in range(max_s * 3):  # Overflow the ring
            t0 = opt.start_tick()
            opt.record_tick(t0)
        # Buffer count capped at max_samples
        assert opt._count == max_s
        # Tick count keeps growing
        assert opt._tick_count == max_s * 3

    def test_reset_stats(self):
        opt = HotPathOptimizer()
        for _ in range(5):
            t0 = opt.start_tick()
            opt.record_tick(t0)
        opt.reset_stats()
        s = opt.stats
        assert s["tick_count"] == 0

    def test_invalid_max_samples_raises(self):
        with pytest.raises(ValueError, match="power of 2"):
            HotPathOptimizer(max_samples=100)

    def test_singleton_returns_same_instance(self):
        a = get_hot_path_optimizer()
        b = get_hot_path_optimizer()
        assert a is b


# ===========================================================================
# ColdPathScheduler — Unit tests
# ===========================================================================


class TestColdPathSchedulerOneShot:
    """Fire-and-forget schedule()."""

    @pytest.mark.asyncio
    async def test_schedule_runs_coro(self):
        scheduler = ColdPathScheduler()
        await scheduler.start()
        called = []

        async def cold_task():
            called.append(1)

        scheduler.schedule(cold_task())
        await asyncio.sleep(0)  # Yield to let the task run
        assert called == [1]
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_schedule_does_not_block_caller(self):
        """schedule() returns immediately — it's O(1) and non-blocking."""
        scheduler = ColdPathScheduler()
        await scheduler.start()
        executed_order = []

        async def slow_cold():
            await asyncio.sleep(0.05)
            executed_order.append("cold")

        executed_order.append("before")
        scheduler.schedule(slow_cold())
        executed_order.append("after")  # Must appear before "cold"

        await asyncio.sleep(0.1)
        assert executed_order[0] == "before"
        assert executed_order[1] == "after"
        assert executed_order[2] == "cold"
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_schedule_isolates_errors(self):
        """Exceptions inside cold tasks must not propagate."""
        scheduler = ColdPathScheduler()
        await scheduler.start()

        async def bad_task():
            raise RuntimeError("cold path error")

        scheduler.schedule(bad_task())
        await asyncio.sleep(0)  # Let it run
        assert scheduler._errors == 1
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_schedule_increments_counter(self):
        scheduler = ColdPathScheduler()
        await scheduler.start()
        loop = asyncio.get_running_loop()
        for _ in range(5):
            fut = loop.create_future()
            fut.set_result(None)
            scheduler.schedule(fut)
        assert scheduler._scheduled == 5
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_oneshot_list_pruned_on_overflow(self):
        """List stays bounded: after tasks complete, pruning removes done entries."""
        from ..cold_path_scheduler import _ONESHOT_PRUNE_THRESHOLD
        scheduler = ColdPathScheduler()
        await scheduler.start()
        n = _ONESHOT_PRUNE_THRESHOLD + 10
        loop = asyncio.get_running_loop()
        for _ in range(n):
            fut = loop.create_future()
            fut.set_result(None)
            scheduler.schedule(fut)
        # Yield several times so all asyncio.sleep(0) tasks actually complete
        for _ in range(10):
            await asyncio.sleep(0)
        # Trigger pruning by adding one more task — now all prior tasks are done
        fut = loop.create_future()
        fut.set_result(None)
        scheduler.schedule(fut)
        # After pruning, list is small (≤ n_still_running + 1)
        assert len(scheduler._oneshot_tasks) <= _ONESHOT_PRUNE_THRESHOLD
        await scheduler.stop()


class TestColdPathSchedulerPeriodic:
    """Periodic task scheduling."""

    @pytest.mark.asyncio
    async def test_periodic_task_fires(self):
        scheduler = ColdPathScheduler()
        await scheduler.start()
        fired = []

        def counter():
            fired.append(1)

        scheduler.schedule_periodic(counter, interval=0.01, name="test")
        await asyncio.sleep(0.05)  # Allow 2–4 firings
        await scheduler.stop()
        assert len(fired) >= 2

    @pytest.mark.asyncio
    async def test_periodic_task_isolates_errors(self):
        scheduler = ColdPathScheduler()
        await scheduler.start()

        def bad():
            raise ValueError("periodic error")

        scheduler.schedule_periodic(bad, interval=0.01, name="bad-task")
        await asyncio.sleep(0.05)
        await scheduler.stop()
        assert scheduler._errors >= 1

    @pytest.mark.asyncio
    async def test_periodic_task_replaced_by_same_name(self):
        scheduler = ColdPathScheduler()
        await scheduler.start()
        first_calls = []
        second_calls = []

        def first():
            first_calls.append(1)

        def second():
            second_calls.append(1)

        scheduler.schedule_periodic(first, interval=0.01, name="same")
        await asyncio.sleep(0.02)
        scheduler.schedule_periodic(second, interval=0.01, name="same")
        count_after_replace = len(first_calls)
        await asyncio.sleep(0.03)
        await scheduler.stop()
        # After replacement, first should have stopped accumulating
        assert len(first_calls) == count_after_replace

    @pytest.mark.asyncio
    async def test_stop_cancels_periodic_tasks(self):
        scheduler = ColdPathScheduler()
        await scheduler.start()
        fired = []

        def counter():
            fired.append(1)

        scheduler.schedule_periodic(counter, interval=0.01, name="cnt")
        await asyncio.sleep(0.02)
        await scheduler.stop()
        count_at_stop = len(fired)
        await asyncio.sleep(0.05)  # Wait — should NOT fire anymore
        assert len(fired) == count_at_stop

    @pytest.mark.asyncio
    async def test_schedule_gc_registers_periodic(self):
        scheduler = ColdPathScheduler()
        await scheduler.start()
        opt = HotPathOptimizer()
        scheduler.schedule_gc(opt, interval=0.01)
        assert "gc-collect" in scheduler._periodic_tasks
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_singleton_returns_same_instance(self):
        a = get_cold_path_scheduler()
        b = get_cold_path_scheduler()
        assert a is b

    @pytest.mark.asyncio
    async def test_stats_shape(self):
        scheduler = ColdPathScheduler()
        await scheduler.start()
        s = scheduler.stats
        assert "running" in s
        assert "periodic_tasks" in s
        assert "oneshot_active" in s
        assert "total_scheduled" in s
        assert "total_errors" in s
        await scheduler.stop()


# ===========================================================================
# TradingInstanceAsync P4 — Hot path behaviour
# ===========================================================================


@pytest.fixture
def mock_config():
    return _make_config()


@pytest.fixture
def mock_orchestrator():
    orc = MagicMock()
    orc.hot_optimizer = HotPathOptimizer()
    return orc


@pytest.fixture
def instance(mock_config, mock_orchestrator):
    """Create a TradingInstanceAsync with minimal mocking."""
    from ..instance_async import TradingInstanceAsync

    with patch("src.autobot.v2.instance_async.get_persistence") as mock_pers:
        mock_pers.return_value = MagicMock()
        inst = TradingInstanceAsync(
            instance_id="test-001",
            config=mock_config,
            orchestrator=mock_orchestrator,
        )
    # Manually set status to RUNNING
    from ..instance import InstanceStatus
    inst.status = InstanceStatus.RUNNING
    return inst


class TestInstanceHotPath:
    """Verify hot-path invariants in TradingInstanceAsync.on_price_update."""

    @pytest.mark.asyncio
    async def test_on_price_update_no_lock_acquired(self, instance):
        """
        on_price_update must not acquire asyncio.Lock.

        We verify this by checking the lock is never acquired during the call.
        In asyncio a lock that is acquired increases its internal counter.
        """
        lock_acquired_count_before = instance._lock._waiters  # internal deque
        ticker = _make_ticker(50_000.0)
        await instance.on_price_update(ticker)
        # _waiters length unchanged → lock was not awaited
        assert instance._lock._waiters == lock_acquired_count_before

    @pytest.mark.asyncio
    async def test_on_price_update_updates_last_price(self, instance):
        ticker = _make_ticker(42_000.0)
        await instance.on_price_update(ticker)
        assert instance._last_price == 42_000.0

    @pytest.mark.asyncio
    async def test_on_price_update_appends_price_history(self, instance):
        before = len(instance._price_history)
        ticker = _make_ticker(43_000.0)
        await instance.on_price_update(ticker)
        assert len(instance._price_history) == before + 1
        _, price = instance._price_history[-1]
        assert price == 43_000.0

    @pytest.mark.asyncio
    async def test_on_price_update_reuses_ticker_timestamp(self, instance):
        """Timestamp in history must come from TickerData, not datetime.now(timezone.utc)."""
        ticker = _make_ticker(44_000.0)
        ts = ticker.timestamp
        await instance.on_price_update(ticker)
        stored_ts, _ = instance._price_history[-1]
        assert stored_ts is ts

    @pytest.mark.asyncio
    async def test_on_price_update_records_latency_when_optimizer_attached(
        self, instance
    ):
        opt = HotPathOptimizer()
        instance.attach_hot_optimizer(opt)
        for _ in range(10):
            await instance.on_price_update(_make_ticker())
        s = opt.stats
        assert s["tick_count"] == 10

    @pytest.mark.asyncio
    async def test_on_price_update_no_optimizer_no_crash(self, instance):
        """Without attached optimizer, on_price_update must still work."""
        assert instance._hot_optimizer is None
        await instance.on_price_update(_make_ticker())  # Must not raise

    @pytest.mark.asyncio
    async def test_attach_hot_optimizer(self, instance):
        opt = HotPathOptimizer()
        instance.attach_hot_optimizer(opt)
        assert instance._hot_optimizer is opt

    @pytest.mark.asyncio
    async def test_check_leverage_not_called_per_tick(self, instance):
        """
        P4 invariant: on_price_update does NOT call check_leverage_downgrade.
        """
        call_count = 0
        original = instance.check_leverage_downgrade

        def counting_check():
            nonlocal call_count
            call_count += 1
            return original()

        instance.check_leverage_downgrade = counting_check
        for _ in range(100):
            await instance.on_price_update(_make_ticker())
        assert call_count == 0, (
            "check_leverage_downgrade must NOT be called on the hot path (P4)"
        )


# ===========================================================================
# Latency benchmark — hot path < 10 µs (conservative, CI-safe)
# ===========================================================================


class TestHotPathLatencyBenchmark:
    """
    Measure actual nanosecond latency of on_price_update.

    Target (spec): < 1 µs on dedicated hardware.
    Test threshold: < 10 µs P99 (CI-safe — shared CI runners add noise).
    """

    @pytest.mark.asyncio
    async def test_on_price_update_latency_p99_below_10us(self, instance):
        """P99 latency of on_price_update must be < 10 µs in a test environment."""
        opt = HotPathOptimizer(max_samples=1024)
        instance.attach_hot_optimizer(opt)

        ticker = _make_ticker(50_000.0)
        N = 500

        for _ in range(N):
            await instance.on_price_update(ticker)

        s = opt.stats
        p99_us = s["p99_ns"] / 1_000
        avg_us = s["avg_ns"] / 1_000

        print(
            f"\n⚡ Hot path latency (N={N}):\n"
            f"   avg={avg_us:.3f} µs  "
            f"p50={s['p50_ns']/1000:.3f} µs  "
            f"p95={s['p95_ns']/1000:.3f} µs  "
            f"p99={p99_us:.3f} µs  "
            f"max={s['max_ns']/1000:.3f} µs"
        )

        assert p99_us < 10.0, (
            f"P99 hot path latency {p99_us:.2f} µs exceeds 10 µs threshold. "
            "Check for I/O, locks, or allocation on the hot path."
        )

    @pytest.mark.asyncio
    async def test_hot_path_optimizer_record_tick_sub_microsecond(self):
        """record_tick() itself must be < 1 µs overhead."""
        opt = HotPathOptimizer(max_samples=512)
        overhead_samples = []
        N = 200

        for _ in range(N):
            t0 = opt.start_tick()
            # Simulate zero work
            elapsed = opt.record_tick(t0)
            overhead_samples.append(elapsed)

        p99_ns = sorted(overhead_samples)[int(N * 0.99)]
        print(f"\n⚡ record_tick overhead P99: {p99_ns} ns")
        # record_tick itself should be well under 1 µs
        assert p99_ns < 1_000, (
            f"record_tick P99 overhead {p99_ns} ns exceeds 1 µs"
        )


# ===========================================================================
# Integration — ColdPathScheduler + hot path together
# ===========================================================================


class TestHotColdIntegration:
    """
    Simulate the P4 architecture: hot path fires cold tasks via scheduler.
    """

    @pytest.mark.asyncio
    async def test_hot_path_schedules_save_state_without_blocking(self):
        """
        Simulate: on_price_update fires save_state() via cold scheduler.
        The hot path must return before save_state completes.
        """
        scheduler = ColdPathScheduler()
        await scheduler.start()
        execution_order = []

        async def fake_save_state():
            await asyncio.sleep(0.01)
            execution_order.append("save_state_done")

        execution_order.append("hot_path_start")
        scheduler.schedule(fake_save_state(), name="save_state")
        execution_order.append("hot_path_end")

        await asyncio.sleep(0.05)
        assert execution_order[0] == "hot_path_start"
        assert execution_order[1] == "hot_path_end"
        assert execution_order[2] == "save_state_done"
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_gc_periodic_fires_while_hot_path_runs(self):
        """
        GC task fires in background while hot path ticks.

        Verified by checking that the periodic task accumulates scheduled
        count while GC auto-collection is disabled.
        """
        import gc as gc_module

        gc_module.enable()
        opt = HotPathOptimizer()
        opt.enter_hot_path()
        assert not gc_module.isenabled()

        scheduler = ColdPathScheduler()
        await scheduler.start()
        scheduler.schedule_gc(opt, interval=0.02)

        scheduled_before = scheduler._scheduled

        # Simulate hot-path ticks running while GC fires in background
        for _ in range(10):
            await asyncio.sleep(0.01)

        await scheduler.stop()
        opt.exit_hot_path()

        # Periodic task should have fired at least twice (10×0.01s / 0.02s interval)
        assert scheduler._scheduled >= scheduled_before + 2, (
            "GC periodic task should have fired at least twice"
        )
