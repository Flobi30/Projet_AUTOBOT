"""Read-only bridge from canonical feature publications to shadow evidence.

The live runtime intentionally does not read a mutable research directory.
This module therefore runs only as an offline/batch binding step: it resolves
one immutable registered artifact, re-verifies either one published canonical
feature vector or one sealed spot/derivatives context, and emits the explicit
metadata required by the non-executable shadow preview boundary. It has no
scheduler, router, executor, paper or order dependency.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any

from autobot.v2.contracts import VerifiedFeatureVector, contract_to_dict

from .derivatives_spot_context import DerivativesSpotResearchContext
from .shadow_governance import ShadowGovernanceError, StrategyArtifact, StrategyArtifactRegistry
from .verified_feature_vector import verified_feature_vector_to_mapping
from .verified_feature_vector_publication import load_published_verified_feature_vector


class OfflineShadowProvenanceError(ValueError):
    """Raised when an offline shadow bind cannot prove every input."""


@dataclass(frozen=True)
class OfflineShadowProvenanceBinding:
    """Concrete, non-executable evidence for one offline shadow preview.

    V1 intentionally supports one material-verified feature snapshot. The
    separately named derivatives/spot binder below proves a coherent common
    observation time for every source rather than silently mixing a spot
    vector with a stale derivatives vector.
    """

    artifact: StrategyArtifact
    vector: VerifiedFeatureVector
    decision_at: datetime
    signal_id: str
    net_expected_edge_bps: float
    shadow_notional_eur: float
    execution_source: str = "offline_shadow_provenance/v1"
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False
    runtime_started: bool = False
    order_created: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.artifact, StrategyArtifact):
            raise OfflineShadowProvenanceError("strategy artifact is required")
        if not isinstance(self.vector, VerifiedFeatureVector):
            raise OfflineShadowProvenanceError("verified feature vector is required")
        decision_at = _utc(self.decision_at, "decision_at")
        if self.vector.observed_at != decision_at:
            raise OfflineShadowProvenanceError("decision_at must equal verified feature vector observed_at")
        signal_id = str(self.signal_id or "").strip()
        if not signal_id:
            raise OfflineShadowProvenanceError("signal_id is required")
        source = str(self.execution_source or "").strip()
        if not source:
            raise OfflineShadowProvenanceError("execution_source is required")
        for field_name in ("net_expected_edge_bps", "shadow_notional_eur"):
            value = float(getattr(self, field_name))
            if not math.isfinite(value) or value <= 0.0:
                raise OfflineShadowProvenanceError(f"{field_name} must be positive and finite")
            object.__setattr__(self, field_name, value)
        if self.research_only is not True or self.paper_capital_allowed or self.live_allowed:
            raise OfflineShadowProvenanceError("offline shadow provenance is research-only")
        if self.runtime_started or self.order_created:
            raise OfflineShadowProvenanceError("offline shadow provenance cannot start runtime or create an order")
        object.__setattr__(self, "decision_at", decision_at)
        object.__setattr__(self, "signal_id", signal_id)
        object.__setattr__(self, "execution_source", source)

    @property
    def fingerprint(self) -> str:
        payload = {
            "artifact": contract_to_dict(self.artifact.to_order_intent_reference()),
            "feature_vector_fingerprint": self.vector.fingerprint,
            "decision_at": self.decision_at.isoformat(),
            "signal_id": self.signal_id,
            "net_expected_edge_bps": self.net_expected_edge_bps,
            "shadow_notional_eur": self.shadow_notional_eur,
            "execution_source": self.execution_source,
        }
        return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    def to_preview_metadata(self) -> dict[str, Any]:
        """Return the exact data accepted by the non-executable preview.

        The result deliberately contains no execution permission, endpoint,
        price discovery or capital allocation authority.  A caller may use it
        only to reproduce a blocked shadow preview in a batch test.
        """

        market = self.vector.market
        return {
            "strategy_id": self.artifact.strategy_id,
            "strategy_version": self.artifact.strategy_version,
            "signal_id": self.signal_id,
            "data_snapshot_id": self.artifact.data_snapshot_id,
            "data_available_at": self.decision_at.isoformat(),
            "net_expected_edge_bps": self.net_expected_edge_bps,
            "shadow_notional_eur": self.shadow_notional_eur,
            "feature_versions": dict(self.artifact.feature_versions),
            "verified_feature_vectors": {
                self.vector.feature_snapshot.feature_snapshot_id: verified_feature_vector_to_mapping(self.vector)
            },
            "strategy_artifact": self.artifact.to_dict(),
            "market_identity": {
                "exchange": market.exchange,
                "market_type": market.market_type,
                "symbol": market.symbol,
                "base_asset": market.base_asset,
                "quote_asset": market.quote_asset,
            },
            "execution_source": self.execution_source,
            "offline_shadow_provenance_fingerprint": self.fingerprint,
            "research_only": True,
            "paper_capital_allowed": False,
            "live_allowed": False,
            "runtime_started": False,
            "order_created": False,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact.artifact_id,
            "artifact_fingerprint": self.artifact.fingerprint,
            "feature_snapshot_id": self.vector.feature_snapshot.feature_snapshot_id,
            "feature_vector_fingerprint": self.vector.fingerprint,
            "market": asdict(self.vector.market),
            "timeframe": self.vector.timeframe,
            "decision_at": self.decision_at.isoformat(),
            "signal_id": self.signal_id,
            "net_expected_edge_bps": self.net_expected_edge_bps,
            "shadow_notional_eur": self.shadow_notional_eur,
            "execution_source": self.execution_source,
            "fingerprint": self.fingerprint,
            "research_only": True,
            "paper_capital_allowed": False,
            "live_allowed": False,
            "runtime_started": False,
            "order_created": False,
        }


@dataclass(frozen=True)
class OfflineDerivativesSpotShadowProvenanceBinding:
    """Immutable multi-source evidence for one non-executable shadow preview.

    The spot vector supplies the only spot-EUR market identity for the preview.
    The perpetual vector is retained as a verified directional context. This
    object cannot convert prices, submit a command or grant paper/live rights.
    """

    artifact: StrategyArtifact
    context: DerivativesSpotResearchContext
    decision_at: datetime
    signal_id: str
    net_expected_edge_bps: float
    shadow_notional_eur: float
    execution_source: str = "offline_derivatives_spot_shadow_provenance/v1"
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False
    runtime_started: bool = False
    order_created: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.artifact, StrategyArtifact):
            raise OfflineShadowProvenanceError("strategy artifact is required")
        if not isinstance(self.context, DerivativesSpotResearchContext):
            raise OfflineShadowProvenanceError("verified derivatives/spot context is required")
        decision_at = _utc(self.decision_at, "decision_at")
        if self.context.observed_at != decision_at:
            raise OfflineShadowProvenanceError("decision_at must equal derivatives/spot context observed_at")
        signal_id = str(self.signal_id or "").strip()
        if not signal_id:
            raise OfflineShadowProvenanceError("signal_id is required")
        source = str(self.execution_source or "").strip()
        if not source:
            raise OfflineShadowProvenanceError("execution_source is required")
        for field_name in ("net_expected_edge_bps", "shadow_notional_eur"):
            value = float(getattr(self, field_name))
            if not math.isfinite(value) or value <= 0.0:
                raise OfflineShadowProvenanceError(f"{field_name} must be positive and finite")
            object.__setattr__(self, field_name, value)
        if self.research_only is not True or self.paper_capital_allowed or self.live_allowed:
            raise OfflineShadowProvenanceError("offline derivatives/spot provenance is research-only")
        if self.runtime_started or self.order_created:
            raise OfflineShadowProvenanceError(
                "offline derivatives/spot provenance cannot start runtime or create an order"
            )
        object.__setattr__(self, "decision_at", decision_at)
        object.__setattr__(self, "signal_id", signal_id)
        object.__setattr__(self, "execution_source", source)

    @property
    def vectors(self) -> tuple[VerifiedFeatureVector, VerifiedFeatureVector]:
        return (self.context.spot_vector, self.context.derivatives_vector)

    @property
    def fingerprint(self) -> str:
        payload = {
            "artifact": contract_to_dict(self.artifact.to_order_intent_reference()),
            "derivatives_spot_context_fingerprint": self.context.fingerprint,
            "feature_vector_fingerprints": {
                vector.feature_snapshot.feature_snapshot_id: vector.fingerprint for vector in self.vectors
            },
            "decision_at": self.decision_at.isoformat(),
            "signal_id": self.signal_id,
            "net_expected_edge_bps": self.net_expected_edge_bps,
            "shadow_notional_eur": self.shadow_notional_eur,
            "execution_source": self.execution_source,
        }
        return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    def to_preview_metadata(self) -> dict[str, Any]:
        """Emit multi-source facts accepted by the blocked shadow preview only."""

        spot_market = self.context.mapping.spot_market
        return {
            "strategy_id": self.artifact.strategy_id,
            "strategy_version": self.artifact.strategy_version,
            "signal_id": self.signal_id,
            "data_snapshot_id": self.artifact.data_snapshot_id,
            "data_available_at": self.decision_at.isoformat(),
            "net_expected_edge_bps": self.net_expected_edge_bps,
            "shadow_notional_eur": self.shadow_notional_eur,
            "feature_versions": dict(self.artifact.feature_versions),
            "verified_feature_vectors": {
                vector.feature_snapshot.feature_snapshot_id: verified_feature_vector_to_mapping(vector)
                for vector in self.vectors
            },
            "strategy_artifact": self.artifact.to_dict(),
            "market_identity": {
                "exchange": spot_market.exchange,
                "market_type": spot_market.market_type,
                "symbol": spot_market.symbol,
                "base_asset": spot_market.base_asset,
                "quote_asset": spot_market.quote_asset,
            },
            "derivatives_spot_context": self.context.to_dict(),
            "execution_source": self.execution_source,
            "offline_derivatives_spot_provenance_fingerprint": self.fingerprint,
            "research_only": True,
            "paper_capital_allowed": False,
            "live_allowed": False,
            "runtime_started": False,
            "order_created": False,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact.artifact_id,
            "artifact_fingerprint": self.artifact.fingerprint,
            "derivatives_spot_context_fingerprint": self.context.fingerprint,
            "spot_feature_vector_fingerprint": self.context.spot_vector.fingerprint,
            "derivatives_feature_vector_fingerprint": self.context.derivatives_vector.fingerprint,
            "spot_market": asdict(self.context.mapping.spot_market),
            "derivatives_market": asdict(self.context.mapping.futures_market),
            "decision_at": self.decision_at.isoformat(),
            "signal_id": self.signal_id,
            "net_expected_edge_bps": self.net_expected_edge_bps,
            "shadow_notional_eur": self.shadow_notional_eur,
            "execution_source": self.execution_source,
            "fingerprint": self.fingerprint,
            "research_only": True,
            "paper_capital_allowed": False,
            "live_allowed": False,
            "runtime_started": False,
            "order_created": False,
        }


def load_offline_shadow_provenance(
    *,
    artifact_registry_path: str | Path,
    artifact_id: str,
    feature_publication_path: str | Path,
    symbol: str,
    timeframe: str,
    decision_at: datetime,
    signal_id: str,
    net_expected_edge_bps: float,
    shadow_notional_eur: float,
    execution_source: str = "offline_shadow_provenance/v1",
) -> OfflineShadowProvenanceBinding:
    """Read and bind immutable artifact and publication evidence only."""

    registry = StrategyArtifactRegistry(Path(artifact_registry_path))
    try:
        artifact = registry.resolve_shadow_artifact(artifact_id)
    except ShadowGovernanceError as exc:
        raise OfflineShadowProvenanceError(f"strategy artifact binding unavailable: {exc}") from exc
    vector = load_published_verified_feature_vector(
        feature_publication_path,
        symbol=symbol,
        timeframe=timeframe,
    )
    return bind_offline_shadow_provenance(
        artifact=artifact,
        vector=vector,
        decision_at=decision_at,
        signal_id=signal_id,
        net_expected_edge_bps=net_expected_edge_bps,
        shadow_notional_eur=shadow_notional_eur,
        execution_source=execution_source,
    )


def bind_offline_shadow_provenance(
    *,
    artifact: StrategyArtifact,
    vector: VerifiedFeatureVector,
    decision_at: datetime,
    signal_id: str,
    net_expected_edge_bps: float,
    shadow_notional_eur: float,
    execution_source: str = "offline_shadow_provenance/v1",
) -> OfflineShadowProvenanceBinding:
    """Bind an already resolved artifact to exactly one verified feature vector."""

    if not isinstance(artifact, StrategyArtifact):
        raise OfflineShadowProvenanceError("strategy artifact is required")
    if not isinstance(vector, VerifiedFeatureVector):
        raise OfflineShadowProvenanceError("verified feature vector is required")
    if artifact.status not in {"SHADOW_ELIGIBLE", "SHADOW"}:
        raise OfflineShadowProvenanceError("strategy artifact is not eligible for a new shadow bind")
    if len(artifact.feature_snapshots) != 1:
        raise OfflineShadowProvenanceError("offline shadow provenance v1 requires exactly one feature snapshot")
    expected_snapshot = artifact.feature_snapshots[0]
    if vector.feature_snapshot != expected_snapshot:
        raise OfflineShadowProvenanceError("verified feature vector snapshot does not match strategy artifact")
    if vector.feature_snapshot.source_snapshot_id != artifact.data_snapshot_id:
        raise OfflineShadowProvenanceError("verified feature vector source snapshot does not match strategy artifact")
    if dict(vector.feature_snapshot.feature_versions) != dict(artifact.feature_versions):
        raise OfflineShadowProvenanceError("verified feature vector versions do not match strategy artifact")
    mandate = artifact.risk_mandate
    if mandate is None or mandate.mode_allowed != "shadow":
        raise OfflineShadowProvenanceError("strategy artifact lacks a shadow-only risk mandate")
    normalized_decision_at = _utc(decision_at, "decision_at")
    if not mandate.is_current(normalized_decision_at):
        raise OfflineShadowProvenanceError("strategy artifact shadow mandate is expired")
    requested_notional = float(shadow_notional_eur)
    if not math.isfinite(requested_notional) or requested_notional <= 0.0:
        raise OfflineShadowProvenanceError("shadow_notional_eur must be positive and finite")
    if requested_notional > mandate.shadow_notional_max_eur + 1e-12:
        raise OfflineShadowProvenanceError("shadow_notional_eur exceeds strategy artifact mandate")
    return OfflineShadowProvenanceBinding(
        artifact=artifact,
        vector=vector,
        decision_at=normalized_decision_at,
        signal_id=signal_id,
        net_expected_edge_bps=net_expected_edge_bps,
        shadow_notional_eur=requested_notional,
        execution_source=execution_source,
    )


def bind_offline_derivatives_spot_shadow_provenance(
    *,
    artifact: StrategyArtifact,
    context: DerivativesSpotResearchContext,
    decision_at: datetime,
    signal_id: str,
    net_expected_edge_bps: float,
    shadow_notional_eur: float,
    execution_source: str = "offline_derivatives_spot_shadow_provenance/v1",
) -> OfflineDerivativesSpotShadowProvenanceBinding:
    """Bind a governed artifact to one exact spot/derivatives context.

    This remains a batch-only contract step. Its only downstream-compatible
    result is a preview with an explicitly rejected risk decision. A caller
    cannot use this function to create an execution command, paper allocation
    or live order.
    """

    if not isinstance(artifact, StrategyArtifact):
        raise OfflineShadowProvenanceError("strategy artifact is required")
    if not isinstance(context, DerivativesSpotResearchContext):
        raise OfflineShadowProvenanceError("verified derivatives/spot context is required")
    if context.mapping.mapping_source != "derivatives_feature_snapshot_v2":
        raise OfflineShadowProvenanceError("derivatives/spot context must use manifest-sealed mapping evidence")
    if artifact.status not in {"SHADOW_ELIGIBLE", "SHADOW"}:
        raise OfflineShadowProvenanceError("strategy artifact is not eligible for a new shadow bind")
    expected_snapshots = {
        context.spot_vector.feature_snapshot.feature_snapshot_id: context.spot_vector.feature_snapshot,
        context.derivatives_vector.feature_snapshot.feature_snapshot_id: context.derivatives_vector.feature_snapshot,
    }
    artifact_snapshots = {snapshot.feature_snapshot_id: snapshot for snapshot in artifact.feature_snapshots}
    if len(expected_snapshots) != 2 or artifact_snapshots != expected_snapshots:
        raise OfflineShadowProvenanceError(
            "derivatives/spot feature snapshot evidence does not match strategy artifact"
        )
    expected_versions: dict[str, str] = {}
    for vector in (context.spot_vector, context.derivatives_vector):
        for feature_id, version in vector.feature_snapshot.feature_versions.items():
            if feature_id in expected_versions:
                raise OfflineShadowProvenanceError("derivatives/spot feature versions must not overlap")
            expected_versions[feature_id] = version
    if dict(artifact.feature_versions) != expected_versions:
        raise OfflineShadowProvenanceError("derivatives/spot feature versions do not match strategy artifact")
    mandate = artifact.risk_mandate
    if mandate is None or mandate.mode_allowed != "shadow":
        raise OfflineShadowProvenanceError("strategy artifact lacks a shadow-only risk mandate")
    normalized_decision_at = _utc(decision_at, "decision_at")
    if not mandate.is_current(normalized_decision_at):
        raise OfflineShadowProvenanceError("strategy artifact shadow mandate is expired")
    requested_notional = float(shadow_notional_eur)
    if not math.isfinite(requested_notional) or requested_notional <= 0.0:
        raise OfflineShadowProvenanceError("shadow_notional_eur must be positive and finite")
    if requested_notional > mandate.shadow_notional_max_eur + 1e-12:
        raise OfflineShadowProvenanceError("shadow_notional_eur exceeds strategy artifact mandate")
    return OfflineDerivativesSpotShadowProvenanceBinding(
        artifact=artifact,
        context=context,
        decision_at=normalized_decision_at,
        signal_id=signal_id,
        net_expected_edge_bps=net_expected_edge_bps,
        shadow_notional_eur=requested_notional,
        execution_source=execution_source,
    )


def _utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise OfflineShadowProvenanceError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)
