from __future__ import annotations

import ast
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
import sqlite3

import pytest

from autobot.v2.contracts import TargetPortfolio
from autobot.v2.research.experiment_registry import ExperimentRegistry, ExperimentSpec
from autobot.v2.research.shadow_governance import (
    ShadowGovernanceError,
    ShadowObservation,
    ShadowPerformanceWindow,
    StrategyArtifactRegistry,
    StrategyArtifact,
    apply_shadow_safety,
    build_strategy_artifact_from_experiment,
    decide_shadow_safety,
    evaluate_shadow_parity,
    feature_snapshot_reference_from_mapping,
    strategy_artifact_reference_from_mapping,
)


pytestmark = pytest.mark.unit


def _artifact(*, status: str = "SHADOW") -> StrategyArtifact:
    return StrategyArtifact(
        strategy_id="funding_basis",
        strategy_version="v1",
        code_commit="ee62e17",
        data_snapshot_id="snapshot-1",
        feature_versions={"basis_bps": "1.0.0"},
        parameters={"threshold": 2.5},
        risk_mandate_fingerprint="mandate-1",
        validation_manifest_fingerprint="validation-1",
        feature_snapshots=(_feature_snapshot(),),
        status=status,
        experiment_id="exp_fixture",
        experiment_fingerprint="fixture-fingerprint",
        human_approval_reference="test-approval-reference",
    )


def _feature_snapshot_evidence() -> dict[str, object]:
    return {
        "feature_snapshot_id": "features_fixture",
        "feature_snapshot_fingerprint": "feature-fingerprint-fixture",
        "snapshot_kind": "FEATURE_SNAPSHOT",
        "source_snapshot_id": "snapshot-1",
        "source_snapshot_fingerprint": "source-fingerprint-fixture",
        "feature_registry_fingerprint": "registry-fingerprint-fixture",
        "feature_versions": {"basis_bps": "1.0.0"},
        "feature_count": 20,
        "parity_ok": True,
        "runtime_parity_proven": True,
        "ingestion_time_unknown_count": 0,
    }


def _feature_snapshot():
    return feature_snapshot_reference_from_mapping(_feature_snapshot_evidence())


def _experiment_spec() -> ExperimentSpec:
    return ExperimentSpec(
        hypothesis_id="funding_basis",
        template_id="funding_extreme_reversion",
        thesis="funding-basis hypothesis for a hermetic shadow-governance test",
        code_commit="ee62e17",
        data_snapshot_id="snapshot-1",
        feature_versions={"basis_bps": "1.0.0"},
        parameters={"threshold": 2.5},
        seed=42,
        cost_model={"fee_bps": 16.0, "slippage_bps": 9.0},
        environment={"mode": "research", "feature_snapshot": _feature_snapshot_evidence()},
    )


def _passed_experiment_registry(tmp_path) -> tuple[ExperimentRegistry, str]:
    registry = ExperimentRegistry(tmp_path / "experiment_registry.sqlite3")
    state = registry.register_experiment(_experiment_spec())
    for stage in ("DATA_CHECK", "NET_SMOKE", "WALK_FORWARD", "STRESS_MONTE_CARLO", "SHADOW_REVIEW"):
        state = registry.record_gate_result(experiment_id=state.experiment_id, stage=stage, status="PASSED")
    assert state.terminal is True
    return registry, state.experiment_id


def _target(*, decision_id: str = "decision-1", weight: float = 0.20) -> TargetPortfolio:
    return TargetPortfolio(
        decision_id=decision_id,
        generated_at=datetime(2026, 7, 11, 12, tzinfo=timezone.utc),
        target_weights={"BTCEUR": weight},
        reserve_cash_weight=1.0 - weight,
        rationale={"BTCEUR": "research_only"},
    )


def _observation(artifact: StrategyArtifact, *, target: TargetPortfolio | None = None, seconds: int = 0) -> ShadowObservation:
    timestamp = datetime(2026, 7, 11, 12, tzinfo=timezone.utc) + timedelta(seconds=seconds)
    return ShadowObservation(
        artifact_id=artifact.artifact_id,
        observed_at=timestamp,
        data_available_at=timestamp,
        source_snapshot_id="snapshot-1",
        feature_fingerprint="feature-fingerprint-1",
        target_portfolio=target or _target(),
    )


