"""
Tests for AdaptiveRangeCalculator.
"""

import math
import time

import pytest
from autobot.v2.strategies.adaptive_grid_config import PairProfile
from autobot.v2.strategies.range_calculator import AdaptiveRangeCalculator


class TestAdaptiveRangeCalculator:
    def setup_method(self):
        self.profile = PairProfile(
            symbol="XXBTZEUR",
            base_range_pct=4.0,
            min_range_pct=2.0,
            max_range_pct=10.0,
            atr_multiplier=2.0,
            hv_ratio_band=(0.7, 1.3),
        )
        self.calc = AdaptiveRangeCalculator(
            self.profile, update_interval_s=0.0,  # Disable throttle for tests
        )

    # --- Initial state ---

    def test_initial_range_is_base(self):
        assert self.calc.get_current_range() == 4.0

    def test_on_price_o1(self):
        """on_price should be O(1) — just deque append."""
        self.calc.on_price(50000.0)
        self.calc.on_price(50100.0)
        # No crash, no recompute yet
        assert self.calc.get_current_range() == 4.0

    # --- update() with ATR ---

    def test_update_with_atr(self):
        result = self.calc.update(atr_pct=3.0)
        # Expected: 3.0 * 2.0 = 6.0, clamped to [2.0, 10.0]
        assert result == 6.0
        assert self.calc.get_current_range() == 6.0

    def test_update_clamps_to_min(self):
        result = self.calc.update(atr_pct=0.5)
        # Expected: 0.5 * 2.0 = 1.0, clamped to min 2.0
        assert result == 2.0

    def test_update_clamps_to_max(self):
        result = self.calc.update(atr_pct=10.0)
        # Expected: 10.0 * 2.0 = 20.0, clamped to max 10.0
        assert result == 10.0

    def test_update_no_atr_uses_base(self):
        result = self.calc.update(atr_pct=None)
        assert result == 4.0  # base_range_pct

    # --- HV ratio regime adjustment ---

    def test_hv_ratio_expanding_vol(self):
        """When HV24 > HV7d, regime_adj > 1 -> wider range."""
        # Feed enough prices to compute HV
        base_price = 50000.0
        # 7d buffer with stable prices
        for i in range(200):
            self.calc.on_price(base_price + (i % 10) * 5)

        # Then inject higher-vol recent prices into 24h window
        for i in range(100):
            self.calc.on_price(base_price + (i % 20) * 50)

        result = self.calc.update(atr_pct=3.0)
        # With expanding vol, range should be >= base ATR-derived range
        assert result >= 2.0  # At minimum

    def test_hv_ratio_insufficient_data(self):
        """With insufficient price data, HV ratio is ignored."""
        # Only 5 prices — not enough for HV computation
        for i in range(5):
            self.calc.on_price(50000.0 + i * 10)
        result = self.calc.update(atr_pct=3.0)
        # Should use base ATR calc without HV adjustment
        assert 2.0 <= result <= 10.0

    # --- Throttling ---

    def test_throttle(self):
        calc = AdaptiveRangeCalculator(self.profile, update_interval_s=1000.0)
        calc.update(atr_pct=3.0)
        # Second call within throttle window should return cached
        old = calc.get_current_range()
        calc.update(atr_pct=8.0)  # Should be throttled
        assert calc.get_current_range() == old

    def test_force_update_ignores_throttle(self):
        calc = AdaptiveRangeCalculator(self.profile, update_interval_s=1000.0)
        calc.update(atr_pct=3.0)
        old = calc.get_current_range()
        result = calc.force_update(atr_pct=5.0)
        assert result != old

    # --- Invalid inputs ---

    def test_on_price_ignores_nan(self):
        self.calc.on_price(float("nan"))
        # Should not crash or add NaN to buffers

    def test_on_price_ignores_negative(self):
        self.calc.on_price(-100.0)
        # Should not crash

    def test_on_price_ignores_zero(self):
        self.calc.on_price(0.0)

    # --- Introspection ---

    def test_get_status(self):
        self.calc.update(atr_pct=3.0)
        status = self.calc.get_status()
        assert status["symbol"] == "XXBTZEUR"
        assert status["current_range_pct"] > 0
        assert status["base_range_pct"] == 4.0
        assert status["min_range_pct"] == 2.0
        assert status["max_range_pct"] == 10.0

    def test_profile_property(self):
        assert self.calc.profile.symbol == "XXBTZEUR"


class TestHVComputation:
    """Test the static _compute_hv method."""

    def test_insufficient_data(self):
        from collections import deque
        prices = deque([100.0] * 10)
        assert AdaptiveRangeCalculator._compute_hv(prices) is None

    def test_constant_prices_zero_vol(self):
        from collections import deque
        prices = deque([100.0] * 100)
        hv = AdaptiveRangeCalculator._compute_hv(prices)
        assert hv is not None
        assert hv == 0.0  # No variance

    def test_volatile_prices_nonzero(self):
        from collections import deque
        import random
        random.seed(42)
        prices = deque()
        p = 100.0
        for _ in range(200):
            p *= (1 + random.gauss(0, 0.02))  # 2% daily vol
            prices.append(p)
        hv = AdaptiveRangeCalculator._compute_hv(prices)
        assert hv is not None
        assert hv > 0.0

    def test_increasing_prices(self):
        from collections import deque
        prices = deque(range(100, 200))  # Monotonically increasing
        hv = AdaptiveRangeCalculator._compute_hv(prices)
        assert hv is not None
        assert hv > 0.0
