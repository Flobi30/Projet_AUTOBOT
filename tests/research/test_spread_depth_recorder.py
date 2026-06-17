import os

import pytest

from autobot.v2.research.spread_depth_recorder import (
    SpreadDepthRecorderConfig,
    record_spread_depth,
)


pytestmark = pytest.mark.unit


def _asset_pairs_fixture():
    return {
        "TRXEUR": {"altname": "TRXEUR", "wsname": "TRX/EUR"},
        "XXRPZEUR": {"altname": "XRPEUR", "wsname": "XRP/EUR"},
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
