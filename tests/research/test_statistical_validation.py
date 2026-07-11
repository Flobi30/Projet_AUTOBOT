from datetime import datetime, timedelta, timezone

import pytest

from autobot.v2.research.statistical_validation import (
    DeflatedSharpeConfig,
    ProbabilisticSharpeConfig,
    assess_deflated_sharpe,
    assess_probabilistic_sharpe,
    evaluate_progressive_pf_quality,
)
from autobot.v2.research.trade_journal import TradeRecord


pytestmark = pytest.mark.unit


def _trades(count: int = 90) -> tuple[TradeRecord, ...]:
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    rows = []
    for index in range(count):
        net = 2.0 if index % 4 else -0.6
        opened = start + timedelta(hours=index)
        rows.append(
            TradeRecord(
                run_id="pytest_dsr",
                strategy_id="high_conviction_swing",
                symbol="TRXEUR" if index % 2 else "XLMZEUR",
                side="buy",
                opened_at=opened,
                closed_at=opened + timedelta(hours=2),
                quantity=10.0,
                entry_price=1.0,
                exit_price=1.0 + net / 10.0,
                gross_pnl_eur=net + 0.25,
                net_pnl_eur=net,
                fees_eur=0.10,
                spread_cost_eur=0.05,
                slippage_eur=0.05,
                latency_cost_eur=0.05,
            )
        )
    return tuple(rows)


def test_deflated_sharpe_proxy_is_research_only_and_never_promotes():
    result = assess_deflated_sharpe(
        _trades(),
        DeflatedSharpeConfig(initial_capital_eur=500.0, assumed_trial_count=8, min_trade_count=50),
    )

    assert result.sample_count == 90
    assert result.research_only is True
    assert result.paper_candidate_allowed is False
    assert result.live_promotion_allowed is False
    assert result.status in {"acceptable_proxy", "overfitting_risk_high"}
    assert 0.0 <= result.overfitting_risk_score <= 100.0


def test_deflated_sharpe_requires_enough_closed_trades():
    result = assess_deflated_sharpe(
        _trades(10),
        DeflatedSharpeConfig(initial_capital_eur=500.0, assumed_trial_count=8, min_trade_count=50),
    )

    assert result.status == "insufficient_sample"
    assert result.acceptable is False
    assert result.overfitting_risk_score >= 70.0


def test_probabilistic_sharpe_is_research_only_and_requires_track_record():
    accepted = assess_probabilistic_sharpe(
        _trades(),
        ProbabilisticSharpeConfig(initial_capital_eur=500.0, min_trade_count=50),
    )
    thin = assess_probabilistic_sharpe(
        _trades(10),
        ProbabilisticSharpeConfig(initial_capital_eur=500.0, min_trade_count=50),
    )

    assert accepted.probability is not None
    assert 0.0 <= accepted.probability <= 1.0
    assert accepted.research_only is True
    assert accepted.paper_candidate_allowed is False
    assert thin.status == "insufficient_sample"
    assert thin.acceptable is False


def test_progressive_pf_gate_reaches_candidate_review_without_promotion():
    assessment = evaluate_progressive_pf_quality(
        strategy_name="high_conviction_swing",
        status="active_research",
        metrics={
            "trade_count": 60,
            "signal_count": 80,
            "net_pnl_eur": 25.0,
            "profit_factor": 1.36,
            "max_drawdown_pct": 6.0,
            "positive_folds": 4,
            "total_folds": 5,
            "largest_positive_symbol_share": 0.28,
            "validation_days": 5,
            "costs_covered": True,
            "runtime_comparable": True,
        },
        robustness={
            "monte_carlo": {"probability_positive_net_pnl": 0.62, "status": "observation_ready"},
            "stress_scenarios": (
                {"metrics": {"total_net_pnl_eur": 5.0, "profit_factor": 1.1}},
                {"metrics": {"total_net_pnl_eur": 3.0, "profit_factor": 1.05}},
            ),
        },
        deflated_sharpe={"acceptable": True, "overfitting_risk_score": 30.0},
        available_cash_eur=500.0,
    )

    assert assessment.decision == "candidate_review_possible"
    assert "B_candidate_review_possible" in assessment.gates_passed
    assert assessment.paper_candidate_allowed is False
    assert assessment.live_promotion_allowed is False


def test_progressive_pf_gate_blocks_overfit_or_thin_samples():
    assessment = evaluate_progressive_pf_quality(
        strategy_name="mean_reversion",
        status="active_research",
        metrics={
            "trade_count": 12,
            "net_pnl_eur": 5.0,
            "profit_factor": 1.4,
            "max_drawdown_pct": 4.0,
            "positive_folds": 1,
            "total_folds": 2,
            "largest_positive_symbol_share": 0.75,
            "validation_days": 1,
            "costs_covered": True,
            "runtime_comparable": True,
        },
        deflated_sharpe={"acceptable": False, "overfitting_risk_score": 85.0},
    )

    assert assessment.decision == "observe_research"
    assert "trade_count_below_50" in assessment.blockers
    assert "single_symbol_positive_pnl_above_40_pct" in assessment.blockers


def test_no_go_strategy_is_no_trade_research():
    assessment = evaluate_progressive_pf_quality(
        strategy_name="grid",
        status="no_go",
        metrics={"trade_count": 0, "profit_factor": 0.0},
    )

    assert assessment.decision == "no_trade_research"
    assert assessment.paper_candidate_allowed is False
    assert assessment.live_promotion_allowed is False
