from __future__ import annotations

import json

import pytest

from autobot.v2.research.manifested_experiment import (
    ManifestedExperimentError,
    build_manifested_experiment_spec,
    load_feature_snapshot_provenance,
)


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


def test_manifested_experiment_binds_all_feature_and_source_fingerprints(tmp_path):
    spec, provenance = build_manifested_experiment_spec(
        hypothesis_id="long_trend",
        template_id="regime_filtered_trend",
        thesis="test thesis",
        code_commit="abc123",
        feature_snapshot_manifest=_manifest(tmp_path),
        parameters={"lookback": 24},
        seed=7,
        cost_model={"profile": "research_stress"},
    )

    assert spec.data_snapshot_id == "ohlcv_v2_test"
    assert spec.feature_versions == {"momentum_3_bps": "1.0.0"}
    assert spec.environment["feature_snapshot"]["feature_snapshot_id"] == "features_v1_test"
    assert spec.environment["runtime_parity_proven"] is False
    assert provenance.runtime_parity_proven is False


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
            feature_snapshot_manifest=_manifest(tmp_path),
            parameters={},
            seed=7,
            cost_model={},
            environment={"live_allowed": True},
        )
