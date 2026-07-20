"""
Tests for ShadowTradingManager – AutoBot V2
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
35 tests covering:
  - registration (valid, duplicate, bad mode)
  - update_performance (normal, research eligibility, negative values)
  - legacy promotion and capital-transfer quarantine
  - get_status (empty, populated, research-only)
  - validation durations per mode
  - thread safety (concurrent registration)
  - edge cases (PF exactly 1.5, boundary day)
"""

from __future__ import annotations

import threading
import time
from unittest.mock import patch

import pytest
import sys, os

pytestmark = pytest.mark.integration

# Direct import bypassing autobot.v2.__init__ (which pulls heavy deps like orjson)
import importlib.util as _ilu

_spec = _ilu.spec_from_file_location(
    "shadow_trading",
    os.path.join(os.path.dirname(__file__), "..", "src", "autobot", "v2", "shadow_trading.py"),
)
_shadow = _ilu.module_from_spec(_spec)
sys.modules[_spec.name] = _shadow
_spec.loader.exec_module(_shadow)

Mode = _shadow.Mode
InstanceState = _shadow.InstanceState
ShadowInstance = _shadow.ShadowInstance
ShadowTradingManager = _shadow.ShadowTradingManager
PF_PROMOTION_THRESHOLD = _shadow.PF_PROMOTION_THRESHOLD
VALIDATION_DAYS = _shadow.VALIDATION_DAYS


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_manager_with_aged_instance(
    instance_id: str = "BTC-001",
    mode: str = "crypto",
    age_days: int = 15,
    pf: float = 1.8,
    trades: int = 50,
) -> ShadowTradingManager:
    """Create a manager with a single instance whose registration time is backdated."""
    mgr = ShadowTradingManager()
    mgr.register_instance(instance_id, mode)
    # Backdate registration (monotonic clock)
    inst = mgr._instances[instance_id]
    inst.registered_at = time.monotonic() - age_days * 86_400
    mgr.update_performance(instance_id, pf, trades)
    return mgr


# Registration

class TestRegistration:

    def test_register_crypto(self):
        mgr = ShadowTradingManager()
        mgr.register_instance("BTC-001", "crypto")
        assert "BTC-001" in mgr._instances
        assert mgr._instances["BTC-001"].mode == Mode.CRYPTO

    def test_register_forex(self):
        mgr = ShadowTradingManager()
        mgr.register_instance("EUR-001", "forex")
        assert mgr._instances["EUR-001"].mode == Mode.FOREX

    def test_register_commodities(self):
        mgr = ShadowTradingManager()
        mgr.register_instance("OIL-001", "commodities")
        assert mgr._instances["OIL-001"].mode == Mode.COMMODITIES

    def test_register_duplicate_raises(self):
        mgr = ShadowTradingManager()
        mgr.register_instance("BTC-001", "crypto")
        with pytest.raises(ValueError, match="already registered"):
            mgr.register_instance("BTC-001", "crypto")

    def test_register_invalid_mode_raises(self):
        mgr = ShadowTradingManager()
        with pytest.raises(ValueError, match="Invalid mode"):
            mgr.register_instance("X-001", "stocks")

    def test_register_after_rejected_transfer_is_still_a_duplicate(self):
        """A rejected legacy transfer cannot manufacture a live conflict."""
        mgr = _make_manager_with_aged_instance("BTC-001", "crypto", 15, 2.0, 60)
        assert mgr.transfer_capital("BTC-001", 1000.0) is False
        with pytest.raises(ValueError, match="already registered"):
            mgr.register_instance("BTC-001", "crypto")


# Update performance

