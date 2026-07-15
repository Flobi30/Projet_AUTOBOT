from __future__ import annotations

import json

import pytest

from autobot.v2 import cli
from autobot.v2.research.experiment_registry import ExperimentRegistry, ExperimentSpec
from autobot.v2.research.shadow_governance import ShadowGovernanceError, StrategyArtifactRegistry


pytestmark = pytest.mark.unit


def _passed_experiment(registry_path):
    registry = ExperimentRegistry(registry_path)
    state = registry.register_experiment(
        ExperimentSpec(
            hypothesis_id="funding_basis",
            template_id="funding_extreme_reversion",
            thesis="Hermetic CLI governance test",
            code_commit="pytest-commit",
            data_snapshot_id="snapshot-pytest",
            feature_versions={"basis_bps": "1.0.0"},
            parameters={"threshold": 2.5},
            seed=7,
            cost_model={"fee_bps": 16.0, "slippage_bps": 9.0},
            environment={"mode": "research"},
        )
    )
    for stage in ("DATA_CHECK", "NET_SMOKE", "WALK_FORWARD", "STRESS_MONTE_CARLO", "SHADOW_REVIEW"):
        state = registry.record_gate_result(experiment_id=state.experiment_id, stage=stage, status="PASSED")
    return registry, state


def test_strategy_artifact_cli_registers_only_bound_non_executable_shadow_artifacts(tmp_path, capsys):
    experiment_registry, state = _passed_experiment(tmp_path / "experiments.sqlite3")
    artifact_path = tmp_path / "artifacts.sqlite3"

    exit_code = cli.main(
        [
            "strategy-artifact-register",
            "--experiment-registry-path",
            str(experiment_registry.path),
            "--artifact-registry-path",
            str(artifact_path),
            "--experiment-id",
            state.experiment_id,
            "--strategy-version",
            "v1",
            "--risk-mandate-fingerprint",
            "mandate-pytest",
            "--validation-manifest-fingerprint",
            "validation-pytest",
            "--status",
            "SHADOW_ELIGIBLE",
            "--human-approval-reference",
            "human-review-pytest-1",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["artifact"]["status"] == "SHADOW_ELIGIBLE"
    assert payload["artifact"]["experiment_fingerprint"] == state.material_fingerprint
    assert payload["shadow_runtime_started"] is False
    assert payload["paper_capital_allowed"] is False
    assert payload["live_allowed"] is False
    assert StrategyArtifactRegistry(
        artifact_path,
        experiment_registry_path=experiment_registry.path,
    ).export_manifest(payload["artifact_id"])["artifact"]["human_approval_reference"] == "human-review-pytest-1"

    exit_code = cli.main(
        [
            "strategy-artifact-resolve-reference",
            "--artifact-registry-path",
            str(artifact_path),
            "--artifact-id",
            payload["artifact_id"],
        ]
    )
    resolved = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert resolved["strategy_artifact_reference"]["artifact_id"] == payload["artifact_id"]
    assert resolved["shadow_runtime_started"] is False
    assert resolved["paper_capital_allowed"] is False
    assert resolved["live_allowed"] is False


def test_strategy_artifact_cli_requires_human_reference_for_shadow_status(tmp_path):
    experiment_registry, state = _passed_experiment(tmp_path / "experiments.sqlite3")

    with pytest.raises(ShadowGovernanceError, match="explicit human approval"):
        cli.main(
            [
                "strategy-artifact-register",
                "--experiment-registry-path",
                str(experiment_registry.path),
                "--artifact-registry-path",
                str(tmp_path / "artifacts.sqlite3"),
                "--experiment-id",
                state.experiment_id,
                "--strategy-version",
                "v1",
                "--risk-mandate-fingerprint",
                "mandate-pytest",
                "--validation-manifest-fingerprint",
                "validation-pytest",
                "--status",
                "SHADOW",
            ]
        )
