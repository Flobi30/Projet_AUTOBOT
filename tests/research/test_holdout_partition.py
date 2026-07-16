from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from autobot.v2.research.holdout_partition import (
    HOLDOUT_REVIEW_ROLE,
    OPTIMIZATION_ROLE,
    HoldoutPartitionConfig,
    HoldoutPartitionError,
    materialize_holdout_partition,
    verify_holdout_partition,
)


pytestmark = pytest.mark.unit


def test_materialized_holdout_is_point_in_time_disjoint_and_idempotent(tmp_path):
    source_manifest, source_file = _source_snapshot(tmp_path)
    start = datetime(2026, 1, 1, 3, tzinfo=timezone.utc)
    config = HoldoutPartitionConfig(
        run_id="pytest_holdout",
        source_snapshot_manifest=source_manifest,
        holdout_start_at=start,
        output_dir=tmp_path / "partitions",
    )

    first = materialize_holdout_partition(config)
    second = materialize_holdout_partition(config)

    assert first == second
    assert first.optimization_row_count == 2
    assert first.holdout_row_count == 2
    assert first.unknown_ingestion_time_count == 1
    assert Path(first.optimization_snapshot_manifest).is_file()
    assert Path(first.holdout_snapshot_manifest).is_file()
    assert first.identity_dict()["optimization_snapshot_id"] == first.optimization_snapshot_id
    optimization_rows = _read_partition_rows(Path(first.optimization_data_dir))
    holdout_rows = _read_partition_rows(Path(first.holdout_data_dir))
    assert {row["available_time"] for row in optimization_rows}.isdisjoint(
        {row["available_time"] for row in holdout_rows}
    )
    assert all(row["available_time"] < start.isoformat() for row in optimization_rows)
    assert all(row["available_time"] >= start.isoformat() for row in holdout_rows)
    assert source_file.exists()
    assert verify_holdout_partition(
        first.manifest_path,
        role=OPTIMIZATION_ROLE,
        data_paths=(Path(first.optimization_data_dir),),
    ) == first
    assert verify_holdout_partition(
        first.manifest_path,
        role=HOLDOUT_REVIEW_ROLE,
        data_paths=(Path(first.holdout_data_dir),),
    ) == first


def test_partition_refuses_source_or_mixed_roots_for_optimization(tmp_path):
    source_manifest, source_file = _source_snapshot(tmp_path)
    partition = materialize_holdout_partition(
        HoldoutPartitionConfig(
            run_id="pytest_roots",
            source_snapshot_manifest=source_manifest,
            holdout_start_at=datetime(2026, 1, 1, 3, tzinfo=timezone.utc),
            output_dir=tmp_path / "partitions",
        )
    )

    with pytest.raises(HoldoutPartitionError, match="exactly its sealed data root"):
        verify_holdout_partition(partition.manifest_path, role=OPTIMIZATION_ROLE, data_paths=(source_file,))
    with pytest.raises(HoldoutPartitionError, match="exactly its sealed data root"):
        verify_holdout_partition(
            partition.manifest_path,
            role=OPTIMIZATION_ROLE,
            data_paths=(Path(partition.optimization_data_dir), Path(partition.holdout_data_dir)),
        )


