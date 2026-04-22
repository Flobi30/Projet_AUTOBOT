import pytest

import asyncio

from autobot.v2.global_kill_switch import GlobalKillSwitchStore
from autobot.v2.kill_switch import KillSwitch
from autobot.v2.reconciliation_strict import StrictReconciliation
from autobot.v2.startup_attestation import StartupAttestation
from autobot.v2.nonce_manager import NonceManager


pytestmark = pytest.mark.integration

class DummyExecutor:
    def __init__(self, tmp_path):
        self._nonce_manager = NonceManager(str(tmp_path / "nonce.db"))

    async def get_balance(self):
        return {"ZEUR": 1000.0}

    async def get_open_orders(self):
        return {}

    async def _safe_api_call(self, method, **params):
        return True, {"result": {"c": ["100"]}}


def _set_minimum_env(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DASHBOARD_API_TOKEN", "tok")
    monkeypatch.setenv("MAX_DRAWDOWN_PCT", "10")
    monkeypatch.setenv("RISK_PER_TRADE_PCT", "1")
    monkeypatch.setenv("MAX_POSITION_SIZE_PCT", "20")
    monkeypatch.setenv("LEAKED_SSH_KEY_ROTATED_ACK", "true")
    monkeypatch.setenv("LIVE_TRADING_CONFIRMATION", "true")
    monkeypatch.setenv("PAPER_TRADING", "false")


def test_multi_instance_shared_key_unsafe_block(monkeypatch, tmp_path):
    async def _run():
        _set_minimum_env(monkeypatch)
        monkeypatch.setenv("DEPLOYMENT_STAGE", "micro_live")
        monkeypatch.setenv("ALLOW_SHARED_API_KEY", "true")
        monkeypatch.setenv("API_KEY_ASSIGNMENT_MODE", "dedicated")
        monkeypatch.setenv("UNIQUE_BOT_ID", "bot-a")
        monkeypatch.setenv("API_KEY_ASSIGNED_BOT_ID", "bot-a")

        gate = StartupAttestation(DummyExecutor(tmp_path), KillSwitch())
        async def _true():
            return True
        for fn in ("_check_exchange_connectivity", "_check_clock_drift", "_check_reconciliation_baseline", "_check_api_auth", "_check_orders_endpoint"):
            monkeypatch.setattr(gate, fn, _true)

        result = await gate.run()
        assert result.ok is False
        assert result.checks["shared_key_guard"] is False

    asyncio.run(_run())


def test_global_kill_switch_propagation(tmp_path):
    async def _run():
        store = GlobalKillSwitchStore(str(tmp_path / "gks.db"))
        ks1 = KillSwitch(global_store=store)
        ks2 = KillSwitch(global_store=store)
        await ks1.trigger("api_failures", "boom")
        assert ks2.is_globally_tripped() is True
    asyncio.run(_run())


def test_reconciliation_mismatch_fills_fees_pnl():
    recon = StrictReconciliation()
    divs = recon.compare_fills_fees_pnl(
        local={"realized_pnl": 10.0, "unrealized_pnl": 2.0, "fees": 0.2},
        exchange={"realized_pnl": 40.0, "unrealized_pnl": 20.0, "fees": 8.0},
        pnl_abs_threshold=5.0,
        fee_abs_threshold=1.0,
    )
    assert any(d.category == "realized_pnl" and d.severity == "critical" for d in divs)
    assert any(d.category == "fees" and d.severity == "critical" for d in divs)


def test_promotion_gate_failure_missing_controls(monkeypatch, tmp_path):
    async def _run():
        _set_minimum_env(monkeypatch)
        monkeypatch.setenv("DEPLOYMENT_STAGE", "small_live")
        monkeypatch.setenv("API_KEY_ASSIGNMENT_MODE", "dedicated")
        monkeypatch.setenv("UNIQUE_BOT_ID", "bot-1")
        monkeypatch.setenv("API_KEY_ASSIGNED_BOT_ID", "bot-1")
        monkeypatch.setenv("ALLOW_SHARED_API_KEY", "false")
        monkeypatch.setenv("SMALL_LIVE_APPROVED", "false")

        gate = StartupAttestation(DummyExecutor(tmp_path), KillSwitch())
        async def _true():
            return True
        for fn in ("_check_exchange_connectivity", "_check_clock_drift", "_check_reconciliation_baseline", "_check_api_auth", "_check_orders_endpoint"):
            monkeypatch.setattr(gate, fn, _true)

        result = await gate.run()
        assert result.ok is False
        assert result.checks["promotion_gate"] is False
    asyncio.run(_run())

