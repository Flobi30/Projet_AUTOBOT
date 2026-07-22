"""Fail-closed cold-restart recovery regressions.

These checks exercise only hermetic fakes and local SQLite files.  They never
create an exchange order or activate paper capital.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from autobot.v2.global_kill_switch import GlobalKillSwitchStore
from autobot.v2.kill_switch import KillSwitch
from autobot.v2.order_executor import OrderStatus
from autobot.v2.order_executor_async import (
    OrderCollectionRecovery,
    OrderExecutorAsync,
    OrderRecoveryLookup,
    OrderRecoveryLookupState,
)
from autobot.v2.order_state_machine import PersistedOrderStateMachine
from autobot.v2.persistence import NonTerminalOrderRecovery, StatePersistence
from autobot.v2.reconciliation_async import ReconciliationManagerAsync
from autobot.v2.signal_handler_async import SignalHandlerAsync
from autobot.v2.startup_attestation import StartupAttestation


pytestmark = pytest.mark.unit


def _recovery_executor(safe_api_call):
    executor = object.__new__(OrderExecutorAsync)
    executor._safe_api_call = safe_api_call
    return executor


@pytest.mark.asyncio
async def test_recovery_lookup_distinguishes_confirmed_absence_from_api_unavailable():
    async def absent(_method, **_params):
        return True, {"result": {}}

    async def unavailable(_method, **_params):
        return False, {"error": ["temporary failure"]}

    absent_lookup = await _recovery_executor(absent).get_order_status_for_recovery("tx-absent")
    unavailable_lookup = await _recovery_executor(unavailable).get_order_status_for_recovery("tx-unknown")

    assert absent_lookup.state is OrderRecoveryLookupState.CONFIRMED_ABSENT
    assert unavailable_lookup.state is OrderRecoveryLookupState.UNAVAILABLE


class _RecoveryOSM:
    def __init__(self) -> None:
        self.transitions = []
        self.unknown = []

    async def recover_non_terminal(self):
        return [{
            "client_order_id": "cold-restart-order",
            "exchange_order_id": "tx-cold-restart",
            "userref": 12,
            "symbol": "XETHZEUR",
        }]

    async def transition(self, *args, **kwargs):
        self.transitions.append((args, kwargs))
        return True

    async def recover_to_terminal(self, *args, **kwargs):
        self.transitions.append((args, kwargs))
        return True

    async def mark_recovery_unknown(self, *args, **kwargs):
        self.unknown.append((args, kwargs))
        return True


class _RecoveryExecutor:
    def __init__(self, lookup: OrderRecoveryLookup) -> None:
        self.lookup = lookup

    async def get_order_status_for_recovery(self, _txid):
        return self.lookup


def _handler_for_recovery(tmp_path, lookup: OrderRecoveryLookup):
    handler = object.__new__(SignalHandlerAsync)
    handler.instance = SimpleNamespace(id="cold-restart-instance")
    handler.order_executor = _RecoveryExecutor(lookup)
    handler._osm = _RecoveryOSM()
    handler._kill_switch = KillSwitch(global_store=GlobalKillSwitchStore(str(tmp_path / "global_kill.db")))
    handler._record_runtime_event = lambda *_args, **kwargs: kwargs
    return handler


@pytest.mark.asyncio
async def test_ambiguous_recovery_marks_unknown_and_trips_global_latch(tmp_path):
    handler = _handler_for_recovery(
        tmp_path,
        OrderRecoveryLookup(
            state=OrderRecoveryLookupState.UNAVAILABLE,
            reason="query_orders_unavailable",
        ),
    )

    await handler.recover()

    assert handler._osm.transitions == []
    assert handler._osm.unknown == [
        (("cold-restart-order", "recovery_exchange_lookup_unavailable"), {})
    ]
    assert handler._kill_switch.tripped is True
    assert handler._kill_switch.global_state().tripped is True


@pytest.mark.asyncio
async def test_confirmed_absence_can_reach_rejected_without_tripping_latch(tmp_path):
    handler = _handler_for_recovery(
        tmp_path,
        OrderRecoveryLookup(
            state=OrderRecoveryLookupState.CONFIRMED_ABSENT,
            reason="query_orders_confirmed_absent",
        ),
    )

    await handler.recover()

    assert handler._osm.unknown == []
    assert handler._osm.transitions == [
        (("cold-restart-order", "REJECTED", "not_found_on_exchange_after_crash"), {})
    ]
    assert handler._kill_switch.tripped is False


@pytest.mark.asyncio
async def test_unavailable_pending_order_ledger_trips_before_any_exchange_lookup(tmp_path):
    handler = _handler_for_recovery(
        tmp_path,
        OrderRecoveryLookup(OrderRecoveryLookupState.FOUND, txid="unexpected"),
    )

    class _UnavailableRecoveryOSM(_RecoveryOSM):
        async def recover_non_terminal_for_recovery(self):
            return NonTerminalOrderRecovery(False, [], "sqlite_locked")

    handler._osm = _UnavailableRecoveryOSM()
    await handler.recover()

    assert handler._osm.transitions == []
    assert handler._osm.unknown == []
    assert handler._kill_switch.global_state().tripped is True
    assert handler._kill_switch.global_state().reason_code == "order_recovery_ledger_unavailable"


@pytest.mark.asyncio
async def test_new_order_recovery_replays_sent_then_unknown_and_keeps_duplicate_guard(tmp_path):
    persistence = StatePersistence(str(tmp_path / "state.db"))
    machine = PersistedOrderStateMachine(persistence)
    record = await machine.new_order(
        instance_id="cold-restart-instance",
        symbol="XETHZEUR",
        side="buy",
        order_type="market",
        requested_qty=1.0,
        strategy_id="trend_momentum",
        decision_id="dec-cold-restart",
        signal_id="sig-cold-restart",
        client_order_id="cold-restart-order",
    )

    assert await machine.mark_recovery_unknown(record.client_order_id, "exchange_lookup_unavailable")
    recovered = await machine.get(record.client_order_id)

    assert recovered is not None
    assert recovered["status"] == "UNKNOWN"
    assert await machine.is_duplicate_active("XETHZEUR", "buy") is True
    await persistence.close()


@pytest.mark.asyncio
async def test_pending_order_recovery_reports_sqlite_failure_explicitly(monkeypatch, tmp_path):
    persistence = StatePersistence(str(tmp_path / "state.db"))
    await persistence.initialize()

    async def fail_get_conn():
        raise RuntimeError("sqlite unavailable")

    monkeypatch.setattr(persistence.orders, "get_conn", fail_get_conn)
    outcome = await PersistedOrderStateMachine(persistence).recover_non_terminal_for_recovery()
    await persistence.close()

    assert outcome.available is False
    assert outcome.orders == []
    assert outcome.reason == "order_recovery_ledger_unavailable:RuntimeError"


@pytest.mark.asyncio
async def test_startup_attestation_blocks_a_persisted_global_kill_switch(tmp_path):
    store = GlobalKillSwitchStore(str(tmp_path / "global_kill.db"))
    switch = KillSwitch(global_store=store)
    await switch.trigger("order_recovery_unknown", "fixture")

    outcome = await StartupAttestation(order_executor=None, kill_switch=switch)._kill_switch_self_test(False)

    assert outcome.ok is False
    assert outcome.reason == "global_kill_switch_already_tripped"


class _ReconciliationExecutor:
    def __init__(self, lookup: OrderRecoveryLookup, open_orders: OrderCollectionRecovery) -> None:
        self.lookup = lookup
        self.open_orders = open_orders

    async def get_order_status_for_recovery(self, _txid):
        return self.lookup

    async def get_open_orders_for_recovery(self):
        return self.open_orders


class _ReconciliationInstance:
    config = SimpleNamespace(symbol="XETHZEUR")

    @staticmethod
    def recalculate_allocated_capital():
        return None

    @staticmethod
    def get_positions_snapshot():
        return [{"id": "pos-cold-restart", "status": "open", "txid": "tx-cold-restart"}]


@pytest.mark.asyncio
async def test_reconciliation_turns_unavailable_exchange_order_evidence_into_critical_divergence():
    executor = _ReconciliationExecutor(
        OrderRecoveryLookup(OrderRecoveryLookupState.UNAVAILABLE, reason="query_orders_unavailable"),
        OrderCollectionRecovery(True, {}),
    )
    manager = ReconciliationManagerAsync(executor, {"cold-restart": _ReconciliationInstance()})

    divergences = await manager.reconcile_all()

    assert [(item.type, item.details["remediation"]) for item in divergences] == [
        ("exchange_order_status_unavailable", "halt_pending_exchange_recovery"),
    ]


@pytest.mark.asyncio
async def test_reconciliation_turns_unavailable_open_orders_into_critical_divergence():
    executor = _ReconciliationExecutor(
        OrderRecoveryLookup(OrderRecoveryLookupState.FOUND, txid="tx-cold-restart", status=OrderStatus("tx-cold-restart", "open", 1.0, 0.0)),
        OrderCollectionRecovery(False, {}, reason="open_orders_unavailable"),
    )
    manager = ReconciliationManagerAsync(executor, {})

    divergences = await manager.reconcile_all()

    assert [(item.type, item.details["remediation"]) for item in divergences] == [
        ("exchange_open_orders_unavailable", "halt_pending_exchange_recovery"),
    ]
