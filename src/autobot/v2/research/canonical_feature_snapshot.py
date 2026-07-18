"""Materialize deterministic, point-in-time feature snapshots for AUTOBOT.

The module is deliberately batch-only and research-only.  It reads a v2
canonical OHLCV manifest, requires an explicit market mapping, computes the
shared feature registry values and writes a reproducible feature bundle.  It
does not import runtime, paper, order, router or execution modules.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import tempfile
from typing import Any, Mapping, Sequence

from autobot.v2.contracts import MarketIdentity, contract_to_dict

from .feature_registry import FeatureRegistry, default_feature_registry, validate_historical_shadow_parity


CANONICAL_FEATURE_SNAPSHOT_SCHEMA_VERSION = 2
CANONICAL_FEATURE_SNAPSHOT_KIND = "CANONICAL_FEATURE_SNAPSHOT"
MATERIAL_HASH_ALGORITHM = "sha256"
DEFAULT_CANONICAL_OHLCV_FEATURE_IDS = (
    "return_1_bps",
    "momentum_3_bps",
    "volatility_20_bps",
    "atr_14_bps",
)
FEATURE_CSV_FIELDS = (
    "source_snapshot_id",
    "feature_id",
    "feature_version",
    "exchange",
    "market_type",
    "symbol",
    "base_asset",
    "quote_asset",
    "timeframe",
    "event_time",
    "available_time",
    "value",
    "status",
    "metadata_json",
)
FEATURE_PARITY_MAX_ROWS = 2_048


@dataclass(frozen=True)
class CanonicalFeatureSnapshotConfig:
    run_id: str
    canonical_manifest_path: Path
    output_dir: Path = Path("data/research/canonical/features")
    manifest_dir: Path = Path("data/research/manifests")
    feature_ids: tuple[str, ...] = DEFAULT_CANONICAL_OHLCV_FEATURE_IDS


@dataclass(frozen=True)
class CanonicalFeatureFile:
    symbol: str
    timeframe: str
    feature_count: int
    ready_count: int
    waiting_count: int
    missing_count: int
    csv_path: str
    content_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CanonicalFeatureSnapshot:
    run_id: str
    generated_at: str
    feature_snapshot_id: str
    fingerprint: str
    bundle_content_fingerprint: str
    source_snapshot_id: str
    source_snapshot_fingerprint: str
    feature_registry_fingerprint: str
    schema_version: int
    feature_ids: tuple[str, ...]
    feature_versions: Mapping[str, str]
    canonical_row_count: int
    eligible_row_count: int
    rejected_unverified_mapping_count: int
    ingestion_time_unknown_count: int
    feature_count: int
    ready_count: int
    waiting_count: int
    missing_count: int
    parity_ok: bool
    status: str
    blockers: tuple[str, ...]
    files: tuple[CanonicalFeatureFile, ...]
    parity_sample_row_count: int = 0
    parity_validation_scope: str = "bounded_deterministic_sample"
    holdout_partition: Mapping[str, Any] | None = None
    holdout_partition_role: str | None = None
    manifest_path: str | None = None
    paper_capital_allowed: bool = False
    live_allowed: bool = False
    promotable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "feature_snapshot_id": self.feature_snapshot_id,
            "fingerprint": self.fingerprint,
            "bundle_content_fingerprint": self.bundle_content_fingerprint,
            "bundle_content_hash_algorithm": MATERIAL_HASH_ALGORITHM,
            "snapshot_kind": CANONICAL_FEATURE_SNAPSHOT_KIND,
            "source_snapshot_id": self.source_snapshot_id,
            "source_snapshot_fingerprint": self.source_snapshot_fingerprint,
            "feature_registry_fingerprint": self.feature_registry_fingerprint,
            "schema_version": self.schema_version,
            "feature_ids": list(self.feature_ids),
            "feature_versions": dict(self.feature_versions),
            "canonical_row_count": self.canonical_row_count,
            "eligible_row_count": self.eligible_row_count,
            "rejected_unverified_mapping_count": self.rejected_unverified_mapping_count,
            "ingestion_time_unknown_count": self.ingestion_time_unknown_count,
            "feature_count": self.feature_count,
            "ready_count": self.ready_count,
            "waiting_count": self.waiting_count,
            "missing_count": self.missing_count,
            "parity_ok": self.parity_ok,
            "parity_sample_row_count": self.parity_sample_row_count,
            "parity_validation_scope": self.parity_validation_scope,
            "holdout_partition": dict(self.holdout_partition) if self.holdout_partition else None,
            "holdout_partition_role": self.holdout_partition_role,
            "status": self.status,
            "blockers": list(self.blockers),
            "files": [item.to_dict() for item in self.files],
            "manifest_path": self.manifest_path,
            "paper_capital_allowed": False,
            "live_allowed": False,
            "promotable": False,
            "safety_notes": [
                "Research-only batch feature materialization.",
                "No runtime order path, shadow activation, paper capital, promotion or live trading.",
                "Rows without exchange-declared base/quote mapping are excluded rather than inferred.",
                "Unknown ingestion time remains explicit and prevents this bundle from proving runtime parity.",
                "Feature CSV content and the logical feature fingerprint are re-verified before a bundle can prove shadow parity.",
            ],
        }


@dataclass(frozen=True)
class FeatureSnapshotMaterialVerification:
    """Evidence that a feature manifest still matches its feature CSV bundle."""

    manifest_path: str
    feature_snapshot_id: str
    fingerprint: str
    bundle_content_fingerprint: str
    file_count: int

    @property
    def material_verified(self) -> bool:
        return True


def build_canonical_feature_snapshot(
    config: CanonicalFeatureSnapshotConfig,
    *,
    registry: FeatureRegistry | None = None,
) -> CanonicalFeatureSnapshot:
    """Write one reproducible feature bundle from a canonical v2 manifest."""

    manifest = _load_manifest(config.canonical_manifest_path)
    holdout_partition, holdout_partition_role = _verified_partition_source(
        manifest,
        config.canonical_manifest_path,
    )
    source_snapshot_id = _required_text(manifest.get("snapshot_id"), "canonical manifest snapshot_id")
    source_fingerprint = _required_text(manifest.get("fingerprint"), "canonical manifest fingerprint")
    feature_ids = tuple(dict.fromkeys(str(item).strip() for item in config.feature_ids if str(item).strip()))
    if not feature_ids:
        raise ValueError("at least one feature id is required")
    active_registry = registry or default_feature_registry()
    for feature_id in feature_ids:
        active_registry.get(feature_id)

    # A complete canonical history may contain millions of bars.  Materialize
    # one canonical market/timeframe at a time and spool its feature CSV while
    # calculating the snapshot fingerprint.  This keeps the public research
    # collector inside its cgroup budget without changing the feature contract.
    config.output_dir.mkdir(parents=True, exist_ok=True)
    canonical_row_count = 0
    eligible_row_count = 0
    rejected_unverified_mapping_count = 0
    ingestion_time_unknown_count = 0
    parity_ok = True
    parity_sample_row_count = 0
    feature_count = 0
    ready_count = 0
    waiting_count = 0
    missing_count = 0
    digest = _feature_fingerprint_digest(
        source_snapshot_id=source_snapshot_id,
        source_fingerprint=source_fingerprint,
        registry_fingerprint=active_registry.fingerprint,
        feature_ids=feature_ids,
    )
    intermediate_files: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str, str, str, str]] = set()
    file_payloads = sorted(
        (item for item in manifest.get("files") or () if isinstance(item, Mapping)),
        key=lambda item: str(item.get("csv_path") or ""),
    )
    with tempfile.TemporaryDirectory(prefix=".autobot_features_", dir=config.output_dir) as temporary_dir:
        temporary_root = Path(temporary_dir)
        for file_index, file_payload in enumerate(file_payloads):
            csv_path = Path(str(file_payload.get("csv_path") or ""))
            if not csv_path.exists():
                raise FileNotFoundError(f"canonical file missing: {csv_path}")
            source_rows = _read_csv(csv_path)
            canonical_row_count += len(source_rows)
            eligible_rows = [
                row for row in source_rows if str(row.get("market_mapping_status") or "").upper() == "EXPLICIT"
            ]
            rejected_unverified_mapping_count += len(source_rows) - len(eligible_rows)
            if not eligible_rows:
                continue
            eligible_row_count += len(eligible_rows)
            ingestion_time_unknown_count += sum(
                not str(row.get("ingestion_time") or "").strip() for row in eligible_rows
            )
            market = _market_from_row(eligible_rows[0])
            timeframe = str(eligible_rows[0].get("timeframe") or "")
            key = (
                market.exchange,
                market.market_type,
                market.symbol,
                market.base_asset,
                market.quote_asset,
                timeframe,
            )
            if key in seen_keys:
                raise ValueError(f"canonical manifest contains duplicate market/timeframe file: {market.symbol} {timeframe}")
            seen_keys.add(key)
            rows = sorted(eligible_rows, key=lambda item: (str(item.get("available_time")), str(item.get("event_time"))))
            parity_rows = _bounded_parity_rows(rows)
            parity_sample_row_count += len(parity_rows)
            parity = validate_historical_shadow_parity(
                rows=parity_rows,
                market=market,
                timeframe=timeframe,
                source_snapshot_id=source_snapshot_id,
                registry=active_registry,
                feature_ids=feature_ids,
            )
            parity_ok = parity_ok and parity.parity_ok
            temporary_csv = temporary_root / f"{file_index:04d}_{market.symbol}_{timeframe}_features.csv"
            group_feature_count = 0
            group_ready_count = 0
            group_waiting_count = 0
            group_missing_count = 0
            with temporary_csv.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=FEATURE_CSV_FIELDS)
                writer.writeheader()
                for value in active_registry.iter_series(
                    rows=rows,
                    market=market,
                    timeframe=timeframe,
                    source_snapshot_id=source_snapshot_id,
                    feature_ids=feature_ids,
                ):
                    payload = _feature_row(contract_to_dict(value))
                    writer.writerow({field: payload.get(field, "") for field in FEATURE_CSV_FIELDS})
                    _update_feature_fingerprint(digest, payload)
                    group_feature_count += 1
                    if payload["status"] == "READY":
                        group_ready_count += 1
                    elif payload["status"] == "WAITING_FOR_MORE_DATA":
                        group_waiting_count += 1
                    else:
                        group_missing_count += 1
            feature_count += group_feature_count
            ready_count += group_ready_count
            waiting_count += group_waiting_count
            missing_count += group_missing_count
            intermediate_files.append(
                {
                    "symbol": market.symbol,
                    "timeframe": timeframe,
                    "feature_count": group_feature_count,
                    "ready_count": group_ready_count,
                    "waiting_count": group_waiting_count,
                    "missing_count": group_missing_count,
                    "temporary_csv": temporary_csv,
                }
            )

        fingerprint = digest.hexdigest()
        feature_snapshot_id = f"features_v{CANONICAL_FEATURE_SNAPSHOT_SCHEMA_VERSION}_{fingerprint[:16]}"
        snapshot_dir = config.output_dir / feature_snapshot_id
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        files: list[CanonicalFeatureFile] = []
        for item in intermediate_files:
            path = snapshot_dir / f"{item['symbol']}_{item['timeframe']}_features.csv"
            item["temporary_csv"].replace(path)
            files.append(
                CanonicalFeatureFile(
                    symbol=item["symbol"],
                    timeframe=item["timeframe"],
                    feature_count=item["feature_count"],
                    ready_count=item["ready_count"],
                    waiting_count=item["waiting_count"],
                    missing_count=item["missing_count"],
                    csv_path=str(path.resolve()),
                    content_sha256=_file_sha256(path),
                )
            )

    blockers: list[str] = []
    if not feature_count:
        blockers.append("DATA_MISSING")
    if rejected_unverified_mapping_count:
        blockers.append("UNVERIFIED_MARKET_MAPPING_ROWS_EXCLUDED")
    if ingestion_time_unknown_count:
        blockers.append("INGESTION_TIME_UNKNOWN_RUNTIME_PARITY_NOT_PROVEN")
    if not parity_ok:
        blockers.append("FEATURE_PARITY_FAILED")
    status = "READY" if feature_count and parity_ok and ingestion_time_unknown_count == 0 else "DATA_MISSING"
    bundle_content_fingerprint = _bundle_content_fingerprint(files)
    snapshot = CanonicalFeatureSnapshot(
        run_id=config.run_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        feature_snapshot_id=feature_snapshot_id,
        fingerprint=fingerprint,
        bundle_content_fingerprint=bundle_content_fingerprint,
        source_snapshot_id=source_snapshot_id,
        source_snapshot_fingerprint=source_fingerprint,
        feature_registry_fingerprint=active_registry.fingerprint,
        schema_version=CANONICAL_FEATURE_SNAPSHOT_SCHEMA_VERSION,
        feature_ids=feature_ids,
        feature_versions={feature_id: active_registry.get(feature_id).version for feature_id in feature_ids},
        canonical_row_count=canonical_row_count,
        eligible_row_count=eligible_row_count,
        rejected_unverified_mapping_count=rejected_unverified_mapping_count,
        ingestion_time_unknown_count=ingestion_time_unknown_count,
        feature_count=feature_count,
        ready_count=ready_count,
        waiting_count=waiting_count,
        missing_count=missing_count,
        parity_ok=parity_ok,
        status=status,
        blockers=tuple(blockers),
        files=tuple(files),
        parity_sample_row_count=parity_sample_row_count,
        holdout_partition=holdout_partition,
        holdout_partition_role=holdout_partition_role,
    )
    manifest_path = config.manifest_dir / f"{config.run_id}_feature_snapshot.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = snapshot.to_dict()
    payload["manifest_path"] = str(manifest_path)
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    (snapshot_dir / "manifest.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return replace(snapshot, manifest_path=str(manifest_path))


def verify_canonical_feature_snapshot_manifest(
    path: str | Path,
    *,
    registry: FeatureRegistry | None = None,
) -> FeatureSnapshotMaterialVerification:
    """Recompute canonical bundle evidence before it is consumed downstream.

    A manifest is not treated as proof by itself.  Every listed CSV must keep
    its declared byte hash and row count, the bundle root must still match, and
    the logical feature fingerprint is rebuilt from the stored feature rows.
    This stays research-only and does not import strategy, runtime or order
    modules.
    """

    manifest_path = Path(path)
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid canonical feature snapshot manifest: {manifest_path}") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("canonical feature snapshot manifest must be an object")
    if int(payload.get("schema_version") or 0) != CANONICAL_FEATURE_SNAPSHOT_SCHEMA_VERSION:
        raise ValueError("canonical feature snapshot manifest schema v2 is required for material verification")
    if str(payload.get("snapshot_kind") or "") != CANONICAL_FEATURE_SNAPSHOT_KIND:
        raise ValueError("canonical feature snapshot kind is invalid")
    if str(payload.get("bundle_content_hash_algorithm") or "") != MATERIAL_HASH_ALGORITHM:
        raise ValueError("canonical feature snapshot bundle hash algorithm is invalid")

    active_registry = registry or default_feature_registry()
    if str(payload.get("feature_registry_fingerprint") or "") != active_registry.fingerprint:
        raise ValueError("canonical feature snapshot registry fingerprint does not match the active registry")
    feature_ids = tuple(str(item).strip() for item in payload.get("feature_ids") or () if str(item).strip())
    if not feature_ids:
        raise ValueError("canonical feature snapshot feature_ids are required")
    expected_versions = {feature_id: active_registry.get(feature_id).version for feature_id in feature_ids}
    if dict(payload.get("feature_versions") or {}) != expected_versions:
        raise ValueError("canonical feature snapshot feature_versions do not match the active registry")

    raw_files = payload.get("files")
    if not isinstance(raw_files, list) or not raw_files:
        raise ValueError("canonical feature snapshot files are required")
    digest = _feature_fingerprint_digest(
        source_snapshot_id=_required_text(payload.get("source_snapshot_id"), "source_snapshot_id"),
        source_fingerprint=_required_text(payload.get("source_snapshot_fingerprint"), "source_snapshot_fingerprint"),
        registry_fingerprint=active_registry.fingerprint,
        feature_ids=feature_ids,
    )
    verified_files: list[CanonicalFeatureFile] = []
    total_feature_count = 0
    for raw_file in raw_files:
        if not isinstance(raw_file, Mapping):
            raise ValueError("canonical feature snapshot file evidence is invalid")
        csv_path = _resolve_feature_csv_path(manifest_path, raw_file.get("csv_path"))
        expected_hash = _required_text(raw_file.get("content_sha256"), "canonical feature CSV content_sha256")
        actual_hash = _file_sha256(csv_path)
        if actual_hash != expected_hash:
            raise ValueError(f"canonical feature CSV content hash mismatch: {csv_path}")
        rows = _read_csv(csv_path)
        expected_count = int(raw_file.get("feature_count") or 0)
        if expected_count <= 0 or len(rows) != expected_count:
            raise ValueError(f"canonical feature CSV row count mismatch: {csv_path}")
        if any(tuple(row) != FEATURE_CSV_FIELDS for row in rows):
            raise ValueError(f"canonical feature CSV schema mismatch: {csv_path}")
        for row in rows:
            _update_feature_fingerprint(digest, {field: row.get(field, "") for field in FEATURE_CSV_FIELDS})
        verified_files.append(
            CanonicalFeatureFile(
                symbol=_required_text(raw_file.get("symbol"), "canonical feature CSV symbol"),
                timeframe=_required_text(raw_file.get("timeframe"), "canonical feature CSV timeframe"),
                feature_count=expected_count,
                ready_count=max(0, int(raw_file.get("ready_count") or 0)),
                waiting_count=max(0, int(raw_file.get("waiting_count") or 0)),
                missing_count=max(0, int(raw_file.get("missing_count") or 0)),
                csv_path=str(csv_path),
                content_sha256=actual_hash,
            )
        )
        total_feature_count += expected_count
    if total_feature_count != int(payload.get("feature_count") or 0):
        raise ValueError("canonical feature snapshot total feature count mismatch")
    if digest.hexdigest() != _required_text(payload.get("fingerprint"), "canonical feature snapshot fingerprint"):
        raise ValueError("canonical feature snapshot logical fingerprint mismatch")
    bundle_fingerprint = _bundle_content_fingerprint(verified_files)
    if bundle_fingerprint != _required_text(payload.get("bundle_content_fingerprint"), "canonical feature bundle content fingerprint"):
        raise ValueError("canonical feature snapshot bundle content fingerprint mismatch")
    return FeatureSnapshotMaterialVerification(
        manifest_path=str(manifest_path),
        feature_snapshot_id=_required_text(payload.get("feature_snapshot_id"), "feature_snapshot_id"),
        fingerprint=str(payload["fingerprint"]),
        bundle_content_fingerprint=bundle_fingerprint,
        file_count=len(verified_files),
    )


def render_canonical_feature_snapshot_report(snapshot: CanonicalFeatureSnapshot) -> str:
    lines = [
        f"# Canonical Feature Snapshot - {snapshot.run_id}",
        "",
        f"- Feature snapshot: `{snapshot.feature_snapshot_id}`",
        f"- Source snapshot: `{snapshot.source_snapshot_id}`",
        f"- Status: `{snapshot.status}`",
        f"- Parity: `{snapshot.parity_ok}`",
        f"- Parity validation: `{snapshot.parity_validation_scope}` ({snapshot.parity_sample_row_count} sampled canonical rows)",
        f"- Canonical rows: `{snapshot.canonical_row_count}`",
        f"- Eligible explicit-mapping rows: `{snapshot.eligible_row_count}`",
        f"- Feature rows: `{snapshot.feature_count}` (ready `{snapshot.ready_count}`, waiting `{snapshot.waiting_count}`, missing `{snapshot.missing_count}`)",
        f"- Mapping rows excluded: `{snapshot.rejected_unverified_mapping_count}`",
        f"- Unknown ingestion-time rows: `{snapshot.ingestion_time_unknown_count}`",
        "",
        "## Blockers",
        "",
    ]
    lines.extend(f"- `{item}`" for item in snapshot.blockers) if snapshot.blockers else lines.append("- None")
    lines.extend(["", "## Safety", "", "- Research-only; cannot activate shadow, paper capital, promotion or live trading.", ""])
    return "\n".join(lines)


def write_canonical_feature_snapshot_report(snapshot: CanonicalFeatureSnapshot, output_dir: str | Path) -> tuple[Path, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / f"{snapshot.run_id}.json"
    markdown_path = output / f"{snapshot.run_id}.md"
    json_path.write_text(json.dumps(snapshot.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(render_canonical_feature_snapshot_report(snapshot), encoding="utf-8")
    return json_path, markdown_path


def upgrade_feature_snapshot_manifest(
    source_path: str | Path,
    output_path: str | Path,
    *,
    registry: FeatureRegistry | None = None,
) -> Path:
    """Add explicit feature versions to a legacy bundle manifest without re-running it.

    The upgrade is permitted only when the recorded registry fingerprint equals
    the active deterministic registry. The source manifest is left untouched.
    """

    source = Path(source_path)
    output = Path(output_path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid feature snapshot manifest: {source}") from exc
    if not isinstance(payload, dict):
        raise ValueError("feature snapshot manifest must be an object")
    active_registry = registry or default_feature_registry()
    if str(payload.get("feature_registry_fingerprint") or "") != active_registry.fingerprint:
        raise ValueError("legacy feature manifest registry fingerprint does not match the active registry")
    feature_ids = tuple(str(item).strip() for item in payload.get("feature_ids") or () if str(item).strip())
    if not feature_ids:
        raise ValueError("legacy feature manifest feature_ids are required")
    versions = {feature_id: active_registry.get(feature_id).version for feature_id in feature_ids}
    existing = payload.get("feature_versions")
    if isinstance(existing, Mapping) and dict(existing) != versions:
        raise ValueError("existing feature_versions conflict with the active registry")
    payload["feature_versions"] = versions
    payload["manifest_upgrade"] = {
        "kind": "feature_versions_backfill",
        "source_manifest": str(source),
        "registry_fingerprint_verified": active_registry.fingerprint,
        "bundle_values_recomputed": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return output


def _load_manifest(path: Path) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid canonical manifest: {path}") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("canonical manifest must be an object")
    if int(str(payload.get("schema_version") or "0")) < 2:
        raise ValueError("canonical manifest schema v2 is required")
    return payload


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _resolve_feature_csv_path(manifest_path: Path, value: Any) -> Path:
    raw_path = Path(_required_text(value, "canonical feature CSV path"))
    candidates = (raw_path,) if raw_path.is_absolute() else (raw_path, manifest_path.resolve().parent / raw_path)
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(f"canonical feature CSV missing: {raw_path}")


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1_048_576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _bundle_content_fingerprint(files: Sequence[CanonicalFeatureFile]) -> str:
    payload = [
        {
            "symbol": item.symbol,
            "timeframe": item.timeframe,
            "feature_count": item.feature_count,
            "content_sha256": item.content_sha256,
        }
        for item in files
    ]
    return _fingerprint({"algorithm": MATERIAL_HASH_ALGORITHM, "files": payload})


def _market_from_row(row: Mapping[str, Any]) -> MarketIdentity:
    return MarketIdentity(
        exchange=str(row.get("exchange") or ""),
        market_type=str(row.get("market_type") or ""),
        symbol=str(row.get("symbol") or ""),
        base_asset=str(row.get("base_asset") or ""),
        quote_asset=str(row.get("quote_asset") or ""),
    )


def _feature_row(payload: Mapping[str, Any]) -> dict[str, Any]:
    market = payload["market"]
    return {
        "source_snapshot_id": payload["source_snapshot_id"],
        "feature_id": payload["feature_id"],
        "feature_version": payload["feature_version"],
        "exchange": market["exchange"],
        "market_type": market["market_type"],
        "symbol": market["symbol"],
        "base_asset": market["base_asset"],
        "quote_asset": market["quote_asset"],
        "timeframe": payload["timeframe"],
        "event_time": payload["event_time"],
        "available_time": payload["available_time"],
        "value": "" if payload["value"] is None else str(payload["value"]),
        "status": str(payload["status"]),
        "metadata_json": json.dumps(payload.get("metadata") or {}, sort_keys=True, separators=(",", ":")),
    }


def _bounded_parity_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return a deterministic parity sample without weakening feature output.

    The full feature bundle is still computed and written.  Only the duplicate
    historical-vs-shadow parity replay is bounded, because replaying an entire
    multi-million-row archive twice can exhaust the isolated collection job.
    """

    normalized = [dict(row) for row in rows]
    if len(normalized) <= FEATURE_PARITY_MAX_ROWS:
        return normalized
    last_index = len(normalized) - 1
    indices = {
        round(index * last_index / (FEATURE_PARITY_MAX_ROWS - 1))
        for index in range(FEATURE_PARITY_MAX_ROWS)
    }
    return [normalized[index] for index in sorted(indices)]


