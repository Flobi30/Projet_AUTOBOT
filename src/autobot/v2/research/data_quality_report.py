"""Research data-quality reporting for AUTOBOT datasets.

This module is read-only and research-only. It never starts runtime services,
never submits orders, and never mutates production state.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from .dataset_builder import parse_timeframe_seconds
from .market_data_repository import MarketBar, MarketDataQualityReport, MarketDataRepository


@dataclass(frozen=True)
class DataQualityFileReport:
    source_path: str
    source_type: str
    row_count: int
    symbols: tuple[str, ...]
    timeframes: tuple[str, ...]
    start_at: str | None
    end_at: str | None
    duplicate_count: int
    gap_count: int
    max_gap_seconds: float
    invalid_ohlc_count: int
    zero_volume_count: int
    volume_status: str
    has_bid_ask: bool
    has_depth: bool
    usable_for_backtest: bool
    exclusions: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["symbols"] = list(self.symbols)
        payload["timeframes"] = list(self.timeframes)
        payload["exclusions"] = list(self.exclusions)
        payload["warnings"] = list(self.warnings)
        return payload


@dataclass(frozen=True)
class DataFoundationReadinessReport:
    run_id: str
    generated_at: str
    files: tuple[DataQualityFileReport, ...]
    usable_file_count: int
    unusable_file_count: int
    symbol_coverage: dict[str, dict[str, Any]]
    overall_status: str
    recommendations: tuple[str, ...]
    json_report_path: str | None = None
    markdown_report_path: str | None = None
    safety_notes: tuple[str, ...] = (
        "Research data-quality report only.",
        "No runtime paper/live service is started.",
        "No paper or live order is created.",
        "No Kraken order can be created by this report.",
        "No live trading permission is granted.",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "files": [item.to_dict() for item in self.files],
            "usable_file_count": self.usable_file_count,
            "unusable_file_count": self.unusable_file_count,
            "symbol_coverage": self.symbol_coverage,
            "overall_status": self.overall_status,
            "recommendations": list(self.recommendations),
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
            "safety_notes": list(self.safety_notes),
        }


def analyze_bars(
    bars: Sequence[MarketBar],
    *,
    source_path: str,
    source_type: str,
    expected_interval_seconds: float | None = None,
) -> DataQualityFileReport:
    """Analyze one in-memory OHLCV dataset."""

    repository = MarketDataRepository()
    quality = repository.validate(bars, expected_interval_seconds=expected_interval_seconds)
    zero_volume_count = sum(1 for bar in bars if float(bar.volume) <= 0.0)
    has_bid_ask = any(_metadata_has_any(bar, ("bid", "ask", "best_bid", "best_ask")) for bar in bars)
    has_depth = any(
        _metadata_has_any(bar, ("depth", "order_book", "book_depth", "depth_eur", "liquidity_eur"))
        for bar in bars
    )
    volume_status = _volume_status(bars, zero_volume_count)
    exclusions, warnings = _quality_classification(quality, bars, volume_status)
    return DataQualityFileReport(
        source_path=source_path,
        source_type=source_type,
        row_count=quality.row_count,
        symbols=quality.symbols,
        timeframes=quality.timeframes,
        start_at=quality.start_at.isoformat() if quality.start_at else None,
        end_at=quality.end_at.isoformat() if quality.end_at else None,
        duplicate_count=quality.duplicate_count,
        gap_count=quality.gap_count,
        max_gap_seconds=quality.max_gap_seconds,
        invalid_ohlc_count=quality.invalid_ohlc_count,
        zero_volume_count=zero_volume_count,
        volume_status=volume_status,
        has_bid_ask=has_bid_ask,
        has_depth=has_depth,
        usable_for_backtest=not exclusions,
        exclusions=tuple(exclusions),
        warnings=tuple(dict.fromkeys([*quality.warnings, *warnings])),
    )


def analyze_dataset_files(
    paths: Iterable[str | Path],
    *,
    default_timeframe: str = "unknown",
) -> tuple[DataQualityFileReport, ...]:
    """Load and analyze CSV/Parquet research datasets."""

    repository = MarketDataRepository()
    reports: list[DataQualityFileReport] = []
    expected_seconds = _expected_seconds(default_timeframe)
    for raw_path in paths:
        path = Path(raw_path)
        if not path.exists():
            reports.append(
                DataQualityFileReport(
                    source_path=str(path),
                    source_type="missing",
                    row_count=0,
                    symbols=(),
                    timeframes=(),
                    start_at=None,
                    end_at=None,
                    duplicate_count=0,
                    gap_count=0,
                    max_gap_seconds=0.0,
                    invalid_ohlc_count=0,
                    zero_volume_count=0,
                    volume_status="unknown",
                    has_bid_ask=False,
                    has_depth=False,
                    usable_for_backtest=False,
                    exclusions=("dataset_file_missing",),
                    warnings=("dataset_file_missing",),
                )
            )
            continue
        suffix = path.suffix.lower()
        try:
            if suffix == ".csv":
                bars = repository.load_csv(path, default_timeframe=default_timeframe)
                source_type = "csv"
            elif suffix == ".parquet":
                bars = repository.load_parquet(path, default_timeframe=default_timeframe)
                source_type = "parquet"
            else:
                raise ValueError(f"unsupported dataset suffix: {suffix}")
        except Exception as exc:
            reports.append(
                DataQualityFileReport(
                    source_path=str(path),
                    source_type=suffix.lstrip(".") or "unknown",
                    row_count=0,
                    symbols=(),
                    timeframes=(),
                    start_at=None,
                    end_at=None,
                    duplicate_count=0,
                    gap_count=0,
                    max_gap_seconds=0.0,
                    invalid_ohlc_count=0,
                    zero_volume_count=0,
                    volume_status="unknown",
                    has_bid_ask=False,
                    has_depth=False,
                    usable_for_backtest=False,
                    exclusions=("dataset_load_failed",),
                    warnings=(f"dataset_load_failed:{exc}",),
                )
            )
            continue
        reports.append(
            analyze_bars(
                bars,
                source_path=str(path),
                source_type=source_type,
                expected_interval_seconds=expected_seconds,
            )
        )
    return tuple(reports)


def build_data_foundation_readiness_report(
    *,
    run_id: str,
    file_reports: Sequence[DataQualityFileReport],
) -> DataFoundationReadinessReport:
    coverage = _symbol_coverage(file_reports)
    usable = sum(1 for item in file_reports if item.usable_for_backtest)
    unusable = len(file_reports) - usable
    recommendations = _recommendations(file_reports, coverage)
    status = "ready_for_research" if usable and not unusable else "partial" if usable else "not_ready"
    return DataFoundationReadinessReport(
        run_id=run_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        files=tuple(file_reports),
        usable_file_count=usable,
        unusable_file_count=unusable,
        symbol_coverage=coverage,
        overall_status=status,
        recommendations=tuple(recommendations),
    )


def write_data_foundation_readiness_report(
    report: DataFoundationReadinessReport,
    output_dir: str | Path,
) -> DataFoundationReadinessReport:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / f"{report.run_id}.json"
    markdown_path = output_path / f"{report.run_id}.md"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(render_data_foundation_readiness_report(report), encoding="utf-8")
    return DataFoundationReadinessReport(
        **{
            **report.to_dict(),
            "files": report.files,
            "recommendations": report.recommendations,
            "json_report_path": str(json_path),
            "markdown_report_path": str(markdown_path),
            "safety_notes": report.safety_notes,
        }
    )


def render_data_foundation_readiness_report(report: DataFoundationReadinessReport) -> str:
    lines = [
        f"# Data Foundation Readiness - {report.run_id}",
        "",
        f"Generated at: `{report.generated_at}`",
        f"Overall status: `{report.overall_status}`",
        f"Usable files: `{report.usable_file_count}`",
        f"Unusable files: `{report.unusable_file_count}`",
        "",
        "## Dataset Files",
        "",
        "| Source | Rows | Symbols | Timeframes | Start | End | Gaps | Duplicates | Volume | Bid/Ask | Depth | Usable | Warnings |",
        "| --- | ---: | --- | --- | --- | --- | ---: | ---: | --- | --- | --- | --- | --- |",
    ]
    for item in report.files:
        lines.append(
            f"| {item.source_path} | {item.row_count} | {', '.join(item.symbols) or '-'} | "
            f"{', '.join(item.timeframes) or '-'} | {item.start_at or '-'} | {item.end_at or '-'} | "
            f"{item.gap_count} | {item.duplicate_count} | {item.volume_status} | "
            f"{'yes' if item.has_bid_ask else 'no'} | {'yes' if item.has_depth else 'no'} | "
            f"{'yes' if item.usable_for_backtest else 'no'} | {', '.join(item.warnings) or 'none'} |"
        )
    lines.extend(["", "## Symbol Coverage", ""])
    lines.append("| Symbol | Files | Rows | Start | End | Warnings |")
    lines.append("| --- | ---: | ---: | --- | --- | --- |")
    for symbol, payload in sorted(report.symbol_coverage.items()):
        lines.append(
            f"| {symbol} | {payload['file_count']} | {payload['row_count']} | "
            f"{payload.get('start_at') or '-'} | {payload.get('end_at') or '-'} | "
            f"{', '.join(payload.get('warnings', [])) or 'none'} |"
        )
    lines.extend(["", "## Recommendations", ""])
    lines.extend(f"- {item}" for item in report.recommendations)
    lines.extend(["", "## Safety", ""])
    lines.extend(f"- {note}" for note in report.safety_notes)
    lines.append("")
    return "\n".join(lines)


def _metadata_has_any(bar: MarketBar, keys: Sequence[str]) -> bool:
    return any(key in (bar.metadata or {}) for key in keys)


def _volume_status(bars: Sequence[MarketBar], zero_volume_count: int) -> str:
    if not bars:
        return "unknown"
    if zero_volume_count == len(bars):
        return "absent_or_zero"
    if zero_volume_count:
        return "partial"
    return "present"


def _quality_classification(
    quality: MarketDataQualityReport,
    bars: Sequence[MarketBar],
    volume_status: str,
) -> tuple[list[str], list[str]]:
    exclusions: list[str] = []
    warnings: list[str] = []
    if quality.row_count <= 0:
        exclusions.append("empty_dataset")
    if quality.duplicate_count:
        warnings.append("duplicates_present")
    if quality.invalid_ohlc_count:
        exclusions.append("invalid_ohlc")
    if not quality.is_chronological:
        exclusions.append("not_chronological")
    if quality.gap_count:
        exclusions.append("data_gaps_present")
        warnings.append("data_gaps_present")
    if volume_status == "absent_or_zero":
        warnings.append("volume_absent")
    if not any(_metadata_has_any(bar, ("bid", "ask", "best_bid", "best_ask")) for bar in bars):
        warnings.append("bid_ask_absent")
    if not any(_metadata_has_any(bar, ("depth", "order_book", "book_depth", "depth_eur", "liquidity_eur")) for bar in bars):
        warnings.append("order_book_depth_absent")
    return exclusions, warnings


def _symbol_coverage(reports: Sequence[DataQualityFileReport]) -> dict[str, dict[str, Any]]:
    coverage: dict[str, dict[str, Any]] = {}
    for report in reports:
        for symbol in report.symbols:
            bucket = coverage.setdefault(
                symbol,
                {"file_count": 0, "row_count": 0, "start_at": None, "end_at": None, "warnings": []},
            )
            bucket["file_count"] += 1
            bucket["row_count"] += report.row_count
            if report.start_at and (bucket["start_at"] is None or report.start_at < bucket["start_at"]):
                bucket["start_at"] = report.start_at
            if report.end_at and (bucket["end_at"] is None or report.end_at > bucket["end_at"]):
                bucket["end_at"] = report.end_at
            bucket["warnings"].extend(report.warnings)
    for bucket in coverage.values():
        bucket["warnings"] = sorted(set(bucket["warnings"]))
    return coverage


def _recommendations(
    reports: Sequence[DataQualityFileReport],
    coverage: dict[str, dict[str, Any]],
) -> list[str]:
    recommendations = [
        "Use exchange OHLCV history for research conclusions; keep market_price_samples as runtime diagnostics only.",
        "Do not promote any strategy unless the tested dataset includes costs and sufficient out-of-sample windows.",
    ]
    if any(report.volume_status != "present" for report in reports):
        recommendations.append("Prefer Kraken REST/CCXT OHLCV exports because market_price_samples has no real volume.")
    if any(not report.has_bid_ask for report in reports):
        recommendations.append("Collect bid/ask or order-book snapshots before trusting intraday cost-sensitive strategies.")
    if any(report.gap_count for report in reports):
        recommendations.append("Exclude or repair datasets with gaps before batch validation.")
    weak_symbols = [symbol for symbol, item in coverage.items() if int(item.get("row_count") or 0) < 500]
    if weak_symbols:
        recommendations.append(f"Treat low-history symbols as not ready: {', '.join(sorted(weak_symbols))}.")
    recommendations.append("Databento is not the first priority for Kraken spot crypto here; public Kraken OHLCV plus local bid/ask/depth capture closes the immediate parity gap with less vendor complexity.")
    return recommendations


def _expected_seconds(timeframe: str) -> float | None:
    try:
        return float(parse_timeframe_seconds(timeframe))
    except ValueError:
        return None
