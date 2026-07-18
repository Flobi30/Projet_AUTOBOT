"""Publish canonical feature vectors for research-only consumers.

This module is deliberately a data hand-off, not a signal, shadow executor or
runtime-order integration.  It resolves only values that were demonstrably
available at a caller-supplied timestamp, serializes them atomically and keeps
all execution permissions false.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import tempfile
from typing import Any, Sequence

from autobot.v2.contracts import FeatureSnapshotReference, VerifiedFeatureVector

from .canonical_feature_snapshot import (
    CANONICAL_FEATURE_SNAPSHOT_KIND,
    load_latest_verified_feature_vectors_from_canonical_snapshot,
    load_verified_feature_vector_from_canonical_snapshot,
)
from .feature_registry import FeatureRegistry
from .verified_feature_vector import parse_verified_feature_vectors, verified_feature_vector_to_mapping


VERIFIED_FEATURE_VECTOR_PUBLICATION_SCHEMA_VERSION = 1
VERIFIED_FEATURE_VECTOR_PUBLICATION_KIND = "RESEARCH_VERIFIED_FEATURE_VECTOR_PUBLICATION"


@dataclass(frozen=True)
class VerifiedFeatureVectorPublication:
    """Immutable metadata for one atomic research data publication."""

    run_id: str
    publication_id: str
    publication_fingerprint: str
    feature_snapshot_id: str
    bundle_content_fingerprint: str
    observed_at: str
    vector_count: int
    output_path: str
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False
    promotable: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.update(
            {
                "schema_version": VERIFIED_FEATURE_VECTOR_PUBLICATION_SCHEMA_VERSION,
                "kind": VERIFIED_FEATURE_VECTOR_PUBLICATION_KIND,
                "research_only": True,
                "paper_capital_allowed": False,
                "live_allowed": False,
                "promotable": False,
            }
        )
        return payload


def publish_verified_feature_vectors(
    *,
    run_id: str,
    feature_snapshot_manifest_path: str | Path,
    observed_at: datetime,
    output_dir: str | Path,
    symbols: Sequence[str] | None = None,
    timeframes: Sequence[str] | None = None,
    registry: FeatureRegistry | None = None,
) -> VerifiedFeatureVectorPublication:
    """Write an idempotent, atomic publication from a READY feature bundle.

    The function has no signal, strategy, scheduler, broker, paper or order
    dependencies.  It intentionally fails closed when the requested snapshot
    cannot prove a fully available vector at ``observed_at``.
    """

    normalized_run_id = str(run_id or "").strip()
    if not normalized_run_id:
        raise ValueError("verified feature vector publication run_id is required")
    normalized_observed_at = _utc(observed_at, "verified feature vector publication observed_at")
    vectors = load_latest_verified_feature_vectors_from_canonical_snapshot(
        feature_snapshot_manifest_path,
        observed_at=normalized_observed_at,
        symbols=symbols,
        timeframes=timeframes,
        registry=registry,
    )
    publication_payload = _publication_payload(
        run_id=normalized_run_id,
        feature_snapshot_manifest_path=Path(feature_snapshot_manifest_path),
        observed_at=normalized_observed_at,
        vectors=vectors,
    )
    fingerprint = _fingerprint(publication_payload)
    publication_id = f"verified_vectors_{fingerprint[:20]}"
    payload = {
        **publication_payload,
        "publication_id": publication_id,
        "publication_fingerprint": fingerprint,
    }
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{normalized_run_id}_verified_feature_vectors.json"
    if target_path.exists():
        existing = _load_existing(target_path)
        if existing.get("publication_fingerprint") != fingerprint:
            raise ValueError("verified feature vector publication path already contains different evidence")
        return _publication_from_payload(existing, output_path=target_path)
    _atomic_write_json(target_path, payload)
    return _publication_from_payload(payload, output_path=target_path)


def load_published_verified_feature_vector(
    path: str | Path,
    *,
    symbol: str,
    timeframe: str,
    registry: FeatureRegistry | None = None,
) -> VerifiedFeatureVector:
    """Re-verify one published vector against its canonical feature bundle.

    A publication is not trusted merely because its JSON structure is valid:
    this reader verifies its evidence fingerprint, parses its strict vector
    contract, reloads the exact canonical event and requires both vectors to
    have the same immutable fingerprint.  It is still research-only and has no
    dependency on a scheduler, signal handler, router or executor.
    """

    publication_path = Path(path)
    payload = _load_existing(publication_path)
    _publication_from_payload(payload, output_path=publication_path)
    target_symbol = _required_text(symbol, "published feature vector symbol").upper()
    target_timeframe = _required_text(timeframe, "published feature vector timeframe")
    raw_vectors = payload.get("vectors")
    if not isinstance(raw_vectors, list):
        raise ValueError("verified feature vector publication vectors are required")
    matching = [
        item
        for item in raw_vectors
        if isinstance(item, dict)
        and str((item.get("market_identity") or {}).get("symbol") or "").upper() == target_symbol
        and str(item.get("timeframe") or "") == target_timeframe
    ]
    if len(matching) != 1:
        raise ValueError("published feature vector market/timeframe is ambiguous or missing")
    observed_at = _parse_utc(payload.get("observed_at"), "published feature vector observed_at")
    snapshot = FeatureSnapshotReference(
        feature_snapshot_id=_required_text(payload.get("feature_snapshot_id"), "published feature snapshot id"),
        fingerprint=_required_text(payload.get("feature_snapshot_fingerprint"), "published feature snapshot fingerprint"),
        snapshot_kind=CANONICAL_FEATURE_SNAPSHOT_KIND,
        source_snapshot_id=_required_text(payload.get("source_snapshot_id"), "published source snapshot id"),
        source_snapshot_fingerprint=_required_text(
            payload.get("source_snapshot_fingerprint"), "published source snapshot fingerprint"
        ),
        feature_registry_fingerprint=_required_text(
            payload.get("feature_registry_fingerprint"), "published feature registry fingerprint"
        ),
        feature_versions=_required_mapping(payload.get("feature_versions"), "published feature versions"),
        runtime_parity_proven=payload.get("runtime_parity_proven") is True,
        material_verified=payload.get("material_verified") is True,
        bundle_content_fingerprint=_required_text(
            payload.get("bundle_content_fingerprint"), "published feature bundle fingerprint"
        ),
        ingestion_time_unknown_count=int(payload.get("ingestion_time_unknown_count") or 0),
    )
    published = parse_verified_feature_vectors(
        {snapshot.feature_snapshot_id: matching[0]},
        snapshots=(snapshot,),
        observed_at=observed_at,
    )[0]
    event_times = {item.event_time for item in published.values}
    if len(event_times) != 1:
        raise ValueError("published feature vector values must share one event_time")
    canonical = load_verified_feature_vector_from_canonical_snapshot(
        _required_text(payload.get("feature_snapshot_manifest_path"), "published feature snapshot manifest path"),
        symbol=target_symbol,
        timeframe=target_timeframe,
        event_time=next(iter(event_times)),
        observed_at=observed_at,
        registry=registry,
    )
    if canonical.fingerprint != published.fingerprint:
        raise ValueError("published feature vector does not match canonical bundle")
    return published


def _publication_payload(
    *,
    run_id: str,
    feature_snapshot_manifest_path: Path,
    observed_at: datetime,
    vectors: Sequence[VerifiedFeatureVector],
) -> dict[str, Any]:
    if not vectors:
        raise ValueError("verified feature vector publication requires vectors")
    snapshots = {item.feature_snapshot.feature_snapshot_id: item.feature_snapshot for item in vectors}
    if len(snapshots) != 1:
        raise ValueError("verified feature vector publication requires one feature snapshot")
    snapshot = next(iter(snapshots.values()))
    vector_payload = [
        verified_feature_vector_to_mapping(vector)
        for vector in sorted(vectors, key=lambda item: (item.market.symbol, item.timeframe, item.fingerprint))
    ]
    return {
        "schema_version": VERIFIED_FEATURE_VECTOR_PUBLICATION_SCHEMA_VERSION,
        "kind": VERIFIED_FEATURE_VECTOR_PUBLICATION_KIND,
        "run_id": run_id,
        "feature_snapshot_manifest_path": str(feature_snapshot_manifest_path),
        "feature_snapshot_id": snapshot.feature_snapshot_id,
        "feature_snapshot_fingerprint": snapshot.fingerprint,
        "bundle_content_fingerprint": snapshot.bundle_content_fingerprint,
        "feature_registry_fingerprint": snapshot.feature_registry_fingerprint,
        "source_snapshot_id": snapshot.source_snapshot_id,
        "source_snapshot_fingerprint": snapshot.source_snapshot_fingerprint,
        "feature_versions": dict(snapshot.feature_versions),
        "runtime_parity_proven": snapshot.runtime_parity_proven,
        "material_verified": snapshot.material_verified,
        "ingestion_time_unknown_count": snapshot.ingestion_time_unknown_count,
        "observed_at": observed_at.isoformat(),
        "vectors": vector_payload,
        "research_only": True,
        "paper_capital_allowed": False,
        "live_allowed": False,
        "promotable": False,
    }


def _publication_from_payload(payload: dict[str, Any], *, output_path: Path) -> VerifiedFeatureVectorPublication:
    _require_equal(payload, "schema_version", VERIFIED_FEATURE_VECTOR_PUBLICATION_SCHEMA_VERSION)
    _require_equal(payload, "kind", VERIFIED_FEATURE_VECTOR_PUBLICATION_KIND)
    for key in ("research_only",):
        if payload.get(key) is not True:
            raise ValueError(f"verified feature vector publication {key} must be true")
    for key in ("paper_capital_allowed", "live_allowed", "promotable"):
        if payload.get(key) is not False:
            raise ValueError(f"verified feature vector publication {key} must be false")
    evidence = {key: value for key, value in payload.items() if key not in {"publication_id", "publication_fingerprint"}}
    fingerprint = _fingerprint(evidence)
    if str(payload.get("publication_fingerprint") or "") != fingerprint:
        raise ValueError("verified feature vector publication fingerprint mismatch")
    if str(payload.get("publication_id") or "") != f"verified_vectors_{fingerprint[:20]}":
        raise ValueError("verified feature vector publication id mismatch")
    return VerifiedFeatureVectorPublication(
        run_id=_required_text(payload.get("run_id"), "verified feature vector publication run_id"),
        publication_id=_required_text(payload.get("publication_id"), "verified feature vector publication id"),
        publication_fingerprint=_required_text(
            payload.get("publication_fingerprint"), "verified feature vector publication fingerprint"
        ),
        feature_snapshot_id=_required_text(payload.get("feature_snapshot_id"), "verified feature vector snapshot id"),
        bundle_content_fingerprint=_required_text(
            payload.get("bundle_content_fingerprint"), "verified feature vector bundle fingerprint"
        ),
        observed_at=_required_text(payload.get("observed_at"), "verified feature vector observed_at"),
        vector_count=len(payload.get("vectors") or ()),
        output_path=str(output_path),
    )


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temp_path = Path(handle.name)
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    try:
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def _load_existing(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid existing verified feature vector publication: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("existing verified feature vector publication must be an object")
    return payload


def _fingerprint(value: dict[str, Any]) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _required_text(value: Any, field_name: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ValueError(f"{field_name} is required")
    return result


def _required_mapping(value: Any, field_name: str) -> dict[str, str]:
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{field_name} is required")
    result = {str(key).strip(): str(item).strip() for key, item in value.items()}
    if not all(result) or not all(result.values()):
        raise ValueError(f"{field_name} is invalid")
    return result


def _parse_utc(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")
    try:
        return _utc(datetime.fromisoformat(value.replace("Z", "+00:00")), field_name)
    except ValueError as exc:
        raise ValueError(f"{field_name} is invalid") from exc


def _require_equal(payload: dict[str, Any], key: str, expected: Any) -> None:
    if payload.get(key) != expected:
        raise ValueError(f"verified feature vector publication {key} is invalid")