def _verified_partition_source(
    manifest: Mapping[str, Any],
    manifest_path: Path,
) -> tuple[Mapping[str, Any] | None, str | None]:
    """Return partition evidence only after the role manifest and CSV root verify.

    A role-scoped canonical manifest is a security boundary: it must be the
    manifest written beside the sealed partition and its listed CSVs must still
    match the partition fingerprint.  A caller cannot merely declare matching
    snapshot ids in a feature manifest.
    """

    raw_partition = manifest.get("holdout_partition")
    if raw_partition is None:
        return None, None
    if not isinstance(raw_partition, Mapping):
        raise ValueError("canonical holdout_partition provenance must be an object")
    from .holdout_partition import (
        HOLDOUT_REVIEW_ROLE,
        OPTIMIZATION_ROLE,
        HoldoutPartitionError,
        load_holdout_partition_reference,
        verify_holdout_partition,
    )

    role = str(raw_partition.get("role") or "").strip()
    if role not in {OPTIMIZATION_ROLE, HOLDOUT_REVIEW_ROLE}:
        raise ValueError("canonical holdout_partition role is invalid")
    partition_manifest = manifest_path.resolve().parent / "partition_manifest.json"
    try:
        reference = load_holdout_partition_reference(partition_manifest)
        expected_manifest = Path(
            reference.optimization_snapshot_manifest
            if role == OPTIMIZATION_ROLE
            else reference.holdout_snapshot_manifest
        ).resolve()
        if manifest_path.resolve() != expected_manifest:
            raise ValueError("canonical partition source manifest is not the sealed role manifest")
        expected_root = Path(
            reference.optimization_data_dir if role == OPTIMIZATION_ROLE else reference.holdout_data_dir
        )
        verify_holdout_partition(partition_manifest, role=role, data_paths=(expected_root,))
    except HoldoutPartitionError as exc:
        raise ValueError(f"canonical partition source is invalid: {exc}") from exc
    expected_provenance = {
        "partition_id": reference.partition_id,
        "partition_fingerprint": reference.fingerprint,
        "role": role,
        "source_snapshot_id": reference.source_snapshot_id,
        "source_snapshot_fingerprint": reference.source_snapshot_fingerprint,
    }
    if dict(raw_partition) != expected_provenance:
        raise ValueError("canonical holdout_partition provenance does not match the sealed partition")
    return reference.identity_dict(), role


def _feature_fingerprint_digest(
    *,
    source_snapshot_id: str,
    source_fingerprint: str,
    registry_fingerprint: str,
    feature_ids: Sequence[str],
) -> Any:
    digest = sha256()
    header = {
        "source_snapshot_id": source_snapshot_id,
        "source_snapshot_fingerprint": source_fingerprint,
        "feature_registry_fingerprint": registry_fingerprint,
        "feature_ids": list(feature_ids),
        "schema_version": CANONICAL_FEATURE_SNAPSHOT_SCHEMA_VERSION,
    }
    digest.update(json.dumps(header, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    digest.update(b"\n")
    return digest


def _update_feature_fingerprint(digest: Any, payload: Mapping[str, Any]) -> None:
    digest.update(json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), default=str).encode("utf-8"))
    digest.update(b"\n")


def _write_feature_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FEATURE_CSV_FIELDS)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in FEATURE_CSV_FIELDS} for row in rows)


def _required_text(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required")
    return text


def _fingerprint(payload: Mapping[str, Any]) -> str:
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()