def test_strategy_artifact_keeps_grid_retired_and_cannot_enable_paper_or_live():
    with pytest.raises(ShadowGovernanceError, match="grid aliases"):
        StrategyArtifact(
            strategy_id="dynamic_grid",
            strategy_version="v1",
            code_commit="commit",
            data_snapshot_id="snapshot",
            feature_versions={},
            parameters={},
            risk_mandate_fingerprint="mandate",
            validation_manifest_fingerprint="validation",
            status="SHADOW",
        )
    with pytest.raises(ShadowGovernanceError, match="cannot permit"):
        StrategyArtifact(
            strategy_id="trend_momentum",
            strategy_version="v1",
            code_commit="commit",
            data_snapshot_id="snapshot",
            feature_versions={},
            parameters={},
            risk_mandate_fingerprint="mandate",
            validation_manifest_fingerprint="validation",
            paper_capital_allowed=True,
        )


def test_strategy_artifact_binds_data_snapshot_to_feature_evidence():
    with pytest.raises(ShadowGovernanceError, match="must match artifact data_snapshot_id"):
        replace(_artifact(), data_snapshot_id="unrelated-snapshot")

    derivatives = feature_snapshot_reference_from_mapping(
        {
            "feature_snapshot_id": "derivatives_features_fixture",
            "fingerprint": "derivatives-feature-fingerprint-fixture",
            "snapshot_kind": "DERIVATIVES_POINT_IN_TIME",
            "source_snapshot_id": "derivatives-snapshot-1",
            "source_snapshot_fingerprint": "derivatives-source-fingerprint-fixture",
            "feature_registry_fingerprint": "registry-fingerprint-fixture",
            "feature_versions": {"funding_rate_relative": "1.0.0"},
            "feature_count": 20,
            "parity_ok": True,
            "runtime_parity_proven": True,
            "ingestion_time_unknown_count": 0,
        }
    )
    combined_snapshot_id = "combined_" + sha256(
        b'{"derivatives":"derivatives-snapshot-1","spot":"snapshot-1"}'
    ).hexdigest()[:16]
    combined = StrategyArtifact(
        strategy_id="funding_basis",
        strategy_version="v2",
        code_commit="ee62e17",
        data_snapshot_id=combined_snapshot_id,
        feature_versions={"basis_bps": "1.0.0", "funding_rate_relative": "1.0.0"},
        parameters={"threshold": 2.5},
        risk_mandate_fingerprint="mandate-1",
        validation_manifest_fingerprint="validation-1",
        feature_snapshots=(_feature_snapshot(), derivatives),
    )

    assert combined.data_snapshot_id == combined_snapshot_id


def test_shadow_artifact_requires_an_experiment_binding_and_human_approval():
    kwargs = {
        "strategy_id": "funding_basis",
        "strategy_version": "v1",
        "code_commit": "ee62e17",
        "data_snapshot_id": "snapshot-1",
        "feature_versions": {"basis_bps": "1.0.0"},
        "parameters": {"threshold": 2.5},
        "risk_mandate_fingerprint": "mandate-1",
        "validation_manifest_fingerprint": "validation-1",
        "feature_snapshots": (_feature_snapshot(),),
        "status": "SHADOW",
    }

    with pytest.raises(ShadowGovernanceError, match="requires an experiment binding"):
        StrategyArtifact(**kwargs)
    with pytest.raises(ShadowGovernanceError, match="supplied together"):
        StrategyArtifact(**kwargs, experiment_id="exp_only")
    with pytest.raises(ShadowGovernanceError, match="explicit human approval"):
        StrategyArtifact(
            **kwargs,
            experiment_id="exp_fixture",
            experiment_fingerprint="fixture-fingerprint",
        )


def test_shadow_artifact_factory_requires_passed_terminal_evidence_and_human_approval(tmp_path):
    registry = ExperimentRegistry(tmp_path / "unpassed_experiments.sqlite3")
    unpassed = registry.register_experiment(_experiment_spec())

    with pytest.raises(ShadowGovernanceError, match="passed terminal SHADOW_REVIEW"):
        build_strategy_artifact_from_experiment(
            experiment_registry=registry,
            experiment_id=unpassed.experiment_id,
            strategy_version="v1",
            risk_mandate_fingerprint="mandate-1",
            validation_manifest_fingerprint="validation-1",
            requested_status="SHADOW",
            human_approval_reference="human-review-1",
        )

    passed_registry, experiment_id = _passed_experiment_registry(tmp_path)
    with pytest.raises(ShadowGovernanceError, match="explicit human approval"):
        build_strategy_artifact_from_experiment(
            experiment_registry=passed_registry,
            experiment_id=experiment_id,
            strategy_version="v1",
            risk_mandate_fingerprint="mandate-1",
            validation_manifest_fingerprint="validation-1",
            requested_status="SHADOW",
        )


