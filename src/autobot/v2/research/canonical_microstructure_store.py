"""Canonical, point-in-time storage for public top-of-book observations.

The store consumes CSV files produced by :mod:`spread_depth_recorder`.  It is
strictly a research data transformation: it has no network access, imports no
runtime/execution module, and explicitly marks every REST observation as
*not* runtime-parity proof.  This avoids turning a sparse public REST sample
into an implicit permission to shadow, paper or live trade.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from autobot.v2.contracts import CanonicalMarketEvent, MarketIdentity


CANONICAL_MICROSTRUCTURE_SCHEMA_VERSION = 1
CANONICAL_MICROSTRUCTURE_FIELDS = (
    "schema_version",
    "exchange",
    "market_type",
    "symbol",
    "base_asset",
    "quote_asset",
    "market_mapping_status",
    "event_time",
    "available_time",
    "ingestion_time",
    "source_snapshot_id",
    "source",
    "best_bid",
    "best_ask",
    "mid_price",
    "spread_bps",
    "bid_depth_quote",
    "ask_depth_quote",
    "latency_ms",
    "temporal_status",
    "runtime_parity_proven",
    "exchange_clock_ahead_seconds",
    "data_quality_status",
    "raw_source_path",
    "raw_source_sha256",
    "raw_source_row_number",
)


@dataclass(frozen=True)
class CanonicalMicrostructureConfig:
    run_id: str
    raw_paths: tuple[Path, ...]
    output_dir: Path = Path("data/research/canonical/microstructure")
    manifest_dir: Path = Path("data/research/manifests")
    report_dir: Path = Path("data/research/reports/canonical_microstructure")
    exchange: str = "kraken"
    market_type: str = "spot"
    max_files: int | None = None
    max_rows: int | None = None

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id must not be empty")
        if not self.raw_paths:
            raise ValueError("raw_paths must not be empty")
        if self.max_files is not None and self.max_files <= 0:
            raise ValueError("max_files must be positive when configured")
        if self.max_rows is not None and self.max_rows <= 0:
            raise ValueError("max_rows must be positive when configured")
        if not self.exchange.strip() or not self.market_type.strip():
            raise ValueError("exchange and market_type are required")


@dataclass(frozen=True)
class CanonicalMicrostructureSnapshot:
    run_id: str
    generated_at: str
    snapshot_id: str
    fingerprint: str
    schema_version: int
    exchange: str
    market_type: str
    raw_paths: tuple[str, ...]
    raw_file_sha256: Mapping[str, str]
    raw_row_count: int
    canonical_row_count: int
    duplicate_count: int
    quarantine_count: int
    start_at: str | None
    end_at: str | None
    symbols: tuple[str, ...]
    runtime_parity_proven: bool = False
    execution_eligible: bool = False
    canonical_csv_path: str | None = None
    manifest_path: str | None = None
    report_path: str | None = None
    quarantine_path: str | None = None
    safety_notes: tuple[str, ...] = (
        "Canonical microstructure snapshot is research-only.",
        "Source is forward-captured public Kraken REST depth.",
        "REST capture does not prove runtime-feed parity.",
        "No paper or live order is created or authorized.",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "raw_paths": list(self.raw_paths),
            "raw_file_sha256": dict(self.raw_file_sha256),
            "symbols": list(self.symbols),
            "safety_notes": list(self.safety_notes),
        }


def build_canonical_microstructure_snapshot(
    config: CanonicalMicrostructureConfig,
) -> CanonicalMicrostructureSnapshot:
    """Materialize one immutable point-in-time microstructure snapshot.

    Invalid legacy rows are quarantined rather than repaired.  In particular,
    there is no inferred quote conversion and no synthetic availability time.
    """

    raw_files = _collect_csv_files(config.raw_paths, max_files=config.max_files)
    raw_hashes = {str(path): _sha256_file(path) for path in raw_files}
    raw_row_count = 0
    quarantine: list[dict[str, Any]] = []
    canonical_by_id: dict[str, dict[str, Any]] = {}

    for path in raw_files:
        with path.open("r", newline="", encoding="utf-8") as handle:
            for row_number, raw in enumerate(csv.DictReader(handle), start=2):
                raw_row_count += 1
                if config.max_rows is not None and raw_row_count > config.max_rows:
                    raise ValueError(f"max_rows exceeded ({config.max_rows})")
                try:
                    row = adapt_spread_depth_row(
                        raw,
                        exchange=config.exchange,
                        market_type=config.market_type,
                        raw_source_path=str(path),
                        raw_source_sha256=raw_hashes[str(path)],
                        raw_source_row_number=row_number,
                    )
                except ValueError as exc:
                    quarantine.append(
                        {
                            "source_path": str(path),
                            "source_row_number": row_number,
                            "reason": str(exc),
                            "row": dict(raw),
                        }
                    )
                    continue
                canonical_by_id.setdefault(str(row["source_snapshot_id"]), row)

    rows = sorted(canonical_by_id.values(), key=_canonical_sort_key)
    fingerprint = fingerprint_canonical_microstructure_rows(rows)
    snapshot_id = f"microstructure_v{CANONICAL_MICROSTRUCTURE_SCHEMA_VERSION}_{fingerprint[:16]}"
    snapshot_dir = config.output_dir / snapshot_id
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    canonical_csv_path = snapshot_dir / "kraken_spot_microstructure.csv"
    _write_csv(canonical_csv_path, rows)

    quarantine_path: Path | None = None
    if quarantine:
        quarantine_dir = config.report_dir / "quarantine"
        quarantine_dir.mkdir(parents=True, exist_ok=True)
        quarantine_path = quarantine_dir / f"{config.run_id}_canonical_microstructure_quarantine.json"
        quarantine_path.write_text(json.dumps(quarantine, indent=2, sort_keys=True), encoding="utf-8")

    duplicate_count = max(0, raw_row_count - len(quarantine) - len(rows))
    snapshot = CanonicalMicrostructureSnapshot(
        run_id=config.run_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        snapshot_id=snapshot_id,
        fingerprint=fingerprint,
        schema_version=CANONICAL_MICROSTRUCTURE_SCHEMA_VERSION,
        exchange=config.exchange.lower(),
        market_type=config.market_type.lower(),
        raw_paths=tuple(str(path) for path in raw_files),
        raw_file_sha256=raw_hashes,
        raw_row_count=raw_row_count,
        canonical_row_count=len(rows),
        duplicate_count=duplicate_count,
        quarantine_count=len(quarantine),
        start_at=rows[0]["event_time"] if rows else None,
        end_at=rows[-1]["event_time"] if rows else None,
        symbols=tuple(sorted({str(row["symbol"]) for row in rows})),
        canonical_csv_path=str(canonical_csv_path),
        quarantine_path=str(quarantine_path) if quarantine_path else None,
    )
    return _write_snapshot_artifacts(snapshot, snapshot_dir, config.manifest_dir, config.report_dir)


def adapt_spread_depth_row(
    raw: Mapping[str, Any],
    *,
    exchange: str,
    market_type: str,
    raw_source_path: str,
    raw_source_sha256: str,
    raw_source_row_number: int,
) -> dict[str, Any]:
    """Validate one forward REST capture against the shared market contract."""

    market_mapping_status = _required(raw.get("market_mapping_status"), "market_mapping_status")
    if market_mapping_status != "EXPLICIT":
        raise ValueError("market_mapping_not_explicit")
    market = MarketIdentity(
        exchange=exchange,
        market_type=market_type,
        symbol=_required(raw.get("symbol"), "symbol"),
        base_asset=_required(raw.get("base_asset"), "base_asset"),
        quote_asset=_required(raw.get("quote_asset"), "quote_asset"),
    )
    if market.quote_asset != "EUR":
        raise ValueError("quote_conversion_not_explicitly_supported")
    if _as_bool(raw.get("runtime_parity_proven")):
        raise ValueError("rest_capture_cannot_claim_runtime_parity")
    temporal_status = _required(raw.get("temporal_status"), "temporal_status")
    if temporal_status != "FORWARD_PUBLIC_REST_INGESTED":
        raise ValueError("unverified_microstructure_temporal_status")
    event_time = _parse_utc(raw.get("event_time"), "event_time")
    available_time = _parse_utc(raw.get("available_time"), "available_time")
    ingestion_time = _parse_utc(raw.get("ingestion_time"), "ingestion_time")
    source_snapshot_id = _required(raw.get("source_snapshot_id"), "source_snapshot_id")
    CanonicalMarketEvent(
        market=market,
        event_time=event_time,
        available_time=available_time,
        ingestion_time=ingestion_time,
        source_snapshot_id=source_snapshot_id,
        payload={"source": _required(raw.get("source"), "source")},
    )
    best_bid = _positive_finite(raw.get("best_bid"), "best_bid")
    best_ask = _positive_finite(raw.get("best_ask"), "best_ask")
    if best_ask < best_bid:
        raise ValueError("best_ask_before_best_bid")
    mid_price = _positive_finite(raw.get("mid_price"), "mid_price")
    spread_bps = _non_negative_finite(raw.get("spread_bps"), "spread_bps")
    bid_depth = _non_negative_finite(raw.get("bid_depth_eur"), "bid_depth_eur")
    ask_depth = _non_negative_finite(raw.get("ask_depth_eur"), "ask_depth_eur")
    latency = _non_negative_finite(raw.get("latency_ms"), "latency_ms")
    clock_ahead_seconds = _non_negative_finite(
        raw.get("exchange_clock_ahead_seconds"),
        "exchange_clock_ahead_seconds",
    )
    if clock_ahead_seconds > 60.0:
        raise ValueError("exchange_clock_ahead_seconds_exceeds_bound")
    expected_mid = (best_bid + best_ask) / 2.0
    if not math.isclose(mid_price, expected_mid, rel_tol=1e-9, abs_tol=1e-9):
        raise ValueError("mid_price_inconsistent_with_best_quotes")
    expected_spread = ((best_ask - best_bid) / expected_mid) * 10_000.0
    if not math.isclose(spread_bps, expected_spread, rel_tol=1e-7, abs_tol=1e-7):
        raise ValueError("spread_bps_inconsistent_with_best_quotes")
    return {
        "schema_version": CANONICAL_MICROSTRUCTURE_SCHEMA_VERSION,
        "exchange": market.exchange,
        "market_type": market.market_type,
        "symbol": market.symbol,
        "base_asset": market.base_asset,
        "quote_asset": market.quote_asset,
        "market_mapping_status": "EXPLICIT",
        "event_time": event_time.isoformat(),
        "available_time": available_time.isoformat(),
        "ingestion_time": ingestion_time.isoformat(),
        "source_snapshot_id": source_snapshot_id,
        "source": _required(raw.get("source"), "source"),
        "best_bid": best_bid,
        "best_ask": best_ask,
        "mid_price": mid_price,
        "spread_bps": spread_bps,
        "bid_depth_quote": bid_depth,
        "ask_depth_quote": ask_depth,
        "latency_ms": latency,
        "temporal_status": temporal_status,
        "runtime_parity_proven": False,
        "exchange_clock_ahead_seconds": clock_ahead_seconds,
        "data_quality_status": "FORWARD_PUBLIC_REST_RESEARCH_ONLY",
        "raw_source_path": raw_source_path,
        "raw_source_sha256": raw_source_sha256,
        "raw_source_row_number": raw_source_row_number,
    }


def fingerprint_canonical_microstructure_rows(rows: Sequence[Mapping[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in sorted(rows, key=_canonical_sort_key):
        stable = {field: row.get(field) for field in CANONICAL_MICROSTRUCTURE_FIELDS if field != "raw_source_path"}
        digest.update(json.dumps(stable, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def render_canonical_microstructure_report(snapshot: CanonicalMicrostructureSnapshot) -> str:
    lines = [
        f"# Canonical Microstructure Snapshot - {snapshot.run_id}",
        "",
        f"Snapshot: `{snapshot.snapshot_id}`",
        f"Fingerprint: `{snapshot.fingerprint}`",
        f"Rows: `{snapshot.canonical_row_count}` canonical / `{snapshot.raw_row_count}` raw",
        f"Duplicates removed: `{snapshot.duplicate_count}`",
        f"Quarantined: `{snapshot.quarantine_count}`",
        f"Period: `{snapshot.start_at or 'none'}` → `{snapshot.end_at or 'none'}`",
        f"Symbols: `{', '.join(snapshot.symbols) or 'none'}`",
        "",
        "## Boundary",
        "",
        "- Explicit Kraken base/quote mappings only; no implicit quote conversion.",
        "- `event_time`, `available_time`, and `ingestion_time` are UTC and contract-validated.",
        "- Public REST captures remain research-only; runtime-feed parity is not claimed.",
        "- No shadow, paper, live, order, or promotion permission is created.",
        "",
    ]
    return "\n".join(lines)


def _write_snapshot_artifacts(
    snapshot: CanonicalMicrostructureSnapshot,
    snapshot_dir: Path,
    manifest_dir: Path,
    report_dir: Path,
) -> CanonicalMicrostructureSnapshot:
    manifest_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / f"{snapshot.run_id}_canonical_microstructure.json"
    report_path = report_dir / f"{snapshot.run_id}_canonical_microstructure.md"
    completed = CanonicalMicrostructureSnapshot(
        **{
            **snapshot.__dict__,
            "manifest_path": str(manifest_path),
            "report_path": str(report_path),
        }
    )
    payload = json.dumps(completed.to_dict(), indent=2, sort_keys=True)
    manifest_path.write_text(payload, encoding="utf-8")
    (snapshot_dir / "manifest.json").write_text(payload, encoding="utf-8")
    report_path.write_text(render_canonical_microstructure_report(completed), encoding="utf-8")
    return completed


def _collect_csv_files(paths: Iterable[Path], *, max_files: int | None) -> tuple[Path, ...]:
    discovered: list[Path] = []
    for path in paths:
        if path.is_dir():
            discovered.extend(candidate for candidate in path.rglob("*.csv") if candidate.is_file())
        elif path.is_file() and path.suffix.lower() == ".csv":
            discovered.append(path)
    ordered = tuple(sorted({candidate.resolve() for candidate in discovered}, key=lambda item: str(item)))
    if max_files is not None:
        return ordered[:max_files]
    return ordered


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CANONICAL_MICROSTRUCTURE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_utc(value: Any, field_name: str) -> datetime:
    text = _required(value, field_name)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name}_invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name}_naive")
    return parsed.astimezone(timezone.utc)


def _required(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name}_missing")
    return text


def _positive_finite(value: Any, field_name: str) -> float:
    number = _finite(value, field_name)
    if number <= 0.0:
        raise ValueError(f"{field_name}_not_positive")
    return number


def _non_negative_finite(value: Any, field_name: str) -> float:
    number = _finite(value, field_name)
    if number < 0.0:
        raise ValueError(f"{field_name}_negative")
    return number


def _finite(value: Any, field_name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name}_invalid") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field_name}_not_finite")
    return number


def _as_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def _canonical_sort_key(row: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(row.get("event_time") or ""),
        str(row.get("symbol") or ""),
        str(row.get("ingestion_time") or ""),
        str(row.get("source_snapshot_id") or ""),
    )
