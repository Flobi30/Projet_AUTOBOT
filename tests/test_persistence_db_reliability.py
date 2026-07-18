import sqlite3

import pytest

from autobot.v2.persistence import StatePersistence
from autobot.v2.order_state_machine import PersistedOrderStateMachine


pytestmark = pytest.mark.unit


class _Cursor:
    rowcount = 1


class _BusyThenOkConnection:
    def __init__(self):
        self.execute_calls = 0
        self.commit_calls = 0

    async def execute(self, *args, **kwargs):
        self.execute_calls += 1
        if self.execute_calls == 1:
            raise sqlite3.OperationalError("database is locked")
        return _Cursor()

    async def commit(self):
        self.commit_calls += 1


@pytest.mark.asyncio
async def test_decision_ledger_write_retries_temporary_sqlite_lock(monkeypatch, tmp_path):
    monkeypatch.setenv("SQLITE_RETRY_BASE_DELAY_MS", "1")
    persistence = StatePersistence(str(tmp_path / "state.db"))
    await persistence.initialize()
    fake_conn = _BusyThenOkConnection()

    async def fake_get_conn():
        return fake_conn

    monkeypatch.setattr(persistence.orders, "get_conn", fake_get_conn)

    ok = await persistence.append_decision_ledger_event(
        event_id="evt-retry",
        decision_id="dec-retry",
        signal_id="sig-retry",
        instance_id="inst",
        symbol="TRXEUR",
        strategy="trend_momentum",
        engine="trend_momentum",
        event_type="decision",
        event_status="no_trade",
        reason="pytest",
        source="pytest",
    )
    await persistence.close()

    assert ok is True
    assert fake_conn.execute_calls == 2
    assert fake_conn.commit_calls == 1


@pytest.mark.asyncio
async def test_order_upsert_retries_temporary_sqlite_lock_without_duplicate_creation(monkeypatch, tmp_path):
    monkeypatch.setenv("SQLITE_RETRY_BASE_DELAY_MS", "1")
    persistence = StatePersistence(str(tmp_path / "state.db"))
    await persistence.initialize()
    fake_conn = _BusyThenOkConnection()

    async def fake_get_conn():
        return fake_conn

    monkeypatch.setattr(persistence.orders, "get_conn", fake_get_conn)
    created = await persistence.upsert_order(
        client_order_id="order-retry",
        instance_id="inst",
        symbol="TRXEUR",
        side="buy",
        order_type="market",
        requested_qty=1.0,
        strategy_id="trend_momentum",
    )
    await persistence.close()

    assert created is True
    assert fake_conn.execute_calls == 2
    assert fake_conn.commit_calls == 1


@pytest.mark.asyncio
async def test_trade_ledger_duplicate_trade_id_is_not_double_counted(tmp_path):
    db_path = tmp_path / "state.db"
    persistence = StatePersistence(str(db_path))
    payload = dict(
        trade_id="dup-trade",
        position_id="pos",
        instance_id="inst",
        symbol="TRXEUR",
        side="buy",
        expected_price=1.0,
        executed_price=1.0,
        volume=10.0,
        fees=0.1,
        slippage_bps=1.0,
        is_opening_leg=True,
        strategy_id="trend_momentum",
        execution_mode="shadow_paper",
    )

    assert await persistence.append_trade_ledger(**payload) is True
    assert await persistence.append_trade_ledger(**payload) is False
    await persistence.close()

    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM trade_ledger WHERE trade_id = ?", ("dup-trade",)).fetchone()[0]
        unique_indexes = [
            row[1]
            for row in conn.execute("PRAGMA index_list(trade_ledger)").fetchall()
            if row[2]
        ]

    assert count == 1
    assert "idx_trade_ledger_trade_id_unique" in unique_indexes