def test_shadow_artifact_factory_refuses_experiment_without_point_in_time_feature_evidence(tmp_path):
    registry = ExperimentRegistry(tmp_path / "legacy_experiments.sqlite3")
    state = registry.register_experiment(
        ExperimentSpec(
            hypothesis_id="funding_basis",
            template_id="funding_extreme_reversion",
            thesis="legacy evidence cannot create a shadow artifact",
            code_commit="ee62e17",
            data_snapshot_id="snapshot-1",
            feature_versions={"basis_bps": "1.0.0"},
            parameters={"threshold": 2.5},
            seed=42,
            cost_model={"fee_bps": 16.0},
            environment={"mode": "research"},
        )
    )
    for stage in ("DATA_CHECK", "NET_SMOKE", "WALK_FORWARD", "STRESS_MONTE_CARLO", "SHADOW_REVIEW"):
        state = registry.record_gate_result(experiment_id=state.experiment_id, stage=stage, status="PASSED")

    with pytest.raises(ShadowGovernanceError, match="point-in-time feature snapshot evidence"):
        build_strategy_artifact_from_experiment(
            experiment_registry=registry,
            experiment_id=state.experiment_id,
            strategy_version="v1",
            risk_mandate_fingerprint="mandate-1",
            validation_manifest_fingerprint="validation-1",
            requested_status="SHADOW_ELIGIBLE",
            human_approval_reference="human-review-1",
        )


def test_shadow_parity_requires_matching_artifact_snapshot_features_and_target():
    artifact = _artifact()
    batch = _observation(artifact)
    matching = _observation(artifact, seconds=1)
    mismatched = _observation(artifact, target=_target(decision_id="decision-2", weight=0.30))

    ok = evaluate_shadow_parity(artifact=artifact, batch_observation=batch, shadow_observation=matching)
    blocked = evaluate_shadow_parity(artifact=artifact, batch_observation=batch, shadow_observation=mismatched)

    assert ok.status == "PARITY_OK"
    assert blocked.status == "PARITY_BLOCKED"
    assert "target_portfolio_mismatch" in blocked.reasons
    assert ok.paper_capital_allowed is False
    assert ok.live_allowed is False


def test_shadow_safety_only_escalates_risk_reduction_and_cannot_start_shadow():
    normal = ShadowPerformanceWindow(
        trade_count=5,
        rolling_profit_factor=1.4,
        rolling_expectancy_eur=0.1,
        max_drawdown_pct=1.0,
        feature_drift_score=0.05,
        cost_drift_bps=0.0,
        data_age=timedelta(seconds=10),
    )
    severe = ShadowPerformanceWindow(
        trade_count=60,
        rolling_profit_factor=0.75,
        rolling_expectancy_eur=-0.2,
        max_drawdown_pct=30.0,
        feature_drift_score=0.90,
        cost_drift_bps=10.0,
        data_age=timedelta(minutes=10),
    )

    watch = decide_shadow_safety(normal, previous_action="DISABLE_NEW_ENTRIES")
    quarantine = decide_shadow_safety(severe)
    research_artifact = _artifact(status="RESEARCH")
    shadow_artifact = _artifact(status="SHADOW")

    assert watch.action == "DISABLE_NEW_ENTRIES"
    assert quarantine.action == "QUARANTINE"
    assert apply_shadow_safety(research_artifact, watch).status == "RESEARCH"
    assert apply_shadow_safety(shadow_artifact, quarantine).status == "QUARANTINED"
    assert quarantine.risk_increase_allowed is False
    assert quarantine.paper_capital_allowed is False
    assert quarantine.live_allowed is False


def test_strategy_artifact_registry_is_append_only_and_refuses_safety_relaxation(tmp_path):
    experiment_registry, experiment_id = _passed_experiment_registry(tmp_path)
    artifact = build_strategy_artifact_from_experiment(
        experiment_registry=experiment_registry,
        experiment_id=experiment_id,
        strategy_version="v1",
        risk_mandate_fingerprint="mandate-1",
        validation_manifest_fingerprint="validation-1",
        requested_status="SHADOW",
        human_approval_reference="human-review-1",
    )
    registry = StrategyArtifactRegistry(
        tmp_path / "strategy_artifacts.sqlite3",
        experiment_registry_path=experiment_registry.path,
    )
    severe = ShadowPerformanceWindow(
        trade_count=60,
        rolling_profit_factor=0.75,
        rolling_expectancy_eur=-0.2,
        max_drawdown_pct=30.0,
        feature_drift_score=0.90,
        cost_drift_bps=10.0,
        data_age=timedelta(minutes=10),
    )
    quarantine = decide_shadow_safety(severe)
    normal = decide_shadow_safety(
        ShadowPerformanceWindow(60, 1.4, 0.1, 1.0, 0.05, 0.0, timedelta(seconds=1))
    )

    artifact_id = registry.register(artifact)
    assert registry.register(artifact) == artifact_id
    assert registry.record_safety_decision(artifact, quarantine) is True
    assert registry.record_safety_decision(artifact, quarantine) is False
    assert registry.latest_action(artifact_id) == "QUARANTINE"
    with pytest.raises(ShadowGovernanceError, match="cannot relax"):
        registry.record_safety_decision(artifact, normal)
    with sqlite3.connect(tmp_path / "strategy_artifacts.sqlite3") as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("DELETE FROM strategy_safety_events")


