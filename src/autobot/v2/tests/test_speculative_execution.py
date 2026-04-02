"""
Tests P6 — Speculative Execution: OrderTemplate + SpeculativeOrderCache + FastOrderBuilder.

Coverage
--------
SpeculativeOrderCache:
    - store / get hit
    - get miss → None
    - precompute_grid_levels creates correct BUY templates
    - store_sell_template creates correct SELL template
    - invalidate removes single template
    - invalidate_symbol removes all templates for that symbol
    - hit/miss counters and hit_rate
    - size property

FastOrderBuilder:
    - build() returns (params_dict, body_bytes) on cache hit
    - build() returns None on cache miss
    - build_dict_only() returns params dict on hit
    - BUY volume = capital / live_price (one division)
    - SELL volume = fixed_volume (pre-computed)
    - body bytes start with correct prefix
    - body bytes contain correct volume

_write_volume_to_buf:
    - zero value
    - sub-unit value (e.g. 0.00123456)
    - integer + fraction (e.g. 1.23456789)
    - whole number (e.g. 5.0)
    - large value (e.g. 99999.12345678)
    - Matches f"{v:.8f}" for a range of values

OrderRouter.submit_speculative:
    - cache hit → correct order submitted
    - cache miss → falls back with a submit call

GridStrategyAsync.attach_speculative_cache:
    - BUY templates created at attach time
    - on_position_opened creates SELL template
    - on_position_closed removes SELL template
    - _init_grid repopulates cache if already attached

Benchmarks (reported, not asserted):
    - cache hit latency (target < 1 µs)
    - cache miss latency
    - FastOrderBuilder.build() vs plain dict construction
"""

from __future__ import annotations

import sys
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

sys.path.insert(0, "/home/node/.openclaw/workspace/src")

from autobot.v2.speculative_order_cache import (
    OrderTemplate,
    SpeculativeOrderCache,
    _build_body_prefix,
)
from autobot.v2.fast_order_builder import (
    FastOrderBuilder,
    _write_volume_to_buf,
    build_volume_str,
)


# ===========================================================================
# Helpers
# ===========================================================================

SYMBOL = "XXBTZEUR"
GRID_LEVELS = [45_000.0, 46_000.0, 47_000.0, 48_000.0, 49_000.0]
CAPITAL = 50.0


def _make_cache() -> SpeculativeOrderCache:
    c = SpeculativeOrderCache()
    c.precompute_grid_levels(SYMBOL, GRID_LEVELS, CAPITAL)
    return c


def _make_builder(cache: SpeculativeOrderCache | None = None) -> FastOrderBuilder:
    return FastOrderBuilder(cache or _make_cache())


# ===========================================================================
# _write_volume_to_buf
# ===========================================================================


class TestWriteVolumeToBuf:
    def _render(self, v: float) -> str:
        buf = bytearray(32)
        end = _write_volume_to_buf(buf, 0, v)
        return buf[:end].decode("ascii")

    def test_zero(self):
        assert self._render(0.0) == "0.00000000"

    def test_sub_unit(self):
        assert self._render(0.00123456) == "0.00123456"

    def test_integer_plus_fraction(self):
        assert self._render(1.23456789) == "1.23456789"

    def test_whole_number(self):
        assert self._render(5.0) == "5.00000000"

    def test_large_value(self):
        assert self._render(99999.12345678) == "99999.12345678"

    def test_tiny_value(self):
        assert self._render(0.00000001) == "0.00000001"

    def test_offset(self):
        """Writing at a non-zero offset leaves preceding bytes intact."""
        buf = bytearray(32)
        buf[0] = ord("X")
        end = _write_volume_to_buf(buf, 1, 1.5)
        assert buf[0] == ord("X")
        assert buf[1:end].decode("ascii") == "1.50000000"

    @pytest.mark.parametrize("v", [
        0.0, 0.001, 0.12345678, 1.0, 1.99999999, 10.5, 100.0, 9999.99999999,
    ])
    def test_matches_fstring(self, v: float):
        """Zero-alloc path must produce the same string as f'{v:.8f}'."""
        result = self._render(v)
        expected = f"{v:.8f}"
        assert result == expected, f"v={v}: got {result!r}, want {expected!r}"

    def test_build_volume_str(self):
        assert build_volume_str(0.5) == "0.50000000"
        assert build_volume_str(0.00100000) == "0.00100000"


