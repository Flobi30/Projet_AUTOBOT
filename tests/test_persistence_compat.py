import sqlite3

import pytest

from autobot.v2.persistence import StatePersistence


pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_save_position_accepts_legacy_positional_call(tmp_path):
    db_path = tmp_path / "state.db"
    persistence = StatePersistence(str(db_path))

    ok = await persistence.save_position(
        "pos-1",
        "inst-1",
        100.0,
        0.25,
        "open",
        "grid",
        {"buy_txid": "paper-1"},
    )
    await persistence.close()

    assert ok is True
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT id, instance_id, buy_price, volume, status, strategy, metadata FROM positions WHERE id = ?",
            ("pos-1",),
        ).fetchone()

    assert row is not None
    assert row[0] == "pos-1"
    assert row[1] == "inst-1"
    assert row[2] == 100.0
    assert row[3] == 0.25
    assert row[4] == "open"
    assert row[5] == "grid"
    assert "paper-1" in row[6]
