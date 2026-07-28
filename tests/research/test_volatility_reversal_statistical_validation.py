from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from autobot.v2.research.generic_cross_sectional_ohlcv_adapter import CrossSectionalTrade
from autobot.v2.research.volatility_reversal_statistical_validation import (
    VolatilityReversalStatisticalValidationConfig,
    build_volatility_reversal_statistical_validation_report,
    volatility_reversal_trade_records,
)


pytestmark = pytest.mark.unit


def test_reversal_statistical_gate_does_not_depend_on_runtime_or_order_paths() -> None:
    source = Path(
        "src/autobot/v2/research/volatility_reversal_statistical_validation.py"
    ).read_text(encoding="utf-8")

    for forbidden_import in (
        "order_router",
        "paper_trading",
        "orchestrator_async",
        "signal_handler_async",
        "kraken_client",
    ):
        assert forbidden_import not in source


def test_reversal_statistical_validation_is_deterministic_and_never_promotes() -> None:
    config = VolatilityReversalStatisticalValidationConfig(
        run_id="pytest_reversal_statistics",
        assumed_trial_count=18,
        trial_scope_id="family_mean_reversion_volatility_reversal",
        min_trade_count=50,
        bootstrap_iterations=100,
        seed=7,
    )

    first = build_volatility_reversal_statistical_validation_report(_trades(), config, walk_forward_passed=True)
    second = build_volatility_reversal_statistical_validation_report(_trades(), config, walk_forward_passed=True)

    assert first.decision == second.decision
    assert first.reasons == second.reasons
    assert first.deflated_sharpe == second.deflated_sharpe
    assert first.probabilistic_sharpe == second.probabilistic_sharpe
    assert first.robustness["monte_carlo"] == second.robustness["monte_carlo"]
    assert first.statistical_gate == second.statistical_gate
    assert first.trade_count == 60
    assert first.assumed_trial_count == 18
    assert first.trial_scope_id == "family_mean_reversion_volatility_reversal"
    assert first.statistical_gate["research_only"] is True
    assert first.statistical_gate["paper_capital_allowed"] is False
    assert first.statistical_gate["live_allowed"] is False
    assert first.paper_capital_allowed is False
    assert first.live_allowed is False
    assert first.promotable is False


def test_reversal_statistical_validation_requires_walk_forward_first() -> None:
    report = build_volatility_reversal_statistical_validation_report(
        _trades(),
        VolatilityReversalStatisticalValidationConfig(
            run_id="pytest_reversal_statistics_blocked",
            assumed_trial_count=1,
        ),
        walk_forward_passed=False,
    )

    assert report.decision == "INSUFFICIENT_DATA"
    assert report.reasons == ("walk_forward_gate_not_passed",)
    assert report.trade_count == 0
    assert report.statistical_gate == {}
    assert report.paper_capital_allowed is False


def test_reversal_trade_records_preserve_explicit_prices_and_cost_attribution() -> None:
    trade = _trades(1)[0]
    record = volatility_reversal_trade_records((trade,), run_id="pytest_reversal_records")[0]

    assert record.symbol == "BTCZEUR"
    assert record.entry_price == trade.metadata["entry_price"]
    assert record.exit_price == trade.metadata["exit_price"]
    assert record.net_pnl_eur == trade.net_pnl_eur
    assert record.fees_eur + record.spread_cost_eur + record.slippage_eur + record.latency_cost_eur == pytest.approx(
        trade.gross_pnl_eur - trade.net_pnl_eur
    )
    assert record.metadata["source"] == "volatility_reversal_walk_forward_oos"
    assert record.metadata["research_only"] is True


def test_reversal_statistical_validation_rejects_ambiguous_cost_evidence() -> None:
    trade = _trades(1)[0]
    malformed = replace(trade, metadata={key: value for key, value in trade.metadata.items() if key != "cost_components_eur"})

    report = build_volatility_reversal_statistical_validation_report(
        (malformed,),
        VolatilityReversalStatisticalValidationConfig(
            run_id="pytest_reversal_invalid_costs",
            assumed_trial_count=1,
        ),
        walk_forward_passed=True,
    )

    assert report.decision == "REJECTED"
    assert report.reasons == ("oos_trade_evidence_invalid:cost_components_eur_missing",)
    assert report.trade_count == 0
    assert report.paper_capital_allowed is False


def _trades(count: int = 60) -> tuple[CrossSectionalTrade, ...]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows: list[CrossSectionalTrade] = []
    for index in range(count):
        gross_pnl = -0.4 if index % 5 == 0 else 2.0
        explicit_cost = 0.5
        entry_price = 100.0
        exit_price = entry_price * (1.0 + gross_pnl / 100.0)
        opened_at = start + timedelta(hours=index * 6 + 1)
        rows.append(
            CrossSectionalTrade(
                symbol="BTCZEUR",
                opened_at=opened_at,
                closed_at=opened_at + timedelta(hours=4),
                signal_at=start + timedelta(hours=index * 6),
                mode="volatility_reversal_after_extension",
                variant_label="z-2__target0.5__hold24h",
                timeframe="1h",
                gross_bps=gross_pnl * 100.0,
                cost_bps=50.0,
                net_bps=(gross_pnl - explicit_cost) * 100.0,
                gross_pnl_eur=gross_pnl,
                net_pnl_eur=gross_pnl - explicit_cost,
                expected_move_bps=250.0,
                estimated_total_cost_bps=50.0,
                metadata={
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "order_notional_eur": 100.0,
                    "cost_components_bps": {
                        "fees_bps": 20.0,
                        "spread_cost_bps": 10.0,
                        "slippage_bps": 10.0,
                        "latency_cost_bps": 10.0,
                    },
                    "cost_components_eur": {
                        "fees_eur": 0.20,
                        "spread_cost_eur": 0.10,
                        "slippage_eur": 0.10,
                        "latency_cost_eur": 0.10,
                    },
                    "regime": "range_like",
                    "exit_reason": "mean_target",
                    "anti_lookahead": "prior_window_excludes_signal_bar",
                },
            )
        )
    return tuple(rows)
