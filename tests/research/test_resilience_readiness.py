from __future__ import annotations

import ast
from pathlib import Path
import sqlite3

import pytest

from autobot.v2.research.resilience_readiness import (
    FailClosedIncidentSummary,
    ResilienceError,
    RetryPolicy,
    build_readiness_dossier_from_coverage,
    create_verified_sqlite_backup,
    decide_fail_closed,
    evaluate_human_paper_readiness,
    retry_bounded,
    run_ephemeral_sqlite_restore_drill,
    summarize_fail_closed_incidents,
    verify_sqlite_restore_drill,
    write_readiness_dossier,
)


pytestmark = pytest.mark.unit


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
    assert written.exists()


def test_resilience_module_does_not_import_runtime_or_execution_paths():
    root = Path(__file__).resolve().parents[2]
    tree = ast.parse((root / "src/autobot/v2/research/resilience_readiness.py").read_text(encoding="utf-8"))
    forbidden = {"autobot.v2.order_router", "autobot.v2.signal_handler_async", "autobot.v2.paper_trading"}
    imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imports.update(node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module)
    assert imports.isdisjoint(forbidden)
