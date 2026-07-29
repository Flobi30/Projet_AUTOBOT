"""Tests for the non-executable portfolio-to-sizing boundary."""

from __future__ import annotations

import ast
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

import pytest

from autobot.v2.contracts import AlphaSignal, MarketIdentity, RiskMandateReference
from autobot.v2.research.portfolio_construction import (
    CapacityObservation,
    PortfolioConstructionError,
    PortfolioCapacityReview,
    build_target_portfolio,
    review_target_portfolio_capacity,
)
from autobot.v2.research.portfolio_sizing import (
    derive_research_sizing_decision,
    research_sizing_blocker,
)
from autobot.v2.research.shadow_governance import (
    StrategyArtifact,
    feature_snapshot_reference_from_mapping,
    strategy_artifact_reference_from_mapping,
)


pytestmark = pytest.mark.unit


def _time() -> datetime:
    return datetime(2026, 7, 29, 10, 0, tzinfo=timezone.utc)


def _market() -> MarketIdentity:
    return MarketIdentity("kraken", "spot", "BTCEUR", "BTC", "EUR")


def _artifact(*, shadow_limit: float = 500.0, expires_at: str = "2026-12-31T23:59:59+00:00"):
    return strategy_artifact_reference_from_mapping(
        StrategyArtifact(
            strategy_id="trend_momentum",
            strategy_version="sizing-v1",
            code_commit="sizing-fixture-commit",
            data_snapshot_id="sizing-snapshot",
            feature_versions={"momentum": "v1"},
            parameters={"fixture": True},
            risk_mandate_fingerprint="sizing-mandate-fingerprint",
            validation_manifest_fingerprint="sizing-validation-fingerprint",
            risk_mandate=RiskMandateReference(
                mandate_id="sizing-shadow-mandate",
                strategy_id="trend_momentum",
                fingerprint="sizing-mandate-fingerprint",
                mode_allowed="shadow",
                capital_max_eur=0.0,
                shadow_notional_max_eur=shadow_limit,
                expires_at=expires_at,
                human_approved_required_for_risk_increase=True,
            ),
            feature_snapshots=(
                feature_snapshot_reference_from_mapping(
                    {
                        "feature_snapshot_id": "sizing-features",
                        "feature_snapshot_fingerprint": "sizing-feature-fingerprint",
                        "snapshot_kind": "FEATURE_SNAPSHOT",
                        "source_snapshot_id": "sizing-snapshot",
                        "source_snapshot_fingerprint": "sizing-source-fingerprint",
                        "feature_registry_fingerprint": "sizing-registry-fingerprint",
                        "feature_versions": {"momentum": "v1"},
                        "feature_count": 1,
                        "parity_ok": True,
                        "runtime_parity_proven": True,
                        "material_verified": True,
                        "bundle_content_fingerprint": "sizing-bundle-content",
                        "ingestion_time_unknown_count": 0,
                    }
                ),
            ),
            status="SHADOW",
            experiment_id="sizing-experiment",
            experiment_fingerprint="sizing-experiment-fingerprint",
            human_approval_reference="sizing-human-approval",
        ).to_dict()
    )


def _target_and_capacity(*, capital_eur: float = 1_000.0):
    signal = AlphaSignal(
        strategy_id="trend_momentum",
        strategy_version="sizing-v1",
        signal_id="sizing-signal",
        market=_market(),
        direction="long",
        generated_at=_time(),
        available_at=_time(),
        feature_versions={"momentum": "v1"},
        data_snapshot_id="sizing-snapshot",
        expected_edge_bps=25.0,
    )
    target = build_target_portfolio((signal,), decision_id="sizing-decision", decision_at=_time()).target
    capacity = review_target_portfolio_capacity(
        target,
        capital_eur=capital_eur,
        observations={
            "BTCEUR": CapacityObservation(
                market=_market(),
                source_snapshot_id="sizing-capacity-source",
                source_snapshot_fingerprint=sha256(b"sizing-capacity-source").hexdigest(),
                event_time=_time(),
                available_time=_time(),
                ingestion_time=_time(),
                observed_liquidity_eur=50_000.0,
            )
        },
        expected_markets={"BTCEUR": _market()},
        max_liquidity_participation=0.05,
    )
    return target, capacity


def test_sizing_is_exactly_capacity_bounded_and_research_only():
    target, capacity = _target_and_capacity()
    artifact = _artifact()

    sizing = derive_research_sizing_decision(
        target=target,
        capacity_review=capacity,
        strategy_artifact=artifact,
        market=_market(),
    )

    assert sizing.status == "READY_FOR_SHADOW_REVIEW"
    assert sizing.proposed_notional_eur == capacity.target_notionals_eur["BTCEUR"]
    assert sizing.reference_capital_eur == capacity.capital_eur
    assert sizing.research_only is True
    assert sizing.paper_capital_allowed is False
    assert sizing.live_allowed is False
    assert research_sizing_blocker(
        sizing,
        target=target,
        capacity_review=capacity,
        strategy_artifact=artifact,
        market=_market(),
    ) is None


def test_sizing_rejects_capacity_mismatch_and_mandate_limit():
    target, capacity = _target_and_capacity()
    with pytest.raises(PortfolioConstructionError, match="capacity ok estimate evidence"):
        replace(
            capacity,
            target_notionals_eur={"BTCEUR": capacity.target_notionals_eur["BTCEUR"] - 1.0},
        )
    limited = derive_research_sizing_decision(
        target=target,
        capacity_review=capacity,
        strategy_artifact=_artifact(shadow_limit=10.0),
        market=_market(),
    )

    assert limited.status == "REJECTED"
    assert limited.reasons == ("shadow_notional_limit_exceeded",)


def test_capacity_ok_cannot_be_constructed_without_complete_market_evidence():
    with pytest.raises(PortfolioConstructionError, match="capacity ok requires target notionals"):
        PortfolioCapacityReview(
            decision_id="forged-capacity-review",
            decision_at=_time(),
            capital_eur=1_000.0,
            target_notionals_eur={},
            estimates=(),
            status="CAPACITY_OK",
            reasons=("forged",),
        )


def test_sizing_rejects_expired_mandate_and_tampered_notional():
    target, capacity = _target_and_capacity()
    expired = derive_research_sizing_decision(
        target=target,
        capacity_review=capacity,
        strategy_artifact=_artifact(expires_at="2026-01-01T00:00:00+00:00"),
        market=_market(),
    )
    ready = derive_research_sizing_decision(
        target=target,
        capacity_review=capacity,
        strategy_artifact=_artifact(),
        market=_market(),
    )
    tampered = replace(ready, proposed_notional_eur=ready.proposed_notional_eur + 1.0)

    assert expired.status == "REJECTED"
    assert expired.reasons == ("risk_mandate_expired",)
    assert research_sizing_blocker(
        tampered,
        target=target,
        capacity_review=capacity,
        strategy_artifact=_artifact(),
        market=_market(),
    ) == "sizing_decision_notional_mismatch"


def test_sizing_module_has_no_execution_or_legacy_allocator_imports():
    import autobot.v2.research.portfolio_sizing as sizing_module

    tree = ast.parse(Path(sizing_module.__file__).read_text(encoding="utf-8"))
    modules = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    modules.update(
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )
    forbidden = ("order_router", "order_executor", "paper_trading", "portfolio_allocator", "kraken")
    assert not any(any(token in module for token in forbidden) for module in modules)
