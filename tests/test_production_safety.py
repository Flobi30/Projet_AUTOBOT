import asyncio
import time

from autobot.v2.kill_switch import KillSwitch
from autobot.v2.order_router import OrderRouter, OrderPriority
from autobot.v2.order_state_machine import PersistedOrderStateMachine
from autobot.v2.persistence import StatePersistence
from autobot.v2.reconciliation_strict import StrictReconciliation


def test_duplicate_order_idempotency(monkeypatch):
    async def _run():
        router = OrderRouter(api_key="k", api_secret="s")
        await router.start()

        calls = {"n": 0}

        async def fake_execute(_request):
            calls["n"] += 1
            await asyncio.sleep(0.05)
            from autobot.v2.order_executor import OrderResult
            return OrderResult(success=True, txid="tx-1")

        monkeypatch.setattr(router, "_execute_request", fake_execute)

        order = {"type": "market", "symbol": "XXBTZEUR", "side": "buy", "volume": 0.01, "client_order_id": "cid-1"}
        r1, r2 = await asyncio.gather(
            router.submit(order, OrderPriority.ORDER),
            router.submit(order, OrderPriority.ORDER),
        )

        assert r1.success and r2.success
        assert calls["n"] == 1
        await router.stop()

    asyncio.run(_run())

def test_kill_switch_on_repeated_api_failures():
    async def _run():
        tripped = {"flag": False}

        async def cb(_event):
            tripped["flag"] = True

        ks = KillSwitch(on_trigger=cb, max_api_failures=3)
        await ks.record_api_failure("timeout")
        await ks.record_api_failure("timeout")
        await ks.record_api_failure("timeout")

        assert ks.tripped is True
        assert tripped["flag"] is True
        assert ks.last_event and ks.last_event.rule == "api_failures"

    asyncio.run(_run())

def test_partial_fill_stuck_triggers_kill_switch():
    async def _run():
        ks = KillSwitch(max_api_failures=99)
        ks.mark_partial("cid-1", now_ts=time.time() - 500)
        await ks.check_partial_stuck(time.time(), max_partial_age_s=180)
        assert ks.tripped is True
        assert ks.last_event and ks.last_event.rule == "partial_fill_stuck"
    asyncio.run(_run())


def test_restart_recovery_non_terminal_orders(tmp_path):
    db = tmp_path / "state.db"
    p = StatePersistence(str(db))
    osm = PersistedOrderStateMachine(p)

    rec = osm.new_order("inst-1", "XXBTZEUR", "buy", "market", 0.1)
    osm.transition(rec.client_order_id, "SENT", "send")

    recovered = osm.recover_non_terminal()
    ids = {o["client_order_id"] for o in recovered}
    assert rec.client_order_id in ids


def test_reconciliation_mismatch_detection():
    recon = StrictReconciliation(cash_abs_threshold=10, cash_rel_threshold=0.005)
    divs = recon.compare_balances(local_total=1000, exchange_total=900)
    assert divs and divs[0].severity == "critical"
    assert recon.should_kill_switch(divs)
