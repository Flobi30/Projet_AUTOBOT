"""Safety tests for the archived synchronous AUTOBOT runtime boundary."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import autobot.v2.instance as legacy_instance
import autobot.v2.orchestrator as legacy_orchestrator
import autobot.v2.tests.test_kraken_api as legacy_kraken_api
from autobot.order_manager import OrderManager as legacy_order_manager
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


def test_legacy_synchronous_capital_lookup_is_retired_before_private_client_creation():
    with pytest.raises(LegacySynchronousRuntimeRetired, match="retired_from_execution"):
        legacy_orchestrator._get_available_capital_real(
            api_key="must-not-be-used",
            api_secret="must-not-be-used",
        )


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


def test_legacy_private_kraken_test_harness_fails_before_credential_or_client_use():
    with pytest.raises(LegacySynchronousRuntimeRetired, match="retired_from_execution"):
        legacy_kraken_api.KrakenAPITester(
            api_key="must-not-be-used",
            api_secret="must-not-be-used",
        )

    with pytest.raises(LegacySynchronousRuntimeRetired, match="retired_from_execution"):
        legacy_kraken_api.main()


def test_legacy_private_kraken_shell_wrapper_cannot_request_or_forward_credentials():
    root = Path(__file__).resolve().parents[1]
    script = (root / "src/autobot/v2/tests/test-kraken.sh").read_text(encoding="utf-8")

    assert "retired_from_execution" in script
    assert "KRAKEN_API_KEY" not in script
    assert "KRAKEN_API_SECRET" not in script
    assert "test_kraken_api.py" not in script


def test_legacy_order_manager_rejects_real_execution_before_client_initialization():
    with pytest.raises(LegacySynchronousRuntimeRetired, match="retired_from_execution"):
        legacy_order_manager(
            api_key="must-not-be-used",
            api_secret="must-not-be-used",
            sandbox=False,
        )
