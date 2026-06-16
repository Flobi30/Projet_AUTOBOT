from datetime import datetime, timezone

import pytest

from autobot.v2.research.historical_data_collector import (
    HistoricalDataCollectorConfig,
    KrakenOHLCPage,
    collect_historical_ohlcv,
    write_historical_data_collection_reports,
)


pytestmark = pytest.mark.unit


def _asset_pairs_fixture():
    return {
        "TRXEUR": {"altname": "TRXEUR", "wsname": "TRX/EUR"},
    }


def _fake_fetcher(pair, interval_minutes, since):
    assert pair == "TRXEUR"
    assert interval_minutes == 5
    assert since is None
    return KrakenOHLCPage(
        pair=pair,
        rows=(
            (datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc).timestamp(), "0.25", "0.26", "0.24", "0.255", "0.252", "1000", 12),
            (datetime(2026, 6, 1, 0, 5, tzinfo=timezone.utc).timestamp(), "0.255", "0.27", "0.25", "0.268", "0.261", "1200", 15),
        ),
        last=123,
    )


def test_historical_collector_writes_csv_and_quality_report(tmp_path):
    config = HistoricalDataCollectorConfig(
        run_id="pytest_history",
        symbols=("TRXEUR",),
        timeframes=("5m",),
        output_dir=tmp_path / "data",
        export_csv=True,
        export_parquet=False,
    )

    result = collect_historical_ohlcv(config, fetcher=_fake_fetcher, asset_pairs_fetcher=_asset_pairs_fixture)
    written = write_historical_data_collection_reports(result, tmp_path / "reports")

    assert sum(item.row_count for item in result.files) == 2
    assert result.files[0].row_count == 2
    assert result.files[0].csv_path
    assert result.readiness.files[0].volume_status == "present"
    assert "bid_ask_absent" in result.files[0].warnings
    assert "order_book_depth_absent" in result.files[0].warnings
    assert "No private Kraken endpoint is called." in written.safety_notes
    assert (tmp_path / "reports" / "pytest_history.md").exists()
    assert (tmp_path / "reports" / "pytest_history_manifest.json").exists()


def test_historical_collector_rejects_unsupported_timeframe(tmp_path):
    with pytest.raises(ValueError, match="not supported by Kraken OHLC"):
        HistoricalDataCollectorConfig(
            run_id="pytest_bad_timeframe",
            symbols=("TRXEUR",),
            timeframes=("2m",),
            output_dir=tmp_path / "data",
        )
