import os
from pathlib import Path

import pytest

from autobot.v2.research.spread_depth_recorder import (
    SpreadDepthRecorderConfig,
    record_spread_depth,
)


pytestmark = pytest.mark.unit


def _asset_pairs_fixture():
    return {
        "TRXEUR": {"altname": "TRXEUR", "wsname": "TRX/EUR", "base": "TRX", "quote": "ZEUR"},
        "XXRPZEUR": {"altname": "XRPEUR", "wsname": "XRP/EUR", "base": "XXRP", "quote": "ZEUR"},
    }


def test_spread_depth_recorder_uses_public_depth_payload_without_private_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "must_not_be_used")
    monkeypatch.setenv("KRAKEN_API_SECRET", "must_not_be_used")
    calls = []

    def fetcher(pair, depth_count):
        calls.append((pair, depth_count))
        return {
            "error": [],
            "result": {
                "TRXEUR": {
                    "bids": [["100.0", "2.0", "1780272000"]],
                    "asks": [["101.0", "3.0", "1780272001"]],
                }
            },
        }

    result = record_spread_depth(
        SpreadDepthRecorderConfig(
            run_id="pytest_spread_depth",
            symbols=("TRXEUR",),
            output_dir=tmp_path,
            depth_count=5,
            samples=1,
        ),
        fetcher=fetcher,
        asset_pairs_fetcher=_asset_pairs_fixture,
    )

    assert calls == [("TRXEUR", 5)]
    snapshot = result.snapshots[0]
    assert snapshot.best_bid == pytest.approx(100.0)
    assert snapshot.best_ask == pytest.approx(101.0)
    assert snapshot.spread_bps == pytest.approx((1.0 / 100.5) * 10_000.0)
    assert snapshot.bid_depth_eur == pytest.approx(200.0)
    assert snapshot.ask_depth_eur == pytest.approx(303.0)
    assert snapshot.base_asset == "TRX"
    assert snapshot.quote_asset == "EUR"
    assert snapshot.market_mapping_status == "EXPLICIT"
    assert snapshot.event_time == snapshot.timestamp_exchange
    assert snapshot.available_time == snapshot.ingestion_time == snapshot.timestamp_local
    assert snapshot.temporal_status == "FORWARD_PUBLIC_REST_INGESTED"
    assert snapshot.runtime_parity_proven is False
    assert snapshot.source_snapshot_id.startswith("kraken_depth_")
    assert result.csv_path
    assert result.markdown_report_path
    assert "No API key is read or exposed." in result.safety_notes
    assert os.environ["KRAKEN_API_KEY"] == "must_not_be_used"


def test_spread_depth_recorder_rejects_invalid_config(tmp_path):
    with pytest.raises(ValueError, match="depth_count must be positive"):
        SpreadDepthRecorderConfig(
            run_id="pytest_bad_depth",
            symbols=("TRXEUR",),
            output_dir=tmp_path,
            depth_count=0,
        )
    with pytest.raises(ValueError, match="max_runtime_seconds must be positive"):
        SpreadDepthRecorderConfig(
            run_id="pytest_bad_deadline",
            symbols=("TRXEUR",),
            output_dir=tmp_path,
            max_runtime_seconds=0.0,
        )


def test_spread_depth_recorder_collapses_alias_duplicates_before_fetch(tmp_path):
    calls = []

    def fetcher(pair, depth_count):
        calls.append((pair, depth_count))
        return {
            "error": [],
            "result": {
                pair: {
                    "bids": [["1.0", "10.0", "1780272000"]],
                    "asks": [["1.1", "10.0", "1780272001"]],
                }
            },
        }

    result = record_spread_depth(
        SpreadDepthRecorderConfig(
            run_id="pytest_alias_collapse_depth",
            symbols=("XRPZEUR", "XRPEUR", "XXRPZEUR"),
            output_dir=tmp_path,
            depth_count=5,
            samples=1,
        ),
        fetcher=fetcher,
        asset_pairs_fetcher=_asset_pairs_fixture,
    )

    assert calls == [("XXRPZEUR", 5)]
    assert [snapshot.symbol for snapshot in result.snapshots] == ["XRPZEUR"]


def test_spread_depth_recorder_stops_cleanly_at_configured_deadline(tmp_path):
    calls: list[tuple[str, int]] = []
    clock = {"value": 0.0}

    def fetcher(pair, depth_count):
        calls.append((pair, depth_count))
        clock["value"] = 2.0
        return {
            "error": [],
            "result": {
                pair: {
                    "bids": [["100.0", "2.0", "1780272000"]],
                    "asks": [["100.2", "3.0", "1780272001"]],
                }
            },
        }

    result = record_spread_depth(
        SpreadDepthRecorderConfig(
            run_id="pytest_timeboxed_depth",
            symbols=("TRXEUR",),
            output_dir=tmp_path,
            samples=3,
            max_runtime_seconds=1.0,
        ),
        fetcher=fetcher,
        asset_pairs_fetcher=_asset_pairs_fixture,
        monotonic_clock=lambda: clock["value"],
    )

    assert calls == [("TRXEUR", 10)]
    assert len(result.snapshots) == 1
    assert result.stop_reason == "max_runtime_seconds_elapsed"
    assert "Stop reason: `max_runtime_seconds_elapsed`" in Path(result.markdown_report_path).read_text(encoding="utf-8")


def test_spread_depth_recorder_rejects_unmapped_or_non_eur_depth_without_implicit_conversion(tmp_path):
    def fetcher(pair, depth_count):
        return {
            "error": [],
            "result": {
                pair: {
                    "bids": [["100.0", "2.0", "1780272000"]],
                    "asks": [["100.2", "2.0", "1780272001"]],
                }
            },
        }

    with pytest.raises(ValueError, match="explicit Kraken base/quote mapping"):
        record_spread_depth(
            SpreadDepthRecorderConfig(run_id="pytest_unmapped", symbols=("TRXEUR",), output_dir=tmp_path),
            fetcher=fetcher,
            asset_pairs_fetcher=lambda: {"TRXEUR": {"altname": "TRXEUR", "wsname": "TRX/EUR"}},
        )

    with pytest.raises(ValueError, match="EUR-quote only"):
        record_spread_depth(
            SpreadDepthRecorderConfig(run_id="pytest_usd", symbols=("TRXUSD",), output_dir=tmp_path),
            fetcher=fetcher,
            asset_pairs_fetcher=lambda: {
                "TRXUSD": {"altname": "TRXUSD", "wsname": "TRX/USD", "base": "TRX", "quote": "ZUSD"}
            },
        )
