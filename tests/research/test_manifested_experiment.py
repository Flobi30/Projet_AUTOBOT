from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone

import pytest

from autobot.v2.research.manifested_experiment import (
    ManifestedExperimentError,
    build_manifested_experiment_spec,
    load_feature_snapshot_provenance,
)
from autobot.v2.research.canonical_feature_snapshot import CanonicalFeatureSnapshotConfig, build_canonical_feature_snapshot
from autobot.v2.research.holdout_partition import HoldoutPartitionConfig, materialize_holdout_partition


pytestmark = pytest.mark.unit


def _manifest(tmp_path, **overrides):
    payload = {
        "status": "READY",
        "parity_ok": True,
        "feature_count": 100,
        "feature_snapshot_id": "features_v1_test",
        "fingerprint": "feature-fingerprint",
        "source_snapshot_id": "ohlcv_v2_test",
        "source_snapshot_fingerprint": "source-fingerprint",
        "feature_registry_fingerprint": "registry-fingerprint",
        "feature_versions": {"momentum_3_bps": "1.0.0"},
        "ingestion_time_unknown_count": 10,
    }
    payload.update(overrides)
    path = tmp_path / "feature_snapshot.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _verified_manifest(tmp_path):
    source = tmp_path / "canonical_features_source.csv"
    fieldnames = (
        "exchange",
        "market_type",
        "symbol",
        "base_asset",
        "quote_asset",
        "market_mapping_status",
        "timeframe",
        "event_time",
        "available_time",
        "ingestion_time",
        "close",
    )
    origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for index in range(25):
            event = origin + timedelta(minutes=5 * index)
            writer.writerow(
                {
                    "exchange": "kraken",
                    "market_type": "spot",
                    "symbol": "BTCEUR",
                    "base_asset": "BTC",
                    "quote_asset": "EUR",
                    "market_mapping_status": "EXPLICIT",
                    "timeframe": "5m",
                    "event_time": event.isoformat(),
                    "available_time": event.isoformat(),
                    "ingestion_time": event.isoformat(),
                    "close": str(100 + index),
                }
            )
    source_manifest = tmp_path / "canonical_features_source.json"
    source_manifest.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "snapshot_id": "canonical_features_source",
                "fingerprint": "canonical-features-source-fingerprint",
                "market_type": "spot",
                "files": [{"csv_path": str(source)}],
            }
        ),
        encoding="utf-8",
    )
    snapshot = build_canonical_feature_snapshot(
        CanonicalFeatureSnapshotConfig(
            run_id="manifested_experiment_verified",
            canonical_manifest_path=source_manifest,
            output_dir=tmp_path / "features",
            manifest_dir=tmp_path / "feature_manifests",
        )
    )
    assert snapshot.status == "READY"
    return snapshot.manifest_path


def test_manifested_experiment_binds_all_feature_and_source_fingerprints(tmp_path):
    spec, provenance = build_manifested_experiment_spec(
        hypothesis_id="long_trend",
        template_id="regime_filtered_trend",
        thesis="test thesis",
        code_commit="abc123",
        feature_snapshot_manifest=_verified_manifest(tmp_path),
        parameters={"lookback": 24},
        seed=7,
        cost_model={"profile": "research_stress"},
    )

    assert spec.data_snapshot_id == "canonical_features_source"
    assert spec.feature_versions["momentum_3_bps"] == "1.0.0"
    assert spec.environment["feature_snapshot"]["material_verified"] is True
    assert spec.environment["feature_snapshot"]["bundle_content_fingerprint"]
    assert "manifest_path" not in spec.environment["feature_snapshot"]
    assert spec.environment["runtime_parity_proven"] is True
    assert provenance.runtime_parity_proven is True


def test_manifested_experiment_refuses_unready_or_unproven_feature_snapshot(tmp_path):
    with pytest.raises(ManifestedExperimentError, match="status must be READY"):
        load_feature_snapshot_provenance(_manifest(tmp_path, status="DATA_MISSING"))

    with pytest.raises(ManifestedExperimentError, match="parity must be true"):
        load_feature_snapshot_provenance(_manifest(tmp_path, parity_ok=False))

    with pytest.raises(ManifestedExperimentError, match="feature_versions are required"):
        load_feature_snapshot_provenance(_manifest(tmp_path, feature_versions={}))


