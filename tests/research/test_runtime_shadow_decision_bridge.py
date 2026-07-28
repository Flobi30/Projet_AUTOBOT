"""Contract tests for the non-executable legacy runtime shadow bridge."""

from __future__ import annotations

import ast
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

import pytest

from autobot.v2.contracts import (
    AlphaSignal,
    MarketIdentity,
    RiskDecision,
    RiskMandateReference,
    contract_fingerprint,
)
from autobot.v2.research.bound_shadow_risk_evidence import BoundShadowRiskEvidence
from autobot.v2.research.portfolio_construction import (
    CapacityObservation,
    build_target_portfolio,
    review_target_portfolio_capacity,
)
from autobot.v2.research.portfolio_sizing import derive_research_sizing_decision
from autobot.v2.research.runtime_shadow_decision_bridge import build_runtime_shadow_decision
from autobot.v2.research.shadow_governance import (
    StrategyArtifact,
    feature_snapshot_reference_from_mapping,
    strategy_artifact_reference_from_mapping,
)
from autobot.v2.research.strategy_risk_mandates import PreTradeAutonomyRequest, StrategyHealthSnapshot
from autobot.v2.strategies import SignalType, TradingSignal


pytestmark = pytest.mark.unit


def _timestamp() -> datetime:
    return datetime(2026, 7, 12, 10, 1, tzinfo=timezone.utc)


def _market() -> MarketIdentity:
    return MarketIdentity("kraken", "spot", "BTCEUR", "BTC", "EUR")


def _artifact_payload() -> dict:
    return StrategyArtifact(
        strategy_id="trend_momentum",
        strategy_version="trend-v3",
        code_commit="bridge-fixture-commit",
        data_snapshot_id="ohlcv_snapshot_1",
        feature_versions={"momentum": "v1"},
        parameters={"fixture": True},
        risk_mandate_fingerprint="bridge-mandate-fixture",
        validation_manifest_fingerprint="bridge-validation-fixture",
        risk_mandate=RiskMandateReference(
            mandate_id="trend_bridge_shadow_mandate",
            strategy_id="trend_momentum",
            fingerprint="bridge-mandate-fixture",
            mode_allowed="shadow",
            capital_max_eur=0.0,
            shadow_notional_max_eur=1_000.0,
            expires_at="2026-12-31T23:59:59+00:00",
            human_approved_required_for_risk_increase=True,
        ),
        feature_snapshots=(
            feature_snapshot_reference_from_mapping(
                {
                    "feature_snapshot_id": "features_bridge_fixture",
                    "feature_snapshot_fingerprint": "feature-fingerprint-bridge-fixture",
                    "snapshot_kind": "FEATURE_SNAPSHOT",
                    "source_snapshot_id": "ohlcv_snapshot_1",
                    "source_snapshot_fingerprint": "source-fingerprint-bridge-fixture",
                    "feature_registry_fingerprint": "registry-fingerprint-bridge-fixture",
                    "feature_versions": {"momentum": "v1"},
                    "feature_count": 1,
                    "parity_ok": True,
                    "runtime_parity_proven": True,
                    "material_verified": True,
                    "bundle_content_fingerprint": "bundle-content-bridge-fixture",
                    "ingestion_time_unknown_count": 0,
                }
            ),
        ),
        status="SHADOW",
        experiment_id="bridge-experiment-fixture",
        experiment_fingerprint="bridge-experiment-fingerprint",
        human_approval_reference="bridge-human-approval",
    ).to_dict()


def _base_metadata() -> dict:
    available_at = _timestamp().isoformat()
    return {
        "strategy_id": "trend_momentum",
        "strategy_version": "trend-v3",
        "signal_id": "sig-bridge-1",
        "data_snapshot_id": "ohlcv_snapshot_1",
        "data_available_at": available_at,
        "net_expected_edge_bps": 24.0,
        "feature_versions": {"momentum": "v1"},
        "strategy_artifact": _artifact_payload(),
        "market_identity": {
            "exchange": "kraken",
            "market_type": "spot",
            "symbol": "BTCEUR",
            "base_asset": "BTC",
            "quote_asset": "EUR",
        },
        "verified_feature_vectors": {
            "features_bridge_fixture": {
                "feature_snapshot_id": "features_bridge_fixture",
                "bundle_content_fingerprint": "bundle-content-bridge-fixture",
                "feature_registry_fingerprint": "registry-fingerprint-bridge-fixture",
                "source_snapshot_id": "ohlcv_snapshot_1",
                "observed_at": available_at,
                "market_identity": {
                    "exchange": "kraken",
                    "market_type": "spot",
                    "symbol": "BTCEUR",
                    "base_asset": "BTC",
                    "quote_asset": "EUR",
                },
                "timeframe": "5m",
                "values": [
                    {
                        "feature_id": "momentum",
                        "feature_version": "v1",
                        "event_time": "2026-07-12T10:00:00+00:00",
                        "available_time": available_at,
                        "source_snapshot_id": "ohlcv_snapshot_1",
                        "value": 24.0,
                        "status": "ready",
                    }
                ],
            }
        },
    }


