from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

import pytest

from autobot.v2.cli import _build_parser
from autobot.v2.research.kraken_post_trade_backfill import (
    KRAKEN_POST_TRADE_ENDPOINT,
    KrakenEurSpotMarket,
    KrakenPostTradeBackfillConfig,
    PostTradeBackfillError,
    PostTradeCursorError,
    PostTradeRequest,
    collect_kraken_spot_post_trade_backfill,
    persist_kraken_spot_post_trade_backfill,
)


pytestmark = pytest.mark.unit
UTC = timezone.utc
MARKET = KrakenEurSpotMarket("BTCZEUR", "BTC/EUR", "BTC", "XBT")


class _FakeClient:
    def __init__(self, pages: list[Mapping[str, Any]]) -> None:
        self.pages = list(pages)
        self.requests: list[PostTradeRequest] = []

    def fetch(self, request: PostTradeRequest) -> Mapping[str, Any]:
        self.requests.append(request)
        if not self.pages:
            raise AssertionError("unexpected page")
        return self.pages.pop(0)


def test_actual_posttrade_shape_paginates_and_preserves_eur_point_in_time():
    client = _FakeClient(
        [
            _page([_trade("a", 0, 5, "100", "1"), _trade("b", 0, 20, "101", "2")], _utc(0, 20)),
            _page([_trade("b", 0, 20, "101", "2"), _trade("c", 1, 5, "102", "3")], _utc(1, 5)),
            _page([_trade("d", 1, 15, "103", "1")], _utc(1, 15)),
        ]
    )

    result = collect_kraken_spot_post_trade_backfill(
        _config(_utc(0), _utc(2), count=2), client=client, retrieved_at=_utc(3)
    )

    assert [item.trade_id for item in result.trades] == ["a", "b", "c", "d"]
    assert result.duplicate_count == 1
    assert result.coverage.coverage_ratio == Decimal("1")
    assert len(result.hourly_bars) == 2
    assert result.hourly_bars[0].open == Decimal("100")
    assert result.hourly_bars[0].close == Decimal("101")
    assert result.hourly_bars[0].volume == Decimal("3")
    assert result.hourly_bars[0].available_time == _utc(1)
    assert result.hourly_bars[0].ingestion_time == _utc(3)
    assert result.hourly_bars[0].to_dict()["temporal_status"] == "HISTORICAL_BACKFILL_AVAILABLE_AT_INGESTION"
    assert client.requests[0].query_params() == {
        "symbol": "BTC/EUR", "from_ts": "2026-01-01T00:00:00Z", "to_ts": "2026-01-01T02:00:00Z", "count": "2"
    }
    assert client.requests[1].from_ts == _utc(0, 20)
    assert result.paper_capital_allowed is False
    assert result.live_allowed is False
    assert result.promotable is False


def test_incomplete_or_empty_hours_remain_explicit_gaps():
    result = collect_kraken_spot_post_trade_backfill(
        _config(_utc(0), _utc(3), count=3),
        client=_FakeClient([_page([_trade("a", 0, 5, "100", "1"), _trade("b", 2, 5, "102", "1")], _utc(2, 5))]),
        retrieved_at=_utc(4),
    )

    assert result.status == "COMPLETE_WITH_GAPS"
    assert result.coverage.covered_completed_hours == 2
    assert result.coverage.gap_hour_starts == (_utc(1),)
    assert result.blockers == ("GAPS_DETECTED",)


def test_page_limit_or_nonadvancing_cursor_is_rejected():
    with pytest.raises(PostTradeCursorError, match="did not advance"):
        collect_kraken_spot_post_trade_backfill(
            _config(_utc(0), _utc(2), count=1),
            client=_FakeClient([
                _page([_trade("a", 0, 5, "100", "1")], _utc(0, 5)),
                _page([_trade("b", 0, 6, "101", "1")], _utc(0, 5)),
            ]),
            retrieved_at=_utc(3),
        )


def test_mismatched_symbol_or_non_eur_mapping_is_rejected():
    with pytest.raises(PostTradeBackfillError, match="explicit EUR"):
        KrakenEurSpotMarket("BTCUSD", "BTC/USD", "BTC", "XBT", "USD")

    with pytest.raises(PostTradeBackfillError, match="unexpected symbol"):
        collect_kraken_spot_post_trade_backfill(
            _config(_utc(0), _utc(1), count=1),
            client=_FakeClient([_page([_trade("a", 0, 5, "100", "1", symbol="BTC/USD")], _utc(0, 5))]),
            retrieved_at=_utc(2),
        )


def test_persistence_keeps_raw_canonical_and_manifest_separate(tmp_path):
    result = collect_kraken_spot_post_trade_backfill(
        _config(_utc(0), _utc(1), count=2),
        client=_FakeClient([_page([_trade("a", 0, 5, "100", "1")], _utc(0, 5))]),
        retrieved_at=_utc(2),
    )

    canonical, manifest, report = persist_kraken_spot_post_trade_backfill(
        result,
        raw_root=tmp_path / "raw",
        canonical_root=tmp_path / "canonical",
        manifest_root=tmp_path / "manifests",
        report_root=tmp_path / "reports",
    )

    with canonical.open("r", encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert row["source_endpoint"] == KRAKEN_POST_TRADE_ENDPOINT
    assert payload["temporal_contract"]["runtime_parity_proven"] is False
    assert payload["paper_capital_allowed"] is False
    assert list((tmp_path / "raw").rglob("page_001.json"))
    assert report.exists()
    assert not list(tmp_path.rglob("*.tmp"))


def test_cli_is_research_only_and_requires_explicit_eur_mapping():
    args = _build_parser().parse_args(
        [
            "collect-kraken-spot-post-trade",
            "--autobot-symbol", "BTCZEUR",
            "--kraken-symbol", "BTC/EUR",
            "--autobot-base-asset", "BTC",
            "--kraken-base-asset", "XBT",
            "--start-at", "2026-01-01T00:00:00Z",
            "--end-at", "2026-01-01T01:00:00Z",
        ]
    )

    assert args.command == "collect-kraken-spot-post-trade"
    assert args.count == 1000
    assert args.max_pages == 20


def _config(start: datetime, end: datetime, *, count: int) -> KrakenPostTradeBackfillConfig:
    return KrakenPostTradeBackfillConfig("pytest_posttrade", MARKET, start, end, count=count, max_pages=5)


def _page(rows: list[dict[str, Any]], last_ts: datetime) -> dict[str, Any]:
    return {"error": [], "result": {"last_ts": last_ts.isoformat(), "count": len(rows), "trades": rows}}


def _trade(
    trade_id: str, hour: int, minute: int, price: str, quantity: str, *, symbol: str = "BTC/EUR"
) -> dict[str, str]:
    trade_ts = _utc(hour, minute)
    return {
        "trade_id": trade_id,
        "price": price,
        "quantity": quantity,
        "symbol": symbol,
        "base_asset": "XBT",
        "quote_asset": "EUR",
        "trade_ts": trade_ts.isoformat(),
        "publication_ts": (trade_ts + timedelta(seconds=1)).isoformat(),
    }


def _utc(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 1, 1, hour, minute, tzinfo=UTC)
