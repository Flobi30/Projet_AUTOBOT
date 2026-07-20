"""Import official Kraken OHLCVT archives into AUTOBOT research inputs.

Kraken publishes complete OHLCVT archives separately from its bounded REST
OHLC endpoint.  This module deliberately imports an operator-supplied archive
only: it has no credentials, no order-capable API client, and no dependency on
the AUTOBOT runtime.  Archive bars are useful for batch research, but their
historical availability cannot prove runtime/shadow parity, so that fact stays
explicit in every normalized row and manifest.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from .data_quality_report import analyze_bars
from .kraken_symbol_mapping import (
    AssetPairsFetcher,
    KrakenPublicPairMapping,
    preflight_kraken_public_symbols,
)
from .market_data_repository import MarketBar, MarketDataRepository
from .symbol_normalization import normalize_research_symbol


OFFICIAL_KRAKEN_OHLCVT_SUPPORT_URL = (
    "https://support.kraken.com/articles/360047124832-downloadable-historical-ohlcvt-open-high-low-close-volume-trades-data"
)
HISTORICAL_ARCHIVE_STATUS = "HISTORICAL_ARCHIVE_AVAILABLE_AT_INGESTION"
KRAKEN_ARCHIVE_TIMEFRAMES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}


class KrakenOhlcvtArchiveError(ValueError):
    """Raised when an OHLCVT archive cannot be imported safely."""


@dataclass(frozen=True)
class KrakenOhlcvtArchiveImportConfig:
    """A bounded import of explicit pair/timeframe members from one ZIP file."""

    run_id: str
    archive_path: Path
    symbols: tuple[str, ...]
    timeframes: tuple[str, ...]
    raw_dir: Path = Path("data/research/raw/kraken_official_ohlcvt")
    normalized_dir: Path = Path("data/research/imports/kraken_official_ohlcvt")
    manifest_dir: Path = Path("data/research/manifests")
    report_dir: Path = Path("reports/research")
    source_url: str = OFFICIAL_KRAKEN_OHLCVT_SUPPORT_URL
    max_archive_bytes: int = 8 * 1024 * 1024 * 1024
    max_selected_uncompressed_bytes: int = 2 * 1024 * 1024 * 1024
    max_rows_per_member: int = 500_000

    def __post_init__(self) -> None:
        if not str(self.run_id).strip():
            raise KrakenOhlcvtArchiveError("run_id must not be empty")
        if not self.symbols:
            raise KrakenOhlcvtArchiveError("at least one symbol is required")
        if not self.timeframes:
            raise KrakenOhlcvtArchiveError("at least one timeframe is required")
        if self.max_archive_bytes <= 0 or self.max_selected_uncompressed_bytes <= 0 or self.max_rows_per_member <= 0:
            raise KrakenOhlcvtArchiveError("archive size and row limits must be positive")
        unsupported = sorted({str(item).strip().lower() for item in self.timeframes} - set(KRAKEN_ARCHIVE_TIMEFRAMES))
        if unsupported:
            raise KrakenOhlcvtArchiveError(f"unsupported Kraken archive timeframes: {unsupported}")
        archive = Path(self.archive_path)
        if not archive.is_file():
            raise KrakenOhlcvtArchiveError(f"archive does not exist: {archive}")
        if archive.stat().st_size > self.max_archive_bytes:
            raise KrakenOhlcvtArchiveError("archive exceeds max_archive_bytes; import a bounded archive or increase the limit explicitly")
        if not str(self.source_url).startswith("https://"):
            raise KrakenOhlcvtArchiveError("source_url must be an HTTPS provenance URL")


@dataclass(frozen=True)
class ImportedOhlcvtMember:
    symbol: str
    timeframe: str
    archive_member: str
    raw_path: str
    normalized_path: str
    row_count: int
    duplicate_count: int
    gap_count: int
    start_at: str | None
    end_at: str | None
    compressed_size_bytes: int
    uncompressed_size_bytes: int
    member_sha256: str
    zip_crc32: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class KrakenOhlcvtArchiveImportResult:
    run_id: str
    imported_at: str
    archive_path: str
    archive_size_bytes: int
    archive_selected_content_fingerprint: str
    source_url: str
    members: tuple[ImportedOhlcvtMember, ...]
    status: str
    blockers: tuple[str, ...]
    manifest_path: str | None = None
    report_path: str | None = None
    research_only: bool = True
    runtime_parity_proven: bool = False
    paper_capital_allowed: bool = False
    live_allowed: bool = False
    promotable: bool = False

    def to_dict(self) -> dict[str, Any]:
        snapshot_id = f"kraken_ohlcvt_{self.archive_selected_content_fingerprint[:16]}"
        return {
            "schema_version": 1,
            "dataset_id": "kraken_official_ohlcvt_archive",
            "run_id": self.run_id,
            "snapshot_id": snapshot_id,
            "imported_at": self.imported_at,
            "archive_path": self.archive_path,
            "archive_size_bytes": self.archive_size_bytes,
            "archive_selected_content_fingerprint": self.archive_selected_content_fingerprint,
            "source_url": self.source_url,
            "members": [member.to_dict() for member in self.members],
            "status": self.status,
            "blockers": list(self.blockers),
            "history_available_for_research": bool(self.members),
            "temporal_contract": {
                "event_time": "UTC bar close",
                "available_time": "UTC bar close assumption from completed official OHLCVT bar",
                "ingestion_time": "UTC archive import time",
                "temporal_status": HISTORICAL_ARCHIVE_STATUS,
                "runtime_parity_proven": False,
            },
            "research_only": True,
            "runtime_parity_proven": False,
            "paper_capital_allowed": False,
            "live_allowed": False,
            "promotable": False,
            "manifest_path": self.manifest_path,
            "report_path": self.report_path,
            "safety_notes": [
                "Official public OHLCVT archive import only.",
                "No Kraken private endpoint, key, paper capital, live execution, promotion, sizing, leverage, router, or order path is used.",
                "Historical archive provenance is research-only and never establishes runtime/shadow parity.",
            ],
        }


def import_kraken_ohlcvt_archive(
    config: KrakenOhlcvtArchiveImportConfig,
    *,
    imported_at: datetime | None = None,
    asset_pairs_fetcher: AssetPairsFetcher | None = None,
    symbol_mappings: Mapping[str, KrakenPublicPairMapping] | None = None,
) -> KrakenOhlcvtArchiveImportResult:
    """Import selected completed OHLCVT members without extracting a full archive.

    Exact selected source members are retained below ``raw_dir``.  Normalized
    rows are written separately for the canonical OHLCV store.  Both output
    families are bounded before any member is read, which prevents a large
    exchange archive from silently consuming the VPS disk.
    """

    timestamp = _utc(imported_at or datetime.now(timezone.utc), "imported_at")
    mappings = _resolve_symbol_mappings(
        config.symbols,
        asset_pairs_fetcher=asset_pairs_fetcher,
        symbol_mappings=symbol_mappings,
    )
    normalized_timeframes = tuple(dict.fromkeys(str(item).strip().lower() for item in config.timeframes))
    archive_path = Path(config.archive_path)

    with zipfile.ZipFile(archive_path) as archive:
        selected = _select_members(archive, mappings=mappings, timeframes=normalized_timeframes)
        expected = {(mapping.autobot_symbol, timeframe) for mapping in mappings.values() for timeframe in normalized_timeframes}
        found = {(mapping.autobot_symbol, timeframe) for mapping, timeframe, _info in selected}
        missing = sorted(expected - found)
        if missing:
            rendered = ", ".join(f"{symbol}:{timeframe}" for symbol, timeframe in missing)
            raise KrakenOhlcvtArchiveError(f"archive lacks requested symbol/timeframe members: {rendered}")
        selected_size = sum(info.file_size for _mapping, _timeframe, info in selected)
        if selected_size > config.max_selected_uncompressed_bytes:
            raise KrakenOhlcvtArchiveError(
                "selected archive members exceed max_selected_uncompressed_bytes; reduce symbols/timeframes or increase the limit explicitly"
            )

        imported_members: list[ImportedOhlcvtMember] = []
        for mapping, timeframe, info in selected:
            raw_path, member_hash = _stream_member_to_raw(
                archive,
                info,
                root=config.raw_dir,
                run_id=config.run_id,
                symbol=mapping.autobot_symbol,
                timeframe=timeframe,
            )
            bars, trade_counts = _parse_member_bars(
                raw_path,
                mapping=mapping,
                timeframe=timeframe,
                member_name=info.filename,
                max_rows=config.max_rows_per_member,
            )
            bars, duplicate_count = _dedupe_bars(bars)
            normalized_path = _normalized_member_path(config.normalized_dir, config.run_id, mapping.autobot_symbol, timeframe)
            _write_normalized_rows(
                normalized_path,
                bars=bars,
                trade_counts=trade_counts,
                mapping=mapping,
                timeframe=timeframe,
                imported_at=timestamp,
                archive_member=info.filename,
                member_hash=member_hash,
                source_url=config.source_url,
            )
            quality = analyze_bars(
                bars,
                source_path=str(normalized_path),
                source_type="kraken_official_ohlcvt_archive",
                expected_interval_seconds=KRAKEN_ARCHIVE_TIMEFRAMES[timeframe] * 60,
            )
            imported_members.append(
                ImportedOhlcvtMember(
                    symbol=mapping.autobot_symbol,
                    timeframe=timeframe,
                    archive_member=info.filename,
                    raw_path=str(raw_path),
                    normalized_path=str(normalized_path),
                    row_count=len(bars),
                    duplicate_count=duplicate_count,
                    gap_count=quality.gap_count,
                    start_at=bars[0].timestamp.isoformat() if bars else None,
                    end_at=bars[-1].timestamp.isoformat() if bars else None,
                    compressed_size_bytes=info.compress_size,
                    uncompressed_size_bytes=info.file_size,
                    member_sha256=member_hash,
                    zip_crc32=info.CRC,
                )
            )

    ordered_members = tuple(sorted(imported_members, key=lambda item: (item.symbol, item.timeframe, item.archive_member)))
    fingerprint = _fingerprint(
        {
            "source_url": config.source_url,
            "archive_size_bytes": archive_path.stat().st_size,
            "members": [member.to_dict() for member in ordered_members],
        }
    )
    blockers = ("HISTORICAL_ARCHIVE_NOT_RUNTIME_PARITY",)
    status = "COMPLETE_WITH_GAPS" if any(item.gap_count for item in ordered_members) else "COMPLETE"
    result = KrakenOhlcvtArchiveImportResult(
        run_id=config.run_id,
        imported_at=timestamp.isoformat(),
        archive_path=str(archive_path),
        archive_size_bytes=archive_path.stat().st_size,
        archive_selected_content_fingerprint=fingerprint,
        source_url=config.source_url,
        members=ordered_members,
        status=status,
        blockers=blockers,
    )
    return _persist_result(result, config)


def _resolve_symbol_mappings(
    symbols: Sequence[str],
    *,
    asset_pairs_fetcher: AssetPairsFetcher | None,
    symbol_mappings: Mapping[str, KrakenPublicPairMapping] | None,
) -> dict[str, KrakenPublicPairMapping]:
    if symbol_mappings is None:
        preflight = preflight_kraken_public_symbols(symbols, asset_pairs_fetcher=asset_pairs_fetcher)
        candidate_mappings = {mapping.autobot_symbol: mapping for mapping in preflight.mappings}
    else:
        candidate_mappings = {normalize_research_symbol(key): value for key, value in symbol_mappings.items()}
    resolved: dict[str, KrakenPublicPairMapping] = {}
    for requested in symbols:
        canonical = normalize_research_symbol(requested)
        mapping = candidate_mappings.get(canonical)
        if mapping is None:
            mapping = next(
                (
                    item
                    for item in candidate_mappings.values()
                    if canonical in _mapping_aliases(item)
                ),
                None,
            )
        if mapping is None:
            raise KrakenOhlcvtArchiveError(f"missing explicit Kraken mapping for {requested}")
        if mapping.explicit_market_mapping() is None:
            raise KrakenOhlcvtArchiveError(f"mapping must declare base/quote assets for {requested}")
        resolved[mapping.autobot_symbol] = mapping
    return resolved


def _select_members(
    archive: zipfile.ZipFile,
    *,
    mappings: Mapping[str, KrakenPublicPairMapping],
    timeframes: Sequence[str],
) -> list[tuple[KrakenPublicPairMapping, str, zipfile.ZipInfo]]:
    selected: list[tuple[KrakenPublicPairMapping, str, zipfile.ZipInfo]] = []
    seen: set[tuple[str, str]] = set()
    for info in archive.infolist():
        if info.is_dir() or not info.filename.lower().endswith(".csv"):
            continue
        timeframe = _member_timeframe(info.filename)
        if timeframe not in timeframes:
            continue
        matching = [mapping for mapping in mappings.values() if _member_matches_mapping(info.filename, mapping)]
        if len(matching) > 1:
            raise KrakenOhlcvtArchiveError(f"ambiguous Kraken archive member mapping: {info.filename}")
        if not matching:
            continue
        key = (matching[0].autobot_symbol, timeframe)
        if key in seen:
            raise KrakenOhlcvtArchiveError(f"duplicate Kraken archive member for {key[0]} {key[1]}")
        seen.add(key)
        selected.append((matching[0], timeframe, info))
    return selected


def _member_timeframe(member_name: str) -> str | None:
    stem = PurePosixPath(member_name).stem.lower()
    match = re.search(r"(?:^|[_\-.])(1|5|15|60|240|1440)$", stem)
    if match is None:
        return None
    minutes = int(match.group(1))
    return next((timeframe for timeframe, interval in KRAKEN_ARCHIVE_TIMEFRAMES.items() if interval == minutes), None)


def _member_matches_mapping(member_name: str, mapping: KrakenPublicPairMapping) -> bool:
    stem = PurePosixPath(member_name).stem.upper()
    stem = re.sub(r"(?:^|[_\-.])(1|5|15|60|240|1440)$", "", stem)
    normalized_stem = _compact(stem)
    aliases = sorted(_mapping_aliases(mapping), key=len, reverse=True)
    return any(normalized_stem.endswith(alias) for alias in aliases)


def _mapping_aliases(mapping: KrakenPublicPairMapping) -> set[str]:
    values = {
        mapping.autobot_symbol,
        mapping.kraken_ohlcv_symbol,
        mapping.runtime_symbol,
        *mapping.aliases,
        mapping.altname or "",
        mapping.wsname or "",
        f"{mapping.base_asset or ''}{mapping.quote_asset or ''}",
    }
    return {_compact(item) for item in values if _compact(item)}


def _compact(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value).upper())


def _parse_member_bars(
    raw_path: Path,
    *,
    mapping: KrakenPublicPairMapping,
    timeframe: str,
    member_name: str,
    max_rows: int,
) -> tuple[list[MarketBar], dict[datetime, int | None]]:
    try:
        with raw_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise KrakenOhlcvtArchiveError(f"archive member has no CSV header: {member_name}")
            fields = {_compact(field): field for field in reader.fieldnames if field}
            timestamp_field = _first_field(fields, "TIMESTAMP", "TIME", "DATE", "DATETIME")
            required = {"OPEN": _first_field(fields, "OPEN"), "HIGH": _first_field(fields, "HIGH"), "LOW": _first_field(fields, "LOW"), "CLOSE": _first_field(fields, "CLOSE"), "VOLUME": _first_field(fields, "VOLUME", "VOL")}
            if timestamp_field is None or any(value is None for value in required.values()):
                raise KrakenOhlcvtArchiveError(f"archive member has unsupported OHLCVT columns: {member_name}")
            trades_field = _first_field(fields, "TRADES", "TRADECOUNT", "COUNT")
            bars: list[MarketBar] = []
            trade_counts: dict[datetime, int | None] = {}
            for row_number, row in enumerate(reader, start=2):
                if row_number - 1 > max_rows:
                    raise KrakenOhlcvtArchiveError(
                        f"archive member exceeds max_rows_per_member ({max_rows}): {member_name}"
                    )
                try:
                    open_time = _parse_timestamp(row[timestamp_field])
                    values = {key: float(str(row[field])) for key, field in required.items() if field is not None}
                except (TypeError, ValueError, KeyError) as exc:
                    raise KrakenOhlcvtArchiveError(f"invalid OHLCVT row {row_number} in {member_name}") from exc
                if min(values["OPEN"], values["HIGH"], values["LOW"], values["CLOSE"]) <= 0.0 or values["VOLUME"] < 0.0:
                    raise KrakenOhlcvtArchiveError(f"invalid non-positive OHLCVT values at row {row_number} in {member_name}")
                trade_count = _optional_nonnegative_int(row.get(trades_field)) if trades_field else None
                bars.append(
                    MarketBar(
                        timestamp=open_time,
                        symbol=mapping.autobot_symbol,
                        timeframe=timeframe,
                        open=values["OPEN"],
                        high=values["HIGH"],
                        low=values["LOW"],
                        close=values["CLOSE"],
                        volume=values["VOLUME"],
                        metadata={},
                    )
                )
                trade_counts[open_time] = trade_count
    except UnicodeDecodeError as exc:
        raise KrakenOhlcvtArchiveError(f"archive member is not UTF-8 CSV: {member_name}") from exc
    if not bars:
        raise KrakenOhlcvtArchiveError(f"archive member has no OHLCVT rows: {member_name}")
    return bars, trade_counts


def _first_field(fields: Mapping[str, str], *candidates: str) -> str | None:
    return next((fields[candidate] for candidate in candidates if candidate in fields), None)


def _parse_timestamp(value: Any) -> datetime:
    raw = str(value).strip()
    try:
        numeric = float(raw)
    except ValueError:
        normalized = f"{raw[:-1]}+00:00" if raw.endswith("Z") else raw
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise KrakenOhlcvtArchiveError(f"invalid OHLCVT timestamp: {value!r}") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise KrakenOhlcvtArchiveError("OHLCVT timestamps must be timezone-aware")
        return parsed.astimezone(timezone.utc).replace(microsecond=0)
    if numeric > 10_000_000_000:
        numeric /= 1_000.0
    return datetime.fromtimestamp(numeric, tz=timezone.utc).replace(microsecond=0)


def _optional_nonnegative_int(value: Any) -> int | None:
    if value is None or not str(value).strip():
        return None
    try:
        parsed = int(str(value))
    except ValueError as exc:
        raise KrakenOhlcvtArchiveError("trade count must be a non-negative integer") from exc
    if parsed < 0:
        raise KrakenOhlcvtArchiveError("trade count must be non-negative")
    return parsed


def _dedupe_bars(bars: Sequence[MarketBar]) -> tuple[list[MarketBar], int]:
    deduped: list[MarketBar] = []
    seen: set[tuple[str, str, datetime]] = set()
    for bar in MarketDataRepository.normalize(bars):
        key = bar.key()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(bar)
    return deduped, len(bars) - len(deduped)


def _write_normalized_rows(
    path: Path,
    *,
    bars: Sequence[MarketBar],
    trade_counts: Mapping[datetime, int | None],
    mapping: KrakenPublicPairMapping,
    timeframe: str,
    imported_at: datetime,
    archive_member: str,
    member_hash: str,
    source_url: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = (
        "schema_version", "timestamp", "symbol", "timeframe", "base_asset", "quote_asset", "open", "high", "low", "close", "volume",
        "metadata", "event_time", "available_time", "ingestion_time", "temporal_status", "bar_close_time", "source_timestamp_role",
        "availability_basis", "source", "source_support_url", "archive_member", "member_sha256",
    )
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    interval = timedelta(minutes=KRAKEN_ARCHIVE_TIMEFRAMES[timeframe])
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for bar in bars:
            close_time = bar.timestamp + interval
            if close_time > imported_at:
                raise KrakenOhlcvtArchiveError(
                    f"archive member contains a bar not closed at import time: {archive_member} {bar.timestamp.isoformat()}"
                )
            metadata = {
                "source": "kraken_official_ohlcvt_archive",
                "source_support_url": source_url,
                "archive_member": archive_member,
                "member_sha256": member_hash,
                "trade_count": trade_counts.get(bar.timestamp),
                "volume_source": "kraken_official_ohlcvt",
                "bid_ask_source": "absent",
                "depth_source": "absent",
                "historical_archive": True,
            }
            writer.writerow(
                {
                    "schema_version": "1",
                    "timestamp": bar.timestamp.isoformat(),
                    "symbol": mapping.autobot_symbol,
                    "timeframe": timeframe,
                    "base_asset": mapping.base_asset or "",
                    "quote_asset": mapping.quote_asset or "",
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                    "metadata": json.dumps(metadata, sort_keys=True),
                    "event_time": close_time.isoformat(),
                    "available_time": close_time.isoformat(),
                    "ingestion_time": imported_at.isoformat(),
                    "temporal_status": HISTORICAL_ARCHIVE_STATUS,
                    "bar_close_time": close_time.isoformat(),
                    "source_timestamp_role": "bar_open",
                    "availability_basis": "OFFICIAL_ARCHIVE_COMPLETED_BAR_ASSUMPTION",
                    "source": "kraken_official_ohlcvt_archive",
                    "source_support_url": source_url,
                    "archive_member": archive_member,
                    "member_sha256": member_hash,
                }
            )
    temporary.replace(path)


def _persist_result(result: KrakenOhlcvtArchiveImportResult, config: KrakenOhlcvtArchiveImportConfig) -> KrakenOhlcvtArchiveImportResult:
    config.manifest_dir.mkdir(parents=True, exist_ok=True)
    config.report_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = config.manifest_dir / f"{config.run_id}_kraken_official_ohlcvt_archive.json"
    report_path = config.report_dir / f"{config.run_id}_kraken_official_ohlcvt_archive.md"
    materialized = KrakenOhlcvtArchiveImportResult(
        **{**result.__dict__, "manifest_path": str(manifest_path), "report_path": str(report_path)}
    )
    _atomic_text(manifest_path, json.dumps(materialized.to_dict(), indent=2, sort_keys=True) + "\n")
    lines = [
        f"# Kraken Official OHLCVT Archive Import — {materialized.run_id}",
        "",
        f"- Status: `{materialized.status}`",
        f"- Archive: `{materialized.archive_path}` ({materialized.archive_size_bytes} bytes)",
        f"- Official provenance: {materialized.source_url}",
        f"- Selected-content fingerprint: `{materialized.archive_selected_content_fingerprint}`",
        f"- Blockers: `{', '.join(materialized.blockers)}`",
        "- Research-only; historical data never proves runtime parity and cannot enable shadow, paper capital, promotion, live trading, or orders.",
        "",
        "## Imported members",
        "",
        "| Symbol | Timeframe | Rows | Duplicates | Gaps | Start | End | Source member |",
        "| --- | --- | ---: | ---: | ---: | --- | --- | --- |",
    ]
    for member in materialized.members:
        lines.append(
            f"| {member.symbol} | {member.timeframe} | {member.row_count} | {member.duplicate_count} | {member.gap_count} | "
            f"{member.start_at or '-'} | {member.end_at or '-'} | {member.archive_member} |"
        )
    _atomic_text(report_path, "\n".join(lines) + "\n")
    return materialized


def _raw_member_path(root: Path, run_id: str, symbol: str, timeframe: str, member_hash: str) -> Path:
    return Path(root) / run_id / f"{symbol}_{timeframe}_{member_hash[:16]}.csv"


def _stream_member_to_raw(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    *,
    root: Path,
    run_id: str,
    symbol: str,
    timeframe: str,
) -> tuple[Path, str]:
    """Persist one selected member in bounded chunks without loading it all."""

    target_dir = Path(root) / run_id
    target_dir.mkdir(parents=True, exist_ok=True)
    temporary = target_dir / f".{symbol}_{timeframe}_{info.header_offset}.tmp"
    digest = hashlib.sha256()
    written = 0
    with archive.open(info, "r") as source, temporary.open("wb") as destination:
        while chunk := source.read(1024 * 1024):
            written += len(chunk)
            if written > info.file_size:
                raise KrakenOhlcvtArchiveError(f"archive member exceeds declared size: {info.filename}")
            digest.update(chunk)
            destination.write(chunk)
    if written != info.file_size:
        temporary.unlink(missing_ok=True)
        raise KrakenOhlcvtArchiveError(f"archive member size mismatch: {info.filename}")
    member_hash = digest.hexdigest()
    destination_path = _raw_member_path(root, run_id, symbol, timeframe, member_hash)
    temporary.replace(destination_path)
    return destination_path, member_hash


def _normalized_member_path(root: Path, run_id: str, symbol: str, timeframe: str) -> Path:
    return Path(root) / f"{run_id}_{symbol}_{timeframe}.csv"


def _fingerprint(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def _atomic_text(path: Path, value: str) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def _utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise KrakenOhlcvtArchiveError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)
