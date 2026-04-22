import asyncio
import json

import aiohttp

from autobot.v2.kill_switch import KillSwitch
from autobot.v2.nonce_manager import NonceManager
from autobot.v2.startup_attestation import StartupAttestation, _CheckOutcome


class DummyExecutor:
    def __init__(self, tmp_path, failures=None):
        self._nonce_manager = NonceManager(str(tmp_path / "nonce.db"))
        self.failures = failures or {}

    async def get_balance(self):
        err = self.failures.get("get_balance")
        if err:
            raise err
        return {"ZEUR": 1000.0}

    async def get_open_orders(self):
        err = self.failures.get("get_open_orders")
        if err:
            raise err
        return {}

    async def _safe_api_call(self, method, **params):
        err = self.failures.get("_safe_api_call")
        if err:
            raise err
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
    async def _v(name, val):
        if val:
            return _CheckOutcome(ok=True, reason="ok", message=f"{name} ok")
        return _CheckOutcome(ok=False, reason=f"{name}_failed", message=f"{name} failed")
    if exchange is not None:
        monkeypatch.setattr(gate, "_check_exchange_connectivity", lambda: _v("exchange_connectivity", exchange))
    if clock is not None:
        monkeypatch.setattr(gate, "_check_clock_drift", lambda: _v("clock_drift", clock))
    if recon is not None:
        monkeypatch.setattr(gate, "_check_reconciliation_baseline", lambda: _v("reconciliation_baseline", recon))
    if auth is not None:
        monkeypatch.setattr(gate, "_check_api_auth", lambda: _v("api_auth", auth))
    if orders is not None:
        monkeypatch.setattr(gate, "_check_orders_endpoint", lambda: _v("orders_endpoint", orders))


def test_startup_blocked_invalid_app_env(monkeypatch, tmp_path):
    async def _run():
        _base_env(monkeypatch)
        monkeypatch.setenv("APP_ENV", "prodx")
        gate = StartupAttestation(DummyExecutor(tmp_path), KillSwitch())
        _patch_network_checks(monkeypatch, gate)
        res = await gate.run()
        assert res.ok is False
        assert res.checks["app_env_valid"] is False
        assert "invalid_app_env" in res.reasons
    asyncio.run(_run())


def test_startup_blocked_live_confirmation_missing(monkeypatch, tmp_path):
    async def _run():
        _base_env(monkeypatch)
        monkeypatch.setenv("LIVE_TRADING_CONFIRMATION", "false")
        gate = StartupAttestation(DummyExecutor(tmp_path), KillSwitch())
        _patch_network_checks(monkeypatch, gate)
        res = await gate.run()
        assert res.ok is False
        assert res.checks["live_confirmation"] is False
        assert "live_confirmation_missing" in res.reasons
    asyncio.run(_run())


def test_startup_blocked_auth_token_missing(monkeypatch, tmp_path):
    async def _run():
        _base_env(monkeypatch)
        monkeypatch.delenv("DASHBOARD_API_TOKEN", raising=False)
        gate = StartupAttestation(DummyExecutor(tmp_path), KillSwitch())
        _patch_network_checks(monkeypatch, gate)
        res = await gate.run()
        assert res.ok is False
        assert res.checks["dashboard_token"] is False
        assert "dashboard_token_missing" in res.reasons
    asyncio.run(_run())


def test_startup_blocked_clock_drift(monkeypatch, tmp_path):
    async def _run():
        _base_env(monkeypatch)
        gate = StartupAttestation(DummyExecutor(tmp_path), KillSwitch())
        _patch_network_checks(monkeypatch, gate, clock=False)
        res = await gate.run()
        assert res.ok is False
        assert res.checks["clock_drift"] is False
        assert "clock_drift_failed" in res.reasons
    asyncio.run(_run())