def test_strategy_artifact_registry_rejects_a_mismatched_experiment_fingerprint(tmp_path):
    experiment_registry, experiment_id = _passed_experiment_registry(tmp_path)
    artifact = build_strategy_artifact_from_experiment(
        experiment_registry=experiment_registry,
        experiment_id=experiment_id,
        strategy_version="v1",
        risk_mandate_fingerprint="mandate-1",
        validation_manifest_fingerprint="validation-1",
        requested_status="SHADOW_ELIGIBLE",
        human_approval_reference="human-review-1",
    )
    mismatched = replace(artifact, experiment_fingerprint="tampered-fingerprint")
    registry = StrategyArtifactRegistry(
        tmp_path / "strategy_artifacts.sqlite3",
        experiment_registry_path=experiment_registry.path,
    )

    with pytest.raises(ShadowGovernanceError, match="fingerprint mismatch"):
        registry.register(mismatched)


def test_strategy_artifact_reference_requires_a_self_consistent_serialized_artifact():
    artifact = _artifact()
    reference = strategy_artifact_reference_from_mapping(artifact.to_dict())

    assert reference.artifact_id == artifact.artifact_id
    assert reference.fingerprint == artifact.fingerprint
    assert reference.strategy_version == artifact.strategy_version

    tampered = artifact.to_dict()
    tampered["fingerprint"] = "tampered"
    with pytest.raises(ShadowGovernanceError, match="fingerprint_mismatch"):
        strategy_artifact_reference_from_mapping(tampered)


def test_strategy_artifact_registry_resolves_only_registered_shadow_references_read_only(tmp_path):
    experiment_registry, experiment_id = _passed_experiment_registry(tmp_path)
    artifact = build_strategy_artifact_from_experiment(
        experiment_registry=experiment_registry,
        experiment_id=experiment_id,
        strategy_version="v1",
        risk_mandate_fingerprint="mandate-1",
        validation_manifest_fingerprint="validation-1",
        requested_status="SHADOW_ELIGIBLE",
        human_approval_reference="human-review-1",
    )
    path = tmp_path / "strategy_artifacts.sqlite3"
    registry = StrategyArtifactRegistry(path, experiment_registry_path=experiment_registry.path)
    artifact_id = registry.register(artifact)
    before = sha256(path.read_bytes()).hexdigest()

    reference = registry.resolve_shadow_order_intent_reference(artifact_id)

    assert reference.artifact_id == artifact_id
    assert reference.fingerprint == artifact.fingerprint
    assert reference.feature_snapshots[0].feature_snapshot_id == "features_fixture"
    assert sha256(path.read_bytes()).hexdigest() == before
    with pytest.raises(ShadowGovernanceError, match="unknown strategy artifact"):
        registry.resolve_shadow_order_intent_reference("unknown")

    research_artifact_id = registry.register(_artifact(status="RESEARCH"))
    with pytest.raises(ShadowGovernanceError, match="not eligible"):
        registry.resolve_shadow_order_intent_reference(research_artifact_id)


def test_shadow_governance_module_does_not_import_runtime_execution_paths():
    root = Path(__file__).resolve().parents[2]
    tree = ast.parse((root / "src/autobot/v2/research/shadow_governance.py").read_text(encoding="utf-8"))
    forbidden = {"autobot.v2.order_router", "autobot.v2.signal_handler_async", "autobot.v2.paper_trading"}
    imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imports.update(node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module)
    assert imports.isdisjoint(forbidden)


def test_feature_snapshot_reference_rejects_unproven_runtime_parity():
    evidence = _feature_snapshot_evidence()
    evidence["runtime_parity_proven"] = False

    with pytest.raises(ShadowGovernanceError, match="feature_snapshot_reference_invalid"):
        feature_snapshot_reference_from_mapping(evidence)
