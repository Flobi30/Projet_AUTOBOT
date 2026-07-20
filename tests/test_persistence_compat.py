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
            "SELECT id, instance_id, buy_price, volume, status, strategy, metadata, symbol FROM positions WHERE id = ?",
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
    assert row[7] is None


@pytest.mark.asyncio
async def test_save_position_persists_symbol_from_metadata(tmp_path):
    db_path = tmp_path / "state.db"
    persistence = StatePersistence(str(db_path))

    ok = await persistence.save_position(
        position_id="pos-symbol",
        instance_id="inst-1",
        buy_price=100.0,
        volume=0.25,
        status="open",
        strategy="grid",
        metadata={"symbol": "XETHZEUR", "buy_txid": "paper-1"},
    )
    await persistence.close()

    assert ok is True
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT symbol, metadata FROM positions WHERE id = ?",
            ("pos-symbol",),
        ).fetchone()

    assert row is not None
    assert row[0] == "XETHZEUR"
    assert "XETHZEUR" in row[1]


@pytest.mark.asyncio
async def test_recover_positions_can_match_orphan_by_ledger_symbol(tmp_path):
    db_path = tmp_path / "state.db"
    persistence = StatePersistence(str(db_path))

    assert await persistence.save_position(
        "pos-legacy",
        "old-inst",
        120.0,
        0.5,
        "open",
        "grid",
        {"buy_txid": "paper-buy-1"},
    )
    assert await persistence.append_trade_ledger(
        trade_id="paper-buy-1",
        position_id="pos-legacy",
        instance_id="old-inst",
        symbol="XETHZEUR",
        side="buy",
        expected_price=120.0,
        executed_price=120.0,
        volume=0.5,
        fees=0.1,
        slippage_bps=0.0,
        is_opening_leg=True,
        strategy_id="trend_momentum",
        decision_id="dec-legacy-recovery",
        signal_id="sig-legacy-recovery",
        execution_mode="shadow_paper",
    )

    recovered = await persistence.recover_positions("new-inst", symbol="XETHZEUR")
    await persistence.close()

    assert [row["id"] for row in recovered] == ["pos-legacy"]


@pytest.mark.asyncio
async def test_instance_state_persists_initial_capital(tmp_path):
    db_path = tmp_path / "state.db"
    persistence = StatePersistence(str(db_path))

    ok = await persistence.save_instance_state(
        "inst-1",
        "running",
        125.0,
        25.0,
        3,
        1,
        initial_capital=100.0,
    )
    recovered = await persistence.recover_instance_state("inst-1")
    await persistence.close()

    assert ok is True
    assert recovered is not None
    assert recovered["current_capital"] == pytest.approx(125.0)
    assert recovered["initial_capital"] == pytest.approx(100.0)
