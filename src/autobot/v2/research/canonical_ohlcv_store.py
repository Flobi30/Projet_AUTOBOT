"""Canonical research OHLCV store for AUTOBOT.

This module is research-only. It reads existing raw OHLCV exports, normalizes
symbols and timestamps, writes deterministic canonical CSV snapshots and
manifests, and never imports or calls runtime trading paths.
"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .market_data_repository import MarketBar
from .symbol_normalization import normalize_research_symbol


TIMEFRAME_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14_400,
    "1d": 86_400,
}

CANONICAL_OHLCV_SCHEMA_VERSION = 2


CANONICAL_FIELDNAMES = (
    "schema_version",
    "exchange",
    "market_type",
    "symbol",
    "base_asset",
    "quote_asset",
    "market_mapping_status",
    "timeframe",
    "event_time",
    "available_time",
    "ingestion_time",
    "bar_close_time",
    "source_timestamp_role",
    "availability_basis",
    "temporal_status",
    "open_timestamp",
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "source_path",
    "source_row_number",
)


@dataclass(frozen=True)
class CanonicalOHLCVConfig:
    run_id: str
    raw_paths: tuple[Path, ...]
    output_dir: Path = Path("data/research/canonical/ohlcv")
    manifest_dir: Path = Path("data/research/manifests")
    quarantine_dir: Path = Path("data/research/quarantine")
    exchange: str = "kraken"
    market_type: str = "spot"
    market_mappings: Mapping[str, Mapping[str, str]] | None = None
    max_files: int | None = None
    max_rows: int | None = None


@dataclass(frozen=True)
class CanonicalOHLCVFile:
    exchange: str
    market_type: str
    symbol: str
    timeframe: str
    row_count: int
    duplicate_count: int
    gap_count: int
    start_at: str | None
    end_at: str | None
    csv_path: str
    source_paths: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["source_paths"] = list(self.source_paths)
        return payload


@dataclass(frozen=True)
class CanonicalOHLCVSnapshot:
    run_id: str
    generated_at: str
    snapshot_id: str
    fingerprint: str
    exchange: str
    market_type: str
    raw_file_count: int
    raw_row_count: int
    canonical_row_count: int
    duplicate_count: int
    gap_count: int
    quarantine_count: int
    storage_size_bytes: int
    start_at: str | None
    end_at: str | None
    symbols: tuple[str, ...]
    timeframes: tuple[str, ...]
    files: tuple[CanonicalOHLCVFile, ...]
    schema_version: int = CANONICAL_OHLCV_SCHEMA_VERSION
    available_start_at: str | None = None
    available_end_at: str | None = None
    manifest_path: str | None = None
    quarantine_manifest_path: str | None = None
    backfill_status: str = "snapshot_from_existing_raw"
    new_data_significance: str = "first_canonical_snapshot_or_uncompared"
    paper_capital_allowed: bool = False
    live_allowed: bool = False
    promotable: bool = False
    safety_notes: tuple[str, ...] = (
        "Research-only canonical OHLCV snapshot.",
        "No live trading, paper capital, promotion, shadow activation, runtime order path, sizing, leverage, UI, or orders.",
        "Raw data is preserved; canonical rows keep source provenance.",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "snapshot_id": self.snapshot_id,
            "fingerprint": self.fingerprint,
            "schema_version": self.schema_version,
            "exchange": self.exchange,
            "market_type": self.market_type,
            "raw_file_count": self.raw_file_count,
            "raw_row_count": self.raw_row_count,
            "canonical_row_count": self.canonical_row_count,
            "duplicate_count": self.duplicate_count,
            "gap_count": self.gap_count,
            "quarantine_count": self.quarantine_count,
            "storage_size_bytes": self.storage_size_bytes,
            "start_at": self.start_at,
            "end_at": self.end_at,
            "available_start_at": self.available_start_at,
            "available_end_at": self.available_end_at,
            "symbols": list(self.symbols),
            "timeframes": list(self.timeframes),
            "files": [item.to_dict() for item in self.files],
            "manifest_path": self.manifest_path,
            "quarantine_manifest_path": self.quarantine_manifest_path,
            "backfill_status": self.backfill_status,
            "new_data_significance": self.new_data_significance,
            "paper_capital_allowed": self.paper_capital_allowed,
            "live_allowed": self.live_allowed,
            "promotable": self.promotable,
            "safety_notes": list(self.safety_notes),
        }


def build_canonical_ohlcv_snapshot(config: CanonicalOHLCVConfig) -> CanonicalOHLCVSnapshot:
    """Build and write one deterministic canonical OHLCV snapshot."""

    raw_files = _iter_raw_ohlcv_files(config.raw_paths)
    if config.max_files is not None:
        raw_files = raw_files[: max(0, config.max_files)]

    raw_rows = 0
    quarantine: list[dict[str, Any]] = []
    by_key: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    duplicate_count = 0

    for path in raw_files:
        for row_number, row in _read_csv_rows(path):
            if config.max_rows is not None and raw_rows >= config.max_rows:
                break
            raw_rows += 1
            try:
                canonical = _canonical_row(
                    row,
                    path=path,
                    row_number=row_number,
                    exchange=config.exchange,
                    market_type=config.market_type,
                    market_mappings=config.market_mappings or {},
                )
            except ValueError as exc:
                quarantine.append(
                    {
                        "path": str(path),
                        "row_number": row_number,
                        "reason": str(exc),
                    }
                )
                continue
            key = (
                canonical["exchange"],
                canonical["market_type"],
                canonical["symbol"],
                canonical["timeframe"],
                canonical["open_timestamp"],
            )
            if key in by_key:
                duplicate_count += 1
                winner = _deterministic_winner(by_key[key], canonical)
                by_key[key] = winner
            else:
                by_key[key] = canonical
        if config.max_rows is not None and raw_rows >= config.max_rows:
            break

    rows = sorted(by_key.values(), key=lambda item: _sort_key(item))
    fingerprint = fingerprint_canonical_rows(rows)
    snapshot_id = f"ohlcv_v{CANONICAL_OHLCV_SCHEMA_VERSION}_{fingerprint[:16]}"
    snapshot_dir = config.output_dir / snapshot_id
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    files: list[CanonicalOHLCVFile] = []
    storage_size = 0
    gap_count = 0
    for (symbol, timeframe), group in _group_by_symbol_timeframe(rows).items():
        output_path = snapshot_dir / f"{config.exchange}_{config.market_type}_{symbol}_{timeframe}.csv"
        _write_canonical_csv(group, output_path)
        storage_size += output_path.stat().st_size
        group_gaps = _gap_count(group, timeframe)
        gap_count += group_gaps
        files.append(
            CanonicalOHLCVFile(
                exchange=config.exchange,
                market_type=config.market_type,
                symbol=symbol,
                timeframe=timeframe,
                row_count=len(group),
                duplicate_count=0,
                gap_count=group_gaps,
                start_at=group[0]["open_timestamp"] if group else None,
                end_at=group[-1]["open_timestamp"] if group else None,
                csv_path=str(output_path),
                source_paths=tuple(sorted({item["source_path"] for item in group})),
            )
        )

    quarantine_manifest_path = None
    if quarantine:
        config.quarantine_dir.mkdir(parents=True, exist_ok=True)
        quarantine_path = config.quarantine_dir / f"{config.run_id}_quarantine.json"
        quarantine_path.write_text(json.dumps(quarantine, indent=2, sort_keys=True), encoding="utf-8")
        quarantine_manifest_path = str(quarantine_path)

    latest_previous = load_latest_canonical_snapshot_manifest(config.manifest_dir)
    start_at = min((item["open_timestamp"] for item in rows), default=None)
    end_at = max((item["open_timestamp"] for item in rows), default=None)
    available_start_at = min((item["available_time"] for item in rows), default=None)
    available_end_at = max((item["available_time"] for item in rows), default=None)
    snapshot = CanonicalOHLCVSnapshot(
        run_id=config.run_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        snapshot_id=snapshot_id,
        fingerprint=fingerprint,
        exchange=config.exchange,
        market_type=config.market_type,
        raw_file_count=len(raw_files),
        raw_row_count=raw_rows,
        canonical_row_count=len(rows),
        duplicate_count=duplicate_count,
        gap_count=gap_count,
        quarantine_count=len(quarantine),
        storage_size_bytes=storage_size,
        start_at=start_at,
        end_at=end_at,
        symbols=tuple(sorted({item["symbol"] for item in rows})),
        timeframes=tuple(sorted({item["timeframe"] for item in rows})),
        files=tuple(sorted(files, key=lambda item: (item.symbol, item.timeframe))),
        available_start_at=available_start_at,
        available_end_at=available_end_at,
        quarantine_manifest_path=quarantine_manifest_path,
        new_data_significance=classify_snapshot_significance(latest_previous, None),
    )
    snapshot = _with_manifest_paths(snapshot, config.manifest_dir, snapshot_dir)
    if latest_previous:
        snapshot = _replace_significance(snapshot, classify_snapshot_significance(latest_previous, snapshot.to_dict()))
    _write_snapshot_manifest(snapshot, config.manifest_dir, snapshot_dir)
    return snapshot


def adapt_legacy_canonical_row(
    row: Mapping[str, Any],
    *,
    market_mappings: Mapping[str, Mapping[str, str]] | None = None,
    recorded_ingestion_time: datetime | None = None,
) -> dict[str, Any]:
    """Adapt one v1 canonical row to v2 without mutating its source file.

    Legacy files did not record actual row ingestion time.  The adapter keeps
    that fact explicit unless a separately persisted ingestion time is supplied.
    """

    if int(str(row.get("schema_version") or "1")) >= CANONICAL_OHLCV_SCHEMA_VERSION and row.get("event_time"):
        return dict(row)
    path = Path(str(row.get("source_path") or f"{row.get('symbol') or 'UNKNOWN'}_{row.get('timeframe') or 'unknown'}.csv"))
    adapted = _canonical_row(
        row,
        path=path,
        row_number=int(row.get("source_row_number") or 0),
        exchange=str(row.get("exchange") or "kraken"),
        market_type=str(row.get("market_type") or "spot"),
        market_mappings=market_mappings or {},
    )
    if recorded_ingestion_time is not None:
        if recorded_ingestion_time.tzinfo is None or recorded_ingestion_time.utcoffset() is None:
            raise ValueError("recorded_ingestion_time must be timezone-aware")
        known_ingestion = max(_parse_iso(adapted["available_time"]) or recorded_ingestion_time, recorded_ingestion_time.astimezone(timezone.utc))
        adapted["ingestion_time"] = known_ingestion.isoformat()
        adapted["temporal_status"] = "MIGRATED_LEGACY_WITH_RECORDED_INGESTION"
    return adapted


def fingerprint_canonical_rows(rows: Sequence[Mapping[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in sorted(rows, key=lambda item: _sort_key(item)):
        stable = {
            "schema_version": str(row.get("schema_version") or CANONICAL_OHLCV_SCHEMA_VERSION),
            "exchange": str(row["exchange"]),
            "market_type": str(row["market_type"]),
            "symbol": str(row["symbol"]),
            "base_asset": str(row.get("base_asset") or ""),
            "quote_asset": str(row.get("quote_asset") or ""),
            "market_mapping_status": str(row.get("market_mapping_status") or "MAPPING_UNVERIFIED"),
            "timeframe": str(row["timeframe"]),
            "event_time": str(row.get("event_time") or row["open_timestamp"]),
            "available_time": str(row.get("available_time") or row["open_timestamp"]),
            "bar_close_time": str(row.get("bar_close_time") or row["open_timestamp"]),
            "open_timestamp": str(row["open_timestamp"]),
            "open": _stable_number(row["open"]),
            "high": _stable_number(row["high"]),
            "low": _stable_number(row["low"]),
            "close": _stable_number(row["close"]),
            "volume": _stable_number(row["volume"]),
        }
        digest.update(json.dumps(stable, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def classify_snapshot_significance(
    previous: Mapping[str, Any] | None,
    current: Mapping[str, Any] | None,
) -> str:
    if not previous:
        return "first_canonical_snapshot_or_uncompared"
    if not current:
        return "first_canonical_snapshot_or_uncompared"
    if previous.get("fingerprint") == current.get("fingerprint"):
        return "same_data"
    prev_rows = int(previous.get("canonical_row_count") or 0)
    curr_rows = int(current.get("canonical_row_count") or 0)
    row_delta = max(0, curr_rows - prev_rows)
    prev_end = _parse_iso(previous.get("end_at"))
    curr_end = _parse_iso(current.get("end_at"))
    period_extension_days = 0.0
    if prev_end and curr_end and curr_end > prev_end:
        period_extension_days = (curr_end - prev_end).total_seconds() / 86_400.0
    if period_extension_days >= 30.0 or row_delta >= max(100, int(prev_rows * 0.05)):
        return "significant_new_period"
    return "minor_addition"


def load_latest_canonical_snapshot_manifest(manifest_dir: str | Path) -> dict[str, Any] | None:
    path = Path(manifest_dir)
    if not path.exists():
        return None
    manifests = sorted(path.glob("*canonical_ohlcv*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    if not manifests:
        manifests = sorted(path.glob("*ohlcv*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    for manifest in manifests:
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("snapshot_id") and payload.get("fingerprint"):
            return payload
    return None


def render_canonical_ohlcv_report(snapshot: CanonicalOHLCVSnapshot) -> str:
    lines = [
        f"# Canonical OHLCV Snapshot - {snapshot.run_id}",
        "",
        f"Generated at: `{snapshot.generated_at}`",
        f"Snapshot: `{snapshot.snapshot_id}`",
        f"Schema version: `{snapshot.schema_version}`",
        f"Fingerprint: `{snapshot.fingerprint}`",
        "",
        "## Summary",
        "",
        f"- Raw files: `{snapshot.raw_file_count}`",
        f"- Raw rows: `{snapshot.raw_row_count}`",
        f"- Canonical rows: `{snapshot.canonical_row_count}`",
        f"- Duplicates removed: `{snapshot.duplicate_count}`",
        f"- Gaps detected: `{snapshot.gap_count}`",
        f"- Quarantined rows: `{snapshot.quarantine_count}`",
        f"- Period: `{snapshot.start_at}` -> `{snapshot.end_at}`",
        f"- Availability: `{snapshot.available_start_at}` -> `{snapshot.available_end_at}`",
        f"- Symbols: `{', '.join(snapshot.symbols)}`",
        f"- Timeframes: `{', '.join(snapshot.timeframes)}`",
        f"- Storage bytes: `{snapshot.storage_size_bytes}`",
        f"- New data significance: `{snapshot.new_data_significance}`",
        "",
        "## Files",
        "",
        "| Symbol | Timeframe | Rows | Gaps | Start | End | Path |",
        "| --- | --- | ---: | ---: | --- | --- | --- |",
    ]
    for item in snapshot.files:
        lines.append(
            f"| `{item.symbol}` | `{item.timeframe}` | {item.row_count} | {item.gap_count} | "
            f"{item.start_at or '-'} | {item.end_at or '-'} | `{item.csv_path}` |"
        )
    lines.extend(["", "## Safety", ""])
    lines.extend(f"- {item}" for item in snapshot.safety_notes)
    lines.append(f"- paper_capital_allowed: `{snapshot.paper_capital_allowed}`")
    lines.append(f"- live_allowed: `{snapshot.live_allowed}`")
    lines.append(f"- promotable: `{snapshot.promotable}`")
    lines.append("")
    return "\n".join(lines)


def write_canonical_ohlcv_report(snapshot: CanonicalOHLCVSnapshot, output_dir: str | Path) -> tuple[Path, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / f"{snapshot.run_id}.json"
    markdown_path = output / f"{snapshot.run_id}.md"
    json_path.write_text(json.dumps(snapshot.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(render_canonical_ohlcv_report(snapshot), encoding="utf-8")
    return json_path, markdown_path


def _iter_raw_ohlcv_files(paths: Sequence[Path]) -> list[Path]:
    files: list[Path] = []
    for root in paths:
        if root.is_file() and root.suffix.lower() == ".csv" and _looks_like_ohlcv_file(root):
            files.append(root)
        elif root.exists():
            files.extend(
                path
                for path in root.rglob("*.csv")
                if path.is_file() and _looks_like_ohlcv_file(path)
            )
    return sorted(dict.fromkeys(files), key=lambda path: str(path).lower())


def _looks_like_ohlcv_file(path: Path) -> bool:
    lowered = str(path).lower()
    if any(token in lowered for token in ("canonical/ohlcv", "quarantine", "spread_depth", "microstructure", "ledger", "decision")):
        return False
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = set(reader.fieldnames or ())
    except (OSError, UnicodeDecodeError, csv.Error):
        return False
    return {"open", "high", "low", "close"}.issubset(fields) and ("timestamp" in fields or "open_timestamp" in fields)


def _read_csv_rows(path: Path) -> Iterable[tuple[int, dict[str, str]]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row_number, row in enumerate(reader, start=2):
                yield row_number, row
    except (OSError, UnicodeDecodeError, csv.Error):
        return


def _canonical_row(
    row: Mapping[str, Any],
    *,
    path: Path,
    row_number: int,
    exchange: str,
    market_type: str,
    market_mappings: Mapping[str, Mapping[str, str]],
) -> dict[str, Any]:
    source_symbol = str(row.get("symbol") or _symbol_from_filename(path))
    source_timeframe = str(row.get("timeframe") or _timeframe_from_filename(path))
    source_timestamp = row.get("open_timestamp") or row.get("timestamp") or row.get("datetime") or row.get("time")
    if _timestamp_is_naive(source_timestamp):
        raise ValueError("naive_timestamp")
    if row.get("timestamp") and row.get("open_timestamp"):
        legacy_timestamp = _parse_iso(row.get("timestamp"))
        open_timestamp = _parse_iso(row.get("open_timestamp"))
        if legacy_timestamp and open_timestamp and legacy_timestamp != open_timestamp:
            raise ValueError("conflicting_timestamp_and_open_timestamp")
    bar = MarketBar.from_mapping(
        {
            **row,
            "timestamp": source_timestamp,
            "symbol": source_symbol,
            "timeframe": source_timeframe,
        },
        default_symbol=source_symbol,
        default_timeframe=source_timeframe,
    )
    timestamp = bar.timestamp.astimezone(timezone.utc).replace(microsecond=0)
    symbol = normalize_research_symbol(bar.symbol)
    timeframe = _normalize_timeframe(bar.timeframe)
    if not symbol:
        raise ValueError("missing_symbol")
    if timeframe == "unknown":
        raise ValueError("missing_timeframe")
    timeframe_seconds = TIMEFRAME_SECONDS.get(timeframe)
    if timeframe_seconds is None:
        raise ValueError(f"unsupported_timeframe:{timeframe}")
    source_timestamp_role = str(row.get("source_timestamp_role") or "legacy_assumed_open").strip().lower()
    if source_timestamp_role in {"legacy_assumed_open", "bar_open", "open"}:
        open_time = timestamp
        bar_close_time = open_time + timedelta(seconds=timeframe_seconds)
    elif source_timestamp_role in {"bar_close", "close"}:
        bar_close_time = timestamp
        open_time = bar_close_time - timedelta(seconds=timeframe_seconds)
        source_timestamp_role = "bar_close"
    else:
        raise ValueError(f"unsupported_source_timestamp_role:{source_timestamp_role}")
    event_time = bar_close_time
    explicit_available = _parse_iso(row.get("available_time") or row.get("bar_close_time"))
    available_time = max(bar_close_time, explicit_available) if explicit_available else bar_close_time
    explicit_ingestion = _parse_iso(
        row.get("ingestion_time") or row.get("ingested_at") or row.get("collected_at") or row.get("fetched_at")
    )
    ingestion_time = max(available_time, explicit_ingestion) if explicit_ingestion else None
    mapping = _explicit_market_mapping(
        symbol,
        row=row,
        configured=market_mappings,
    )
    return {
        "schema_version": str(CANONICAL_OHLCV_SCHEMA_VERSION),
        "exchange": exchange.lower(),
        "market_type": market_type.lower(),
        "symbol": symbol,
        "base_asset": mapping["base_asset"],
        "quote_asset": mapping["quote_asset"],
        "market_mapping_status": mapping["status"],
        "timeframe": timeframe,
        "event_time": event_time.isoformat(),
        "available_time": available_time.isoformat(),
        "ingestion_time": ingestion_time.isoformat() if ingestion_time else "",
        "bar_close_time": bar_close_time.isoformat(),
        "source_timestamp_role": source_timestamp_role,
        "availability_basis": "EXPLICIT_SOURCE" if explicit_available else "DERIVED_BAR_CLOSE",
        "temporal_status": "EXPLICIT_SOURCE_TIMES" if explicit_ingestion or explicit_available else "AVAILABLE_AT_BAR_CLOSE_INGESTION_UNKNOWN",
        "open_timestamp": open_time.isoformat(),
        "timestamp": open_time.isoformat(),
        "open": _stable_number(bar.open),
        "high": _stable_number(bar.high),
        "low": _stable_number(bar.low),
        "close": _stable_number(bar.close),
        "volume": _stable_number(bar.volume),
        "source_path": str(path),
        "source_row_number": row_number,
    }


def _explicit_market_mapping(
    symbol: str,
    *,
    row: Mapping[str, Any],
    configured: Mapping[str, Mapping[str, str]],
) -> dict[str, str]:
    """Return only an explicit base/quote mapping; never guess a conversion."""

    candidate = configured.get(symbol) or configured.get(str(row.get("symbol") or "")) or {}
    base = str(candidate.get("base_asset") or row.get("base_asset") or "").strip().upper()
    quote = str(candidate.get("quote_asset") or row.get("quote_asset") or "").strip().upper()
    if base and quote:
        return {"base_asset": base, "quote_asset": quote, "status": "EXPLICIT"}
    return {"base_asset": "", "quote_asset": "", "status": "MAPPING_UNVERIFIED"}


def _write_canonical_csv(rows: Sequence[Mapping[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CANONICAL_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in CANONICAL_FIELDNAMES})


def _write_snapshot_manifest(snapshot: CanonicalOHLCVSnapshot, manifest_dir: Path, snapshot_dir: Path) -> None:
    manifest_dir.mkdir(parents=True, exist_ok=True)
    payload = snapshot.to_dict()
    manifest_path = Path(str(snapshot.manifest_path)) if snapshot.manifest_path else manifest_dir / f"{snapshot.run_id}_canonical_ohlcv.json"
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    (snapshot_dir / "manifest.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _with_manifest_paths(
    snapshot: CanonicalOHLCVSnapshot,
    manifest_dir: Path,
    snapshot_dir: Path,
) -> CanonicalOHLCVSnapshot:
    manifest_path = manifest_dir / f"{snapshot.run_id}_canonical_ohlcv.json"
    return CanonicalOHLCVSnapshot(
        **{
            **snapshot.to_dict(),
            "symbols": snapshot.symbols,
            "timeframes": snapshot.timeframes,
            "files": snapshot.files,
            "safety_notes": snapshot.safety_notes,
            "manifest_path": str(manifest_path),
        }
    )


def _replace_significance(snapshot: CanonicalOHLCVSnapshot, significance: str) -> CanonicalOHLCVSnapshot:
    return CanonicalOHLCVSnapshot(
        **{
            **snapshot.to_dict(),
            "symbols": snapshot.symbols,
            "timeframes": snapshot.timeframes,
            "files": snapshot.files,
            "safety_notes": snapshot.safety_notes,
            "new_data_significance": significance,
        }
    )


def _deterministic_winner(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    left_key = (str(left.get("source_path")), int(left.get("source_row_number") or 0))
    right_key = (str(right.get("source_path")), int(right.get("source_row_number") or 0))
    return dict(left if left_key <= right_key else right)


def _group_by_symbol_timeframe(rows: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault((str(row["symbol"]), str(row["timeframe"])), []).append(dict(row))
    return {key: sorted(group, key=lambda item: item["open_timestamp"]) for key, group in groups.items()}


def _gap_count(rows: Sequence[Mapping[str, Any]], timeframe: str) -> int:
    seconds = TIMEFRAME_SECONDS.get(timeframe)
    if not seconds or len(rows) < 2:
        return 0
    gaps = 0
    previous = _parse_iso(rows[0]["open_timestamp"])
    for row in rows[1:]:
        current = _parse_iso(row["open_timestamp"])
        if previous and current:
            delta = (current - previous).total_seconds()
            if delta > seconds * 1.5:
                gaps += 1
        previous = current
    return gaps


def _sort_key(row: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(row["exchange"]),
        str(row["market_type"]),
        str(row["symbol"]),
        str(row["timeframe"]),
        str(row["open_timestamp"]),
    )


def _stable_number(value: Any) -> str:
    number = float(value)
    return format(number, ".12g")


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _timestamp_is_naive(value: Any) -> bool:
    if value in (None, "") or isinstance(value, (int, float)):
        return False
    if isinstance(value, datetime):
        return value.tzinfo is None or value.utcoffset() is None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is None or parsed.utcoffset() is None


def _normalize_timeframe(value: str) -> str:
    raw = str(value or "").strip().lower()
    aliases = {
        "60": "1h",
        "15": "15m",
        "5": "5m",
        "1": "1m",
        "240": "4h",
        "1440": "1d",
    }
    return aliases.get(raw, raw or "unknown")


def _symbol_from_filename(path: Path) -> str:
    stem = path.stem.upper().replace("-", "_")
    for token in stem.split("_"):
        if token.endswith("EUR") and len(token) >= 6:
            return token
    return "UNKNOWN"


def _timeframe_from_filename(path: Path) -> str:
    parts = path.stem.lower().replace("-", "_").split("_")
    for token in ("1m", "5m", "15m", "1h", "4h", "1d"):
        if token in parts:
            return token
    return "unknown"
