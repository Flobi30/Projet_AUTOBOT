import pytest

from autobot.v2.instance_split_policy import (
    EXECUTION_FLAG_NAME,
    InstanceSplitEvidence,
    InstanceSplitPolicy,
    InstanceSplitPolicyConfig,
)


pytestmark = pytest.mark.unit


def _evidence(**overrides):
    payload = {
        "parent_instance_id": "parent_1",
        "strategy_id": "dynamic_grid",
        "strategy_status": "paper_candidate",
        "paper_mode": True,
        "live_promotion_allowed": False,
        "parent_lifetime_split_count": 0,
        "parent_capital_eur": 4000.0,
        "parent_available_eur": 2000.0,
        "net_pnl_eur": 50.0,
        "official_paper_net_pnl_eur": 50.0,
        "profit_factor": 1.5,
        "trade_count": 150,
        "validation_days": 10,
        "max_drawdown_pct": 6.0,
        "strategy_scorecard": 82.0,
        "dominant_failure_mode": "healthy",
    }
    payload.update(overrides)
    return InstanceSplitEvidence(**payload)


def test_split_policy_can_plan_but_executor_is_disabled_by_default():
    decision = InstanceSplitPolicy().evaluate(_evidence())

    assert decision.allowed_to_plan is True
    assert decision.executable_now is False
    assert decision.live_promotion_allowed is False
    assert EXECUTION_FLAG_NAME in decision.config["feature_flag"]


def test_split_policy_blocks_when_paper_mode_is_false():
    decision = InstanceSplitPolicy().evaluate(_evidence(paper_mode=False))

    assert decision.allowed_to_plan is False
    assert "paper_mode_required" in decision.blockers


def test_split_policy_blocks_parent_that_already_split():
    decision = InstanceSplitPolicy().evaluate(_evidence(parent_lifetime_split_count=1))

    assert decision.allowed_to_plan is False
    assert "parent_already_split" in decision.blockers


def test_split_policy_blocks_unvalidated_strategy_and_weak_mfe():
    decision = InstanceSplitPolicy().evaluate(
        _evidence(strategy_status="research_only", dominant_failure_mode="weak_mfe_below_cost")
    )

    assert decision.allowed_to_plan is False
    assert "strategy_status_not_validated" in decision.blockers
    assert "blocked_failure_mode:weak_mfe_below_cost" in decision.blockers


def test_split_policy_blocks_live_promotion_signal_even_with_good_metrics():
    decision = InstanceSplitPolicy(InstanceSplitPolicyConfig(executor_enabled=True)).evaluate(
        _evidence(live_promotion_allowed=True)
    )

    assert decision.allowed_to_plan is False
    assert decision.executable_now is False
    assert decision.live_promotion_allowed is False
    assert "live_promotion_must_remain_false" in decision.blockers
