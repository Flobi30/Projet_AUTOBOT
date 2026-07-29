from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path

import pytest

from autobot.v2.contracts import MarketIdentity, TargetPortfolio
from autobot.v2.research.legacy_portfolio_allocation_comparison import (
    LegacyAllocationComparisonError,
    compare_target_portfolio_to_legacy_allocation,
)


pytestmark = pytest.mark.unit


def _target() -> TargetPortfolio:
    market = MarketIdentity("kraken", "spot", "BTCEUR", "BTC", "EUR")
    return TargetPortfolio(
        decision_id="canonical-decision",
        generated_at=datetime(2026, 7, 29, 12, tzinfo=timezone.utc),
        target_weights={"BTCEUR": 0.30, "ETHEUR": 0.20},
        reserve_cash_weight=0.50,
        cash_asset="EUR",
        source_signal_ids=("sig-btc", "sig-eth"),
        source_strategy_ids=("funding_basis",),
        source_data_snapshot_ids=("features-1",),
        source_feature_versions={"basis_bps": "1"},
        source_markets={"BTCEUR": market, "ETHEUR": MarketIdentity("kraken", "spot", "ETHEUR", "ETH", "EUR")},
    )


def test_legacy_allocation_comparison_reports_exact_alignment_without_authorizing_capital():
    result = compare_target_portfolio_to_legacy_allocation(
        _target(),
        reference_capital_eur=1_000.0,
        legacy_symbol_caps={"btceur": 300.0, "ETHEUR": 200.0},
        legacy_reserve_cash_eur=500.0,
    )

    assert result.status == "ALIGNED_FOR_RESEARCH_ONLY"
    assert result.reasons == ()
    assert result.per_symbol_delta_eur == {"BTCEUR": 0.0, "ETHEUR": 0.0}
    assert result.research_only is True
    assert result.paper_capital_allowed is False
    assert result.live_allowed is False


def test_legacy_allocation_comparison_exposes_symbol_and_cash_divergence_without_mutation():
    result = compare_target_portfolio_to_legacy_allocation(
        _target(),
        reference_capital_eur=1_000.0,
        legacy_symbol_caps={"BTCEUR": 250.0, "XRPEUR": 250.0},
        legacy_reserve_cash_eur=450.0,
    )

    assert result.status == "DIVERGENCE_REVIEW_REQUIRED"
    assert result.target_only_symbols == ("ETHEUR",)
    assert result.legacy_only_symbols == ("XRPEUR",)
    assert result.reasons == (
        "canonical_target_symbols_missing_from_legacy",
        "legacy_symbols_absent_from_canonical_target",
        "per_symbol_notional_divergence",
        "reserve_cash_divergence",
    )
    assert result.canonical_notionals_eur == {"BTCEUR": 300.0, "ETHEUR": 200.0}
    assert result.legacy_notionals_eur == {"BTCEUR": 250.0, "XRPEUR": 250.0}


@pytest.mark.parametrize(
    ("legacy_symbol_caps", "legacy_reserve_cash_eur", "error"),
    [
        ({"BTCEUR": -1.0}, 500.0, "non-negative"),
        ({"BTCEUR": 300.0}, -1.0, "non-negative"),
        ({" ": 300.0}, 500.0, "symbol is required"),
    ],
)
def test_legacy_allocation_comparison_rejects_ambiguous_economic_inputs(
    legacy_symbol_caps,
    legacy_reserve_cash_eur,
    error,
):
    with pytest.raises(LegacyAllocationComparisonError, match=error):
        compare_target_portfolio_to_legacy_allocation(
            _target(),
            reference_capital_eur=1_000.0,
            legacy_symbol_caps=legacy_symbol_caps,
            legacy_reserve_cash_eur=legacy_reserve_cash_eur,
        )


def test_comparison_module_isolated_from_runtime_allocator_and_execution_paths():
    root = Path(__file__).resolve().parents[2]
    tree = ast.parse(
        (root / "src/autobot/v2/research/legacy_portfolio_allocation_comparison.py").read_text(encoding="utf-8")
    )
    imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imports.update(node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module)

    assert imports.isdisjoint(
        {
            "autobot.v2.portfolio_allocator",
            "autobot.v2.orchestrator_async",
            "autobot.v2.order_router",
            "autobot.v2.signal_handler_async",
            "autobot.v2.paper_trading",
        }
    )
