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
from typing import Any, Mapping, Sequence

from autobot.v2.contracts import MarketIdentity, contract_to_dict

from .feature_registry import FeatureRegistry, default_feature_registry, validate_historical_shadow_parity


CANONICAL_FEATURE_SNAPSHOT_SCHEMA_VERSION = 1
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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CanonicalFeatureSnapshot:
    run_id: str
    generated_at: str
    feature_snapshot_id: str
    fingerprint: str
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
            ],
        }


def build_canonical_feature_snapshot(
    config: CanonicalFeatureSnapshotConfig,
    *,
    registry: FeatureRegistry | None = None,
) -> CanonicalFeatureSnapshot:
    """Write one reproducible feature bundle from a canonical v2 manifest."""

    manifest = _load_manifest(config.canonical_manifest_path)
    source_snapshot_id = _required_text(manifest.get("snapshot_id"), "canonical manifest snapshot_id")
    source_fingerprint = _required_text(manifest.get("fingerprint"), "canonical manifest fingerprint")
    feature_ids = tuple(dict.fromkeys(str(item).strip() for item in config.feature_ids if str(item).strip()))
    if not feature_ids:
        raise ValueError("at least one feature id is required")
    active_registry = registry or default_feature_registry()
    for feature_id in feature_ids:
        active_registry.get(feature_id)

    canonical_rows: list[dict[str, Any]] = []
    eligible_groups: dict[tuple[str, str, str, str, str, str], list[dict[str, Any]]] = {}
    rejected_unverified_mapping_count = 0
    ingestion_time_unknown_count = 0
    for file_payload in manifest.get("files") or []:
        if not isinstance(file_payload, Mapping):
            continue
        csv_path = Path(str(file_payload.get("csv_path") or ""))
        if not csv_path.exists():
            raise FileNotFoundError(f"canonical file missing: {csv_path}")
        for row in _read_csv(csv_path):
            canonical_rows.append(row)
            if str(row.get("market_mapping_status") or "").upper() != "EXPLICIT":
                rejected_unverified_mapping_count += 1
                continue
            if not str(row.get("ingestion_time") or "").strip():
                ingestion_time_unknown_count += 1
            market = _market_from_row(row)
            key = (
                market.exchange,
                market.market_type,
                market.symbol,
                market.base_asset,
                market.quote_asset,
                str(row.get("timeframe") or ""),
            )
            eligible_groups.setdefault(key, []).append(row)

    group_payloads: list[tuple[tuple[str, str, str, str, str, str], list[dict[str, Any]], list[dict[str, Any]]]] = []
    parity_ok = True
    for key in sorted(eligible_groups):
        exchange, market_type, symbol, base_asset, quote_asset, timeframe = key
        market = MarketIdentity(
            exchange=exchange,
            market_type=market_type,
            symbol=symbol,
            base_asset=base_asset,
            quote_asset=quote_asset,
        )
        rows = sorted(eligible_groups[key], key=lambda item: (str(item.get("available_time")), str(item.get("event_time"))))
        parity = validate_historical_shadow_parity(
            rows=rows,
            market=market,
            timeframe=timeframe,
            source_snapshot_id=source_snapshot_id,
            registry=active_registry,
            feature_ids=feature_ids,
        )
        parity_ok = parity_ok and parity.parity_ok
        values = active_registry.compute_series(
            rows=rows,
            market=market,
            timeframe=timeframe,
            source_snapshot_id=source_snapshot_id,
            feature_ids=feature_ids,
        )
        payloads = [_feature_row(contract_to_dict(value)) for value in values]
        group_payloads.append((key, rows, payloads))

    all_rows = [payload for _, _, payloads in group_payloads for payload in payloads]
    fingerprint = _fingerprint(
        {
            "source_snapshot_id": source_snapshot_id,
            "source_snapshot_fingerprint": source_fingerprint,
            "feature_registry_fingerprint": active_registry.fingerprint,
            "feature_ids": feature_ids,
            "rows": all_rows,
        }
    )
    feature_snapshot_id = f"features_v{CANONICAL_FEATURE_SNAPSHOT_SCHEMA_VERSION}_{fingerprint[:16]}"
    snapshot_dir = config.output_dir / feature_snapshot_id
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    files: list[CanonicalFeatureFile] = []
    for key, _, payloads in group_payloads:
        _, _, symbol, _, _, timeframe = key
        path = snapshot_dir / f"{symbol}_{timeframe}_features.csv"
        _write_feature_csv(path, payloads)
        files.append(
            CanonicalFeatureFile(
                symbol=symbol,
                timeframe=timeframe,
                feature_count=len(payloads),
                ready_count=sum(item["status"] == "READY" for item in payloads),
                waiting_count=sum(item["status"] == "WAITING_FOR_MORE_DATA" for item in payloads),
                missing_count=sum(item["status"] == "DATA_MISSING" for item in payloads),
                csv_path=str(path),
            )
        )

    blockers: list[str] = []
    if not all_rows:
        blockers.append("DATA_MISSING")
    if rejected_unverified_mapping_count:
        blockers.append("UNVERIFIED_MARKET_MAPPING_ROWS_EXCLUDED")
    if ingestion_time_unknown_count:
        blockers.append("INGESTION_TIME_UNKNOWN_RUNTIME_PARITY_NOT_PROVEN")
    if not parity_ok:
        blockers.append("FEATURE_PARITY_FAILED")
    status = "READY" if all_rows and parity_ok and ingestion_time_unknown_count == 0 else "DATA_MISSING"
    snapshot = CanonicalFeatureSnapshot(
        run_id=config.run_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        feature_snapshot_id=feature_snapshot_id,
        fingerprint=fingerprint,
        source_snapshot_id=source_snapshot_id,
        source_snapshot_fingerprint=source_fingerprint,
        feature_registry_fingerprint=active_registry.fingerprint,
        schema_version=CANONICAL_FEATURE_SNAPSHOT_SCHEMA_VERSION,
        feature_ids=feature_ids,
        feature_versions={feature_id: active_registry.get(feature_id).version for feature_id in feature_ids},
        canonical_row_count=len(canonical_rows),
        eligible_row_count=sum(len(rows) for rows in eligible_groups.values()),
        rejected_unverified_mapping_count=rejected_unverified_mapping_count,
        ingestion_time_unknown_count=ingestion_time_unknown_count,
        feature_count=len(all_rows),
        ready_count=sum(item["status"] == "READY" for item in all_rows),
        waiting_count=sum(item["status"] == "WAITING_FOR_MORE_DATA" for item in all_rows),
        missing_count=sum(item["status"] == "DATA_MISSING" for item in all_rows),
        parity_ok=parity_ok,
        status=status,
        blockers=tuple(blockers),
        files=tuple(files),
    )
    manifest_path = config.manifest_dir / f"{config.run_id}_feature_snapshot.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = snapshot.to_dict()
    payload["manifest_path"] = str(manifest_path)
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    (snapshot_dir / "manifest.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return replace(snapshot, manifest_path=str(manifest_path))


def render_canonical_feature_snapshot_report(snapshot: CanonicalFeatureSnapshot) -> str:
    lines = [
        f"# Canonical Feature Snapshot - {snapshot.run_id}",
        "",
        f"- Feature snapshot: `{snapshot.feature_snapshot_id}`",
        f"- Source snapshot: `{snapshot.source_snapshot_id}`",
        f"- Status: `{snapshot.status}`",
        f"- Parity: `{snapshot.parity_ok}`",
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
