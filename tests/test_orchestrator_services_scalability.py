from autobot.v2.orchestrator_services import ScalabilityGuardService, ScalabilityMetrics
from autobot.v2.scalability_guard import GuardThresholds, ScalabilityGuard


def test_scalability_guard_service_evaluates_state():
    guard = ScalabilityGuard(
        GuardThresholds(
            cpu_pct_max=50.0,
            memory_pct_max=80.0,
            ws_stale_seconds_max=10.0,
            ws_lag_max=100,
            execution_failure_rate_max=0.2,
            reconciliation_mismatch_max=0.5,
        )
    )
    service = ScalabilityGuardService(guard)

    decision = service.evaluate(
        ScalabilityMetrics(
            cpu_pct=95.0,
            memory_pct=90.0,
            ws_connected=True,
            ws_stale_seconds=0.0,
            ws_total_lag=0,
            execution_failure_rate=0.0,
            reconciliation_mismatch_ratio=0.0,
            kill_switch_tripped=False,
            pf_degraded=False,
            validation_degraded=False,
        )
    )

    assert decision is not None
    assert decision.state.value in {"FREEZE", "FORCE_REDUCE", "ALLOW_SCALE_UP"}
    assert decision.reasons
