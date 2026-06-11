import json
import sqlite3

import pytest

from autobot.v2.research.orphan_position_reconciliation import audit_orphan_positions


pytestmark = pytest.mark.unit


def test_orphan_reconciliation_is_read_only(tmp_path):
    db_path = tmp_path / "state.db"
    connection = sqlite3.connect(db_path)
    connection.execute(
        "CREATE TABLE positions (id TEXT, instance_id TEXT, buy_price REAL, volume REAL, "
        "status TEXT, open_time TEXT, strategy TEXT, metadata TEXT, symbol TEXT)"
    )
    connection.execute("CREATE TABLE instance_state (instance_id TEXT PRIMARY KEY)")
    connection.execute("CREATE TABLE trade_ledger (position_id TEXT, instance_id TEXT)")
    connection.execute(
        "INSERT INTO positions VALUES(?,?,?,?,?,?,?,?,?)",
        ("pos-1", "old-instance", 10.0, 2.0, "open", "2026-05-01T00:00:00+00:00", "grid", json.dumps({"buy_txid": None}), None),
    )
    connection.commit()
    connection.close()

    report = audit_orphan_positions(state_db_path=db_path, run_id="test")

    assert report.orphan_count == 1
    assert report.orphan_notional_eur == 20.0
    assert report.positions[0].recommended_status == "legacy_orphan_candidate"
    assert report.write_performed is False

    connection = sqlite3.connect(db_path)
    try:
        assert connection.execute("SELECT status FROM positions WHERE id='pos-1'").fetchone()[0] == "open"
    finally:
        connection.close()
