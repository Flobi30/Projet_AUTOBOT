"""Strict parsing for feature values crossing AUTOBOT's shadow boundary.

The functions here are pure and deliberately do not import a scheduler,
router, paper engine or execution client.  A missing or mismatched feature
vector is evidence of insufficient provenance, not a cue to infer values.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from autobot.v2.contracts import (
    FeatureSnapshotReference,
    FeatureValue,
    MarketIdentity,
    VerifiedFeatureVector,
)


class VerifiedFeatureVectorError(ValueError):
    """Raised when shadow metadata cannot prove its concrete feature inputs."""


def parse_verified_feature_vectors(
    value: Any,
    *,
    snapshots: Sequence[FeatureSnapshotReference],
    observed_at: datetime,
) -> tuple[VerifiedFeatureVector, ...]:
    """Parse exactly one complete point-in-time vector per artifact snapshot."""

    if not isinstance(value, Mapping) or not value:
        raise VerifiedFeatureVectorError("verified_feature_vectors_required")
    expected = {snapshot.feature_snapshot_id: snapshot for snapshot in snapshots}
    supplied = {str(snapshot_id): payload for snapshot_id, payload in value.items()}
    if set(supplied) != set(expected):
        raise VerifiedFeatureVectorError("verified_feature_vector_snapshot_set_mismatch")
    return tuple(
        _parse_vector(
            supplied[snapshot_id],
            snapshot=snapshot,
            observed_at=observed_at,
        )
        for snapshot_id, snapshot in sorted(expected.items())
    )


def verified_feature_vector_to_mapping(vector: VerifiedFeatureVector) -> dict[str, Any]:
    """Serialize one verified vector for the strict shadow preview boundary.

    This is deliberately the inverse of the parser's public payload shape,
    rather than a generic dataclass dump: the preview requires an explicit
    ``market_identity`` and independently repeats bundle/registry/source
    evidence before it accepts the values.
    """

    if not isinstance(vector, VerifiedFeatureVector):
        raise VerifiedFeatureVectorError("verified_feature_vector_required")
    market = vector.market
    return {
        "feature_snapshot_id": vector.feature_snapshot.feature_snapshot_id,
        "bundle_content_fingerprint": vector.feature_snapshot.bundle_content_fingerprint,
        "feature_registry_fingerprint": vector.feature_snapshot.feature_registry_fingerprint,
        "source_snapshot_id": vector.feature_snapshot.source_snapshot_id,
        "observed_at": vector.observed_at.isoformat(),
        "market_identity": {
            "exchange": market.exchange,
            "market_type": market.market_type,
            "symbol": market.symbol,
            "base_asset": market.base_asset,
            "quote_asset": market.quote_asset,
        },
        "timeframe": vector.timeframe,
        "values": [
            {
                "feature_id": item.feature_id,
                "feature_version": item.feature_version,
                "event_time": item.event_time.isoformat(),
                "available_time": item.available_time.isoformat(),
                "source_snapshot_id": item.source_snapshot_id,
                "value": item.value,
                "status": item.status,
                "metadata": dict(item.metadata),
            }
            for item in sorted(vector.values, key=lambda item: item.feature_id)
        ],
    }


def _parse_vector(
    value: Any,
    *,
    snapshot: FeatureSnapshotReference,
    observed_at: datetime,
) -> VerifiedFeatureVector:
    if not isinstance(value, Mapping):
        raise VerifiedFeatureVectorError("verified_feature_vector_payload_invalid")
    _require_equal(value, "feature_snapshot_id", snapshot.feature_snapshot_id)
    _require_equal(value, "bundle_content_fingerprint", snapshot.bundle_content_fingerprint)
    _require_equal(value, "feature_registry_fingerprint", snapshot.feature_registry_fingerprint)
    _require_equal(value, "source_snapshot_id", snapshot.source_snapshot_id)
    vector_observed_at = _parse_utc(value.get("observed_at"), "verified_feature_vector_observed_at")
    normalized_observed_at = _utc(observed_at, "observed_at")
    if vector_observed_at != normalized_observed_at:
        raise VerifiedFeatureVectorError("verified_feature_vector_observed_at_mismatch")
    market = _parse_market(value.get("market_identity"))
    timeframe = _required_text(value.get("timeframe"), "verified_feature_vector_timeframe")
    raw_values = value.get("values")
    if not isinstance(raw_values, (list, tuple)):
        raise VerifiedFeatureVectorError("verified_feature_vector_values_required")
    values = tuple(
        _parse_feature_value(raw_value, market=market, timeframe=timeframe)
        for raw_value in raw_values
    )
    try:
        return VerifiedFeatureVector(
            feature_snapshot=snapshot,
            market=market,
            timeframe=timeframe,
            observed_at=normalized_observed_at,
            values=values,
        )
    except (TypeError, ValueError) as exc:
        raise VerifiedFeatureVectorError(f"verified_feature_vector_invalid:{exc}") from exc


def _parse_feature_value(
    value: Any,
    *,
    market: MarketIdentity,
    timeframe: str,
) -> FeatureValue:
    if not isinstance(value, Mapping):
        raise VerifiedFeatureVectorError("verified_feature_value_invalid")
    metadata = value.get("metadata") or {}
    if not isinstance(metadata, Mapping):
        raise VerifiedFeatureVectorError("verified_feature_value_metadata_invalid")
    try:
        return FeatureValue(
            feature_id=_required_text(value.get("feature_id"), "feature_id"),
            feature_version=_required_text(value.get("feature_version"), "feature_version"),
            market=market,
            timeframe=timeframe,
            event_time=_parse_utc(value.get("event_time"), "feature_event_time"),
            available_time=_parse_utc(value.get("available_time"), "feature_available_time"),
            source_snapshot_id=_required_text(value.get("source_snapshot_id"), "source_snapshot_id"),
            value=value.get("value"),
            status=str(value.get("status") or ""),
            metadata=dict(metadata),
        )
    except (TypeError, ValueError) as exc:
        raise VerifiedFeatureVectorError(f"verified_feature_value_invalid:{exc}") from exc


def _parse_market(value: Any) -> MarketIdentity:
    if not isinstance(value, Mapping):
        raise VerifiedFeatureVectorError("verified_feature_vector_market_identity_required")
    try:
        return MarketIdentity(
            exchange=_required_text(value.get("exchange"), "market_exchange"),
            market_type=_required_text(value.get("market_type"), "market_type"),
            symbol=_required_text(value.get("symbol"), "market_symbol"),
            base_asset=_required_text(value.get("base_asset"), "base_asset"),
            quote_asset=_required_text(value.get("quote_asset"), "quote_asset"),
        )
    except ValueError as exc:
        raise VerifiedFeatureVectorError(f"verified_feature_vector_market_identity_invalid:{exc}") from exc


def _require_equal(value: Mapping[str, Any], key: str, expected: str | None) -> None:
    if str(value.get(key) or "").strip() != str(expected or "").strip():
        raise VerifiedFeatureVectorError(f"verified_feature_vector_{key}_mismatch")


def _required_text(value: Any, field_name: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise VerifiedFeatureVectorError(f"{field_name}_required")
    return result


def _parse_utc(value: Any, field_name: str) -> datetime:
    if isinstance(value, datetime):
        return _utc(value, field_name)
    if not isinstance(value, str) or not value.strip():
        raise VerifiedFeatureVectorError(f"{field_name}_required")
    try:
        return _utc(datetime.fromisoformat(value.replace("Z", "+00:00")), field_name)
    except ValueError as exc:
        raise VerifiedFeatureVectorError(f"{field_name}_invalid") from exc


def _utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise VerifiedFeatureVectorError(f"{field_name}_must_be_timezone_aware")
    return value.astimezone(timezone.utc)
