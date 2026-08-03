"""Explicit, non-executable spot/derivatives research context.

Kraken Futures features can describe positioning or basis around an asset whose
AUTOBOT research return is measured on a Kraken spot-EUR market. They are not
interchangeable prices. This module makes that relationship explicit before a
future research adapter can use both sets of features at one point in time.

The context never converts a perpetual USD price into EUR, never constructs an
``AlphaSignal`` or an order, and imports no runtime, router, paper or exchange
client. It is evidence only; a strategy still needs its own bounded research
adapter and all statistical gates.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from autobot.v2.contracts import MarketIdentity, VerifiedFeatureVector

from .derivatives_feature_snapshot import (
    FORWARD_CAPTURE_ONLY_PROVENANCE_SCOPE,
    DerivativesFeatureSnapshotManifestError,
    inspect_derivatives_feature_snapshot_manifest,
)


DERIVATIVES_SPOT_RESEARCH_CONTEXT_KIND = "DERIVATIVES_SPOT_RESEARCH_CONTEXT_V1"
_SPOT_SNAPSHOT_KIND = "CANONICAL_FEATURE_SNAPSHOT"
_DERIVATIVES_SNAPSHOT_KIND = "DERIVATIVES_POINT_IN_TIME"


class DerivativesSpotResearchContextError(ValueError):
    """Raised when spot and derivatives facts lack explicit common provenance."""


@dataclass(frozen=True)
class FuturesSpotResearchMapping:
    """One auditable, directional mapping from a perpetual to a spot market.

    ``mapping_fingerprint`` identifies the manifest or controlled mapping
    record reviewed by research. The mapping is deliberately not a currency
    conversion: a USD perpetual may contextualise BTC/EUR research, but any
    future return, cost and capacity evidence must come from the spot market.
    """

    mapping_id: str
    futures_market: MarketIdentity
    spot_market: MarketIdentity
    mapping_source: str
    mapping_fingerprint: str
    price_conversion_allowed: bool = False
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False
    promotable: bool = False

    def __post_init__(self) -> None:
        for field_name in ("mapping_id", "mapping_source", "mapping_fingerprint"):
            value = str(getattr(self, field_name) or "").strip()
            if not value:
                raise DerivativesSpotResearchContextError(f"{field_name} is required")
            object.__setattr__(self, field_name, value)
        if not isinstance(self.futures_market, MarketIdentity) or not isinstance(self.spot_market, MarketIdentity):
            raise DerivativesSpotResearchContextError("explicit futures and spot market identities are required")
        if self.futures_market.market_type != "perpetual":
            raise DerivativesSpotResearchContextError("futures mapping requires a perpetual market")
        if self.spot_market.market_type != "spot":
            raise DerivativesSpotResearchContextError("futures mapping requires a spot market")
        if self.futures_market.base_asset != self.spot_market.base_asset:
            raise DerivativesSpotResearchContextError("futures and spot mapping base assets must match")
        if self.futures_market == self.spot_market:
            raise DerivativesSpotResearchContextError("futures and spot mapping must identify different markets")
        if self.price_conversion_allowed:
            raise DerivativesSpotResearchContextError("spot/derivatives context forbids implicit price conversion")
        if not self.research_only or self.paper_capital_allowed or self.live_allowed or self.promotable:
            raise DerivativesSpotResearchContextError("spot/derivatives mapping is research-only")


@dataclass(frozen=True)
class DerivativesSpotResearchContext:
    """Verified simultaneous evidence from explicit spot and perpetual markets.

    The context is not a cross-currency valuation. Consumers can inspect the
    derivative vector as feature context only and must bind PnL/costs to the
    spot vector separately. Both values have to be available at exactly the
    same observation time; a later derivative feature cannot be backfilled
    into an earlier spot decision.
    """

    mapping: FuturesSpotResearchMapping
    spot_vector: VerifiedFeatureVector
    derivatives_vector: VerifiedFeatureVector
    observed_at: datetime
    context_kind: str = DERIVATIVES_SPOT_RESEARCH_CONTEXT_KIND
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False
    promotable: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.mapping, FuturesSpotResearchMapping):
            raise DerivativesSpotResearchContextError("explicit futures/spot mapping is required")
        if not isinstance(self.spot_vector, VerifiedFeatureVector):
            raise DerivativesSpotResearchContextError("verified spot feature vector is required")
        if not isinstance(self.derivatives_vector, VerifiedFeatureVector):
            raise DerivativesSpotResearchContextError("verified derivatives feature vector is required")
        observed_at = _utc(self.observed_at, "observed_at")
        context_kind = str(self.context_kind or "").strip().upper()
        if context_kind != DERIVATIVES_SPOT_RESEARCH_CONTEXT_KIND:
            raise DerivativesSpotResearchContextError("context_kind is invalid")
        if self.spot_vector.market != self.mapping.spot_market:
            raise DerivativesSpotResearchContextError("spot vector does not match explicit mapping")
        if self.derivatives_vector.market != self.mapping.futures_market:
            raise DerivativesSpotResearchContextError("derivatives vector does not match explicit mapping")
        if self.spot_vector.observed_at != observed_at or self.derivatives_vector.observed_at != observed_at:
            raise DerivativesSpotResearchContextError("spot and derivatives vectors must share observed_at")
        if self.spot_vector.feature_snapshot.snapshot_kind != _SPOT_SNAPSHOT_KIND:
            raise DerivativesSpotResearchContextError("spot vector requires canonical spot feature snapshot evidence")
        if self.derivatives_vector.feature_snapshot.snapshot_kind != _DERIVATIVES_SNAPSHOT_KIND:
            raise DerivativesSpotResearchContextError(
                "derivatives vector requires point-in-time derivatives feature snapshot evidence"
            )
        if self.spot_vector.feature_snapshot.feature_snapshot_id == self.derivatives_vector.feature_snapshot.feature_snapshot_id:
            raise DerivativesSpotResearchContextError("spot and derivatives feature snapshots must stay distinct")
        if not self.research_only or self.paper_capital_allowed or self.live_allowed or self.promotable:
            raise DerivativesSpotResearchContextError("spot/derivatives context is research-only")
        object.__setattr__(self, "observed_at", observed_at)
        object.__setattr__(self, "context_kind", context_kind)

    @property
    def fingerprint(self) -> str:
        return sha256(_canonical_json(self.to_dict()).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "context_kind": self.context_kind,
            "mapping": {
                **asdict(self.mapping),
                "futures_market": asdict(self.mapping.futures_market),
                "spot_market": asdict(self.mapping.spot_market),
            },
            "spot_feature_vector_fingerprint": self.spot_vector.fingerprint,
            "derivatives_feature_vector_fingerprint": self.derivatives_vector.fingerprint,
            "spot_feature_snapshot_id": self.spot_vector.feature_snapshot.feature_snapshot_id,
            "derivatives_feature_snapshot_id": self.derivatives_vector.feature_snapshot.feature_snapshot_id,
            "observed_at": self.observed_at.isoformat(),
            "spot_pnl_market": asdict(self.mapping.spot_market),
            "derivatives_context_market": asdict(self.mapping.futures_market),
            "price_conversion_allowed": False,
            "price_relation": "DERIVATIVES_DIRECTIONAL_CONTEXT_ONLY",
            "research_only": True,
            "paper_capital_allowed": False,
            "live_allowed": False,
            "promotable": False,
        }


def build_derivatives_spot_research_context(
    *,
    mapping: FuturesSpotResearchMapping,
    spot_vector: VerifiedFeatureVector,
    derivatives_vector: VerifiedFeatureVector,
    observed_at: datetime,
) -> DerivativesSpotResearchContext:
    """Construct one exact, research-only multi-market feature context.

    ``mapping`` is intentionally a required domain object. Callers cannot
    infer a spot symbol from a futures symbol or manufacture a price conversion
    through a string helper.
    """

    return DerivativesSpotResearchContext(
        mapping=mapping,
        spot_vector=spot_vector,
        derivatives_vector=derivatives_vector,
        observed_at=observed_at,
    )


def build_derivatives_spot_research_context_from_snapshot(
    *,
    derivatives_snapshot_manifest: str | Path,
    spot_vector: VerifiedFeatureVector,
    derivatives_vector: VerifiedFeatureVector,
) -> DerivativesSpotResearchContext:
    """Bind a spot vector to the mapping sealed inside a derivatives bundle.

    This is the production-facing research constructor. It re-verifies the
    material snapshot and recomputes its mapping fingerprint before accepting
    the explicit ``autobot_spot_symbol`` relation. This prevents a caller from
    attaching a valid perpetual feature vector to a different spot market by
    merely supplying a plausible mapping string.
    """

    manifest_path = Path(derivatives_snapshot_manifest)
    try:
        availability = inspect_derivatives_feature_snapshot_manifest(manifest_path)
    except DerivativesFeatureSnapshotManifestError as exc:
        raise DerivativesSpotResearchContextError(str(exc)) from exc
    if availability.status != "READY":
        raise DerivativesSpotResearchContextError(
            f"derivatives snapshot is not ready: {availability.status}"
        )
    if availability.provenance_scope != FORWARD_CAPTURE_ONLY_PROVENANCE_SCOPE:
        raise DerivativesSpotResearchContextError(
            "derivatives spot context requires forward_capture_only provenance"
        )
    if not availability.material_verified or not availability.runtime_parity_proven or not availability.parity_ok:
        raise DerivativesSpotResearchContextError(
            "derivatives spot context requires material-verified runtime parity"
        )
    payload = _load_manifest(manifest_path)
    expected_snapshot_id = _required_text(payload.get("feature_snapshot_id"), "derivatives feature_snapshot_id")
    expected_vector_prefix = f"{expected_snapshot_id}_"
    if not derivatives_vector.feature_snapshot.feature_snapshot_id.startswith(expected_vector_prefix):
        raise DerivativesSpotResearchContextError(
            "derivatives vector does not belong to supplied derivatives snapshot"
        )
    for field_name in ("source_snapshot_id", "source_snapshot_fingerprint", "feature_registry_fingerprint"):
        if getattr(derivatives_vector.feature_snapshot, field_name) != _required_text(
            payload.get(field_name),
            f"derivatives {field_name}",
        ):
            raise DerivativesSpotResearchContextError(
                "derivatives vector provenance does not match supplied derivatives snapshot"
            )
    mapping_fingerprint = _required_text(
        payload.get("market_mapping_fingerprint"),
        "derivatives market_mapping_fingerprint",
    )
    mappings = _validated_manifest_mappings(payload)
    if mapping_fingerprint != _mapping_fingerprint(mappings):
        raise DerivativesSpotResearchContextError(
            "derivatives market mapping fingerprint does not match explicit mappings"
        )
    futures_symbol = derivatives_vector.market.symbol
    mapping_payload = mappings.get(futures_symbol)
    if mapping_payload is None:
        raise DerivativesSpotResearchContextError("derivatives vector symbol lacks an explicit spot mapping")
    expected_spot_symbol = mapping_payload["autobot_spot_symbol"]
    if spot_vector.market.symbol != expected_spot_symbol:
        raise DerivativesSpotResearchContextError(
            "spot vector symbol does not match derivatives snapshot mapping"
        )
    if (
        derivatives_vector.market.base_asset != mapping_payload["base_asset"]
        or derivatives_vector.market.quote_asset != mapping_payload["quote_asset"]
    ):
        raise DerivativesSpotResearchContextError(
            "derivatives vector market does not match derivatives snapshot mapping"
        )
    mapping = FuturesSpotResearchMapping(
        mapping_id=(f"{expected_snapshot_id}:{futures_symbol}:{expected_spot_symbol}").lower(),
        futures_market=derivatives_vector.market,
        spot_market=spot_vector.market,
        mapping_source="derivatives_feature_snapshot_v2",
        mapping_fingerprint=mapping_fingerprint,
    )
    return build_derivatives_spot_research_context(
        mapping=mapping,
        spot_vector=spot_vector,
        derivatives_vector=derivatives_vector,
        observed_at=derivatives_vector.observed_at,
    )


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DerivativesSpotResearchContextError(f"invalid derivatives feature snapshot manifest: {path}") from exc
    if not isinstance(payload, dict):
        raise DerivativesSpotResearchContextError("derivatives feature snapshot manifest must be an object")
    return payload


def _validated_manifest_mappings(payload: dict[str, Any]) -> dict[str, dict[str, str]]:
    raw_mappings = payload.get("market_mappings")
    if not isinstance(raw_mappings, list) or not raw_mappings:
        raise DerivativesSpotResearchContextError("derivatives snapshot market_mappings are required")
    mappings: dict[str, dict[str, str]] = {}
    for raw_mapping in raw_mappings:
        if not isinstance(raw_mapping, dict):
            raise DerivativesSpotResearchContextError("derivatives snapshot market mapping is invalid")
        futures_symbol = _required_text(raw_mapping.get("futures_symbol"), "derivatives mapping futures_symbol").upper()
        normalized = {
            "futures_symbol": futures_symbol,
            "base_asset": _required_text(raw_mapping.get("base_asset"), "derivatives mapping base_asset").upper(),
            "quote_asset": _required_text(raw_mapping.get("quote_asset"), "derivatives mapping quote_asset").upper(),
            "autobot_spot_symbol": _required_text(
                raw_mapping.get("autobot_spot_symbol"),
                "derivatives mapping autobot_spot_symbol",
            ).upper(),
        }
        if futures_symbol in mappings:
            raise DerivativesSpotResearchContextError("derivatives snapshot market mapping is ambiguous")
        mappings[futures_symbol] = normalized
    return mappings


def _mapping_fingerprint(mappings: dict[str, dict[str, str]]) -> str:
    ordered = tuple(mappings[key] for key in sorted(mappings))
    return sha256(_canonical_json({"mappings": ordered}).encode("utf-8")).hexdigest()


def _required_text(value: object, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise DerivativesSpotResearchContextError(f"{field_name} is required")
    return normalized


def _utc(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise DerivativesSpotResearchContextError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)
