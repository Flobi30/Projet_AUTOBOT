from autobot.v2.config import (
    ENABLE_SCALABILITY_GUARD,
    SCALING_GUARD_CPU_PCT_MAX,
    SCALING_GUARD_EXEC_FAILURE_RATE_MAX,
    SCALING_GUARD_MEMORY_PCT_MAX,
    SCALING_GUARD_RECON_MISMATCH_MAX,
    SCALING_GUARD_WS_LAG_MAX,
    SCALING_GUARD_WS_STALE_SECONDS_MAX,
)
from autobot.v2.scalability_guard import (
    GuardInput,
    GuardThresholds,
    ScalabilityGuard,
    ScalingState,
)


def test_scalability_guard_state_transitions_allow_freeze_force_reduce():
    guard = ScalabilityGuard(
        GuardThresholds(
            cpu_pct_max=80,
            memory_pct_max=80,
            ws_stale_seconds_max=30,
            ws_lag_max=100,
            execution_failure_rate_max=0.2,
            reconciliation_mismatch_max=0.1,
        )
    )

    allow = guard.evaluate(GuardInput(cpu_pct=20, memory_pct=20, ws_connected=True))
    assert allow.state == ScalingState.ALLOW_SCALE_UP

    freeze = guard.evaluate(GuardInput(cpu_pct=81, memory_pct=20, ws_connected=True))
    assert freeze.state == ScalingState.FREEZE
    assert "cpu_pressure" in freeze.reasons

    force_reduce = guard.evaluate(
        GuardInput(cpu_pct=20, memory_pct=20, ws_connected=True, reconciliation_mismatch_ratio=0.2)
    )
    assert force_reduce.state == ScalingState.FORCE_REDUCE
    assert "reconciliation_mismatch" in force_reduce.reasons


def test_scalability_guard_kill_switch_and_reconciliation_veto_behavior():
    guard = ScalabilityGuard(GuardThresholds(reconciliation_mismatch_max=0.05))

    kill_veto = guard.evaluate(GuardInput(kill_switch_tripped=True))
    assert kill_veto.state == ScalingState.FORCE_REDUCE
    assert "kill_switch_tripped" in kill_veto.reasons

    recon_veto = guard.evaluate(GuardInput(reconciliation_mismatch_ratio=0.10))
    assert recon_veto.state == ScalingState.FORCE_REDUCE
    assert "reconciliation_mismatch" in recon_veto.reasons


def test_scalability_guard_default_thresholds_are_conservative_for_current_deployment():
    # feature is safe by default: disabled
    assert ENABLE_SCALABILITY_GUARD is False

    # conservative threshold sanity checks
    assert 80 <= SCALING_GUARD_CPU_PCT_MAX <= 100
    assert 80 <= SCALING_GUARD_MEMORY_PCT_MAX <= 100
    assert SCALING_GUARD_WS_STALE_SECONDS_MAX >= 30
    assert SCALING_GUARD_WS_LAG_MAX >= 1000
    assert 0.2 <= SCALING_GUARD_EXEC_FAILURE_RATE_MAX <= 1.0
    assert 0.0 < SCALING_GUARD_RECON_MISMATCH_MAX <= 0.1
