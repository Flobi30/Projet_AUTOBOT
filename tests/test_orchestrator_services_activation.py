import pytest

from autobot.v2.instance_activation_manager import InstanceActivationManager
from autobot.v2.orchestrator_services import ActivationContext, InstanceActivationService
from autobot.v2.scalability_guard import ScalingState


pytestmark = pytest.mark.integration

def test_instance_activation_service_returns_decision_payload():
    manager = InstanceActivationManager(
        default_tier=2,
        promote_score_min=0.5,
        demote_score_max=0.3,
        promote_health_min=0.7,
        demote_health_max=0.4,
        hysteresis_cycles=1,
        cooldown_seconds=0,
    )
    service = InstanceActivationService(manager)
    context = ActivationContext(
        ranked_symbols=["BTC/USD", "ETH/USD", "XRP/USD"],
        scored_map={
            "BTC/USD": {"score": 0.9},
            "ETH/USD": {"score": 0.7},
            "XRP/USD": {"score": 0.1},
        },
        guard_state=ScalingState.ALLOW_SCALE_UP,
        health_score=0.8,
        running_instances=1,
        now_ts=100.0,
    )

    result = service.apply(context)

    assert result is not None
    assert result.target_instances >= 1
    assert "action" in result.payload
    assert "XRP/USD" in result.rejected_symbols


def test_instance_activation_service_below_threshold_symbols():
    symbols = ["BTC/USD", "ETH/USD"]
    scored = {"BTC/USD": {"score": 0.8}, "ETH/USD": {"score": 0.0}}
    lows = InstanceActivationService.below_threshold_symbols(symbols, scored)
    assert "ETH/USD" in lows
