from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3

import pytest

from autobot.v2.contracts import TargetPortfolio
from autobot.v2.research.shadow_governance import (
    ShadowGovernanceError,
    ShadowObservation,
    ShadowPerformanceWindow,
    StrategyArtifactRegistry,
    StrategyArtifact,
    apply_shadow_safety,
    decide_shadow_safety,
    evaluate_shadow_parity,
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
        status=status,
    )


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
    artifact = _artifact()
    registry = StrategyArtifactRegistry(tmp_path / "strategy_artifacts.sqlite3")
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


def test_shadow_governance_module_does_not_import_runtime_execution_paths():
    root = Path(__file__).resolve().parents[2]
    tree = ast.parse((root / "src/autobot/v2/research/shadow_governance.py").read_text(encoding="utf-8"))
    forbidden = {"autobot.v2.order_router", "autobot.v2.signal_handler_async", "autobot.v2.paper_trading"}
    imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imports.update(node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module)
    assert imports.isdisjoint(forbidden)
