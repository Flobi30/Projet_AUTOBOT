"""Fail-closed runtime-to-contract preview for AUTOBOT shadow observation.

This adapter deliberately does not import an executor, router, paper engine, or
runtime risk manager.  It converts a fully attributable legacy BUY signal into
the v1 contracts needed by the future runtime path and terminates in a rejected
``RiskDecision``.  The resulting preview is diagnostic evidence only: it can
never create an ``ExecutionCommand`` or an order.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import math
from typing import Any, Mapping, Sequence

from autobot.v2.contracts import (
    AlphaSignal,
    MarketIdentity,
    OrderIntent,
    RiskDecision,
    StrategyArtifactReference,
    TargetPortfolio,
    VerifiedFeatureVector,
    contract_to_dict,
)
from autobot.v2.strategy_runtime_policy import is_runtime_engine_retired

from .derivatives_spot_context import (
    DerivativesSpotResearchContextError,
    FuturesSpotResearchMapping,
    build_derivatives_spot_research_context,
)
from .portfolio_construction import PortfolioConstructionError, build_target_portfolio
from .shadow_governance import strategy_artifact_reference_from_mapping
from .verified_feature_vector import VerifiedFeatureVectorError, parse_verified_feature_vectors


@dataclass(frozen=True)
class RuntimeShadowPreview:
    """Non-executable contract evidence for one blocked legacy BUY signal."""

    status: str
    reason: str | None
    alpha_signal: AlphaSignal | None = None
    target_portfolio: TargetPortfolio | None = None
    order_intent: OrderIntent | None = None
    risk_decision: RiskDecision | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "alpha_signal": contract_to_dict(self.alpha_signal) if self.alpha_signal else None,
            "target_portfolio": contract_to_dict(self.target_portfolio) if self.target_portfolio else None,
            "order_intent": contract_to_dict(self.order_intent) if self.order_intent else None,
            "risk_decision": contract_to_dict(self.risk_decision) if self.risk_decision else None,
            "execution_command_created": False,
            "research_only": True,
            "paper_capital_allowed": False,
            "live_allowed": False,
        }


def preview_runtime_buy_signal(
    *,
    symbol: str,
    price: float,
    signal_timestamp: datetime,
    metadata: Mapping[str, Any],
    decision_id: str,
) -> RuntimeShadowPreview:
    """Build an observation-only v1 pipeline from explicit signal provenance.

    Every field which could otherwise be guessed is mandatory.  Missing
    attribution is evidence of a runtime boundary gap, not a reason to invent
    a quote currency, feature version, data timestamp, or position size.
    """

    try:
        generated_at = _utc(signal_timestamp, "signal_timestamp")
        strategy_id = _required_metadata_text(metadata, "strategy_id")
        if is_runtime_engine_retired(strategy_id):
            return _rejected(decision_id, generated_at, "strategy_runtime_retired")
        strategy_version = _required_metadata_text(metadata, "strategy_version")
        data_snapshot_id = _required_metadata_text(metadata, "data_snapshot_id")
        market = _market_identity(metadata, expected_symbol=symbol)
        feature_versions = _feature_versions(metadata)
        artifact = _strategy_artifact_reference(
            metadata,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            data_snapshot_id=data_snapshot_id,
            feature_versions=feature_versions,
        )
        available_at = _metadata_timestamp(metadata, "data_available_at")
        if available_at < generated_at:
            return _rejected(decision_id, generated_at, "data_available_before_signal")
        feature_vectors = parse_verified_feature_vectors(
            metadata.get("verified_feature_vectors"),
            snapshots=artifact.feature_snapshots,
            observed_at=available_at,
        )
        _validate_derivatives_spot_context(
            metadata,
            vectors=feature_vectors,
            observed_at=available_at,
        )
        expected_edge_bps = _positive_finite_metadata_number(metadata, "net_expected_edge_bps")
        shadow_notional = _positive_finite_metadata_number(metadata, "shadow_notional_eur")

        signal_id = str(metadata.get("signal_id") or _stable_id("signal", decision_id, strategy_id, market.symbol, generated_at.isoformat()))
        alpha = AlphaSignal(
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            signal_id=signal_id,
            market=market,
            direction="long",
            generated_at=generated_at,
            available_at=available_at,
            feature_versions=feature_versions,
            data_snapshot_id=data_snapshot_id,
            expected_edge_bps=expected_edge_bps,
            metadata={
                "adapter": "runtime_shadow_preview/v1",
                "signal_price": float(price),
                "source": str(metadata.get("execution_source") or "legacy_runtime_signal"),
                "strategy_artifact_id": artifact.artifact_id,
                "strategy_artifact_fingerprint": artifact.fingerprint,
                "verified_feature_vector_fingerprints": {
                    vector.feature_snapshot.feature_snapshot_id: vector.fingerprint
                    for vector in feature_vectors
                },
            },
        )
        target_result = build_target_portfolio(
            [alpha],
            decision_id=decision_id,
            decision_at=available_at,
        )
        if not target_result.accepted_signal_ids or market.symbol not in target_result.target.target_weights:
            reason = target_result.rejected_signals[0].reason if target_result.rejected_signals else "target_portfolio_rejected"
            return _rejected(decision_id, available_at, reason, alpha_signal=alpha, target=target_result.target)

        intent = OrderIntent(
            decision_id=decision_id,
            strategy_id=strategy_id,
            strategy_artifact=artifact,
            market=market,
            side="buy",
            target_notional=shadow_notional,
            created_at=available_at,
            data_available_at=available_at,
            execution_mode="shadow",
            client_order_id=_stable_id("shadow_order", decision_id, strategy_id, market.symbol),
            metadata={
                "adapter": "runtime_shadow_preview/v1",
                "requested_price": float(price),
                "target_weight": target_result.target.target_weights[market.symbol],
                "strategy_artifact_id": artifact.artifact_id,
                "strategy_artifact_fingerprint": artifact.fingerprint,
                "paper_capital_allowed": False,
                "live_allowed": False,
            },
        )
        return RuntimeShadowPreview(
            status="SHADOW_PREVIEW_READY",
            reason="execution_disabled_pending_runtime_integration",
            alpha_signal=alpha,
            target_portfolio=target_result.target,
            order_intent=intent,
            risk_decision=RiskDecision(
                decision_id=decision_id,
                approved=False,
                decided_at=available_at,
                reasons=("shadow_preview_only_no_execution",),
            ),
        )
    except (
        KeyError,
        TypeError,
        ValueError,
        PortfolioConstructionError,
        VerifiedFeatureVectorError,
    ) as exc:
        return _rejected(decision_id, _safe_utc(signal_timestamp), str(exc))


def _rejected(
    decision_id: str,
    decided_at: datetime,
    reason: str,
    *,
    alpha_signal: AlphaSignal | None = None,
    target: TargetPortfolio | None = None,
) -> RuntimeShadowPreview:
    return RuntimeShadowPreview(
        status="SHADOW_PREVIEW_REJECTED",
        reason=reason,
        alpha_signal=alpha_signal,
        target_portfolio=target,
        risk_decision=RiskDecision(
            decision_id=decision_id,
            approved=False,
            decided_at=decided_at,
            reasons=(reason,),
        ),
    )


def _market_identity(metadata: Mapping[str, Any], *, expected_symbol: str) -> MarketIdentity:
    value = metadata.get("market_identity")
    if not isinstance(value, Mapping):
        raise ValueError("market_identity_required")
    market = MarketIdentity(
        exchange=str(value.get("exchange") or ""),
        market_type=str(value.get("market_type") or ""),
        symbol=str(value.get("symbol") or ""),
        base_asset=str(value.get("base_asset") or ""),
        quote_asset=str(value.get("quote_asset") or ""),
    )
    if market.symbol != str(expected_symbol).strip().upper().replace("/", ""):
        raise ValueError("market_identity_symbol_mismatch")
    return market


def _feature_versions(metadata: Mapping[str, Any]) -> dict[str, str]:
    value = metadata.get("feature_versions")
    if not isinstance(value, Mapping) or not value:
        raise ValueError("feature_versions_required")
    normalized = {str(key).strip(): str(version).strip() for key, version in value.items()}
    if not all(normalized.values()):
        raise ValueError("feature_versions_invalid")
    return normalized


def _validate_derivatives_spot_context(
    metadata: Mapping[str, Any],
    *,
    vectors: Sequence[VerifiedFeatureVector],
    observed_at: datetime,
) -> None:
    """Require explicit mapping evidence when a preview consumes derivatives.

    A one-source spot preview retains the v1 shape. A two-source context is
    stricter: the persisted metadata must reconstruct an exact research-only
    spot/perpetual context at the same point in time. The resulting preview is
    still terminated by a rejected risk decision below.
    """

    derivative_vectors = [
        vector
        for vector in vectors
        if vector.feature_snapshot.snapshot_kind == "DERIVATIVES_POINT_IN_TIME"
    ]
    if not derivative_vectors:
        return
    spot_vectors = [
        vector
        for vector in vectors
        if vector.feature_snapshot.snapshot_kind in {"FEATURE_SNAPSHOT", "CANONICAL_FEATURE_SNAPSHOT"}
    ]
    if len(vectors) != 2 or len(spot_vectors) != 1 or len(derivative_vectors) != 1:
        raise ValueError("derivatives_spot_feature_vector_composition_invalid")
    context_payload = metadata.get("derivatives_spot_context")
    if not isinstance(context_payload, Mapping):
        raise ValueError("derivatives_spot_context_required")
    if str(context_payload.get("context_kind") or "").upper() != "DERIVATIVES_SPOT_RESEARCH_CONTEXT_V1":
        raise ValueError("derivatives_spot_context_kind_invalid")
    mapping_payload = context_payload.get("mapping")
    if not isinstance(mapping_payload, Mapping):
        raise ValueError("derivatives_spot_context_mapping_required")
    try:
        mapping = FuturesSpotResearchMapping(
            mapping_id=str(mapping_payload.get("mapping_id") or ""),
            futures_market=_market_identity_from_context(mapping_payload.get("futures_market")),
            spot_market=_market_identity_from_context(mapping_payload.get("spot_market")),
            mapping_source=str(mapping_payload.get("mapping_source") or ""),
            mapping_fingerprint=str(mapping_payload.get("mapping_fingerprint") or ""),
            price_conversion_allowed=mapping_payload.get("price_conversion_allowed") is True,
            research_only=mapping_payload.get("research_only") is True,
            paper_capital_allowed=mapping_payload.get("paper_capital_allowed") is True,
            live_allowed=mapping_payload.get("live_allowed") is True,
            promotable=mapping_payload.get("promotable") is True,
        )
        context = build_derivatives_spot_research_context(
            mapping=mapping,
            spot_vector=spot_vectors[0],
            derivatives_vector=derivative_vectors[0],
            observed_at=observed_at,
        )
    except (DerivativesSpotResearchContextError, TypeError, ValueError) as exc:
        raise ValueError(f"derivatives_spot_context_invalid:{exc}") from exc
    if context_payload.get("spot_feature_vector_fingerprint") != spot_vectors[0].fingerprint:
        raise ValueError("derivatives_spot_context_spot_vector_mismatch")
    if context_payload.get("derivatives_feature_vector_fingerprint") != derivative_vectors[0].fingerprint:
        raise ValueError("derivatives_spot_context_derivatives_vector_mismatch")
    if context_payload.get("observed_at") != context.observed_at.isoformat():
        raise ValueError("derivatives_spot_context_observed_at_mismatch")
    if context_payload.get("price_conversion_allowed") is not False:
        raise ValueError("derivatives_spot_context_price_conversion_forbidden")
    if context_payload.get("spot_pnl_market") != _market_mapping(context.mapping.spot_market):
        raise ValueError("derivatives_spot_context_spot_pnl_market_mismatch")
    if context_payload.get("derivatives_context_market") != _market_mapping(context.mapping.futures_market):
        raise ValueError("derivatives_spot_context_derivatives_market_mismatch")


def _market_identity_from_context(value: object) -> MarketIdentity:
    if not isinstance(value, Mapping):
        raise ValueError("derivatives_spot_context_market_required")
    return MarketIdentity(
        exchange=str(value.get("exchange") or ""),
        market_type=str(value.get("market_type") or ""),
        symbol=str(value.get("symbol") or ""),
        base_asset=str(value.get("base_asset") or ""),
        quote_asset=str(value.get("quote_asset") or ""),
    )


def _market_mapping(market: MarketIdentity) -> dict[str, str]:
    return {
        "exchange": market.exchange,
        "market_type": market.market_type,
        "symbol": market.symbol,
        "base_asset": market.base_asset,
        "quote_asset": market.quote_asset,
    }


def _strategy_artifact_reference(
    metadata: Mapping[str, Any],
    *,
    strategy_id: str,
    strategy_version: str,
    data_snapshot_id: str,
    feature_versions: Mapping[str, str],
) -> StrategyArtifactReference:
    artifact = strategy_artifact_reference_from_mapping(metadata.get("strategy_artifact"))
    if artifact.strategy_id != strategy_id.lower():
        raise ValueError("strategy_artifact_strategy_mismatch")
    if artifact.strategy_version != strategy_version:
        raise ValueError("strategy_artifact_version_mismatch")
    if artifact.data_snapshot_id != data_snapshot_id:
        raise ValueError("strategy_artifact_snapshot_mismatch")
    if dict(artifact.feature_versions) != dict(feature_versions):
        raise ValueError("strategy_artifact_feature_versions_mismatch")
    if artifact.status not in {"SHADOW_ELIGIBLE", "SHADOW"}:
        raise ValueError("strategy_artifact_not_shadow_eligible")
    return artifact


def _metadata_timestamp(metadata: Mapping[str, Any], key: str) -> datetime:
    value = metadata.get(key)
    if isinstance(value, datetime):
        return _utc(value, key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key}_required")
    return _utc(datetime.fromisoformat(value.replace("Z", "+00:00")), key)


def _positive_finite_metadata_number(metadata: Mapping[str, Any], key: str) -> float:
    try:
        value = float(metadata.get(key))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key}_required") from exc
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{key}_must_be_positive_finite")
    return value


def _required_metadata_text(metadata: Mapping[str, Any], key: str) -> str:
    value = str(metadata.get(key) or "").strip()
    if not value:
        raise ValueError(f"{key}_required")
    return value


def _utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name}_must_be_timezone_aware")
    return value.astimezone(timezone.utc)


def _safe_utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc) if value.tzinfo and value.utcoffset() is not None else datetime.now(timezone.utc)


def _stable_id(prefix: str, *parts: str) -> str:
    payload = "|".join(str(part) for part in parts)
    return f"{prefix}_{sha256(payload.encode('utf-8')).hexdigest()[:24]}"
