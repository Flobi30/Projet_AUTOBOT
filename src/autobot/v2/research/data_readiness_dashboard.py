"""Research data-readiness dashboard for AUTOBOT datasets.

The dashboard is a generated Markdown/JSON report. It is read-only and never
starts or modifies paper/live trading.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from .data_quality_report import DataQualityFileReport, analyze_dataset_files
from .microstructure_profile import MicrostructureSymbolProfile


@dataclass(frozen=True)
class DataReadinessRow:
    symbol: str
    timeframe: str
    coverage_days: float
    bar_count: int
    gap_count: int
    duplicate_count_final: int
    zero_volume_ratio: float
    bid_ask_coverage: float
    depth_coverage: float
    usability_tier: str
    batch_validation_ready: bool
    paper_candidate_review_ready: bool
    microstructure_status: str
    live_promotion_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DataReadinessDashboardReport:
    run_id: str
    generated_at: str
    rows: tuple[DataReadinessRow, ...]
    json_report_path: str | None = None
    markdown_report_path: str | None = None
    safety_notes: tuple[str, ...] = (
        "Data readiness dashboard is research-only.",
        "No runtime paper/live service is started.",
        "No paper or live order is created.",
        "No strategy is promoted.",
        "No live trading permission is granted.",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "rows": [row.to_dict() for row in self.rows],
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
            "safety_notes": list(self.safety_notes),
        }


def build_data_readiness_dashboard(
    *,
    run_id: str,
    dataset_paths: Iterable[str | Path],
    default_timeframe: str = "unknown",
    microstructure_profiles: Sequence[MicrostructureSymbolProfile] = (),
) -> DataReadinessDashboardReport:
    file_reports = analyze_dataset_files(dataset_paths, default_timeframe=default_timeframe)
    profile_by_symbol = {profile.symbol.upper(): profile for profile in microstructure_profiles}
    rows = tuple(_rows_from_file_reports(file_reports, profile_by_symbol))
    return DataReadinessDashboardReport(
        run_id=run_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        rows=rows,
    )


def write_data_readiness_dashboard(
    report: DataReadinessDashboardReport,
    output_dir: str | Path,
) -> DataReadinessDashboardReport:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / f"data_readiness_dashboard_{report.run_id}.json"
    markdown_path = output_path / f"data_readiness_dashboard_{report.run_id}.md"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(render_data_readiness_dashboard(report), encoding="utf-8")
    return DataReadinessDashboardReport(
        run_id=report.run_id,
        generated_at=report.generated_at,
        rows=report.rows,
        json_report_path=str(json_path),
        markdown_report_path=str(markdown_path),
        safety_notes=report.safety_notes,
    )


def render_data_readiness_dashboard(report: DataReadinessDashboardReport) -> str:
    lines = [
        f"# Data Readiness Dashboard - {report.run_id}",
        "",
        f"Generated at: `{report.generated_at}`",
        "",
        "## Readiness",
        "",
        "| Symbol | Timeframe | Days | Bars | Gaps | Duplicates | Zero Vol | Bid/Ask Cov | Depth Cov | Tier | Batch Ready | Paper Candidate Ready | Microstructure | Live Allowed |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- | --- | --- |",
    ]
    for row in sorted(report.rows, key=lambda item: (item.symbol, item.timeframe)):
        lines.append(
            f"| {row.symbol} | {row.timeframe} | {row.coverage_days:.3f} | {row.bar_count} | "
            f"{row.gap_count} | {row.duplicate_count_final} | {row.zero_volume_ratio:.3f} | "
            f"{row.bid_ask_coverage:.3f} | {row.depth_coverage:.3f} | {row.usability_tier} | "
            f"{'yes' if row.batch_validation_ready else 'no'} | "
            f"{'yes' if row.paper_candidate_review_ready else 'no'} | {row.microstructure_status} | "
            f"{'yes' if row.live_promotion_allowed else 'no'} |"
        )
    lines.extend(["", "## Safety", ""])
    lines.extend(f"- {note}" for note in report.safety_notes)
    lines.append("")
    return "\n".join(lines)


def _rows_from_file_reports(
    file_reports: Sequence[DataQualityFileReport],
    profile_by_symbol: dict[str, MicrostructureSymbolProfile],
) -> list[DataReadinessRow]:
    rows: list[DataReadinessRow] = []
    for report in file_reports:
        symbols = report.symbols or ("UNKNOWN",)
        timeframes = report.timeframes or ("unknown",)
        for symbol in symbols:
            profile = profile_by_symbol.get(symbol.upper())
            microstructure_status = profile.cost_risk_status if profile else "missing"
            batch_ready = report.final_usability_tier in {
                "ready_for_batch_validation",
                "ready_for_paper_candidate_review",
            }
            paper_ready = report.final_usability_tier == "ready_for_paper_candidate_review" or (
                batch_ready and profile is not None and profile.cost_risk_status != "avoid"
            )
            for timeframe in timeframes:
                rows.append(
                    DataReadinessRow(
                        symbol=symbol,
                        timeframe=timeframe,
                        coverage_days=report.coverage_days,
                        bar_count=report.row_count,
                        gap_count=report.gap_count,
                        duplicate_count_final=report.duplicate_count,
                        zero_volume_ratio=report.zero_volume_ratio,
                        bid_ask_coverage=report.bid_ask_coverage,
                        depth_coverage=report.depth_coverage,
                        usability_tier=report.final_usability_tier,
                        batch_validation_ready=batch_ready,
                        paper_candidate_review_ready=paper_ready,
                        microstructure_status=microstructure_status,
                        live_promotion_allowed=False,
                    )
                )
    return rows
