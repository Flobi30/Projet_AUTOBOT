from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from autobot.v2.cli import _build_parser
from autobot.v2.research.canonical_ohlcv_store import (
    CanonicalOHLCVConfig,
    adapt_legacy_canonical_row,
    build_canonical_ohlcv_snapshot,
    classify_snapshot_significance,
)


pytestmark = pytest.mark.unit


def test_canonical_ohlcv_snapshot_dedupes_sorts_and_uses_utc(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    first = raw / "XXBTZEUR_5m_a.csv"
    second = raw / "BTCZEUR_5m_b.csv"
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    _write_rows(first, "XXBTZEUR", "5m", [start, start + timedelta(minutes=5), start + timedelta(minutes=20)])
    _write_rows(second, "BTCZEUR", "5m", [start])

    snapshot = build_canonical_ohlcv_snapshot(
        CanonicalOHLCVConfig(
            run_id="pytest_canonical",
            raw_paths=(raw,),
            output_dir=tmp_path / "canonical" / "ohlcv",
            manifest_dir=tmp_path / "manifests",
            quarantine_dir=tmp_path / "quarantine",
        )
    )

    assert snapshot.raw_row_count == 4
    assert snapshot.canonical_row_count == 3
    assert snapshot.duplicate_count == 1
    assert snapshot.gap_count == 1
    assert snapshot.symbols == ("BTCZEUR",)
    assert snapshot.files[0].csv_path.endswith("kraken_spot_BTCZEUR_5m.csv")
    rows = _read_rows(Path(snapshot.files[0].csv_path))
    assert [row["open_timestamp"] for row in rows] == sorted(row["open_timestamp"] for row in rows)
    assert all(row["open_timestamp"].endswith("+00:00") for row in rows)
    assert {(row["exchange"], row["market_type"], row["symbol"], row["timeframe"]) for row in rows} == {
        ("kraken", "spot", "BTCZEUR", "5m")
    }
    assert Path(str(snapshot.manifest_path)).exists()


def test_canonical_ohlcv_snapshot_is_idempotent(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    _write_rows(raw / "ETHZEUR_1h.csv", "ETHZEUR", "1h", [start + timedelta(hours=index) for index in range(3)])

    first = build_canonical_ohlcv_snapshot(
        CanonicalOHLCVConfig(
            run_id="pytest_first",
            raw_paths=(raw,),
            output_dir=tmp_path / "canonical" / "ohlcv",
            manifest_dir=tmp_path / "manifests",
            quarantine_dir=tmp_path / "quarantine",
        )
    )
    second = build_canonical_ohlcv_snapshot(
        CanonicalOHLCVConfig(
            run_id="pytest_second",
            raw_paths=(raw,),
            output_dir=tmp_path / "canonical" / "ohlcv",
            manifest_dir=tmp_path / "manifests",
            quarantine_dir=tmp_path / "quarantine",
        )
    )

    assert first.fingerprint == second.fingerprint
    assert first.snapshot_id == second.snapshot_id
    assert second.new_data_significance == "same_data"


def test_canonical_ohlcv_rows_are_point_in_time_and_use_explicit_market_mapping(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    _write_rows(raw / "BTCZEUR_5m.csv", "BTCZEUR", "5m", [start])

    snapshot = build_canonical_ohlcv_snapshot(
        CanonicalOHLCVConfig(
            run_id="pytest_temporal",
            raw_paths=(raw,),
            output_dir=tmp_path / "canonical" / "ohlcv",
            manifest_dir=tmp_path / "manifests",
            quarantine_dir=tmp_path / "quarantine",
            market_mappings={"BTCZEUR": {"base_asset": "BTC", "quote_asset": "EUR"}},
        )
    )
    row = _read_rows(Path(snapshot.files[0].csv_path))[0]

    assert row["schema_version"] == "2"
    assert row["event_time"] == "2026-01-01T00:05:00+00:00"
    assert row["bar_close_time"] == "2026-01-01T00:05:00+00:00"
    assert row["available_time"] == row["bar_close_time"]
    assert row["ingestion_time"] == ""
    assert row["source_timestamp_role"] == "legacy_assumed_open"
    assert row["availability_basis"] == "DERIVED_BAR_CLOSE"
    assert row["temporal_status"] == "AVAILABLE_AT_BAR_CLOSE_INGESTION_UNKNOWN"
    assert (row["base_asset"], row["quote_asset"], row["market_mapping_status"]) == ("BTC", "EUR", "EXPLICIT")


def test_canonical_ohlcv_quarantines_naive_source_timestamp(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    path = raw / "BTCZEUR_5m.csv"
    path.write_text(
        "timestamp,symbol,timeframe,open,high,low,close,volume\n"
        "2026-01-01T00:00:00,BTCZEUR,5m,100,101,99,100.5,1000\n",
        encoding="utf-8",
    )

    snapshot = build_canonical_ohlcv_snapshot(
        CanonicalOHLCVConfig(
            run_id="pytest_naive",
            raw_paths=(raw,),
            output_dir=tmp_path / "canonical" / "ohlcv",
            manifest_dir=tmp_path / "manifests",
            quarantine_dir=tmp_path / "quarantine",
        )
    )

    assert snapshot.canonical_row_count == 0
    assert snapshot.quarantine_count == 1
    quarantine = json.loads((tmp_path / "quarantine" / "pytest_naive_quarantine.json").read_text(encoding="utf-8"))
    assert quarantine[0]["reason"] == "naive_timestamp"


def test_legacy_canonical_rows_adapt_without_faking_ingestion_time():
    legacy = {
        "exchange": "kraken",
        "market_type": "spot",
        "symbol": "BTCZEUR",
        "timeframe": "5m",
        "open_timestamp": "2026-01-01T00:00:00+00:00",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "open": "100",
        "high": "101",
        "low": "99",
        "close": "100.5",
        "volume": "1000",
        "source_path": "legacy.csv",
        "source_row_number": "2",
    }

    adapted = adapt_legacy_canonical_row(
        legacy,
        market_mappings={"BTCZEUR": {"base_asset": "BTC", "quote_asset": "EUR"}},
    )

    assert adapted["schema_version"] == "2"
    assert adapted["event_time"] == "2026-01-01T00:05:00+00:00"
    assert adapted["ingestion_time"] == ""
    assert adapted["temporal_status"] == "AVAILABLE_AT_BAR_CLOSE_INGESTION_UNKNOWN"


def test_conflicting_legacy_timestamp_columns_are_quarantined(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "BTCZEUR_5m.csv").write_text(
        "timestamp,open_timestamp,symbol,timeframe,open,high,low,close,volume\n"
        "2026-01-01T00:00:00+00:00,2026-01-01T00:05:00+00:00,BTCZEUR,5m,100,101,99,100.5,1000\n",
        encoding="utf-8",
    )

    snapshot = build_canonical_ohlcv_snapshot(
        CanonicalOHLCVConfig(
            run_id="pytest_conflict",
            raw_paths=(raw,),
            output_dir=tmp_path / "canonical" / "ohlcv",
            manifest_dir=tmp_path / "manifests",
            quarantine_dir=tmp_path / "quarantine",
        )
    )

    assert snapshot.canonical_row_count == 0
    quarantine = json.loads((tmp_path / "quarantine" / "pytest_conflict_quarantine.json").read_text(encoding="utf-8"))
    assert quarantine[0]["reason"] == "conflicting_timestamp_and_open_timestamp"


def test_snapshot_significance_changes_only_for_meaningful_new_period():
    previous = {
        "fingerprint": "old",
        "canonical_row_count": 1_000,
        "end_at": "2026-01-01T00:00:00+00:00",
    }
    minor = {
        "fingerprint": "new_minor",
        "canonical_row_count": 1_005,
        "end_at": "2026-01-02T00:00:00+00:00",
    }
    significant = {
        "fingerprint": "new_sig",
        "canonical_row_count": 1_250,
        "end_at": "2026-02-15T00:00:00+00:00",
    }

    assert classify_snapshot_significance(previous, previous) == "same_data"
    assert classify_snapshot_significance(previous, minor) == "minor_addition"
    assert classify_snapshot_significance(previous, significant) == "significant_new_period"


def test_canonicalize_ohlcv_cli_is_registered():
    parser = _build_parser()
    args = parser.parse_args(
        [
            "canonicalize-ohlcv",
            "--raw-paths",
            "data/research/raw",
            "--max-files",
            "2",
        ]
    )

    assert args.command == "canonicalize-ohlcv"
    assert args.max_files == 2
    assert args.market_mapping_source == "kraken_public"
    assert args.report_dir == "data/research/reports/canonical_ohlcv"


def _write_rows(path: Path, symbol: str, timeframe: str, timestamps: list[datetime]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["timestamp", "symbol", "timeframe", "open", "high", "low", "close", "volume"],
        )
        writer.writeheader()
        for index, timestamp in enumerate(timestamps):
            price = 100 + index
            writer.writerow(
                {
                    "timestamp": timestamp.isoformat(),
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "open": price,
                    "high": price + 1,
                    "low": price - 1,
                    "close": price + 0.25,
                    "volume": 1000,
                }
            )


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))
