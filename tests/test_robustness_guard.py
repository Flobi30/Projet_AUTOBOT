from autobot.v2.robustness_guard import RobustnessGuard


def test_walk_forward_and_dsr_pass_on_stable_series():
    guard = RobustnessGuard(min_pf=1.01, min_trades=30)
    pnls = [1.2, -0.6, 1.0, -0.4, 1.1, -0.5] * 20
    result = guard.evaluate(pnls)
    assert result["wf_oos_pf"] >= 1.0
    assert result["pbo_cscv"] <= 0.3


def test_walk_forward_fails_on_noisy_negative_series():
    guard = RobustnessGuard(min_pf=1.05, min_trades=30)
    pnls = [0.4, -1.2, 0.3, -1.0, 0.2, -0.9] * 20
    result = guard.evaluate(pnls)
    assert result["pass"] == 0.0


def test_guard_ignores_non_finite_values():
    guard = RobustnessGuard(min_pf=1.01, min_trades=20)
    pnls = [1.0, -0.5, float("nan"), float("inf"), -float("inf")] * 20
    result = guard.evaluate(pnls)
    assert "dsr" in result
    assert "pbo_cscv" in result
    assert result["pbo_proxy"] >= 0.0
