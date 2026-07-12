"""Materialize point-in-time research features from canonical derivatives data.

The module is batch-only and research-only.  It reads only the canonical
Kraken Futures histories produced by the public collector and keeps the
perpetual USD market identity separate from AUTOBOT's EUR spot symbols.  It
never converts quotes implicitly and imports no runtime, router, paper or
execution module.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping, Sequence
import uuid

from autobot.v2.contracts import MarketIdentity, contract_to_dict

from .feature_registry import FeatureRegistry, default_feature_registry, validate_historical_shadow_parity


DERIVATIVES_FEATURE_SNAPSHOT_SCHEMA_VERSION = 1
DERIVATIVES_POINT_IN_TIME_KIND = "DERIVATIVES_POINT_IN_TIME"
DEFAULT_DERIVATIVES_FEATURE_IDS = (
    "funding_rate_relative",
    "basis_bps",
    "open_interest_change_24_pct",
)
FEATURE_DATASET_BY_ID = {
    "funding_rate_relative": "funding",
    "basis_bps": "basis",
    "open_interest_change_24_pct": "tickers",
}
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
class DerivativesFeatureSnapshotConfig:
    run_id: str
    derivatives_manifest_path: Path
    as_of_time: datetime
    output_dir: Path = Path("data/research/canonical/derivatives_features")
    manifest_dir: Path = Path("data/research/manifests")
    feature_ids: tuple[str, ...] = DEFAULT_DERIVATIVES_FEATURE_IDS

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id must not be empty")
        if self.as_of_time.tzinfo is None or self.as_of_time.utcoffset() is None:
            raise ValueError("as_of_time must be timezone-aware")


@dataclass(frozen=True)
class DerivativesFeatureFile:
    source_dataset: str
    futures_symbol: str
    feature_count: int
    ready_count: int
    waiting_count: int
    missing_count: int
    csv_path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DerivativesFeatureSnapshot:
    run_id: str
    generated_at: str
    feature_snapshot_id: str
    fingerprint: str
    source_snapshot_id: str
    source_snapshot_fingerprint: str
    provenance_fingerprint: str
    snapshot_kind: str
    as_of_time: str
    market_mapping_fingerprint: str
    feature_registry_fingerprint: str
    schema_version: int
    feature_ids: tuple[str, ...]
    feature_versions: Mapping[str, str]
    feature_count: int
    ready_count: int
    waiting_count: int
    missing_count: int
    parity_ok: bool
    runtime_parity_proven: bool
    status: str
    blockers: tuple[str, ...]
    files: tuple[DerivativesFeatureFile, ...]
    datasets: Mapping[str, Mapping[str, Any]]
    temporal_contract: Mapping[str, Any]
    basis_contract: Mapping[str, Any]
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
            "provenance_fingerprint": self.provenance_fingerprint,
            "snapshot_kind": self.snapshot_kind,
            "as_of_time": self.as_of_time,
            "market_mapping_fingerprint": self.market_mapping_fingerprint,
            "feature_registry_fingerprint": self.feature_registry_fingerprint,
            "schema_version": self.schema_version,
            "feature_ids": list(self.feature_ids),
            "feature_versions": dict(self.feature_versions),
            "feature_count": self.feature_count,
            "ready_count": self.ready_count,
            "waiting_count": self.waiting_count,
            "missing_count": self.missing_count,
            "parity_ok": self.parity_ok,
            "runtime_parity_proven": self.runtime_parity_proven,
            "ingestion_time_unknown_count": 0,
            "status": self.status,
            "blockers": list(self.blockers),
            "files": [item.to_dict() for item in self.files],
            "datasets": {key: dict(value) for key, value in self.datasets.items()},
            "temporal_contract": dict(self.temporal_contract),
            "basis_contract": dict(self.basis_contract),
            "manifest_path": self.manifest_path,
            "paper_capital_allowed": False,
            "live_allowed": False,
            "promotable": False,
            "safety_notes": [
                "Research-only derivatives feature materialization.",
                "No quote-currency conversion, order path, shadow activation, paper capital, promotion or live trading.",
                "Backfilled derivatives rows remain explicit and cannot prove runtime parity.",
            ],
        }


def build_derivatives_feature_snapshot(
    config: DerivativesFeatureSnapshotConfig,
    *,
    registry: FeatureRegistry | None = None,
) -> DerivativesFeatureSnapshot:
    """Create one reproducible feature bundle from a derivatives manifest."""

    manifest = _load_derivatives_manifest(config.derivatives_manifest_path)
    feature_ids = tuple(dict.fromkeys(str(item).strip() for item in config.feature_ids if str(item).strip()))
    if not feature_ids:
        raise ValueError("at least one derivatives feature id is required")
    if any(feature_id not in FEATURE_DATASET_BY_ID for feature_id in feature_ids):
        unknown = sorted(set(feature_ids) - set(FEATURE_DATASET_BY_ID))
        raise ValueError(f"unsupported derivatives feature ids: {', '.join(unknown)}")
    active_registry = registry or default_feature_registry()
    for feature_id in feature_ids:
        active_registry.get(feature_id)

    as_of_time = _utc(config.as_of_time)
    dataset_paths = _history_paths(manifest)
    raw_source_rows = {dataset: _read_csv(path) for dataset, path in dataset_paths.items()}
    source_rows, future_rows_excluded, invalid_temporal_rows = _point_in_time_rows(raw_source_rows, as_of_time)
    mappings = _validated_market_mappings(manifest)
    source_rows, mapping_rows_excluded = _filter_rows_by_mapping(source_rows, mappings)
    invalid_basis_rows = sum(
        1
        for row in source_rows["basis"]
        if str(row.get("confidence_status") or "") != "MARK_INDEX_SAME_QUOTE"
    )
    source_rows["basis"] = [
        row for row in source_rows["basis"] if str(row.get("confidence_status") or "") == "MARK_INDEX_SAME_QUOTE"
    ]
    market_mapping_fingerprint = _fingerprint({"mappings": mappings})
    source_snapshot_fingerprint = _fingerprint(
        {
            "as_of_time": as_of_time.isoformat(),
            "market_mapping_fingerprint": market_mapping_fingerprint,
            "rows": {dataset: rows for dataset, rows in sorted(source_rows.items())},
        }
    )
    source_snapshot_id = f"derivatives_v{DERIVATIVES_FEATURE_SNAPSHOT_SCHEMA_VERSION}_{source_snapshot_fingerprint[:16]}"

    payloads_by_group: dict[tuple[str, str], list[dict[str, Any]]] = {}
    files: list[DerivativesFeatureFile] = []
    parity_ok = True
    runtime_parity_proven = _runtime_parity_proven(source_rows)
    for feature_id in feature_ids:
        dataset = FEATURE_DATASET_BY_ID[feature_id]
        grouped = _group_rows(source_rows[dataset])
        for futures_symbol, rows in sorted(grouped.items()):
            market = _market_from_derivatives_rows(futures_symbol, rows)
            parity = validate_historical_shadow_parity(
                rows=rows,
                market=market,
                timeframe=_timeframe_for_dataset(dataset),
                source_snapshot_id=source_snapshot_id,
                registry=active_registry,
                feature_ids=(feature_id,),
            )
            parity_ok = parity_ok and parity.parity_ok
            values = active_registry.compute_series(
                rows=rows,
                market=market,
                timeframe=_timeframe_for_dataset(dataset),
                source_snapshot_id=source_snapshot_id,
                feature_ids=(feature_id,),
            )
            payloads_by_group.setdefault((dataset, futures_symbol), []).extend(_feature_row(contract_to_dict(value)) for value in values)

    output_rows = [row for _key, rows in sorted(payloads_by_group.items()) for row in rows]
    fingerprint = _fingerprint(
        {
            "source_snapshot_id": source_snapshot_id,
            "source_snapshot_fingerprint": source_snapshot_fingerprint,
            "feature_registry_fingerprint": active_registry.fingerprint,
            "feature_ids": feature_ids,
            "rows": output_rows,
        }
    )
    feature_snapshot_id = f"derivatives_features_v{DERIVATIVES_FEATURE_SNAPSHOT_SCHEMA_VERSION}_{fingerprint[:16]}"
    snapshot_dir = config.output_dir / feature_snapshot_id
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    for (dataset, futures_symbol), payloads in sorted(payloads_by_group.items()):
        path = snapshot_dir / f"{dataset}_{futures_symbol}_features.csv"
        _write_feature_csv(path, payloads)
        files.append(
            DerivativesFeatureFile(
                source_dataset=dataset,
                futures_symbol=futures_symbol,
                feature_count=len(payloads),
                ready_count=sum(item["status"] == "READY" for item in payloads),
                waiting_count=sum(item["status"] == "WAITING_FOR_MORE_DATA" for item in payloads),
                missing_count=sum(item["status"] == "DATA_MISSING" for item in payloads),
                csv_path=str(path),
            )
        )

    blockers = _blockers(
        manifest,
        output_rows,
        feature_ids=feature_ids,
        parity_ok=parity_ok,
        runtime_parity_proven=runtime_parity_proven,
        invalid_basis_rows=invalid_basis_rows,
    )
    status = _snapshot_status(manifest, output_rows, feature_ids=feature_ids, parity_ok=parity_ok)
    provenance_fingerprint = _fingerprint(
        {
            "collector_snapshot_id": manifest.get("snapshot_id"),
            "collector_fingerprint": manifest.get("fingerprint"),
            "source_snapshot_fingerprint": source_snapshot_fingerprint,
            "market_mapping_fingerprint": market_mapping_fingerprint,
            "as_of_time": as_of_time.isoformat(),
        }
    )
    snapshot = DerivativesFeatureSnapshot(
        run_id=config.run_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        feature_snapshot_id=feature_snapshot_id,
        fingerprint=fingerprint,
        source_snapshot_id=source_snapshot_id,
        source_snapshot_fingerprint=source_snapshot_fingerprint,
        provenance_fingerprint=provenance_fingerprint,
        snapshot_kind=DERIVATIVES_POINT_IN_TIME_KIND,
        as_of_time=as_of_time.isoformat(),
        market_mapping_fingerprint=market_mapping_fingerprint,
        feature_registry_fingerprint=active_registry.fingerprint,
        schema_version=DERIVATIVES_FEATURE_SNAPSHOT_SCHEMA_VERSION,
        feature_ids=feature_ids,
        feature_versions={feature_id: active_registry.get(feature_id).version for feature_id in feature_ids},
        feature_count=len(output_rows),
        ready_count=sum(item["status"] == "READY" for item in output_rows),
        waiting_count=sum(item["status"] == "WAITING_FOR_MORE_DATA" for item in output_rows),
        missing_count=sum(item["status"] == "DATA_MISSING" for item in output_rows),
        parity_ok=parity_ok,
        runtime_parity_proven=runtime_parity_proven,
        status=status,
        blockers=tuple(blockers),
        files=tuple(files),
        datasets=_dataset_summaries(dataset_paths, source_rows),
        temporal_contract={
            "event_time": "market event timestamp",
            "available_time": "earliest timestamp allowed for feature use",
            "ingestion_time": "AUTOBOT collection timestamp",
            "as_of_time": as_of_time.isoformat(),
            "future_rows_excluded": future_rows_excluded,
            "invalid_temporal_rows_excluded": invalid_temporal_rows,
            "market_mapping_rows_excluded": mapping_rows_excluded,
            "runtime_parity_proven": runtime_parity_proven,
        },
        basis_contract={
            "calculation_method": "mark_over_index_same_quote",
            "same_quote_required": True,
            "accepted_confidence_status": "MARK_INDEX_SAME_QUOTE",
            "invalid_or_unverified_rows_excluded": invalid_basis_rows,
            "implicit_usd_eur_conversion_allowed": False,
        },
    )
    manifest_path = config.manifest_dir / f"{config.run_id}_derivatives_feature_snapshot.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = snapshot.to_dict()
    payload["manifest_path"] = str(manifest_path)
    _write_json_atomic(manifest_path, payload)
    _write_json_atomic(snapshot_dir / "manifest.json", payload)
    return replace(snapshot, manifest_path=str(manifest_path))


def render_derivatives_feature_snapshot_report(snapshot: DerivativesFeatureSnapshot) -> str:
    lines = [
        f"# Derivatives Feature Snapshot - {snapshot.run_id}",
        "",
        f"- Feature snapshot: `{snapshot.feature_snapshot_id}`",
        f"- Snapshot kind: `{snapshot.snapshot_kind}`",
        f"- As of: `{snapshot.as_of_time}`",
        f"- Status: `{snapshot.status}`",
        f"- Deterministic parity: `{snapshot.parity_ok}`",
        f"- Runtime parity proven: `{snapshot.runtime_parity_proven}`",
        f"- Feature rows: `{snapshot.feature_count}` (ready `{snapshot.ready_count}`, waiting `{snapshot.waiting_count}`, missing `{snapshot.missing_count}`)",
        "",
        "## Blockers",
        "",
    ]
    lines.extend(f"- `{blocker}`" for blocker in snapshot.blockers) if snapshot.blockers else lines.append("- None")
    lines.extend(["", "## Safety", "", "- Research-only; no paper capital, promotion or live trading.", "- Perpetual USD markets are never implicitly converted to EUR spot markets.", ""])
    return "\n".join(lines)


def write_derivatives_feature_snapshot_report(snapshot: DerivativesFeatureSnapshot, output_dir: str | Path) -> tuple[Path, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / f"{snapshot.run_id}.json"
    markdown_path = output / f"{snapshot.run_id}.md"
    _write_json_atomic(json_path, snapshot.to_dict())
    markdown_path.write_text(render_derivatives_feature_snapshot_report(snapshot), encoding="utf-8")
    return json_path, markdown_path


def _load_derivatives_manifest(path: Path) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid derivatives manifest: {path}") from exc
    if not isinstance(payload, Mapping) or int(payload.get("schema_version") or 0) < 2:
        raise ValueError("derivatives collector manifest schema v2 is required")
    return payload


def _history_paths(manifest: Mapping[str, Any]) -> dict[str, Path]:
    required = {
        "funding": "funding_history_path",
        "basis": "basis_history_path",
        "tickers": "open_interest_history_path",
    }
    paths: dict[str, Path] = {}
    for dataset, key in required.items():
        path = Path(str(manifest.get(key) or ""))
        if not path.exists():
            raise FileNotFoundError(f"derivatives history path missing for {dataset}: {path}")
        paths[dataset] = path
    return paths


def _validated_market_mappings(manifest: Mapping[str, Any]) -> tuple[dict[str, str], ...]:
    mappings: list[dict[str, str]] = []
    for item in manifest.get("mappings") or ():
        if not isinstance(item, Mapping):
            continue
        futures_symbol = str(item.get("futures_symbol") or "").strip()
        base_asset = str(item.get("base_asset") or "").strip()
        quote_asset = str(item.get("quote_asset") or "").strip()
        if not futures_symbol or not base_asset or not quote_asset:
            raise ValueError("derivatives manifest contains an incomplete market mapping")
        mappings.append(
            {
                "futures_symbol": futures_symbol,
                "base_asset": base_asset,
                "quote_asset": quote_asset,
                "autobot_spot_symbol": str(item.get("autobot_spot_symbol") or ""),
            }
        )
    if not mappings:
        raise ValueError("derivatives manifest must contain explicit market mappings")
    return tuple(sorted(mappings, key=lambda item: item["futures_symbol"]))


def _point_in_time_rows(
    datasets: Mapping[str, Sequence[Mapping[str, Any]]],
    as_of_time: datetime,
) -> tuple[dict[str, list[dict[str, Any]]], int, int]:
    accepted: dict[str, list[dict[str, Any]]] = {}
    future_rows_excluded = 0
    invalid_temporal_rows = 0
    for dataset, rows in datasets.items():
        accepted_rows: list[dict[str, Any]] = []
        for row in rows:
            event_time = _row_time(row, "event_time")
            available_time = _row_time(row, "available_time")
            ingestion_time = _row_time(row, "ingestion_time")
            if event_time is None or available_time is None or ingestion_time is None or available_time < event_time:
                invalid_temporal_rows += 1
                continue
            if event_time > as_of_time or available_time > as_of_time:
                future_rows_excluded += 1
                continue
            accepted_rows.append(
                {
                    **dict(row),
                    "event_time": event_time.isoformat(),
                    "available_time": available_time.isoformat(),
                    "ingestion_time": ingestion_time.isoformat(),
                }
            )
        accepted[dataset] = accepted_rows
    return accepted, future_rows_excluded, invalid_temporal_rows


def _filter_rows_by_mapping(
    datasets: Mapping[str, Sequence[Mapping[str, Any]]],
    mappings: Sequence[Mapping[str, str]],
) -> tuple[dict[str, list[dict[str, Any]]], int]:
    expected = {
        item["futures_symbol"]: (item["base_asset"], item["quote_asset"])
        for item in mappings
    }
    accepted: dict[str, list[dict[str, Any]]] = {}
    excluded = 0
    for dataset, rows in datasets.items():
        accepted_rows: list[dict[str, Any]] = []
        for row in rows:
            symbol = str(row.get("futures_symbol") or "")
            base_quote = expected.get(symbol)
            if base_quote is None:
                excluded += 1
                continue
            expected_base, expected_quote = base_quote
            recorded_base = str(row.get("base_asset") or "")
            recorded_quote = str(row.get("quote_asset") or "")
            if (recorded_base and recorded_base != expected_base) or (recorded_quote and recorded_quote != expected_quote):
                excluded += 1
                continue
            # Historical funding exports from the first collector schema did
            # not persist quote_asset.  The source manifest's explicit
            # contract mapping may safely complete that missing metadata; it
            # never converts a price or guesses a different market.
            accepted_rows.append(
                {
                    **dict(row),
                    "base_asset": recorded_base or expected_base,
                    "quote_asset": recorded_quote or expected_quote,
                }
            )
        accepted[dataset] = accepted_rows
    return accepted, excluded


def _dataset_summaries(
    paths: Mapping[str, Path],
    datasets: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, dict[str, Any]]:
    return {
        dataset: {
            "path": str(paths[dataset]),
            "row_count": len(rows),
            "start_at": _min_timestamp(rows),
            "end_at": _max_timestamp(rows),
            "fingerprint": _fingerprint({"dataset": dataset, "rows": rows}),
        }
        for dataset, rows in sorted(datasets.items())
    }


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle) if row.get("timestamp")]


def _group_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        symbol = str(row.get("futures_symbol") or "").strip()
        if not symbol:
            continue
        grouped.setdefault(symbol, []).append(dict(row))
    return {
        symbol: sorted(values, key=lambda item: (str(item.get("available_time") or ""), str(item.get("event_time") or "")))
        for symbol, values in grouped.items()
    }


def _market_from_derivatives_rows(futures_symbol: str, rows: Sequence[Mapping[str, Any]]) -> MarketIdentity:
    first = rows[0] if rows else {}
    exchange = str(first.get("exchange") or "").strip()
    base_asset = str(first.get("base_asset") or "").strip()
    quote_asset = str(first.get("quote_asset") or "").strip()
    if not exchange or not base_asset or not quote_asset:
        raise ValueError(f"incomplete derivatives market mapping for {futures_symbol}")
    return MarketIdentity(
        exchange=exchange,
        market_type="perpetual",
        symbol=futures_symbol,
        base_asset=base_asset,
        quote_asset=quote_asset,
    )


def _timeframe_for_dataset(dataset: str) -> str:
    return "funding_interval" if dataset == "funding" else "snapshot"


def _row_time(row: Mapping[str, Any], key: str) -> datetime | None:
    value = row.get(key) or row.get("timestamp")
    if not value:
        return None
    try:
        return _utc(datetime.fromisoformat(str(value).replace("Z", "+00:00")))
    except ValueError:
        return None


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc).replace(microsecond=0)


def _min_timestamp(rows: Sequence[Mapping[str, Any]]) -> str | None:
    values = [str(row.get("event_time") or row.get("timestamp")) for row in rows if row.get("event_time") or row.get("timestamp")]
    return min(values) if values else None


def _max_timestamp(rows: Sequence[Mapping[str, Any]]) -> str | None:
    values = [str(row.get("event_time") or row.get("timestamp")) for row in rows if row.get("event_time") or row.get("timestamp")]
    return max(values) if values else None


def _runtime_parity_proven(source_rows: Mapping[str, Sequence[Mapping[str, Any]]]) -> bool:
    for rows in source_rows.values():
        for row in rows:
            if not str(row.get("ingestion_time") or "").strip():
                return False
            if str(row.get("temporal_status") or "") == "HISTORICAL_BACKFILL_AVAILABLE_AT_INGESTION":
                return False
    return True


def _blockers(
    manifest: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    *,
    feature_ids: Sequence[str],
    parity_ok: bool,
    runtime_parity_proven: bool,
    invalid_basis_rows: int,
) -> list[str]:
    blockers: list[str] = []
    if not rows:
        blockers.append("DATA_MISSING")
    present_feature_ids = {str(item.get("feature_id") or "") for item in rows}
    if not set(feature_ids).issubset(present_feature_ids):
        blockers.append("FEATURE_DATA_MISSING")
    if "funding_rate_relative" in feature_ids and not bool(manifest.get("funding_history_ready")):
        blockers.append("FUNDING_HISTORY_MISSING")
    if "basis_bps" in feature_ids and not bool(manifest.get("basis_history_ready")):
        blockers.append("BASIS_HISTORY_WAITING")
    if "open_interest_change_24_pct" in feature_ids and not bool(manifest.get("open_interest_history_ready")):
        blockers.append("OPEN_INTEREST_HISTORY_WAITING")
    if any(item.get("status") == "DATA_MISSING" for item in rows):
        blockers.append("FEATURE_DATA_MISSING")
    if invalid_basis_rows:
        blockers.append("BASIS_UNVERIFIED_ROWS_EXCLUDED")
    if not parity_ok:
        blockers.append("FEATURE_PARITY_FAILED")
    if not runtime_parity_proven:
        blockers.append("DERIVATIVES_RUNTIME_PARITY_NOT_PROVEN")
    return blockers


def _snapshot_status(
    manifest: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    *,
    feature_ids: Sequence[str],
    parity_ok: bool,
) -> str:
    if not rows or not parity_ok or any(item.get("status") == "DATA_MISSING" for item in rows):
        return "DATA_MISSING"
    present_feature_ids = {str(item.get("feature_id") or "") for item in rows}
    if not set(feature_ids).issubset(present_feature_ids):
        return "DATA_MISSING"
    waiting_for_history = (
        ("funding_rate_relative" in feature_ids and not bool(manifest.get("funding_history_ready")))
        or ("basis_bps" in feature_ids and not bool(manifest.get("basis_history_ready")))
        or ("open_interest_change_24_pct" in feature_ids and not bool(manifest.get("open_interest_history_ready")))
    )
    if waiting_for_history:
        return "WAITING_FOR_MORE_DATA"
    return "READY"


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
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FEATURE_CSV_FIELDS)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in FEATURE_CSV_FIELDS} for row in rows)
    temporary.replace(path)


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def _fingerprint(payload: Mapping[str, Any]) -> str:
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()
