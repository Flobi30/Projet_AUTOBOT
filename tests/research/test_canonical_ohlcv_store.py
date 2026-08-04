from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from autobot.v2.cli import _build_parser
from autobot.v2.research.canonical_ohlcv_store import (
    CanonicalOHLCVManifestError,
    CanonicalOHLCVConfig,
    adapt_legacy_canonical_row,
    build_canonical_ohlcv_snapshot,
    classify_snapshot_significance,
    resolve_canonical_ohlcv_snapshot_files,
    verify_canonical_raw_source_provenance,
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
    assert verify_canonical_raw_source_provenance(snapshot) is True


def test_canonical_manifest_resolves_only_its_declared_snapshot_files(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    source = raw / "BTCZEUR_5m.csv"
    _write_rows(source, "BTCZEUR", "5m", [datetime(2026, 1, 1, tzinfo=timezone.utc)])
    snapshot = build_canonical_ohlcv_snapshot(
        CanonicalOHLCVConfig(
            run_id="pytest_manifest_binding",
            raw_paths=(raw,),
            output_dir=tmp_path / "canonical" / "ohlcv",
            manifest_dir=tmp_path / "manifests",
            quarantine_dir=tmp_path / "quarantine",
        )
    )

    assert snapshot.manifest_path
    assert resolve_canonical_ohlcv_snapshot_files(snapshot.manifest_path) == (
        Path(snapshot.files[0].csv_path),
    )

    malformed = json.loads(Path(snapshot.manifest_path).read_text(encoding="utf-8"))
    malformed["files"][0]["csv_path"] = str(tmp_path / "outside_snapshot.csv")
    malformed_path = tmp_path / "malformed_manifest.json"
    malformed_path.write_text(json.dumps(malformed), encoding="utf-8")
    with pytest.raises(CanonicalOHLCVManifestError, match="outside_snapshot"):
        resolve_canonical_ohlcv_snapshot_files(malformed_path)

    malformed["schema_version"] = "not-a-version"
    malformed_path.write_text(json.dumps(malformed), encoding="utf-8")
    with pytest.raises(CanonicalOHLCVManifestError, match="schema_unsupported"):
        resolve_canonical_ohlcv_snapshot_files(malformed_path)


def test_canonical_snapshot_detects_raw_source_mutation_after_materialization(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    source = raw / "BTCZEUR_5m.csv"
    _write_rows(source, "BTCZEUR", "5m", [datetime(2026, 1, 1, tzinfo=timezone.utc)])

    first = build_canonical_ohlcv_snapshot(
        CanonicalOHLCVConfig(
            run_id="pytest_raw_hash_first",
            raw_paths=(raw,),
            output_dir=tmp_path / "canonical" / "ohlcv",
            manifest_dir=tmp_path / "manifests",
            quarantine_dir=tmp_path / "quarantine",
        )
    )

    assert len(first.raw_sources) == 1
    assert verify_canonical_raw_source_provenance(first) is True
    assert verify_canonical_raw_source_provenance(first.to_dict()) is True
    source.write_text(source.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert verify_canonical_raw_source_provenance(first) is False

    second = build_canonical_ohlcv_snapshot(
        CanonicalOHLCVConfig(
            run_id="pytest_raw_hash_second",
            raw_paths=(raw,),
            output_dir=tmp_path / "canonical" / "ohlcv",
            manifest_dir=tmp_path / "manifests",
            quarantine_dir=tmp_path / "quarantine",
        )
    )

    assert second.fingerprint != first.fingerprint
    assert verify_canonical_raw_source_provenance(second) is True


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


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    (
        ("available_time", "2026-01-01T00:06:00", "naive_available_time"),
        ("bar_close_time", "2026-01-01T00:05:00", "naive_bar_close_time"),
        ("ingestion_time", "2026-01-01T00:07:00", "naive_ingestion_time"),
    ),
)
def test_canonical_ohlcv_quarantines_naive_explicit_temporal_times(tmp_path, field, value, reason):
    raw = tmp_path / "raw"
    raw.mkdir()
    path = raw / "BTCZEUR_5m.csv"
    path.write_text(
        "timestamp,symbol,timeframe,open,high,low,close,volume," + field + "\n"
        "2026-01-01T00:00:00+00:00,BTCZEUR,5m,100,101,99,100.5,1000," + value + "\n",
        encoding="utf-8",
    )

    snapshot = build_canonical_ohlcv_snapshot(
        CanonicalOHLCVConfig(
            run_id=f"pytest_naive_{field}",
            raw_paths=(raw,),
            output_dir=tmp_path / "canonical" / "ohlcv",
            manifest_dir=tmp_path / "manifests",
            quarantine_dir=tmp_path / "quarantine",
        )
    )

    assert snapshot.canonical_row_count == 0
    quarantine = json.loads((tmp_path / "quarantine" / f"pytest_naive_{field}_quarantine.json").read_text(encoding="utf-8"))
    assert quarantine[0]["reason"] == reason


def test_canonical_ohlcv_preserves_explicit_aware_temporal_times(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    path = raw / "BTCZEUR_5m.csv"
    path.write_text(
        "timestamp,symbol,timeframe,open,high,low,close,volume,available_time,bar_close_time,ingestion_time\n"
        "2026-01-01T00:00:00+00:00,BTCZEUR,5m,100,101,99,100.5,1000,"
        "2026-01-01T00:06:00+00:00,2026-01-01T00:05:00+00:00,2026-01-01T00:07:00+00:00\n",
        encoding="utf-8",
    )

    snapshot = build_canonical_ohlcv_snapshot(
        CanonicalOHLCVConfig(
            run_id="pytest_aware_temporal_times",
            raw_paths=(raw,),
            output_dir=tmp_path / "canonical" / "ohlcv",
            manifest_dir=tmp_path / "manifests",
            quarantine_dir=tmp_path / "quarantine",
        )
    )

    row = _read_rows(Path(snapshot.files[0].csv_path))[0]
    assert row["available_time"] == "2026-01-01T00:06:00+00:00"
    assert row["bar_close_time"] == "2026-01-01T00:05:00+00:00"
    assert row["ingestion_time"] == "2026-01-01T00:07:00+00:00"


def test_canonical_ohlcv_uses_known_ingestion_when_source_availability_is_missing(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    path = raw / "BTCZEUR_5m.csv"
    path.write_text(
        "timestamp,symbol,timeframe,open,high,low,close,volume,ingestion_time\n"
        "2026-01-01T00:00:00+00:00,BTCZEUR,5m,100,101,99,100.5,1000,2026-01-01T00:15:00+00:00\n",
        encoding="utf-8",
    )

    snapshot = build_canonical_ohlcv_snapshot(
        CanonicalOHLCVConfig(
            run_id="pytest_ingestion_constrained_availability",
            raw_paths=(raw,),
            output_dir=tmp_path / "canonical" / "ohlcv",
            manifest_dir=tmp_path / "manifests",
            quarantine_dir=tmp_path / "quarantine",
        )
    )

    row = _read_rows(Path(snapshot.files[0].csv_path))[0]
    assert row["bar_close_time"] == "2026-01-01T00:05:00+00:00"
    assert row["available_time"] == "2026-01-01T00:15:00+00:00"
    assert row["ingestion_time"] == "2026-01-01T00:15:00+00:00"
    assert row["availability_basis"] == "DERIVED_BAR_CLOSE_CONSTRAINED_BY_INGESTION"
    assert row["temporal_status"] == "HISTORICAL_BACKFILL_AVAILABLE_AT_INGESTION"


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


def test_legacy_canonical_row_with_recorded_ingestion_becomes_available_at_ingestion():
    legacy = {
        "exchange": "kraken",
        "market_type": "spot",
        "symbol": "BTCZEUR",
        "timeframe": "5m",
        "open_timestamp": "2026-01-01T00:00:00+00:00",
        "open": "100",
        "high": "101",
        "low": "99",
        "close": "100.5",
        "volume": "1000",
    }
    recorded_ingestion = datetime(2026, 1, 1, 0, 15, tzinfo=timezone.utc)

    adapted = adapt_legacy_canonical_row(legacy, recorded_ingestion_time=recorded_ingestion)

    assert adapted["available_time"] == recorded_ingestion.isoformat()
    assert adapted["ingestion_time"] == recorded_ingestion.isoformat()
    assert adapted["availability_basis"] == "MIGRATED_LEGACY_BAR_CLOSE_CONSTRAINED_BY_RECORDED_INGESTION"
    assert adapted["temporal_status"] == "MIGRATED_LEGACY_WITH_RECORDED_INGESTION"


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


def test_canonical_snapshot_spools_duplicate_history_without_leaving_runtime_artifacts(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    timestamps = [start + timedelta(minutes=5 * index) for index in range(2_500)]
    _write_rows(raw / "BTCZEUR_5m_a.csv", "BTCZEUR", "5m", timestamps)
    _write_rows(raw / "BTCZEUR_5m_b.csv", "BTCZEUR", "5m", timestamps)
    output_dir = tmp_path / "canonical" / "ohlcv"

    snapshot = build_canonical_ohlcv_snapshot(
        CanonicalOHLCVConfig(
            run_id="pytest_spooled_history",
            raw_paths=(raw,),
            output_dir=output_dir,
            manifest_dir=tmp_path / "manifests",
            quarantine_dir=tmp_path / "quarantine",
            market_mappings={"BTCZEUR": {"base_asset": "BTC", "quote_asset": "EUR"}},
        )
    )

    assert snapshot.raw_row_count == 5_000
    assert snapshot.canonical_row_count == 2_500
    assert snapshot.duplicate_count == 2_500
    assert not list(output_dir.glob(".autobot_canonical_*"))


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
