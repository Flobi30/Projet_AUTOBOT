from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from autobot.v2.contracts import FeatureSnapshotReference, FeatureValue, MarketIdentity, VerifiedFeatureVector
from autobot.v2.research.strategy_orchestrator import StrategyResearchSignal
from autobot.v2.research.strategy_research_alpha_adapter import (
    StrategyResearchAlphaAdapterError,
    StrategyResearchAlphaProvenance,
    adapt_strategy_research_signal_to_alpha,
)


pytestmark = pytest.mark.unit


def _at() -> datetime:
    return datetime(2026, 7, 18, 12, tzinfo=timezone.utc)


def _vector() -> VerifiedFeatureVector:
    market = MarketIdentity("kraken", "spot", "BTCEUR", "BTC", "EUR")
    feature_snapshot = FeatureSnapshotReference(
        feature_snapshot_id="feature-snapshot-fixture",
        fingerprint="feature-snapshot-fingerprint",
        snapshot_kind="CANONICAL_FEATURE_SNAPSHOT",
        source_snapshot_id="ohlcv-snapshot-fixture",
        source_snapshot_fingerprint="ohlcv-fingerprint-fixture",
        feature_registry_fingerprint="feature-registry-fingerprint",
        feature_versions={"momentum_3_bps": "1.0.0"},
        runtime_parity_proven=True,
        material_verified=True,
        bundle_content_fingerprint="bundle-content-fingerprint",
    )
    return VerifiedFeatureVector(
        feature_snapshot=feature_snapshot,
        market=market,
        timeframe="15m",
        observed_at=_at(),
        values=(
            FeatureValue(
                feature_id="momentum_3_bps",
                feature_version="1.0.0",
                market=market,
                timeframe="15m",
                event_time=_at() - timedelta(minutes=15),
                available_time=_at(),
                source_snapshot_id="ohlcv-snapshot-fixture",
                value=24.0,
            ),
        ),
    )


def _signal(*, direction: str = "buy", metadata: dict[str, object] | None = None, symbol: str = "BTCEUR") -> StrategyResearchSignal:
    return StrategyResearchSignal(
        strategy_name="trend_momentum",
        symbol=symbol,
        timestamp=_at() - timedelta(minutes=1),
        direction=direction,
        confidence=0.8,
        expected_move_bps=30.0,
        cost_profile="research_stress",
        regime="trend",
        reason="pytest",
        metadata=metadata or {},
        research_only=True,
        instance_id="pytest-instance",
    )


def _provenance() -> StrategyResearchAlphaProvenance:
    return StrategyResearchAlphaProvenance(
        strategy_id="trend_momentum",
        strategy_version="v1",
        feature_vector=_vector(),
        cost_model_fingerprint="cost-fingerprint",
    )


def test_long_alpha_requires_verified_vector_and_net_edge_bound_to_cost_model():
    adaptation = adapt_strategy_research_signal_to_alpha(
        _signal(metadata={"net_expected_edge_bps": 15.0, "cost_model_fingerprint": "cost-fingerprint"}),
        provenance=_provenance(),
    )

    alpha = adaptation.alpha_signal
    assert alpha.direction == "long"
    assert alpha.expected_edge_bps == pytest.approx(15.0)
    assert alpha.market == _vector().market
    assert alpha.available_at == _at()
    assert alpha.metadata["feature_vector_fingerprint"] == _vector().fingerprint
    assert alpha.metadata["paper_capital_allowed"] is False
    assert adaptation.live_allowed is False


def test_long_alpha_rejects_missing_or_mismatched_net_cost_evidence():
    with pytest.raises(StrategyResearchAlphaAdapterError, match="net_expected_edge_bps_missing"):
        adapt_strategy_research_signal_to_alpha(_signal(), provenance=_provenance())
    with pytest.raises(StrategyResearchAlphaAdapterError, match="net_expected_edge_cost_model_mismatch"):
        adapt_strategy_research_signal_to_alpha(
            _signal(metadata={"net_expected_edge_bps": 15.0, "cost_model_fingerprint": "other"}),
            provenance=_provenance(),
        )


def test_sell_becomes_flat_and_never_a_short_signal():
    adaptation = adapt_strategy_research_signal_to_alpha(_signal(direction="sell"), provenance=_provenance())

    assert adaptation.alpha_signal.direction == "flat"
    assert adaptation.alpha_signal.expected_edge_bps is None


def test_adapter_rejects_mismatched_market_or_future_signal_timestamp():
    with pytest.raises(StrategyResearchAlphaAdapterError, match="does not match verified feature vector market"):
        adapt_strategy_research_signal_to_alpha(
            _signal(symbol="ETHZEUR", metadata={"net_expected_edge_bps": 15.0, "cost_model_fingerprint": "cost-fingerprint"}),
            provenance=_provenance(),
        )
    signal = _signal(metadata={"net_expected_edge_bps": 15.0, "cost_model_fingerprint": "cost-fingerprint"})
    future = StrategyResearchSignal(
        **{**signal.__dict__, "timestamp": _at() + timedelta(seconds=1)}
    )
    with pytest.raises(StrategyResearchAlphaAdapterError, match="cannot follow"):
        adapt_strategy_research_signal_to_alpha(future, provenance=_provenance())


def test_adapter_module_has_no_runtime_paper_or_router_imports():
    root = Path(__file__).resolve().parents[2]
    module = root / "src" / "autobot" / "v2" / "research" / "strategy_research_alpha_adapter.py"
    tree = ast.parse(module.read_text(encoding="utf-8"))
    imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imports.update(node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module)

    forbidden = {
        "autobot.v2.order_router",
        "autobot.v2.signal_handler_async",
        "autobot.v2.paper_trading",
        "autobot.v2.orchestrator_async",
    }
    assert imports.isdisjoint(forbidden)