class TestUpdatePerformance:

    def test_update_basic(self):
        mgr = ShadowTradingManager()
        mgr.register_instance("BTC-001", "crypto")
        result = mgr.update_performance("BTC-001", 1.2, 30)
        assert result is False  # validation period not elapsed
        assert mgr._instances["BTC-001"].pf == 1.2
        assert mgr._instances["BTC-001"].trades == 30

    def test_update_returns_true_when_eligible(self):
        mgr = _make_manager_with_aged_instance("BTC-001", "crypto", 15, 1.6, 40)
        # Re-update to trigger fresh return
        result = mgr.update_performance("BTC-001", 1.7, 50)
        assert result is True

    def test_update_not_eligible_low_pf(self):
        mgr = ShadowTradingManager()
        mgr.register_instance("BTC-001", "crypto")
        mgr._instances["BTC-001"].registered_at = time.monotonic() - 15 * 86_400
        result = mgr.update_performance("BTC-001", 1.2, 40)
        assert result is False

    def test_update_not_eligible_too_early(self):
        mgr = ShadowTradingManager()
        mgr.register_instance("BTC-001", "crypto")
        # Just registered - 0 days elapsed
        result = mgr.update_performance("BTC-001", 2.0, 40)
        assert result is False

    def test_update_after_rejected_transfer_remains_research_only(self):
        mgr = _make_manager_with_aged_instance("BTC-001", "crypto", 15, 2.0, 60)
        assert mgr.transfer_capital("BTC-001", 1000.0) is False
        result = mgr.update_performance("BTC-001", 2.5, 80)
        assert result is True
        assert mgr._instances["BTC-001"].state is InstanceState.SHADOW

    def test_update_negative_pf_raises(self):
        mgr = ShadowTradingManager()
        mgr.register_instance("BTC-001", "crypto")
        with pytest.raises(ValueError, match="non-negative"):
            mgr.update_performance("BTC-001", -0.5, 10)

    def test_update_negative_trades_raises(self):
        mgr = ShadowTradingManager()
        mgr.register_instance("BTC-001", "crypto")
        with pytest.raises(ValueError, match="non-negative"):
            mgr.update_performance("BTC-001", 1.0, -1)

    def test_update_unknown_instance_raises(self):
        mgr = ShadowTradingManager()
        with pytest.raises(KeyError, match="not found"):
            mgr.update_performance("NOPE", 1.0, 10)


# should_promote_to_live

class TestShouldPromote:

    def test_not_ready_fresh(self):
        mgr = ShadowTradingManager()
        mgr.register_instance("BTC-001", "crypto")
        mgr.update_performance("BTC-001", 2.0, 50)
        assert mgr.should_promote_to_live("BTC-001") is False

    def test_ready_after_validation_is_still_not_promotable(self):
        mgr = _make_manager_with_aged_instance("BTC-001", "crypto", 15, 1.8, 50)
        assert mgr.should_promote_to_live("BTC-001") is False

    def test_not_ready_pf_below_threshold(self):
        mgr = _make_manager_with_aged_instance("BTC-001", "crypto", 15, 1.4, 50)
        assert mgr.should_promote_to_live("BTC-001") is False

    def test_rejected_transfer_does_not_change_promotion_answer(self):
        mgr = _make_manager_with_aged_instance("BTC-001", "crypto", 15, 2.0, 60)
        assert mgr.transfer_capital("BTC-001", 500.0) is False
        assert mgr.should_promote_to_live("BTC-001") is False

    def test_pf_exactly_threshold_is_not_a_promotion_gate(self):
        mgr = _make_manager_with_aged_instance("BTC-001", "crypto", 14, 1.5, 40)
        assert mgr.should_promote_to_live("BTC-001") is False


# transfer_capital

