from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path

import pytest

from autobot.v2.research.metrics_engine import MetricsResult
from autobot.v2.research.robustness_experiments import (
    CostStressScenario,
    MonteCarloSummary,
    RobustnessExperimentReport,
    StressScenarioResult,
)
from autobot.v2.research.statistical_gate_summary import (
    StatisticalGateConfig,
    StatisticalGateEvidence,
    summarize_statistical_gate,
)
from autobot.v2.research.statistical_validation import (
    DeflatedSharpeResult,
    ProbabilisticSharpeResult,
)


pytestmark = pytest.mark.unit


def test_acceptable_evidence_is_shadow_review_only_and_never_promotable():
    summary = summarize_statistical_gate(_evidence())

    assert summary.decision == "SHADOW_REVIEW_ELIGIBLE"
    assert summary.blockers == ()
    assert summary.shadow_review_eligible is True
    assert summary.research_only is True
    assert summary.paper_capital_allowed is False
    assert summary.live_allowed is False
    assert summary.promotable is False
    assert "probabilistic_sharpe_per_trade_proxy" in summary.method_notes
    assert "deflated_sharpe_proxy" in summary.method_notes


def test_insufficient_sample_fails_closed():
    summary = summarize_statistical_gate(_evidence(trade_count=12))

    assert summary.decision == "RESEARCH_BLOCKED"
    assert "trade_count_below_50" in summary.blockers


def test_excessive_trial_count_fails_closed_even_with_acceptable_proxies():
    summary = summarize_statistical_gate(
        _evidence(trial_count=17),
        StatisticalGateConfig(max_trial_count=16),
    )

    assert summary.decision == "RESEARCH_BLOCKED"
    assert "trial_count_exceeds_maximum_16" in summary.blockers


def test_deflated_trial_count_must_match_explicit_trial_count():
    evidence = _evidence()
    mismatched = DeflatedSharpeResult(
        **{**evidence.deflated_sharpe.__dict__, "assumed_trial_count": 7}
    )
    summary = summarize_statistical_gate(
        StatisticalGateEvidence(
            **{**evidence.__dict__, "deflated_sharpe": mismatched}
        )
    )

    assert summary.decision == "RESEARCH_BLOCKED"
    assert "deflated_sharpe_trial_count_mismatch" in summary.blockers


def test_missing_out_of_sample_confirmation_fails_closed():
    summary = summarize_statistical_gate(_evidence(out_of_sample_confirmed=False))

    assert summary.decision == "RESEARCH_BLOCKED"
    assert "out_of_sample_not_confirmed" in summary.blockers


def test_negative_net_result_fails_closed():
    summary = summarize_statistical_gate(_evidence(net_pnl_eur=-0.01))

    assert summary.decision == "RESEARCH_BLOCKED"
    assert "net_pnl_not_positive_after_costs" in summary.blockers


def test_missing_or_invalid_evidence_fails_closed():
    summary = summarize_statistical_gate(
        StatisticalGateEvidence(
            trade_count=0,
            trial_count=None,
            net_pnl_eur=float("nan"),
            out_of_sample_confirmed=None,
            net_of_costs=False,
            probabilistic_sharpe=None,
            deflated_sharpe=None,
            robustness=None,
        )
    )

    assert summary.decision == "RESEARCH_BLOCKED"
    assert {
        "trade_count_missing_or_invalid",
        "trial_count_missing_or_invalid",
        "net_pnl_missing_or_invalid",
        "out_of_sample_not_confirmed",
        "net_of_costs_not_confirmed",
        "probabilistic_sharpe_missing",
        "deflated_sharpe_missing",
        "robustness_evidence_missing",
    }.issubset(summary.blockers)


def test_module_has_no_execution_dependencies():
    root = Path(__file__).resolve().parents[2]
    module = root / "src/autobot/v2/research/statistical_gate_summary.py"
    tree = ast.parse(module.read_text(encoding="utf-8"))
    imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imports.update(node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module)

    forbidden = {
        "autobot.v2.order_router",
        "autobot.v2.signal_handler_async",
        "autobot.v2.paper_trading",
        "autobot.v2.orchestrator_async",
        "autobot.v2.kraken_client",
    }
    assert imports.isdisjoint(forbidden)


def _evidence(
    *,
    trade_count: int = 60,
    trial_count: int = 8,
    net_pnl_eur: float = 12.0,
    out_of_sample_confirmed: bool = True,
) -> StatisticalGateEvidence:
    return StatisticalGateEvidence(
        trade_count=trade_count,
        trial_count=trial_count,
        net_pnl_eur=net_pnl_eur,
        out_of_sample_confirmed=out_of_sample_confirmed,
        net_of_costs=True,
        probabilistic_sharpe=ProbabilisticSharpeResult(
            sample_count=trade_count,
            sharpe_like=0.4,
            benchmark_sharpe=0.0,
            probability=0.8,
            standard_error=0.1,
            skewness=0.0,
            kurtosis=3.0,
            status="acceptable_proxy",
            acceptable=True,
        ),
        deflated_sharpe=DeflatedSharpeResult(
            sample_count=trade_count,
            sharpe_like=2.1,
            expected_max_sharpe=1.0,
            deflated_sharpe_probability=0.8,
            skewness=0.0,
            kurtosis=3.0,
            assumed_trial_count=trial_count,
            status="acceptable_proxy",
            overfitting_risk_score=20.0,
            acceptable=True,
        ),
        robustness=_robustness(trade_count),
    )


def _robustness(trade_count: int) -> RobustnessExperimentReport:
    metrics = MetricsResult(
        initial_capital_eur=500.0,
        final_equity_eur=512.0,
        total_return_pct=2.4,
        trade_count=trade_count,
        closed_trade_count=trade_count,
        total_gross_pnl_eur=20.0,
        total_net_pnl_eur=12.0,
        total_fees_eur=4.0,
        total_spread_cost_eur=2.0,
        total_slippage_eur=1.0,
        total_latency_cost_eur=1.0,
        winrate_pct=60.0,
        profit_factor=1.3,
        expectancy_eur=0.2,
        average_win_eur=1.0,
        average_loss_eur=-0.8,
        max_drawdown_eur=5.0,
        max_drawdown_pct=1.0,
        average_trade_duration_seconds=3600.0,
        sharpe_like=0.4,
        sortino_like=0.5,
    )
    return RobustnessExperimentReport(
        run_id="pytest_statistical_gate",
        generated_at=datetime(2026, 7, 18, tzinfo=timezone.utc).isoformat(),
        trade_count=trade_count,
        initial_capital_eur=500.0,
        monte_carlo=MonteCarloSummary(
            sample_count=trade_count,
            iterations=100,
            seed=7,
            confidence_level=0.95,
            probability_positive_net_pnl=0.7,
            net_pnl_p05_eur=2.0,
            net_pnl_p50_eur=12.0,
            net_pnl_p95_eur=20.0,
            profit_factor_p05=1.1,
            profit_factor_p50=1.3,
            max_drawdown_p50_pct=2.0,
            max_drawdown_p95_pct=4.0,
            mean_trade_return_lower=0.001,
            mean_trade_return_p50=0.002,
            mean_trade_return_upper=0.003,
            status="ok",
        ),
        stress_scenarios=(
            StressScenarioResult(scenario=CostStressScenario(name="base"), metrics=metrics),
        ),
        verdict="observation_ready_not_promoted",
        reasons=("pytest",),
    )
