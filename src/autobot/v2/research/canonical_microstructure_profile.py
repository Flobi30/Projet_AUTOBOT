"""Read-only cost and capacity evidence from canonical microstructure snapshots.

This module consumes only point-in-time canonical top-of-book captures. It
does not contact Kraken, update a cost profile, create an order, or grant
shadow, paper, or live permission. Public REST captures are useful for
conservative research calibration only after enough cross-session coverage has
accumulated; they never prove runtime-feed parity.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from autobot.v2.contracts import MarketIdentity


CANONICAL_MICROSTRUCTURE_FILE_NAME = "kraken_spot_microstructure.csv"
PROFILE_FINGERPRINT_FIELDS = (
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
    "data_quality_status",
)


class CanonicalMicrostructureProfileError(ValueError):
    """Raised when canonical microstructure inputs are structurally invalid."""


@dataclass(frozen=True)
class CanonicalMicrostructureProfileConfig:
    """Explicit coverage requirements for research-only calibration evidence."""

    run_id: str
    canonical_paths: tuple[Path, ...]
    output_dir: Path = Path("reports/research/canonical_microstructure_profiles")
    min_samples_per_symbol: int = 96
    min_distinct_utc_hours: int = 12
    min_observation_span: timedelta = timedelta(hours=24)

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise CanonicalMicrostructureProfileError("run_id must not be empty")
        if not self.canonical_paths:
            raise CanonicalMicrostructureProfileError("canonical_paths must not be empty")
        if self.min_samples_per_symbol <= 0:
            raise CanonicalMicrostructureProfileError("min_samples_per_symbol must be positive")
        if not 1 <= self.min_distinct_utc_hours <= 24:
            raise CanonicalMicrostructureProfileError("min_distinct_utc_hours must be in [1, 24]")
        if self.min_observation_span <= timedelta(0):
            raise CanonicalMicrostructureProfileError("min_observation_span must be positive")


@dataclass(frozen=True)
class CanonicalMicrostructureSymbolProfile:
    """Per-market descriptive evidence, never an execution configuration."""

    symbol: str
    base_asset: str
    quote_asset: str
    sample_count: int
    distinct_utc_hours: int
    first_event_time: str
    last_event_time: str
    observation_span_seconds: float
    median_spread_bps: float
    p75_spread_bps: float
    p95_spread_bps: float
    p99_spread_bps: float
    median_bid_depth_eur: float
    median_ask_depth_eur: float
    p95_latency_ms: float
    observed_research_spread_bps: float
    observed_stress_spread_bps: float
    calibration_status: str
    reasons: tuple[str, ...] = ()
    runtime_parity_proven: bool = False
    execution_eligible: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reasons"] = list(self.reasons)
        return payload


@dataclass(frozen=True)
class CanonicalMicrostructureProfileReport:
    run_id: str
    generated_at: str
    source_paths: tuple[str, ...]
    source_fingerprint: str
    raw_row_count: int
    accepted_row_count: int
    duplicate_row_count: int
    rejected_row_count: int
    status: str
    profiles: tuple[CanonicalMicrostructureSymbolProfile, ...]
    rejected_reasons: Mapping[str, int] = field(default_factory=dict)
    json_report_path: str | None = None
    markdown_report_path: str | None = None
    runtime_parity_proven: bool = False
    execution_eligible: bool = False
    safety_notes: tuple[str, ...] = (
        "Read-only research profile from canonical public REST top-of-book captures.",
        "Observed values are descriptive evidence, not an automatic cost-model update.",
        "Public REST captures do not prove runtime-feed parity.",
        "No paper or live order, capital allocation, promotion, or runtime routing is created.",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "source_paths": list(self.source_paths),
            "source_fingerprint": self.source_fingerprint,
            "raw_row_count": self.raw_row_count,
            "accepted_row_count": self.accepted_row_count,
            "duplicate_row_count": self.duplicate_row_count,
            "rejected_row_count": self.rejected_row_count,
            "status": self.status,
            "profiles": [profile.to_dict() for profile in self.profiles],
            "rejected_reasons": dict(self.rejected_reasons),
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
            "runtime_parity_proven": self.runtime_parity_proven,
            "execution_eligible": self.execution_eligible,
            "safety_notes": list(self.safety_notes),
        }


def build_canonical_microstructure_profile(
    config: CanonicalMicrostructureProfileConfig,
) -> CanonicalMicrostructureProfileReport:
    """Build deterministic point-in-time profile evidence from canonical data."""

    paths = _collect_canonical_csv_paths(config.canonical_paths)
    rows_by_source_id: dict[str, dict[str, Any]] = {}
    raw_row_count = 0
    duplicate_row_count = 0
    rejected_reasons: dict[str, int] = {}

    for path in paths:
        with path.open("r", newline="", encoding="utf-8") as handle:
            for raw in csv.DictReader(handle):
                raw_row_count += 1
                try:
                    row = _normalize_canonical_row(raw)
                except CanonicalMicrostructureProfileError as exc:
                    _increment(rejected_reasons, str(exc))
                    continue
                source_id = str(row["source_snapshot_id"])
                prior = rows_by_source_id.get(source_id)
                if prior is None:
                    rows_by_source_id[source_id] = row
                elif _row_fingerprint(prior) == _row_fingerprint(row):
                    duplicate_row_count += 1
                else:
                    _increment(rejected_reasons, "source_snapshot_id_conflict")

    rows = sorted(rows_by_source_id.values(), key=_row_sort_key)
    profiles = tuple(
        _profile_symbol(symbol, [row for row in rows if str(row["symbol"]) == symbol], config)
        for symbol in sorted({str(row["symbol"]) for row in rows})
    )
    if not rows:
        status = "DATA_MISSING"
    elif rejected_reasons:
        status = "DATA_QUALITY_REVIEW_REQUIRED"
    elif all(profile.calibration_status == "RESEARCH_CALIBRATION_READY" for profile in profiles):
        status = "RESEARCH_CALIBRATION_READY"
    else:
        status = "WAITING_FOR_MORE_DATA"
    return CanonicalMicrostructureProfileReport(
        run_id=config.run_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        source_paths=tuple(str(path) for path in paths),
        source_fingerprint=_fingerprint_rows(rows),
        raw_row_count=raw_row_count,
        accepted_row_count=len(rows),
        duplicate_row_count=duplicate_row_count,
        rejected_row_count=sum(rejected_reasons.values()),
        status=status,
        profiles=profiles,
        rejected_reasons=dict(sorted(rejected_reasons.items())),
    )


def write_canonical_microstructure_profile_report(
    report: CanonicalMicrostructureProfileReport,
    output_dir: str | Path,
) -> CanonicalMicrostructureProfileReport:
    """Persist compact decision evidence without modifying source snapshots."""

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / f"{report.run_id}.json"
    markdown_path = destination / f"{report.run_id}.md"
    completed = replace(report, json_report_path=str(json_path), markdown_report_path=str(markdown_path))
    json_path.write_text(json.dumps(completed.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(render_canonical_microstructure_profile_report(completed), encoding="utf-8")
    return completed


def render_canonical_microstructure_profile_report(report: CanonicalMicrostructureProfileReport) -> str:
    lines = [
        f"# Canonical Microstructure Research Profile - {report.run_id}",
        "",
        f"Status: {report.status}",
        f"Source fingerprint: {report.source_fingerprint}",
        f"Rows: {report.accepted_row_count} accepted / {report.raw_row_count} raw / "
        f"{report.duplicate_row_count} duplicate / {report.rejected_row_count} rejected",
        "",
        "## Symbol Coverage",
        "",
        "| Symbol | Samples | UTC Hours | Span h | P75 Spread bps | P95 Spread bps | Median Bid Depth EUR | Median Ask Depth EUR | P95 Latency ms | Status | Reasons |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for profile in report.profiles:
        lines.append(
            f"| {profile.symbol} | {profile.sample_count} | {profile.distinct_utc_hours} | "
            f"{profile.observation_span_seconds / 3600.0:.2f} | {profile.p75_spread_bps:.6f} | "
            f"{profile.p95_spread_bps:.6f} | {profile.median_bid_depth_eur:.6f} | "
            f"{profile.median_ask_depth_eur:.6f} | {profile.p95_latency_ms:.6f} | "
            f"{profile.calibration_status} | {', '.join(profile.reasons) or 'none'} |"
        )
    if report.rejected_reasons:
        lines.extend(["", "## Rejected Rows", ""])
        lines.extend(f"- {reason}: {count}" for reason, count in report.rejected_reasons.items())
    lines.extend(["", "## Safety", ""])
    lines.extend(f"- {note}" for note in report.safety_notes)
    lines.append("")
    return "\n".join(lines)


def _profile_symbol(
    symbol: str,
    rows: Sequence[Mapping[str, Any]],
    config: CanonicalMicrostructureProfileConfig,
) -> CanonicalMicrostructureSymbolProfile:
    ordered = sorted(rows, key=_row_sort_key)
    first = _parse_utc(ordered[0]["event_time"], "event_time")
    last = _parse_utc(ordered[-1]["event_time"], "event_time")
    span = max(timedelta(0), last - first)
    distinct_hours = len({_parse_utc(row["event_time"], "event_time").hour for row in ordered})
    spreads = [float(row["spread_bps"]) for row in ordered]
    bid_depths = [float(row["bid_depth_quote"]) for row in ordered]
    ask_depths = [float(row["ask_depth_quote"]) for row in ordered]
    latencies = [float(row["latency_ms"]) for row in ordered]
    reasons: list[str] = []
    if len(ordered) < config.min_samples_per_symbol:
        reasons.append("sample_count_below_minimum")
    if distinct_hours < config.min_distinct_utc_hours:
        reasons.append("utc_hour_coverage_below_minimum")
    if span < config.min_observation_span:
        reasons.append("observation_span_below_minimum")
    status = "RESEARCH_CALIBRATION_READY" if not reasons else "WAITING_FOR_MORE_DATA"
    return CanonicalMicrostructureSymbolProfile(
        symbol=symbol,
        base_asset=str(ordered[0]["base_asset"]),
        quote_asset=str(ordered[0]["quote_asset"]),
        sample_count=len(ordered),
        distinct_utc_hours=distinct_hours,
        first_event_time=first.isoformat(),
        last_event_time=last.isoformat(),
        observation_span_seconds=span.total_seconds(),
        median_spread_bps=statistics.median(spreads),
        p75_spread_bps=_quantile(spreads, 0.75),
        p95_spread_bps=_quantile(spreads, 0.95),
        p99_spread_bps=_quantile(spreads, 0.99),
        median_bid_depth_eur=statistics.median(bid_depths),
        median_ask_depth_eur=statistics.median(ask_depths),
        p95_latency_ms=_quantile(latencies, 0.95),
        observed_research_spread_bps=max(statistics.median(spreads), _quantile(spreads, 0.75)),
        observed_stress_spread_bps=max(_quantile(spreads, 0.95), _quantile(spreads, 0.99)),
        calibration_status=status,
        reasons=tuple(reasons),
    )


def _collect_canonical_csv_paths(paths: Iterable[Path]) -> tuple[Path, ...]:
    discovered: list[Path] = []
    for candidate in paths:
        path = Path(candidate)
        if path.is_dir():
            discovered.extend(path.rglob(CANONICAL_MICROSTRUCTURE_FILE_NAME))
        elif path.is_file() and path.suffix.lower() == ".csv":
            discovered.append(path)
    return tuple(sorted({item.resolve() for item in discovered}, key=lambda item: str(item)))


def _normalize_canonical_row(raw: Mapping[str, Any]) -> dict[str, Any]:
    if _required(raw.get("schema_version"), "schema_version") != "1":
        raise CanonicalMicrostructureProfileError("unsupported_schema_version")
    exchange = _required(raw.get("exchange"), "exchange").lower()
    market_type = _required(raw.get("market_type"), "market_type").lower()
    if exchange != "kraken" or market_type != "spot":
        raise CanonicalMicrostructureProfileError("unsupported_market_identity")
    if _required(raw.get("market_mapping_status"), "market_mapping_status") != "EXPLICIT":
        raise CanonicalMicrostructureProfileError("market_mapping_not_explicit")
    market = MarketIdentity(
        exchange=exchange,
        market_type=market_type,
        symbol=_required(raw.get("symbol"), "symbol"),
        base_asset=_required(raw.get("base_asset"), "base_asset"),
        quote_asset=_required(raw.get("quote_asset"), "quote_asset"),
    )
    if market.quote_asset != "EUR":
        raise CanonicalMicrostructureProfileError("quote_conversion_not_explicitly_supported")
    if _as_bool(raw.get("runtime_parity_proven")):
        raise CanonicalMicrostructureProfileError("rest_capture_cannot_claim_runtime_parity")
    if _required(raw.get("temporal_status"), "temporal_status") != "FORWARD_PUBLIC_REST_INGESTED":
        raise CanonicalMicrostructureProfileError("temporal_status_not_forward_rest")
    if _required(raw.get("data_quality_status"), "data_quality_status") != "FORWARD_PUBLIC_REST_RESEARCH_ONLY":
        raise CanonicalMicrostructureProfileError("data_quality_status_not_research_only")
    event_time = _parse_utc(raw.get("event_time"), "event_time")
    available_time = _parse_utc(raw.get("available_time"), "available_time")
    ingestion_time = _parse_utc(raw.get("ingestion_time"), "ingestion_time")
    if event_time > available_time:
        raise CanonicalMicrostructureProfileError("event_time_after_available_time")
    if available_time > ingestion_time:
        raise CanonicalMicrostructureProfileError("available_time_after_ingestion_time")
    bid = _positive_finite(raw.get("best_bid"), "best_bid")
    ask = _positive_finite(raw.get("best_ask"), "best_ask")
    if ask < bid:
        raise CanonicalMicrostructureProfileError("best_ask_before_best_bid")
    mid = _positive_finite(raw.get("mid_price"), "mid_price")
    spread = _non_negative_finite(raw.get("spread_bps"), "spread_bps")
    bid_depth = _non_negative_finite(raw.get("bid_depth_quote"), "bid_depth_quote")
    ask_depth = _non_negative_finite(raw.get("ask_depth_quote"), "ask_depth_quote")
    latency = _non_negative_finite(raw.get("latency_ms"), "latency_ms")
    expected_mid = (bid + ask) / 2.0
    expected_spread = ((ask - bid) / expected_mid) * 10_000.0
    if not math.isclose(mid, expected_mid, rel_tol=1e-9, abs_tol=1e-9):
        raise CanonicalMicrostructureProfileError("mid_price_inconsistent_with_best_quotes")
    if not math.isclose(spread, expected_spread, rel_tol=1e-7, abs_tol=1e-7):
        raise CanonicalMicrostructureProfileError("spread_bps_inconsistent_with_best_quotes")
    return {
        "schema_version": 1,
        "exchange": market.exchange,
        "market_type": market.market_type,
        "symbol": market.symbol,
        "base_asset": market.base_asset,
        "quote_asset": market.quote_asset,
        "market_mapping_status": "EXPLICIT",
        "event_time": event_time.isoformat(),
        "available_time": available_time.isoformat(),
        "ingestion_time": ingestion_time.isoformat(),
        "source_snapshot_id": _required(raw.get("source_snapshot_id"), "source_snapshot_id"),
        "source": _required(raw.get("source"), "source"),
        "best_bid": bid,
        "best_ask": ask,
        "mid_price": mid,
        "spread_bps": spread,
        "bid_depth_quote": bid_depth,
        "ask_depth_quote": ask_depth,
        "latency_ms": latency,
        "temporal_status": "FORWARD_PUBLIC_REST_INGESTED",
        "runtime_parity_proven": False,
        "data_quality_status": "FORWARD_PUBLIC_REST_RESEARCH_ONLY",
    }


def _fingerprint_rows(rows: Sequence[Mapping[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in sorted(rows, key=_row_sort_key):
        digest.update(_row_fingerprint(row).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _row_fingerprint(row: Mapping[str, Any]) -> str:
    stable = {field: row.get(field) for field in PROFILE_FINGERPRINT_FIELDS}
    return hashlib.sha256(
        json.dumps(stable, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _row_sort_key(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("event_time") or ""),
        str(row.get("symbol") or ""),
        str(row.get("source_snapshot_id") or ""),
    )


def _parse_utc(value: Any, field_name: str) -> datetime:
    text = _required(value, field_name)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CanonicalMicrostructureProfileError(f"{field_name}_invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CanonicalMicrostructureProfileError(f"{field_name}_naive")
    return parsed.astimezone(timezone.utc)


def _required(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise CanonicalMicrostructureProfileError(f"{field_name}_missing")
    return text


def _positive_finite(value: Any, field_name: str) -> float:
    number = _finite(value, field_name)
    if number <= 0.0:
        raise CanonicalMicrostructureProfileError(f"{field_name}_not_positive")
    return number


def _non_negative_finite(value: Any, field_name: str) -> float:
    number = _finite(value, field_name)
    if number < 0.0:
        raise CanonicalMicrostructureProfileError(f"{field_name}_negative")
    return number


def _finite(value: Any, field_name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise CanonicalMicrostructureProfileError(f"{field_name}_invalid") from exc
    if not math.isfinite(number):
        raise CanonicalMicrostructureProfileError(f"{field_name}_not_finite")
    return number


def _as_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def _quantile(values: Sequence[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * q))))
    return ordered[index]


def _increment(counter: dict[str, int], key: str) -> None:
    counter[key] = counter.get(key, 0) + 1