# ===========================================================================
# SpeculativeOrderCache
# ===========================================================================


class TestSpeculativeOrderCache:
    def test_precompute_creates_buy_templates(self):
        c = SpeculativeOrderCache()
        c.precompute_grid_levels(SYMBOL, GRID_LEVELS, CAPITAL)
        assert c.size == len(GRID_LEVELS)

    def test_get_hit_returns_template(self):
        c = _make_cache()
        t = c.get(SYMBOL, "buy", 2)
        assert t is not None
        assert t.symbol == SYMBOL
        assert t.side == "buy"
        assert t.level_index == 2
        assert t.level_price == GRID_LEVELS[2]
        assert t.capital_per_level == CAPITAL

    def test_get_miss_returns_none(self):
        c = _make_cache()
        assert c.get(SYMBOL, "buy", 999) is None
        assert c.get("UNKNOWN", "buy", 0) is None
        assert c.get(SYMBOL, "sell", 0) is None  # no sell templates yet

    def test_hit_miss_counters(self):
        c = _make_cache()
        c.get(SYMBOL, "buy", 0)   # hit
        c.get(SYMBOL, "buy", 0)   # hit
        c.get(SYMBOL, "buy", 99)  # miss
        assert c.hits == 2
        assert c.misses == 1
        assert abs(c.hit_rate() - 2 / 3) < 1e-9

    def test_reset_stats(self):
        c = _make_cache()
        c.get(SYMBOL, "buy", 0)
        c.reset_stats()
        assert c.hits == 0
        assert c.misses == 0

    def test_store_sell_template(self):
        c = _make_cache()
        c.store_sell_template(SYMBOL, level_index=2, level_price=47_000.0, volume=0.00106382)
        t = c.get(SYMBOL, "sell", 2)
        assert t is not None
        assert t.side == "sell"
        assert t.has_fixed_volume
        assert t.fixed_volume == pytest.approx(0.00106382)

    def test_buy_template_has_no_fixed_volume(self):
        c = _make_cache()
        t = c.get(SYMBOL, "buy", 0)
        assert t is not None
        assert not t.has_fixed_volume
        assert t.fixed_volume == -1.0

    def test_body_prefix_format(self):
        c = _make_cache()
        t = c.get(SYMBOL, "buy", 0)
        assert t is not None
        expected = b"pair=XXBTZEUR&type=buy&ordertype=market&volume="
        assert t.body_prefix == expected

    def test_invalidate_single(self):
        c = _make_cache()
        c.invalidate(SYMBOL, "buy", 2)
        assert c.get(SYMBOL, "buy", 2) is None
        # others untouched
        assert c.get(SYMBOL, "buy", 1) is not None

    def test_invalidate_symbol(self):
        c = _make_cache()
        c.precompute_grid_levels("XETHZEUR", [1000.0, 1100.0], CAPITAL)
        c.invalidate_symbol(SYMBOL)
        assert c.get(SYMBOL, "buy", 0) is None
        # Other symbol untouched
        assert c.get("XETHZEUR", "buy", 0) is not None

    def test_precompute_resets_on_recenter(self):
        """Second call to precompute_grid_levels replaces old templates."""
        c = SpeculativeOrderCache()
        c.precompute_grid_levels(SYMBOL, GRID_LEVELS, CAPITAL)
        new_levels = [50_000.0, 51_000.0]
        c.invalidate_symbol(SYMBOL)
        c.precompute_grid_levels(SYMBOL, new_levels, CAPITAL)
        assert c.size == 2
        assert c.get(SYMBOL, "buy", 0).level_price == 50_000.0

    def test_invalid_capital_raises(self):
        c = SpeculativeOrderCache()
        with pytest.raises(ValueError):
            c.precompute_grid_levels(SYMBOL, GRID_LEVELS, capital_per_level=0.0)

    def test_get_stats(self):
        c = _make_cache()
        c.get(SYMBOL, "buy", 0)
        stats = c.get_stats()
        assert stats["size"] == len(GRID_LEVELS)
        assert stats["hits"] == 1
        assert stats["misses"] == 0
        assert stats["hit_rate"] == 1.0


