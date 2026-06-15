import pytest

from autobot.v2.research.instance_split_validation_harness import (
    run_instance_split_validation,
)


pytestmark = pytest.mark.unit


def _evidence(**overrides):
    payload = {
        "parent_instance_id": "parent-validation",
        "parent_capital_eur": 4000.0,
        "parent_available_eur": 3000.0,
        "parent_lifetime_split_count": 0,
        "paper_mode": True,
        "strategy_id": "trend_momentum",
        "strategy_status": "paper_validated",
        "net_pnl_eur": 250.0,
        "profit_factor": 1.45,
        "trade_count": 180,
        "validation_days": 14,
        "max_drawdown_pct": 6.0,
        "strategy_scorecard": 84.0,
        "dominant_failure_mode": "healthy",
        "official_paper_net_pnl_eur": 220.0,
        "live_promotion_allowed": False,
    }
    payload.update(overrides)
    return payload


def test_validation_harness_proves_split_isolation_and_lifetime_rule(tmp_path):
    result = run_instance_split_validation(
        run_id="pytest_split_validation",
        evidence=_evidence(),
        output_dir=tmp_path,
    )

    assert result.status == "PASS"
    assert result.checks["capital_conserved_at_split"] is True
    assert result.checks["child_state_changes_independently"] is True
    assert result.checks["lineage_persisted"] is True
    assert result.checks["second_split_blocked_for_lifetime"] is True
    assert result.checks["no_order_path"] is True
    assert result.first_decision["live_promotion_allowed"] is False
    assert "parent_already_split" in result.second_decision["blockers"]
    assert (tmp_path / "pytest_split_validation.md").exists()
    assert (tmp_path / "pytest_split_validation.json").exists()


def test_validation_harness_refuses_live_mode(tmp_path):
    result = run_instance_split_validation(
        run_id="pytest_split_validation_live_block",
        evidence=_evidence(paper_mode=False),
        output_dir=tmp_path,
    )

    assert result.status == "FAIL"
    assert result.first_decision["executable_now"] is False
    assert "paper_mode_required" in result.first_decision["blockers"]
