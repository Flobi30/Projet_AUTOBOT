"""Research-only public spread/depth recorder for AUTOBOT.

This module reads public Kraken top-of-book/depth data only. It never reads
private keys, never submits orders, and is not wired into runtime trading.
"""

from __future__ import annotations

import csv
import json
import statistics
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .kraken_symbol_mapping import (
    AssetPairsFetcher,
    KrakenPublicPairMapping,
    preflight_kraken_public_symbols,
)
from .symbol_normalization import normalize_research_symbol


KRAKEN_REST_DEPTH_URL = "https://api.kraken.com/0/public/Depth"


@dataclass(frozen=True)
class SpreadDepthSnapshot:
    timestamp_local: str
    timestamp_exchange: str | None
    symbol: str
    source: str
    best_bid: float
    best_ask: float
    mid_price: float
    spread_bps: float
    bid_depth_eur: float
    ask_depth_eur: float
    latency_ms: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SpreadDepthRecorderConfig:
    run_id: str
    symbols: tuple[str, ...]
    output_dir: Path = Path("data/research/microstructure")
    provider: str = "kraken_rest_public_depth"
    depth_count: int = 10
    samples: int = 1
    sleep_seconds: float = 0.0
    export_csv: bool = True
    continue_on_error: bool = False

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id must not be empty")
        if not self.symbols:
            raise ValueError("symbols must not be empty")
        if self.depth_count <= 0:
            raise ValueError("depth_count must be positive")
        if self.samples <= 0:
            raise ValueError("samples must be positive")
        if self.sleep_seconds < 0.0:
            raise ValueError("sleep_seconds cannot be negative")


@dataclass(frozen=True)
class SpreadDepthRecorderResult:
    run_id: str
    generated_at: str
    provider: str
    snapshots: tuple[SpreadDepthSnapshot, ...]
    summary_by_symbol: dict[str, dict[str, float]]
    errors: tuple[dict[str, Any], ...] = ()
    csv_path: str | None = None
    markdown_report_path: str | None = None
    safety_notes: tuple[str, ...] = (
        "Research microstructure capture only.",
        "Public Kraken depth endpoint only.",
        "No API key is read or exposed.",
        "No paper or live order is created.",
        "No live trading permission is granted.",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "provider": self.provider,
            "snapshots": [snapshot.to_dict() for snapshot in self.snapshots],
            "summary_by_symbol": self.summary_by_symbol,
            "errors": list(self.errors),
            "csv_path": self.csv_path,
            "markdown_report_path": self.markdown_report_path,
            "safety_notes": list(self.safety_notes),
        }


DepthFetcher = Callable[[str, int], Mapping[str, Any]]


def record_spread_depth(
    config: SpreadDepthRecorderConfig,
    *,
    fetcher: DepthFetcher | None = None,
    asset_pairs_fetcher: AssetPairsFetcher | None = None,
    symbol_mappings: Mapping[str, KrakenPublicPairMapping] | None = None,
) -> SpreadDepthRecorderResult:
    fetch = fetcher or fetch_kraken_depth_page
    mapping_by_symbol, collection_symbols = _resolve_collection_symbols(
        config.symbols,
        asset_pairs_fetcher=asset_pairs_fetcher,
        symbol_mappings=symbol_mappings,
    )
    snapshots: list[SpreadDepthSnapshot] = []
    errors: list[dict[str, Any]] = []
    for sample_index in range(config.samples):
        for symbol in collection_symbols:
            requested_symbol = str(symbol).strip().upper()
            canonical_requested = normalize_research_symbol(symbol)
            mapping = (
                mapping_by_symbol.get(requested_symbol)
                or mapping_by_symbol.get(requested_symbol.replace("/", "").replace("-", "").replace("_", ""))
                or mapping_by_symbol.get(canonical_requested)
            )
            if mapping is None:
                raise ValueError(f"missing Kraken public symbol mapping for {requested_symbol or canonical_requested}")
            canonical_symbol = mapping.autobot_symbol
            try:
                started = time.perf_counter()
                payload = fetch(mapping.kraken_ohlcv_symbol, config.depth_count)
                latency_ms = (time.perf_counter() - started) * 1000.0
                snapshots.append(
                    _snapshot_from_depth_payload(
                        payload,
                        symbol=canonical_symbol,
                        provider=config.provider,
                        latency_ms=latency_ms,
                    )
                )
            except Exception as exc:
                if not config.continue_on_error:
                    raise
                errors.append(
                    {
                        "symbol": canonical_symbol,
                        "sample_index": sample_index,
                        "error": str(exc),
                        "source": config.provider,
                    }
                )
        if sample_index < config.samples - 1 and config.sleep_seconds:
            time.sleep(config.sleep_seconds)
    result = SpreadDepthRecorderResult(
        run_id=config.run_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        provider=config.provider,
        snapshots=tuple(snapshots),
        summary_by_symbol=_summary_by_symbol(snapshots),
        errors=tuple(errors),
    )
    return write_spread_depth_recording(result, config.output_dir, export_csv=config.export_csv)