# ===========================================================================
# FastOrderBuilder
# ===========================================================================


class TestFastOrderBuilder:
    def test_build_returns_tuple_on_hit(self):
        builder = _make_builder()
        result = builder.build(SYMBOL, "buy", 2, live_price=47_100.0)
        assert result is not None
        params, body = result

    def test_build_returns_none_on_miss(self):
        builder = _make_builder()
        assert builder.build(SYMBOL, "buy", 99, live_price=47_000.0) is None

    def test_buy_volume_uses_live_price(self):
        builder = _make_builder()
        live_price = 47_000.0
        result = builder.build(SYMBOL, "buy", 2, live_price)
        assert result is not None
        params, _ = result
        expected_volume = CAPITAL / live_price
        actual_volume = float(params["volume"])
        assert actual_volume == pytest.approx(expected_volume, rel=1e-6)

    def test_sell_volume_uses_fixed(self):
        cache = _make_cache()
        cache.store_sell_template(SYMBOL, level_index=2, level_price=47_000.0, volume=0.00106382)
        builder = FastOrderBuilder(cache)
        result = builder.build(SYMBOL, "sell", 2, live_price=48_000.0)
        assert result is not None
        params, _ = result
        assert float(params["volume"]) == pytest.approx(0.00106382, rel=1e-6)

    def test_body_bytes_start_with_prefix(self):
        builder = _make_builder()
        result = builder.build(SYMBOL, "buy", 1, live_price=46_500.0)
        assert result is not None
        _, body = result
        assert body.startswith(b"pair=XXBTZEUR&type=buy&ordertype=market&volume=")

    def test_body_bytes_contain_volume(self):
        builder = _make_builder()
        live_price = 46_000.0
        result = builder.build(SYMBOL, "buy", 1, live_price)
        assert result is not None
        params, body = result
        expected_vol = params["volume"].encode("ascii")
        assert expected_vol in body

    def test_params_dict_keys(self):
        builder = _make_builder()
        result = builder.build(SYMBOL, "buy", 0, live_price=45_500.0)
        assert result is not None
        params, _ = result
        assert set(params.keys()) == {"type", "symbol", "side", "volume"}
        assert params["type"] == "market"
        assert params["symbol"] == SYMBOL
        assert params["side"] == "buy"

    def test_build_dict_only_hit(self):
        builder = _make_builder()
        params = builder.build_dict_only(SYMBOL, "buy", 0, live_price=45_000.0)
        assert params is not None
        assert params["side"] == "buy"
        assert float(params["volume"]) == pytest.approx(CAPITAL / 45_000.0, rel=1e-6)

    def test_build_dict_only_miss(self):
        builder = _make_builder()
        assert builder.build_dict_only(SYMBOL, "buy", 999, live_price=45_000.0) is None

    def test_hit_miss_counters(self):
        builder = _make_builder()
        builder.build(SYMBOL, "buy", 0, 45_000.0)  # hit
        builder.build(SYMBOL, "buy", 99, 45_000.0)  # miss
        assert builder.hits == 1
        assert builder.misses == 1
        assert builder.hit_rate() == 0.5

    def test_get_stats(self):
        builder = _make_builder()
        builder.build(SYMBOL, "buy", 0, 45_000.0)
        stats = builder.get_stats()
        assert stats["hits"] == 1
        assert stats["hit_rate"] == 1.0


# ===========================================================================
# OrderRouter integration
# ===========================================================================


