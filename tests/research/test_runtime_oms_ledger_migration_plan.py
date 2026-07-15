from __future__ import annotations

import ast
from pathlib import Path
import sqlite3

import pytest

from autobot.v2.research.runtime_oms_ledger_migration_plan import plan_runtime_oms_ledger_migration


pytestmark = pytest.mark.unit


def _create_legacy_runtime_tables(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE orders (client_order_id TEXT, exchange_order_id TEXT)")
        connection.execute(
            "CREATE TABLE order_state_transitions (id INTEGER PRIMARY KEY, client_order_id TEXT, from_status TEXT, to_status TEXT, reason TEXT, occurred_at TEXT)"
        )
        connection.execute(
            """
            CREATE TABLE trade_ledger (
                id INTEGER PRIMARY KEY,
                trade_id TEXT,
                exchange_order_id TEXT,
                decision_id TEXT,
                signal_id TEXT,
                strategy_id TEXT,
                execution_mode TEXT,
                volume REAL,
                executed_price REAL,
                fees REAL,
                created_at TEXT
            )
            """
        )


def test_migration_plan_is_read_only_deterministic_and_quarantines_unknown_provenance(tmp_path):
    state_db = tmp_path / "state.sqlite3"
    _create_legacy_runtime_tables(state_db)
    with sqlite3.connect(state_db) as connection:
        connection.execute("INSERT INTO orders VALUES ('client-1', 'exchange-1')")
        connection.execute("INSERT INTO order_state_transitions VALUES (1, 'client-1', 'NEW', 'SENT', 'legacy', '2026-07-15T12:00:00+00:00')")
        connection.execute("INSERT INTO order_state_transitions VALUES (2, 'client-1', NULL, 'ACK', 'missing', '2026-07-15T12:00:30+00:00')")
        connection.execute("INSERT INTO order_state_transitions VALUES (3, NULL, 'SENT', 'ACK', 'invalid', '2026-07-15T12:01:00+00:00')")
        connection.execute("INSERT INTO order_state_transitions VALUES (4, 'unknown-client', 'SENT', 'ACK', 'orphan', '2026-07-15T12:01:30+00:00')")
        connection.execute(
            "INSERT INTO trade_ledger VALUES (1, 'fill-1', 'exchange-1', 'decision-1', 'signal-1', 'trend_momentum', 'shadow_paper', 2.0, 100.0, 0.2, '2026-07-15T12:02:00+00:00')"
        )
        connection.execute(
            "INSERT INTO trade_ledger VALUES (2, 'fill-2', 'exchange-1', 'decision-2', 'signal-2', NULL, 'shadow_paper', 1.0, 100.0, 0.1, '2026-07-15T12:03:00+00:00')"
        )
    before = state_db.read_bytes()

    first = plan_runtime_oms_ledger_migration(state_db)
    second = plan_runtime_oms_ledger_migration(state_db)

    assert first.status == "MIGRATION_REVIEW_REQUIRED"
    assert first.migration_allowed is False
    assert first.canonical_intent_candidate_count == 0
    assert first.unmigratable_order_intent_count == 1
    assert first.reconstructable_order_event_count == 1
    assert first.reconstructable_order_event_with_exchange_order_id_count == 1
    assert first.order_event_reconciliation_required_count == 1
    assert first.reconstructable_fill_event_count == 1
    assert first.quarantine_reason_counts == {
        "missing_client_order_id": 1,
        "missing_from_status": 1,
        "missing_strategy_id": 1,
        "unresolved_legacy_order": 1,
    }
    assert first.candidate_fingerprint == second.candidate_fingerprint
    assert first.quarantine_fingerprint == second.quarantine_fingerprint
    assert first.paper_capital_allowed is False and first.live_allowed is False
    assert state_db.read_bytes() == before


def test_migration_plan_quarantines_unknown_costs_non_finite_values_duplicates_and_bad_transitions(tmp_path):
    state_db = tmp_path / "state.sqlite3"
    _create_legacy_runtime_tables(state_db)
    with sqlite3.connect(state_db) as connection:
        connection.execute("INSERT INTO orders VALUES ('client-1', 'exchange-1')")
        connection.execute("INSERT INTO order_state_transitions VALUES (1, 'client-1', 'FILLED', 'SENT', NULL, '2026-07-15T12:00:00+00:00')")
        connection.execute(
            "INSERT INTO trade_ledger VALUES (1, 'duplicate-fill', 'exchange-1', 'd-1', 's-1', 'trend', 'shadow_paper', 1.0, 100.0, 0.1, '2026-07-15T12:01:00+00:00')"
        )
        connection.execute(
            "INSERT INTO trade_ledger VALUES (2, 'duplicate-fill', 'exchange-1', 'd-2', 's-2', 'trend', 'shadow_paper', 1.0, 100.0, 0.1, '2026-07-15T12:02:00+00:00')"
        )
        connection.execute(
            "INSERT INTO trade_ledger VALUES (3, 'missing-fees', 'exchange-1', 'd-3', 's-3', 'trend', 'shadow_paper', 1.0, 100.0, NULL, '2026-07-15T12:03:00+00:00')"
        )
        connection.execute(
            "INSERT INTO trade_ledger VALUES (4, 'nan-volume', 'exchange-1', 'd-4', 's-4', 'trend', 'shadow_paper', 'NaN', 100.0, 0.1, '2026-07-15T12:04:00+00:00')"
        )

    plan = plan_runtime_oms_ledger_migration(state_db)

    assert plan.reconstructable_order_event_count == 0
    assert plan.reconstructable_fill_event_count == 0
    assert plan.quarantine_reason_counts == {
        "duplicate_trade_id": 2,
        "incoherent_legacy_transition": 1,
        "invalid_fill_values": 1,
        "missing_fees": 1,
    }


def test_migration_plan_quarantines_non_monotonic_transition_timestamps(tmp_path):
    state_db = tmp_path / "state.sqlite3"
    _create_legacy_runtime_tables(state_db)
    with sqlite3.connect(state_db) as connection:
        connection.execute("INSERT INTO orders VALUES ('client-1', 'exchange-1')")
        connection.execute("INSERT INTO order_state_transitions VALUES (1, 'client-1', 'NEW', 'SENT', NULL, '2026-07-15T12:01:00+00:00')")
        connection.execute("INSERT INTO order_state_transitions VALUES (2, 'client-1', 'SENT', 'ACK', NULL, '2026-07-15T12:00:00+00:00')")

    plan = plan_runtime_oms_ledger_migration(state_db)

    assert plan.reconstructable_order_event_count == 1
    assert plan.quarantine_reason_counts == {"non_monotonic_legacy_transition_time": 1}


def test_migration_plan_does_not_create_missing_database(tmp_path):
    state_db = tmp_path / "missing.sqlite3"

    plan = plan_runtime_oms_ledger_migration(state_db)

    assert plan.status == "NO_RUNTIME_ORDER_EVIDENCE"
    assert plan.database_exists is False
    assert state_db.exists() is False


def test_migration_planner_does_not_import_runtime_execution_components():
    root = Path(__file__).resolve().parents[2]
    tree = ast.parse((root / "src/autobot/v2/research/runtime_oms_ledger_migration_plan.py").read_text(encoding="utf-8"))
    imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imports.update(node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module)
    assert imports.isdisjoint(
        {
            "autobot.v2.order_router",
            "autobot.v2.paper_trading",
            "autobot.v2.reconciliation_async",
            "autobot.v2.signal_handler_async",
        }
    )
