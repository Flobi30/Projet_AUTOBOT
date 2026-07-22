from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from autobot.v2.research.funding_basis_research_adapter import (
    FundingBasisTrade,
    funding_basis_trade_records,
)
from autobot.v2.research.funding_basis_statistical_validation import (
    FundingBasisStatisticalValidationConfig,
    build_funding_basis_statistical_validation_report,
)


pytestmark = pytest.mark.unit


def test_funding_basis_statistical_validation_is_deterministic_and_never_promotes():
    config = FundingBasisStatisticalValidationConfig(
        run_id="pytest_funding_statistics",
        assumed_trial_count=12,
        trial_scope_id="family_funding_basis",
        min_trade_count=50,
        bootstrap_iterations=100,
        seed=7,
    )
    first = build_funding_basis_statistical_validation_report(_trades(), config, walk_forward_passed=True)
    second = build_funding_basis_statistical_validation_report(_trades(), config, walk_forward_passed=True)

    assert first.decision == second.decision
    assert first.reasons == second.reasons
    assert first.deflated_sharpe == second.deflated_sharpe
    assert first.probabilistic_sharpe == second.probabilistic_sharpe
    assert first.robustness["monte_carlo"] == second.robustness["monte_carlo"]
    assert first.robustness["stress_scenarios"] == second.robustness["stress_scenarios"]
    assert first.statistical_gate == second.statistical_gate
    assert first.trade_count == 60
    assert first.assumed_trial_count == 12
    assert first.trial_scope_id == "family_funding_basis"
    assert first.deflated_sharpe["research_only"] is True
    assert first.probabilistic_sharpe["paper_candidate_allowed"] is False
    assert first.robustness["live_promotion_allowed"] is False
    assert first.statistical_gate["research_only"] is True
    assert first.statistical_gate["paper_capital_allowed"] is False
    assert first.statistical_gate["live_allowed"] is False
    assert first.statistical_gate["promotable"] is False
    assert first.paper_capital_allowed is False
    assert first.live_allowed is False
    assert first.promotable is False


def test_funding_basis_statistical_validation_requires_walk_forward_first():
    report = build_funding_basis_statistical_validation_report(
        _trades(),
        FundingBasisStatisticalValidationConfig(run_id="pytest_funding_statistics_blocked", assumed_trial_count=1),
        walk_forward_passed=False,
    )

    assert report.decision == "INSUFFICIENT_DATA"
    assert report.reasons == ("walk_forward_gate_not_passed",)
    assert report.trade_count == 0
    assert report.trial_scope_id == "hypothesis_funding_basis"
    assert report.deflated_sharpe == {}
    assert report.statistical_gate == {}
    assert report.paper_capital_allowed is False


def test_funding_basis_trade_records_preserve_spot_prices_and_cost_attribution():
    trade = _trades(1)[0]
    record = funding_basis_trade_records((trade,), run_id="pytest_records")[0]

    assert record.symbol == "BTCZEUR"
    assert record.entry_price == trade.entry_price
    assert record.exit_price == trade.exit_price
    assert record.net_pnl_eur == trade.net_pnl_eur
    assert record.fees_eur + record.spread_cost_eur + record.slippage_eur + record.latency_cost_eur == pytest.approx(
        trade.gross_pnl_eur - trade.net_pnl_eur
    )
    assert record.metadata["spot_only_pnl"] is True
    assert record.metadata["futures_symbol"] == "PF_XBTUSD"
    assert record.metadata["funding_carry_eur"] == 0.0
    assert record.metadata["funding_carry_attribution"] == {
        "applicable": False,
        "funding_carry_eur": 0.0,
        "reason": "spot_only_directional_context_no_perpetual_position",
        "funding_rate_used_as_feature_only": True,
    }


def _trades(count: int = 60) -> tuple[FundingBasisTrade, ...]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    for index in range(count):
        gross_pnl = -0.4 if index % 5 == 0 else 2.0
        cost = 0.5
        entry = 100.0
        exit_price = entry * (1.0 + gross_pnl / 100.0)
        rows.append(
            FundingBasisTrade(
                spot_symbol="BTCZEUR",
                futures_symbol="PF_XBTUSD",
                signal_at=start + timedelta(hours=index * 6),
                opened_at=start + timedelta(hours=index * 6 + 1),
                closed_at=start + timedelta(hours=index * 6 + 5),
                timeframe="1h",
                variant_label="funding_p10_hold4h",
                funding_rate_relative=-0.004,
                funding_percentile_threshold=-0.002,
                basis_bps=-8.0,
                entry_price=entry,
                exit_price=exit_price,
                gross_bps=gross_pnl * 100.0,
                cost_bps=50.0,
                net_bps=(gross_pnl - cost) * 100.0,
                order_notional_eur=100.0,
                gross_pnl_eur=gross_pnl,
                net_pnl_eur=gross_pnl - cost,
                fees_eur=0.20,
                spread_cost_eur=0.10,
                slippage_eur=0.10,
                latency_cost_eur=0.10,
                metadata={"implicit_usd_eur_price_conversion": False},
            )
        )
    return tuple(rows)