def test_manifested_experiment_cannot_relax_research_only_safety(tmp_path):
    with pytest.raises(ManifestedExperimentError, match="cannot enable"):
        build_manifested_experiment_spec(
            hypothesis_id="long_trend",
            template_id="regime_filtered_trend",
            thesis="test thesis",
            code_commit="abc123",
            feature_snapshot_manifest=_verified_manifest(tmp_path),
            parameters={},
            seed=7,
            cost_model={},
            environment={"live_allowed": True},
        )


def test_manifested_experiment_fingerprint_changes_for_material_inputs_not_runner_identity(tmp_path):
    common = {
        "hypothesis_id": "long_trend",
        "template_id": "regime_filtered_trend",
        "thesis": "test thesis",
        "code_commit": "abc123",
        "feature_snapshot_manifest": _verified_manifest(tmp_path),
        "parameters": {"max_variants": 3, "symbols": ["BTCZEUR"]},
        "seed": 7,
        "cost_model": {"profile": "research_stress"},
    }

    first, _ = build_manifested_experiment_spec(**common, environment={"data_paths": ["canonical"]})
    second, _ = build_manifested_experiment_spec(**common, environment={"data_paths": ["canonical"]})

    assert first.experiment_id == second.experiment_id


def test_manifested_experiment_binds_a_physical_holdout_identity(tmp_path):
    partition = _physical_holdout_partition(tmp_path)
    spec, _ = build_manifested_experiment_spec(
        hypothesis_id="long_trend",
        template_id="regime_filtered_trend",
        thesis="test thesis",
        code_commit="abc123",
        feature_snapshot_manifest=_manifest(
            tmp_path,
            source_snapshot_id=partition.optimization_snapshot_id,
            source_snapshot_fingerprint=partition.optimization_snapshot_fingerprint,
            holdout_partition=partition.identity_dict(),
            holdout_partition_role="optimization",
        ),
        parameters={"lookback": 24},
        seed=7,
        cost_model={"profile": "research_stress"},
        holdout_id=partition.partition_id,
        holdout_partition_manifest=partition.manifest_path,
    )

    assert spec.holdout_id == partition.partition_id
    assert spec.environment["holdout_partition"]["optimization_snapshot_id"] == partition.optimization_snapshot_id
    assert "manifest_path" not in spec.environment["holdout_partition"]
    assert "optimization_data_dir" not in spec.environment["holdout_partition"]
    assert spec.to_dict()["paper_capital_allowed"] is False
    assert spec.to_dict()["live_allowed"] is False


def test_manifested_experiment_refuses_unpartitioned_or_mismatched_holdout(tmp_path):
    common = {
        "hypothesis_id": "long_trend",
        "template_id": "regime_filtered_trend",
        "thesis": "test thesis",
        "code_commit": "abc123",
        "feature_snapshot_manifest": _manifest(tmp_path),
        "parameters": {},
        "seed": 7,
        "cost_model": {"profile": "research_stress"},
        "holdout_id": "holdout_2026_q3",
    }
    with pytest.raises(ManifestedExperimentError, match="physical holdout partition"):
        build_manifested_experiment_spec(**common)

    partition = _physical_holdout_partition(tmp_path)
    mismatched = {
        **common,
        "feature_snapshot_manifest": _manifest(
            tmp_path,
            source_snapshot_id="other_snapshot",
            source_snapshot_fingerprint="other-fingerprint",
            holdout_partition=partition.identity_dict(),
            holdout_partition_role="optimization",
        ),
    }
    mismatched["holdout_id"] = partition.partition_id
    with pytest.raises(ManifestedExperimentError, match="optimization snapshot does not match"):
        build_manifested_experiment_spec(
            **mismatched,
            holdout_partition_manifest=partition.manifest_path,
        )


def _physical_holdout_partition(tmp_path):
    source_file = tmp_path / "canonical.csv"
    fieldnames = ("event_time", "available_time", "ingestion_time", "symbol", "close")
    origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with source_file.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for index in range(4):
            event = origin + timedelta(hours=index + 1)
            writer.writerow(
                {
                    "event_time": event.isoformat(),
                    "available_time": event.isoformat(),
                    "ingestion_time": event.isoformat(),
                    "symbol": "BTCEUR",
                    "close": "100",
                }
            )
    canonical_manifest = tmp_path / "canonical_snapshot.json"
    canonical_manifest.write_text(
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
    return materialize_holdout_partition(
        HoldoutPartitionConfig(
            run_id="manifested_experiment_pytest",
            source_snapshot_manifest=canonical_manifest,
            holdout_start_at=origin + timedelta(hours=3),
            output_dir=tmp_path / "partitions",
        )
    )
