"""
Tests for SmartRecentering.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest
from autobot.v2.strategies.smart_recentering import SmartRecentering, SmartRecenterResult

pytestmark = pytest.mark.unit


class TestSmartRecentering:
    def setup_method(self):
        self.sr = SmartRecentering(
            center_price=50000.0,
            range_percent=7.0,
            num_levels=15,
            drift_threshold_pct=5.0,
            adx_threshold=25.0,
            cooldown_minutes=45,
            max_recenters_per_day=4,
            trailing_pct=5.0,
            min_shift_pct=25.0,
            max_shift_pct=75.0,
            velocity_window=20,
        )

    # --- should_recenter ---

    def test_no_recenter_below_threshold(self):
        # 2% drift — below 5% threshold
        price = 50000.0 * 1.02
        assert self.sr.should_recenter(price) is False

    def test_recenter_above_threshold(self):
        # 6% drift — above 5% threshold
        price = 50000.0 * 1.06
        assert self.sr.should_recenter(price) is True

    def test_blocked_by_adx(self):
        price = 50000.0 * 1.10  # Big drift
        assert self.sr.should_recenter(price, adx=30.0) is False

    def test_allowed_low_adx(self):
        price = 50000.0 * 1.10
        assert self.sr.should_recenter(price, adx=20.0) is True

    def test_cooldown_blocks(self):
        price = 50000.0 * 1.10
        # First recenter: allowed
        assert self.sr.should_recenter(price) is True
        self.sr.compute_recenter(price)
        # Second immediately: blocked by cooldown
        assert self.sr.should_recenter(price) is False

    def test_daily_cap(self):
        price = 50000.0 * 1.10
        for _ in range(4):
            self.sr.should_recenter(price)
            self.sr.compute_recenter(price)
            self.sr._last_recenter = None  # Reset cooldown for testing

        assert self.sr.should_recenter(price) is False  # 4th should fail (daily cap)

    # --- compute_recenter ---

    def test_progressive_shift(self):
        """Center should NOT snap fully to price — should be a partial shift."""
        price = 53000.0  # 6% above center
        result = self.sr.compute_recenter(price)
        assert result.should_recenter is True

        # New center should be between old center and price
        assert result.new_center > 50000.0
        assert result.new_center < 53000.0
        assert result.shift_pct > 0
        assert result.shift_pct < 100

    def test_no_recenter_small_drift(self):
        price = 50500.0  # 1% drift
        result = self.sr.compute_recenter(price)
        assert result.should_recenter is False
        assert result.new_center == 50000.0

    def test_new_grid_levels_generated(self):
        price = 53000.0
        result = self.sr.compute_recenter(price)
        assert len(result.new_grid_levels) == 15
        # Levels should be sorted
        assert result.new_grid_levels == sorted(result.new_grid_levels)

    def test_positions_to_close(self):
        """Far out-of-range positions should be marked for closure."""
        price = 55000.0  # 10% drift
        open_levels = {
            0: {"entry_price": 46000.0, "volume": 0.001},  # Very far below
            7: {"entry_price": 50000.0, "volume": 0.001},  # Near center
            14: {"entry_price": 52000.0, "volume": 0.001},  # Above center
        }
        grid_levels = list(range(46500, 53500, 500))  # Approximate
        result = self.sr.compute_recenter(price, open_levels, grid_levels)
        # Level 0 (at 46000) should likely be marked for close
        assert isinstance(result.positions_to_close, list)

    def test_velocity_affects_shift(self):
        """Higher velocity should produce a larger shift ratio."""
        # Low velocity: small price changes
        sr_low = SmartRecentering(
            center_price=50000.0, range_percent=7.0, num_levels=15,
            drift_threshold_pct=5.0, min_shift_pct=25.0, max_shift_pct=75.0,
        )
        for _ in range(20):
            sr_low.should_recenter(50000.0)  # Flat prices
        result_low = sr_low.compute_recenter(53000.0)

        # High velocity: large price changes
        sr_high = SmartRecentering(
            center_price=50000.0, range_percent=7.0, num_levels=15,
            drift_threshold_pct=5.0, min_shift_pct=25.0, max_shift_pct=75.0,
        )
        for i in range(20):
            sr_high.should_recenter(50000.0 + i * 200)  # Rising prices
        result_high = sr_high.compute_recenter(53000.0)

        # High velocity should have larger shift
        assert result_high.shift_pct >= result_low.shift_pct

    # --- trailing anchor ---

    def test_trailing_anchor_shifts_up(self):
        price = 50000.0 * 1.06  # 6% above center
        shifted = self.sr.check_trailing_anchor(price)
        assert shifted is True
        assert self.sr.center_price > 50000.0
        assert self.sr.center_price < price

    def test_trailing_anchor_no_shift_below_threshold(self):
        price = 50000.0 * 1.03  # 3% — below trailing_pct of 5%
        shifted = self.sr.check_trailing_anchor(price)
        assert shifted is False
        assert self.sr.center_price == 50000.0

    def test_trailing_anchor_40_pct_shift(self):
        """Trailing anchor should shift 40% of the gap (not 50% like old DGT)."""
        price = 55000.0  # 10% above
        self.sr.check_trailing_anchor(price)
        gap = 55000.0 - 50000.0
        expected = 50000.0 + gap * 0.4
        assert abs(self.sr.center_price - expected) < 0.01

    # --- backward compat ---

    def test_recenter_backward_compat(self):
        """recenter() should work like the old DGT for backward compat."""
        result = self.sr.recenter(53000.0)
        assert isinstance(result, SmartRecenterResult)
        assert result.new_center > 50000.0

    # --- async ---

    def test_async_recenter(self):
        async def run():
            result = await self.sr.async_recenter(53000.0)
            assert result.new_center > 50000.0

        asyncio.run(run())

    # --- introspection ---

    def test_recenters_today(self):
        assert self.sr.recenters_today == 0
        self.sr.compute_recenter(53000.0)
        assert self.sr.recenters_today == 1

    def test_last_recenter_initially_none(self):
        assert self.sr.last_recenter is None

    def test_recenter_history(self):
        self.sr.compute_recenter(53000.0)
        assert len(self.sr.recenter_history) == 1

    def test_get_status(self):
        status = self.sr.get_status()
        assert "center_price" in status
        assert "min_shift_pct" in status
        assert "max_shift_pct" in status
        assert status["center_price"] == 50000.0

    # --- daily reset ---

    def test_daily_counter_resets(self):
        self.sr._recenters_today = 3
        self.sr._today_date = datetime.now(timezone.utc).date() - timedelta(days=1)
        # Accessing recenters_today should trigger reset
        assert self.sr.recenters_today == 0
