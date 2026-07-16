import json

import pytest

from autobot.v2.research.strategy_scorecard import (
    StrategyEvidence,
    score_matrix,
    score_strategy,
    write_strategy_scorecard_report,
)
from autobot.v2.research.validation_matrix import MatrixCellResult, MatrixRunResult


pytestmark = pytest.mark.unit


def _evidence(**overrides):
    defaults = {
        "strategy_id": "trend_momentum",
        "source": "backtest",
        "closed_trades": 80,
        "net_pnl_eur": 42.0,
        "gross_pnl_eur": 64.0,
        "profit_factor": 1.55,
        "expectancy_eur": 0.525,
        "max_drawdown_pct": 4.0,
        "total_return_pct": 4.2,
        "baseline_delta_pct": 1.1,
        "regimes_tested": 3,
        "positive_regimes": 2,
        "fees_included": True,
        "slippage_included": True,
        "baseline_included": True,
        "out_of_sample_included": True,
    }
    defaults.update(overrides)
    return StrategyEvidence(**defaults)


def _cell(strategy, **overrides):
    defaults = {
        "run_id": f"pytest_{strategy}",
        "symbol": "TRXEUR",
        "strategy": strategy,
        "mode": "backtest",
        "status": "ok",
        "decision": "promote_candidate",
        "reason": "criteria_passed",
        "bar_count": 100,
        "closed_trades": 40,
        "net_pnl_eur": 8.0,
        "total_return_pct": 0.8,
        "profit_factor": 1.35,
        "max_drawdown_pct": 3.0,
        "contract_signal_boundary_enforced": True,
        "report_path": "reports/test.md",
    }
    defaults.update(overrides)
    return MatrixCellResult(**defaults)


def test_negative_net_pnl_rejects_and_never_allows_live():
    result = score_strategy(
        _evidence(
            net_pnl_eur=-3.0,
            total_return_pct=-0.3,
            profit_factor=0.8,
            expectancy_eur=-0.05,
            max_drawdown_pct=8.0,
        )
    )

    assert result.score < 50
    assert result.decision == "reject"
    assert result.recommended_status == "rejected"
    assert result.live_promotion_allowed is False
    assert "non_positive_net_pnl" in result.blockers


def test_missing_baseline_caps_score_below_shadow_even_if_metrics_look_good():
    result = score_strategy(_evidence(baseline_included=False, baseline_delta_pct=None))

    assert result.score <= 49.0
    assert result.tier == "disabled"
    assert result.recommended_status == "rejected"
    assert "missing_baseline_cap_49" in result.caps_applied
    assert "baseline_missing" in result.blockers
    assert result.live_promotion_allowed is False


def test_insufficient_sample_can_only_keep_testing():
    result = score_strategy(_evidence(closed_trades=8, net_pnl_eur=5.0, profit_factor=2.0))

    assert result.score <= 64.0
    assert result.decision == "keep_testing"
    assert "insufficient_closed_trades" in result.blockers
    assert result.live_promotion_allowed is False


def test_strong_paper_evidence_can_reach_review_tier_without_live_permission():
    result = score_strategy(
        _evidence(
            source="official_paper",
            paper_evidence=True,
            closed_trades=180,
            net_pnl_eur=130.0,
            gross_pnl_eur=190.0,
            profit_factor=1.95,
            expectancy_eur=0.72,
            max_drawdown_pct=3.0,
            total_return_pct=13.0,
            baseline_delta_pct=8.5,
            regimes_tested=4,
            positive_regimes=4,
            out_of_sample_included=True,
            passing_folds=5,
            total_folds=5,
        )
    )

    assert result.score >= 85.0
    assert result.tier == "human_live_review_candidate"
    assert result.recommended_status == "paper_validated"
    assert result.decision == "human_review_only"
    assert result.live_promotion_allowed is False


def test_score_matrix_aggregates_by_strategy_and_keeps_baseline_gate_conservative():
    matrix = MatrixRunResult(
        run_id="pytest_matrix",
        mode="backtest",
        cell_count=3,
        success_count=3,
        error_count=0,
        results=(
            _cell("grid", symbol="TRXEUR", net_pnl_eur=5.0, closed_trades=30, profit_factor=1.4),
            _cell("grid", symbol="XLMZEUR", net_pnl_eur=-2.0, closed_trades=30, profit_factor=0.8),
            _cell("trend", symbol="BTCEUR", net_pnl_eur=-7.0, closed_trades=40, profit_factor=0.7),
        ),
    )

    report = score_matrix(matrix)
    by_strategy = {result.strategy_id: result for result in report.results}

    assert set(by_strategy) == {"grid", "trend"}
    assert by_strategy["grid"].evidence.closed_trades == 60
    assert by_strategy["grid"].evidence.net_pnl_eur == pytest.approx(3.0)
    assert by_strategy["grid"].score <= 49.0
    assert "baseline_missing" in by_strategy["grid"].blockers
    assert by_strategy["trend"].decision == "reject"
    assert by_strategy["trend"].live_promotion_allowed is False


def test_scorecard_report_writer_outputs_safety_notes(tmp_path):
    report = score_matrix(
        MatrixRunResult(
            run_id="pytest_matrix",
            mode="backtest",
            cell_count=1,
            success_count=1,
            error_count=0,
            results=(_cell("trend"),),
        ),
        baseline_included=True,
        out_of_sample_included=True,
    )

    written = write_strategy_scorecard_report(report, tmp_path)

    assert written.json_report_path
    assert written.markdown_report_path
    payload = json.loads((tmp_path / "pytest_matrix_strategy_scorecard.json").read_text(encoding="utf-8"))
    assert payload["results"][0]["live_promotion_allowed"] is False
    markdown = (tmp_path / "pytest_matrix_strategy_scorecard.md").read_text(encoding="utf-8")
    assert "No live trading permission is granted" in markdown


def test_matrix_evidence_cannot_become_paper_candidate_even_with_strict_contract():
    matrix = MatrixRunResult(
        run_id="pytest_strict_matrix",
        mode="walk_forward",
        cell_count=1,
        success_count=1,
        error_count=0,
        results=(
            _cell(
                "trend",
                mode="walk_forward",
                decision="walk_forward_passed",
                closed_trades=250,
                net_pnl_eur=120.0,
                total_return_pct=12.0,
                profit_factor=2.0,
                max_drawdown_pct=3.0,
                contract_signal_boundary_enforced=True,
            ),
        ),
    )

    result = score_matrix(matrix, baseline_included=True, out_of_sample_included=True).results[0]

    assert result.score <= 74.0
    assert result.tier == "shadow_only"
    assert result.decision == "keep_testing"
    assert "research_matrix_not_paper_evidence_cap_74" in result.caps_applied


def test_matrix_evidence_without_alpha_contract_is_capped_below_shadow():
    matrix = MatrixRunResult(
        run_id="pytest_legacy_matrix",
        mode="walk_forward",
        cell_count=1,
        success_count=1,
        error_count=0,
        results=(
            _cell(
                "trend",
                mode="walk_forward",
                decision="research_only",
                contract_signal_boundary_enforced=False,
            ),
        ),
    )

    result = score_matrix(matrix, baseline_included=True, out_of_sample_included=True).results[0]

    assert result.score <= 64.0
    assert "alpha_contract_boundary_missing" in result.blockers
    assert "alpha_contract_boundary_missing_cap_64" in result.caps_applied
