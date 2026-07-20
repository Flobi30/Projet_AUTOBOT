"""Fail-closed tests for the real Kraken execution boundary."""

import asyncio

import pytest

from autobot.v2 import orchestrator_async
from autobot.v2.order_executor import OrderExecutor
from autobot.v2.order_executor_async import OrderExecutorAsync


pytestmark = pytest.mark.unit


def _clear_execution_flags(monkeypatch):
    for name in (
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


def test_real_mutation_requires_all_explicit_flags(monkeypatch):
    async def _run():
        for name, value in {
            "PAPER_TRADING": "false",
            "LIVE_TRADING_CONFIRMATION": "true",
            "STRATEGY_ROUTER_LIVE_ENABLED": "true",
            "AUTOBOT_REAL_ORDER_EXECUTION_ENABLED": "true",
            "PREFLIGHT_ONLY": "false",
        }.items():
            monkeypatch.setenv(name, value)

        executor = OrderExecutorAsync(api_key="test-key", api_secret="c2VjcmV0")
        calls = []

        async def _authorized_query(method, **params):
            calls.append((method, params))
            return {"error": [], "result": {"count": 1}}

        monkeypatch.setattr(executor, "_query_private", _authorized_query)
        monkeypatch.setattr(executor, "_rate_limit", lambda: asyncio.sleep(0))
        success, response = await executor._safe_api_call("CancelOrder", txid="test")

        assert success is True
        assert response["result"]["count"] == 1
        assert calls == [("CancelOrder", {"txid": "test"})]

    asyncio.run(_run())


def test_sync_executor_cannot_bypass_real_mutation_guard(monkeypatch):
    _clear_execution_flags(monkeypatch)
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


def test_paper_mode_refuses_fallback_when_paper_executor_is_unavailable(monkeypatch):
    monkeypatch.setattr(orchestrator_async, "PaperTradingExecutor", None)

    with pytest.raises(RuntimeError, match="paper_executor_unavailable"):
        orchestrator_async._require_paper_executor(True)
