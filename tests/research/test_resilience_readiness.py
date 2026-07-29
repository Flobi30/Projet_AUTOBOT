from __future__ import annotations

import ast
from contextlib import closing
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

import pytest

from autobot.v2.research.resilience_readiness import (
    FailClosedRecoveryPlan,
    FailClosedIncidentSummary,
    IncidentDecision,
    PaperReadinessDossier,
    ResilienceError,
    RetryPolicy,
    RuntimeDeploymentEvidence,
    audit_sqlite_backup_scope,
    build_readiness_dossier_from_coverage,
    create_verified_sqlite_backup_bundle,
    create_verified_sqlite_backup,
    decide_fail_closed,
    evaluate_human_paper_readiness,
    load_runtime_deployment_evidence,
    plan_fail_closed_recovery,
    retry_bounded,
    runtime_deployment_evidence_from_mapping,
    run_fail_closed_drill,
    run_ephemeral_sqlite_restore_drill,
    summarize_fail_closed_incidents,
    verify_sqlite_backup_bundle_restore_drill,
    verify_sqlite_restore_drill,
    write_readiness_dossier,
)


pytestmark = pytest.mark.unit


def _write_sqlite(path: Path, *, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("CREATE TABLE evidence (id INTEGER PRIMARY KEY, value TEXT)")
        connection.execute("INSERT INTO evidence(value) VALUES (?)", (value,))
        connection.commit()


def _backup_scope_repo(tmp_path: Path, *, include_optional: bool = False) -> Path:
    repo = tmp_path / "repo"
    _write_sqlite(repo / "data" / "autobot_state.db", value="runtime")
    _write_sqlite(repo / "data" / "global_kill_switch.db", value="kill-switch")
    if include_optional:
        _write_sqlite(repo / "data" / "research" / "experiment_registry.sqlite3", value="experiments")
        _write_sqlite(repo / "data" / "research" / "strategy_artifacts.sqlite3", value="artifacts")
    return repo


def _deployment_evidence(*, observed_at: datetime | None = None, **overrides: object) -> RuntimeDeploymentEvidence:
    commit = "a" * 40
    payload: dict[str, object] = {
        "source_commit": commit,
        "github_commit": commit,
        "vps_commit": commit,
        "container_revision": commit,
        "observed_at": (observed_at or datetime(2026, 7, 29, 12, tzinfo=timezone.utc)).isoformat(),
        "container_healthy": True,
        "health_endpoint_healthy": True,
        "websocket_connected": True,
        "observation_only_runtime": True,
        "paper_capital_disabled": True,
        "live_disabled": True,
        "automatic_promotion_disabled": True,
    }
    payload.update(overrides)
    return RuntimeDeploymentEvidence(**payload)  # type: ignore[arg-type]


def test_fail_closed_actions_are_monotonic_and_never_enable_risk():
    stale = decide_fail_closed("DATA_STALE")
    unknown = decide_fail_closed("ORDER_UNKNOWN", previous_action=stale.action)
    recovered_stream = decide_fail_closed("WEBSOCKET_DISCONNECTED", previous_action=unknown.action)

    assert stale.action == "BLOCK_NEW_SIGNALS"
    assert unknown.action == "HALT"
    assert recovered_stream.action == "HALT"
    assert unknown.risk_increase_allowed is False
    assert unknown.paper_capital_allowed is False
    assert unknown.live_allowed is False


def test_incident_summary_normalizes_and_uses_the_strictest_fail_closed_action():
    summary = summarize_fail_closed_incidents(("api_unavailable", "DATA_STALE", "API_UNAVAILABLE", "ORDER_UNKNOWN"))

    assert summary.incident_types == ("API_UNAVAILABLE", "DATA_STALE", "ORDER_UNKNOWN")
    assert summary.action == "HALT"
    assert "order_unknown:order_state_unknown" in summary.reasons
    assert summary.research_only is True
    assert summary.paper_capital_allowed is False
    assert summary.live_allowed is False


def test_incident_summary_rejects_unknown_or_scalar_inputs():
    with pytest.raises(ResilienceError, match="unsupported incident types"):
        summarize_fail_closed_incidents(("UNKNOWN_INCIDENT",))
    with pytest.raises(ResilienceError, match="sequence, not a string"):
        summarize_fail_closed_incidents("DATA_STALE")
    with pytest.raises(ResilienceError, match="cannot authorize paper or live"):
        FailClosedIncidentSummary(
            incident_types=("DATA_STALE",),
            action="BLOCK_NEW_SIGNALS",
            reasons=("fixture",),
            paper_capital_allowed=True,
        )


def test_fail_closed_public_contracts_reject_weaker_manual_actions():
    with pytest.raises(ResilienceError, match="weaker than the required"):
        IncidentDecision("DATA_STALE", "NORMAL", "forged_healthy_state")
    with pytest.raises(ResilienceError, match="non-empty reason"):
        IncidentDecision("DATA_STALE", "BLOCK_NEW_SIGNALS", "")
    with pytest.raises(ResilienceError, match="weaker than the required"):
        FailClosedIncidentSummary(
            incident_types=("ORDER_UNKNOWN",),
            action="BLOCK_NEW_ORDERS",
            reasons=("forged_partial_action",),
        )
    with pytest.raises(ResilienceError, match="omits a required"):
        FailClosedRecoveryPlan(
            incident_types=("ORDER_UNKNOWN",),
            steps=("BLOCK_NEW_SIGNALS", "BLOCK_NEW_ORDERS"),
            terminal_action="BLOCK_NEW_ORDERS",
        )


def test_fail_closed_recovery_plan_is_monotonic_and_non_executable():
    stale = plan_fail_closed_recovery(("DATA_STALE",))
    unknown = plan_fail_closed_recovery(("ORDER_UNKNOWN",))
    risk_breach = plan_fail_closed_recovery(("RISK_LIMIT_BREACH",))
    composite = plan_fail_closed_recovery(("DATA_STALE", "RISK_LIMIT_BREACH"))

    assert stale.steps == ("BLOCK_NEW_SIGNALS",)
    assert unknown.steps == ("BLOCK_NEW_SIGNALS", "BLOCK_NEW_ORDERS", "CANCEL_OPEN_ORDERS", "HALT")
    assert risk_breach.steps == (
        "BLOCK_NEW_SIGNALS",
        "BLOCK_NEW_ORDERS",
        "CANCEL_OPEN_ORDERS",
        "REDUCE_POSITIONS",
        "HALT",
    )
    assert composite.steps == risk_breach.steps
    assert composite.execution_authorized is False
    assert composite.paper_capital_allowed is False
    assert composite.live_allowed is False


def test_fail_closed_drill_covers_full_hierarchy_without_runtime_side_effects():
    report = run_fail_closed_drill()

    assert report.all_passed is True
    assert {scenario.incident_type for scenario in report.scenarios} >= {
        "DATA_STALE",
        "ORDER_UNKNOWN",
        "RISK_LIMIT_BREACH",
    }
    assert report.composite_steps == (
        "BLOCK_NEW_SIGNALS",
        "BLOCK_NEW_ORDERS",
        "CANCEL_OPEN_ORDERS",
        "REDUCE_POSITIONS",
        "HALT",
    )
    assert report.composite_terminal_action == "HALT"
    assert report.order_submission_attempted is False
    assert report.paper_capital_allowed is False
    assert report.live_allowed is False


def test_bounded_retry_recovers_only_within_limit_and_exposes_failure():
    attempts = {"count": 0}

    def transient() -> str:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise sqlite3.OperationalError("database is locked")
        return "ok"

    value, recovered = retry_bounded(
        transient,
        retryable=(sqlite3.OperationalError,),
        policy=RetryPolicy(max_attempts=3, initial_delay_seconds=0.01, multiplier=2.0),
        sleeper=lambda _: None,
    )
    failed_value, failed = retry_bounded(
        lambda: (_ for _ in ()).throw(sqlite3.OperationalError("database is locked")),
        retryable=(sqlite3.OperationalError,),
        policy=RetryPolicy(max_attempts=2, initial_delay_seconds=0.01),
        sleeper=lambda _: None,
    )

    assert value == "ok"
    assert recovered.recovered is True and recovered.attempts == 3
    assert recovered.delays_seconds == pytest.approx((0.01, 0.02))
    assert failed_value is None
    assert failed.recovered is False and failed.error_type == "OperationalError"


def test_verified_sqlite_backup_can_be_read_and_never_claims_unconfigured_encryption(tmp_path):
    source = tmp_path / "source.sqlite3"
    destination = tmp_path / "backup.sqlite3"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE observations (id INTEGER PRIMARY KEY, value TEXT)")
        connection.execute("INSERT INTO observations(value) VALUES ('preserved')")
    source_before = source.read_bytes()

    manifest = create_verified_sqlite_backup(source, destination)
    with sqlite3.connect(destination) as connection:
        restored = connection.execute("SELECT value FROM observations").fetchone()[0]

    assert manifest.integrity_check.lower() == "ok"
    assert manifest.source_sha256
    assert manifest.backup_sha256
    assert manifest.encrypted is False
    assert manifest.foreign_key_violation_count == 0
    assert restored == "preserved"
    assert source.read_bytes() == source_before
    with pytest.raises(ResilienceError, match="approved external backup layer"):
        create_verified_sqlite_backup(source, tmp_path / "encrypted.sqlite3", encrypted=True)
    with pytest.raises(ResilienceError, match="destination must differ"):
        create_verified_sqlite_backup(source, source)
    with pytest.raises(ResilienceError, match="refusing to overwrite"):
        create_verified_sqlite_backup(source, destination)


def test_sqlite_backup_scope_audit_is_fixed_read_only_and_marks_absent_research_registries_optional(tmp_path):
    repo = _backup_scope_repo(tmp_path)
    state_before = (repo / "data" / "autobot_state.db").read_bytes()
    kill_before = (repo / "data" / "global_kill_switch.db").read_bytes()

    audit = audit_sqlite_backup_scope(repo)

    assert [entry.identifier for entry in audit.entries] == [
        "runtime_state",
        "global_kill_switch",
        "experiment_registry",
        "strategy_artifacts",
    ]
    assert [entry.status for entry in audit.entries] == [
        "READY",
        "READY",
        "MISSING_OPTIONAL",
        "MISSING_OPTIONAL",
    ]
    assert audit.missing_required == ()
    assert audit.research_only is True
    assert audit.paper_capital_allowed is False
    assert audit.live_allowed is False
    assert state_before == (repo / "data" / "autobot_state.db").read_bytes()
    assert kill_before == (repo / "data" / "global_kill_switch.db").read_bytes()
    assert not (repo / "data" / "research" / "experiment_registry.sqlite3").exists()
    assert not (repo / "data" / "research" / "strategy_artifacts.sqlite3").exists()


def test_sqlite_backup_bundle_captures_fixed_scope_and_preserves_wal_commits(tmp_path):
    repo = _backup_scope_repo(tmp_path, include_optional=True)
    state_path = repo / "data" / "autobot_state.db"
    with sqlite3.connect(state_path) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("INSERT INTO evidence(value) VALUES ('committed_in_wal')")
        connection.commit()
        state_before = state_path.read_bytes()
        bundle = create_verified_sqlite_backup_bundle(repo, tmp_path / "backups" / "run_2026_07_29")

    assert bundle.bundle_id == "run_2026_07_29"
    assert bundle.capture_finished_at >= bundle.capture_started_at
    assert [entry.status for entry in bundle.entries] == ["BACKED_UP"] * 4
    assert (tmp_path / "backups" / "run_2026_07_29" / "manifest.json").is_file()
    assert state_before == state_path.read_bytes()
    for entry in bundle.entries:
        assert entry.backup is not None
        backup_path = Path(entry.backup.backup_path)
        assert backup_path.is_file()
        assert verify_sqlite_restore_drill(backup_path).temporary_restore_cleaned is True
    with sqlite3.connect(Path(bundle.entries[0].backup.backup_path)) as connection:  # type: ignore[union-attr]
        count = connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
    assert count == 2


def test_sqlite_backup_bundle_restore_drill_is_hermetic_and_validates_only_fixed_scope(tmp_path):
    repo = _backup_scope_repo(tmp_path, include_optional=True)
    bundle_path = tmp_path / "backups" / "restore_proof"
    create_verified_sqlite_backup_bundle(repo, bundle_path)
    manifest_before = (bundle_path / "manifest.json").read_bytes()
    snapshot_before = {path.name: path.read_bytes() for path in bundle_path.glob("*.sqlite3")}

    drill = verify_sqlite_backup_bundle_restore_drill(bundle_path)

    assert [entry.identifier for entry in drill.entries] == [
        "runtime_state",
        "global_kill_switch",
        "experiment_registry",
        "strategy_artifacts",
    ]
    assert all(entry.restore.temporary_restore_cleaned for entry in drill.entries)
    assert drill.bundle_manifest_sha256_before == drill.bundle_manifest_sha256_after
    assert drill.research_only is True
    assert drill.paper_capital_allowed is False
    assert drill.live_allowed is False
    assert manifest_before == (bundle_path / "manifest.json").read_bytes()
    assert snapshot_before == {path.name: path.read_bytes() for path in bundle_path.glob("*.sqlite3")}


def test_sqlite_backup_bundle_restore_drill_rejects_tampered_manifest_or_missing_snapshot(tmp_path):
    repo = _backup_scope_repo(tmp_path)
    bundle_path = tmp_path / "backups" / "tampered_bundle"
    create_verified_sqlite_backup_bundle(repo, bundle_path)
    manifest_path = bundle_path / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["entries"][0]["backup"]["backup_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    with pytest.raises(ResilienceError, match="snapshot fingerprint mismatch"):
        verify_sqlite_backup_bundle_restore_drill(bundle_path)

    fresh_bundle_path = tmp_path / "backups" / "missing_snapshot"
    create_verified_sqlite_backup_bundle(repo, fresh_bundle_path)
    (fresh_bundle_path / "runtime_state.sqlite3").unlink()
    with pytest.raises(ResilienceError, match="snapshot is missing"):
        verify_sqlite_backup_bundle_restore_drill(fresh_bundle_path)


@pytest.mark.parametrize(
    ("missing_filename", "expected_identifier"),
    (("autobot_state.db", "runtime_state"), ("global_kill_switch.db", "global_kill_switch")),
)
def test_sqlite_backup_bundle_fails_closed_for_missing_required_source_or_unsafe_identifier(
    tmp_path,
    missing_filename,
    expected_identifier,
):
    repo = _backup_scope_repo(tmp_path)
    (repo / "data" / missing_filename).unlink()
    destination = tmp_path / "backups" / "missing_required"

    with pytest.raises(ResilienceError, match=f"required SQLite backup sources are missing: {expected_identifier}"):
        create_verified_sqlite_backup_bundle(repo, destination)
    assert not destination.exists()

    _write_sqlite(repo / "data" / missing_filename, value="restored-fixture")
    with pytest.raises(ResilienceError, match="backup bundle identifier is unsafe"):
        create_verified_sqlite_backup_bundle(repo, tmp_path / "backups" / "unsafe..bundle")
    assert not (tmp_path / "backups" / "unsafe..bundle").exists()


def test_sqlite_backup_bundle_skips_only_optional_absent_sources_and_refuses_overwrite(tmp_path):
    repo = _backup_scope_repo(tmp_path)
    destination = tmp_path / "backups" / "bounded_scope"

    bundle = create_verified_sqlite_backup_bundle(repo, destination)

    assert [entry.status for entry in bundle.entries] == [
        "BACKED_UP",
        "BACKED_UP",
        "SKIPPED_OPTIONAL_MISSING",
        "SKIPPED_OPTIONAL_MISSING",
    ]
    with pytest.raises(ResilienceError, match="refusing to overwrite"):
        create_verified_sqlite_backup_bundle(repo, destination)


def test_sqlite_restore_drill_is_hermetic_and_preserves_backup_input(tmp_path):
    source = tmp_path / "source.sqlite3"
    backup = tmp_path / "backup.sqlite3"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE observations (id INTEGER PRIMARY KEY, value TEXT)")
        connection.executemany("INSERT INTO observations(value) VALUES (?)", [("one",), ("two",)])
    create_verified_sqlite_backup(source, backup)

    manifest = verify_sqlite_restore_drill(backup)

    assert manifest.backup_sha256_before == manifest.backup_sha256_after
    assert manifest.source_schema_sha256 == manifest.restored_schema_sha256
    assert manifest.source_table_row_counts == {"observations": 2}
    assert manifest.restored_table_row_counts == {"observations": 2}
    assert manifest.source_foreign_key_violation_count == 0
    assert manifest.restored_foreign_key_violation_count == 0
    assert manifest.temporary_restore_cleaned is True
    assert manifest.paper_capital_allowed is False
    assert manifest.live_allowed is False


def test_ephemeral_sqlite_restore_drill_retains_no_backup_and_preserves_source(tmp_path):
    source = tmp_path / "source.sqlite3"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE observations (id INTEGER PRIMARY KEY, value TEXT)")
        connection.executemany("INSERT INTO observations(value) VALUES (?)", [("one",), ("two",)])
    source_before = source.read_bytes()

    manifest = run_ephemeral_sqlite_restore_drill(source)

    assert manifest.source_path == str(source.resolve())
    assert manifest.backup.integrity_check.lower() == "ok"
    assert manifest.restore.integrity_check.lower() == "ok"
    assert manifest.restore.source_table_row_counts == {"observations": 2}
    assert manifest.restore.source_foreign_key_violation_count == 0
    assert manifest.restore.restored_foreign_key_violation_count == 0
    assert manifest.temporary_backup_cleaned is True
    assert manifest.paper_capital_allowed is False
    assert manifest.live_allowed is False
    assert source.read_bytes() == source_before


def test_sqlite_restore_drill_rejects_corrupt_or_missing_backup(tmp_path):
    corrupt = tmp_path / "corrupt.sqlite3"
    corrupt.write_bytes(b"not a sqlite database")

    with pytest.raises(ResilienceError, match="could not read the backup safely"):
        verify_sqlite_restore_drill(corrupt)
    with pytest.raises(ResilienceError, match="does not exist"):
        verify_sqlite_restore_drill(tmp_path / "missing.sqlite3")


def test_backup_and_restore_drills_reject_foreign_key_violations(tmp_path):
    source = tmp_path / "foreign_key_violation.sqlite3"
    with sqlite3.connect(source) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
        connection.execute(
            "CREATE TABLE child (id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES parent(id))"
        )
        connection.execute("INSERT INTO child(id, parent_id) VALUES (1, 999)")

    before = source.read_bytes()
    with pytest.raises(ResilienceError, match="foreign key check failed: 1 violation"):
        create_verified_sqlite_backup(source, tmp_path / "backup.sqlite3")
    with pytest.raises(ResilienceError, match="foreign key check failed: 1 violation"):
        verify_sqlite_restore_drill(source)

    assert source.read_bytes() == before
    assert not (tmp_path / "backup.sqlite3").exists()


def test_readiness_dossier_is_non_authorizing_and_blocks_partial_or_unsafe_layers():
    required = {layer: "VERIFIED" for layer in (3, 5, 10, 11, 12, 13, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24)}
    ready = evaluate_human_paper_readiness(
        layer_statuses=required,
        kill_switch_tested=True,
        reconciliation_tested=True,
        restore_tested=True,
        deployment_evidence=_deployment_evidence(),
        evaluated_at=datetime(2026, 7, 29, 12, 1, tzinfo=timezone.utc),
    )
    blocked = evaluate_human_paper_readiness(
        layer_statuses={**required, 22: "UNSAFE"},
        kill_switch_tested=False,
        reconciliation_tested=True,
        restore_tested=False,
    )

    assert ready.status == "READY_FOR_HUMAN_PAPER_REVIEW"
    assert ready.paper_capital_allowed is False
    assert ready.live_allowed is False
    assert blocked.status == "NOT_READY_FOR_HUMAN_PAPER_REVIEW"
    assert "layer_22_unsafe" in blocked.blockers
    assert "kill_switch_not_tested" in blocked.blockers
    assert "restore_not_tested" in blocked.blockers
    assert "deployment_evidence_missing" in blocked.blockers


def test_versioned_coverage_produces_not_ready_dossier_until_runtime_gates_are_verified(tmp_path):
    coverage = tmp_path / "coverage.json"
    coverage.write_text(
        '{"layers":[{"id":3,"status":"VERIFIED"},{"id":5,"status":"VERIFIED"},{"id":10,"status":"VERIFIED"},{"id":11,"status":"VERIFIED"},{"id":12,"status":"VERIFIED"},{"id":13,"status":"UNSAFE"},{"id":15,"status":"VERIFIED"},{"id":16,"status":"VERIFIED"},{"id":17,"status":"VERIFIED"},{"id":18,"status":"VERIFIED"},{"id":19,"status":"VERIFIED"},{"id":20,"status":"UNSAFE"},{"id":21,"status":"VERIFIED"},{"id":22,"status":"UNSAFE"},{"id":23,"status":"PARTIAL"},{"id":24,"status":"PARTIAL"}]}',
        encoding="utf-8",
    )

    dossier = build_readiness_dossier_from_coverage(coverage)
    written = write_readiness_dossier(dossier, tmp_path / "dossier.md")

    assert dossier.status == "NOT_READY_FOR_HUMAN_PAPER_REVIEW"
    assert "layer_13_unsafe" in dossier.blockers
    assert "layer_22_unsafe" in dossier.blockers
    assert "deployment_evidence_missing" in dossier.blockers
    assert written.exists()


def test_readiness_dossier_requires_fresh_aligned_observation_only_deployment_evidence():
    required = {layer: "VERIFIED" for layer in (3, 5, 10, 11, 12, 13, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24)}
    now = datetime(2026, 7, 29, 12, 10, tzinfo=timezone.utc)
    evidence = _deployment_evidence(
        observed_at=datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc),
        vps_commit="b" * 40,
        paper_capital_disabled=False,
        automatic_promotion_disabled=False,
    )

    dossier = evaluate_human_paper_readiness(
        layer_statuses=required,
        kill_switch_tested=True,
        reconciliation_tested=True,
        restore_tested=True,
        deployment_evidence=evidence,
        evaluated_at=now,
        max_deployment_evidence_age_seconds=60,
    )

    assert dossier.status == "NOT_READY_FOR_HUMAN_PAPER_REVIEW"
    assert "deployment_evidence_stale" in dossier.blockers
    assert "vps_commit_not_aligned_with_source" in dossier.blockers
    assert "paper_capital_not_disabled" in dossier.blockers
    assert "automatic_promotion_not_disabled" in dossier.blockers
    assert dossier.paper_capital_allowed is False
    assert dossier.live_allowed is False


def test_runtime_deployment_evidence_rejects_non_commit_or_naive_timestamp():
    with pytest.raises(ResilienceError, match="source_commit"):
        _deployment_evidence(source_commit="not-a-commit")
    with pytest.raises(ResilienceError, match="timezone-aware"):
        _deployment_evidence(observed_at=datetime(2026, 7, 29, 12, 0))
    with pytest.raises(ResilienceError, match="container_healthy"):
        _deployment_evidence(container_healthy="true")


def test_runtime_deployment_evidence_json_loader_requires_the_exact_verifier_schema(tmp_path):
    source = tmp_path / "runtime_evidence.json"
    payload = asdict(_deployment_evidence())
    source.write_text(json.dumps(payload), encoding="utf-8")

    loaded = load_runtime_deployment_evidence(source)
    reconstructed = runtime_deployment_evidence_from_mapping(payload)

    assert loaded == reconstructed
    with pytest.raises(ResilienceError, match="unexpected fields"):
        runtime_deployment_evidence_from_mapping({**payload, "paper_capital_allowed": False})
    with pytest.raises(ResilienceError, match="missing fields"):
        runtime_deployment_evidence_from_mapping(
            {key: value for key, value in payload.items() if key != "websocket_connected"}
        )


def test_readiness_dossier_rejects_deployment_evidence_from_another_source_commit():
    required = {layer: "VERIFIED" for layer in (3, 5, 10, 11, 12, 13, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24)}
    dossier = evaluate_human_paper_readiness(
        layer_statuses=required,
        kill_switch_tested=True,
        reconciliation_tested=True,
        restore_tested=True,
        deployment_evidence=_deployment_evidence(),
        expected_source_commit="b" * 40,
        evaluated_at=datetime(2026, 7, 29, 12, 1, tzinfo=timezone.utc),
    )

    assert dossier.status == "NOT_READY_FOR_HUMAN_PAPER_REVIEW"
    assert "deployment_evidence_source_commit_mismatch" in dossier.blockers


def test_readiness_dossier_rejects_invalid_expected_source_commit_even_without_evidence():
    with pytest.raises(ResilienceError, match="expected_source_commit"):
        evaluate_human_paper_readiness(
            layer_statuses={},
            kill_switch_tested=False,
            reconciliation_tested=False,
            restore_tested=False,
            expected_source_commit="not-a-commit",
        )


def test_readiness_dossier_cannot_authorize_execution_even_if_constructed_directly():
    with pytest.raises(ResilienceError, match="cannot authorize"):
        PaperReadinessDossier(
            status="READY_FOR_HUMAN_PAPER_REVIEW",
            blockers=(),
            layer_statuses={},
            kill_switch_tested=True,
            reconciliation_tested=True,
            restore_tested=True,
            paper_capital_allowed=True,
        )


def test_resilience_module_does_not_import_runtime_or_execution_paths():
    root = Path(__file__).resolve().parents[2]
    tree = ast.parse((root / "src/autobot/v2/research/resilience_readiness.py").read_text(encoding="utf-8"))
    forbidden = {"autobot.v2.order_router", "autobot.v2.signal_handler_async", "autobot.v2.paper_trading"}
    imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imports.update(node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module)
    assert imports.isdisjoint(forbidden)
