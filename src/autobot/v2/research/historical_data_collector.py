"""Historical OHLCV collection for AUTOBOT research.

The collector uses public market-data endpoints only. It does not read Kraken
private keys, cannot submit orders, and is intentionally separated from
runtime paper/live execution.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .data_quality_report import (
    DataFoundationReadinessReport,
    analyze_bars,
    build_data_foundation_readiness_report,
    write_data_foundation_readiness_report,
)
from .dataset_builder import parse_timeframe_seconds
from .market_data_repository import MarketBar, MarketDataRepository
from .symbol_normalization import normalize_research_symbol


KRAKEN_REST_OHLC_URL = "https://api.kraken.com/0/public/OHLC"
KRAKEN_SUPPORTED_INTERVALS = {1, 5, 15, 30, 60, 240, 1440, 10080, 21600}


@dataclass(frozen=True)
class KrakenOHLCPage:
    pair: str
    rows: tuple[tuple[Any, ...], ...]
    last: int | None = None


@dataclass(frozen=True)
class FetchedOHLCRows:
    rows: tuple[tuple[Any, ...], ...]
    last_cursor: int | None
    pages_fetched: int
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class HistoricalDataCollectorConfig:
    run_id: str
    symbols: tuple[str, ...]
    timeframes: tuple[str, ...] = ("1m", "5m", "15m", "1h")
    output_dir: Path = Path("data/research/historical")
    provider: str = "kraken_rest_public"
    since: int | None = None
    start_at: str | None = None
    end_at: str | None = None
    max_pages: int = 1
    sleep_seconds: float = 0.0
    dedupe: bool = True
    fail_on_gaps: bool = False
    export_csv: bool = True
    export_parquet: bool = True

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id must not be empty")
        if not self.symbols:
            raise ValueError("symbols must not be empty")
        if not self.timeframes:
            raise ValueError("timeframes must not be empty")
        if self.max_pages <= 0:
            raise ValueError("max_pages must be positive")
        if self.sleep_seconds < 0.0:
            raise ValueError("sleep_seconds cannot be negative")
        if self.since is not None and self.start_at:
            raise ValueError("use either since or start_at, not both")
        start_dt = _parse_optional_datetime(self.start_at)
        end_dt = _parse_optional_datetime(self.end_at)
        if start_dt and end_dt and end_dt < start_dt:
            raise ValueError("end_at must be greater than or equal to start_at")
        for timeframe in self.timeframes:
            _timeframe_to_kraken_interval(timeframe)


@dataclass(frozen=True)
class HistoricalDataFile:
    symbol: str
    timeframe: str
    provider: str
    row_count: int
    start_at: str | None
    end_at: str | None
    requested_start_at: str | None = None
    requested_end_at: str | None = None
    last_cursor: int | None = None
    pages_fetched: int = 0
    row_count_raw: int = 0
    row_count_deduped: int = 0
    duplicate_count: int = 0
    csv_path: str | None = None
    parquet_path: str | None = None
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["warnings"] = list(self.warnings)
        return payload


@dataclass(frozen=True)
class HistoricalDataCollectionResult:
    run_id: str
    provider: str
    generated_at: str
    files: tuple[HistoricalDataFile, ...]
    readiness: DataFoundationReadinessReport
    manifest_path: str | None = None
    markdown_report_path: str | None = None
    safety_notes: tuple[str, ...] = (
        "Public historical data collection only.",
        "No private Kraken endpoint is called.",
        "No API key is read or exposed.",
        "No paper or live order is created.",
        "No live trading permission is granted.",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "provider": self.provider,
            "generated_at": self.generated_at,
            "files": [item.to_dict() for item in self.files],
            "readiness": self.readiness.to_dict(),
            "manifest_path": self.manifest_path,
            "markdown_report_path": self.markdown_report_path,
            "safety_notes": list(self.safety_notes),
        }


OHLCFetcher = Callable[[str, int, int | None], KrakenOHLCPage]


def collect_historical_ohlcv(
    config: HistoricalDataCollectorConfig,
    *,
    fetcher: OHLCFetcher | None = None,
) -> HistoricalDataCollectionResult:
    """Collect public OHLCV and write CSV/Parquet research datasets."""

    repository = MarketDataRepository()
    fetch = fetcher or fetch_kraken_ohlc_page
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    files: list[HistoricalDataFile] = []
    file_quality_reports = []
    start_dt = _parse_optional_datetime(config.start_at)
    end_dt = _parse_optional_datetime(config.end_at)
    since_cursor = config.since if start_dt is None else int(start_dt.timestamp())

    for symbol in config.symbols:
        canonical_symbol = normalize_research_symbol(symbol)
        for timeframe in config.timeframes:
            interval = _timeframe_to_kraken_interval(timeframe)
            fetched = _fetch_pages(
                fetch,
                symbol,
                interval,
                since=since_cursor,
                start_at=start_dt,
                end_at=end_dt,
                max_pages=config.max_pages,
                sleep_seconds=config.sleep_seconds,
            )
            raw_bars = _bars_from_kraken_rows(
                fetched.rows,
                symbol=canonical_symbol,
                timeframe=timeframe,
                provider=config.provider,
            )
            bars, duplicate_count = _dedupe_bars(raw_bars) if config.dedupe else (
                MarketDataRepository.normalize(raw_bars),
                _count_duplicate_bars(raw_bars),
            )
            safe_symbol = canonical_symbol.replace("/", "").upper()
            safe_timeframe = timeframe.lower()
            csv_path: Path | None = None
            parquet_path: Path | None = None
            warnings: list[str] = list(fetched.warnings)
            if duplicate_count:
                warnings.append("duplicates_deduped" if config.dedupe else "duplicates_present")
            if config.export_csv:
                csv_path = repository.save_csv(bars, output_dir / f"{config.run_id}_{safe_symbol}_{safe_timeframe}.csv")
            if config.export_parquet:
                try:
                    parquet_path = repository.save_parquet(
                        bars,
                        output_dir / f"{config.run_id}_{safe_symbol}_{safe_timeframe}.parquet",
                    )
                except ImportError:
                    warnings.append("parquet_export_unavailable")
            expected_seconds = parse_timeframe_seconds(timeframe)
            quality = analyze_bars(
                bars,
                source_path=str(parquet_path or csv_path or f"{config.provider}:{symbol}:{timeframe}"),
                source_type=config.provider,
                expected_interval_seconds=expected_seconds,
            )
            if config.fail_on_gaps and quality.gap_count:
                raise ValueError(
                    f"data gaps detected for {canonical_symbol} {timeframe}: {quality.gap_count}"
                )
            file_quality_reports.append(quality)
            files.append(
                HistoricalDataFile(
                    symbol=canonical_symbol,
                    timeframe=timeframe,
                    provider=config.provider,
                    row_count=len(bars),
                    start_at=bars[0].timestamp.isoformat() if bars else None,
                    end_at=bars[-1].timestamp.isoformat() if bars else None,
                    requested_start_at=start_dt.isoformat() if start_dt else None,
                    requested_end_at=end_dt.isoformat() if end_dt else None,
                    last_cursor=fetched.last_cursor,
                    pages_fetched=fetched.pages_fetched,
                    row_count_raw=len(raw_bars),
                    row_count_deduped=len(bars),
                    duplicate_count=duplicate_count,
                    csv_path=str(csv_path) if csv_path else None,
                    parquet_path=str(parquet_path) if parquet_path else None,
                    warnings=tuple(dict.fromkeys([*warnings, *quality.warnings])),
                )
            )

    readiness = build_data_foundation_readiness_report(
        run_id=f"{config.run_id}_readiness",
        file_reports=file_quality_reports,
    )
    readiness = write_data_foundation_readiness_report(readiness, output_dir / "quality")
    result = HistoricalDataCollectionResult(
        run_id=config.run_id,
        provider=config.provider,
        generated_at=datetime.now(timezone.utc).isoformat(),
        files=tuple(files),
        readiness=readiness,
    )
    return write_historical_data_collection_reports(result, output_dir)


def fetch_kraken_ohlc_page(pair: str, interval_minutes: int, since: int | None) -> KrakenOHLCPage:
    """Fetch one public Kraken OHLC page.

    This function intentionally uses the public REST endpoint and never touches
    private trading credentials.
    """

    if interval_minutes not in KRAKEN_SUPPORTED_INTERVALS:
        raise ValueError(f"unsupported Kraken OHLC interval: {interval_minutes}")
    params: dict[str, Any] = {"pair": pair, "interval": interval_minutes}
    if since is not None:
        params["since"] = int(since)
    url = f"{KRAKEN_REST_OHLC_URL}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=20) as response:  # nosec B310 - public, fixed HTTPS API.
        payload = json.loads(response.read().decode("utf-8"))
    errors = payload.get("error") or []
    if errors:
        raise ValueError(f"Kraken OHLC error for {pair}: {errors}")
    result = payload.get("result") or {}
    last = _safe_int(result.get("last"))
    data_key = next((key for key in result.keys() if key != "last"), None)
    rows = tuple(tuple(row) for row in result.get(data_key, ())) if data_key else ()
    return KrakenOHLCPage(pair=str(data_key or pair), rows=rows, last=last)


def write_historical_data_collection_reports(
    result: HistoricalDataCollectionResult,
    output_dir: str | Path,
) -> HistoricalDataCollectionResult:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    manifest_path = output_path / f"{result.run_id}_manifest.json"
    markdown_path = output_path / f"{result.run_id}.md"
    manifest_path.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(render_historical_data_collection_report(result), encoding="utf-8")
    return HistoricalDataCollectionResult(
        run_id=result.run_id,
        provider=result.provider,
        generated_at=result.generated_at,
        files=result.files,
        readiness=result.readiness,
        manifest_path=str(manifest_path),
        markdown_report_path=str(markdown_path),
        safety_notes=result.safety_notes,
    )


def render_historical_data_collection_report(result: HistoricalDataCollectionResult) -> str:
    lines = [
        f"# Historical Data Collection - {result.run_id}",
        "",
        f"Provider: `{result.provider}`",
        f"Generated at: `{result.generated_at}`",
        f"Readiness: `{result.readiness.overall_status}`",
        "",
        "## Files",
        "",
        "| Symbol | Timeframe | Rows | Raw | Duplicates | Pages | Cursor | Start | End | CSV | Parquet | Warnings |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- | --- | --- |",
    ]
    for item in result.files:
        lines.append(
            f"| {item.symbol} | {item.timeframe} | {item.row_count} | {item.row_count_raw} | "
            f"{item.duplicate_count} | {item.pages_fetched} | {item.last_cursor or '-'} | "
            f"{item.start_at or '-'} | {item.end_at or '-'} | {item.csv_path or '-'} | {item.parquet_path or '-'} | "
            f"{', '.join(item.warnings) or 'none'} |"
        )
    lines.extend(["", "## Safety", ""])
    lines.extend(f"- {note}" for note in result.safety_notes)
    lines.append("")
    return "\n".join(lines)


def _fetch_pages(
    fetcher: OHLCFetcher,
    pair: str,
    interval: int,
    *,
    since: int | None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    max_pages: int,
    sleep_seconds: float,
) -> FetchedOHLCRows:
    rows: list[tuple[Any, ...]] = []
    cursor = since
    seen_cursors: set[int] = set()
    warnings: list[str] = []
    start_epoch = int(start_at.timestamp()) if start_at else None
    end_epoch = int(end_at.timestamp()) if end_at else None
    pages_fetched = 0
    for page_index in range(max_pages):
        page = fetcher(pair, interval, cursor)
        pages_fetched += 1
        rows.extend(page.rows)
        page_epochs = [_row_epoch(row) for row in page.rows]
        if end_epoch is not None and any(epoch is not None and epoch >= end_epoch for epoch in page_epochs):
            break
        if page.last is None or page.last == cursor or page.last in seen_cursors:
            break
        seen_cursors.add(page.last)
        cursor = page.last
        if page_index < max_pages - 1 and sleep_seconds:
            time.sleep(sleep_seconds)
    else:
        warnings.append("max_pages_reached")
    filtered_rows = []
    for row in rows:
        epoch = _row_epoch(row)
        if epoch is None:
            continue
        if start_epoch is not None and epoch < start_epoch:
            continue
        if end_epoch is not None and epoch > end_epoch:
            continue
        filtered_rows.append(row)
    return FetchedOHLCRows(
        rows=tuple(filtered_rows),
        last_cursor=cursor,
        pages_fetched=pages_fetched,
        warnings=tuple(warnings),
    )


def _bars_from_kraken_rows(
    rows: Sequence[Sequence[Any]],
    *,
    symbol: str,
    timeframe: str,
    provider: str,
) -> list[MarketBar]:
    bars: list[MarketBar] = []
    for row in rows:
        if len(row) < 7:
            continue
        try:
            timestamp = datetime.fromtimestamp(float(row[0]), tz=timezone.utc)
            open_price = float(row[1])
            high = float(row[2])
            low = float(row[3])
            close = float(row[4])
            volume = float(row[6])
        except (TypeError, ValueError):
            continue
        if min(open_price, high, low, close) <= 0.0 or volume < 0.0:
            continue
        bars.append(
            MarketBar(
                timestamp=timestamp,
                symbol=symbol,
                timeframe=timeframe,
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=volume,
                metadata={
                    "source": provider,
                    "volume_source": "kraken_ohlcv",
                    "bid_ask_source": "absent",
                    "depth_source": "absent",
                },
            )
        )
    return MarketDataRepository.normalize(bars)


def _timeframe_to_kraken_interval(timeframe: str) -> int:
    seconds = parse_timeframe_seconds(timeframe)
    minutes = int(seconds // 60)
    if seconds % 60 != 0 or minutes not in KRAKEN_SUPPORTED_INTERVALS:
        raise ValueError(f"timeframe {timeframe!r} is not supported by Kraken OHLC")
    return minutes


def _dedupe_bars(bars: Sequence[MarketBar]) -> tuple[list[MarketBar], int]:
    deduped: list[MarketBar] = []
    seen: set[tuple[str, str, datetime]] = set()
    duplicate_count = 0
    for bar in MarketDataRepository.normalize(bars):
        key = bar.key()
        if key in seen:
            duplicate_count += 1
            continue
        seen.add(key)
        deduped.append(bar)
    return deduped, duplicate_count


def _count_duplicate_bars(bars: Sequence[MarketBar]) -> int:
    keys = [bar.key() for bar in bars]
    return len(keys) - len(set(keys))


def _row_epoch(row: Sequence[Any]) -> int | None:
    if not row:
        return None
    try:
        return int(float(row[0]))
    except (TypeError, ValueError):
        return None


def _parse_optional_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _safe_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None
