import asyncio

from autobot.v2.kill_switch import KillSwitch
from autobot.v2.global_kill_switch import GlobalKillSwitchStore
from autobot.v2.nonce_manager import NonceManager
from autobot.v2.startup_attestation import StartupAttestation


class DummyExecutor:
    def __init__(self, tmp_path):
        self._nonce_manager = NonceManager(str(tmp_path / "nonce.db"))

    async def get_balance(self):
        return {"ZEUR": 1000.0}

    async def get_open_orders(self):
        return {}

    async def _safe_api_call(self, method, **params):
        return True, {"result": {"c": ["100"]}}


def _base_env(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("PAPER_TRADING", "false")
    monkeypatch.setenv("DEPLOYMENT_STAGE", "micro_live")
    monkeypatch.setenv("LIVE_TRADING_CONFIRMATION", "true")
    monkeypatch.setenv("DASHBOARD_API_TOKEN", "tok")
    monkeypatch.setenv("MAX_DRAWDOWN_PCT", "10")
    monkeypatch.setenv("RISK_PER_TRADE_PCT", "1")
    monkeypatch.setenv("MAX_POSITION_SIZE_PCT", "20")
    monkeypatch.setenv("LEAKED_SSH_KEY_ROTATED_ACK", "true")
    monkeypatch.setenv("API_KEY_ASSIGNMENT_MODE", "dedicated")
    monkeypatch.setenv("ALLOW_SHARED_API_KEY", "false")
    monkeypatch.setenv("UNIQUE_BOT_ID", "bot-1")
    monkeypatch.setenv("API_KEY_ASSIGNED_BOT_ID", "bot-1")
    monkeypatch.setenv("MAX_LIVE_INSTANCES", "1")
    monkeypatch.delenv("KRAKEN_API_KEY_FINGERPRINT", raising=False)


def _patch_network_checks(monkeypatch, gate, exchange=True, clock=True, recon=True, auth=True, orders=True):
    async def _v(val):
        return val
    monkeypatch.setattr(gate, "_check_exchange_connectivity", lambda: _v(exchange))
    monkeypatch.setattr(gate, "_check_clock_drift", lambda: _v(clock))
    monkeypatch.setattr(gate, "_check_reconciliation_baseline", lambda: _v(recon))
    monkeypatch.setattr(gate, "_check_api_auth", lambda: _v(auth))
    monkeypatch.setattr(gate, "_check_orders_endpoint", lambda: _v(orders))


def _kill_switch(tmp_path):
    return KillSwitch(global_store=GlobalKillSwitchStore(str(tmp_path / "gks.db")))


def test_startup_blocked_invalid_app_env(monkeypatch, tmp_path):
    async def _run():
        _base_env(monkeypatch)
        monkeypatch.setenv("APP_ENV", "prodx")
        gate = StartupAttestation(DummyExecutor(tmp_path), _kill_switch(tmp_path))
        _patch_network_checks(monkeypatch, gate)
        res = await gate.run()
        assert res.ok is False
        assert res.checks["app_env_valid"] is False
    asyncio.run(_run())


def test_startup_blocked_live_confirmation_missing(monkeypatch, tmp_path):
    async def _run():
        _base_env(monkeypatch)
        monkeypatch.setenv("LIVE_TRADING_CONFIRMATION", "false")
        gate = StartupAttestation(DummyExecutor(tmp_path), _kill_switch(tmp_path))
        _patch_network_checks(monkeypatch, gate)
        res = await gate.run()
        assert res.ok is False
        assert res.checks["live_confirmation"] is False
    asyncio.run(_run())


def test_startup_blocked_auth_token_missing(monkeypatch, tmp_path):
    async def _run():
        _base_env(monkeypatch)
        monkeypatch.delenv("DASHBOARD_API_TOKEN", raising=False)
        gate = StartupAttestation(DummyExecutor(tmp_path), _kill_switch(tmp_path))
        _patch_network_checks(monkeypatch, gate)
        res = await gate.run()
        assert res.ok is False
        assert res.checks["dashboard_token"] is False
    asyncio.run(_run())


def test_startup_blocked_clock_drift(monkeypatch, tmp_path):
    async def _run():
        _base_env(monkeypatch)
        gate = StartupAttestation(DummyExecutor(tmp_path), _kill_switch(tmp_path))
        _patch_network_checks(monkeypatch, gate, clock=False)
        res = await gate.run()
        assert res.ok is False
        assert res.checks["clock_drift"] is False
    asyncio.run(_run())


def test_startup_blocked_exchange_health_check(monkeypatch, tmp_path):
    async def _run():
        _base_env(monkeypatch)
        gate = StartupAttestation(DummyExecutor(tmp_path), _kill_switch(tmp_path))
        _patch_network_checks(monkeypatch, gate, exchange=False)
        res = await gate.run()
        assert res.ok is False
        assert res.checks["exchange_connectivity"] is False
    asyncio.run(_run())


def test_startup_blocked_reconciliation_baseline(monkeypatch, tmp_path):
    async def _run():
        _base_env(monkeypatch)
        gate = StartupAttestation(DummyExecutor(tmp_path), _kill_switch(tmp_path))
        _patch_network_checks(monkeypatch, gate, recon=False)
        res = await gate.run()
        assert res.ok is False
        assert res.checks["reconciliation_baseline"] is False
    asyncio.run(_run())