def test_partition_detects_tampered_sealed_data(tmp_path):
    source_manifest, _ = _source_snapshot(tmp_path)
    partition = materialize_holdout_partition(
        HoldoutPartitionConfig(
            run_id="pytest_tamper",
            source_snapshot_manifest=source_manifest,
            holdout_start_at=datetime(2026, 1, 1, 3, tzinfo=timezone.utc),
            output_dir=tmp_path / "partitions",
        )
    )
    sealed_file = next(Path(partition.optimization_data_dir).glob("*.csv"))
    sealed_file.chmod(0o666)
    sealed_file.write_text(sealed_file.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(HoldoutPartitionError, match="contents do not match"):
        verify_holdout_partition(
            partition.manifest_path,
            role=OPTIMIZATION_ROLE,
            data_paths=(Path(partition.optimization_data_dir),),
        )


def test_partition_rejects_unlisted_files_and_symlinks(tmp_path):
    source_manifest, source_file = _source_snapshot(tmp_path)
    partition = materialize_holdout_partition(
        HoldoutPartitionConfig(
            run_id="pytest_unlisted",
            source_snapshot_manifest=source_manifest,
            holdout_start_at=datetime(2026, 1, 1, 3, tzinfo=timezone.utc),
            output_dir=tmp_path / "partitions",
        )
    )
    optimization_dir = Path(partition.optimization_data_dir)
    unexpected = optimization_dir / "unexpected.json"
    unexpected.write_text("{}", encoding="utf-8")
    with pytest.raises(HoldoutPartitionError, match="unexpected non-CSV"):
        verify_holdout_partition(
            partition.manifest_path,
            role=OPTIMIZATION_ROLE,
            data_paths=(optimization_dir,),
        )
    unexpected.unlink()

    symlink = optimization_dir / "escaped.csv"
    try:
        symlink.symlink_to(source_file)
    except OSError:
        pytest.skip("symlink creation is unavailable in this environment")
    with pytest.raises(HoldoutPartitionError, match="cannot contain symlinks"):
        verify_holdout_partition(
            partition.manifest_path,
            role=OPTIMIZATION_ROLE,
            data_paths=(optimization_dir,),
        )


def test_partition_detects_a_modified_role_snapshot_manifest(tmp_path):
    source_manifest, _ = _source_snapshot(tmp_path)
    partition = materialize_holdout_partition(
        HoldoutPartitionConfig(
            run_id="pytest_role_manifest",
            source_snapshot_manifest=source_manifest,
            holdout_start_at=datetime(2026, 1, 1, 3, tzinfo=timezone.utc),
            output_dir=tmp_path / "partitions",
        )
    )
    role_manifest = Path(partition.optimization_snapshot_manifest)
    role_manifest.chmod(0o666)
    payload = json.loads(role_manifest.read_text(encoding="utf-8"))
    payload["snapshot_id"] = "tampered_snapshot"
    role_manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(HoldoutPartitionError, match="snapshot manifest does not match"):
        verify_holdout_partition(
            partition.manifest_path,
            role=OPTIMIZATION_ROLE,
            data_paths=(Path(partition.optimization_data_dir),),
        )


def _source_snapshot(tmp_path: Path) -> tuple[Path, Path]:
    source_dir = tmp_path / "canonical" / "ohlcv" / "snapshot"
    source_dir.mkdir(parents=True)
    source_file = source_dir / "kraken_spot_BTCEUR_1h.csv"
    fields = (
        "exchange",
        "market_type",
        "symbol",
        "timeframe",
        "open_timestamp",
        "event_time",
        "available_time",
        "ingestion_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
    )
    origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    for index in range(5):
        event = origin + timedelta(hours=index + 1)
        rows.append(
            {
                "exchange": "kraken",
                "market_type": "spot",
                "symbol": "BTCEUR",
                "timeframe": "1h",
                "open_timestamp": (event - timedelta(hours=1)).isoformat(),
                "event_time": event.isoformat(),
                "available_time": event.isoformat(),
                "ingestion_time": "" if index == 4 else event.isoformat(),
                "open": "100",
                "high": "101",
                "low": "99",
                "close": "100",
                "volume": "1000",
            }
        )
    with source_file.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    manifest = tmp_path / "canonical_snapshot.json"
    manifest.write_text(
        json.dumps(
            {
                "snapshot_id": "ohlcv_v2_test",
                "fingerprint": "source-fingerprint",
                "market_type": "spot",
                "files": [{"csv_path": str(source_file)}],
            }
        ),
        encoding="utf-8",
    )
    return manifest, source_file


def _read_partition_rows(directory: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in directory.glob("*.csv"):
        with path.open("r", encoding="utf-8", newline="") as handle:
            rows.extend(dict(row) for row in csv.DictReader(handle))
    return rows
