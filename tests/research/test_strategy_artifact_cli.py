from __future__ import annotations

import json
import csv
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

import pytest

from autobot.v2 import cli
from autobot.v2.research.experiment_registry import ExperimentRegistry, ExperimentSpec
from autobot.v2.research.shadow_review_evidence import seal_shadow_review_evidence
from autobot.v2.research.canonical_feature_snapshot import (
    CanonicalFeatureSnapshotConfig,
    build_canonical_feature_snapshot,
)
from autobot.v2.research.manifested_experiment import load_feature_snapshot_provenance
from autobot.v2.research.shadow_governance import ShadowGovernanceError, StrategyArtifactRegistry
from autobot.v2.research.strategy_risk_mandates import load_strategy_risk_mandates


pytestmark = pytest.mark.unit


def _holdout_partition_fixture() -> dict[str, object]:
    return {
        "schema_version": 1,
        "partition_id": "holdout_cli_fixture",
        "fingerprint": "holdout-cli-fixture-fingerprint",
        "holdout_snapshot_id": "holdout-cli-review",
        "holdout_snapshot_fingerprint": "holdout-cli-review-fingerprint",
        "source_snapshot_id": "snapshot-cli",
        "source_snapshot_fingerprint": "snapshot-cli-fingerprint",
    }


def _holdout_provenance(
    experiment_id: str,
    *,
    feature_versions: dict[str, str],
    cost_model: dict[str, float],
) -> dict[str, object]:
    partition = _holdout_partition_fixture()
    identity = {
        "schema_version": 1,
        "experiment_id": experiment_id,
        "partition_id": partition["partition_id"],
        "partition_fingerprint": partition["fingerprint"],
        "holdout_snapshot_id": partition["holdout_snapshot_id"],
        "holdout_snapshot_fingerprint": partition["holdout_snapshot_fingerprint"],
        "source_snapshot_id": partition["source_snapshot_id"],
        "source_snapshot_fingerprint": partition["source_snapshot_fingerprint"],
        "code_commit": "pytest-commit",
        "feature_versions": feature_versions,
        "parameter_fingerprint": sha256(
            json.dumps({"threshold": 2.5}, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "cost_model_fingerprint": sha256(
            json.dumps(cost_model, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
    }
    return {
        **identity,
        "fingerprint": sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
    }


def _holdout_artifact_fixture(
    experiment_id: str,
    *,
    feature_versions: dict[str, str],
    cost_model: dict[str, float],
) -> dict[str, object]:
    return {
        "holdout_partition": _holdout_partition_fixture(),
        "role": "holdout_review",
        "result_fingerprint": "holdout-cli-final-result",
        "sha256": "holdout-cli-final-result-sha256",
        "data_root": "/sealed/holdout-cli",
        "shadow_review_evidence": seal_shadow_review_evidence(
            experiment_id=experiment_id,
            holdout_evaluation={
                "verdict": "HOLDOUT_PASSED_RESEARCH_ONLY",
                "blockers": [],
                "trade_count": 50,
                "net_pnl_eur": 3.0,
                "provenance": _holdout_provenance(
                    experiment_id,
                    feature_versions=feature_versions,
                    cost_model=cost_model,
                ),
                "research_only": True,
                "paper_capital_allowed": False,
                "live_allowed": False,
                "promotable": False,
            },
            statistical_gate_summary={
                "decision": "SHADOW_REVIEW_ELIGIBLE",
                "blockers": [],
                "shadow_review_eligible": True,
                "trade_count": 50,
                "trial_count": 8,
                "net_pnl_eur": 3.0,
                "out_of_sample_confirmed": True,
                "net_of_costs": True,
                "research_only": True,
                "paper_capital_allowed": False,
                "live_allowed": False,
                "promotable": False,
            },
        ),
    }


def _verified_feature_snapshot_evidence(root: Path) -> dict[str, object]:
    source = root / "canonical_source.csv"
    fields = (
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
        "open",
        "high",
        "low",
        "close",
        "volume",
    )
    origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index in range(25):
            event_time = origin + timedelta(minutes=index * 5)
            close = 100.0 + index
            writer.writerow(
                {
                    "exchange": "kraken",
                    "market_type": "spot",
                    "symbol": "BTCEUR",
                    "base_asset": "BTC",
                    "quote_asset": "EUR",
                    "market_mapping_status": "EXPLICIT",
                    "timeframe": "5m",
                    "event_time": event_time.isoformat(),
                    "available_time": event_time.isoformat(),
                    "ingestion_time": event_time.isoformat(),
                    "open": str(close - 0.5),
                    "high": str(close + 1.0),
                    "low": str(close - 1.0),
                    "close": str(close),
                    "volume": "100",
                }
            )
    source_manifest = root / "canonical_source.json"
    source_manifest.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "snapshot_id": "snapshot-pytest",
                "fingerprint": "source-fingerprint-cli-fixture",
                "market_type": "spot",
                "files": [{"csv_path": str(source)}],
            }
        ),
        encoding="utf-8",
    )
    snapshot = build_canonical_feature_snapshot(
        CanonicalFeatureSnapshotConfig(
            run_id="strategy_artifact_cli_fixture",
            canonical_manifest_path=source_manifest,
            output_dir=root / "features",
            manifest_dir=root / "feature_manifests",
        )
    )
    assert snapshot.status == "READY"
    return load_feature_snapshot_provenance(Path(str(snapshot.manifest_path))).to_dict()


def _passed_experiment(registry_path):
    registry = ExperimentRegistry(registry_path)
    feature_snapshot = _verified_feature_snapshot_evidence(Path(registry_path).parent)
    state = registry.register_experiment(
        ExperimentSpec(
            hypothesis_id="funding_basis",
            template_id="funding_extreme_reversion",
            thesis="Hermetic CLI governance test",
            code_commit="pytest-commit",
            image_ref="oci-revision:pytest-commit",
            data_snapshot_id="snapshot-pytest",
            feature_versions=feature_snapshot["feature_versions"],
            parameters={"threshold": 2.5},
            seed=7,
            cost_model={"fee_bps": 16.0, "slippage_bps": 9.0},
            environment={
                "mode": "research",
                "holdout_partition": _holdout_partition_fixture(),
                "feature_snapshot": feature_snapshot,
            },
            holdout_id="holdout_cli_fixture",
        )
    )
    registry.reserve_holdout(
        holdout_id="holdout_cli_fixture",
        data_snapshot_id="snapshot-pytest-holdout",
        immutable_fingerprint="holdout-cli-fixture-fingerprint",
        manifest={"partition": _holdout_partition_fixture()},
    )
    for stage in ("DATA_CHECK", "NET_SMOKE", "WALK_FORWARD", "STRESS_MONTE_CARLO"):
        state = registry.record_gate_result(experiment_id=state.experiment_id, stage=stage, status="PASSED")
    registry.record_final_holdout_review(
        experiment_id=state.experiment_id,
        metrics={"net_pnl_eur": 3.0, "profit_factor": 1.2},
        artifact=_holdout_artifact_fixture(
            state.experiment_id,
            feature_versions=dict(feature_snapshot["feature_versions"]),
            cost_model={"fee_bps": 16.0, "slippage_bps": 9.0},
        ),
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
