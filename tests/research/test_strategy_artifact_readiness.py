import ast
from pathlib import Path
import sqlite3

import pytest

from autobot.v2.research.strategy_artifact_readiness import (
    audit_strategy_artifact_readiness,
    audit_strategy_artifact_readiness_snapshot,
)


pytestmark = pytest.mark.unit


def _create_registry(path, *, campaign_column: bool = True):
    campaign = ", research_campaign_id TEXT" if campaign_column else ""
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE experiments (experiment_id TEXT PRIMARY KEY, hypothesis_id TEXT, template_id TEXT, created_at TEXT, spec_json TEXT"
            + campaign
            + ")"
        )
        connection.execute(
            "CREATE TABLE experiment_trials (trial_id TEXT PRIMARY KEY, experiment_id TEXT, dimension TEXT, uses_holdout INTEGER, optimization INTEGER)"
        )
        connection.execute(
            "CREATE TABLE experiment_transitions (transition_id TEXT PRIMARY KEY, experiment_id TEXT, stage TEXT, status TEXT, recorded_at TEXT)"
        )


def test_missing_registry_is_reported_without_creating_database(tmp_path):
    path = tmp_path / "missing.sqlite3"

    audit = audit_strategy_artifact_readiness(path)

    assert audit.status == "REGISTRY_MISSING"
    assert audit.schema_status == "REGISTRY_MISSING"
    assert audit.schema_blockers == ("experiment_registry_missing",)
    assert path.exists() is False
    assert audit.shadow_runtime_started is False
    assert audit.paper_capital_allowed is False
    assert audit.live_allowed is False


def test_legacy_schema_is_a_read_only_migration_blocker(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    _create_registry(path, campaign_column=False)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO experiments VALUES (?, ?, ?, ?, ?)",
            ("exp_legacy", "funding_basis", "basis", "2026-07-22T10:00:00+00:00", "{}"),
        )
        connection.execute(
            "INSERT INTO experiment_transitions VALUES (?, ?, ?, ?, ?)",
            ("transition_legacy", "exp_legacy", "NET_SMOKE", "REJECTED", "2026-07-22T10:01:00+00:00"),
        )

    audit = audit_strategy_artifact_readiness(path)

    assert audit.status == "SCHEMA_MIGRATION_REQUIRED"
    assert audit.schema_status == "LEGACY_SCHEMA"
    assert "missing_column:experiments.research_campaign_id" in audit.schema_blockers
    assert audit.candidates[0].state == "REJECTED"
    assert "missing_column:experiments.research_campaign_id" in audit.candidates[0].blockers


def test_unreadable_registry_fails_closed_without_creating_an_artifact_registry(tmp_path):
    registry_path = tmp_path / "invalid.sqlite3"
    registry_path.write_text("not a sqlite database", encoding="utf-8")
    artifact_registry_path = tmp_path / "artifacts.sqlite3"

    audit = audit_strategy_artifact_readiness(registry_path, artifact_registry_path=artifact_registry_path)

    assert audit.status == "REGISTRY_UNAVAILABLE"
    assert audit.schema_blockers == ("experiment_registry_read_only_open_failed",)
    assert artifact_registry_path.exists() is False


def test_passed_final_holdout_is_evidence_ready_but_not_authorized(tmp_path):
    path = tmp_path / "current.sqlite3"
    _create_registry(path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO experiments VALUES (?, ?, ?, ?, ?, ?)",
            ("exp_ready", "trend_momentum", "trend", "2026-07-22T10:00:00+00:00", "{}", "trend-v1"),
        )
        connection.execute(
            "INSERT INTO experiment_transitions VALUES (?, ?, ?, ?, ?)",
            ("transition_ready", "exp_ready", "SHADOW_REVIEW", "PASSED", "2026-07-22T10:01:00+00:00"),
        )
        connection.execute(
            "INSERT INTO experiment_trials VALUES (?, ?, ?, ?, ?)",
            ("trial_holdout", "exp_ready", "final_holdout_review", 1, 0),
        )

    audit = audit_strategy_artifact_readiness(path)
    candidate = audit.candidates[0]

    assert audit.status == "HUMAN_GOVERNANCE_REQUIRED"
    assert audit.artifact_registration_ready_count == 1
    assert candidate.state == "EVIDENCE_READY_HUMAN_GOVERNANCE_REQUIRED"
    assert candidate.artifact_registration_ready is True
    assert "explicit_human_approval_reference_required" in candidate.blockers
    assert "immutable_shadow_risk_mandate_required" in candidate.blockers
    assert candidate.paper_capital_allowed is False
    assert candidate.live_allowed is False
    assert audit.order_created is False


def test_snapshot_audit_reads_a_verified_wal_snapshot_and_preserves_live_source(tmp_path):
    registry_path = tmp_path / "live_registry.sqlite3"
    _create_registry(registry_path)
    with sqlite3.connect(registry_path) as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA wal_autocheckpoint = 0")
        connection.execute(
            "INSERT INTO experiments VALUES (?, ?, ?, ?, ?, ?)",
            ("exp_shadow", "trend_momentum", "trend", "2026-07-22T10:00:00+00:00", "{}", "campaign-a"),
        )
        connection.execute(
            "INSERT INTO experiment_transitions VALUES (?, ?, ?, ?, ?)",
            ("transition_shadow", "exp_shadow", "NET_SMOKE", "REJECTED", "2026-07-22T10:01:00+00:00"),
        )
        connection.commit()

        source_before = registry_path.read_bytes()
        audit = audit_strategy_artifact_readiness_snapshot(
            registry_path,
            artifact_registry_path=tmp_path / "missing_artifacts.sqlite3",
        )

        assert audit.status == "NO_SHADOW_ARTIFACT_CANDIDATE"
        assert audit.readiness is not None
        assert audit.readiness.candidates[0].state == "REJECTED"
        assert audit.registry_path == str(registry_path.resolve())
        assert audit.registry_snapshot is not None
        assert audit.registry_snapshot.integrity_check.lower() == "ok"
        assert audit.registry_snapshot.source_changed_during_snapshot is False
        assert audit.temporary_snapshots_cleaned is True
        assert registry_path.read_bytes() == source_before
        assert (tmp_path / "missing_artifacts.sqlite3").exists() is False
        assert audit.shadow_runtime_started is False
        assert audit.paper_capital_allowed is False
        assert audit.live_allowed is False
        assert audit.order_created is False


def test_snapshot_audit_fails_closed_for_an_unreadable_live_source(tmp_path):
    registry_path = tmp_path / "invalid.sqlite3"
    registry_path.write_text("not a sqlite database", encoding="utf-8")

    audit = audit_strategy_artifact_readiness_snapshot(registry_path)

    assert audit.status == "SNAPSHOT_UNAVAILABLE"
    assert audit.readiness is None
    assert audit.blocker is not None
    assert audit.blocker.startswith("verified_snapshot_failed:")
    assert audit.temporary_snapshots_cleaned is True
    assert audit.shadow_runtime_started is False
    assert audit.paper_capital_allowed is False
    assert audit.live_allowed is False
    assert audit.order_created is False


def test_readiness_audit_has_no_execution_or_runtime_imports():
    module_path = Path(__file__).resolve().parents[2] / "src/autobot/v2/research/strategy_artifact_readiness.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    forbidden = {"order_router", "paper_trading", "signal_handler_async", "orchestrator_async", "kraken_client"}
    imports = {
        alias.name.split(".")[-1]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imports.update(
        node.module.split(".")[-1]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )
    assert forbidden.isdisjoint(imports)