def test_startup_blocked_exchange_health_check(monkeypatch, tmp_path):
    async def _run():
        _base_env(monkeypatch)
        gate = StartupAttestation(DummyExecutor(tmp_path), KillSwitch())
        _patch_network_checks(monkeypatch, gate, exchange=False)
        res = await gate.run()
        assert res.ok is False
        assert res.checks["exchange_connectivity"] is False
        assert "exchange_connectivity_failed" in res.reasons
    asyncio.run(_run())


def test_startup_blocked_reconciliation_baseline(monkeypatch, tmp_path):
    async def _run():
        _base_env(monkeypatch)
        gate = StartupAttestation(DummyExecutor(tmp_path), KillSwitch())
        _patch_network_checks(monkeypatch, gate, recon=False)
        res = await gate.run()
        assert res.ok is False
        assert res.checks["reconciliation_baseline"] is False
        assert "reconciliation_baseline_failed" in res.reasons
    asyncio.run(_run())


def test_attestation_report_json_serializable(monkeypatch, tmp_path):
    async def _run():
        _base_env(monkeypatch)
        gate = StartupAttestation(DummyExecutor(tmp_path), KillSwitch())
        _patch_network_checks(monkeypatch, gate)
        result = await gate.run()
        payload = json.loads(result.to_json())
        assert payload["status"] == "pass"
        assert payload["ok"] is True
        assert payload["diagnostics"]["app_env_valid"]["status"] == "pass"
    asyncio.run(_run())


def test_failure_reason_network_error(monkeypatch, tmp_path):
    async def _run():
        _base_env(monkeypatch)
        executor = DummyExecutor(tmp_path, failures={"_safe_api_call": aiohttp.ClientError("boom")})
        gate = StartupAttestation(executor, KillSwitch())
        _patch_network_checks(monkeypatch, gate, exchange=None, clock=True, recon=True, auth=True, orders=True)
        res = await gate.run()
        assert res.checks["exchange_connectivity"] is False
        assert "exchange_connectivity_network_error" in res.reasons
        assert res.diagnostics["exchange_connectivity"]["error_code"] == "network"
    asyncio.run(_run())


def test_failure_reason_auth_error(monkeypatch, tmp_path):
    async def _run():
        _base_env(monkeypatch)
        executor = DummyExecutor(tmp_path, failures={"get_balance": PermissionError("denied")})
        gate = StartupAttestation(executor, KillSwitch())
        _patch_network_checks(monkeypatch, gate, exchange=True, clock=True, recon=True, auth=None, orders=True)
        res = await gate.run()
        assert res.checks["api_auth"] is False
        assert "api_auth_permission_denied" in res.reasons
        assert res.diagnostics["api_auth"]["error_code"] == "auth"
    asyncio.run(_run())


def test_failure_reason_timeout_error(monkeypatch, tmp_path):
    async def _run():
        _base_env(monkeypatch)
        executor = DummyExecutor(tmp_path, failures={"get_open_orders": asyncio.TimeoutError()})
        gate = StartupAttestation(executor, KillSwitch())
        _patch_network_checks(monkeypatch, gate, exchange=True, clock=True, recon=True, auth=True, orders=None)
        res = await gate.run()
        assert res.checks["orders_endpoint"] is False
        assert "orders_endpoint_timeout" in res.reasons
        assert res.diagnostics["orders_endpoint"]["error_code"] == "timeout"
    asyncio.run(_run())


def test_failure_reason_io_error(monkeypatch, tmp_path):
    async def _run():
        _base_env(monkeypatch)
        gate = StartupAttestation(DummyExecutor(tmp_path), KillSwitch())
        _patch_network_checks(monkeypatch, gate)

        class FailingNonce:
            def next_nonce(self, _key):
                raise OSError("disk full")

        gate.order_executor._nonce_manager = FailingNonce()
        res = await gate.run()
        assert res.checks["nonce_health"] is False
        assert "nonce_io_error" in res.reasons
        assert res.diagnostics["nonce_health"]["error_code"] == "io"
    asyncio.run(_run())
