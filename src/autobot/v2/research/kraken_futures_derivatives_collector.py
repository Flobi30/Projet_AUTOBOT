"""Research-only Kraken Futures derivatives data collector.

This module uses public Kraken Futures market-data endpoints only. It stores
raw official responses for audit, writes canonical derivatives datasets, and
does not import or call AUTOBOT runtime router/executor/order paths.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import shutil
import time
import urllib.parse
import urllib.request
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence


KRAKEN_FUTURES_BASE_URL = "https://futures.kraken.com"
TICKERS_ENDPOINT = "/derivatives/api/v3/tickers"
INSTRUMENTS_ENDPOINT = "/derivatives/api/v3/instruments"
HISTORICAL_FUNDING_ENDPOINT = "/derivatives/api/v3/historical-funding-rates"
CHARTS_ENDPOINT_PREFIX = "/api/charts/v1"
ALLOWED_CHART_TICK_TYPES = {"trade", "mark", "spot"}
ORDER_ENDPOINT_TOKENS = ("sendorder", "cancel", "editorder", "batchorder", "order", "private")
BASE_ALIASES = {"XBT": "BTC"}
AUTOBOT_SPOT_SYMBOLS = {
    "BTC": "BTCZEUR",
    "ETH": "ETHZEUR",
    "SOL": "SOLEUR",
    "XRP": "XRPZEUR",
    "ADA": "ADAEUR",
    "LINK": "LINKEUR",
}
TIMEFRAME_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3_600, "4h": 14_400, "1d": 86_400}
DERIVATIVES_SCHEMA_VERSION = 2
# A single current ticker is useful for monitoring, but it is not a history.
# These conservative forward-collection requirements intentionally keep
# funding/basis research blocked while the public ticker archive is young.
FORWARD_HISTORY_MIN_COVERAGE_SECONDS = 7 * 24 * 60 * 60
FORWARD_HISTORY_MIN_OBSERVATIONS_PER_SYMBOL = 96


@dataclass(frozen=True)
class KrakenFuturesInstrumentMapping:
    futures_symbol: str
    base_asset: str
    quote_asset: str
    pair: str
    autobot_spot_symbol: str | None
    raw_symbol: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class KrakenFuturesCollectorConfig:
    run_id: str
    priority_assets: tuple[str, ...] = ("BTC", "ETH", "SOL", "XRP", "ADA", "LINK")
    max_symbols: int = 2
    tick_types: tuple[str, ...] = ("trade", "mark", "spot")
    resolution: str = "1m"
    max_candles: int = 25
    raw_dir: Path = Path("data/research/raw/kraken_futures")
    canonical_dir: Path = Path("data/research/canonical/derivatives")
    manifest_dir: Path = Path("data/research/manifests")
    report_dir: Path = Path("reports/research/kraken_futures_derivatives")
    collect_funding: bool = True
    collect_tickers: bool = True
    collect_candles: bool = True
    sleep_seconds: float = 0.0
    timeout_seconds: float = 20.0
    continue_on_error: bool = False
    observed_at: datetime | None = None
    raw_retention_days: int | None = None

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id must not be empty")
        if not self.priority_assets:
            raise ValueError("priority_assets must not be empty")
        if self.max_symbols <= 0 or self.max_symbols > 20:
            raise ValueError("max_symbols must be between 1 and 20")
        if self.max_candles <= 0 or self.max_candles > 2_000:
            raise ValueError("max_candles must be between 1 and 2000")
        if self.sleep_seconds < 0.0:
            raise ValueError("sleep_seconds cannot be negative")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.raw_retention_days is not None and self.raw_retention_days < 0:
            raise ValueError("raw_retention_days must be non-negative when provided")
        if self.observed_at is not None and (self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None):
            raise ValueError("observed_at must be timezone-aware when provided")
        unknown_ticks = sorted(set(self.tick_types) - ALLOWED_CHART_TICK_TYPES)
        if unknown_ticks:
            raise ValueError(f"unsupported Kraken Futures tick types: {', '.join(unknown_ticks)}")


@dataclass(frozen=True)
class KrakenFuturesDatasetSummary:
    dataset_id: str
    row_count: int
    duplicate_count: int
    invalid_count: int
    start_at: str | None
    end_at: str | None
    csv_path: str | None
    storage_size_bytes: int
    quality_status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class KrakenFuturesCollectionResult:
    run_id: str
    generated_at: str
    snapshot_id: str
    fingerprint: str
    provenance_fingerprint: str
    mappings: tuple[KrakenFuturesInstrumentMapping, ...]
    datasets: tuple[KrakenFuturesDatasetSummary, ...]
    errors: tuple[dict[str, Any], ...]
    raw_response_count: int
    funding_history_ready: bool
    funding_history_start: str | None
    funding_history_end: str | None
    mark_candles_ready: bool
    trade_candles_ready: bool
    spot_reference_candles_ready: bool
    current_open_interest_ready: bool
    open_interest_history_ready: bool
    predicted_funding_ready: bool
    basis_current_ready: bool
    basis_history_ready: bool
    basis_confidence_status: str
    derivatives_data_quality: str
    funding_history_row_count: int = 0
    funding_history_path: str | None = None
    derivatives_candle_history_row_count: int = 0
    derivatives_candle_history_path: str | None = None
    basis_history_row_count: int = 0
    basis_history_start: str | None = None
    basis_history_end: str | None = None
    basis_history_path: str | None = None
    open_interest_history_row_count: int = 0
    open_interest_history_start: str | None = None
    open_interest_history_end: str | None = None
    open_interest_history_path: str | None = None
    raw_retention_deleted_run_count: int = 0
    raw_retention_reclaimed_bytes: int = 0
    manifest_path: str | None = None
    markdown_report_path: str | None = None
    paper_capital_allowed: bool = False
    live_allowed: bool = False
    promotable: bool = False
    schema_version: int = DERIVATIVES_SCHEMA_VERSION
    safety_notes: tuple[str, ...] = (
        "Research-only Kraken Futures public market-data collection.",
        "No private endpoint, order endpoint, API key, paper capital, live trading, promotion, shadow activation, sizing, leverage, UI, or runtime order path.",
        "Raw official responses are preserved for audit.",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "snapshot_id": self.snapshot_id,
            "fingerprint": self.fingerprint,
            "provenance_fingerprint": self.provenance_fingerprint,
            "mappings": [item.to_dict() for item in self.mappings],
            "datasets": [item.to_dict() for item in self.datasets],
            "errors": list(self.errors),
            "raw_response_count": self.raw_response_count,
            "funding_history_ready": self.funding_history_ready,
            "funding_history_start": self.funding_history_start,
            "funding_history_end": self.funding_history_end,
            "mark_candles_ready": self.mark_candles_ready,
            "trade_candles_ready": self.trade_candles_ready,
            "spot_reference_candles_ready": self.spot_reference_candles_ready,
            "current_open_interest_ready": self.current_open_interest_ready,
            "open_interest_history_ready": self.open_interest_history_ready,
            "predicted_funding_ready": self.predicted_funding_ready,
            "basis_current_ready": self.basis_current_ready,
            "basis_history_ready": self.basis_history_ready,
            "basis_confidence_status": self.basis_confidence_status,
            "derivatives_data_quality": self.derivatives_data_quality,
            "funding_history_row_count": self.funding_history_row_count,
            "funding_history_path": self.funding_history_path,
            "derivatives_candle_history_row_count": self.derivatives_candle_history_row_count,
            "derivatives_candle_history_path": self.derivatives_candle_history_path,
            "basis_history_row_count": self.basis_history_row_count,
            "basis_history_start": self.basis_history_start,
            "basis_history_end": self.basis_history_end,
            "basis_history_path": self.basis_history_path,
            "open_interest_history_row_count": self.open_interest_history_row_count,
            "open_interest_history_start": self.open_interest_history_start,
            "open_interest_history_end": self.open_interest_history_end,
            "open_interest_history_path": self.open_interest_history_path,
            "raw_retention_deleted_run_count": self.raw_retention_deleted_run_count,
            "raw_retention_reclaimed_bytes": self.raw_retention_reclaimed_bytes,
            "manifest_path": self.manifest_path,
            "markdown_report_path": self.markdown_report_path,
            "paper_capital_allowed": self.paper_capital_allowed,
            "live_allowed": self.live_allowed,
            "promotable": self.promotable,
            "safety_notes": list(self.safety_notes),
        }


class KrakenFuturesClient(Protocol):
    def get_json(self, endpoint: str, params: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        ...


class KrakenFuturesPublicClient:
    """Tiny public Kraken Futures HTTP client with endpoint guardrails."""

    def __init__(self, *, base_url: str = KRAKEN_FUTURES_BASE_URL, timeout_seconds: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def get_json(self, endpoint: str, params: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        assert_public_kraken_futures_endpoint(endpoint)
        query = f"?{urllib.parse.urlencode(dict(params or {}))}" if params else ""
        url = f"{self.base_url}{endpoint}{query}"
        with urllib.request.urlopen(url, timeout=self.timeout_seconds) as response:  # nosec B310 - fixed public HTTPS API.
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError(f"unexpected Kraken Futures response for {endpoint}")
        return payload


def assert_public_kraken_futures_endpoint(endpoint: str) -> None:
    lowered = endpoint.lower()
    if any(token in lowered for token in ORDER_ENDPOINT_TOKENS):
        raise ValueError(f"forbidden Kraken Futures endpoint for research collector: {endpoint}")
    allowed = (
        endpoint == TICKERS_ENDPOINT
        or endpoint == INSTRUMENTS_ENDPOINT
        or endpoint == HISTORICAL_FUNDING_ENDPOINT
        or endpoint.startswith(f"{CHARTS_ENDPOINT_PREFIX}/")
    )
    if not allowed:
        raise ValueError(f"endpoint is not on the P18J public allow-list: {endpoint}")


def collect_kraken_futures_derivatives(
    config: KrakenFuturesCollectorConfig,
    *,
    client: KrakenFuturesClient | None = None,
) -> KrakenFuturesCollectionResult:
    """Collect a bounded Kraken Futures derivatives research snapshot."""

    api = client or KrakenFuturesPublicClient(timeout_seconds=config.timeout_seconds)
    collection_time = _collection_time(config)
    raw_run_dir = config.raw_dir / config.run_id
    raw_run_dir.mkdir(parents=True, exist_ok=True)
    config.canonical_dir.mkdir(parents=True, exist_ok=True)
    config.manifest_dir.mkdir(parents=True, exist_ok=True)
    config.report_dir.mkdir(parents=True, exist_ok=True)

    raw_response_count = 0
    errors: list[dict[str, Any]] = []
    ticker_payload = _safe_fetch(api, TICKERS_ENDPOINT, raw_run_dir / "tickers.json", errors, config.continue_on_error)
    raw_response_count += 1 if ticker_payload is not None else 0
    instruments_payload = _safe_fetch(api, INSTRUMENTS_ENDPOINT, raw_run_dir / "instruments.json", errors, config.continue_on_error)
    raw_response_count += 1 if instruments_payload is not None else 0
    mappings = discover_priority_perpetuals(ticker_payload or {}, instruments_payload or {}, config.priority_assets)
    mappings = mappings[: config.max_symbols]

    funding_rows: list[dict[str, Any]] = []
    ticker_rows: list[dict[str, Any]] = []
    candle_rows: list[dict[str, Any]] = []
    basis_rows: list[dict[str, Any]] = []
    invalid_rows: list[dict[str, Any]] = []

    if config.collect_tickers and ticker_payload:
        ticker_rows.extend(
            _ticker_rows_from_payload(
                ticker_payload,
                mappings,
                invalid_rows=invalid_rows,
                ingestion_time=collection_time,
            )
        )
        basis_rows.extend(_basis_rows_from_tickers(ticker_rows, invalid_rows=invalid_rows))

    for mapping in mappings:
        if config.collect_funding:
            payload = _safe_fetch(
                api,
                HISTORICAL_FUNDING_ENDPOINT,
                raw_run_dir / f"{mapping.futures_symbol}_historical_funding.json",
                errors,
                config.continue_on_error,
                params={"symbol": mapping.futures_symbol},
            )
            raw_response_count += 1 if payload is not None else 0
            if payload:
                funding_rows.extend(
                    _funding_rows_from_payload(
                        payload,
                        mapping,
                        invalid_rows=invalid_rows,
                        ingestion_time=collection_time,
                    )
                )
            _sleep(config.sleep_seconds)
        if config.collect_candles:
            for tick_type in config.tick_types:
                endpoint = f"{CHARTS_ENDPOINT_PREFIX}/{tick_type}/{mapping.futures_symbol}/{config.resolution}"
                payload = _safe_fetch(
                    api,
                    endpoint,
                    raw_run_dir / f"{mapping.futures_symbol}_{tick_type}_{config.resolution}_candles.json",
                    errors,
                    config.continue_on_error,
                )
                raw_response_count += 1 if payload is not None else 0
                if payload:
                    candle_rows.extend(
                        _candle_rows_from_payload(
                            payload,
                            mapping,
                            tick_type=tick_type,
                            timeframe=config.resolution,
                            max_candles=config.max_candles,
                            invalid_rows=invalid_rows,
                            ingestion_time=collection_time,
                        )
                    )
                _sleep(config.sleep_seconds)

    funding_rows, funding_dupes = _dedupe_rows(funding_rows, ("exchange", "futures_symbol", "timestamp"))
    ticker_rows, ticker_dupes = _dedupe_rows(ticker_rows, ("exchange", "futures_symbol", "timestamp"))
    candle_rows, candle_dupes = _dedupe_rows(candle_rows, ("exchange", "futures_symbol", "tick_type", "timeframe", "timestamp"))
    basis_rows, basis_dupes = _dedupe_rows(basis_rows, ("exchange", "futures_symbol", "timestamp", "calculation_method"))

    funding_path = _write_csv(
        funding_rows,
        config.canonical_dir / "funding" / f"{config.run_id}_funding_rates.csv",
        (
            "schema_version", "exchange", "futures_symbol", "base_asset", "timestamp", "event_time", "available_time",
            "ingestion_time", "temporal_status", "funding_rate_absolute", "funding_rate_relative", "source", "source_endpoint",
        ),
    )
    ticker_path = _write_csv(
        ticker_rows,
        config.canonical_dir / "tickers" / f"{config.run_id}_ticker_snapshots.csv",
        (
            "schema_version", "timestamp", "event_time", "available_time", "ingestion_time", "temporal_status", "timestamp_source",
            "exchange",
            "futures_symbol",
            "base_asset",
            "quote_asset",
            "mark_price",
            "index_price",
            "bid",
            "ask",
            "premium",
            "current_funding_rate",
            "predicted_funding_rate",
            "next_funding_timestamp",
            "open_interest",
            "volume",
            "suspended",
            "post_only",
            "source", "source_endpoint",
        ),
    )
    candle_path = _write_csv(
        candle_rows,
        config.canonical_dir / "candles" / f"{config.run_id}_derivatives_candles.csv",
        (
            "schema_version", "timestamp", "event_time", "available_time", "ingestion_time", "bar_close_time", "temporal_status",
            "exchange",
            "futures_symbol",
            "base_asset",
            "quote_asset",
            "tick_type",
            "timeframe",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "source", "source_endpoint",
        ),
    )
    basis_path = _write_csv(
        basis_rows,
        config.canonical_dir / "basis" / f"{config.run_id}_basis.csv",
        (
            "schema_version", "timestamp", "event_time", "available_time", "ingestion_time", "temporal_status",
            "exchange",
            "futures_symbol",
            "base_asset",
            "quote_asset",
            "basis_bps",
            "mark_price",
            "index_or_reference_price",
            "calculation_method",
            "confidence_status",
            "source", "source_endpoint",
        ),
    )

    # The collector writes one immutable file per run.  Read the canonical
    # archive after the current rows have been persisted so readiness reflects
    # the accumulated forward history, never just the latest snapshot.
    funding_history_rows, funding_history_path, _funding_history_duplicates = _load_or_compact_canonical_history(
        config.canonical_dir / "funding",
        history_filename="funding_history.csv",
        key_fields=("exchange", "futures_symbol", "timestamp"),
        fieldnames=(
            "schema_version", "exchange", "futures_symbol", "base_asset", "timestamp", "event_time", "available_time",
            "ingestion_time", "temporal_status", "funding_rate_absolute", "funding_rate_relative", "source", "source_endpoint",
        ),
        compact=config.collect_funding,
    )
    candle_history_rows, candle_history_path, _candle_history_duplicates = _load_or_compact_canonical_history(
        config.canonical_dir / "candles",
        history_filename="derivatives_candle_history.csv",
        key_fields=("exchange", "futures_symbol", "tick_type", "timeframe", "timestamp"),
        fieldnames=(
            "schema_version", "timestamp", "event_time", "available_time", "ingestion_time", "bar_close_time", "temporal_status",
            "exchange", "futures_symbol", "base_asset", "quote_asset", "tick_type", "timeframe", "open", "high", "low", "close",
            "volume", "source", "source_endpoint",
        ),
        compact=config.collect_candles,
    )
    ticker_history_rows, ticker_history_path, _ticker_history_duplicates = _compact_canonical_history(
        config.canonical_dir / "tickers",
        history_filename="ticker_history.csv",
        key_fields=("exchange", "futures_symbol", "timestamp"),
        fieldnames=(
            "schema_version", "timestamp", "event_time", "available_time", "ingestion_time", "temporal_status", "timestamp_source",
            "exchange", "futures_symbol", "base_asset", "quote_asset", "mark_price", "index_price", "bid", "ask", "premium",
            "current_funding_rate", "predicted_funding_rate", "next_funding_timestamp", "open_interest", "volume", "suspended", "post_only",
            "source", "source_endpoint",
        ),
    )
    basis_history_rows, basis_history_path, _basis_history_duplicates = _compact_canonical_history(
        config.canonical_dir / "basis",
        history_filename="basis_history.csv",
        key_fields=("exchange", "futures_symbol", "timestamp", "calculation_method"),
        fieldnames=(
            "schema_version", "timestamp", "event_time", "available_time", "ingestion_time", "temporal_status", "exchange",
            "futures_symbol", "base_asset", "quote_asset", "basis_bps", "mark_price", "index_or_reference_price",
            "calculation_method", "confidence_status", "source", "source_endpoint",
        ),
    )
    open_interest_history_rows = [
        row
        for row in ticker_history_rows
        if _safe_float(row.get("open_interest")) is not None and _safe_float(row.get("open_interest")) >= 0.0
    ]
    valid_basis_history_rows = [
        row
        for row in basis_history_rows
        if row.get("confidence_status") == "MARK_INDEX_SAME_QUOTE"
    ]
    open_interest_history_ready = _forward_history_ready(open_interest_history_rows, mappings)
    basis_history_ready = _forward_history_ready(valid_basis_history_rows, mappings)

    datasets = (
        _dataset_summary("funding_rates", funding_rows, funding_dupes, _invalid_count(invalid_rows, "funding_rates"), funding_path, "historical_funding_ready" if funding_rows else "missing"),
        _dataset_summary("ticker_snapshots", ticker_rows, ticker_dupes, _invalid_count(invalid_rows, "ticker_snapshots"), ticker_path, "current_snapshot_ready" if ticker_rows else "missing"),
        _dataset_summary("derivatives_candles", candle_rows, candle_dupes, _invalid_count(invalid_rows, "derivatives_candles"), candle_path, "bounded_candle_sample_ready" if candle_rows else "missing"),
        _dataset_summary("basis", basis_rows, basis_dupes, _invalid_count(invalid_rows, "basis"), basis_path, _basis_quality(basis_rows)),
    )
    all_datasets = {
        "funding_rates": funding_rows,
        "ticker_snapshots": ticker_rows,
        "derivatives_candles": candle_rows,
        "basis": basis_rows,
    }
    fingerprint = fingerprint_derivatives_rows(all_datasets)
    provenance_fingerprint = fingerprint_derivatives_rows(all_datasets, include_provenance=True)
    result = KrakenFuturesCollectionResult(
        run_id=config.run_id,
        generated_at=collection_time.isoformat(),
        snapshot_id=f"kraken_futures_{fingerprint[:16]}",
        fingerprint=fingerprint,
        provenance_fingerprint=provenance_fingerprint,
        mappings=tuple(mappings),
        datasets=datasets,
        errors=tuple([*errors, *invalid_rows]),
        raw_response_count=raw_response_count,
        funding_history_ready=bool(funding_history_rows),
        funding_history_start=_min_timestamp(funding_history_rows),
        funding_history_end=_max_timestamp(funding_history_rows),
        mark_candles_ready=any(row.get("tick_type") == "mark" for row in candle_history_rows),
        trade_candles_ready=any(row.get("tick_type") == "trade" for row in candle_history_rows),
        spot_reference_candles_ready=any(row.get("tick_type") == "spot" for row in candle_history_rows),
        current_open_interest_ready=any(_safe_float(row.get("open_interest")) is not None for row in ticker_rows),
        open_interest_history_ready=open_interest_history_ready,
        predicted_funding_ready=any(_safe_float(row.get("predicted_funding_rate")) is not None for row in ticker_rows),
        basis_current_ready=bool(basis_rows),
        basis_history_ready=basis_history_ready,
        basis_confidence_status=_aggregate_basis_confidence(basis_rows),
        derivatives_data_quality=_quality_label(funding_history_rows, ticker_rows, candle_history_rows, basis_rows),
        funding_history_row_count=len(funding_history_rows),
        funding_history_path=str(funding_history_path),
        derivatives_candle_history_row_count=len(candle_history_rows),
        derivatives_candle_history_path=str(candle_history_path),
        basis_history_row_count=len(valid_basis_history_rows),
        basis_history_start=_min_timestamp(valid_basis_history_rows),
        basis_history_end=_max_timestamp(valid_basis_history_rows),
        basis_history_path=str(basis_history_path),
        open_interest_history_row_count=len(open_interest_history_rows),
        open_interest_history_start=_min_timestamp(open_interest_history_rows),
        open_interest_history_end=_max_timestamp(open_interest_history_rows),
        open_interest_history_path=str(ticker_history_path),
    )
    persisted = write_kraken_futures_derivatives_report(result, config)
    if config.raw_retention_days is None or persisted.errors:
        return persisted
    deleted_count, reclaimed_bytes = _prune_raw_runs(
        raw_dir=config.raw_dir,
        current_run_id=config.run_id,
        retention_days=config.raw_retention_days,
        now=collection_time,
    )
    if not deleted_count:
        return persisted
    return write_kraken_futures_derivatives_report(
        replace(
            persisted,
            raw_retention_deleted_run_count=deleted_count,
            raw_retention_reclaimed_bytes=reclaimed_bytes,
        ),
        config,
    )


def discover_priority_perpetuals(
    ticker_payload: Mapping[str, Any],
    instruments_payload: Mapping[str, Any] | None,
    priority_assets: Sequence[str],
) -> tuple[KrakenFuturesInstrumentMapping, ...]:
    tickers = ticker_payload.get("tickers") or ()
    priority = [_normalize_base_asset(item) for item in priority_assets]
    by_base: dict[str, KrakenFuturesInstrumentMapping] = {}
    for ticker in tickers:
        if not isinstance(ticker, Mapping):
            continue
        symbol = str(ticker.get("symbol") or "").upper()
        tag = str(ticker.get("tag") or "").lower()
        if tag != "perpetual" or not symbol.startswith("PF_"):
            continue
        pair = str(ticker.get("pair") or "")
        base, quote = _base_quote_from_pair(pair, symbol)
        base = _normalize_base_asset(base)
        quote = quote.upper()
        if quote != "USD" or base not in priority:
            continue
        by_base.setdefault(
            base,
            KrakenFuturesInstrumentMapping(
                futures_symbol=symbol,
                base_asset=base,
                quote_asset=quote,
                pair=f"{base}:{quote}",
                autobot_spot_symbol=AUTOBOT_SPOT_SYMBOLS.get(base),
                raw_symbol=symbol,
            ),
        )
    return tuple(by_base[base] for base in priority if base in by_base)


def calculate_basis_bps(
    *,
    mark_price: float,
    reference_price: float,
    mark_quote: str,
    reference_quote: str,
) -> tuple[float | None, str]:
    if mark_quote.upper() != reference_quote.upper():
        return None, "BASIS_REFERENCE_UNVERIFIED"
    if mark_price <= 0.0 or reference_price <= 0.0:
        return None, "BASIS_INVALID_PRICE"
    return ((mark_price / reference_price) - 1.0) * 10_000.0, "MARK_INDEX_SAME_QUOTE"


def fingerprint_derivatives_rows(
    datasets: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    include_provenance: bool = False,
) -> str:
    digest = hashlib.sha256()
    for dataset_id in sorted(datasets):
        canonical_rows = [_economic_row(row, include_provenance=include_provenance) for row in datasets[dataset_id]]
        for row in sorted(canonical_rows, key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":"))):
            digest.update(dataset_id.encode("utf-8"))
            digest.update(b":")
            digest.update(json.dumps(row, sort_keys=True, separators=(",", ":")).encode("utf-8"))
            digest.update(b"\n")
    return digest.hexdigest()


def _economic_row(row: Mapping[str, Any], *, include_provenance: bool) -> dict[str, Any]:
    ignored = set()
    if not include_provenance:
        ignored = {
            "schema_version",
            "ingestion_time",
            "temporal_status",
            "source_endpoint",
            "timestamp_source",
            "source_request_params",
        }
    return {str(key): value for key, value in row.items() if str(key) not in ignored}


def write_kraken_futures_derivatives_report(
    result: KrakenFuturesCollectionResult,
    config: KrakenFuturesCollectorConfig,
) -> KrakenFuturesCollectionResult:
    config.manifest_dir.mkdir(parents=True, exist_ok=True)
    config.report_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = config.manifest_dir / f"{result.run_id}_kraken_futures_derivatives.json"
    markdown_path = config.report_dir / f"{result.run_id}.md"
    with_paths = KrakenFuturesCollectionResult(
        **{
            **result.to_dict(),
            "mappings": result.mappings,
            "datasets": result.datasets,
            "errors": result.errors,
            "safety_notes": result.safety_notes,
            "manifest_path": str(manifest_path),
            "markdown_report_path": str(markdown_path),
        }
    )
    manifest_path.write_text(json.dumps(with_paths.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(render_kraken_futures_derivatives_report(with_paths), encoding="utf-8")
    return with_paths


def render_kraken_futures_derivatives_report(result: KrakenFuturesCollectionResult) -> str:
    lines = [
        f"# Kraken Futures Derivatives Collection - {result.run_id}",
        "",
        f"Generated at: `{result.generated_at}`",
        f"Snapshot: `{result.snapshot_id}`",
        f"Fingerprint: `{result.fingerprint}`",
        f"Provenance fingerprint: `{result.provenance_fingerprint}`",
        "",
        "## Mappings",
        "",
        "| Futures Symbol | Base | Quote | AUTOBOT Spot Symbol | Pair |",
        "| --- | --- | --- | --- | --- |",
    ]
    for mapping in result.mappings:
        lines.append(
            f"| `{mapping.futures_symbol}` | `{mapping.base_asset}` | `{mapping.quote_asset}` | "
            f"`{mapping.autobot_spot_symbol or '-'}` | `{mapping.pair}` |"
        )
    lines.extend(["", "## Datasets", ""])
    lines.append("| Dataset | Rows | Duplicates | Invalid | Start | End | Quality | Path |")
    lines.append("| --- | ---: | ---: | ---: | --- | --- | --- | --- |")
    for item in result.datasets:
        lines.append(
            f"| `{item.dataset_id}` | {item.row_count} | {item.duplicate_count} | {item.invalid_count} | "
            f"{item.start_at or '-'} | {item.end_at or '-'} | `{item.quality_status}` | `{item.csv_path or '-'}` |"
        )
    lines.extend(
        [
            "",
            "## Readiness",
            "",
            f"- funding_history_ready: `{result.funding_history_ready}`",
            f"- funding_history_start: `{result.funding_history_start}`",
            f"- funding_history_end: `{result.funding_history_end}`",
            f"- funding_history_rows: `{result.funding_history_row_count}`",
            f"- funding_history_path: `{result.funding_history_path or '-'}`",
            f"- mark_candles_ready: `{result.mark_candles_ready}`",
            f"- trade_candles_ready: `{result.trade_candles_ready}`",
            f"- spot_reference_candles_ready: `{result.spot_reference_candles_ready}`",
            f"- derivatives_candle_history_rows: `{result.derivatives_candle_history_row_count}`",
            f"- derivatives_candle_history_path: `{result.derivatives_candle_history_path or '-'}`",
            f"- current_open_interest_ready: `{result.current_open_interest_ready}`",
            f"- open_interest_history_ready: `{result.open_interest_history_ready}`",
            f"- predicted_funding_ready: `{result.predicted_funding_ready}`",
            f"- basis_current_ready: `{result.basis_current_ready}`",
            f"- basis_history_ready: `{result.basis_history_ready}`",
            f"- basis_history_rows: `{result.basis_history_row_count}`",
            f"- basis_history_period: `{result.basis_history_start or '-'} -> {result.basis_history_end or '-'}`",
            f"- basis_history_path: `{result.basis_history_path or '-'}`",
            f"- basis_confidence_status: `{result.basis_confidence_status}`",
            f"- open_interest_history_rows: `{result.open_interest_history_row_count}`",
            f"- open_interest_history_period: `{result.open_interest_history_start or '-'} -> {result.open_interest_history_end or '-'}`",
            f"- open_interest_history_path: `{result.open_interest_history_path or '-'}`",
            f"- forward_history_policy: `{FORWARD_HISTORY_MIN_OBSERVATIONS_PER_SYMBOL} observations per symbol across at least {FORWARD_HISTORY_MIN_COVERAGE_SECONDS // 86400} days`",
            f"- derivatives_data_quality: `{result.derivatives_data_quality}`",
            f"- errors: `{len(result.errors)}`",
            f"- raw_response_count: `{result.raw_response_count}`",
            f"- raw_retention_deleted_run_count: `{result.raw_retention_deleted_run_count}`",
            f"- raw_retention_reclaimed_bytes: `{result.raw_retention_reclaimed_bytes}`",
            "",
            "## Safety",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in result.safety_notes)
    lines.append(f"- paper_capital_allowed: `{result.paper_capital_allowed}`")
    lines.append(f"- live_allowed: `{result.live_allowed}`")
    lines.append(f"- promotable: `{result.promotable}`")
    lines.append("")
    return "\n".join(lines)


def _prune_raw_runs(
    *,
    raw_dir: Path,
    current_run_id: str,
    retention_days: int,
    now: datetime,
) -> tuple[int, int]:
    """Delete only verified old immediate raw-run directories after success.

    Canonical histories and manifests are written before this function is
    called.  The resolver and direct-parent checks make a malformed path or a
    symlink fail closed rather than expanding deletion scope.
    """

    root = raw_dir.resolve()
    if not root.exists() or not root.is_dir():
        return 0, 0
    cutoff = now.timestamp() - (retention_days * 24 * 60 * 60)
    deleted_count = 0
    reclaimed_bytes = 0
    for candidate in root.iterdir():
        if candidate.name == current_run_id or candidate.is_symlink() or not candidate.is_dir():
            continue
        try:
            resolved = candidate.resolve()
            if resolved.parent != root or candidate.stat().st_mtime >= cutoff:
                continue
            size = _directory_size(resolved)
            shutil.rmtree(resolved)
        except OSError:
            continue
        deleted_count += 1
        reclaimed_bytes += size
    return deleted_count, reclaimed_bytes


def _directory_size(path: Path) -> int:
    total = 0
    for child in path.rglob("*"):
        if child.is_file() and not child.is_symlink():
            try:
                total += child.stat().st_size
            except OSError:
                continue
    return total


def _safe_fetch(
    client: KrakenFuturesClient,
    endpoint: str,
    raw_path: Path,
    errors: list[dict[str, Any]],
    continue_on_error: bool,
    params: Mapping[str, Any] | None = None,
) -> Mapping[str, Any] | None:
    try:
        payload = client.get_json(endpoint, params)
        result = payload.get("result")
        if result not in (None, "success"):
            raise ValueError(f"Kraken Futures returned result={result!r}")
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return payload
    except Exception as exc:
        error = {"dataset": "raw_fetch", "endpoint": endpoint, "params": dict(params or {}), "error": str(exc)}
        errors.append(error)
        if not continue_on_error:
            raise
        return None


def _funding_rows_from_payload(
    payload: Mapping[str, Any],
    mapping: KrakenFuturesInstrumentMapping,
    *,
    invalid_rows: list[dict[str, Any]],
    ingestion_time: datetime,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    previous: datetime | None = None
    for item in payload.get("rates") or ():
        if not isinstance(item, Mapping):
            continue
        timestamp = _parse_timestamp(item.get("timestamp"))
        absolute = _safe_float(item.get("fundingRate"))
        relative = _safe_float(item.get("relativeFundingRate"))
        if timestamp is None or absolute is None or relative is None:
            invalid_rows.append({"dataset": "funding_rates", "futures_symbol": mapping.futures_symbol, "reason": "invalid_funding_row"})
            continue
        if previous and timestamp < previous:
            invalid_rows.append({"dataset": "funding_rates", "futures_symbol": mapping.futures_symbol, "reason": "funding_timestamps_not_ordered"})
        previous = timestamp
        rows.append(
            {
                "schema_version": str(DERIVATIVES_SCHEMA_VERSION),
                "exchange": "kraken_futures",
                "futures_symbol": mapping.futures_symbol,
                "base_asset": mapping.base_asset,
                "timestamp": timestamp.isoformat(),
                "event_time": timestamp.isoformat(),
                "available_time": ingestion_time.isoformat(),
                "ingestion_time": ingestion_time.isoformat(),
                "temporal_status": "HISTORICAL_BACKFILL_AVAILABLE_AT_INGESTION",
                "funding_rate_absolute": _stable_number(absolute),
                "funding_rate_relative": _stable_number(relative),
                "source": HISTORICAL_FUNDING_ENDPOINT,
                "source_endpoint": HISTORICAL_FUNDING_ENDPOINT,
            }
        )
    return rows


def _ticker_rows_from_payload(
    payload: Mapping[str, Any],
    mappings: Sequence[KrakenFuturesInstrumentMapping],
    *,
    invalid_rows: list[dict[str, Any]],
    ingestion_time: datetime,
) -> list[dict[str, Any]]:
    by_symbol = {str(item.get("symbol") or "").upper(): item for item in payload.get("tickers") or () if isinstance(item, Mapping)}
    server_time = _parse_timestamp(payload.get("serverTime"))
    timestamp_source = "exchange_server_time" if server_time is not None else "collector_received_at_fallback"
    server_time = server_time or ingestion_time
    rows: list[dict[str, Any]] = []
    for mapping in mappings:
        item = by_symbol.get(mapping.futures_symbol)
        if not item:
            invalid_rows.append({"dataset": "ticker_snapshots", "futures_symbol": mapping.futures_symbol, "reason": "ticker_missing"})
            continue
        mark = _safe_float(item.get("markPrice"))
        index = _safe_float(item.get("indexPrice"))
        bid = _safe_float(item.get("bid"))
        ask = _safe_float(item.get("ask"))
        open_interest = _safe_float(item.get("openInterest"))
        if mark is None or mark <= 0.0 or index is None or index <= 0.0:
            invalid_rows.append({"dataset": "ticker_snapshots", "futures_symbol": mapping.futures_symbol, "reason": "invalid_mark_or_index"})
            continue
        if item.get("openInterest") not in (None, "") and (open_interest is None or open_interest < 0.0):
            invalid_rows.append({"dataset": "ticker_snapshots", "futures_symbol": mapping.futures_symbol, "reason": "negative_open_interest"})
            open_interest = None
        if bid is not None and ask is not None and bid > ask:
            invalid_rows.append({"dataset": "ticker_snapshots", "futures_symbol": mapping.futures_symbol, "reason": "bid_above_ask"})
            continue
        premium = ((mark / index) - 1.0) if index > 0 else None
        rows.append(
            {
                "schema_version": str(DERIVATIVES_SCHEMA_VERSION),
                "timestamp": server_time.isoformat(),
                "event_time": server_time.isoformat(),
                "available_time": server_time.isoformat(),
                "ingestion_time": ingestion_time.isoformat(),
                "temporal_status": "EXCHANGE_SNAPSHOT_TIME",
                "timestamp_source": timestamp_source,
                "exchange": "kraken_futures",
                "futures_symbol": mapping.futures_symbol,
                "base_asset": mapping.base_asset,
                "quote_asset": mapping.quote_asset,
                "mark_price": _stable_number(mark),
                "index_price": _stable_number(index),
                "bid": _stable_number(bid) if bid is not None else "",
                "ask": _stable_number(ask) if ask is not None else "",
                "premium": _stable_number(premium) if premium is not None else "",
                "current_funding_rate": _stable_number(_safe_float(item.get("fundingRate"))) if _safe_float(item.get("fundingRate")) is not None else "",
                "predicted_funding_rate": _stable_number(_safe_float(item.get("fundingRatePrediction"))) if _safe_float(item.get("fundingRatePrediction")) is not None else "",
                "next_funding_timestamp": str(item.get("nextFundingTime") or item.get("nextFundingTimestamp") or ""),
                "open_interest": _stable_number(open_interest) if open_interest is not None else "",
                "volume": _stable_number(_safe_float(item.get("vol24h"))) if _safe_float(item.get("vol24h")) is not None else "",
                "suspended": str(bool(item.get("suspended", False))).lower(),
                "post_only": str(bool(item.get("postOnly", False))).lower(),
                "source": TICKERS_ENDPOINT,
                "source_endpoint": TICKERS_ENDPOINT,
            }
        )
    return rows


def _basis_rows_from_tickers(rows: Sequence[Mapping[str, Any]], *, invalid_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    basis_rows: list[dict[str, Any]] = []
    for row in rows:
        mark = _safe_float(row.get("mark_price"))
        index = _safe_float(row.get("index_price"))
        if mark is None or index is None:
            continue
        basis, status = calculate_basis_bps(
            mark_price=mark,
            reference_price=index,
            mark_quote=str(row.get("quote_asset") or ""),
            reference_quote=str(row.get("quote_asset") or ""),
        )
        if basis is None:
            invalid_rows.append({"dataset": "basis", "futures_symbol": row.get("futures_symbol"), "reason": status})
            continue
        if abs(basis) > 5_000:
            invalid_rows.append({"dataset": "basis", "futures_symbol": row.get("futures_symbol"), "reason": "basis_bps_anomaly"})
            continue
        basis_rows.append(
            {
                "schema_version": str(DERIVATIVES_SCHEMA_VERSION),
                "timestamp": row["timestamp"],
                "event_time": row["event_time"],
                "available_time": row["available_time"],
                "ingestion_time": row["ingestion_time"],
                "temporal_status": row["temporal_status"],
                "exchange": "kraken_futures",
                "futures_symbol": row["futures_symbol"],
                "base_asset": row["base_asset"],
                "quote_asset": row["quote_asset"],
                "basis_bps": _stable_number(basis),
                "mark_price": row["mark_price"],
                "index_or_reference_price": row["index_price"],
                "calculation_method": "mark_over_index",
                "confidence_status": status,
                "source": TICKERS_ENDPOINT,
                "source_endpoint": TICKERS_ENDPOINT,
            }
        )
    return basis_rows


def _candle_rows_from_payload(
    payload: Mapping[str, Any],
    mapping: KrakenFuturesInstrumentMapping,
    *,
    tick_type: str,
    timeframe: str,
    max_candles: int,
    invalid_rows: list[dict[str, Any]],
    ingestion_time: datetime,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    candles = list(payload.get("candles") or ())[-max_candles:]
    for item in candles:
        if not isinstance(item, Mapping):
            continue
        timestamp = _parse_timestamp(item.get("time"))
        open_price = _safe_float(item.get("open"))
        high = _safe_float(item.get("high"))
        low = _safe_float(item.get("low"))
        close = _safe_float(item.get("close"))
        volume = _safe_float(item.get("volume"))
        prices = (open_price, high, low, close)
        if timestamp is None or any(value is None for value in prices) or min(float(value) for value in prices if value is not None) <= 0.0:
            invalid_rows.append({"dataset": "derivatives_candles", "futures_symbol": mapping.futures_symbol, "tick_type": tick_type, "reason": "invalid_candle_prices"})
            continue
        if volume is None or volume < 0.0:
            invalid_rows.append({"dataset": "derivatives_candles", "futures_symbol": mapping.futures_symbol, "tick_type": tick_type, "reason": "invalid_candle_volume"})
            continue
        seconds = TIMEFRAME_SECONDS.get(timeframe)
        if seconds is None:
            invalid_rows.append({"dataset": "derivatives_candles", "futures_symbol": mapping.futures_symbol, "tick_type": tick_type, "reason": "unsupported_timeframe"})
            continue
        bar_close_time = timestamp + timedelta(seconds=seconds)
        if bar_close_time > ingestion_time:
            invalid_rows.append({"dataset": "derivatives_candles", "futures_symbol": mapping.futures_symbol, "tick_type": tick_type, "reason": "unclosed_candle"})
            continue
        rows.append(
            {
                "schema_version": str(DERIVATIVES_SCHEMA_VERSION),
                "timestamp": timestamp.isoformat(),
                "event_time": timestamp.isoformat(),
                "available_time": bar_close_time.isoformat(),
                "ingestion_time": ingestion_time.isoformat(),
                "bar_close_time": bar_close_time.isoformat(),
                "temporal_status": "AVAILABLE_AFTER_BAR_CLOSE",
                "exchange": "kraken_futures",
                "futures_symbol": mapping.futures_symbol,
                "base_asset": mapping.base_asset,
                "quote_asset": mapping.quote_asset,
                "tick_type": tick_type,
                "timeframe": timeframe,
                "open": _stable_number(open_price),
                "high": _stable_number(high),
                "low": _stable_number(low),
                "close": _stable_number(close),
                "volume": _stable_number(volume),
                "source": f"{CHARTS_ENDPOINT_PREFIX}/{tick_type}/{{symbol}}/{{resolution}}",
                "source_endpoint": f"{CHARTS_ENDPOINT_PREFIX}/{tick_type}/{{symbol}}/{{resolution}}",
            }
        )
    return rows


def _dedupe_rows(rows: Sequence[dict[str, Any]], key_fields: Sequence[str]) -> tuple[list[dict[str, Any]], int]:
    seen: dict[tuple[str, ...], dict[str, Any]] = {}
    duplicate_count = 0
    for row in rows:
        key = tuple(str(row.get(field, "")) for field in key_fields)
        if key in seen:
            duplicate_count += 1
            winner = min(seen[key], row, key=lambda item: json.dumps(item, sort_keys=True))
            seen[key] = winner
        else:
            seen[key] = row
    return sorted(seen.values(), key=lambda item: tuple(str(item.get(field, "")) for field in key_fields)), duplicate_count


def _compact_canonical_history(
    dataset_dir: Path,
    *,
    history_filename: str,
    key_fields: Sequence[str],
    fieldnames: Sequence[str],
) -> tuple[list[dict[str, Any]], Path, int]:
    """Build one atomically-published, deduplicated forward-history dataset.

    Per-run CSVs remain immutable audit artifacts.  The compacted history is
    the only input used for readiness; it excludes itself to prevent a retry
    or a previous compaction from multiplying observations.
    """

    dataset_dir.mkdir(parents=True, exist_ok=True)
    run_paths = sorted(path for path in dataset_dir.glob("*.csv") if path.name != history_filename)
    rows: list[dict[str, Any]] = []
    for path in run_paths:
        with path.open("r", encoding="utf-8", newline="") as handle:
            rows.extend(dict(row) for row in csv.DictReader(handle) if row.get("timestamp"))
    deduped_rows, duplicate_count = _dedupe_rows(rows, key_fields)
    history_path = dataset_dir / history_filename
    _write_csv(deduped_rows, history_path, fieldnames)
    return deduped_rows, history_path, duplicate_count


def _load_or_compact_canonical_history(
    dataset_dir: Path,
    *,
    history_filename: str,
    key_fields: Sequence[str],
    fieldnames: Sequence[str],
    compact: bool,
) -> tuple[list[dict[str, Any]], Path, int]:
    """Reuse an existing immutable-history compaction when a run skips it.

    Ticker-only forward collection must not make previously backfilled funding
    or candle capability disappear.  Recompacting those large datasets every
    fifteen minutes would also waste CPU and disk I/O, so they are refreshed
    only when their source is collected or when no compact history exists yet.
    """

    history_path = dataset_dir / history_filename
    if compact or not history_path.exists():
        return _compact_canonical_history(
            dataset_dir,
            history_filename=history_filename,
            key_fields=key_fields,
            fieldnames=fieldnames,
        )
    with history_path.open("r", encoding="utf-8", newline="") as handle:
        rows = [dict(row) for row in csv.DictReader(handle) if row.get("timestamp")]
    deduped_rows, duplicate_count = _dedupe_rows(rows, key_fields)
    if duplicate_count:
        _write_csv(deduped_rows, history_path, fieldnames)
    return deduped_rows, history_path, duplicate_count


def _forward_history_ready(
    rows: Sequence[Mapping[str, Any]],
    mappings: Sequence[KrakenFuturesInstrumentMapping],
) -> bool:
    """Require meaningful coverage for every current mapping before unlocks.

    This is a data-availability gate, deliberately not a strategy-validation
    gate.  A later experiment still needs its own out-of-sample and cost
    validation before it can become shadow eligible.
    """

    if not mappings:
        return False
    by_symbol: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        symbol = str(row.get("futures_symbol") or "")
        if symbol:
            by_symbol.setdefault(symbol, []).append(row)
    for mapping in mappings:
        symbol_rows = by_symbol.get(mapping.futures_symbol, [])
        if len(symbol_rows) < FORWARD_HISTORY_MIN_OBSERVATIONS_PER_SYMBOL:
            return False
        if _time_coverage_seconds(symbol_rows) < FORWARD_HISTORY_MIN_COVERAGE_SECONDS:
            return False
    return True


def _write_csv(rows: Sequence[Mapping[str, Any]], path: Path, fieldnames: Sequence[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    with temporary_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
    temporary_path.replace(path)
    return path


def _dataset_summary(
    dataset_id: str,
    rows: Sequence[Mapping[str, Any]],
    duplicate_count: int,
    invalid_count: int,
    csv_path: Path,
    quality_status: str,
) -> KrakenFuturesDatasetSummary:
    return KrakenFuturesDatasetSummary(
        dataset_id=dataset_id,
        row_count=len(rows),
        duplicate_count=duplicate_count,
        invalid_count=invalid_count,
        start_at=_min_timestamp(rows),
        end_at=_max_timestamp(rows),
        csv_path=str(csv_path),
        storage_size_bytes=csv_path.stat().st_size if csv_path.exists() else 0,
        quality_status=quality_status,
    )


def _basis_quality(rows: Sequence[Mapping[str, Any]]) -> str:
    if not rows:
        return "missing"
    if all(row.get("confidence_status") == "MARK_INDEX_SAME_QUOTE" for row in rows):
        return "current_basis_same_quote_ready"
    return "basis_reference_unverified"


def _quality_label(
    funding_rows: Sequence[Mapping[str, Any]],
    ticker_rows: Sequence[Mapping[str, Any]],
    candle_rows: Sequence[Mapping[str, Any]],
    basis_rows: Sequence[Mapping[str, Any]],
) -> str:
    if funding_rows and ticker_rows and candle_rows and basis_rows:
        return "smoke_ready_current_basis_only"
    if funding_rows and ticker_rows:
        return "partial_derivatives_data"
    return "missing_or_incomplete"


def _aggregate_basis_confidence(rows: Sequence[Mapping[str, Any]]) -> str:
    if not rows:
        return "BASIS_MISSING"
    statuses = {str(row.get("confidence_status") or "") for row in rows}
    if statuses == {"MARK_INDEX_SAME_QUOTE"}:
        return "MARK_INDEX_SAME_QUOTE"
    return "BASIS_REFERENCE_UNVERIFIED"


def _invalid_count(invalid_rows: Sequence[Mapping[str, Any]], dataset_id: str) -> int:
    return sum(1 for item in invalid_rows if item.get("dataset") == dataset_id)


def _min_timestamp(rows: Sequence[Mapping[str, Any]]) -> str | None:
    timestamps = [str(row.get("timestamp")) for row in rows if row.get("timestamp")]
    return min(timestamps) if timestamps else None


def _max_timestamp(rows: Sequence[Mapping[str, Any]]) -> str | None:
    timestamps = [str(row.get("timestamp")) for row in rows if row.get("timestamp")]
    return max(timestamps) if timestamps else None


def _time_coverage_seconds(rows: Sequence[Mapping[str, Any]]) -> float:
    start = _parse_timestamp(_min_timestamp(rows))
    end = _parse_timestamp(_max_timestamp(rows))
    if start is None or end is None:
        return 0.0
    return max(0.0, (end - start).total_seconds())


def _parse_timestamp(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)) or (isinstance(value, str) and value.strip().isdigit()):
            numeric = float(value)
            if numeric > 10_000_000_000:
                numeric /= 1000.0
            return datetime.fromtimestamp(numeric, tz=timezone.utc).replace(microsecond=0)
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    except (ValueError, OSError, OverflowError):
        return None


def _safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _stable_number(value: Any) -> str:
    number = _safe_float(value)
    if number is None:
        return ""
    return format(number, ".12g")


def _base_quote_from_pair(pair: str, symbol: str) -> tuple[str, str]:
    if ":" in pair:
        left, right = pair.split(":", 1)
        return left.upper(), right.upper()
    raw = symbol.removeprefix("PF_")
    if raw.endswith("USD"):
        return raw[:-3], "USD"
    return raw, "UNKNOWN"


def _normalize_base_asset(value: str) -> str:
    raw = str(value or "").upper().strip()
    return BASE_ALIASES.get(raw, raw)


def _sleep(seconds: float) -> None:
    if seconds > 0.0:
        time.sleep(seconds)


def _collection_time(config: KrakenFuturesCollectorConfig) -> datetime:
    value = config.observed_at or datetime.now(timezone.utc)
    return value.astimezone(timezone.utc).replace(microsecond=0)
