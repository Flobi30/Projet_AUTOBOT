from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path

import pytest

from autobot.v2.contracts import MarketIdentity
from autobot.v2.research.backtest_alpha_adapter import (
    BacktestAlphaAdapterError,
    BacktestSignalProvenance,
    adapt_backtest_signal_to_alpha,
)
from autobot.v2.research.backtest_engine import BacktestSignal


pytestmark = pytest.mark.unit


def _at() -> datetime:
    return datetime(2026, 7, 16, 12, tzinfo=timezone.utc)


def _provenance() -> BacktestSignalProvenance:
    return BacktestSignalProvenance(
        strategy_id="trend_momentum",
        strategy_version="v2",
        data_snapshot_id="canonical-ohlcv-v2",
        feature_versions={"momentum_20": "1.0.0", "atr_14": "1.0.0"},
        markets={
            "BTCEUR": MarketIdentity("kraken", "spot", "BTCEUR", "BTC", "EUR"),
        },
    )


def test_buy_signal_becomes_explicit_long_alpha_without_changing_its_decision_time():
    adaptation = adapt_backtest_signal_to_alpha(
        BacktestSignal(
            symbol="BTCEUR",
            side="buy",
            price=100.0,
            timestamp=_at(),
            reason="momentum_entry",
            metadata={"expected_edge_bps": 24.0, "gross_edge_bps": 80.0},
        ),
        provenance=_provenance(),
    )

    signal = adaptation.alpha_signal
    assert adaptation.portfolio_action == "ENTER_LONG"
    assert signal.direction == "long"
    assert signal.market == MarketIdentity("kraken", "spot", "BTCEUR", "BTC", "EUR")
    assert signal.generated_at == _at()
    assert signal.available_at == _at()
    assert signal.expected_edge_bps == pytest.approx(24.0)
    assert signal.metadata["decision_price"] == pytest.approx(100.0)
    assert adaptation.paper_capital_allowed is False
    assert adaptation.live_allowed is False


def test_buy_requires_explicit_net_expected_edge_and_does_not_promote_gross_edge_metadata():
    signal = BacktestSignal(
        symbol="BTCEUR",
        side="buy",
        price=100.0,
        timestamp=_at(),
        reason="legacy_entry",
        metadata={"gross_edge_bps": 80.0},
    )

    with pytest.raises(BacktestAlphaAdapterError, match="expected_edge_bps_missing"):
        adapt_backtest_signal_to_alpha(signal, provenance=_provenance())


def test_sell_signal_is_reduce_to_cash_not_a_short_alpha():
    adaptation = adapt_backtest_signal_to_alpha(
        BacktestSignal(
            symbol="BTCEUR",
            side="sell",
            price=101.0,
            timestamp=_at(),
            reason="exit",
        ),
        provenance=_provenance(),
    )

    assert adaptation.portfolio_action == "REDUCE_TO_CASH"
    assert adaptation.alpha_signal.direction == "flat"
    assert adaptation.alpha_signal.expected_edge_bps is None


def test_adapter_rejects_implicit_symbol_quote_or_market_mapping():
    signal = BacktestSignal(
        symbol="BTCUSD",
        side="buy",
        price=100.0,
        timestamp=_at(),
        reason="wrong_quote",
        metadata={"expected_edge_bps": 20.0},
    )

    with pytest.raises(BacktestAlphaAdapterError, match="explicit_market_mapping_missing:BTCUSD"):
        adapt_backtest_signal_to_alpha(signal, provenance=_provenance())


def test_adapter_module_remains_research_only_and_does_not_import_runtime_execution_paths():
    root = Path(__file__).resolve().parents[2]
    tree = ast.parse((root / "src/autobot/v2/research/backtest_alpha_adapter.py").read_text(encoding="utf-8"))
    forbidden = {"autobot.v2.order_router", "autobot.v2.signal_handler_async", "autobot.v2.paper_trading"}
    imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imports.update(node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module)

    assert imports.isdisjoint(forbidden)
