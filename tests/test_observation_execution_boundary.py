"""Regression coverage for the research runtime's no-execution boundary."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from autobot.v2.observation_executor import (
    OBSERVATION_EXECUTION_DISABLED,
    ObservationOnlyOrderExecutor,
)
from autobot.v2.order_executor import OrderSide
from autobot.v2.orchestrator_async import _build_runtime_order_executor
from autobot.v2.runtime_execution_mode import (
    observation_only_runtime,
    paper_execution_authorized,
)
from autobot.v2.startup_attestation import StartupAttestation, _CheckOutcome


pytestmark = pytest.mark.unit


def test_paper_execution_requires_every_explicit_guard(monkeypatch):
    monkeypatch.setenv("PAPER_TRADING", "true")
    monkeypatch.setenv("PAPER_EXECUTION_ADAPTER_ENABLED", "true")
    monkeypatch.setenv("PAPER_EXECUTION_ROUTER_ENABLED", "true")
    monkeypatch.setenv("PAPER_TEST_TRADING_ENABLED", "false")
    monkeypatch.delenv("AUTOBOT_OBSERVATION_ONLY_RUNTIME", raising=False)

    assert paper_execution_authorized() is False
    assert observation_only_runtime() is True

    monkeypatch.setenv("PAPER_TEST_TRADING_ENABLED", "true")
    assert paper_execution_authorized() is True
    assert observation_only_runtime() is False

    monkeypatch.setenv("AUTOBOT_OBSERVATION_ONLY_RUNTIME", "true")
    assert observation_only_runtime() is True

    monkeypatch.setenv("AUTOBOT_OBSERVATION_ONLY_RUNTIME", "false")
    monkeypatch.setenv("PAPER_TEST_TRADING_ENABLED", "false")
    assert paper_execution_authorized() is False
    assert observation_only_runtime() is True


def test_executor_selection_fails_closed_without_full_paper_authorization(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    executor, mode = _build_runtime_order_executor(
        paper_mode=True,
        observation_only=False,
        paper_execution_enabled=False,
        api_key="must_not_be_used",
        api_secret="must_not_be_used",
    )

    assert isinstance(executor, ObservationOnlyOrderExecutor)
    assert mode == "observation_only"
    assert not (tmp_path / "data" / "paper_trades.db").exists()


def test_observation_executor_rejects_all_order_writes_without_a_wallet(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    async def _run():
        executor = ObservationOnlyOrderExecutor()
        result = await executor.execute_market_order("XXBTZEUR", OrderSide.BUY, 0.01)

        assert result.success is False
        assert result.error == OBSERVATION_EXECUTION_DISABLED
        assert await executor.get_balance() == {}
        assert await executor.get_open_orders() == {}
        assert await executor.cancel_order("any") is False
        recovery = await executor.get_open_orders_for_recovery()
        assert recovery.available is False
        assert recovery.reason == OBSERVATION_EXECUTION_DISABLED

    asyncio.run(_run())
    assert not (tmp_path / "data" / "paper_trades.db").exists()


def test_observation_attestation_skips_private_kraken_checks(monkeypatch, tmp_path):
    async def _run():
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("PAPER_TRADING", "true")
        monkeypatch.setenv("DEPLOYMENT_STAGE", "paper")
        monkeypatch.setenv("DASHBOARD_API_TOKEN", "test-token")
        monkeypatch.setenv("MAX_DRAWDOWN_PCT", "10")
        monkeypatch.setenv("RISK_PER_TRADE_PCT", "1")
        monkeypatch.setenv("MAX_POSITION_SIZE_PCT", "20")
        monkeypatch.setenv("LEAKED_SSH_KEY_ROTATED_ACK", "true")
        monkeypatch.setenv("KRAKEN_API_KEY_FINGERPRINT", "safe-test-key")

        gate = StartupAttestation(order_executor=None, kill_switch=object())
        monkeypatch.setattr(
            gate,
            "_check_public_exchange_connectivity",
            AsyncMock(return_value=_CheckOutcome(ok=True, message="public exchange ok")),
        )
        monkeypatch.setattr(gate, "_check_db_writable", lambda: _CheckOutcome(ok=True, message="db ok"))
        monkeypatch.setattr(gate, "_check_audit_writable", AsyncMock(return_value=_CheckOutcome(ok=True, message="audit ok")))
        monkeypatch.setattr(gate, "_check_clock_drift", AsyncMock(return_value=_CheckOutcome(ok=True, message="clock ok")))
        monkeypatch.setattr(gate, "_kill_switch_self_test", AsyncMock(return_value=_CheckOutcome(ok=True, message="kill ok")))

        private_auth = AsyncMock(side_effect=AssertionError("private auth must not run"))
        private_orders = AsyncMock(side_effect=AssertionError("private orders must not run"))
        private_reconciliation = AsyncMock(side_effect=AssertionError("private reconciliation must not run"))
        monkeypatch.setattr(gate, "_check_api_auth", private_auth)
        monkeypatch.setattr(gate, "_check_orders_endpoint", private_orders)
        monkeypatch.setattr(gate, "_check_reconciliation_baseline", private_reconciliation)

        result = await gate.run(observation_only=True)

        assert result.ok is True
        assert result.checks["execution_mode"] is True
        assert result.diagnostics["api_auth"]["reason"] == "ok"
        assert result.diagnostics["api_auth"]["message"] == "not applicable: observation-only runtime"
        private_auth.assert_not_awaited()
        private_orders.assert_not_awaited()
        private_reconciliation.assert_not_awaited()

    asyncio.run(_run())
