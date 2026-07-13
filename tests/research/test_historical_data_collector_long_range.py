from datetime import datetime, timezone

import pytest

from autobot.v2.research.historical_data_collector import (
    HistoricalDataCollectorConfig,
    KrakenOHLCPage,
    collect_historical_ohlcv,
)


pytestmark = pytest.mark.unit


def _asset_pairs_fixture():
    return {
        "TRXEUR": {"altname": "TRXEUR", "wsname": "TRX/EUR"},
    }


def _ts(minute: int) -> float:
    return datetime(2026, 6, 1, 0, minute, tzinfo=timezone.utc).timestamp()


def test_historical_collector_paginates_from_start_and_stops_at_end(tmp_path):
    calls = []

    def fetcher(pair, interval_minutes, since):
        calls.append(since)
        if len(calls) == 1:
            return KrakenOHLCPage(
                pair=pair,
                rows=(
                    (_ts(0), "100", "101", "99", "100.5", "100", "10", 1),
                    (_ts(5), "100.5", "102", "100", "101.5", "101", "11", 2),
                ),
                last=int(_ts(5)),
            )
        return KrakenOHLCPage(
            pair=pair,
            rows=(
                (_ts(5), "100.5", "102", "100", "101.5", "101", "11", 2),
                (_ts(10), "101.5", "103", "101", "102.5", "102", "12", 3),
                (_ts(15), "102.5", "104", "102", "103.5", "103", "13", 4),
            ),
            last=int(_ts(15)),
        )

    result = collect_historical_ohlcv(
        HistoricalDataCollectorConfig(
            run_id="pytest_long_range",
            symbols=("TRXEUR",),
            timeframes=("5m",),
            output_dir=tmp_path,
            start_at="2026-06-01T00:00:00+00:00",
            end_at="2026-06-01T00:10:00+00:00",
            max_pages=5,
            export_csv=True,
            export_parquet=False,
        ),
        fetcher=fetcher,
        asset_pairs_fetcher=_asset_pairs_fixture,
    )

    assert calls == [int(_ts(0)), int(_ts(5))]
    file = result.files[0]
    assert file.pages_fetched == 2
    assert file.row_count_raw == 4
    assert file.row_count_closed == 4
    assert file.row_count_deduped == 3
    assert file.duplicate_count == 1
    assert file.row_count_closed == file.row_count_deduped + file.duplicate_count
    assert file.end_at == "2026-06-01T00:10:00+00:00"
    assert result.readiness.files[0].duplicate_count == 0


def test_historical_collector_fail_on_gaps_rejects_strict_run(tmp_path):
    def fetcher(pair, interval_minutes, since):
        return KrakenOHLCPage(
            pair=pair,
            rows=(
                (_ts(0), "100", "101", "99", "100.5", "100", "10", 1),
                (_ts(20), "101", "102", "100", "101.5", "101", "11", 2),
            ),
            last=int(_ts(20)),
        )

    with pytest.raises(ValueError, match="data gaps detected"):
        collect_historical_ohlcv(
            HistoricalDataCollectorConfig(
                run_id="pytest_fail_gaps",
                symbols=("TRXEUR",),
                timeframes=("5m",),
                output_dir=tmp_path,
                fail_on_gaps=True,
                export_csv=False,
                export_parquet=False,
            ),
            fetcher=fetcher,
            asset_pairs_fetcher=_asset_pairs_fixture,
        )


def test_historical_collector_rejects_ambiguous_since_and_start_at(tmp_path):
    with pytest.raises(ValueError, match="use either since or start_at"):
        HistoricalDataCollectorConfig(
            run_id="pytest_ambiguous",
            symbols=("TRXEUR",),
            timeframes=("5m",),
            output_dir=tmp_path,
            since=1,
            start_at="2026-06-01T00:00:00+00:00",
        )
