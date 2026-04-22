import pytest

import time

from autobot.v2.robustness_guard import RobustnessGuard
from autobot.v2.safety_guard import SafetyGuard


pytestmark = pytest.mark.integration

def test_dsr_slow_path_returns_neutral_immediately():
    guard = RobustnessGuard(min_pf=1.01, min_trades=20)
    guard.configure_safety(dsr_timeout_ms=50, dsr_cache_s=300)
    guard._last_dsr_exec_ms = 100.0
    t0 = time.perf_counter()
    value = guard.evaluate_dsr_safe([0.2, -0.1, 0.3] * 50)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    assert value == 1.0
    assert elapsed_ms < 5.0


def test_walk_forward_auto_bypass_when_block_ratio_too_high():
    guard = RobustnessGuard(min_pf=2.0, min_trades=20)
    guard.configure_safety(max_block_ratio=0.8)
    pnls = [-1.0, 0.1, -0.9, 0.2] * 50
    assert guard.validate_walk_forward_safe(pnls, instance_age_days=30) is True


def test_safety_guard_switches_to_emergency_after_three_slow_cycles():
    sg = SafetyGuard(emergency_cycle_ms=100, emergency_consecutive=3)
    assert sg.check_performance_budget(150.0) is True
    assert sg.check_performance_budget(150.0) is True
    assert sg.check_performance_budget(150.0) is False
    assert sg.emergency_mode is True
