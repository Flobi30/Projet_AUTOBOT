from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from autobot.v2.contracts import FeatureSnapshotReference, FeatureValue, MarketIdentity, VerifiedFeatureVector
from autobot.v2.research.derivatives_spot_context import (
    DerivativesSpotResearchContext,
    DerivativesSpotResearchContextError,
    FuturesSpotResearchMapping,
    build_derivatives_spot_research_context,
)


pytestmark = pytest.mark.unit


def _at() -> datetime:
    return datetime(2026, 8, 3, 12, tzinfo=timezone.utc)


def _spot_market() -> MarketIdentity:
    return MarketIdentity("kraken", "spot", "BTCEUR", "BTC", "EUR")


def _derivatives_market() -> MarketIdentity:
    return MarketIdentity("kraken_futures", "perpetual", "PF_XBTUSD", "BTC", "USD")


def _vector(*, market: MarketIdentity, kind: str, snapshot_id: str, feature_id: str) -> VerifiedFeatureVector:
    observed_at = _at()
    snapshot = FeatureSnapshotReference(
        feature_snapshot_id=snapshot_id,
        fingerprint=f"{snapshot_id}-fingerprint",
        snapshot_kind=kind,
        source_snapshot_id=f"{snapshot_id}-source",
        source_snapshot_fingerprint=f"{snapshot_id}-source-fingerprint",
        feature_registry_fingerprint=f"{snapshot_id}-registry-fingerprint",
        feature_versions={feature_id: "1.0.0"},
        runtime_parity_proven=True,
        material_verified=True,
        bundle_content_fingerprint=f"{snapshot_id}-bundle-content-fingerprint",
    )
    return VerifiedFeatureVector(
        feature_snapshot=snapshot,
        market=market,
        timeframe="1h",
        observed_at=observed_at,
        values=(
            FeatureValue(
                feature_id=feature_id,
                feature_version="1.0.0",
                market=market,
                timeframe="1h",
                event_time=observed_at - timedelta(hours=1),
                available_time=observed_at,
                source_snapshot_id=snapshot.source_snapshot_id,
                value=12.5,
            ),
        ),
    )


def _mapping() -> FuturesSpotResearchMapping:
    return FuturesSpotResearchMapping(
        mapping_id="kraken-futures-pf-xbtusd-to-btceur-v1",
        futures_market=_derivatives_market(),
        spot_market=_spot_market(),
        mapping_source="kraken_futures_derivatives_manifest_v2",
        mapping_fingerprint="mapping-fixture-fingerprint",
    )


def _context() -> DerivativesSpotResearchContext:
    return build_derivatives_spot_research_context(
        mapping=_mapping(),
        spot_vector=_vector(
            market=_spot_market(),
            kind="CANONICAL_FEATURE_SNAPSHOT",
            snapshot_id="spot-feature-snapshot",
            feature_id="momentum_3_bps",
        ),
        derivatives_vector=_vector(
            market=_derivatives_market(),
            kind="DERIVATIVES_POINT_IN_TIME",
            snapshot_id="derivatives-feature-snapshot",
            feature_id="funding_rate_relative",
        ),
        observed_at=_at(),
    )


def test_context_binds_same_base_markets_without_implicit_usd_eur_conversion():
    context = _context()

    assert context.mapping.futures_market.symbol == "PF_XBTUSD"
    assert context.mapping.spot_market.symbol == "BTCEUR"
    assert context.mapping.futures_market.quote_asset == "USD"
    assert context.mapping.spot_market.quote_asset == "EUR"
    assert context.to_dict()["price_conversion_allowed"] is False
    assert context.to_dict()["price_relation"] == "DERIVATIVES_DIRECTIONAL_CONTEXT_ONLY"
    assert context.to_dict()["spot_pnl_market"]["symbol"] == "BTCEUR"
    assert context.research_only is True
    assert context.paper_capital_allowed is False
    assert context.live_allowed is False
    assert context.promotable is False
    assert context.fingerprint == _context().fingerprint


def test_context_rejects_unaligned_observation_times_or_market_mapping_mismatch():
    context = _context()
    late_derivatives = replace(context.derivatives_vector, observed_at=_at() + timedelta(hours=1))
    with pytest.raises(DerivativesSpotResearchContextError, match="share observed_at"):
        build_derivatives_spot_research_context(
            mapping=context.mapping,
            spot_vector=context.spot_vector,
            derivatives_vector=late_derivatives,
            observed_at=_at(),
        )

    with pytest.raises(DerivativesSpotResearchContextError, match="base assets must match"):
        FuturesSpotResearchMapping(
            mapping_id=context.mapping.mapping_id,
            futures_market=context.mapping.futures_market,
            spot_market=MarketIdentity("kraken", "spot", "ETHEUR", "ETH", "EUR"),
            mapping_source=context.mapping.mapping_source,
            mapping_fingerprint=context.mapping.mapping_fingerprint,
        )


def test_context_requires_explicit_market_kinds_and_remains_non_promotable():
    context = _context()
    with pytest.raises(DerivativesSpotResearchContextError, match="forbids implicit price conversion"):
        replace(context.mapping, price_conversion_allowed=True)

    bad_derivatives_snapshot = replace(
        context.derivatives_vector.feature_snapshot,
        snapshot_kind="CANONICAL_FEATURE_SNAPSHOT",
    )
    bad_derivatives_vector = replace(context.derivatives_vector, feature_snapshot=bad_derivatives_snapshot)
    with pytest.raises(DerivativesSpotResearchContextError, match="point-in-time derivatives"):
        build_derivatives_spot_research_context(
            mapping=context.mapping,
            spot_vector=context.spot_vector,
            derivatives_vector=bad_derivatives_vector,
            observed_at=_at(),
        )

    with pytest.raises(DerivativesSpotResearchContextError, match="research-only"):
        replace(context, paper_capital_allowed=True)


def test_context_module_has_no_runtime_or_order_path_imports():
    source = Path("src/autobot/v2/research/derivatives_spot_context.py").read_text(encoding="utf-8")

    for forbidden in ("order_router", "paper_trading", "signal_handler", "kraken_client", "create_order"):
        assert forbidden not in source
