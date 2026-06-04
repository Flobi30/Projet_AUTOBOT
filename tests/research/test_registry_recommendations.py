import json

import pytest

from autobot.v2.research.registry_recommendations import (
    RegistryRecommendationCriteria,
    load_matrix_result,
    recommend_from_matrix,
    write_registry_recommendation_report,
)
from autobot.v2.research.validation_matrix import MatrixCellResult, MatrixRunResult


pytestmark = pytest.mark.unit


def _matrix(cells, *, mode="backtest"):
    return MatrixRunResult(
        run_id="pytest_matrix",
        mode=mode,
        cell_count=len(cells),
        success_count=sum(1 for cell in cells if cell.status == "ok"),
        error_count=sum(1 for cell in cells if cell.status == "error"),
        results=tuple(cells),
    )


def _cell(
    strategy,
    *,
    symbol="TRXEUR",
    decision="promote_candidate",
    reason="backtest_criteria_passed_for_human_review",
    closed_trades=40,
    net_pnl_eur=12.0,
    profit_factor=1.4,
    max_drawdown_pct=4.0,
    mode="backtest",
    status="ok",
    error=None,
):
    return MatrixCellResult(
        run_id=f"pytest_{symbol}_{strategy}",
        symbol=symbol,
        strategy=strategy,
        mode=mode,
        status=status,
        decision=decision,
        reason=reason,
        bar_count=120,
        closed_trades=closed_trades,
        net_pnl_eur=net_pnl_eur,
        total_return_pct=1.2,
        profit_factor=profit_factor,
        max_drawdown_pct=max_drawdown_pct,
        report_path=f"reports/{symbol}_{strategy}.md",
        error=error,
    )


def test_recommendation_promotes_only_to_next_safe_registry_step():
    registry = {
        "hypotheses": [
            {"strategy_id": "trend_momentum", "validation_status": "learning"},
            {"strategy_id": "dynamic_grid", "validation_status": "candidate"},
        ]
    }
    report = recommend_from_matrix(
        _matrix(
            [
                _cell("trend", symbol="BTCEUR"),
                _cell("grid", symbol="TRXEUR"),
            ]
        ),
        registry_payload=registry,
    )

    by_strategy = {item.strategy: item for item in report.recommendations}

    assert by_strategy["grid"].recommended_status == "backtest_passed"
    assert by_strategy["grid"].live_promotion_allowed is False
    assert by_strategy["grid"].registry_update_applied is False

    assert by_strategy["trend"].recommended_status == "candidate"
    assert by_strategy["trend"].evidence_status == "backtest_passed"
    assert "workflow_step_required" in by_strategy["trend"].reason
    assert by_strategy["trend"].live_promotion_allowed is False


def test_negative_matrix_recommends_rejection_without_live_permission():
    report = recommend_from_matrix(
        _matrix(
            [
                _cell(
                    "mean_reversion",
                    decision="reject",
                    reason="negative_net_pnl",
                    closed_trades=55,
                    net_pnl_eur=-8.0,
                    profit_factor=0.72,
                    max_drawdown_pct=8.5,
                )
            ]
        ),
        registry_payload={"hypotheses": [{"strategy_id": "mean_reversion", "validation_status": "candidate"}]},
    )

    recommendation = report.recommendations[0]

    assert recommendation.recommended_status == "rejected"
    assert recommendation.decision == "reject"
    assert recommendation.reason == "non_positive_aggregate_net_pnl"
    assert recommendation.live_promotion_allowed is False


def test_insufficient_sample_keeps_strategy_in_learning_or_candidate():
    report = recommend_from_matrix(
        _matrix(
            [
                _cell(
                    "grid",
                    decision="keep_testing",
                    reason="insufficient_closed_trades",
                    closed_trades=4,
                    net_pnl_eur=2.0,
                    profit_factor=2.0,
                    max_drawdown_pct=0.5,
                )
            ]
        ),
        registry_payload={"hypotheses": [{"strategy_id": "dynamic_grid", "validation_status": "learning"}]},
    )

    recommendation = report.recommendations[0]

    assert recommendation.decision == "keep_testing"
    assert recommendation.recommended_status == "candidate"
    assert recommendation.reason == "insufficient_closed_trades"


def test_walk_forward_matrix_recommends_walk_forward_passed_after_backtest_stage():
    report = recommend_from_matrix(
        _matrix(
            [
                _cell(
                    "grid",
                    decision="walk_forward_passed",
                    reason="walk_forward_criteria_passed_for_human_review",
                    mode="walk_forward",
                    profit_factor=None,
                )
            ],
            mode="walk_forward",
        ),
        registry_payload={"hypotheses": [{"strategy_id": "dynamic_grid", "validation_status": "backtest_passed"}]},
    )

    recommendation = report.recommendations[0]

    assert recommendation.recommended_status == "walk_forward_passed"
    assert recommendation.decision == "promote_candidate"
    assert recommendation.live_promotion_allowed is False


def test_report_writer_and_loader_round_trip_matrix_json(tmp_path):
    matrix = _matrix([_cell("grid")])
    matrix_json = tmp_path / "matrix.json"
    matrix_json.write_text(json.dumps(matrix.to_dict()), encoding="utf-8")

    loaded = load_matrix_result(matrix_json)
    report = write_registry_recommendation_report(
        recommend_from_matrix(loaded, criteria=RegistryRecommendationCriteria(min_closed_trades=10)),
        tmp_path / "recommendations",
    )

    assert loaded.run_id == "pytest_matrix"
    assert report.json_report_path
    assert report.markdown_report_path
    assert (tmp_path / "recommendations" / "pytest_matrix_registry_recommendations.json").exists()
    markdown = (tmp_path / "recommendations" / "pytest_matrix_registry_recommendations.md").read_text(
        encoding="utf-8"
    )
    assert "No live trading permission is granted" in markdown


def test_loader_accepts_validate_strategies_workflow_json(tmp_path):
    matrix = _matrix([_cell("grid")])
    workflow_json = tmp_path / "validate_strategies.json"
    workflow_json.write_text(
        json.dumps(
            {
                "command": "validate-strategies",
                "dataset": {"run_id": "pytest_dataset"},
                "matrix": matrix.to_dict(),
            }
        ),
        encoding="utf-8",
    )

    loaded = load_matrix_result(workflow_json)

    assert loaded.run_id == "pytest_matrix"
    assert loaded.cell_count == 1
    assert loaded.results[0].strategy == "grid"
