"""Bounded, public-only Kraken Spot PostTrade backfill for research data.

This module intentionally has no connection to AUTOBOT's order, paper-capital,
promotion, or live paths.  It creates a reproducible *research* input from
Kraken's public ``/0/public/PostTrade`` contract, whose response includes both
matching-engine and publication timestamps.  Historical retrieval never
pretends to prove real-time parity: every persisted bar remains marked
``HISTORICAL_BACKFILL_AVAILABLE_AT_INGESTION``.
"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence
from urllib.parse import urlencode
from urllib.request import Request, urlopen


KRAKEN_POST_TRADE_ENDPOINT = "/0/public/PostTrade"
KRAKEN_POST_TRADE_URL = f"https://api.kraken.com{KRAKEN_POST_TRADE_ENDPOINT}"
MAX_POST_TRADE_COUNT = 1_000
MAX_POST_TRADE_PAGES = 100
MAX_POST_TRADE_WINDOW = timedelta(hours=24)
ONE_HOUR = timedelta(hours=1)
HISTORICAL_BACKFILL_STATUS = "HISTORICAL_BACKFILL_AVAILABLE_AT_INGESTION"


class PostTradeBackfillError(ValueError):
    """Raised when public PostTrade evidence cannot safely be canonicalized."""


class PostTradeCursorError(PostTradeBackfillError):
    """Raised when Kraken's documented pagination cursor cannot advance."""


@dataclass(frozen=True)
class KrakenEurSpotMarket:
    """Explicit EUR-quoted market identity; no currency conversion is allowed."""

    autobot_symbol: str
    kraken_symbol: str
    autobot_base_asset: str
    kraken_base_asset: str
    quote_asset: str = "EUR"

    def __post_init__(self) -> None:
        symbol = str(self.autobot_symbol).strip().upper()
        kraken_symbol = str(self.kraken_symbol).strip().upper()
        autobot_base_asset = str(self.autobot_base_asset).strip().upper()
        kraken_base_asset = str(self.kraken_base_asset).strip().upper()
        quote_asset = str(self.quote_asset).strip().upper()
        if not symbol.endswith("EUR") or not kraken_symbol or not autobot_base_asset or not kraken_base_asset:
            raise PostTradeBackfillError("an explicit EUR AUTOBOT/Kraken market mapping is required")
        if quote_asset != "EUR":
            raise PostTradeBackfillError("PostTrade research only supports EUR-quoted spot markets")
        if "/EUR" not in kraken_symbol:
            raise PostTradeBackfillError("kraken_symbol must be an explicit EUR display symbol such as BTC/EUR")
        object.__setattr__(self, "autobot_symbol", symbol)
        object.__setattr__(self, "kraken_symbol", kraken_symbol)
        object.__setattr__(self, "autobot_base_asset", autobot_base_asset)
        object.__setattr__(self, "kraken_base_asset", kraken_base_asset)
        object.__setattr__(self, "quote_asset", quote_asset)

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class KrakenPostTradeBackfillConfig:
    """One explicitly bounded public PostTrade retrieval window."""

    run_id: str
    market: KrakenEurSpotMarket
    start_at: datetime
    end_at: datetime
    count: int = MAX_POST_TRADE_COUNT
    max_pages: int = 20
    timeout_seconds: float = 20.0

    def __post_init__(self) -> None:
        if not str(self.run_id).strip():
            raise PostTradeBackfillError("run_id must not be empty")
        start_at = _utc(self.start_at, "start_at")
        end_at = _utc(self.end_at, "end_at")
        if end_at <= start_at:
            raise PostTradeBackfillError("end_at must be later than start_at")
        if end_at - start_at > MAX_POST_TRADE_WINDOW:
            raise PostTradeBackfillError("PostTrade retrieval window must not exceed 24 hours")
        if not isinstance(self.count, int) or isinstance(self.count, bool) or not 1 <= self.count <= MAX_POST_TRADE_COUNT:
            raise PostTradeBackfillError("count must be an integer between 1 and 1000")
        if not isinstance(self.max_pages, int) or isinstance(self.max_pages, bool) or not 1 <= self.max_pages <= MAX_POST_TRADE_PAGES:
            raise PostTradeBackfillError("max_pages must be an integer between 1 and 100")
        if self.timeout_seconds <= 0.0:
            raise PostTradeBackfillError("timeout_seconds must be positive")
        object.__setattr__(self, "start_at", start_at)
        object.__setattr__(self, "end_at", end_at)


