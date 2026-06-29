import json
from pathlib import Path

import pytest

from autobot.v2.research.strategy_edge_improvement import (
    StrategyEdgeReviewConfig,
    build_strategy_edge_improvement_report,
    write_strategy_edge_improvement_report,
)


pytestmark = pytest.mark.unit


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _orchestrator_report() -> dict:
    primary = {
        "cost_profile": "research_stress",
        "policy": "conservative",
        "total_net_pnl_eur": 7.12,
        "profit_factor": 1.09,
        "total_trade_count": 45,
        "winrate_pct": 37.78,
        "worst_fold_drawdown_pct": 4.01,
        "positive_fold_count": 2,
        "fold_count": 8,
        "largest_positive_symbol_share": 0.67,
        "contributors": [
            {"symbol": "BCHEUR", "net_pnl_eur": 30.0, "trade_count": 5},
            {"symbol": "SOLEUR", "net_pnl_eur": 5.0, "trade_count": 5},
            {"symbol": "XLMZEUR", "net_pnl_eur": -17.0, "trade_count": 7},
            {"symbol": "AVAXEUR", "net_pnl_eur": -12.0, "trade_count": 7},
        ],
    }
    return {
        "run_id": "pytest_orchestrator",
        "high_conviction_walk_forward": {"run_id": "pytest_hc", "primary_aggregate": primary},
        "strategy_scores": [
            {
                "strategy_name": "high_conviction_swing",
                "status": "active_research",
                "evidence": {
                    "trade_count": 45,
                    "profit_factor": 1.09,
                    "net_pnl_eur": 7.12,
                    "winrate_pct": 37.78,
                    "max_drawdown_pct": 4.01,
                    "positive_folds": 2,
                    "total_folds": 8,
                },
            },
            {
                "strategy_name": "trend_momentum",
                "status": "research_signal_only",
                "evidence": {"trade_count": 221, "profit_factor": 0.27, "net_pnl_eur": -53.0},
            },
            {
                "strategy_name": "mean_reversion",
                "status": "research_signal_only",
                "evidence": {"trade_count": 116, "profit_factor": 1.03, "net_pnl_eur": 0.22},
            },
            {"strategy_name": "relative_value", "status": "no_go", "evidence": {"trade_count": 0}},
            {"strategy_name": "grid", "status": "archived", "evidence": {"trade_count": 0}},
        ],
        "pair_scores": [
            {"symbol": "BCHEUR", "closed_trade_count": 5, "net_pnl_eur": 30.0, "profit_factor": 10.0},
            {"symbol": "SOLEUR", "closed_trade_count": 5, "net_pnl_eur": 5.0, "profit_factor": 2.0},
            {"symbol": "XLMZEUR", "closed_trade_count": 7, "net_pnl_eur": -17.0, "profit_factor": 0.02},
            {"symbol": "AVAXEUR", "closed_trade_count": 7, "net_pnl_eur": -12.0, "profit_factor": 0.25},
        ],
    }


def _high_conviction_report() -> dict:
    return {
        "run_id": "pytest_hc",
        "primary_aggregate": {
            "cost_profile": "research_stress",
            "total_net_pnl_eur": 7.12,
            "profit_factor": 1.09,
            "total_trade_count": 45,
            "positive_fold_count": 2,
            "fold_count": 8,
            "largest_positive_symbol_share": 0.67,
            "contributors": [
                {"symbol": "BCHEUR", "net_pnl_eur": 30.0, "trade_count": 5},
                {"symbol": "SOLEUR", "net_pnl_eur": 5.0, "trade_count": 5},
                {"symbol": "XLMZEUR", "net_pnl_eur": -17.0, "trade_count": 7},
                {"symbol": "AVAXEUR", "net_pnl_eur": -12.0, "trade_count": 7},
            ],
        },
        "aggregates": [
            {"cost_profile": "paper_current_taker", "total_net_pnl_eur": 9.0, "profit_factor": 1.12},
            {"cost_profile": "research_stress", "total_net_pnl_eur": 7.12, "profit_factor": 1.09},
        ],
    }


