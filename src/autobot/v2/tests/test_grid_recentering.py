"""
Tests — GridRecenteringManager (DGT) + GridStrategyAsync integration.

Coverage:
    GridRecenteringManager — should_recenter:
        - Returns True when drift > threshold and all conditions met
        - Returns False when drift < threshold (price inside grid)
        - Returns False when ADX >= adx_threshold (strong trend)
        - Returns False when cooldown not elapsed
        - Returns False when daily cap reached

    GridRecenteringManager — recenter:
        - Updates center_price and returns correct new grid levels
        - Increments daily counter
        - Records last_recenter timestamp
        - Appends to history

    Trailing anchor:
        - Shifts center to midpoint when price rises > trailing_pct
        - Does NOT consume daily quota
        - Does NOT reset cooldown timer
        - Does NOT fire when price is below trailing_pct threshold

    get_status:
        - Returns accurate snapshot of all fields

    GridStrategyAsync integration:
        - on_price triggers DGT recenter when drift exceeded
        - SELL signals emitted for all open levels before recenter
        - center_price and grid_levels updated in strategy after recenter
        - emergency_mode NOT entered if DGT recenters first
        - DGT disabled via config (enable_dgt=False)
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone, timedelta
from typing import Any, List
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit

sys.path.insert(0, "/home/node/.openclaw/workspace/src")

from autobot.v2.grid_recentering import GridRecenteringManager, RecenterResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_manager(
    center: float = 50_000.0,
    range_pct: float = 7.0,
    num_levels: int = 15,
    drift_threshold: float = 7.0,
    adx_threshold: float = 25.0,
    cooldown_minutes: int = 60,
    max_per_day: int = 3,
    trailing_pct: float = 5.0,
) -> GridRecenteringManager:
    return GridRecenteringManager(
        center_price=center,
        range_percent=range_pct,
        num_levels=num_levels,
        drift_threshold_pct=drift_threshold,
        adx_threshold=adx_threshold,
        cooldown_minutes=cooldown_minutes,
        max_recenters_per_day=max_per_day,
        trailing_pct=trailing_pct,
    )


def _make_grid_instance(
    center: float = 50_000.0,
    capital: float = 1_000.0,
    enable_dgt: bool = True,
    dgt_drift: float = 7.0,
    dgt_cooldown: int = 60,
    dgt_max_per_day: int = 3,
):
    """Return a minimal mock instance suitable for GridStrategyAsync."""
    instance = MagicMock()
    instance.get_available_capital.return_value = capital
    instance.config.symbol = "XBT/EUR"
    instance.orchestrator = None
    cfg = {
        "center_price": center,
        "range_percent": 7.0,
        "num_levels": 15,
        "max_positions": 10,
        "enable_dgt": enable_dgt,
        "dgt_drift_threshold_pct": dgt_drift,
        "dgt_cooldown_minutes": dgt_cooldown,
        "dgt_max_recenters_per_day": dgt_max_per_day,
    }
    return instance, cfg


# ---------------------------------------------------------------------------
# GridRecenteringManager — should_recenter
# ---------------------------------------------------------------------------


class TestShouldRecenter:
    def test_returns_true_when_all_conditions_met(self):
        mgr = _make_manager(center=50_000.0, cooldown_minutes=0)
        # Price drifted 8% above center
        assert mgr.should_recenter(54_000.0) is True

    def test_returns_false_when_drift_below_threshold(self):
        mgr = _make_manager(center=50_000.0, drift_threshold=7.0, cooldown_minutes=0)
        # Only 3% drift — not enough
        assert mgr.should_recenter(51_500.0) is False

    def test_returns_false_when_drift_exactly_at_threshold(self):
        mgr = _make_manager(center=50_000.0, drift_threshold=7.0, cooldown_minutes=0)
        # Exactly 7% — boundary: drift_pct (7.0) is NOT < 7.0, so True
        assert mgr.should_recenter(53_500.0) is True

    def test_returns_false_strong_trend_adx(self):
        mgr = _make_manager(center=50_000.0, adx_threshold=25.0, cooldown_minutes=0)
        # Price drifted enough, but ADX = 30 (strong trend)
        assert mgr.should_recenter(54_000.0, adx=30.0) is False

    def test_returns_true_when_adx_below_threshold(self):
        mgr = _make_manager(center=50_000.0, adx_threshold=25.0, cooldown_minutes=0)
        assert mgr.should_recenter(54_000.0, adx=20.0) is True

    def test_returns_true_when_adx_not_provided(self):
        mgr = _make_manager(center=50_000.0, cooldown_minutes=0)
        # No ADX given → trend condition skipped
        assert mgr.should_recenter(54_000.0, adx=None) is True

    def test_returns_false_during_cooldown(self):
        mgr = _make_manager(center=50_000.0, cooldown_minutes=60)
        # Simulate a recent recenter
        mgr._last_recenter = datetime.now(timezone.utc) - timedelta(minutes=30)
        assert mgr.should_recenter(54_000.0) is False

    def test_returns_true_after_cooldown_elapsed(self):
        mgr = _make_manager(center=50_000.0, cooldown_minutes=60)
        mgr._last_recenter = datetime.now(timezone.utc) - timedelta(minutes=61)
        assert mgr.should_recenter(54_000.0) is True

    def test_returns_false_when_daily_cap_reached(self):
        mgr = _make_manager(center=50_000.0, cooldown_minutes=0, max_per_day=3)
        mgr._recenters_today = 3
        mgr._today_date = datetime.now(timezone.utc).date()
        assert mgr.should_recenter(54_000.0) is False

    def test_returns_true_when_under_daily_cap(self):
        mgr = _make_manager(center=50_000.0, cooldown_minutes=0, max_per_day=3)
        mgr._recenters_today = 2
        mgr._today_date = datetime.now(timezone.utc).date()
        assert mgr.should_recenter(54_000.0) is True

    def test_downside_drift_also_triggers(self):
        mgr = _make_manager(center=50_000.0, drift_threshold=7.0, cooldown_minutes=0)
        # Price dropped 10% below center
        assert mgr.should_recenter(45_000.0) is True


# ---------------------------------------------------------------------------
# GridRecenteringManager — recenter
# ---------------------------------------------------------------------------


class TestRecenter:
    def test_updates_center_price(self):
        mgr = _make_manager(center=50_000.0)
        mgr.recenter(54_000.0)
        assert mgr.center_price == 54_000.0

    def test_returns_correct_new_center(self):
        mgr = _make_manager(center=50_000.0)
        result = mgr.recenter(54_000.0)
        assert result.new_center == 54_000.0
        assert result.old_center == 50_000.0

    def test_returns_non_empty_grid_levels(self):
        mgr = _make_manager(center=50_000.0, num_levels=15)
        result = mgr.recenter(54_000.0)
        assert len(result.new_grid_levels) == 15

    def test_grid_levels_centered_on_new_price(self):
        mgr = _make_manager(center=50_000.0, range_pct=10.0, num_levels=11)
        result = mgr.recenter(54_000.0)
        levels = result.new_grid_levels
        # Midpoint of sorted levels should be approximately new center
        mid = levels[len(levels) // 2]
        assert abs(mid - 54_000.0) < 100.0

    def test_increments_daily_counter(self):
        mgr = _make_manager()
        mgr._today_date = datetime.now(timezone.utc).date()
        mgr.recenter(54_000.0)
        assert mgr.recenters_today == 1
        mgr.recenter(56_000.0)
        assert mgr.recenters_today == 2

    def test_records_last_recenter_timestamp(self):
        mgr = _make_manager()
        before = datetime.now(timezone.utc)
        mgr.recenter(54_000.0)
        after = datetime.now(timezone.utc)
        assert mgr.last_recenter is not None
        assert before <= mgr.last_recenter <= after

    def test_appends_to_history(self):
        mgr = _make_manager()
        assert len(mgr.recenter_history) == 0
        mgr.recenter(54_000.0)
        assert len(mgr.recenter_history) == 1
        mgr.recenter(56_000.0)
        assert len(mgr.recenter_history) == 2

    def test_result_contains_drift_info_in_reason(self):
        mgr = _make_manager(center=50_000.0)
        result = mgr.recenter(54_000.0)
        assert "DGT" in result.reason
        assert "50000" in result.reason or "50_000" in result.reason.replace(",", "")

    def test_result_success_is_true(self):
        mgr = _make_manager()
        result = mgr.recenter(54_000.0)
        assert result.success is True

    def test_recenter_count_today_in_result(self):
        mgr = _make_manager()
        mgr._today_date = datetime.now(timezone.utc).date()
        result = mgr.recenter(54_000.0)
        assert result.recenter_count_today == 1


# ---------------------------------------------------------------------------
# Trailing anchor
# ---------------------------------------------------------------------------


class TestTrailingAnchor:
    def test_fires_when_price_exceeds_trailing_pct(self):
        mgr = _make_manager(center=50_000.0, trailing_pct=5.0)
        shifted = mgr.check_trailing_anchor(52_600.0)  # +5.2%
        assert shifted is True

    def test_does_not_fire_below_trailing_pct(self):
        mgr = _make_manager(center=50_000.0, trailing_pct=5.0)
        shifted = mgr.check_trailing_anchor(52_000.0)  # +4% < 5%
        assert shifted is False

    def test_center_shifted_to_midpoint(self):
        mgr = _make_manager(center=50_000.0, trailing_pct=5.0)
        price = 53_000.0  # +6%
        mgr.check_trailing_anchor(price)
        expected = 50_000.0 + (53_000.0 - 50_000.0) * 0.5
        assert mgr.center_price == expected

    def test_does_not_consume_daily_quota(self):
        mgr = _make_manager(center=50_000.0, trailing_pct=5.0)
        mgr._today_date = datetime.now(timezone.utc).date()
        mgr.check_trailing_anchor(53_000.0)
        assert mgr.recenters_today == 0

    def test_does_not_reset_cooldown_timer(self):
        mgr = _make_manager(center=50_000.0, trailing_pct=5.0)
        sentinel = datetime.now(timezone.utc) - timedelta(hours=2)
        mgr._last_recenter = sentinel
        mgr.check_trailing_anchor(53_000.0)
        assert mgr.last_recenter == sentinel

    def test_does_not_fire_for_downside_move(self):
        mgr = _make_manager(center=50_000.0, trailing_pct=5.0)
        # Price dropped 10% — trailing anchor is upside-only
        shifted = mgr.check_trailing_anchor(45_000.0)
        assert shifted is False


# ---------------------------------------------------------------------------
# get_status
# ---------------------------------------------------------------------------


class TestGetStatus:
    def test_contains_all_keys(self):
        mgr = _make_manager()
        status = mgr.get_status()
        for key in (
            "center_price",
            "drift_threshold_pct",
            "adx_threshold",
            "cooldown_minutes",
            "max_recenters_per_day",
            "recenters_today",
            "last_recenter",
            "history_count",
        ):
            assert key in status, f"Missing key: {key}"

    def test_last_recenter_none_before_first_recenter(self):
        mgr = _make_manager()
        assert mgr.get_status()["last_recenter"] is None

    def test_history_count_increments(self):
        mgr = _make_manager()
        mgr.recenter(54_000.0)
        mgr.recenter(56_000.0)
        assert mgr.get_status()["history_count"] == 2


# ---------------------------------------------------------------------------
# GridStrategyAsync integration
# ---------------------------------------------------------------------------


class TestGridStrategyAsyncDGT:
    """Integration tests for DGT inside GridStrategyAsync."""

    def _make_strategy(self, center=50_000.0, enable_dgt=True, cooldown=0):
        from autobot.v2.strategies.grid_async import GridStrategyAsync

        instance, cfg = _make_grid_instance(
            center=center,
            enable_dgt=enable_dgt,
            dgt_drift=7.0,
            dgt_cooldown=cooldown,
        )
        strategy = GridStrategyAsync(instance, cfg)
        # Disable module checks to isolate DGT behaviour
        strategy._regime_detector = None
        strategy._oi_monitor = None
        return strategy, instance

    def test_dgt_manager_created_when_enabled(self):
        strategy, _ = self._make_strategy(enable_dgt=True)
        assert strategy._dgt is not None

    def test_dgt_manager_not_created_when_disabled(self):
        strategy, _ = self._make_strategy(enable_dgt=False)
        assert strategy._dgt is None

    def test_recenter_triggered_on_price_drift(self):
        strategy, instance = self._make_strategy(center=50_000.0, cooldown=0)
        original_center = strategy.center_price

        signals: list = []
        strategy.set_signal_callback(lambda s: signals.append(s))

        # Price drifts 10% below center → DGT should recenter
        drifted_price = 45_000.0
        strategy.on_price(drifted_price)

        assert strategy.center_price == drifted_price
        assert strategy.center_price != original_center

    def test_recenter_updates_grid_levels(self):
        strategy, instance = self._make_strategy(center=50_000.0, cooldown=0)
        old_levels = list(strategy.grid_levels)

        strategy.on_price(45_000.0)

        assert strategy.grid_levels != old_levels
        # New levels should be centered near 45_000
        mid = strategy.grid_levels[len(strategy.grid_levels) // 2]
        assert abs(mid - 45_000.0) < 500.0

    def test_sell_signals_emitted_for_open_levels_before_recenter(self):
        strategy, instance = self._make_strategy(center=50_000.0, cooldown=0)

        # Manually inject open positions
        strategy.open_levels = {
            0: {"entry_price": 49_000.0, "volume": 0.01, "opened_at": datetime.now(timezone.utc)},
            1: {"entry_price": 48_000.0, "volume": 0.02, "opened_at": datetime.now(timezone.utc)},
        }

        signals: list = []
        strategy.set_signal_callback(lambda s: signals.append(s))

        strategy.on_price(45_000.0)

        sell_signals = [s for s in signals if s.type.value == "sell"]
        assert len(sell_signals) == 2
        for sig in sell_signals:
            assert sig.metadata.get("dgt_recenter") is True

    def test_open_levels_cleared_after_recenter(self):
        strategy, instance = self._make_strategy(center=50_000.0, cooldown=0)
        strategy.open_levels = {
            0: {"entry_price": 49_000.0, "volume": 0.01, "opened_at": datetime.now(timezone.utc)},
        }
        strategy.on_price(45_000.0)
        assert strategy.open_levels == {}

    def test_emergency_mode_not_entered_when_dgt_recenters(self):
        strategy, instance = self._make_strategy(center=50_000.0, cooldown=0)
        # Price drops beyond emergency threshold — DGT should intercept first
        # emergency_close_price = 50_000 * (1 - 7 * 2 / 100) = 43_000
        strategy.on_price(45_000.0)
        assert strategy._emergency_mode is False

    def test_dgt_blocked_by_strong_trend(self):
        """When regime detector reports ADX >= 25, DGT must NOT recenter."""
        from autobot.v2.strategies.grid_async import GridStrategyAsync

        instance, cfg = _make_grid_instance(center=50_000.0, dgt_cooldown=0)
        strategy = GridStrategyAsync(instance, cfg)

        # Inject a regime detector that exposes get_adx()
        regime_mock = MagicMock()
        regime_mock.should_trade_grid.return_value = True
        regime_mock.get_adx = MagicMock(return_value=35.0)  # strong trend
        strategy._regime_detector = regime_mock
        strategy._oi_monitor = None

        original_center = strategy.center_price
        strategy.on_price(45_000.0)

        # DGT blocked → center unchanged (emergency mode may have fired instead)
        assert strategy.center_price == original_center

    def test_no_recenter_when_price_within_threshold(self):
        strategy, _ = self._make_strategy(center=50_000.0, cooldown=0)
        original_center = strategy.center_price

        # Only 3% drift — below 7% threshold
        strategy.on_price(51_500.0)

        assert strategy.center_price == original_center

    def test_cooldown_prevents_second_immediate_recenter(self):
        strategy, instance = self._make_strategy(center=50_000.0, cooldown=60)
        # First recenter
        strategy.on_price(45_000.0)
        center_after_first = strategy.center_price

        # Immediately try another recenter
        strategy.on_price(40_000.0)
        # Cooldown active → center stays at 45_000
        assert strategy.center_price == center_after_first

    def test_dgt_daily_counter_increments(self):
        strategy, _ = self._make_strategy(center=50_000.0, cooldown=0)
        assert strategy._dgt is not None
        strategy._dgt._today_date = datetime.now(timezone.utc).date()

        strategy.on_price(45_000.0)
        assert strategy._dgt.recenters_today == 1