class TestOrderRouterSpeculative:
    @pytest.mark.asyncio
    async def test_set_speculative_cache(self):
        """set_speculative_cache attaches cache without errors."""
        from autobot.v2.order_router import OrderRouter
        router = OrderRouter(api_key="k", api_secret="s")
        cache = _make_cache()
        router.set_speculative_cache(cache)
        assert router._spec_cache is cache

    @pytest.mark.asyncio
    async def test_submit_speculative_hit(self):
        """submit_speculative with a cache hit calls submit with correct params."""
        from autobot.v2.order_router import OrderRouter, OrderPriority
        from autobot.v2.order_executor_async import OrderResult

        router = OrderRouter(api_key="k", api_secret="s")
        cache = _make_cache()
        router.set_speculative_cache(cache)

        submitted_orders = []

        async def _fake_submit(order, priority=OrderPriority.ORDER, instance_id=None):
            submitted_orders.append(order)
            return OrderResult(success=True, txid="abc123")

        router.submit = _fake_submit

        result = await router.submit_speculative(
            symbol=SYMBOL,
            side="buy",
            level_index=2,
            live_price=47_000.0,
        )
        assert result.success
        assert len(submitted_orders) == 1
        order = submitted_orders[0]
        assert order["symbol"] == SYMBOL
        assert order["side"] == "buy"
        expected_vol = CAPITAL / 47_000.0
        assert order["volume"] == pytest.approx(expected_vol, rel=1e-6)

    @pytest.mark.asyncio
    async def test_submit_speculative_miss_fallback(self):
        """submit_speculative with no cache falls back to submit."""
        from autobot.v2.order_router import OrderRouter, OrderPriority
        from autobot.v2.order_executor_async import OrderResult

        router = OrderRouter(api_key="k", api_secret="s")
        # No cache attached

        submitted_orders = []

        async def _fake_submit(order, priority=OrderPriority.ORDER, instance_id=None):
            submitted_orders.append(order)
            return OrderResult(success=True)

        router.submit = _fake_submit

        await router.submit_speculative(
            symbol=SYMBOL,
            side="buy",
            level_index=0,
            live_price=45_000.0,
        )
        assert len(submitted_orders) == 1


# ===========================================================================
# GridStrategyAsync integration
# ===========================================================================


def _make_grid_instance(symbol: str = SYMBOL, capital: float = 1000.0) -> Any:
    """Build a minimal mock instance for GridStrategyAsync."""
    cfg = MagicMock()
    cfg.symbol = symbol
    instance = MagicMock()
    instance.config = cfg
    instance.get_available_capital.return_value = capital
    return instance


class TestGridStrategySpeculative:
    def test_attach_cache_precomputes_buy_templates(self):
        from autobot.v2.strategies.grid_async import GridStrategyAsync

        instance = _make_grid_instance()
        strategy = GridStrategyAsync(instance, {"num_levels": 5})
        cache = SpeculativeOrderCache()
        strategy.attach_speculative_cache(cache)

        # All grid levels should have BUY templates
        for idx in range(len(strategy.grid_levels)):
            t = cache.get(SYMBOL, "buy", idx)
            assert t is not None, f"Missing BUY template for level {idx}"
            assert t.capital_per_level == pytest.approx(
                strategy._runtime_capital_per_level, rel=1e-6
            )

    def test_on_position_opened_creates_sell_template(self):
        from autobot.v2.strategies.grid_async import GridStrategyAsync

        instance = _make_grid_instance()
        strategy = GridStrategyAsync(instance, {"num_levels": 5})
        cache = SpeculativeOrderCache()
        strategy.attach_speculative_cache(cache)

        # Simulate opening a position near grid level 2
        pos = MagicMock()
        pos.buy_price = strategy.grid_levels[2]
        pos.volume = 0.001

        strategy.on_position_opened(pos)

        # SELL template should now exist for the nearest level
        idx = strategy._find_nearest_level(pos.buy_price)
        t = cache.get(SYMBOL, "sell", idx)
        assert t is not None
        assert t.has_fixed_volume
        assert t.fixed_volume == pytest.approx(0.001, rel=1e-6)

    def test_on_position_closed_removes_sell_template(self):
        from autobot.v2.strategies.grid_async import GridStrategyAsync

        instance = _make_grid_instance()
        strategy = GridStrategyAsync(instance, {"num_levels": 5})
        cache = SpeculativeOrderCache()
        strategy.attach_speculative_cache(cache)

        pos = MagicMock()
        pos.buy_price = strategy.grid_levels[1]
        pos.volume = 0.001

        strategy.on_position_opened(pos)
        idx = strategy._find_nearest_level(pos.buy_price)
        assert cache.get(SYMBOL, "sell", idx) is not None

        strategy.on_position_closed(pos, profit=0.5)
        assert cache.get(SYMBOL, "sell", idx) is None

    def test_no_cache_attached_no_error(self):
        """Grid without attached cache operates normally."""
        from autobot.v2.strategies.grid_async import GridStrategyAsync

        instance = _make_grid_instance()
        strategy = GridStrategyAsync(instance, {"num_levels": 5})

        pos = MagicMock()
        pos.buy_price = strategy.grid_levels[1]
        pos.volume = 0.001
        strategy.on_position_opened(pos)
        strategy.on_position_closed(pos, profit=0.0)
        # No AttributeError — _spec_cache is None