def test_strategy_edge_review_classifies_current_strategies_and_blocks_promotion(tmp_path):
    orchestrator_path = _write_json(tmp_path / "orchestrator.json", _orchestrator_report())
    high_conviction_path = _write_json(tmp_path / "hc.json", _high_conviction_report())

    report = build_strategy_edge_improvement_report(
        StrategyEdgeReviewConfig(
            run_id="pytest_edge",
            output_dir=tmp_path,
            report_date="2026-06-29",
            strategy_orchestrator_report_path=orchestrator_path,
            high_conviction_report_path=high_conviction_path,
        )
    )

    triage = {item.strategy_name: item for item in report.strategy_triage}
    assert triage["high_conviction_swing"].requested_status == "active_research_keep_testing"
    assert triage["high_conviction_swing"].capital_status == "capital_research_limited"
    assert "insufficient_trade_count_for_candidate_review" in triage["high_conviction_swing"].blockers
    assert triage["trend_momentum"].capital_status == "no_capital_redesign_required"
    assert "redesign_required_before_capital" in triage["trend_momentum"].blockers
    assert triage["mean_reversion"].capital_status == "no_capital_cost_aware_review_required"
    assert triage["relative_value"].requested_status == "no_go"
    assert triage["grid"].requested_status == "archived"
    assert report.safety["live_promotion_allowed"] is False
    assert report.safety["official_paper_modified"] is False


def test_pair_attribution_flags_concentration_and_research_quarantine(tmp_path):
    orchestrator_path = _write_json(tmp_path / "orchestrator.json", _orchestrator_report())
    high_conviction_path = _write_json(tmp_path / "hc.json", _high_conviction_report())
    report = build_strategy_edge_improvement_report(
        StrategyEdgeReviewConfig(
            run_id="pytest_edge",
            report_date="2026-06-29",
            strategy_orchestrator_report_path=orchestrator_path,
            high_conviction_report_path=high_conviction_path,
        )
    )

    by_symbol = {item.symbol: item for item in report.pair_attribution}
    assert by_symbol["BCHEUR"].action == "concentration_watch_research_only"
    assert by_symbol["XLMZEUR"].action == "research_quarantine_candidate"
    assert by_symbol["AVAXEUR"].action == "research_quarantine_candidate"
    without_bch = next(item for item in report.leave_one_symbol_out if item.symbol_removed == "BCHEUR")
    assert without_bch.interpretation == "depends_on_positive_pair"
    without_xlm = next(item for item in report.leave_one_symbol_out if item.symbol_removed == "XLMZEUR")
    assert without_xlm.interpretation == "pair_damages_portfolio"


def test_write_strategy_edge_reports_creates_review_improvement_and_json(tmp_path):
    orchestrator_path = _write_json(tmp_path / "orchestrator.json", _orchestrator_report())
    high_conviction_path = _write_json(tmp_path / "hc.json", _high_conviction_report())
    report = build_strategy_edge_improvement_report(
        StrategyEdgeReviewConfig(
            run_id="pytest_edge",
            output_dir=tmp_path,
            report_date="2026-06-29",
            strategy_orchestrator_report_path=orchestrator_path,
            high_conviction_report_path=high_conviction_path,
        )
    )

    written = write_strategy_edge_improvement_report(report, tmp_path / "reports")

    assert Path(written.review_markdown_path).exists()
    assert Path(written.improvement_markdown_path).exists()
    assert Path(written.json_report_path).exists()
    payload = json.loads(Path(written.json_report_path).read_text(encoding="utf-8"))
    assert payload["safety"]["research_only"] is True
    assert "Trend Momentum redesign plan" in Path(written.improvement_markdown_path).read_text(encoding="utf-8")
