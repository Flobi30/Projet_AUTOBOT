from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3

import pytest

from autobot.v2.research.runtime_resilience_audit import (
    RuntimeResilienceAuditError,
    audit_runtime_resilience,
)


pytestmark = pytest.mark.unit


def _state_db(path: Path, observed_at: str | None = None) -> Path:
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE market_price_samples (id INTEGER PRIMARY KEY, observed_at TEXT NOT NULL)"
        )
        if observed_at is not None:
            connection.execute("INSERT INTO market_price_samples(observed_at) VALUES (?)", (observed_at,))
    return path


def test_runtime_resilience_audit_reports_healthy_only_with_explicit_websocket_proof(tmp_path):
    now = datetime(2026, 7, 16, 12, tzinfo=timezone.utc)
    state_db = _state_db(tmp_path / "state.sqlite3", (now - timedelta(seconds=20)).isoformat())
    before = state_db.read_bytes()

    report = audit_runtime_resilience(
        state_db,
        max_data_age_seconds=60,
        min_free_disk_bytes=0,
        websocket_status="connected",
        websocket_observed_at=now - timedelta(seconds=10),
        evaluated_at=now,
    )

    assert report.status == "RESILIENCE_HEALTHY"
    assert report.evaluated_at == now.isoformat()
    assert report.sqlite_integrity_check == "ok"
    assert report.websocket_observed_at == (now - timedelta(seconds=10)).isoformat()
    assert report.websocket_age_seconds == 10.0
    assert report.incident_types == ()
    assert report.fail_closed.action == "NORMAL"
    assert report.paper_capital_allowed is False
    assert report.live_allowed is False
    assert state_db.read_bytes() == before


def test_runtime_resilience_audit_fails_closed_for_stale_data_disk_and_websocket(tmp_path):
    now = datetime(2026, 7, 16, 12, tzinfo=timezone.utc)
    state_db = _state_db(tmp_path / "state.sqlite3", (now - timedelta(minutes=20)).isoformat())

    report = audit_runtime_resilience(
        state_db,
        max_data_age_seconds=60,
        min_free_disk_bytes=10**30,
        websocket_status="disconnected",
        evaluated_at=now,
    )

    assert report.status == "INCIDENTS_DETECTED"
    assert report.incident_types == ("DATA_STALE", "DISK_FULL", "WEBSOCKET_DISCONNECTED")
    assert report.fail_closed.action == "HALT"
    assert "market_data_stale" in report.reasons
    assert "free_disk_below_minimum" in report.reasons
    assert "websocket_reported_disconnected" in report.reasons


def test_runtime_resilience_audit_fails_closed_for_missing_or_invalid_runtime_database(tmp_path):
    now = datetime(2026, 7, 16, 12, tzinfo=timezone.utc)
    missing = audit_runtime_resilience(
        tmp_path / "missing.sqlite3",
        min_free_disk_bytes=0,
        websocket_status="connected",
        websocket_observed_at=now,
        evaluated_at=now,
    )
    invalid_path = tmp_path / "invalid.sqlite3"
    invalid_path.write_text("not sqlite", encoding="utf-8")
    invalid = audit_runtime_resilience(
        invalid_path,
        min_free_disk_bytes=0,
        websocket_status="connected",
        websocket_observed_at=now,
        evaluated_at=now,
    )

    assert missing.incident_types == ("DATA_STALE", "SQLITE_CORRUPT")
    assert missing.fail_closed.action == "HALT"
    assert invalid.incident_types == ("DATA_STALE", "SQLITE_CORRUPT")
    assert invalid.fail_closed.action == "HALT"


def test_runtime_resilience_audit_treats_an_incompatible_market_schema_as_corrupt(tmp_path):
    now = datetime(2026, 7, 16, 12, tzinfo=timezone.utc)
    state_db = tmp_path / "incompatible.sqlite3"
    with sqlite3.connect(state_db) as connection:
        connection.execute("CREATE TABLE market_price_samples (id INTEGER PRIMARY KEY, wrong_column TEXT)")

    report = audit_runtime_resilience(
        state_db,
        min_free_disk_bytes=0,
        websocket_status="connected",
        websocket_observed_at=now,
        evaluated_at=now,
    )

    assert report.incident_types == ("DATA_STALE", "SQLITE_CORRUPT")
    assert report.fail_closed.action == "HALT"
    assert "sqlite_operational_error:OperationalError" in report.reasons


