import sqlite3

import pytest

from autobot.v2.research.no_trade_attribution_report import build_no_trade_attribution_report


pytestmark = pytest.mark.unit


def test_no_trade_attribution_counts_blockers(tmp_path):
    db_path = tmp_path / "state.db"
    connection = sqlite3.connect(db_path)
    connection.execute(
        "CREATE TABLE decision_ledger (id INTEGER PRIMARY KEY, symbol TEXT, strategy TEXT, "
        "event_type TEXT, event_status TEXT, reason TEXT, created_at TEXT)"
    )
    rows = [
        ("TRXEUR", "grid", "no_trade", "abstain", "router_selected_no_trade", "2026-06-11T10:00:00+00:00"),
        ("SOLEUR", "grid", "governance_block", "blocked", "official_underperforming", "2026-06-11T10:10:00+00:00"),
        ("ETHEUR", "grid", "decision", "rejected", "cost_guard_below_edge", "2026-06-11T11:00:00+00:00"),
        ("BTCEUR", "grid", "decision", "rejected", "microstructure_filter_block", "2026-06-11T11:10:00+00:00"),
    ]
    connection.executemany(
        "INSERT INTO decision_ledger(symbol,strategy,event_type,event_status,reason,created_at) VALUES(?,?,?,?,?,?)",
        rows,
    )
    connection.commit()
    connection.close()

    report = build_no_trade_attribution_report(state_db_path=db_path, run_id="test")

    assert report.counts["no_trade"] == 1
    assert report.counts["abstain"] == 1
    assert report.counts["governance_block"] == 2
    assert report.counts["cost_guard"] == 1
    assert report.counts["microstructure_filter"] == 1
    assert report.counts["router_selected_no_trade"] == 1
    assert report.live_promotion_allowed is False