@dataclass(frozen=True)
class PostTradeRequest:
    market: KrakenEurSpotMarket
    from_ts: datetime
    to_ts: datetime
    count: int
    page_number: int

    def query_params(self) -> dict[str, str]:
        return {
            "symbol": self.market.kraken_symbol,
            "from_ts": self.from_ts.isoformat().replace("+00:00", "Z"),
            "to_ts": self.to_ts.isoformat().replace("+00:00", "Z"),
            "count": str(self.count),
        }


class KrakenPostTradeClient(Protocol):
    def fetch(self, request: PostTradeRequest) -> Mapping[str, Any]:
        """Fetch one public PostTrade page; implementations must never use credentials."""


class UrllibKrakenPostTradeClient:
    """Minimal stdlib-only public Kraken client for bounded research collection."""

    def __init__(self, *, timeout_seconds: float = 20.0) -> None:
        if timeout_seconds <= 0.0:
            raise PostTradeBackfillError("timeout_seconds must be positive")
        self._timeout_seconds = timeout_seconds

    def fetch(self, request: PostTradeRequest) -> Mapping[str, Any]:
        query = urlencode(request.query_params())
        http_request = Request(
            f"{KRAKEN_POST_TRADE_URL}?{query}",
            headers={"Accept": "application/json", "User-Agent": "AUTOBOT-research-posttrade/1"},
            method="GET",
        )
        with urlopen(http_request, timeout=self._timeout_seconds) as response:  # nosec B310: fixed public HTTPS host
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, Mapping):
            raise PostTradeBackfillError("Kraken PostTrade response must be a JSON object")
        return payload


@dataclass(frozen=True)
class NormalizedPostTrade:
    trade_id: str
    trade_ts: datetime
    publication_ts: datetime
    price: Decimal
    quantity: Decimal
    source_response_sha256: str


@dataclass(frozen=True)
class CompletedHourlyBar:
    market: KrakenEurSpotMarket
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    trade_count: int
    event_time: datetime
    available_time: datetime
    ingestion_time: datetime
    max_publication_time: datetime

    def to_dict(self) -> dict[str, str | int]:
        return {
            "schema_version": "1",
            "market": self.market.autobot_symbol,
            "kraken_symbol": self.market.kraken_symbol,
            "base_asset": self.market.autobot_base_asset,
            "kraken_base_asset": self.market.kraken_base_asset,
            "quote_asset": self.market.quote_asset,
            "timestamp": self.open_time.isoformat(),
            "event_time": self.event_time.isoformat(),
            "available_time": self.available_time.isoformat(),
            "ingestion_time": self.ingestion_time.isoformat(),
            "temporal_status": HISTORICAL_BACKFILL_STATUS,
            "bar_close_time": self.close_time.isoformat(),
            "open": str(self.open),
            "high": str(self.high),
            "low": str(self.low),
            "close": str(self.close),
            "volume": str(self.volume),
            "trade_count": self.trade_count,
            "max_publication_time": self.max_publication_time.isoformat(),
            "source": "kraken_spot_post_trade",
            "source_endpoint": KRAKEN_POST_TRADE_ENDPOINT,
        }


