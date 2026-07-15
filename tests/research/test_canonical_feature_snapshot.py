from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from autobot.v2.cli import _build_parser
from autobot.v2.research.canonical_feature_snapshot import (
    CanonicalFeatureSnapshotConfig,
    build_canonical_feature_snapshot,
    upgrade_feature_snapshot_manifest,
)
from autobot.v2.research.canonical_ohlcv_store import CanonicalOHLCVConfig, build_canonical_ohlcv_snapshot


pytestmark = pytest.mark.unit


def _canonical_manifest(tmp_path: Path, *, explicit_mapping: bool, row_count: int = 25) -> Path:
    raw = tmp_path / "raw"
    raw.mkdir()
    path = raw / "BTCZEUR_5m.csv"
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("timestamp", "symbol", "timeframe", "open", "high", "low", "close", "volume"))
        writer.writeheader()
        for index in range(row_count):
            price = 100.0 + index
            writer.writerow(
                {
                    "timestamp": (start + timedelta(minutes=index * 5)).isoformat(),
                    "symbol": "BTCZEUR",
                    "timeframe": "5m",
                    "open": price - 0.5,
                    "high": price + 1.0,
                    "low": price - 1.0,
                    "close": price,
                    "volume": 100,
                }
            )
    snapshot = build_canonical_ohlcv_snapshot(
        CanonicalOHLCVConfig(
            run_id="canonical_source",
            raw_paths=(raw,),
            output_dir=tmp_path / "canonical",
            manifest_dir=tmp_path / "manifests",
            quarantine_dir=tmp_path / "quarantine",
            market_mappings={"BTCZEUR": {"base_asset": "BTC", "quote_asset": "EUR"}} if explicit_mapping else None,
        )
    )
    return Path(str(snapshot.manifest_path))


def test_materialized_feature_snapshot_is_deterministic_and_has_feature_parity(tmp_path):
    manifest = _canonical_manifest(tmp_path, explicit_mapping=True)
    config = CanonicalFeatureSnapshotConfig(
        run_id="features_one",
        canonical_manifest_path=manifest,
        output_dir=tmp_path / "features",
        manifest_dir=tmp_path / "feature_manifests",
    )

    first = build_canonical_feature_snapshot(config)
    second = build_canonical_feature_snapshot(
        CanonicalFeatureSnapshotConfig(
            **{**config.__dict__, "run_id": "features_two"}
        )
    )

    assert first.status == "DATA_MISSING"
    assert first.parity_ok is True
    assert first.feature_count == 25 * 4
    assert first.feature_versions == {
        "return_1_bps": "1.0.0",
        "momentum_3_bps": "1.0.0",
        "volatility_20_bps": "1.0.0",
        "atr_14_bps": "1.0.0",
    }
    assert first.ready_count > 0
    assert first.fingerprint == second.fingerprint
    assert first.feature_snapshot_id == second.feature_snapshot_id
    assert first.ingestion_time_unknown_count == 25
    assert "INGESTION_TIME_UNKNOWN_RUNTIME_PARITY_NOT_PROVEN" in first.blockers
    assert Path(str(first.manifest_path)).exists()


def test_materialized_feature_snapshot_excludes_unverified_market_mappings(tmp_path):
    manifest = _canonical_manifest(tmp_path, explicit_mapping=False)

    snapshot = build_canonical_feature_snapshot(
        CanonicalFeatureSnapshotConfig(
            run_id="features_unverified",
            canonical_manifest_path=manifest,
            output_dir=tmp_path / "features",
            manifest_dir=tmp_path / "feature_manifests",
        )
    )

    assert snapshot.status == "DATA_MISSING"
    assert snapshot.feature_count == 0
    assert snapshot.rejected_unverified_mapping_count == 25
    assert "UNVERIFIED_MARKET_MAPPING_ROWS_EXCLUDED" in snapshot.blockers


def test_feature_snapshot_streams_full_history_with_bounded_parity_replay(tmp_path):
    manifest = _canonical_manifest(tmp_path, explicit_mapping=True, row_count=2_500)

    snapshot = build_canonical_feature_snapshot(
        CanonicalFeatureSnapshotConfig(
            run_id="features_bounded_parity",
            canonical_manifest_path=manifest,
            output_dir=tmp_path / "features",
            manifest_dir=tmp_path / "feature_manifests",
        )
    )

    assert snapshot.canonical_row_count == 2_500
    assert snapshot.feature_count == 2_500 * 4
    assert snapshot.parity_sample_row_count == 2_048
    assert snapshot.parity_validation_scope == "bounded_deterministic_sample"
    assert snapshot.parity_ok is True
    assert not list((tmp_path / "features").glob(".autobot_features_*"))


def test_legacy_feature_manifest_upgrade_requires_matching_registry_fingerprint(tmp_path):
    manifest = _canonical_manifest(tmp_path, explicit_mapping=True)
    snapshot = build_canonical_feature_snapshot(
        CanonicalFeatureSnapshotConfig(
            run_id="features_upgrade",
            canonical_manifest_path=manifest,
            output_dir=tmp_path / "features",
            manifest_dir=tmp_path / "feature_manifests",
        )
    )
    payload = json.loads(Path(str(snapshot.manifest_path)).read_text(encoding="utf-8"))
    payload.pop("feature_versions")
    legacy = tmp_path / "legacy_features.json"
    legacy.write_text(json.dumps(payload), encoding="utf-8")

    upgraded = upgrade_feature_snapshot_manifest(legacy, tmp_path / "upgraded_features.json")

    upgraded_payload = json.loads(upgraded.read_text(encoding="utf-8"))
    assert upgraded_payload["feature_versions"] == snapshot.feature_versions
    assert upgraded_payload["manifest_upgrade"]["bundle_values_recomputed"] is False


def test_materialize_feature_snapshot_cli_is_registered():
    parser = _build_parser()
    args = parser.parse_args(
        [
            "materialize-feature-snapshot",
            "--canonical-manifest",
            "data/research/manifests/example.json",
        ]
    )

    assert args.command == "materialize-feature-snapshot"
    assert args.feature_ids == "return_1_bps,momentum_3_bps,volatility_20_bps,atr_14_bps"
    assert args.report_dir == "data/research/reports/canonical_features"


def test_alpha_runner_accepts_explicit_feature_manifest_for_registry_evidence():
    parser = _build_parser()
    args = parser.parse_args(
        [
            "alpha-hypothesis-runner",
            "--hypothesis-id",
            "long_trend",
            "--feature-snapshot-manifest",
            "data/research/manifests/features.json",
        ]
    )

    assert args.feature_snapshot_manifest.endswith("features.json")
    assert args.experiment_registry == "data/research/experiment_registry.sqlite3"


def test_upgrade_feature_snapshot_manifest_cli_is_registered():
    parser = _build_parser()
    args = parser.parse_args(
        [
            "upgrade-feature-snapshot-manifest",
            "--source-manifest",
            "data/research/manifests/legacy.json",
            "--output-manifest",
            "data/research/manifests/upgraded.json",
        ]
    )

    assert args.command == "upgrade-feature-snapshot-manifest"
