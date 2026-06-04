"""Build clean research OHLCV datasets from AUTOBOT runtime samples.

This module is research-only. It reads persisted ``market_price_samples`` and
exports deterministic OHLCV bars for validation runs. Runtime paper/live
execution does not import or depend on this module.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

from .market_data_repository import MarketBar, MarketDataQualityReport, MarketDataRepository


_TIMEFRAME_UNITS = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
}


@dataclass(frozen=True)
class DatasetTimeframeExport:
    timeframe: str
    timeframe_seconds: int
    bar_count: int
    symbol_count: int
    csv_path: str | None
    parquet_path: str | None
    quality: MarketDataQualityReport
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["quality"] = self.quality.to_dict()
        return data


@dataclass(frozen=True)
class DatasetBuildConfig:
    run_id: str
    state_db_path: Path
    output_dir: Path = Path("data/research")
    symbols: tuple[str, ...] = ()
    timeframes: tuple[str, ...] = ("1m", "5m", "15m")
    start_at: str | None = None
    end_at: str | None = None
    limit: int | None = None
    export_csv: bool = True
    export_parquet: bool = False
    canonicalize_symbols: bool = True

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id must not be empty")
        if not self.timeframes:
            raise ValueError("timeframes must not be empty")
        for timeframe in self.timeframes:
            parse_timeframe_seconds(timeframe)


@dataclass(frozen=True)
class DatasetBuildResult:
    run_id: str
    source_type: str
    source_path: str
    output_dir: str
    raw_sample_count: int
    usable_sample_count: int
    raw_duplicate_count: int
    timestamp_collision_count: int
    symbols: tuple[str, ...]
    exports: tuple[DatasetTimeframeExport, ...]
    raw_symbols: tuple[str, ...] = ()
    normalized_symbol_count: int = 0
    manifest_path: str | None = None
    markdown_report_path: str | None = None
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "source_type": self.source_type,
            "source_path": self.source_path,
            "output_dir": self.output_dir,
            "raw_sample_count": self.raw_sample_count,
            "usable_sample_count": self.usable_sample_count,
            "raw_duplicate_count": self.raw_duplicate_count,
            "timestamp_collision_count": self.timestamp_collision_count,
            "symbols": list(self.symbols),
            "raw_symbols": list(self.raw_symbols),
            "normalized_symbol_count": self.normalized_symbol_count,
            "exports": [export.to_dict() for export in self.exports],
            "manifest_path": self.manifest_path,
            "markdown_report_path": self.markdown_report_path,
            "warnings": list(self.warnings),
            "safety_notes": [
                "Research dataset build only.",
                "No runtime paper/live service is started.",
                "No strategy registry mutation is performed.",
                "No Kraken order can be created by this command.",
                "No live trading permission is granted.",
            ],
        }


def parse_timeframe_seconds(timeframe: str) -> int:
    text = str(timeframe).strip().lower()
    if len(text) < 2:
        raise ValueError(f"invalid timeframe: {timeframe!r}")
    unit = text[-1]
    amount_text = text[:-1]
    if unit not in _TIMEFRAME_UNITS:
        raise ValueError(f"unsupported timeframe unit: {timeframe!r}")
    try:
        amount = int(amount_text)
    except ValueError as exc:
        raise ValueError(f"invalid timeframe amount: {timeframe!r}") from exc
    if amount <= 0:
        raise ValueError(f"timeframe amount must be positive: {timeframe!r}")
    return amount * _TIMEFRAME_UNITS[unit]


def build_dataset_from_state_db(config: DatasetBuildConfig) -> DatasetBuildResult:
    repository = MarketDataRepository()
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_samples = repository.load_autobot_state_db(
        config.state_db_path,
        symbols=config.symbols,
        start_at=config.start_at,
        end_at=config.end_at,
        limit=config.limit,
        canonicalize_symbols=config.canonicalize_symbols,
    )
    usable_samples, raw_duplicate_count, timestamp_collision_count = _dedupe_samples(raw_samples)
    warnings: list[str] = []
    if not raw_samples:
        warnings.append("empty_market_price_samples")
    if raw_duplicate_count:
        warnings.append("raw_duplicate_samples_removed")
    if timestamp_collision_count:
        warnings.append("same_timestamp_multiple_prices")
    warnings.append("volume_unavailable_from_market_price_samples")
    normalized_symbol_count = sum(1 for sample in usable_samples if sample.metadata.get("symbol_normalized") is True)
    if normalized_symbol_count:
        warnings.append("symbols_canonicalized")

    exports: list[DatasetTimeframeExport] = []
    for timeframe in config.timeframes:
        timeframe_seconds = parse_timeframe_seconds(timeframe)
        bars = aggregate_samples_to_ohlcv(
            usable_samples,
            timeframe=timeframe,
            timeframe_seconds=timeframe_seconds,
        )
        quality = repository.validate(bars, expected_interval_seconds=timeframe_seconds)
        csv_path: Path | None = None
        parquet_path: Path | None = None
        export_warnings: list[str] = []
        safe_timeframe = timeframe.lower()
        if config.export_csv:
            csv_path = repository.save_csv(bars, output_dir / f"{config.run_id}_{safe_timeframe}.csv")
        if config.export_parquet:
            try:
                parquet_path = repository.save_parquet(bars, output_dir / f"{config.run_id}_{safe_timeframe}.parquet")
            except ImportError:
                export_warnings.append("parquet_export_unavailable")
        exports.append(
            DatasetTimeframeExport(
                timeframe=timeframe,
                timeframe_seconds=timeframe_seconds,
                bar_count=len(bars),
                symbol_count=len({bar.symbol for bar in bars}),
                csv_path=str(csv_path) if csv_path else None,
                parquet_path=str(parquet_path) if parquet_path else None,
                quality=quality,
                warnings=tuple(export_warnings),
            )
        )

    result = DatasetBuildResult(
        run_id=config.run_id,
        source_type="autobot_state_db.market_price_samples",
        source_path=str(config.state_db_path),
        output_dir=str(output_dir),
        raw_sample_count=len(raw_samples),
        usable_sample_count=len(usable_samples),
        raw_duplicate_count=raw_duplicate_count,
        timestamp_collision_count=timestamp_collision_count,
        symbols=tuple(sorted({bar.symbol for bar in usable_samples})),
        raw_symbols=tuple(sorted({str(bar.metadata.get("raw_symbol")) for bar in usable_samples if bar.metadata.get("raw_symbol")})),
        normalized_symbol_count=normalized_symbol_count,
        exports=tuple(exports),
        warnings=tuple(warnings),
    )
    return write_dataset_build_reports(result, output_dir)


def aggregate_samples_to_ohlcv(
    samples: Sequence[MarketBar],
    *,
    timeframe: str,
    timeframe_seconds: int,
) -> list[MarketBar]:
    buckets: dict[tuple[str, datetime], list[MarketBar]] = {}
    for sample in samples:
        bucket_at = floor_timestamp(sample.timestamp, timeframe_seconds)
        buckets.setdefault((sample.symbol, bucket_at), []).append(sample)

    bars: list[MarketBar] = []
    for (symbol, bucket_at), bucket_samples in sorted(buckets.items(), key=lambda item: (item[0][0], item[0][1])):
        ordered = sorted(bucket_samples, key=lambda sample: sample.timestamp)
        prices = [sample.close for sample in ordered]
        bars.append(
            MarketBar(
                timestamp=bucket_at,
                symbol=symbol,
                timeframe=timeframe,
                open=prices[0],
                high=max(prices),
                low=min(prices),
                close=prices[-1],
                volume=0.0,
                metadata={
                    "source": "market_price_samples_ohlcv",
                    "sample_count": len(ordered),
                    "timeframe_seconds": timeframe_seconds,
                    "volume_source": "unavailable_from_market_price_samples",
                    "first_sample_at": ordered[0].timestamp.isoformat(),
                    "last_sample_at": ordered[-1].timestamp.isoformat(),
                },
            )
        )
    return MarketDataRepository.normalize(bars)


def floor_timestamp(timestamp: datetime, timeframe_seconds: int) -> datetime:
    ts = timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=timezone.utc)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    elapsed = int((ts.astimezone(timezone.utc) - epoch).total_seconds())
    bucket_start = elapsed - (elapsed % timeframe_seconds)
    return epoch + timedelta(seconds=bucket_start)


def write_dataset_build_reports(result: DatasetBuildResult, output_dir: Path) -> DatasetBuildResult:
    manifest_path = output_dir / f"{result.run_id}_manifest.json"
    markdown_path = output_dir / f"{result.run_id}_quality.md"
    manifest_path.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(render_dataset_build_report(result), encoding="utf-8")
    return DatasetBuildResult(
        run_id=result.run_id,
        source_type=result.source_type,
        source_path=result.source_path,
        output_dir=result.output_dir,
        raw_sample_count=result.raw_sample_count,
        usable_sample_count=result.usable_sample_count,
        raw_duplicate_count=result.raw_duplicate_count,
        timestamp_collision_count=result.timestamp_collision_count,
        symbols=result.symbols,
        exports=result.exports,
        raw_symbols=result.raw_symbols,
        normalized_symbol_count=result.normalized_symbol_count,
        manifest_path=str(manifest_path),
        markdown_report_path=str(markdown_path),
        warnings=result.warnings,
    )


def render_dataset_build_report(result: DatasetBuildResult) -> str:
    lines = [
        f"# Dataset Build - {result.run_id}",
        "",
        "## Scope",
        "",
        "Research-only dataset build from AUTOBOT runtime market samples. This report does not imply strategy",
        "readiness, paper execution, live permission, or profitability.",
        "",
        "## Source",
        "",
        f"- Source type: `{result.source_type}`",
        f"- Source path: `{result.source_path}`",
        f"- Raw samples: `{result.raw_sample_count}`",
        f"- Usable samples: `{result.usable_sample_count}`",
        f"- Exact duplicates removed: `{result.raw_duplicate_count}`",
        f"- Same-timestamp collisions: `{result.timestamp_collision_count}`",
        f"- Symbols: `{', '.join(result.symbols) if result.symbols else 'none'}`",
        f"- Raw aliases normalized: `{', '.join(result.raw_symbols) if result.raw_symbols else 'none'}`",
        f"- Normalized sample count: `{result.normalized_symbol_count}`",
        f"- Warnings: `{', '.join(result.warnings) if result.warnings else 'none'}`",
        "",
        "## Exports",
        "",
        "| Timeframe | Bars | Symbols | Gaps | Max Gap Seconds | CSV | Parquet | Warnings |",
        "| --- | ---: | ---: | ---: | ---: | --- | --- | --- |",
    ]
    for export in result.exports:
        quality = export.quality
        lines.append(
            "| {tf} | {bars} | {symbols} | {gaps} | {max_gap:.0f} | {csv} | {parquet} | {warnings} |".format(
                tf=export.timeframe,
                bars=export.bar_count,
                symbols=export.symbol_count,
                gaps=quality.gap_count,
                max_gap=quality.max_gap_seconds,
                csv=export.csv_path or "",
                parquet=export.parquet_path or "",
                warnings=", ".join(tuple(quality.warnings) + tuple(export.warnings)) or "none",
            )
        )
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "- Research dataset build only.",
            "- No runtime paper/live service is started.",
            "- No strategy registry mutation is performed.",
            "- No Kraken order can be created by this command.",
            "- No live trading permission is granted.",
        ]
    )
    return "\n".join(lines) + "\n"


def _dedupe_samples(samples: Sequence[MarketBar]) -> tuple[list[MarketBar], int, int]:
    seen_exact: set[tuple[str, str, float]] = set()
    seen_timestamp: dict[tuple[str, str], float] = {}
    deduped: list[MarketBar] = []
    duplicate_count = 0
    timestamp_collision_count = 0
    for sample in samples:
        timestamp_key = sample.timestamp.isoformat()
        exact_key = (sample.symbol, timestamp_key, sample.close)
        if exact_key in seen_exact:
            duplicate_count += 1
            continue
        seen_exact.add(exact_key)
        ts_key = (sample.symbol, timestamp_key)
        previous_price = seen_timestamp.get(ts_key)
        if previous_price is not None and previous_price != sample.close:
            timestamp_collision_count += 1
        seen_timestamp[ts_key] = sample.close
        deduped.append(sample)
    return deduped, duplicate_count, timestamp_collision_count
