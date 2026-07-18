"""Strict bridge from research observations to the canonical ``AlphaSignal``.

``StrategyResearchSignal`` is a legacy research/reporting shape.  It may only
cross into the portfolio-facing alpha contract when the observation is bound to
an immutable, point-in-time ``VerifiedFeatureVector`` and a positive *net*
edge calculated with the exact declared cost profile.  This module is
research-only: it neither imports nor creates order, paper or runtime objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from typing import Any, Mapping

from autobot.v2.contracts import AlphaSignal, VerifiedFeatureVector


class StrategyResearchAlphaAdapterError(ValueError):
    """Raised when a research observation lacks canonical alpha evidence."""


@dataclass(frozen=True)
class StrategyResearchAlphaProvenance:
    """Evidence that a research observation needs before becoming alpha.

    The feature vector owns the market identity, temporal boundary, source
    snapshot and feature versions.  The adapter intentionally refuses symbol
    inference or an edge based only on gross move estimates.
    """

    strategy_id: str
    strategy_version: str
    feature_vector: VerifiedFeatureVector
    cost_model_fingerprint: str
    source: str = "strategy_research_alpha_adapter/v1"

    def __post_init__(self) -> None:
        for field_name in ("strategy_id", "strategy_version", "cost_model_fingerprint", "source"):
            value = str(getattr(self, field_name) or "").strip()
            if not value:
                raise StrategyResearchAlphaAdapterError(f"{field_name} is required")
            object.__setattr__(self, field_name, value.lower() if field_name == "strategy_id" else value)
        if not isinstance(self.feature_vector, VerifiedFeatureVector):
            raise StrategyResearchAlphaAdapterError("feature_vector must be a VerifiedFeatureVector")


@dataclass(frozen=True)
class StrategyResearchAlphaAdaptation:
    """Canonical non-executable alpha evidence emitted by the bridge."""

    alpha_signal: AlphaSignal
    source_signal_id: str
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False
    promotable: bool = False

    def __post_init__(self) -> None:
        if not self.research_only or self.paper_capital_allowed or self.live_allowed or self.promotable:
            raise StrategyResearchAlphaAdapterError("strategy research alpha adaptation is research-only")
        if not str(self.source_signal_id).strip():
            raise StrategyResearchAlphaAdapterError("source_signal_id is required")


def adapt_strategy_research_signal_to_alpha(
    signal: Any,
    *,
    provenance: StrategyResearchAlphaProvenance,
) -> StrategyResearchAlphaAdaptation:
    """Adapt one observation only when all material alpha evidence is present.

    ``buy`` observations become long alpha and require a positive
    ``net_expected_edge_bps`` bound to ``cost_model_fingerprint``.  ``sell``
    observations become ``flat`` only; the bridge never manufactures a short.
    A legacy signal timestamp must precede the feature vector's explicit
    observation timestamp, preventing the adapter from backdating features.
    """

    source_signal_id = _required_text(getattr(signal, "signal_id", None), "source_signal_id")
    strategy_id = _required_text(getattr(signal, "strategy_id", None), "strategy_id").lower()
    if strategy_id != provenance.strategy_id:
        raise StrategyResearchAlphaAdapterError("strategy_id does not match alpha provenance")
    symbol = _required_text(getattr(signal, "symbol", None), "signal symbol").upper()
    vector = provenance.feature_vector
    if vector.market.symbol != symbol:
        raise StrategyResearchAlphaAdapterError("signal symbol does not match verified feature vector market")
    generated_at = _utc(getattr(signal, "timestamp", None), "signal timestamp")
    if generated_at > vector.observed_at:
        raise StrategyResearchAlphaAdapterError("signal timestamp cannot follow feature vector observed_at")
    direction_text = _required_text(getattr(signal, "direction", None), "signal direction").lower()
    metadata = getattr(signal, "metadata", None)
    if not isinstance(metadata, Mapping):
        raise StrategyResearchAlphaAdapterError("signal metadata is required")
    if direction_text == "buy":
        direction = "long"
        expected_edge_bps = _net_expected_edge_bps(
            metadata,
            cost_model_fingerprint=provenance.cost_model_fingerprint,
        )
    elif direction_text == "sell":
        direction = "flat"
        expected_edge_bps = None
    else:
        raise StrategyResearchAlphaAdapterError("strategy research direction must be buy or sell")

    alpha_signal = AlphaSignal(
        strategy_id=provenance.strategy_id,
        strategy_version=provenance.strategy_version,
        signal_id=_alpha_signal_id(source_signal_id, provenance),
        market=vector.market,
        direction=direction,
        generated_at=vector.observed_at,
        available_at=vector.observed_at,
        feature_versions=vector.feature_snapshot.feature_versions,
        data_snapshot_id=vector.feature_snapshot.source_snapshot_id,
        expected_edge_bps=expected_edge_bps,
        metadata={
            **dict(metadata),
            "source": provenance.source,
            "source_signal_id": source_signal_id,
            "source_signal_generated_at": generated_at.isoformat(),
            "feature_vector_fingerprint": vector.fingerprint,
            "feature_snapshot_id": vector.feature_snapshot.feature_snapshot_id,
            "feature_snapshot_fingerprint": vector.feature_snapshot.fingerprint,
            "cost_model_fingerprint": provenance.cost_model_fingerprint,
            "research_only": True,
            "paper_capital_allowed": False,
            "live_allowed": False,
            "promotable": False,
        },
    )
    return StrategyResearchAlphaAdaptation(alpha_signal=alpha_signal, source_signal_id=source_signal_id)


def _net_expected_edge_bps(metadata: Mapping[str, Any], *, cost_model_fingerprint: str) -> float:
    value = metadata.get("net_expected_edge_bps")
    if value is None:
        raise StrategyResearchAlphaAdapterError("net_expected_edge_bps_missing_for_long_signal")
    try:
        expected_edge_bps = float(value)
    except (TypeError, ValueError) as exc:
        raise StrategyResearchAlphaAdapterError("net_expected_edge_bps must be numeric") from exc
    if not math.isfinite(expected_edge_bps) or expected_edge_bps <= 0.0:
        raise StrategyResearchAlphaAdapterError("net_expected_edge_bps must be positive and finite")
    declared_fingerprint = str(metadata.get("cost_model_fingerprint") or "").strip()
    if declared_fingerprint != cost_model_fingerprint:
        raise StrategyResearchAlphaAdapterError("net_expected_edge_cost_model_mismatch")
    return expected_edge_bps


def _alpha_signal_id(source_signal_id: str, provenance: StrategyResearchAlphaProvenance) -> str:
    payload = {
        "source_signal_id": source_signal_id,
        "strategy_id": provenance.strategy_id,
        "strategy_version": provenance.strategy_version,
        "feature_vector_fingerprint": provenance.feature_vector.fingerprint,
        "cost_model_fingerprint": provenance.cost_model_fingerprint,
        "source": provenance.source,
    }
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _utc(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise StrategyResearchAlphaAdapterError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _required_text(value: object, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise StrategyResearchAlphaAdapterError(f"{field_name} is required")
    return normalized