@dataclass(frozen=True)
class PostTradeCoverage:
    expected_completed_hours: int
    covered_completed_hours: int
    gap_hour_starts: tuple[datetime, ...]

    @property
    def coverage_ratio(self) -> Decimal:
        return Decimal("1") if not self.expected_completed_hours else Decimal(self.covered_completed_hours) / Decimal(self.expected_completed_hours)

    def to_dict(self) -> dict[str, Any]:
        return {
            "expected_completed_hours": self.expected_completed_hours,
            "covered_completed_hours": self.covered_completed_hours,
            "coverage_ratio": str(self.coverage_ratio),
            "gap_hour_starts": [item.isoformat() for item in self.gap_hour_starts],
        }


@dataclass(frozen=True)
class KrakenPostTradeBackfillResult:
    config: KrakenPostTradeBackfillConfig
    retrieved_at: datetime
    raw_pages: tuple[Mapping[str, Any], ...]
    raw_response_sha256: tuple[str, ...]
    trades: tuple[NormalizedPostTrade, ...]
    duplicate_count: int
    out_of_interval_count: int
    hourly_bars: tuple[CompletedHourlyBar, ...]
    coverage: PostTradeCoverage
    status: str
    blockers: tuple[str, ...]
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False
    promotable: bool = False

    def manifest_payload(self, *, canonical_path: Path, raw_dir: Path) -> dict[str, Any]:
        rows = [bar.to_dict() for bar in self.hourly_bars]
        fingerprint = _fingerprint({"config": _config_payload(self.config), "rows": rows, "coverage": self.coverage.to_dict()})
        return {
            "schema_version": 1,
            "dataset_id": "kraken_spot_post_trade_ohlcv",
            "run_id": self.config.run_id,
            "snapshot_id": f"spot_post_trade_{fingerprint[:16]}",
            "fingerprint": fingerprint,
            "market": self.config.market.to_dict(),
            "requested_start": self.config.start_at.isoformat(),
            "requested_end": self.config.end_at.isoformat(),
            "retrieved_at": self.retrieved_at.isoformat(),
            "raw_page_count": len(self.raw_pages),
            "raw_response_sha256": list(self.raw_response_sha256),
            "trade_count": len(self.trades),
            "hourly_bar_count": len(rows),
            "duplicate_count": self.duplicate_count,
            "out_of_interval_count": self.out_of_interval_count,
            "coverage": self.coverage.to_dict(),
            "status": self.status,
            "blockers": list(self.blockers),
            "temporal_contract": {
                "event_time": "UTC hour open",
                "available_time": "max(hour close, latest trade publication time)",
                "ingestion_time": "UTC retrieval time",
                "temporal_status": HISTORICAL_BACKFILL_STATUS,
                "runtime_parity_proven": False,
            },
            "canonical_path": str(canonical_path),
            "raw_dir": str(raw_dir),
            "research_only": True,
            "paper_capital_allowed": False,
            "live_allowed": False,
            "promotable": False,
        }


