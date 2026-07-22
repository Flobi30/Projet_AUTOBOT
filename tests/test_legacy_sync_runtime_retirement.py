"""Safety tests for the archived synchronous AUTOBOT runtime boundary."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import autobot.v2.instance as legacy_instance
import autobot.v2.orchestrator as legacy_orchestrator
from autobot.v2.legacy_runtime import LegacySynchronousRuntimeRetired


pytestmark = pytest.mark.unit


def test_legacy_orchestrator_fails_before_execution_or_websocket_initialization(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(
        legacy_orchestrator,
        "get_order_executor",
        lambda *args, **kwargs: calls.append("order_executor"),
    )
    monkeypatch.setattr(
        legacy_orchestrator,
        "WebSocketMultiplexer",
        lambda *args, **kwargs: calls.append("websocket"),
    )

    with pytest.raises(LegacySynchronousRuntimeRetired, match="retired_from_execution"):
        legacy_orchestrator.Orchestrator(api_key="ignored", api_secret="ignored")

    assert calls == []


def test_legacy_trading_instance_fails_before_persistence_or_executor_use(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(
        legacy_instance,
        "get_persistence",
        lambda: calls.append("persistence"),
    )
    config = SimpleNamespace(name="legacy", initial_capital=100.0)

    with pytest.raises(LegacySynchronousRuntimeRetired, match="retired_from_execution"):
        legacy_instance.TradingInstance(
            instance_id="legacy-instance",
            config=config,
            orchestrator=object(),
            order_executor=object(),
        )

    assert calls == []