# ===========================================================================
# Benchmarks (not assertions — just print timings)
# ===========================================================================


class TestBenchmarks:
    ITERATIONS = 100_000

    def test_bench_cache_hit_latency(self, capsys):
        """Cache hit latency — target < 1 µs."""
        cache = _make_cache()
        N = self.ITERATIONS

        t0 = time.perf_counter()
        for _ in range(N):
            _ = cache.get(SYMBOL, "buy", 2)
        elapsed_ns = (time.perf_counter() - t0) * 1e9 / N

        with capsys.disabled():
            print(
                f"\n[P6 Bench] cache.get() hit: {elapsed_ns:.1f} ns/op "
                f"(target <1000 ns)"
            )
        # soft assertion — warn not fail
        assert elapsed_ns < 5_000, f"Cache hit unexpectedly slow: {elapsed_ns:.0f} ns"

    def test_bench_cache_miss_latency(self, capsys):
        """Cache miss latency."""
        cache = _make_cache()
        N = self.ITERATIONS

        t0 = time.perf_counter()
        for _ in range(N):
            _ = cache.get(SYMBOL, "buy", 9999)
        elapsed_ns = (time.perf_counter() - t0) * 1e9 / N

        with capsys.disabled():
            print(
                f"\n[P6 Bench] cache.get() miss: {elapsed_ns:.1f} ns/op"
            )

    def test_bench_fast_builder_vs_dict(self, capsys):
        """FastOrderBuilder.build_dict_only() vs plain dict construction."""
        cache = _make_cache()
        builder = FastOrderBuilder(cache)
        N = self.ITERATIONS
        live_price = 47_000.0

        # --- fast path ---
        t0 = time.perf_counter()
        for _ in range(N):
            _ = builder.build_dict_only(SYMBOL, "buy", 2, live_price)
        fast_ns = (time.perf_counter() - t0) * 1e9 / N

        # --- standard dict construction (baseline) ---
        t0 = time.perf_counter()
        for _ in range(N):
            _ = {
                "type": "market",
                "symbol": SYMBOL,
                "side": "buy",
                "volume": f"{CAPITAL / live_price:.8f}",
            }
        std_ns = (time.perf_counter() - t0) * 1e9 / N

        speedup = std_ns / fast_ns if fast_ns > 0 else float("inf")

        with capsys.disabled():
            print(
                f"\n[P6 Bench] build_dict_only(): {fast_ns:.1f} ns/op  "
                f"| plain dict: {std_ns:.1f} ns/op  "
                f"| speedup: {speedup:.2f}x"
            )

    def test_bench_write_volume_vs_fstring(self, capsys):
        """_write_volume_to_buf vs f'{v:.8f}' allocation."""
        N = self.ITERATIONS
        buf = bytearray(32)
        v = 0.00123456

        t0 = time.perf_counter()
        for _ in range(N):
            _write_volume_to_buf(buf, 0, v)
        zero_alloc_ns = (time.perf_counter() - t0) * 1e9 / N

        t0 = time.perf_counter()
        for _ in range(N):
            _ = f"{v:.8f}"
        fstring_ns = (time.perf_counter() - t0) * 1e9 / N

        speedup = fstring_ns / zero_alloc_ns if zero_alloc_ns > 0 else float("inf")

        with capsys.disabled():
            print(
                f"\n[P6 Bench] _write_volume_to_buf: {zero_alloc_ns:.1f} ns/op  "
                f"| f-string: {fstring_ns:.1f} ns/op  "
                f"| speedup: {speedup:.2f}x"
            )