def collect_kraken_spot_post_trade_backfill(
    config: KrakenPostTradeBackfillConfig,
    *,
    client: KrakenPostTradeClient | None = None,
    retrieved_at: datetime | None = None,
) -> KrakenPostTradeBackfillResult:
    """Collect one bounded public EUR spot window without any order-capable API."""

    collected_at = _utc(retrieved_at or datetime.now(timezone.utc), "retrieved_at")
    fetch_client = client or UrllibKrakenPostTradeClient(timeout_seconds=config.timeout_seconds)
    cursor = config.start_at
    previous_cursor: datetime | None = None
    pages: list[Mapping[str, Any]] = []
    hashes: list[str] = []
    trades_by_id: dict[str, NormalizedPostTrade] = {}
    duplicates = 0
    out_of_interval = 0

    for page_number in range(1, config.max_pages + 1):
        request = PostTradeRequest(config.market, cursor, config.end_at, config.count, page_number)
        payload = fetch_client.fetch(request)
        page_trades, last_ts, raw_hash = _normalize_page(payload, request)
        pages.append(payload)
        hashes.append(raw_hash)
        if previous_cursor is not None and last_ts <= previous_cursor:
            if not page_trades and last_ts == previous_cursor:
                break
            raise PostTradeCursorError("Kraken PostTrade last_ts did not advance strictly")
        if last_ts < cursor:
            raise PostTradeCursorError("Kraken PostTrade last_ts precedes the requested cursor")

        new_count = 0
        for trade in page_trades:
            if not config.start_at <= trade.trade_ts < config.end_at:
                out_of_interval += 1
                continue
            existing = trades_by_id.get(trade.trade_id)
            if existing is None:
                trades_by_id[trade.trade_id] = trade
                new_count += 1
            elif _economic_trade_key(existing) != _economic_trade_key(trade):
                raise PostTradeBackfillError(f"conflicting duplicate Kraken trade id: {trade.trade_id}")
            else:
                duplicates += 1

        # Fewer than the requested count proves this bounded result set is exhausted.
        if len(page_trades) < config.count or not page_trades or last_ts >= config.end_at:
            break
        if new_count == 0:
            raise PostTradeCursorError("Kraken PostTrade page contains no new economic trades")
        previous_cursor = last_ts
        cursor = last_ts
    else:
        raise PostTradeCursorError("Kraken PostTrade page budget exhausted before the bounded window completed")

    ordered_trades = tuple(sorted(trades_by_id.values(), key=lambda item: (item.trade_ts, item.publication_ts, item.trade_id)))
    bars = _aggregate_completed_bars(ordered_trades, config.market, collected_at, config.start_at, config.end_at)
    coverage = _coverage(config.start_at, config.end_at, collected_at, bars)
    blockers = ("GAPS_DETECTED",) if coverage.gap_hour_starts else ()
    return KrakenPostTradeBackfillResult(
        config=config,
        retrieved_at=collected_at,
        raw_pages=tuple(pages),
        raw_response_sha256=tuple(hashes),
        trades=ordered_trades,
        duplicate_count=duplicates,
        out_of_interval_count=out_of_interval,
        hourly_bars=bars,
        coverage=coverage,
        status="COMPLETE_WITH_GAPS" if blockers else "COMPLETE",
        blockers=blockers,
    )


def persist_kraken_spot_post_trade_backfill(
    result: KrakenPostTradeBackfillResult,
    *,
    raw_root: Path,
    canonical_root: Path,
    manifest_root: Path,
    report_root: Path,
) -> tuple[Path, Path, Path]:
    """Persist raw pages, canonical rows and an auditable compact report atomically."""

    raw_dir = raw_root / result.config.run_id / result.config.market.autobot_symbol
    raw_dir.mkdir(parents=True, exist_ok=True)
    for index, payload in enumerate(result.raw_pages, start=1):
        _atomic_json(raw_dir / f"page_{index:03d}.json", payload)

    canonical_path = canonical_root / f"{result.config.run_id}_{result.config.market.autobot_symbol}_1h.csv"
    canonical_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_csv(canonical_path, [bar.to_dict() for bar in result.hourly_bars])
    manifest_path = manifest_root / f"{result.config.run_id}_kraken_spot_post_trade.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_json(manifest_path, result.manifest_payload(canonical_path=canonical_path, raw_dir=raw_dir))
    report_path = report_root / f"{result.config.run_id}_kraken_spot_post_trade.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        "\n".join(
            (
                f"# Kraken Spot PostTrade Research Backfill — {result.config.run_id}",
                "",
                f"- Market: `{result.config.market.autobot_symbol}` / `{result.config.market.kraken_symbol}`",
                f"- Window: `{result.config.start_at.isoformat()}` → `{result.config.end_at.isoformat()}`",
                f"- Status: `{result.status}`",
                f"- Trades: `{len(result.trades)}`; completed 1h bars: `{len(result.hourly_bars)}`",
                f"- Coverage: `{result.coverage.covered_completed_hours}/{result.coverage.expected_completed_hours}`",
                f"- Blockers: `{', '.join(result.blockers) if result.blockers else 'none'}`",
                "- Research-only; no paper capital, live, promotion or order path.",
            )
        ) + "\n",
        encoding="utf-8",
    )
    return canonical_path, manifest_path, report_path