class TestTransferCapital:

    def test_transfer_is_rejected_without_state_or_capital_mutation(self):
        mgr = _make_manager_with_aged_instance("BTC-001", "crypto", 15, 2.0, 60)
        before = mgr._instances["BTC-001"]
        before_capital = before.paper_capital
        assert mgr.transfer_capital("BTC-001", 1000.0) is False
        inst = mgr._instances["BTC-001"]
        assert inst.state is InstanceState.SHADOW
        assert inst.paper_capital == before_capital
        assert mgr.get_status()["live_ids"] == []

    def test_transfer_not_qualified(self):
        mgr = ShadowTradingManager()
        mgr.register_instance("BTC-001", "crypto")
        assert mgr.transfer_capital("BTC-001", 1000.0) is False

    def test_transfer_zero_amount(self):
        mgr = _make_manager_with_aged_instance("BTC-001", "crypto", 15, 2.0, 60)
        assert mgr.transfer_capital("BTC-001", 0) is False

    def test_transfer_negative_amount(self):
        mgr = _make_manager_with_aged_instance("BTC-001", "crypto", 15, 2.0, 60)
        assert mgr.transfer_capital("BTC-001", -500.0) is False


# get_status

class TestGetStatus:

    def test_status_empty(self):
        mgr = ShadowTradingManager()
        status = mgr.get_status()
        assert status["total_instances"] == 0
        assert status["shadow_count"] == 0
        assert status["promoted_count"] == 0
        assert status["instances"] == {}

    def test_status_with_instances(self):
        mgr = _make_manager_with_aged_instance("BTC-001", "crypto", 15, 1.8, 50)
        mgr.register_instance("EUR-001", "forex")
        status = mgr.get_status()
        assert status["total_instances"] == 2
        assert status["shadow_count"] == 2
        assert "BTC-001" in status["instances"]
        assert status["instances"]["BTC-001"]["pf"] == 1.8

    def test_status_after_rejected_promotion_stays_shadow(self):
        mgr = _make_manager_with_aged_instance("BTC-001", "crypto", 15, 2.0, 60)
        assert mgr.transfer_capital("BTC-001", 1000.0) is False
        status = mgr.get_status()
        assert status["promoted_count"] == 0
        assert status["shadow_count"] == 1
        assert status["live_ids"] == []
        assert status["instances"]["BTC-001"]["state"] == "shadow"


# Validation durations

class TestValidationDurations:

    @pytest.mark.parametrize("mode,expected_days", [
        ("crypto", 14),
        ("forex", 21),
        ("commodities", 28),
    ])
    def test_validation_days(self, mode, expected_days):
        mgr = ShadowTradingManager()
        mgr.register_instance("T-001", mode)
        inst = mgr._instances["T-001"]
        assert inst.validation_days == expected_days

    def test_forex_not_ready_at_20_days(self):
        mgr = _make_manager_with_aged_instance("EUR-001", "forex", 20, 2.0, 60)
        assert mgr.should_promote_to_live("EUR-001") is False

    def test_forex_numerically_ready_is_still_not_promotable(self):
        mgr = _make_manager_with_aged_instance("EUR-001", "forex", 21, 2.0, 60)
        assert mgr.should_promote_to_live("EUR-001") is False

    def test_commodities_not_ready_at_27_days(self):
        mgr = _make_manager_with_aged_instance("OIL-001", "commodities", 27, 2.0, 60)
        assert mgr.should_promote_to_live("OIL-001") is False

    def test_commodities_numerically_ready_is_still_not_promotable(self):
        mgr = _make_manager_with_aged_instance("OIL-001", "commodities", 28, 2.0, 60)
        assert mgr.should_promote_to_live("OIL-001") is False


# Thread safety

class TestThreadSafety:

    def test_concurrent_registrations(self):
        mgr = ShadowTradingManager()
        errors: list[Exception] = []

        def register(iid: str):
            try:
                mgr.register_instance(iid, "crypto")
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=register, args=(f"T-{i:03d}",))
                   for i in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(mgr._instances) == 100

    def test_concurrent_updates(self):
        mgr = _make_manager_with_aged_instance("BTC-001", "crypto", 15, 1.0, 10)
        results: list[bool] = []

        def update(pf: float):
            r = mgr.update_performance("BTC-001", pf, 50)
            results.append(r)

        threads = [threading.Thread(target=update, args=(1.5 + i * 0.01,))
                   for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 50
        # All should return True (aged + PF >= 1.5)
        assert all(results)
