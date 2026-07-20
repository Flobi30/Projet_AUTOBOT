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
        decision_id="dec-order-retry",
        signal_id="sig-order-retry",
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
        decision_id="dec-dup-trade",
        signal_id="sig-dup-trade",
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
@pytest.mark.parametrize(
    ("missing_field", "reason"),
    [
        ("decision_id", "decision_id_required"),
        ("signal_id", "signal_id_required"),
        ("fees", "fees_required"),
        ("slippage_bps", "slippage_bps_required"),
        ("execution_mode", "execution_mode_required"),
    ],
)
async def test_new_trade_ledger_rows_require_canonical_provenance(tmp_path, caplog, missing_field, reason):
    persistence = StatePersistence(str(tmp_path / "state.db"))
    payload = {
        "trade_id": f"canonical-{missing_field}",
        "position_id": "pos",
        "instance_id": "inst",
        "symbol": "TRXEUR",
        "side": "buy",
        "expected_price": 1.0,
        "executed_price": 1.0,
        "volume": 10.0,
        "fees": 0.1,
        "slippage_bps": 1.0,
        "is_opening_leg": True,
        "strategy_id": "trend_momentum",
        "decision_id": "dec-canonical",
        "signal_id": "sig-canonical",
        "execution_mode": "shadow_paper",
    }
    payload.pop(missing_field)

    assert await persistence.append_trade_ledger(**payload) is False
    await persistence.close()

    with sqlite3.connect(tmp_path / "state.db") as conn:
        persisted_rows = conn.execute("SELECT COUNT(*) FROM trade_ledger").fetchone()[0]

    assert persisted_rows == 0
    assert reason in caplog.text


@pytest.mark.asyncio
async def test_new_trade_ledger_rows_reject_legacy_execution_mode(tmp_path, caplog):
    persistence = StatePersistence(str(tmp_path / "state.db"))

    accepted = await persistence.append_trade_ledger(
        trade_id="legacy-mode",
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
        decision_id="dec-legacy-mode",
        signal_id="sig-legacy-mode",
        execution_mode="legacy_unspecified",
    )
    await persistence.close()

    assert accepted is False
    assert "execution_mode_required" in caplog.text


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
        decision_id="dec-order-1",
        signal_id="sig-order-1",
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
async def test_order_transition_enforces_graph_and_normalizes_cancelled_alias(tmp_path):
    persistence = StatePersistence(str(tmp_path / "state.db"))
    machine = PersistedOrderStateMachine(persistence)
    record = await machine.new_order(
        instance_id="instance-1",
        symbol="TRXEUR",
        side="buy",
        order_type="market",
        requested_qty=1.0,
        strategy_id="trend_momentum",
        decision_id="dec-transition-graph",
        signal_id="sig-transition-graph",
        client_order_id="order-transition-graph",
    )

    assert await machine.transition(record.client_order_id, "FILLED", "cannot_skip_submission") is False
    assert await machine.transition(record.client_order_id, "CANCELLED", "exchange_cancelled") is True
    # Retrying the same terminal state after an uncertain commit is idempotent.
    assert await machine.transition(record.client_order_id, "CANCELED", "retry_terminal") is True
    assert await machine.transition(record.client_order_id, "UNKNOWN", "terminal_must_not_reopen") is False
    await persistence.close()

    with sqlite3.connect(tmp_path / "state.db") as connection:
        status = connection.execute(
            "SELECT status FROM orders WHERE client_order_id = 'order-transition-graph'"
        ).fetchone()[0]
        transitions = connection.execute(
            "SELECT from_status, to_status FROM order_state_transitions WHERE client_order_id = 'order-transition-graph'"
        ).fetchall()

    assert status == "CANCELED"
    assert transitions == [("NEW", "CANCELED")]


