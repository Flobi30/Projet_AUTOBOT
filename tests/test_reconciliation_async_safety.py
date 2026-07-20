"""Fail-closed regression tests for the asynchronous reconciliation boundary."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from autobot.v2.global_kill_switch import GlobalKillSwitchStore
from autobot.v2.orchestrator_async import OrchestratorAsync
from autobot.v2.reconciliation_async import ReconciliationManagerAsync
from autobot.v2.reconciliation_models import Divergence


pytestmark = pytest.mark.unit


class _Executor:
    def __init__(self, *, statuses=None, closed_orders=None, open_orders=None):
        self.statuses = statuses or {}
        self.closed_orders = closed_orders or {}
        self.open_orders = open_orders or {}
        self.cancelled = []

    async def get_order_status(self, txid):
        return self.statuses.get(txid)

    async def get_closed_orders(self, **_kwargs):
        return self.closed_orders

    async def get_open_orders(self):
        return self.open_orders

    async def cancel_order(self, txid):
        self.cancelled.append(txid)
        return True


class _Instance:
    def __init__(self, positions):
        self.config = SimpleNamespace(symbol="XETHZEUR")
        self._positions = positions
        self.close_calls = []
        self.recalculate_calls = 0

    def recalculate_allocated_capital(self):
        self.recalculate_calls += 1

    def get_positions_snapshot(self):
        return list(self._positions)

    async def close_position(self, *args, **kwargs):
        self.close_calls.append((args, kwargs))


@pytest.mark.asyncio
async def test_missing_txid_is_quarantined_without_synthetic_close():
    instance = _Instance([{"id": "pos-missing", "status": "open", "buy_price": 100.0}])
    manager = ReconciliationManagerAsync(_Executor(), {"inst": instance})

    divergences = await manager.reconcile_all()

    assert instance.close_calls == []
    assert [(item.type, item.details["remediation"]) for item in divergences] == [
        ("orphan_local", "blocked_no_synthetic_close"),
    ]
    assert manager.get_stats()["last_critical_divergence_count"] == 1


@pytest.mark.asyncio
async def test_heuristic_external_sell_is_quarantined_without_local_pnl():
    instance = _Instance([{"id": "pos-buy", "status": "open", "txid": "buy-1"}])
    executor = _Executor(
        statuses={"buy-1": SimpleNamespace(status="closed", volume_exec=0.5)},
        closed_orders={
            "sell-unattributed": {
                "descr": {"type": "sell", "pair": "XETHZEUR"},
                "vol": 0.5,
                "avg_price": 111.0,
            }
        },
    )
    manager = ReconciliationManagerAsync(executor, {"inst": instance})

    divergences = await manager.reconcile_all()

    assert instance.close_calls == []
    assert [(item.type, item.details["remediation"]) for item in divergences] == [
        ("unattributed_external_sell", "blocked_no_heuristic_close"),
    ]


@pytest.mark.asyncio
async def test_orphaned_protective_order_is_detected_not_cancelled():
    executor = _Executor(
        open_orders={"stop-1": {"descr": {"ordertype": "stop-loss"}}},
    )
    manager = ReconciliationManagerAsync(executor, {"inst": _Instance([])})

    divergences = await manager.reconcile_all()

    assert executor.cancelled == []
    assert [(item.type, item.details["remediation"]) for item in divergences] == [
        ("orphan_exchange_order", "blocked_no_auto_cancel"),
    ]


@pytest.mark.asyncio
async def test_critical_divergence_notifies_the_fail_closed_callback():
    observed = []

    async def on_critical(divergences):
        observed.extend(divergences)

    manager = ReconciliationManagerAsync(
        _Executor(),
        {"inst": _Instance([{"id": "pos-missing", "status": "open"}])},
        on_critical_divergence=on_critical,
    )

    await manager.reconcile_all()

    assert [item.type for item in observed] == ["orphan_local"]


@pytest.mark.asyncio
async def test_orchestrator_persists_a_global_halt_for_critical_reconciliation(tmp_path):
    orchestrator = object.__new__(OrchestratorAsync)
    store = GlobalKillSwitchStore(str(tmp_path / "global_kill.db"))
    orchestrator._global_kill_store = store

    await orchestrator._on_critical_reconciliation_divergence([
        Divergence(
            type="orphan_exchange_order",
            position_id=None,
            kraken_txid="stop-1",
            details={},
            severity="critical",
        )
    ])

    state = store.get()
    assert state.tripped is True
    assert state.reason_code == "reconciliation_required"