def _normalize_page(payload: Mapping[str, Any], request: PostTradeRequest) -> tuple[tuple[NormalizedPostTrade, ...], datetime, str]:
    if not isinstance(payload, Mapping) or payload.get("error"):
        raise PostTradeBackfillError(f"Kraken public PostTrade error: {payload.get('error') if isinstance(payload, Mapping) else 'invalid response'}")
    result = payload.get("result")
    if not isinstance(result, Mapping):
        raise PostTradeBackfillError("Kraken public PostTrade response lacks result")
    raw_trades = result.get("trades")
    if not isinstance(raw_trades, Sequence) or isinstance(raw_trades, (str, bytes, bytearray)):
        raise PostTradeBackfillError("Kraken public PostTrade response lacks trades")
    last_ts = _parse_timestamp(result.get("last_ts"), "last_ts")
    raw_hash = _fingerprint(payload)
    normalized: list[NormalizedPostTrade] = []
    for index, row in enumerate(raw_trades):
        if not isinstance(row, Mapping):
            raise PostTradeBackfillError(f"PostTrade trade {index} is not an object")
        normalized.append(_normalize_trade(row, request.market, raw_hash, index))
    declared_count = result.get("count")
    if declared_count is not None:
        try:
            parsed_count = int(declared_count)
        except (TypeError, ValueError) as exc:
            raise PostTradeBackfillError("PostTrade response count is invalid") from exc
        if parsed_count != len(normalized):
            raise PostTradeBackfillError("PostTrade response count does not match trades length")
    return tuple(sorted(normalized, key=lambda item: (item.trade_ts, item.publication_ts, item.trade_id))), last_ts, raw_hash


def _normalize_trade(row: Mapping[str, Any], market: KrakenEurSpotMarket, raw_hash: str, index: int) -> NormalizedPostTrade:
    symbol = str(row.get("symbol") or "").strip().upper()
    if symbol != market.kraken_symbol:
        raise PostTradeBackfillError(f"PostTrade trade {index} has unexpected symbol {symbol!r}")
    if (
        str(row.get("base_asset") or "").strip().upper() != market.kraken_base_asset
        or str(row.get("quote_asset") or "").strip().upper() != "EUR"
    ):
        raise PostTradeBackfillError(f"PostTrade trade {index} violates explicit EUR market mapping")
    trade_ts = _parse_timestamp(row.get("trade_ts"), "trade_ts")
    publication_ts = _parse_timestamp(row.get("publication_ts"), "publication_ts")
    if publication_ts < trade_ts:
        raise PostTradeBackfillError(f"PostTrade trade {index} was published before it matched")
    trade_id = str(row.get("trade_id") or "").strip()
    if not trade_id:
        raise PostTradeBackfillError(f"PostTrade trade {index} lacks trade_id")
    return NormalizedPostTrade(
        trade_id=trade_id,
        trade_ts=trade_ts,
        publication_ts=publication_ts,
        price=_positive_decimal(row.get("price"), "price"),
        quantity=_positive_decimal(row.get("quantity"), "quantity"),
        source_response_sha256=raw_hash,
    )