def fetch_kraken_depth_page(pair: str, depth_count: int) -> Mapping[str, Any]:
    params = {"pair": pair, "count": int(depth_count)}
    url = f"{KRAKEN_REST_DEPTH_URL}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=20) as response:  # nosec B310 - public, fixed HTTPS API.
        payload = json.loads(response.read().decode("utf-8"))
    errors = payload.get("error") or []
    if errors:
        raise ValueError(f"Kraken depth error for {pair}: {errors}")
    return payload


def write_spread_depth_recording(
    result: SpreadDepthRecorderResult,
    output_dir: str | Path,
    *,
    export_csv: bool = True,
) -> SpreadDepthRecorderResult:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    csv_path: Path | None = None
    if export_csv:
        csv_path = output_path / f"{result.run_id}_spread_depth.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "timestamp_local",
                    "timestamp_exchange",
                    "symbol",
                    "source",
                    "best_bid",
                    "best_ask",
                    "mid_price",
                    "spread_bps",
                    "bid_depth_eur",
                    "ask_depth_eur",
                    "latency_ms",
                ],
            )
            writer.writeheader()
            writer.writerows(snapshot.to_dict() for snapshot in result.snapshots)
    markdown_path = output_path / f"{result.run_id}_spread_depth.md"
    markdown_path.write_text(render_spread_depth_report(result), encoding="utf-8")
    return SpreadDepthRecorderResult(
        run_id=result.run_id,
        generated_at=result.generated_at,
        provider=result.provider,
        snapshots=result.snapshots,
        summary_by_symbol=result.summary_by_symbol,
        errors=result.errors,
        csv_path=str(csv_path) if csv_path else None,
        markdown_report_path=str(markdown_path),
        safety_notes=result.safety_notes,
    )


