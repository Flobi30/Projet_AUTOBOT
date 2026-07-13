import csv
from datetime import datetime, timezone
from pathlib import Path

import pytest

from autobot.v2.research.historical_data_collector import (
    HistoricalDataCollectorConfig,
    KrakenOHLCPage,
    collect_historical_ohlcv,
    write_historical_data_collection_reports,
)
from autobot.v2.research.canonical_feature_snapshot import (
    CanonicalFeatureSnapshotConfig,
    build_canonical_feature_snapshot,
)
from autobot.v2.research.canonical_ohlcv_store import (
    CanonicalOHLCVConfig,
    build_canonical_ohlcv_snapshot,
)
from autobot.v2.research import historical_data_collector as collector_module


pytestmark = pytest.mark.unit


def _asset_pairs_fixture():
    return {
        "TRXEUR": {"altname": "TRXEUR", "wsname": "TRX/EUR"},
        "XXRPZEUR": {"altname": "XRPEUR", "wsname": "XRP/EUR"},
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


def test_historical_collector_excludes_open_bar_and_records_point_in_time_provenance(tmp_path, monkeypatch):
    collection_time = datetime(2026, 6, 1, 0, 6, tzinfo=timezone.utc)
    monkeypatch.setattr(collector_module, "_utc_now", lambda: collection_time)
    result = collect_historical_ohlcv(
        HistoricalDataCollectorConfig(
            run_id="pytest_point_in_time",
            symbols=("TRXEUR",),
            timeframes=("5m",),
            output_dir=tmp_path / "raw",
            export_csv=True,
            export_parquet=False,
        ),
        fetcher=_fake_fetcher,
        asset_pairs_fetcher=_asset_pairs_fixture,
    )

    collected = result.files[0]
    assert collected.row_count_raw == 2
    assert collected.row_count_closed == 1
    assert collected.row_count == 1
    assert collected.incomplete_bar_count == 1
    assert collected.collection_time == collection_time.isoformat()
    assert "incomplete_current_bars_excluded" in collected.warnings

    csv_path = tmp_path / "raw" / "pytest_point_in_time_TRXEUR_5m.csv"
    with csv_path.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    assert rows[0]["timestamp"] == "2026-06-01T00:00:00+00:00"
    assert rows[0]["available_time"] == collection_time.isoformat()
    assert rows[0]["ingestion_time"] == collection_time.isoformat()
    assert rows[0]["collected_at"] == collection_time.isoformat()

    canonical = build_canonical_ohlcv_snapshot(
        CanonicalOHLCVConfig(
            run_id="pytest_point_in_time_canonical",
            raw_paths=(csv_path,),
            output_dir=tmp_path / "canonical",
            manifest_dir=tmp_path / "manifests",
            quarantine_dir=tmp_path / "quarantine",
            market_mappings={"TRXEUR": {"base_asset": "TRX", "quote_asset": "EUR"}},
        )
    )
    with Path(canonical.files[0].csv_path).open("r", newline="", encoding="utf-8") as handle:
        canonical_rows = list(csv.DictReader(handle))
    assert canonical_rows[0]["available_time"] == collection_time.isoformat()
    assert canonical_rows[0]["ingestion_time"] == collection_time.isoformat()
    feature_snapshot = build_canonical_feature_snapshot(
        CanonicalFeatureSnapshotConfig(
            run_id="pytest_point_in_time_features",
            canonical_manifest_path=Path(str(canonical.manifest_path)),
            output_dir=tmp_path / "features",
            manifest_dir=tmp_path / "feature_manifests",
        )
    )
    assert feature_snapshot.ingestion_time_unknown_count == 0
    assert "INGESTION_TIME_UNKNOWN_RUNTIME_PARITY_NOT_PROVEN" not in feature_snapshot.blockers


def test_historical_collector_keeps_bar_that_closes_at_collection_time(tmp_path, monkeypatch):
    collection_time = datetime(2026, 6, 1, 0, 5, tzinfo=timezone.utc)
    monkeypatch.setattr(collector_module, "_utc_now", lambda: collection_time)
    result = collect_historical_ohlcv(
        HistoricalDataCollectorConfig(
            run_id="pytest_closed_boundary",
            symbols=("TRXEUR",),
            timeframes=("5m",),
            output_dir=tmp_path,
            export_csv=False,
            export_parquet=False,
        ),
        fetcher=_fake_fetcher,
        asset_pairs_fetcher=_asset_pairs_fixture,
    )

    collected = result.files[0]
    assert collected.row_count_raw == collected.row_count_closed + collected.incomplete_bar_count
    assert collected.row_count_raw == 2
    assert collected.row_count_closed == 1
    assert collected.row_count_deduped == 1
    assert collected.duplicate_count == 0


def test_historical_collector_rejects_unsupported_timeframe(tmp_path):
    with pytest.raises(ValueError, match="not supported by Kraken OHLC"):
        HistoricalDataCollectorConfig(
            run_id="pytest_bad_timeframe",
            symbols=("TRXEUR",),
            timeframes=("2m",),
            output_dir=tmp_path / "data",
        )


def test_historical_collector_collapses_alias_duplicates_before_fetch(tmp_path):
    calls = []

    def fetcher(pair, interval_minutes, since):
        calls.append((pair, interval_minutes, since))
        return KrakenOHLCPage(
            pair=pair,
            rows=(
                (datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc).timestamp(), "1.0", "1.1", "0.9", "1.0", "1.0", "10", 1),
                (datetime(2026, 6, 1, 0, 5, tzinfo=timezone.utc).timestamp(), "1.0", "1.2", "1.0", "1.1", "1.1", "11", 2),
            ),
            last=None,
        )

    result = collect_historical_ohlcv(
        HistoricalDataCollectorConfig(
            run_id="pytest_alias_collapse",
            symbols=("XRPZEUR", "XRPEUR", "XXRPZEUR"),
            timeframes=("5m",),
            output_dir=tmp_path / "data",
            export_csv=True,
            export_parquet=False,
        ),
        fetcher=fetcher,
        asset_pairs_fetcher=_asset_pairs_fixture,
    )

    assert calls == [("XXRPZEUR", 5, None)]
    assert len(result.files) == 1
    assert result.files[0].symbol == "XRPZEUR"
