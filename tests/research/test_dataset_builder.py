import json
import sqlite3

import pytest

from autobot.v2.research.dataset_builder import (
    DatasetBuildConfig,
    build_dataset_from_state_db,
    parse_timeframe_seconds,
)
from autobot.v2.research.market_data_repository import MarketDataRepository


pytestmark = pytest.mark.unit


def _state_db_with_price_samples(path):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE market_price_samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sample_id TEXT,
                symbol TEXT,
                price REAL,
                observed_at TEXT,
                bucket_start TEXT,
                source TEXT,
                created_at TEXT
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO market_price_samples
            (sample_id, symbol, price, observed_at, bucket_start, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("s1", "TRXEUR", 100.0, "2026-06-04T00:00:10+00:00", "b1", "runtime", "c1"),
                ("s1_dup", "TRXEUR", 100.0, "2026-06-04T00:00:10+00:00", "b1", "runtime", "c1"),
                ("s2", "TRXEUR", 101.0, "2026-06-04T00:00:40+00:00", "b1", "runtime", "c2"),
                ("s3", "TRXEUR", 102.0, "2026-06-04T00:02:00+00:00", "b3", "runtime", "c3"),
                ("e1", "ETHEUR", 2000.0, "2026-06-04T00:00:05+00:00", "b1", "runtime", "c4"),
            ],
        )


def test_parse_timeframe_seconds():
    assert parse_timeframe_seconds("1m") == 60
    assert parse_timeframe_seconds("15m") == 900
    assert parse_timeframe_seconds("1h") == 3600


def test_build_dataset_aggregates_samples_dedupes_and_marks_gaps(tmp_path):
    db_path = tmp_path / "state.db"
    _state_db_with_price_samples(db_path)

    result = build_dataset_from_state_db(
        DatasetBuildConfig(
            run_id="pytest_dataset",
            state_db_path=db_path,
            output_dir=tmp_path / "datasets",
            symbols=("TRXEUR",),
            timeframes=("1m", "5m"),
        )
    )

    assert result.raw_sample_count == 4
    assert result.usable_sample_count == 3
    assert result.raw_duplicate_count == 1
    assert result.symbols == ("TRXEUR",)
    assert "volume_unavailable_from_market_price_samples" in result.warnings
    assert result.manifest_path and result.markdown_report_path

    export_1m = next(export for export in result.exports if export.timeframe == "1m")
    assert export_1m.bar_count == 2
    assert export_1m.quality.gap_count == 1
    assert export_1m.csv_path is not None

    bars = MarketDataRepository().load_csv(export_1m.csv_path)
    assert len(bars) == 2
    assert bars[0].open == pytest.approx(100.0)
    assert bars[0].high == pytest.approx(101.0)
    assert bars[0].low == pytest.approx(100.0)
    assert bars[0].close == pytest.approx(101.0)
    assert bars[0].volume == 0.0
    assert bars[0].metadata["source"] == "market_price_samples_ohlcv"

    manifest = json.loads((tmp_path / "datasets" / "pytest_dataset_manifest.json").read_text(encoding="utf-8"))
    assert manifest["raw_duplicate_count"] == 1
    assert manifest["exports"][0]["quality"]["row_count"] >= 1
    assert (tmp_path / "datasets" / "pytest_dataset_quality.md").exists()
