"""Regression coverage for the research runtime's no-execution boundary."""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock

import pytest

import autobot.v2.orchestrator_async as async_orchestrator
from autobot.v2.observation_executor import (
    OBSERVATION_EXECUTION_DISABLED,
    ObservationOnlyOrderExecutor,
)
from autobot.v2.order_executor import OrderExecutor, OrderSide
from autobot.v2.order_executor_async import OrderExecutorAsync
from autobot.v2.order_router import (
    OBSERVATION_ORDER_ROUTER_DISABLED,
    OrderRouter,
)
from autobot.v2.paper_trading import (
    OrderExecutorAsyncWithPaper,
    get_paper_executor,
    reset_paper_executor,
)
from autobot.v2.orchestrator_async import (
    OrchestratorAsync,
    _build_runtime_order_executor,
    _exchange_reconciliation_enabled,
)
from autobot.v2.reconciliation import (
    LegacyReconciliationQuarantinedError,
    ReconciliationManager,
)
from autobot.v2.runtime_execution_mode import (
    ObservationOnlyExecutionComponentDisabled,
    observation_only_runtime,
    paper_execution_authorized,
    runtime_exchange_credentials,
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


def test_observation_runtime_defaults_closed_until_an_execution_authorization_is_complete(monkeypatch):
    for name in (
        "AUTOBOT_OBSERVATION_ONLY_RUNTIME",
        "PAPER_TRADING",
        "PAPER_EXECUTION_ADAPTER_ENABLED",
        "PAPER_EXECUTION_ROUTER_ENABLED",
        "PAPER_TEST_TRADING_ENABLED",
        "LIVE_TRADING_CONFIRMATION",
        "STRATEGY_ROUTER_LIVE_ENABLED",
        "AUTOBOT_REAL_ORDER_EXECUTION_ENABLED",
        "PREFLIGHT_ONLY",
    ):
        monkeypatch.delenv(name, raising=False)

    assert observation_only_runtime() is True

    # A manually cleared observation lock is not itself an authorization.
    monkeypatch.setenv("AUTOBOT_OBSERVATION_ONLY_RUNTIME", "false")
    assert observation_only_runtime() is True

    for name, value in {
        "PAPER_TRADING": "false",
        "LIVE_TRADING_CONFIRMATION": "true",
        "STRATEGY_ROUTER_LIVE_ENABLED": "true",
        "AUTOBOT_REAL_ORDER_EXECUTION_ENABLED": "true",
        "PREFLIGHT_ONLY": "false",
    }.items():
        monkeypatch.setenv(name, value)
    assert observation_only_runtime() is False

    # The explicit lock remains authoritative even over a complete future
    # authorization configuration.
    monkeypatch.setenv("AUTOBOT_OBSERVATION_ONLY_RUNTIME", "true")
    assert observation_only_runtime() is True


def test_observation_runtime_never_starts_private_exchange_reconciliation():
    assert _exchange_reconciliation_enabled(observation_only=True) is False
    assert _exchange_reconciliation_enabled(observation_only=False) is True


def test_observation_runtime_rejects_legacy_private_capital_lookup(monkeypatch):
    monkeypatch.setenv("AUTOBOT_OBSERVATION_ONLY_RUNTIME", "true")

    with pytest.raises(ObservationOnlyExecutionComponentDisabled, match="legacy async capital lookup"):
        async_orchestrator._get_available_capital_real(
            api_key="must-not-be-used",
            api_secret="must-not-be-used",
        )


def test_observation_runtime_discards_private_credentials_before_component_construction(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "environment-key-must-not-survive")
    monkeypatch.setenv("KRAKEN_API_SECRET", "environment-secret-must-not-survive")

    api_key, api_secret = runtime_exchange_credentials(
        "argument-key-must-not-survive",
        "argument-secret-must-not-survive",
        observation_only=True,
    )

    assert api_key is None
    assert api_secret is None
    assert "KRAKEN_API_KEY" not in os.environ
    assert "KRAKEN_API_SECRET" not in os.environ


def test_non_observation_runtime_preserves_explicit_credentials(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "environment-key")
    monkeypatch.setenv("KRAKEN_API_SECRET", "environment-secret")

    api_key, api_secret = runtime_exchange_credentials(
        "explicit-key",
        "explicit-secret",
        observation_only=False,
    )

    assert (api_key, api_secret) == ("explicit-key", "explicit-secret")
    assert os.environ["KRAKEN_API_KEY"] == "environment-key"
    assert os.environ["KRAKEN_API_SECRET"] == "environment-secret"


def test_direct_observation_orchestrator_never_forwards_credentials_to_public_websocket(
    monkeypatch,
    tmp_path,
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AUTOBOT_OBSERVATION_ONLY_RUNTIME", "true")
    monkeypatch.setenv("PAPER_TRADING", "true")
    monkeypatch.setenv("KRAKEN_API_KEY", "environment-key-must-not-survive")
    monkeypatch.setenv("KRAKEN_API_SECRET", "environment-secret-must-not-survive")

    orchestrator = OrchestratorAsync(
        api_key="argument-key-must-not-survive",
        api_secret="argument-secret-must-not-survive",
    )

    assert orchestrator.api_key is None
    assert orchestrator.api_secret is None
    assert orchestrator.ring_dispatcher._ws.api_key is None
    assert orchestrator.ring_dispatcher._ws.api_secret is None
    assert "KRAKEN_API_KEY" not in os.environ
    assert "KRAKEN_API_SECRET" not in os.environ


def test_legacy_order_router_cannot_construct_an_executor_or_submit_in_observation_mode(monkeypatch):
    async def _run():
        monkeypatch.setenv("AUTOBOT_OBSERVATION_ONLY_RUNTIME", "true")
        router = OrderRouter(api_key="must-not-be-used", api_secret="must-not-be-used")

        assert router._executor is None
        await router.start()
        assert router.is_running() is False

        for request in (
            {"type": "market", "symbol": "XXBTZEUR", "side": "buy", "volume": 0.01},
            {"type": "cancel", "txid": "must-not-be-used"},
            {"type": "balance"},
        ):
            result = await router.submit(request)
            assert result.success is False
            assert result.error == OBSERVATION_ORDER_ROUTER_DISABLED

        assert router.get_queue_size() == 0

    asyncio.run(_run())


def test_legacy_sync_reconciliation_cannot_be_constructed_in_observation_mode(monkeypatch):
    monkeypatch.setenv("AUTOBOT_OBSERVATION_ONLY_RUNTIME", "true")

    with pytest.raises(
        LegacyReconciliationQuarantinedError,
        match="legacy_sync_reconciliation_retired_in_observation_runtime",
    ):
        ReconciliationManager(order_executor=object(), instances={})


def test_direct_private_executors_cannot_be_constructed_in_observation_mode(monkeypatch):
    monkeypatch.setenv("AUTOBOT_OBSERVATION_ONLY_RUNTIME", "true")

    with pytest.raises(ObservationOnlyExecutionComponentDisabled, match="OrderExecutorAsync"):
        OrderExecutorAsync(api_key="must-not-be-used", api_secret="must-not-be-used")
    with pytest.raises(ObservationOnlyExecutionComponentDisabled, match="OrderExecutor"):
        OrderExecutor(api_key="must-not-be-used", api_secret="must-not-be-used")


def test_operational_paper_entrypoints_cannot_bypass_observation_mode(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTOBOT_OBSERVATION_ONLY_RUNTIME", "true")
    reset_paper_executor()

    with pytest.raises(ObservationOnlyExecutionComponentDisabled, match="OrderExecutorAsyncWithPaper"):
        OrderExecutorAsyncWithPaper(paper_mode=True)

    db_path = tmp_path / "paper_trades.db"
    with pytest.raises(ObservationOnlyExecutionComponentDisabled, match="get_paper_executor"):
        get_paper_executor(db_path=str(db_path))

    assert not db_path.exists()


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


def test_observation_attestation_does_not_require_paper_or_live_confirmation(monkeypatch, tmp_path):
    async def _run():
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("PAPER_TRADING", "false")
        monkeypatch.setenv("LIVE_TRADING_CONFIRMATION", "false")
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

        result = await gate.run(observation_only=True)

        assert result.ok is True
        assert result.checks["live_confirmation"] is True
        assert result.diagnostics["live_confirmation"]["message"] == "not applicable: observation-only runtime cannot execute"

    asyncio.run(_run())