def _signal(metadata: dict | None = None, *, signal_type: SignalType = SignalType.BUY) -> TradingSignal:
    return TradingSignal(
        type=signal_type,
        symbol="BTC/EUR",
        price=65_000.0,
        volume=0.1,
        reason="bridge fixture",
        timestamp=datetime(2026, 7, 12, 10, tzinfo=timezone.utc),
        metadata=metadata or _base_metadata(),
    )


def _alpha() -> AlphaSignal:
    return AlphaSignal(
        strategy_id="trend_momentum",
        strategy_version="trend-v3",
        signal_id="sig-bridge-1",
        market=_market(),
        direction="long",
        generated_at=datetime(2026, 7, 12, 10, tzinfo=timezone.utc),
        available_at=_timestamp(),
        feature_versions={"momentum": "v1"},
        data_snapshot_id="ohlcv_snapshot_1",
        expected_edge_bps=24.0,
    )


def _verified_metadata() -> dict:
    metadata = _base_metadata()
    decision_id = "dec-bridge-1"
    alpha = _alpha()
    artifact = strategy_artifact_reference_from_mapping(metadata["strategy_artifact"])
    target = build_target_portfolio((alpha,), decision_id=decision_id, decision_at=alpha.available_at).target
    capacity = review_target_portfolio_capacity(
        target,
        capital_eur=1_000.0,
        observations={
            "BTCEUR": CapacityObservation(
                market=_market(),
                source_snapshot_id="capacity-bridge-fixture",
                source_snapshot_fingerprint=sha256(b"capacity-bridge-fixture").hexdigest(),
                event_time=alpha.available_at,
                available_time=alpha.available_at,
                ingestion_time=alpha.available_at,
                observed_liquidity_eur=20_000.0,
            )
        },
        expected_markets={"BTCEUR": _market()},
        max_liquidity_participation=0.05,
    )
    notional = capacity.target_notionals_eur["BTCEUR"]
    request = PreTradeAutonomyRequest(
        strategy_id="trend_momentum",
        symbol="BTCEUR",
        timeframe="5m",
        order_type="market",
        notional_eur=notional,
        symbol_exposure_eur=0.0,
        total_exposure_eur=0.0,
        daily_loss_eur=0.0,
        drawdown_pct=0.0,
        trades_today=0,
        orders_last_minute=0,
        fees_today_eur=0.0,
        slippage_bps=1.0,
        spread_bps=1.0,
        estimated_edge_bps=24.0,
        estimated_total_cost_bps=10.0,
        data_age_seconds=0,
        evaluated_at=alpha.available_at,
    )
    evidence = BoundShadowRiskEvidence(
        decision_id=decision_id,
        signal_id=alpha.signal_id,
        strategy_artifact_id=artifact.artifact_id,
        strategy_artifact_fingerprint=artifact.fingerprint,
        mandate_id=artifact.risk_mandate.mandate_id,
        mandate_fingerprint=artifact.risk_mandate.fingerprint,
        market_symbol="BTCEUR",
        target_portfolio_fingerprint=contract_fingerprint(target),
        capacity_review_fingerprint=contract_fingerprint(capacity),
        pre_trade_request=request,
        health=StrategyHealthSnapshot(rolling_pf=1.2, rolling_expectancy=0.1),
        gate_decision="ALLOW",
        gate_reasons=("research_shadow_only",),
        gate_checks_fingerprint="bridge-gate-checks-fixture",
        risk_decision=RiskDecision(
            decision_id=decision_id,
            approved=True,
            decided_at=alpha.available_at,
            reasons=("research_shadow_evidence_allowed",),
        ),
        evaluated_at=alpha.available_at,
        target_notional_eur=notional,
    )
    metadata["capacity_review"] = capacity
    metadata["sizing_decision"] = derive_research_sizing_decision(
        target=target,
        capacity_review=capacity,
        strategy_artifact=artifact,
        market=_market(),
    )
    metadata["bound_shadow_risk_evidence"] = evidence
    return metadata