def test_runtime_resilience_audit_does_not_claim_websocket_health_when_unknown(tmp_path):
    now = datetime(2026, 7, 16, 12, tzinfo=timezone.utc)
    state_db = _state_db(tmp_path / "state.sqlite3", now.isoformat())

    report = audit_runtime_resilience(
        state_db,
        min_free_disk_bytes=0,
        websocket_status="unknown",
        evaluated_at=now,
    )

    assert report.status == "PARTIAL_OBSERVABILITY"
    assert report.incident_types == ()
    assert "websocket_not_observed" in report.reasons


def test_runtime_resilience_audit_fails_closed_without_fresh_connected_websocket_evidence(tmp_path):
    now = datetime(2026, 7, 16, 12, tzinfo=timezone.utc)
    state_db = _state_db(tmp_path / "state.sqlite3", now.isoformat())

    missing = audit_runtime_resilience(
        state_db,
        min_free_disk_bytes=0,
        websocket_status="connected",
        evaluated_at=now,
    )
    stale = audit_runtime_resilience(
        state_db,
        min_free_disk_bytes=0,
        websocket_status="connected",
        websocket_observed_at=now - timedelta(seconds=61),
        max_websocket_age_seconds=60,
        evaluated_at=now,
    )

    assert missing.incident_types == ("WEBSOCKET_DISCONNECTED",)
    assert missing.fail_closed.action == "BLOCK_NEW_ORDERS"
    assert "websocket_connected_evidence_missing" in missing.reasons
    assert stale.incident_types == ("WEBSOCKET_DISCONNECTED",)
    assert stale.websocket_age_seconds == 61.0
    assert "websocket_connected_evidence_stale" in stale.reasons


def test_runtime_resilience_audit_rejects_invalid_or_future_websocket_evidence(tmp_path):
    now = datetime(2026, 7, 16, 12, tzinfo=timezone.utc)
    state_db = _state_db(tmp_path / "state.sqlite3", now.isoformat())

    future = audit_runtime_resilience(
        state_db,
        min_free_disk_bytes=0,
        websocket_status="connected",
        websocket_observed_at=now + timedelta(seconds=1),
        evaluated_at=now,
    )

    assert future.incident_types == ("WEBSOCKET_DISCONNECTED",)
    assert "websocket_observed_at_in_future" in future.reasons
    with pytest.raises(RuntimeResilienceAuditError, match="websocket_observed_at"):
        audit_runtime_resilience(state_db, websocket_observed_at="not-a-timestamp")


def test_runtime_resilience_audit_rejects_invalid_configuration_and_runtime_imports(tmp_path):
    state_db = _state_db(tmp_path / "state.sqlite3", datetime.now(timezone.utc).isoformat())
    with pytest.raises(RuntimeResilienceAuditError, match="max_data_age_seconds"):
        audit_runtime_resilience(state_db, max_data_age_seconds=-1)
    with pytest.raises(RuntimeResilienceAuditError, match="max_websocket_age_seconds"):
        audit_runtime_resilience(state_db, max_websocket_age_seconds=-1)
    with pytest.raises(RuntimeResilienceAuditError, match="websocket_status"):
        audit_runtime_resilience(state_db, websocket_status="invented")  # type: ignore[arg-type]

    root = Path(__file__).resolve().parents[2]
    tree = ast.parse((root / "src/autobot/v2/research/runtime_resilience_audit.py").read_text(encoding="utf-8"))
    forbidden = {"autobot.v2.order_router", "autobot.v2.signal_handler_async", "autobot.v2.paper_trading"}
    imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imports.update(node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module)
    assert imports.isdisjoint(forbidden)