def _aggregate_completed_bars(
    trades: Sequence[NormalizedPostTrade],
    market: KrakenEurSpotMarket,
    ingestion_time: datetime,
    start_at: datetime,
    end_at: datetime,
) -> tuple[CompletedHourlyBar, ...]:
    grouped: dict[datetime, list[NormalizedPostTrade]] = {}
    for trade in trades:
        open_time = trade.trade_ts.replace(minute=0, second=0, microsecond=0)
        close_time = open_time + ONE_HOUR
        if open_time < start_at or close_time > end_at or close_time > ingestion_time:
            continue
        grouped.setdefault(open_time, []).append(trade)
    bars: list[CompletedHourlyBar] = []
    for open_time, bucket in sorted(grouped.items()):
        ordered = sorted(bucket, key=lambda item: (item.trade_ts, item.publication_ts, item.trade_id))
        max_publication = max(item.publication_ts for item in ordered)
        close_time = open_time + ONE_HOUR
        bars.append(
            CompletedHourlyBar(
                market=market,
                open_time=open_time,
                close_time=close_time,
                open=ordered[0].price,
                high=max(item.price for item in ordered),
                low=min(item.price for item in ordered),
                close=ordered[-1].price,
                volume=sum((item.quantity for item in ordered), Decimal("0")),
                trade_count=len(ordered),
                event_time=open_time,
                available_time=max(close_time, max_publication),
                ingestion_time=ingestion_time,
                max_publication_time=max_publication,
            )
        )
    return tuple(bars)


def _coverage(start_at: datetime, end_at: datetime, ingestion_time: datetime, bars: Sequence[CompletedHourlyBar]) -> PostTradeCoverage:
    cutoff = min(end_at, ingestion_time)
    first = start_at.replace(minute=0, second=0, microsecond=0)
    if first < start_at:
        first += ONE_HOUR
    expected: list[datetime] = []
    current = first
    while current + ONE_HOUR <= cutoff:
        expected.append(current)
        current += ONE_HOUR
    covered = {bar.open_time for bar in bars}
    gaps = tuple(item for item in expected if item not in covered)
    return PostTradeCoverage(len(expected), len(expected) - len(gaps), gaps)


def _parse_timestamp(value: Any, field_name: str) -> datetime:
    if isinstance(value, datetime):
        return _utc(value, field_name)
    if value is None or isinstance(value, bool):
        raise PostTradeBackfillError(f"{field_name} is required")
    text = str(value).strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    # Kraken may return nanosecond precision while datetime stores microseconds.
    if "." in text:
        prefix, suffix = text.split(".", 1)
        zone_index = max(suffix.find("+"), suffix.find("-"))
        fractional, zone = (suffix, "") if zone_index < 0 else (suffix[:zone_index], suffix[zone_index:])
        text = f"{prefix}.{fractional[:6]}{zone}"
    try:
        return _utc(datetime.fromisoformat(text), field_name)
    except ValueError as exc:
        raise PostTradeBackfillError(f"invalid {field_name}") from exc


def _positive_decimal(value: Any, field_name: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise PostTradeBackfillError(f"invalid {field_name}") from exc
    if not parsed.is_finite() or parsed <= 0:
        raise PostTradeBackfillError(f"{field_name} must be a positive finite decimal")
    return parsed


def _economic_trade_key(trade: NormalizedPostTrade) -> tuple[Any, ...]:
    """Compare replayed page boundaries without treating raw-page lineage as trade data."""

    return (trade.trade_id, trade.trade_ts, trade.publication_ts, trade.price, trade.quantity)


def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise PostTradeBackfillError(f"{field_name} must be an explicit UTC datetime")
    return value.astimezone(timezone.utc)


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def _config_payload(config: KrakenPostTradeBackfillConfig) -> dict[str, Any]:
    return {
        "run_id": config.run_id,
        "market": config.market.to_dict(),
        "start_at": config.start_at.isoformat(),
        "end_at": config.end_at.isoformat(),
        "count": config.count,
        "max_pages": config.max_pages,
    }


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    temporary.replace(path)


def _atomic_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = [
        "schema_version", "market", "kraken_symbol", "base_asset", "kraken_base_asset", "quote_asset", "timestamp", "event_time",
        "available_time", "ingestion_time", "temporal_status", "bar_close_time", "open", "high", "low", "close",
        "volume", "trade_count", "max_publication_time", "source", "source_endpoint",
    ]
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)
