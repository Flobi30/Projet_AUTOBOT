from __future__ import annotations

import json

import pytest

from autobot.v2 import cli
from autobot.v2.research.experiment_registry import ExperimentRegistry, ExperimentSpec
from autobot.v2.research.shadow_governance import ShadowGovernanceError, StrategyArtifactRegistry
from autobot.v2.research.strategy_risk_mandates import load_strategy_risk_mandates


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
            environment={
                "mode": "research",
                "feature_snapshot": {
                    "feature_snapshot_id": "features_cli_fixture",
                    "feature_snapshot_fingerprint": "feature-fingerprint-cli-fixture",
                    "snapshot_kind": "FEATURE_SNAPSHOT",
                    "source_snapshot_id": "snapshot-pytest",
                    "source_snapshot_fingerprint": "source-fingerprint-cli-fixture",
                    "feature_registry_fingerprint": "registry-fingerprint-cli-fixture",
                    "feature_versions": {"basis_bps": "1.0.0"},
                    "feature_count": 20,
                    "parity_ok": True,
                    "runtime_parity_proven": True,
                    "ingestion_time_unknown_count": 0,
                },
            },
            holdout_id="holdout_cli_fixture",
        )
    )
    registry.reserve_holdout(
        holdout_id="holdout_cli_fixture",
        data_snapshot_id="snapshot-pytest-holdout",
        immutable_fingerprint="holdout-cli-fixture-fingerprint",
    )
    for stage in ("DATA_CHECK", "NET_SMOKE", "WALK_FORWARD", "STRESS_MONTE_CARLO"):
        state = registry.record_gate_result(experiment_id=state.experiment_id, stage=stage, status="PASSED")
    registry.record_final_holdout_review(
        experiment_id=state.experiment_id,
        metrics={"net_pnl_eur": 3.0, "profit_factor": 1.2},
    )
    state = registry.record_gate_result(experiment_id=state.experiment_id, stage="SHADOW_REVIEW", status="PASSED")
    return registry, state


def _risk_mandate_args(tmp_path):
    path = tmp_path / "mandates.json"
    path.write_text(
        json.dumps(
            {
                "mandates": [
                    {
                        "mandate_id": "funding_basis_shadow_mandate",
                        "strategy_id": "funding_basis",
                        "mode_allowed": "shadow",
                        "capital_max_eur": 0.0,
                        "max_daily_loss_eur": 0.0,
                        "max_drawdown_pct": 0.0,
                        "max_position_eur": 0.0,
                        "max_symbol_exposure_eur": 0.0,
                        "max_total_exposure_eur": 0.0,
                        "max_trades_per_day": 0,
                        "max_orders_per_minute": 0,
                        "max_fees_per_day_eur": 0.0,
                        "max_slippage_bps": 0.0,
                        "max_spread_bps": 0.0,
                        "allowed_symbols": [],
                        "allowed_timeframes": [],
                        "allowed_order_types": [],
                        "cooldown_after_losses": 0,
                        "rolling_pf_min": 1.0,
                        "rolling_expectancy_min": 0.0,
                        "min_edge_to_cost_ratio": 1.0,
                        "data_freshness_max_seconds": 1,
                        "expires_at": "2026-12-31T23:59:59+00:00",
                        "human_approved_required_for_risk_increase": True,
                        "paper_capital_allowed": False,
                        "live_allowed": False,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    mandate = load_strategy_risk_mandates(path)["funding_basis"]
    return path, mandate.mandate_id, mandate.fingerprint


def test_strategy_artifact_cli_registers_only_bound_non_executable_shadow_artifacts(tmp_path, capsys):
    experiment_registry, state = _passed_experiment(tmp_path / "experiments.sqlite3")
    artifact_path = tmp_path / "artifacts.sqlite3"
    mandates_path, mandate_id, mandate_fingerprint = _risk_mandate_args(tmp_path)

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
            mandate_fingerprint,
            "--risk-mandates",
            str(mandates_path),
            "--risk-mandate-id",
            mandate_id,
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
    assert payload["artifact"]["risk_mandate"]["fingerprint"] == mandate_fingerprint
    assert payload["risk_mandate_id"] == mandate_id
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
    mandates_path, mandate_id, mandate_fingerprint = _risk_mandate_args(tmp_path)

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
                mandate_fingerprint,
                "--risk-mandates",
                str(mandates_path),
                "--risk-mandate-id",
                mandate_id,
                "--validation-manifest-fingerprint",
                "validation-pytest",
                "--status",
                "SHADOW",
            ]
        )


def test_strategy_artifact_cli_rejects_caller_supplied_mandate_fingerprint_mismatch(tmp_path):
    experiment_registry, state = _passed_experiment(tmp_path / "experiments.sqlite3")
    mandates_path, mandate_id, _ = _risk_mandate_args(tmp_path)

    with pytest.raises(ValueError, match="does not match immutable mandate evidence"):
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
                "caller-supplied-mismatch",
                "--risk-mandates",
                str(mandates_path),
                "--risk-mandate-id",
                mandate_id,
                "--validation-manifest-fingerprint",
                "validation-pytest",
                "--status",
                "SHADOW_ELIGIBLE",
                "--human-approval-reference",
                "human-review-pytest-1",
            ]
        )
