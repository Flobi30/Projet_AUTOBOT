"""Fail-closed tests for the real Kraken execution boundary."""

import asyncio

import pytest

from autobot.v2 import orchestrator_async
from autobot.v2.order_executor import OrderExecutor
from autobot.v2.order_executor_async import OrderExecutorAsync
from autobot.v2.runtime_execution_mode import ObservationOnlyExecutionComponentDisabled


pytestmark = pytest.mark.unit


def _clear_execution_flags(monkeypatch):
    for name in (
        "AUTOBOT_OBSERVATION_ONLY_RUNTIME",
        "PAPER_TRADING",
        "LIVE_TRADING_CONFIRMATION",
        "STRATEGY_ROUTER_LIVE_ENABLED",
        "AUTOBOT_REAL_ORDER_EXECUTION_ENABLED",
        "PREFLIGHT_ONLY",
    ):
        monkeypatch.delenv(name, raising=False)


def test_real_add_order_is_blocked_without_explicit_authorization(monkeypatch):
    async def _run():
        _clear_execution_flags(monkeypatch)
        monkeypatch.setattr(
            "autobot.v2.order_executor_async.reject_private_execution_component",
            lambda _component: None,
        )
        executor = OrderExecutorAsync(api_key="test-key", api_secret="c2VjcmV0")
        called = False

        async def _unexpected_query(*_args, **_kwargs):
            nonlocal called
            called = True
            return {"error": []}

        monkeypatch.setattr(executor, "_query_private", _unexpected_query)
        success, response = await executor._safe_api_call("AddOrder", pair="XXBTZEUR")

        assert success is False
        assert response["error_code"] == "REAL_ORDER_MUTATION_BLOCKED"
        assert called is False

    asyncio.run(_run())


def test_real_cancel_order_is_blocked_without_explicit_authorization(monkeypatch):
    async def _run():
        _clear_execution_flags(monkeypatch)
        monkeypatch.setattr(
            "autobot.v2.order_executor_async.reject_private_execution_component",
            lambda _component: None,
        )
        executor = OrderExecutorAsync(api_key="test-key", api_secret="c2VjcmV0")
        called = False

        async def _unexpected_query(*_args, **_kwargs):
            nonlocal called
            called = True
            return {"error": []}

        monkeypatch.setattr(executor, "_query_private", _unexpected_query)
        success, response = await executor._safe_api_call("CancelOrder", txid="test")

        assert success is False
        assert response["error_code"] == "REAL_ORDER_MUTATION_BLOCKED"
        assert called is False

    asyncio.run(_run())


def test_program_execution_lock_blocks_real_mutation_even_with_every_legacy_flag(monkeypatch):
    async def _run():
        for name, value in {
            "PAPER_TRADING": "false",
            "LIVE_TRADING_CONFIRMATION": "true",
            "STRATEGY_ROUTER_LIVE_ENABLED": "true",
            "AUTOBOT_REAL_ORDER_EXECUTION_ENABLED": "true",
            "PREFLIGHT_ONLY": "false",
        }.items():
            monkeypatch.setenv(name, value)

        monkeypatch.setattr(
            "autobot.v2.order_executor_async.reject_private_execution_component",
            lambda _component: None,
        )
        executor = OrderExecutorAsync(api_key="test-key", api_secret="c2VjcmV0")
        calls = []

        async def _authorized_query(method, **params):
            calls.append((method, params))
            return {"error": [], "result": {"count": 1}}

        monkeypatch.setattr(executor, "_query_private", _authorized_query)
        monkeypatch.setattr(executor, "_rate_limit", lambda: asyncio.sleep(0))
        success, response = await executor._safe_api_call("CancelOrder", txid="test")

        assert success is False
        assert response["error_code"] == "REAL_ORDER_MUTATION_BLOCKED"
        assert calls == []

    asyncio.run(_run())


def test_sync_executor_cannot_bypass_real_mutation_guard(monkeypatch):
    _clear_execution_flags(monkeypatch)
    monkeypatch.setattr(
        "autobot.v2.order_executor.reject_private_execution_component",
        lambda _component: None,
    )
    executor = OrderExecutor(api_key="test-key", api_secret="test-secret")
    queried = False

    def _unexpected_client():
        nonlocal queried
        queried = True
        raise AssertionError("blocked mutation must not create a Kraken client")

    monkeypatch.setattr(executor, "_get_client", _unexpected_client)
    success, response = executor._safe_api_call("AddOrder", pair="XXBTZEUR")

    assert success is False
    assert response["error_code"] == "REAL_ORDER_MUTATION_BLOCKED"
    assert queried is False


def test_sync_private_client_rejects_constructor_bypass_before_object_state_access():
    executor = object.__new__(OrderExecutor)

    with pytest.raises(ObservationOnlyExecutionComponentDisabled, match="disabled"):
        executor._get_client()


def test_async_private_query_rejects_constructor_bypass_before_object_state_access():
    async def _run():
        executor = object.__new__(OrderExecutorAsync)

        with pytest.raises(ObservationOnlyExecutionComponentDisabled, match="disabled"):
            await executor._query_private("Balance")

    asyncio.run(_run())


def test_private_executor_repr_never_exposes_key_material(monkeypatch):
    _clear_execution_flags(monkeypatch)
    monkeypatch.setattr(
        "autobot.v2.order_executor_async.reject_private_execution_component",
        lambda _component: None,
    )
    key = "visible-key-material"
    executor = OrderExecutorAsync(api_key=key, api_secret="c2VjcmV0")

    rendered = repr(executor)

    assert key not in rendered
    assert key[:6] not in rendered
    assert "private_credentials_configured=True" in rendered


def test_paper_mode_refuses_fallback_when_paper_executor_is_unavailable(monkeypatch):
    monkeypatch.setattr(orchestrator_async, "PaperTradingExecutor", None)

    with pytest.raises(RuntimeError, match="paper_executor_unavailable"):
        orchestrator_async._require_paper_executor(True)
