"""Research-only public spread/depth recorder for AUTOBOT.

This module reads public Kraken top-of-book/depth data only. It never reads
private keys, never submits orders, and is not wired into runtime trading.
"""

from __future__ import annotations

import csv
import hashlib
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
MAX_EXCHANGE_CLOCK_AHEAD_SECONDS = 60.0


@dataclass(frozen=True)
class SpreadDepthSnapshot:
    """One forward-captured public top-of-book observation.

    ``timestamp_local`` and ``timestamp_exchange`` are retained for legacy
    CSV readers.  The explicit point-in-time fields are the canonical source
    for any new research consumer.  A REST capture is useful research evidence
    but does *not* prove runtime-feed parity, so it cannot by itself authorize
    shadow, paper or live activity.
    """

    timestamp_local: str
    timestamp_exchange: str | None
    event_time: str
    available_time: str
    ingestion_time: str
    symbol: str
    base_asset: str
    quote_asset: str
    market_mapping_status: str
    source_snapshot_id: str
    temporal_status: str
    runtime_parity_proven: bool
    exchange_clock_ahead_seconds: float
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
    max_runtime_seconds: float | None = None
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
        if self.max_runtime_seconds is not None and self.max_runtime_seconds <= 0.0:
            raise ValueError("max_runtime_seconds must be positive when configured")


@dataclass(frozen=True)
class SpreadDepthRecorderResult:
    run_id: str
    generated_at: str
    provider: str
    snapshots: tuple[SpreadDepthSnapshot, ...]
    summary_by_symbol: dict[str, dict[str, float]]
    errors: tuple[dict[str, Any], ...] = ()
    stop_reason: str | None = None
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
            "stop_reason": self.stop_reason,
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
    monotonic_clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> SpreadDepthRecorderResult:
    fetch = fetcher or fetch_kraken_depth_page
    mapping_by_symbol, collection_symbols = _resolve_collection_symbols(
        config.symbols,
        asset_pairs_fetcher=asset_pairs_fetcher,
        symbol_mappings=symbol_mappings,
    )
    snapshots: list[SpreadDepthSnapshot] = []
    errors: list[dict[str, Any]] = []
    deadline = (
        monotonic_clock() + config.max_runtime_seconds
        if config.max_runtime_seconds is not None
        else None
    )
    stop_reason: str | None = None
    for sample_index in range(config.samples):
        if _deadline_reached(deadline, monotonic_clock):
            stop_reason = "max_runtime_seconds_elapsed"
            break
        for symbol in collection_symbols:
            if _deadline_reached(deadline, monotonic_clock):
                stop_reason = "max_runtime_seconds_elapsed"
                break
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
                        mapping=mapping,
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
        if stop_reason:
            break
        if sample_index < config.samples - 1 and config.sleep_seconds:
            remaining_seconds = _remaining_seconds(deadline, monotonic_clock)
            if remaining_seconds is not None and remaining_seconds <= 0.0:
                stop_reason = "max_runtime_seconds_elapsed"
                break
            sleep(
                min(config.sleep_seconds, remaining_seconds)
                if remaining_seconds is not None
                else config.sleep_seconds
            )
    result = SpreadDepthRecorderResult(
        run_id=config.run_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        provider=config.provider,
        snapshots=tuple(snapshots),
        summary_by_symbol=_summary_by_symbol(snapshots),
        errors=tuple(errors),
        stop_reason=stop_reason,
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
                    "event_time",
                    "available_time",
                    "ingestion_time",
                    "symbol",
                    "base_asset",
                    "quote_asset",
                    "market_mapping_status",
                    "source_snapshot_id",
                    "temporal_status",
                    "runtime_parity_proven",
                    "exchange_clock_ahead_seconds",
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
        stop_reason=result.stop_reason,
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
        f"Stop reason: `{result.stop_reason or 'completed'}`",
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
    mapping: KrakenPublicPairMapping,
    provider: str,
    latency_ms: float,
) -> SpreadDepthSnapshot:
    if mapping.market_mapping_status != "EXPLICIT" or not mapping.base_asset or not mapping.quote_asset:
        raise ValueError(
            f"explicit Kraken base/quote mapping is required for {mapping.autobot_symbol}; "
            "refusing an implicit depth-currency conversion"
        )
    if mapping.quote_asset != "EUR":
        raise ValueError(
            f"spread/depth recorder is EUR-quote only for now; {mapping.autobot_symbol} "
            f"has explicit quote {mapping.quote_asset} and cannot be silently converted"
        )
    symbol = mapping.autobot_symbol
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
    local_received_at = datetime.now(timezone.utc)
    event_at = _parse_timestamp(timestamp_exchange) if timestamp_exchange else local_received_at
    clock_ahead_seconds = max(0.0, (event_at - local_received_at).total_seconds())
    if clock_ahead_seconds > MAX_EXCHANGE_CLOCK_AHEAD_SECONDS:
        raise ValueError(f"future exchange timestamp rejected for {symbol}")
    # Public book timestamps are whole seconds while the local receive clock
    # has microsecond precision.  A small exchange/local clock skew is normal;
    # normalize *forward* to the later timestamp so research never treats a
    # quote as known before the exchange says it existed.
    ingestion_at = max(local_received_at, event_at)
    # The REST response becomes usable only when AUTOBOT has received it.
    # Kraken does not expose a separate public availability timestamp, so the
    # conservative availability bound is this local ingestion instant.
    ingestion_time = ingestion_at.isoformat()
    source_snapshot_id = _source_snapshot_id(
        provider=provider,
        mapping=mapping,
        event_time=event_at.isoformat(),
        best_bid=best_bid,
        best_ask=best_ask,
        bid_depth_eur=_depth_eur(bids),
        ask_depth_eur=_depth_eur(asks),
    )
    return SpreadDepthSnapshot(
        timestamp_local=local_received_at.isoformat(),
        timestamp_exchange=timestamp_exchange,
        event_time=event_at.isoformat(),
        available_time=ingestion_time,
        ingestion_time=ingestion_time,
        symbol=symbol,
        base_asset=mapping.base_asset,
        quote_asset=mapping.quote_asset,
        market_mapping_status=mapping.market_mapping_status,
        source_snapshot_id=source_snapshot_id,
        temporal_status="FORWARD_PUBLIC_REST_INGESTED",
        runtime_parity_proven=False,
        exchange_clock_ahead_seconds=clock_ahead_seconds,
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


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("exchange timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _source_snapshot_id(
    *,
    provider: str,
    mapping: KrakenPublicPairMapping,
    event_time: str,
    best_bid: float,
    best_ask: float,
    bid_depth_eur: float,
    ask_depth_eur: float,
) -> str:
    """Return a deterministic identity for an economic depth observation."""

    payload = {
        "provider": provider,
        "symbol": mapping.autobot_symbol,
        "kraken_symbol": mapping.kraken_ohlcv_symbol,
        "base_asset": mapping.base_asset,
        "quote_asset": mapping.quote_asset,
        "event_time": event_time,
        "best_bid": best_bid,
        "best_ask": best_ask,
        "bid_depth_eur": bid_depth_eur,
        "ask_depth_eur": ask_depth_eur,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return f"kraken_depth_{hashlib.sha256(encoded.encode('utf-8')).hexdigest()[:24]}"


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


def _deadline_reached(deadline: float | None, monotonic_clock: Callable[[], float]) -> bool:
    return deadline is not None and monotonic_clock() >= deadline


def _remaining_seconds(deadline: float | None, monotonic_clock: Callable[[], float]) -> float | None:
    return None if deadline is None else max(0.0, deadline - monotonic_clock())


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
