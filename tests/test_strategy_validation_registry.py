import json
from pathlib import Path

import pytest

from autobot.v2.strategy_validation_registry import (
    REQUIRED_STRATEGY_FIELDS,
    WORKFLOW_STATUSES,
    StrategyAcceptanceCriteria,
    StrategyValidationError,
    assert_can_transition,
    assert_valid_registry,
    can_execute_official_paper,
    can_request_live_review,
    can_transition,
    entry_by_strategy_id,
    evaluate_promotion,
    load_registry,
    validate_registry,
    validate_strategy_entry,
)


pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = REPO_ROOT / "docs" / "research" / "strategy_hypotheses.json"


def _passing_backtest_metrics() -> dict:
    return {
        "closed_trades": 64,
        "profit_factor": 1.42,
        "net_pnl_eur": 12.5,
        "max_drawdown_pct": 5.2,
        "sharpe": 0.55,
        "sortino": 0.31,
        "fees_included": True,
        "slippage_included": True,
        "baseline_comparison": True,
        "baseline_delta_eur": 3.1,
        "out_of_sample_periods": 2,
    }


def test_strategy_registry_json_is_valid_and_has_required_fields():
    payload = load_registry(REGISTRY_PATH)

    assert payload["decision_statuses"] == list(WORKFLOW_STATUSES)
    assert validate_registry(payload) == []

    for entry in payload["hypotheses"]:
        assert set(REQUIRED_STRATEGY_FIELDS).issubset(entry.keys())
        assert entry["validation_status"] in WORKFLOW_STATUSES
        assert entry["baseline_comparison"]
        assert entry["fees_model"]
        assert entry["slippage_model"]


def test_strategy_registry_rejects_missing_baseline():
    payload = load_registry(REGISTRY_PATH)
    broken = json.loads(json.dumps(payload))
    broken["hypotheses"][0]["baseline_comparison"] = {}

    errors = validate_registry(broken)

    assert any("baseline_comparison_missing" in error for error in errors)
    with pytest.raises(StrategyValidationError):
        assert_valid_registry(broken)


def test_workflow_status_transitions_do_not_skip_stages():
    assert can_transition("learning", "candidate") is True
    assert can_transition("candidate", "backtest_passed") is True
    assert can_transition("learning", "paper_validated") is False
    assert can_transition("paper_validated", "candidate") is False
    assert can_transition("candidate", "rejected") is True
    assert can_transition("shadow_passed", "retired_from_execution") is True

    with pytest.raises(StrategyValidationError):
        assert_can_transition("learning", "shadow_passed")


def test_strategy_cannot_be_promoted_without_sufficient_metrics():
    decision = evaluate_promotion(
        current_status="candidate",
        target_status="backtest_passed",
        metrics={
            "closed_trades": 8,
            "profit_factor": 0.9,
            "net_pnl_eur": -1.0,
            "fees_included": True,
            "slippage_included": True,
            "baseline_comparison": True,
            "out_of_sample_periods": 1,
        },
    )

    assert decision.allowed is False
    assert "closed_trades" in decision.reasons
    assert "profit_factor" in decision.reasons
    assert "net_pnl_eur" in decision.reasons


def test_strategy_must_be_compared_to_baseline():
    metrics = _passing_backtest_metrics()
    metrics["baseline_comparison"] = False

    decision = evaluate_promotion(
        current_status="candidate",
        target_status="backtest_passed",
        metrics=metrics,
    )

    assert decision.allowed is False
    assert "baseline_comparison" in decision.reasons


def test_fees_and_slippage_are_required_for_validated_backtests():
    metrics = _passing_backtest_metrics()
    metrics["fees_included"] = False
    metrics["slippage_included"] = False

    decision = evaluate_promotion(
        current_status="candidate",
        target_status="backtest_passed",
        metrics=metrics,
    )

    assert decision.allowed is False
    assert "fees_included" in decision.reasons
    assert "slippage_included" in decision.reasons


def test_backtest_cannot_pass_without_out_of_sample_period():
    metrics = _passing_backtest_metrics()
    metrics["out_of_sample_periods"] = 0

    decision = evaluate_promotion(
        current_status="candidate",
        target_status="backtest_passed",
        metrics=metrics,
    )

    assert decision.allowed is False
    assert "out_of_sample_periods" in decision.reasons


def test_backtest_passes_when_required_cost_baseline_and_oos_exist():
    decision = evaluate_promotion(
        current_status="candidate",
        target_status="backtest_passed",
        metrics=_passing_backtest_metrics(),
    )

    assert decision.allowed is True
    assert decision.reasons == ()


def test_shadow_and_paper_statuses_have_stricter_evidence_requirements():
    metrics = _passing_backtest_metrics()
    metrics.update(
        {
            "shadow_closed_trades": 32,
            "shadow_profit_factor": 1.31,
            "shadow_net_pnl_eur": 2.8,
        }
    )
    shadow = evaluate_promotion(
        current_status="walk_forward_passed",
        target_status="shadow_passed",
        metrics=metrics,
    )
    assert shadow.allowed is True

    paper = evaluate_promotion(
        current_status="shadow_passed",
        target_status="paper_validated",
        metrics=metrics,
    )
    assert paper.allowed is False
    assert "paper_closed_trades" in paper.reasons

    metrics.update(
        {
            "paper_closed_trades": 120,
            "paper_profit_factor": 1.23,
            "paper_net_pnl_eur": 15.0,
            "paper_max_drawdown_pct": 6.5,
        }
    )
    paper = evaluate_promotion(
        current_status="shadow_passed",
        target_status="paper_validated",
        metrics=metrics,
    )
    assert paper.allowed is True


def test_registry_entries_define_official_paper_and_live_review_eligibility():
    payload = load_registry(REGISTRY_PATH)

    dynamic_grid = entry_by_strategy_id(payload, "dynamic_grid")
    no_trade = entry_by_strategy_id(payload, "no_trade_baseline")

    assert dynamic_grid is not None
    assert no_trade is not None
    assert can_execute_official_paper(dynamic_grid) is False
    assert can_request_live_review(dynamic_grid) is False
    assert can_execute_official_paper(no_trade) is False
    assert can_request_live_review(no_trade) is False


def test_malformed_strategy_entry_blocks_paper_and_live_eligibility():
    payload = load_registry(REGISTRY_PATH)
    no_trade = dict(entry_by_strategy_id(payload, "no_trade_baseline"))
    no_trade["validation_status"] = "paper_validated"
    no_trade["baseline_comparison"] = {}
    no_trade.pop("fees_model")

    errors = validate_strategy_entry(no_trade, label="no_trade_baseline")

    assert "no_trade_baseline:baseline_comparison_missing" in errors
    assert "no_trade_baseline:fees_model_missing" in errors
    assert can_execute_official_paper(no_trade) is False
    assert can_request_live_review(no_trade) is False


def test_thresholds_can_be_configured_for_low_sample_research_tests():
    criteria = StrategyAcceptanceCriteria(
        min_closed_trades=3,
        min_profit_factor=1.1,
        min_sharpe=0.0,
    )
    metrics = _passing_backtest_metrics()
    metrics["closed_trades"] = 3
    metrics["profit_factor"] = 1.11
    metrics["sharpe"] = 0.01

    decision = evaluate_promotion(
        current_status="candidate",
        target_status="backtest_passed",
        metrics=metrics,
        criteria=criteria,
    )

    assert decision.allowed is True
