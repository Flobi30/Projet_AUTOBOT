"""Fail-closed bridge from legacy strategy signals to shadow contracts.

The production runtime still receives :class:`TradingSignal` values from
legacy strategies.  This module gives those signals one strictly bounded,
non-executable path into the canonical research contracts:

``TradingSignal -> AlphaSignal -> TargetPortfolio -> RiskDecision``.

It never creates an intent, invokes a simulator, or imports a runtime service.
Complete immutable provenance is mandatory.  When the legacy producer cannot
provide it, the bridge records an explicit rejection instead of inferring a
market identity, feature, capacity value, or risk state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from typing import Any, Mapping

from autobot.v2.contracts import (
    AlphaSignal,
    MarketIdentity,
    RiskDecision,
    SizingDecision,
    StrategyArtifactReference,
    TargetPortfolio,
    contract_to_dict,
)
from autobot.v2.strategies import SignalType, TradingSignal
from autobot.v2.strategy_runtime_policy import is_runtime_engine_retired

from .bound_shadow_risk_evidence import BoundShadowRiskEvidence, shadow_risk_evidence_blocker
from .portfolio_construction import (
    PortfolioCapacityReview,
    PortfolioConstructionError,
    build_target_portfolio,
)
from .portfolio_sizing import research_sizing_blocker
from .shadow_governance import strategy_artifact_reference_from_mapping
from .verified_feature_vector import VerifiedFeatureVectorError, parse_verified_feature_vectors


@dataclass(frozen=True)
class RuntimeShadowDecision:
    """Canonical evidence emitted for a blocked legacy runtime entry.

    ``risk_decision`` is intentionally always rejected.  A verified result
    proves the data and governance boundaries line up; it does not authorize
    any downstream activity.
    """

    status: str
    reason: str
    alpha_signal: AlphaSignal | None = None
    target_portfolio: TargetPortfolio | None = None
    sizing_decision: SizingDecision | None = None
    risk_decision: RiskDecision | None = None
    capacity_review: PortfolioCapacityReview | None = None
    risk_evidence_fingerprint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "alpha_signal": contract_to_dict(self.alpha_signal) if self.alpha_signal else None,
            "target_portfolio": contract_to_dict(self.target_portfolio) if self.target_portfolio else None,
            "sizing_decision": contract_to_dict(self.sizing_decision) if self.sizing_decision else None,
            "risk_decision": contract_to_dict(self.risk_decision) if self.risk_decision else None,
            "capacity_review": contract_to_dict(self.capacity_review) if self.capacity_review else None,
            "risk_evidence_fingerprint": self.risk_evidence_fingerprint,
            "order_intent_created": False,
            "execution_command_created": False,
            "research_only": True,
            "paper_capital_allowed": False,
            "live_allowed": False,
        }


def build_runtime_shadow_decision(
    signal: TradingSignal,
    *,
    decision_id: str,
) -> RuntimeShadowDecision:
    """Translate one legacy BUY signal only when all point-in-time facts exist.

    The bridge accepts concrete in-memory evidence contracts from an upstream
    research/shadow scheduler.  It deliberately does not deserialize mutable
    stores or construct capacity/risk facts from runtime defaults.
    """

    generated_at = _safe_utc(getattr(signal, "timestamp", None))
    try:
        if not isinstance(signal, TradingSignal):
            raise ValueError("legacy_trading_signal_required")
        if signal.type is not SignalType.BUY:
            raise ValueError("legacy_signal_type_must_be_buy")
        metadata = signal.metadata
        if not isinstance(metadata, Mapping):
            raise ValueError("signal_metadata_required")
        normalized_decision_id = _required_text(decision_id, "decision_id")
        generated_at = _utc(signal.timestamp, "signal_timestamp")
        strategy_id = _required_text(metadata.get("strategy_id"), "strategy_id")
        if is_runtime_engine_retired(strategy_id):
            return _rejected(normalized_decision_id, generated_at, "strategy_runtime_retired")
        strategy_version = _required_text(metadata.get("strategy_version"), "strategy_version")
        data_snapshot_id = _required_text(metadata.get("data_snapshot_id"), "data_snapshot_id")
        signal_id = _required_text(metadata.get("signal_id"), "signal_id")
        market = _market_identity(metadata, expected_symbol=signal.symbol)
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
            return _rejected(normalized_decision_id, generated_at, "data_available_before_signal")
        vectors = parse_verified_feature_vectors(
            metadata.get("verified_feature_vectors"),
            snapshots=artifact.feature_snapshots,
            observed_at=available_at,
        )
        if any(vector.market != market for vector in vectors):
            return _rejected(normalized_decision_id, available_at, "verified_feature_vector_market_mismatch")
        expected_edge_bps = _positive_finite_metadata_number(metadata, "net_expected_edge_bps")
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
                "adapter": "runtime_shadow_decision_bridge/v1",
                "source": str(metadata.get("execution_source") or "legacy_runtime_signal"),
                "legacy_signal_reason": str(signal.reason or ""),
                "observed_price": _positive_finite_signal_price(signal.price),
                "strategy_artifact_id": artifact.artifact_id,
                "strategy_artifact_fingerprint": artifact.fingerprint,
                "verified_feature_vector_fingerprints": {
                    vector.feature_snapshot.feature_snapshot_id: vector.fingerprint
                    for vector in vectors
                },
            },
        )
        target_result = build_target_portfolio(
            [alpha],
            decision_id=normalized_decision_id,
            decision_at=available_at,
        )
        if alpha.signal_id not in target_result.accepted_signal_ids:
            reason = (
                target_result.rejected_signals[0].reason
                if target_result.rejected_signals
                else "target_portfolio_rejected"
            )
            return _rejected(
                normalized_decision_id,
                available_at,
                reason,
                alpha_signal=alpha,
                target_portfolio=target_result.target,
            )
        capacity_review = _required_capacity_review(metadata)
        if capacity_review.decision_id != normalized_decision_id:
            return _rejected(
                normalized_decision_id,
                available_at,
                "capacity_review_decision_id_mismatch",
                alpha_signal=alpha,
                target_portfolio=target_result.target,
                capacity_review=capacity_review,
            )
        sizing_decision = _required_sizing_decision(metadata)
        sizing_blocker = research_sizing_blocker(
            sizing_decision,
            target=target_result.target,
            capacity_review=capacity_review,
            strategy_artifact=artifact,
            market=market,
        )
        if sizing_blocker is not None:
            return _rejected(
                normalized_decision_id,
                available_at,
                sizing_blocker,
                alpha_signal=alpha,
                target_portfolio=target_result.target,
                capacity_review=capacity_review,
                sizing_decision=sizing_decision,
            )
        evidence = _required_risk_evidence(metadata)
        blocker = shadow_risk_evidence_blocker(
            evidence,
            decision_id=normalized_decision_id,
            signal=alpha,
            strategy_artifact=artifact,
            target=target_result.target,
            capacity_review=capacity_review,
        )
        if blocker is not None:
            return _rejected(
                normalized_decision_id,
                available_at,
                blocker,
                alpha_signal=alpha,
                target_portfolio=target_result.target,
                capacity_review=capacity_review,
                sizing_decision=sizing_decision,
            )
        return RuntimeShadowDecision(
            status="SHADOW_DECISION_VERIFIED_NO_EXECUTION",
            reason="runtime_shadow_observation_only",
            alpha_signal=alpha,
            target_portfolio=target_result.target,
            sizing_decision=sizing_decision,
            capacity_review=capacity_review,
            risk_evidence_fingerprint=evidence.fingerprint,
            risk_decision=RiskDecision(
                decision_id=normalized_decision_id,
                approved=False,
                decided_at=available_at,
                reasons=("runtime_shadow_observation_only",),
                warnings=("verified_upstream_shadow_risk_evidence",),
            ),
        )
    except (
        KeyError,
        TypeError,
        ValueError,
        PortfolioConstructionError,
        VerifiedFeatureVectorError,
    ) as exc:
        return _rejected(_safe_text(decision_id, "decision_unknown"), generated_at, str(exc))


def _rejected(
    decision_id: str,
    decided_at: datetime,
    reason: str,
    *,
    alpha_signal: AlphaSignal | None = None,
    target_portfolio: TargetPortfolio | None = None,
    capacity_review: PortfolioCapacityReview | None = None,
    sizing_decision: SizingDecision | None = None,
) -> RuntimeShadowDecision:
    return RuntimeShadowDecision(
        status="SHADOW_DECISION_REJECTED",
        reason=reason,
        alpha_signal=alpha_signal,
        target_portfolio=target_portfolio,
        capacity_review=capacity_review,
        sizing_decision=sizing_decision,
        risk_decision=RiskDecision(
            decision_id=decision_id,
            approved=False,
            decided_at=decided_at,
            reasons=(reason,),
        ),
    )


def _required_capacity_review(metadata: Mapping[str, Any]) -> PortfolioCapacityReview:
    value = metadata.get("capacity_review")
    if not isinstance(value, PortfolioCapacityReview):
        raise ValueError("capacity_review_required")
    if value.status != "CAPACITY_OK":
        raise ValueError("capacity_review_not_ok")
    return value


def _required_risk_evidence(metadata: Mapping[str, Any]) -> BoundShadowRiskEvidence:
    value = metadata.get("bound_shadow_risk_evidence")
    if not isinstance(value, BoundShadowRiskEvidence):
        raise ValueError("bound_shadow_risk_evidence_required")
    return value


def _required_sizing_decision(metadata: Mapping[str, Any]) -> SizingDecision:
    value = metadata.get("sizing_decision")
    if not isinstance(value, SizingDecision):
        raise ValueError("sizing_decision_required")
    return value


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
    if market.symbol != _normalized_symbol(expected_symbol):
        raise ValueError("market_identity_symbol_mismatch")
    return market


def _feature_versions(metadata: Mapping[str, Any]) -> dict[str, str]:
    value = metadata.get("feature_versions")
    if not isinstance(value, Mapping) or not value:
        raise ValueError("feature_versions_required")
    normalized = {str(key).strip(): str(version).strip() for key, version in value.items()}
    if not all(normalized.keys()) or not all(normalized.values()):
        raise ValueError("feature_versions_invalid")
    return normalized


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
    try:
        return _utc(datetime.fromisoformat(value.replace("Z", "+00:00")), key)
    except ValueError as exc:
        raise ValueError(f"{key}_invalid") from exc


def _positive_finite_metadata_number(metadata: Mapping[str, Any], key: str) -> float:
    try:
        value = float(metadata.get(key))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key}_required") from exc
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{key}_must_be_positive_finite")
    return value


def _positive_finite_signal_price(value: Any) -> float:
    try:
        price = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("signal_price_required") from exc
    if not math.isfinite(price) or price <= 0.0:
        raise ValueError("signal_price_must_be_positive_finite")
    return price


def _required_text(value: Any, key: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ValueError(f"{key}_required")
    return result


def _normalized_symbol(value: Any) -> str:
    return str(value or "").strip().upper().replace("/", "")


def _utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name}_must_be_timezone_aware")
    return value.astimezone(timezone.utc)


def _safe_utc(value: Any) -> datetime:
    if isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None:
        return value.astimezone(timezone.utc)
    return datetime.now(timezone.utc)


def _safe_text(value: Any, fallback: str) -> str:
    result = str(value or "").strip()
    return result or fallback
