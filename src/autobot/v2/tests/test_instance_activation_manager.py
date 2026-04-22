import pytest

from autobot.v2.instance_activation_manager import ActivationInput, InstanceActivationManager
from autobot.v2.scalability_guard import ScalingState


pytestmark = pytest.mark.unit

def _inp(now, score=80, health=85, guard=ScalingState.ALLOW_SCALE_UP, ranked=10, running=1):
    symbols = [f"SYM{i}" for i in range(ranked)]
    return ActivationInput(
        ranked_symbols=symbols,
        avg_rank_score=score,
        guard_state=guard,
        health_score=health,
        running_instances=running,
        now_ts=float(now),
    )


def test_activation_manager_promotion_path_1_to_2_to_5():
    m = InstanceActivationManager(
        default_tier=1,
        hysteresis_cycles=1,
        cooldown_seconds=1,
        promote_score_min=70,
        demote_score_max=40,
        promote_health_min=70,
        demote_health_max=50,
    )

    d1 = m.decide(_inp(10, ranked=10))
    assert d1.action == "promote"
    assert d1.target_tier == 2

    d2 = m.decide(_inp(12, ranked=10))
    assert d2.action == "promote"
    assert d2.target_tier == 5


def test_activation_manager_demotion_conditions():
    m = InstanceActivationManager(
        default_tier=5,
        hysteresis_cycles=1,
        cooldown_seconds=1,
        promote_score_min=70,
        demote_score_max=45,
        promote_health_min=70,
        demote_health_max=50,
    )

    d = m.decide(_inp(10, score=30, health=40, ranked=5, running=5))
    assert d.action == "demote"
    assert d.target_tier == 2


def test_activation_manager_hysteresis_anti_thrashing():
    m = InstanceActivationManager(
        default_tier=1,
        hysteresis_cycles=2,
        cooldown_seconds=1,
        promote_score_min=70,
        demote_score_max=45,
        promote_health_min=70,
        demote_health_max=50,
    )

    first = m.decide(_inp(10, score=80, health=80, ranked=10))
    second = m.decide(_inp(12, score=80, health=80, ranked=10))

    assert first.action == "hold"
    assert first.reason == "promote_hysteresis"
    assert second.action == "promote"
    assert second.target_tier == 2


def test_activation_manager_default_conservative_tier_1_and_freeze():
    m = InstanceActivationManager(default_tier=1, hysteresis_cycles=1, cooldown_seconds=60)
    d = m.decide(_inp(10, guard=ScalingState.FREEZE, running=3, ranked=10))

    assert m.current_tier == 1
    assert d.action == "freeze"
    assert d.target_tier == 1
    assert d.target_instances <= 1