@pytest.mark.asyncio
async def test_market_sample_retry_is_idempotent(monkeypatch, tmp_path):
    monkeypatch.setenv("SQLITE_RETRY_BASE_DELAY_MS", "1")
    persistence = StatePersistence(str(tmp_path / "state.db"))
    await persistence.initialize()
    fake_conn = _BusyThenOkConnection()

    async def fake_get_conn():
        return fake_conn

    async def fake_executemany(*args, **kwargs):
        fake_conn.execute_calls += 1
        if fake_conn.execute_calls == 1:
            raise sqlite3.OperationalError("database is busy")
        return _Cursor()

    fake_conn.executemany = fake_executemany
    monkeypatch.setattr(persistence.orders, "get_conn", fake_get_conn)

    count = await persistence.append_market_price_samples(
        [
            {
                "sample_id": "px-1",
                "symbol": "TRXEUR",
                "price": 0.2,
                "observed_at": "2026-07-03T00:00:00+00:00",
                "bucket_start": "2026-07-03T00:00:00+00:00",
            }
        ]
    )
    await persistence.close()

    assert count == 1
    assert fake_conn.execute_calls == 2


@pytest.mark.asyncio
async def test_order_transition_records_explicit_from_status_and_rejects_orphans(tmp_path):
    persistence = StatePersistence(str(tmp_path / "state.db"))
    await persistence.initialize()
    assert await persistence.upsert_order(
        client_order_id="order-1",
        instance_id="instance-1",
        symbol="TRXEUR",
        side="buy",
        order_type="market",
        requested_qty=1.0,
        status="NEW",
        strategy_id="trend_momentum",
    )

    assert await persistence.transition_order_state(
        client_order_id="order-1",
        to_status="SENT",
        reason="submitted_for_shadow_observation",
        source="pytest",
    )
    assert await persistence.transition_order_state(
        client_order_id="unknown-order",
        to_status="SENT",
        reason="must_not_create_orphan_transition",
        source="pytest",
    ) is False
    await persistence.close()

    with sqlite3.connect(tmp_path / "state.db") as connection:
        transition = connection.execute(
            "SELECT client_order_id, from_status, to_status FROM order_state_transitions"
        ).fetchall()
        status, strategy_id = connection.execute(
            "SELECT status, strategy_id FROM orders WHERE client_order_id = 'order-1'"
        ).fetchone()

    assert transition == [("order-1", "NEW", "SENT")]
    assert status == "SENT"
    assert strategy_id == "trend_momentum"


@pytest.mark.asyncio
async def test_order_creation_rejects_missing_strategy_provenance(tmp_path):
    persistence = StatePersistence(str(tmp_path / "state.db"))
    await persistence.initialize()

    created = await persistence.upsert_order(
        client_order_id="missing-strategy",
        instance_id="instance-1",
        symbol="TRXEUR",
        side="buy",
        order_type="market",
        requested_qty=1.0,
    )
    await persistence.close()

    assert created is False
    with sqlite3.connect(tmp_path / "state.db") as connection:
        assert connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_order_state_machine_requires_strategy_id(tmp_path):
    persistence = StatePersistence(str(tmp_path / "state.db"))
    machine = PersistedOrderStateMachine(persistence)

    with pytest.raises(ValueError, match="strategy_id is required"):
        await machine.new_order(
            instance_id="instance-1",
            symbol="TRXEUR",
            side="buy",
            order_type="market",
            requested_qty=1.0,
            strategy_id="",
        )
    await persistence.close()


@pytest.mark.asyncio
async def test_order_state_machine_stops_when_persistence_rejects_new_order(tmp_path, monkeypatch):
    persistence = StatePersistence(str(tmp_path / "state.db"))
    machine = PersistedOrderStateMachine(persistence)

    async def reject_order(**_kwargs):
        return False

    monkeypatch.setattr(persistence, "upsert_order", reject_order)
    with pytest.raises(RuntimeError, match="persisted order creation was rejected"):
        await machine.new_order(
            instance_id="instance-1",
            symbol="TRXEUR",
            side="buy",
            order_type="market",
            requested_qty=1.0,
            strategy_id="trend_momentum",
        )
    await persistence.close()
