from __future__ import annotations

import ast
from pathlib import Path
import sqlite3

import pytest

from autobot.v2.research.runtime_oms_ledger_audit import audit_runtime_oms_ledger


pytestmark = pytest.mark.unit


def _create_runtime_tables(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE orders (client_order_id TEXT, decision_id TEXT, signal_id TEXT, status TEXT)")
        connection.execute("CREATE TABLE order_state_transitions (client_order_id TEXT, from_status TEXT, to_status TEXT)")
        connection.execute("CREATE TABLE trade_ledger (trade_id TEXT, decision_id TEXT, signal_id TEXT, strategy_id TEXT, execution_mode TEXT)")


def test_runtime_oms_audit_is_read_only_and_flags_incomplete_evidence(tmp_path):
    state_db = tmp_path / "state.sqlite3"
    _create_runtime_tables(state_db)
    with sqlite3.connect(state_db) as connection:
        connection.execute("INSERT INTO orders VALUES ('order-1', NULL, 'signal-1', 'NEW')")
        connection.execute("INSERT INTO order_state_transitions VALUES ('order-1', NULL, 'SENT')")
        connection.execute("INSERT INTO trade_ledger VALUES ('trade-1', NULL, 'signal-1', NULL, 'shadow')")
    before = state_db.read_bytes()

    report = audit_runtime_oms_ledger(state_db)

    assert report.status == "RECONCILIATION_REQUIRED"
    assert report.non_terminal_order_count == 1
    assert report.orders_missing_provenance_count == 1
    assert report.transitions_missing_from_status_count == 1
    assert report.untraceable_trade_count == 1
    assert report.paper_capital_allowed is False and report.live_allowed is False
    assert state_db.read_bytes() == before


def test_runtime_oms_audit_handles_missing_database_without_creating_it(tmp_path):
    state_db = tmp_path / "missing.sqlite3"
    report = audit_runtime_oms_ledger(state_db)
    assert report.status == "NO_RUNTIME_ORDER_EVIDENCE"
    assert state_db.exists() is False


def test_runtime_oms_audit_does_not_import_execution_components():
    root = Path(__file__).resolve().parents[2]
    tree = ast.parse((root / "src/autobot/v2/research/runtime_oms_ledger_audit.py").read_text(encoding="utf-8"))
    imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imports.update(node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module)
    assert imports.isdisjoint({"autobot.v2.order_router", "autobot.v2.paper_trading", "autobot.v2.reconciliation_async"})
