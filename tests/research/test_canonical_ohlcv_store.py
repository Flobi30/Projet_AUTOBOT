from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from autobot.v2.cli import _build_parser
from autobot.v2.research.canonical_ohlcv_store import (
    CanonicalOHLCVConfig,
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
