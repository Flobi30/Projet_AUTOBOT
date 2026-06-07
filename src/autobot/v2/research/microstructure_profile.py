"""Microstructure profile builder for AUTOBOT research.

The profile reads research CSV snapshots produced by ``spread_depth_recorder``.
It is read-only, does not call Kraken, and cannot create orders.
"""

from __future__ import annotations

import csv
import json
import statistics
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


@dataclass(frozen=True)
class MicrostructureSymbolProfile:
    symbol: str
    sample_count: int
    median_spread_bps: float
    p75_spread_bps: float
    p95_spread_bps: float
    p99_spread_bps: float
    median_bid_depth_eur: float
    median_ask_depth_eur: float
    p95_latency_ms: float
    cost_risk_status: str
    recommended_research_spread_bps: float
    recommended_stress_spread_bps: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MicrostructureProfileReport:
    run_id: str
    generated_at: str
    source_paths: tuple[str, ...]
    profiles: tuple[MicrostructureSymbolProfile, ...]
    json_report_path: str | None = None
    markdown_report_path: str | None = None
    safety_notes: tuple[str, ...] = (
        "Microstructure profile is research-only.",
        "Profile reads local CSV snapshots only.",
        "No API key is read or exposed.",
        "No paper or live order is created.",
        "No live trading permission is granted.",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "source_paths": list(self.source_paths),
            "profiles": [profile.to_dict() for profile in self.profiles],
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
            "safety_notes": list(self.safety_notes),
        }


def build_microstructure_profile(
    paths: Iterable[str | Path],
    *,
    run_id: str,
) -> MicrostructureProfileReport:
    path_tuple = tuple(Path(path) for path in paths)
    rows = _load_rows(path_tuple)
    profiles: list[MicrostructureSymbolProfile] = []
    for symbol in sorted({str(row["symbol"]).upper() for row in rows}):
        symbol_rows = [row for row in rows if str(row["symbol"]).upper() == symbol]
        profiles.append(_profile_symbol(symbol, symbol_rows))
    return MicrostructureProfileReport(
        run_id=run_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        source_paths=tuple(str(path) for path in path_tuple),
        profiles=tuple(profiles),
    )


def write_microstructure_profile_report(
    report: MicrostructureProfileReport,
    output_dir: str | Path,
) -> MicrostructureProfileReport:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / f"{report.run_id}.json"
    markdown_path = output_path / f"{report.run_id}.md"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(render_microstructure_profile_report(report), encoding="utf-8")
    return MicrostructureProfileReport(
        run_id=report.run_id,
        generated_at=report.generated_at,
        source_paths=report.source_paths,
        profiles=report.profiles,
        json_report_path=str(json_path),
        markdown_report_path=str(markdown_path),
        safety_notes=report.safety_notes,
    )


def render_microstructure_profile_report(report: MicrostructureProfileReport) -> str:
    lines = [
        f"# Microstructure Profile - {report.run_id}",
        "",
        f"Generated at: `{report.generated_at}`",
        "",
        "## Profiles",
        "",
        "| Symbol | Samples | Median Spread | P75 Spread | P95 Spread | P99 Spread | Median Bid Depth | Median Ask Depth | P95 Latency | Cost Risk | Research Spread | Stress Spread |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: |",
    ]
    for profile in report.profiles:
        lines.append(
            f"| {profile.symbol} | {profile.sample_count} | {profile.median_spread_bps:.6f} | "
            f"{profile.p75_spread_bps:.6f} | {profile.p95_spread_bps:.6f} | {profile.p99_spread_bps:.6f} | "
            f"{profile.median_bid_depth_eur:.6f} | {profile.median_ask_depth_eur:.6f} | "
            f"{profile.p95_latency_ms:.6f} | {profile.cost_risk_status} | "
            f"{profile.recommended_research_spread_bps:.6f} | {profile.recommended_stress_spread_bps:.6f} |"
        )
    lines.extend(["", "## Safety", ""])
    lines.extend(f"- {note}" for note in report.safety_notes)
    lines.append("")
    return "\n".join(lines)


def _load_rows(paths: Iterable[str | Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw_path in paths:
        path = Path(raw_path)
        if not path.exists():
            continue
        with path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                if row.get("symbol"):
                    rows.append(dict(row))
    return rows


def _profile_symbol(symbol: str, rows: Sequence[dict[str, Any]]) -> MicrostructureSymbolProfile:
    spreads = [_safe_float(row.get("spread_bps")) for row in rows]
    spreads = [value for value in spreads if value is not None]
    bid_depths = [_safe_float(row.get("bid_depth_eur")) for row in rows]
    bid_depths = [value for value in bid_depths if value is not None]
    ask_depths = [_safe_float(row.get("ask_depth_eur")) for row in rows]
    ask_depths = [value for value in ask_depths if value is not None]
    latencies = [_safe_float(row.get("latency_ms")) for row in rows]
    latencies = [value for value in latencies if value is not None]
    median_spread = statistics.median(spreads) if spreads else 0.0
    p75_spread = _quantile(spreads, 0.75)
    p95_spread = _quantile(spreads, 0.95)
    p99_spread = _quantile(spreads, 0.99)
    median_bid_depth = statistics.median(bid_depths) if bid_depths else 0.0
    median_ask_depth = statistics.median(ask_depths) if ask_depths else 0.0
    p95_latency = _quantile(latencies, 0.95)
    return MicrostructureSymbolProfile(
        symbol=symbol,
        sample_count=len(rows),
        median_spread_bps=median_spread,
        p75_spread_bps=p75_spread,
        p95_spread_bps=p95_spread,
        p99_spread_bps=p99_spread,
        median_bid_depth_eur=median_bid_depth,
        median_ask_depth_eur=median_ask_depth,
        p95_latency_ms=p95_latency,
        cost_risk_status=_cost_risk_status(p95_spread, median_bid_depth, median_ask_depth, p95_latency),
        recommended_research_spread_bps=max(median_spread, p75_spread),
        recommended_stress_spread_bps=max(p95_spread, p99_spread),
    )


def _cost_risk_status(
    p95_spread_bps: float,
    median_bid_depth_eur: float,
    median_ask_depth_eur: float,
    p95_latency_ms: float,
) -> str:
    min_depth = min(median_bid_depth_eur, median_ask_depth_eur)
    if p95_spread_bps >= 80.0 or min_depth <= 50.0 or p95_latency_ms >= 5_000.0:
        return "avoid"
    if p95_spread_bps >= 40.0 or min_depth <= 250.0 or p95_latency_ms >= 2_000.0:
        return "expensive"
    if p95_spread_bps <= 15.0 and min_depth >= 1_000.0 and p95_latency_ms <= 1_000.0:
        return "cheap"
    return "normal"


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _quantile(values: Sequence[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * q))))
    return ordered[index]
