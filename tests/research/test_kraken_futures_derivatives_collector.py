from __future__ import annotations

import json
import csv
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from typing import Any, Mapping

import pytest

from autobot.v2.cli import _build_parser
from autobot.v2.research.data_capability_scanner import build_data_capability_scan_report
from autobot.v2.research.kraken_futures_derivatives_collector import (
    HISTORICAL_FUNDING_ENDPOINT,
    INSTRUMENTS_ENDPOINT,
    TICKERS_ENDPOINT,
    KrakenFuturesCollectorConfig,
    assert_public_kraken_futures_endpoint,
    calculate_basis_bps,
    collect_kraken_futures_derivatives,
    fingerprint_derivatives_rows,
)


pytestmark = pytest.mark.unit


class _FakeKrakenFuturesClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Mapping[str, Any] | None]] = []

    def get_json(self, endpoint: str, params: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        assert_public_kraken_futures_endpoint(endpoint)
        self.calls.append((endpoint, params))
        if endpoint == TICKERS_ENDPOINT:
            return _ticker_payload()
        if endpoint == INSTRUMENTS_ENDPOINT:
            return {"result": "success", "instruments": [{"symbol": "PF_XBTUSD", "base": "BTC", "quote": "USD"}]}
        if endpoint == HISTORICAL_FUNDING_ENDPOINT:
            return _funding_payload()
        if endpoint.startswith("/api/charts/v1/"):
            return _candles_payload()
        raise AssertionError(endpoint)


def test_collect_kraken_futures_derivatives_writes_canonical_datasets(tmp_path):
    client = _FakeKrakenFuturesClient()
    result = collect_kraken_futures_derivatives(
        KrakenFuturesCollectorConfig(
            run_id="pytest_p18j",
            priority_assets=("BTC", "ETH"),
            max_symbols=2,
            max_candles=2,
            raw_dir=tmp_path / "raw" / "kraken_futures",
            canonical_dir=tmp_path / "canonical" / "derivatives",
            manifest_dir=tmp_path / "manifests",
            report_dir=tmp_path / "reports",
            observed_at=datetime(2026, 7, 10, 1, 0, tzinfo=timezone.utc),
        ),
        client=client,
    )

    assert [item.futures_symbol for item in result.mappings] == ["PF_XBTUSD", "PF_ETHUSD"]
    assert result.funding_history_ready is True
    assert result.mark_candles_ready is True
    assert result.trade_candles_ready is True
    assert result.spot_reference_candles_ready is True
    assert result.current_open_interest_ready is True
    assert result.open_interest_history_ready is False
    assert result.predicted_funding_ready is True
    assert result.basis_current_ready is True
    assert result.basis_history_ready is False
    assert result.basis_confidence_status == "MARK_INDEX_SAME_QUOTE"
    assert result.paper_capital_allowed is False
    assert result.live_allowed is False
    assert result.promotable is False
    assert Path(str(result.manifest_path)).exists()
    for dataset in result.datasets:
        assert Path(str(dataset.csv_path)).exists()
        assert dataset.duplicate_count == 0
    funding = next(item for item in result.datasets if item.dataset_id == "funding_rates")
    with Path(str(funding.csv_path)).open("r", encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["schema_version"] == "2"
    assert row["temporal_status"] == "HISTORICAL_BACKFILL_AVAILABLE_AT_INGESTION"
    assert row["available_time"] == "2026-07-10T01:00:00+00:00"


def test_derivatives_collector_rejects_unclosed_candles(tmp_path):
    client = _FakeKrakenFuturesClient()
    result = collect_kraken_futures_derivatives(
        KrakenFuturesCollectorConfig(
            run_id="pytest_unclosed",
            priority_assets=("BTC",),
            max_symbols=1,
            max_candles=2,
            raw_dir=tmp_path / "raw",
            canonical_dir=tmp_path / "canonical",
            manifest_dir=tmp_path / "manifests",
            report_dir=tmp_path / "reports",
            observed_at=datetime(2026, 7, 8, 17, 26, tzinfo=timezone.utc),
        ),
        client=client,
    )

    candles = next(item for item in result.datasets if item.dataset_id == "derivatives_candles")
    assert candles.row_count == 0
    assert any(item.get("reason") == "unclosed_candle" for item in result.errors)


def test_invalid_open_interest_does_not_discard_valid_mark_index_or_basis(tmp_path):
    class _InvalidOIClient(_FakeKrakenFuturesClient):
        def get_json(self, endpoint, params=None):
            payload = super().get_json(endpoint, params)
            if endpoint == TICKERS_ENDPOINT:
                payload["tickers"][0]["openInterest"] = "nan"
            return payload

    result = collect_kraken_futures_derivatives(
        KrakenFuturesCollectorConfig(
            run_id="pytest_invalid_oi",
            priority_assets=("BTC",),
            max_symbols=1,
            raw_dir=tmp_path / "raw",
            canonical_dir=tmp_path / "canonical",
            manifest_dir=tmp_path / "manifests",
            report_dir=tmp_path / "reports",
            observed_at=datetime(2026, 7, 10, 1, 0, tzinfo=timezone.utc),
        ),
        client=_InvalidOIClient(),
    )

    ticker = next(item for item in result.datasets if item.dataset_id == "ticker_snapshots")
    basis = next(item for item in result.datasets if item.dataset_id == "basis")
    assert ticker.row_count == 1
    assert basis.row_count == 1
    assert result.current_open_interest_ready is False
    assert any(item.get("reason") == "negative_open_interest" for item in result.errors)


def test_basis_same_quote_and_usd_eur_rejection():
    basis, status = calculate_basis_bps(mark_price=101.0, reference_price=100.0, mark_quote="USD", reference_quote="USD")
    assert basis == pytest.approx(100.0)
    assert status == "MARK_INDEX_SAME_QUOTE"

    basis, status = calculate_basis_bps(mark_price=101.0, reference_price=100.0, mark_quote="USD", reference_quote="EUR")
    assert basis is None
    assert status == "BASIS_REFERENCE_UNVERIFIED"


def test_forbidden_order_endpoints_are_rejected():
    with pytest.raises(ValueError):
        assert_public_kraken_futures_endpoint("/derivatives/api/v3/sendorder")
    with pytest.raises(ValueError):
        assert_public_kraken_futures_endpoint("/derivatives/api/v3/cancelorder")


def test_derivatives_fingerprint_is_idempotent():
    rows = {
        "funding_rates": [
            {"exchange": "kraken_futures", "futures_symbol": "PF_XBTUSD", "timestamp": "2026-01-01T00:00:00+00:00", "funding_rate_relative": "0.1"},
            {"exchange": "kraken_futures", "futures_symbol": "PF_ETHUSD", "timestamp": "2026-01-01T00:00:00+00:00", "funding_rate_relative": "0.2"},
        ]
    }
    reversed_rows = {"funding_rates": tuple(reversed(rows["funding_rates"]))}

    assert fingerprint_derivatives_rows(rows) == fingerprint_derivatives_rows(reversed_rows)


def test_scanner_marks_current_oi_distinct_from_historical_oi_and_keeps_funding_basis_waiting(tmp_path):
    client = _FakeKrakenFuturesClient()
    result = collect_kraken_futures_derivatives(
        KrakenFuturesCollectorConfig(
            run_id="pytest_p18j_scan",
            priority_assets=("BTC", "ETH"),
            max_symbols=2,
            max_candles=2,
            raw_dir=tmp_path / "raw" / "kraken_futures",
            canonical_dir=tmp_path / "canonical" / "derivatives",
            manifest_dir=tmp_path / "manifests",
            report_dir=tmp_path / "reports",
        ),
        client=client,
    )
    report = build_data_capability_scan_report(
        run_id="pytest_derivatives_scan",
        data_roots=(tmp_path,),
        memory_path=tmp_path / "missing_memory.json",
    )

    state = report.scheduler_data_state
    assert state["funding_history_ready"] is True
    assert state["current_open_interest_ready"] is True
    assert state["open_interest_history_ready"] is False
    assert state["basis_history_ready"] is False
    assert state["liquidation_data_ready"] is False
    assert report.alpha_family_status["funding_basis"]["status"] == "WAITING_FOR_MORE_DATA"
    assert "basis_history_too_short" in report.alpha_family_status["funding_basis"]["blockers"]
    assert report.alpha_family_status["liquidation_cascade"]["status"] == "DATA_MISSING"
    assert report.paper_capital_allowed is False
    assert result.live_allowed is False


def test_collect_kraken_futures_derivatives_cli_is_registered():
    parser = _build_parser()
    args = parser.parse_args(
        [
            "collect-kraken-futures-derivatives",
            "--assets",
            "BTC,ETH",
            "--max-symbols",
            "2",
            "--max-candles",
            "5",
            "--raw-retention-days",
            "7",
        ]
    )

    assert args.command == "collect-kraken-futures-derivatives"
    assert args.max_symbols == 2
    assert args.max_candles == 5
    assert args.raw_retention_days == 7


def test_raw_retention_prunes_only_old_completed_raw_runs_after_canonical_write(tmp_path):
    raw_dir = tmp_path / "raw" / "kraken_futures"
    old_run = raw_dir / "old_completed_run"
    old_run.mkdir(parents=True)
    old_payload = old_run / "tickers.json"
    old_payload.write_text("{}", encoding="utf-8")
    old_time = datetime(2026, 7, 1, tzinfo=timezone.utc).timestamp()
    os.utime(old_run, (old_time, old_time))

    result = collect_kraken_futures_derivatives(
        KrakenFuturesCollectorConfig(
            run_id="retention_current_run",
            priority_assets=("BTC",),
            max_symbols=1,
            max_candles=2,
            raw_dir=raw_dir,
            canonical_dir=tmp_path / "canonical",
            manifest_dir=tmp_path / "manifests",
            report_dir=tmp_path / "reports",
            raw_retention_days=7,
            observed_at=datetime(2026, 7, 10, 1, 0, tzinfo=timezone.utc),
        ),
        client=_FakeKrakenFuturesClient(),
    )

    assert not old_run.exists()
    assert (raw_dir / "retention_current_run").exists()
    assert result.raw_retention_deleted_run_count == 1
    assert result.raw_retention_reclaimed_bytes >= 2


def test_ticker_only_run_preserves_backfilled_funding_and_candle_capabilities(tmp_path):
    initial = KrakenFuturesCollectorConfig(
        run_id="full_backfill",
        priority_assets=("BTC", "ETH"),
        max_symbols=2,
        max_candles=2,
        raw_dir=tmp_path / "raw",
        canonical_dir=tmp_path / "canonical",
        manifest_dir=tmp_path / "manifests",
        report_dir=tmp_path / "reports",
        observed_at=datetime(2026, 7, 10, 1, 0, tzinfo=timezone.utc),
    )
    full = collect_kraken_futures_derivatives(initial, client=_FakeKrakenFuturesClient())
    ticker_only = collect_kraken_futures_derivatives(
        replace(initial, run_id="ticker_only", collect_funding=False, collect_candles=False),
        client=_FakeKrakenFuturesClient(),
    )

    assert full.funding_history_ready is True
    assert ticker_only.funding_history_ready is True
    assert ticker_only.funding_history_row_count == full.funding_history_row_count
    assert ticker_only.mark_candles_ready is True
    assert ticker_only.trade_candles_ready is True
    assert ticker_only.spot_reference_candles_ready is True
    assert Path(str(ticker_only.funding_history_path)).exists()
    assert Path(str(ticker_only.derivatives_candle_history_path)).exists()

    scan = build_data_capability_scan_report(
        run_id="ticker_only_preserves_capabilities",
        data_roots=(tmp_path,),
        memory_path=tmp_path / "missing_memory.json",
    )
    funding = next(item for item in scan.capabilities if item.capability_id == "funding_rates")
    assert funding.available is True
    assert funding.row_count == full.funding_history_row_count


def test_ticker_only_forward_collection_compacts_history_atomically_and_requires_meaningful_coverage(tmp_path):
    canonical_dir = tmp_path / "canonical" / "derivatives"
    _seed_forward_history(canonical_dir)

    client = _FakeKrakenFuturesClient()
    config = KrakenFuturesCollectorConfig(
        run_id="ticker_only_first",
        priority_assets=("BTC", "ETH"),
        max_symbols=2,
        raw_dir=tmp_path / "raw",
        canonical_dir=canonical_dir,
        manifest_dir=tmp_path / "manifests",
        report_dir=tmp_path / "reports",
        collect_funding=False,
        collect_candles=False,
        observed_at=datetime(2026, 7, 20, 1, 0, tzinfo=timezone.utc),
    )
    first = collect_kraken_futures_derivatives(config, client=client)

    called_endpoints = [endpoint for endpoint, _params in client.calls]
    assert HISTORICAL_FUNDING_ENDPOINT not in called_endpoints
    assert not any(endpoint.startswith("/api/charts/v1/") for endpoint in called_endpoints)
    assert first.open_interest_history_ready is True
    assert first.basis_history_ready is True
    assert first.open_interest_history_row_count >= 192
    assert first.basis_history_row_count >= 192
    assert Path(str(first.open_interest_history_path)).exists()
    assert Path(str(first.basis_history_path)).exists()
    assert not list(canonical_dir.rglob("*.tmp"))

    second = collect_kraken_futures_derivatives(
        replace(config, run_id="ticker_only_retry"),
        client=_FakeKrakenFuturesClient(),
    )
    assert second.open_interest_history_row_count == first.open_interest_history_row_count
    assert second.basis_history_row_count == first.basis_history_row_count


def _seed_forward_history(canonical_dir: Path) -> None:
    ticker_path = canonical_dir / "tickers" / "seed_history.csv"
    basis_path = canonical_dir / "basis" / "seed_history.csv"
    ticker_path.parent.mkdir(parents=True, exist_ok=True)
    basis_path.parent.mkdir(parents=True, exist_ok=True)
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    ticker_fields = ("exchange", "futures_symbol", "timestamp", "open_interest")
    basis_fields = ("exchange", "futures_symbol", "timestamp", "calculation_method", "confidence_status")
    with ticker_path.open("w", encoding="utf-8", newline="") as ticker_handle, basis_path.open("w", encoding="utf-8", newline="") as basis_handle:
        ticker_writer = csv.DictWriter(ticker_handle, fieldnames=ticker_fields)
        basis_writer = csv.DictWriter(basis_handle, fieldnames=basis_fields)
        ticker_writer.writeheader()
        basis_writer.writeheader()
        for index in range(96):
            timestamp = (start + timedelta(hours=index * 2)).isoformat()
            for symbol in ("PF_XBTUSD", "PF_ETHUSD"):
                ticker_writer.writerow(
                    {
                        "exchange": "kraken_futures",
                        "futures_symbol": symbol,
                        "timestamp": timestamp,
                        "open_interest": "10",
                    }
                )
                basis_writer.writerow(
                    {
                        "exchange": "kraken_futures",
                        "futures_symbol": symbol,
                        "timestamp": timestamp,
                        "calculation_method": "mark_over_index_same_quote",
                        "confidence_status": "MARK_INDEX_SAME_QUOTE",
                    }
                )


def _ticker_payload() -> dict[str, Any]:
    return {
        "result": "success",
        "serverTime": "2026-07-10T00:00:00Z",
        "tickers": [
            {
                "symbol": "PF_XBTUSD",
                "tag": "perpetual",
                "pair": "XBT:USD",
                "markPrice": 101.0,
                "indexPrice": 100.0,
                "bid": 100.9,
                "ask": 101.1,
                "openInterest": 10.0,
                "fundingRate": 0.1,
                "fundingRatePrediction": 0.2,
                "vol24h": 1000.0,
                "suspended": False,
                "postOnly": False,
            },
            {
                "symbol": "PF_ETHUSD",
                "tag": "perpetual",
                "pair": "ETH:USD",
                "markPrice": 202.0,
                "indexPrice": 200.0,
                "bid": 201.9,
                "ask": 202.1,
                "openInterest": 20.0,
                "fundingRate": -0.1,
                "fundingRatePrediction": -0.2,
                "vol24h": 2000.0,
                "suspended": False,
                "postOnly": False,
            },
        ],
    }


def _funding_payload() -> dict[str, Any]:
    return {
        "result": "success",
        "rates": [
            {"timestamp": "2026-07-09T23:00:00Z", "fundingRate": 0.5, "relativeFundingRate": 0.0001},
            {"timestamp": "2026-07-10T00:00:00Z", "fundingRate": 0.4, "relativeFundingRate": 0.0002},
        ],
    }


def _candles_payload() -> dict[str, Any]:
    return {
        "candles": [
            {"time": 1783531560000, "open": "100", "high": "101", "low": "99", "close": "100.5", "volume": "1.0"},
            {"time": 1783531620000, "open": "100.5", "high": "102", "low": "100", "close": "101.5", "volume": "2.0"},
        ]
    }