@pytest.mark.asyncio
async def test_order_recovery_replays_required_states_before_filled(tmp_path):
    persistence = StatePersistence(str(tmp_path / "state.db"))
    machine = PersistedOrderStateMachine(persistence)
    record = await machine.new_order(
        instance_id="instance-1",
        symbol="TRXEUR",
        side="buy",
        order_type="market",
        requested_qty=1.0,
        strategy_id="trend_momentum",
        decision_id="dec-recovery-graph",
        signal_id="sig-recovery-graph",
        client_order_id="order-recovery-graph",
    )

    assert await machine.recover_to_terminal(
        record.client_order_id,
        "FILLED",
        "recovered_terminal_from_exchange",
        exchange_order_id="paper-filled-1",
        filled_qty=1.0,
        avg_fill_price=0.2,
    ) is True
    await persistence.close()

    with sqlite3.connect(tmp_path / "state.db") as connection:
        status = connection.execute(
            "SELECT status FROM orders WHERE client_order_id = 'order-recovery-graph'"
        ).fetchone()[0]
        transitions = connection.execute(
            "SELECT from_status, to_status FROM order_state_transitions WHERE client_order_id = 'order-recovery-graph'"
        ).fetchall()

    assert status == "FILLED"
    assert transitions == [("NEW", "SENT"), ("SENT", "ACK"), ("ACK", "FILLED")]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("missing_field", "reason"),
    [
        ("strategy_id", "strategy_id_required"),
        ("decision_id", "decision_id_required"),
        ("signal_id", "signal_id_required"),
    ],
)
async def test_order_creation_rejects_missing_canonical_provenance(tmp_path, caplog, missing_field, reason):
    persistence = StatePersistence(str(tmp_path / "state.db"))
    await persistence.initialize()
    payload = dict(
        client_order_id="missing-strategy",
        instance_id="instance-1",
        symbol="TRXEUR",
        side="buy",
        order_type="market",
        requested_qty=1.0,
        strategy_id="trend_momentum",
        decision_id="dec-missing-field",
        signal_id="sig-missing-field",
    )
    payload.pop(missing_field)
    created = await persistence.upsert_order(**payload)
    await persistence.close()

    assert created is False
    assert reason in caplog.text
    with sqlite3.connect(tmp_path / "state.db") as connection:
        assert connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("strategy_id", "decision_id", "signal_id", "reason"),
    [
        ("", "dec-order", "sig-order", "strategy_id_required"),
        ("trend_momentum", None, "sig-order", "decision_id_required"),
        ("trend_momentum", "dec-order", None, "signal_id_required"),
    ],
)
async def test_order_state_machine_requires_canonical_provenance(
    tmp_path,
    strategy_id,
    decision_id,
    signal_id,
    reason,
):
    persistence = StatePersistence(str(tmp_path / "state.db"))
    machine = PersistedOrderStateMachine(persistence)

    with pytest.raises(ValueError, match=reason):
        await machine.new_order(
            instance_id="instance-1",
            symbol="TRXEUR",
            side="buy",
            order_type="market",
            requested_qty=1.0,
            strategy_id=strategy_id,
            decision_id=decision_id,
            signal_id=signal_id,
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
            decision_id="dec-persistence-rejected",
            signal_id="sig-persistence-rejected",
        )
    await persistence.close()


@pytest.mark.asyncio
async def test_position_close_reservation_and_durable_close_are_idempotent(tmp_path):
    db_path = tmp_path / "state.db"
    persistence = StatePersistence(str(db_path))
    assert await persistence.save_position(
        position_id="pos-close",
        instance_id="instance-close",
        buy_price=100.0,
        volume=0.1,
        status="open",
        strategy="trend_momentum",
        symbol="XETHZEUR",
    ) is True

    assert await persistence.reserve_position_close("pos-close") is True
    assert await persistence.reserve_position_close("pos-close") is False
    assert await persistence.release_position_close("pos-close") is True
    assert await persistence.reserve_position_close("pos-close") is True

    trade_data = {
        "instance_id": "instance-close",
        "price": 110.0,
        "volume": 0.1,
        "profit": 0.7,
        "timestamp": "2026-07-20T00:00:00+00:00",
    }
    instance_state = {
        "instance_id": "instance-close",
        "status": "running",
        "current_capital": 100.7,
        "allocated_capital": 0.0,
        "win_count": 1,
        "loss_count": 0,
        "initial_capital": 100.0,
    }
    assert await persistence.close_position_and_record_trade(
        "pos-close",
        trade_data,
        instance_state=instance_state,
    ) is True
    # A retry after an uncertain commit must not produce a second closing row.
    assert await persistence.close_position_and_record_trade(
        "pos-close",
        trade_data,
        instance_state=instance_state,
    ) is True
    await persistence.close()

    with sqlite3.connect(db_path) as connection:
        position_status = connection.execute(
            "SELECT status FROM positions WHERE id = 'pos-close'"
        ).fetchone()[0]
        closing_trades = connection.execute(
            "SELECT COUNT(*) FROM trades WHERE position_id = 'pos-close' AND side = 'sell'"
        ).fetchone()[0]
        state = connection.execute(
            "SELECT current_capital, allocated_capital, win_count, loss_count FROM instance_state WHERE instance_id = 'instance-close'"
        ).fetchone()

    assert position_status == "closed"
    assert closing_trades == 1
    assert state == pytest.approx((100.7, 0.0, 1, 0))