def render_spread_depth_report(result: SpreadDepthRecorderResult) -> str:
    lines = [
        f"# Spread / Depth Recording - {result.run_id}",
        "",
        f"Generated at: `{result.generated_at}`",
        f"Provider: `{result.provider}`",
        f"Snapshots: `{len(result.snapshots)}`",
        f"Errors: `{len(result.errors)}`",
        "",
        "## Summary By Symbol",
        "",
        "| Symbol | Samples | Spread Mean | Spread Median | Spread P95 | Spread P99 | Bid Depth Median | Ask Depth Median | Latency Median ms |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for symbol, summary in sorted(result.summary_by_symbol.items()):
        lines.append(
            f"| {symbol} | {int(summary['samples'])} | {summary['spread_mean_bps']:.6f} | "
            f"{summary['spread_median_bps']:.6f} | {summary['spread_p95_bps']:.6f} | "
            f"{summary['spread_p99_bps']:.6f} | {summary['bid_depth_median_eur']:.6f} | "
            f"{summary['ask_depth_median_eur']:.6f} | {summary['latency_median_ms']:.6f} |"
        )
    if result.errors:
        lines.extend(["", "## Errors", ""])
        lines.append("| Symbol | Sample | Source | Error |")
        lines.append("| --- | ---: | --- | --- |")
        for item in result.errors:
            lines.append(
                f"| {item.get('symbol', '-')} | {item.get('sample_index', '-')} | "
                f"{item.get('source', '-')} | {item.get('error', '-')} |"
            )
    lines.extend(["", "## Safety", ""])
    lines.extend(f"- {note}" for note in result.safety_notes)
    lines.append("")
    return "\n".join(lines)


def _snapshot_from_depth_payload(
    payload: Mapping[str, Any],
    *,
    symbol: str,
    provider: str,
    latency_ms: float,
) -> SpreadDepthSnapshot:
    result = payload.get("result") or {}
    pair_key = next(iter(result), None)
    if pair_key is None:
        raise ValueError(f"missing depth data for {symbol}")
    book = result[pair_key]
    bids = tuple(book.get("bids") or ())
    asks = tuple(book.get("asks") or ())
    if not bids or not asks:
        raise ValueError(f"empty depth book for {symbol}")
    best_bid = float(bids[0][0])
    best_ask = float(asks[0][0])
    if best_bid <= 0.0 or best_ask <= 0.0 or best_ask < best_bid:
        raise ValueError(f"invalid bid/ask for {symbol}")
    mid = (best_bid + best_ask) / 2.0
    timestamp_exchange = _book_timestamp(bids[0], asks[0])
    return SpreadDepthSnapshot(
        timestamp_local=datetime.now(timezone.utc).isoformat(),
        timestamp_exchange=timestamp_exchange,
        symbol=symbol,
        source=provider,
        best_bid=best_bid,
        best_ask=best_ask,
        mid_price=mid,
        spread_bps=((best_ask - best_bid) / mid) * 10_000.0,
        bid_depth_eur=_depth_eur(bids),
        ask_depth_eur=_depth_eur(asks),
        latency_ms=latency_ms,
    )


def _depth_eur(rows: Sequence[Sequence[Any]]) -> float:
    total = 0.0
    for row in rows:
        if len(row) < 2:
            continue
        try:
            total += float(row[0]) * float(row[1])
        except (TypeError, ValueError):
            continue
    return total


def _book_timestamp(*rows: Sequence[Any]) -> str | None:
    timestamps = []
    for row in rows:
        if len(row) < 3:
            continue
        try:
            timestamps.append(float(row[2]))
        except (TypeError, ValueError):
            continue
    if not timestamps:
        return None
    return datetime.fromtimestamp(max(timestamps), tz=timezone.utc).isoformat()


def _summary_by_symbol(snapshots: Sequence[SpreadDepthSnapshot]) -> dict[str, dict[str, float]]:
    summary: dict[str, dict[str, float]] = {}
    for symbol in sorted({snapshot.symbol for snapshot in snapshots}):
        rows = [snapshot for snapshot in snapshots if snapshot.symbol == symbol]
        spreads = [row.spread_bps for row in rows]
        bid_depths = [row.bid_depth_eur for row in rows]
        ask_depths = [row.ask_depth_eur for row in rows]
        latencies = [row.latency_ms for row in rows]
        summary[symbol] = {
            "samples": float(len(rows)),
            "spread_mean_bps": statistics.fmean(spreads) if spreads else 0.0,
            "spread_median_bps": statistics.median(spreads) if spreads else 0.0,
            "spread_p95_bps": _quantile(spreads, 0.95),
            "spread_p99_bps": _quantile(spreads, 0.99),
            "bid_depth_median_eur": statistics.median(bid_depths) if bid_depths else 0.0,
            "ask_depth_median_eur": statistics.median(ask_depths) if ask_depths else 0.0,
            "latency_median_ms": statistics.median(latencies) if latencies else 0.0,
        }
    return summary


def _quantile(values: Sequence[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * q))))
    return ordered[index]


def _resolve_collection_symbols(
    symbols: Sequence[str],
    *,
    asset_pairs_fetcher: AssetPairsFetcher | None = None,
    symbol_mappings: Mapping[str, KrakenPublicPairMapping] | None = None,
) -> tuple[dict[str, KrakenPublicPairMapping], tuple[str, ...]]:
    if symbol_mappings is None:
        preflight = preflight_kraken_public_symbols(symbols, asset_pairs_fetcher=asset_pairs_fetcher)
        mapping_by_symbol = preflight.mapping_by_symbol()
        collection_symbols = preflight.resolved_symbols
    else:
        mapping_by_symbol = dict(symbol_mappings)
        collection: list[str] = []
        for requested in symbols:
            mapping = _lookup_symbol_mapping(mapping_by_symbol, requested)
            if mapping is None:
                continue
            if mapping.autobot_symbol not in collection:
                collection.append(mapping.autobot_symbol)
        collection_symbols = tuple(collection)
    for requested in symbols:
        mapping = _lookup_symbol_mapping(mapping_by_symbol, requested)
        if mapping is None:
            continue
        raw = str(requested).strip().upper()
        mapping_by_symbol[raw] = mapping
        mapping_by_symbol[raw.replace("/", "").replace("-", "").replace("_", "")] = mapping
    return mapping_by_symbol, collection_symbols


def _lookup_symbol_mapping(
    mapping_by_symbol: Mapping[str, KrakenPublicPairMapping],
    symbol: str,
) -> KrakenPublicPairMapping | None:
    requested_symbol = str(symbol).strip().upper()
    return (
        mapping_by_symbol.get(requested_symbol)
        or mapping_by_symbol.get(requested_symbol.replace("/", "").replace("-", "").replace("_", ""))
        or mapping_by_symbol.get(normalize_research_symbol(symbol))
    )