def test_verified_legacy_signal_records_canonical_non_executable_decision():
    decision = build_runtime_shadow_decision(_signal(_verified_metadata()), decision_id="dec-bridge-1")

    assert decision.status == "SHADOW_DECISION_VERIFIED_NO_EXECUTION"
    assert decision.alpha_signal is not None
    assert decision.alpha_signal.signal_id == "sig-bridge-1"
    assert decision.target_portfolio is not None
    assert decision.target_portfolio.decision_id == "dec-bridge-1"
    assert decision.sizing_decision is not None
    assert decision.sizing_decision.status == "READY_FOR_SHADOW_REVIEW"
    assert decision.sizing_decision.research_only is True
    assert decision.sizing_decision.paper_capital_allowed is False
    assert decision.sizing_decision.live_allowed is False
    assert decision.risk_decision is not None
    assert decision.risk_decision.decision_id == "dec-bridge-1"
    assert decision.risk_decision.approved is False
    assert decision.risk_decision.reasons == ("runtime_shadow_observation_only",)
    payload = decision.to_dict()
    assert "order_intent" not in payload
    assert payload["order_intent_created"] is False
    assert payload["execution_command_created"] is False
    assert payload["paper_capital_allowed"] is False
    assert payload["live_allowed"] is False


def test_missing_capacity_or_risk_evidence_fails_closed_without_inference():
    missing_capacity = build_runtime_shadow_decision(_signal(_base_metadata()), decision_id="dec-bridge-1")
    metadata = _base_metadata()
    verified = _verified_metadata()
    metadata["capacity_review"] = verified["capacity_review"]
    metadata["sizing_decision"] = verified["sizing_decision"]
    missing_risk = build_runtime_shadow_decision(_signal(metadata), decision_id="dec-bridge-1")

    assert missing_capacity.status == "SHADOW_DECISION_REJECTED"
    assert missing_capacity.reason == "capacity_review_required"
    assert missing_risk.status == "SHADOW_DECISION_REJECTED"
    assert missing_risk.reason == "bound_shadow_risk_evidence_required"
    assert missing_capacity.risk_decision is not None and missing_capacity.risk_decision.approved is False


def test_missing_or_tampered_sizing_fails_closed_without_inference():
    metadata = _verified_metadata()
    metadata.pop("sizing_decision")
    missing = build_runtime_shadow_decision(_signal(metadata), decision_id="dec-bridge-1")

    tampered = _verified_metadata()
    sizing = tampered["sizing_decision"]
    tampered["sizing_decision"] = sizing.__class__(
        **{
            **sizing.__dict__,
            "proposed_notional_eur": sizing.proposed_notional_eur + 1.0,
        }
    )
    invalid = build_runtime_shadow_decision(_signal(tampered), decision_id="dec-bridge-1")

    assert missing.status == "SHADOW_DECISION_REJECTED"
    assert missing.reason == "sizing_decision_required"
    assert invalid.status == "SHADOW_DECISION_REJECTED"
    assert invalid.reason == "sizing_decision_notional_mismatch"


def test_legacy_signal_type_and_retired_strategy_are_rejected():
    sell = build_runtime_shadow_decision(_signal(_base_metadata(), signal_type=SignalType.SELL), decision_id="dec-bridge-1")
    retired = _base_metadata()
    retired["strategy_id"] = "dynamic_grid"
    blocked = build_runtime_shadow_decision(_signal(retired), decision_id="dec-bridge-1")

    assert sell.reason == "legacy_signal_type_must_be_buy"
    assert blocked.reason == "strategy_runtime_retired"


def test_bridge_import_boundary_excludes_execution_and_legacy_allocator_modules():
    import autobot.v2.research.runtime_shadow_decision_bridge as bridge

    tree = ast.parse(Path(bridge.__file__).read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )
    forbidden = ("order_router", "order_executor", "paper_trading", "portfolio_allocator", "kraken")
    assert not any(any(token in module for token in forbidden) for module in imported)
