"""Regression tests for the active runtime's observation-only strategy guard."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from autobot.v2.instance_async import TradingInstanceAsync
from autobot.v2.strategies.observation_async import ObservationOnlyStrategyAsync


pytestmark = pytest.mark.unit


def _instance(tmp_path, monkeypatch, requested_strategy: str) -> TradingInstanceAsync:
    monkeypatch.chdir(tmp_path)
    config = SimpleNamespace(
        name="runtime-policy-test",
        symbol="XXBTZEUR",
        strategy=requested_strategy,
        initial_capital=100.0,
        leverage=1,
        tp_sl_config={},
    )
    with patch("autobot.v2.instance_async.get_persistence", return_value=MagicMock()):
        return TradingInstanceAsync("runtime-policy", config, MagicMock())


@pytest.mark.parametrize("requested_strategy", ("trend", "grid", "unknown"))
def test_noncanonical_runtime_strategy_is_replaced_before_signal_handler_setup(tmp_path, monkeypatch, requested_strategy):
    instance = _instance(tmp_path, monkeypatch, requested_strategy)

    instance._init_strategy()

    assert isinstance(instance._strategy, ObservationOnlyStrategyAsync)
    assert instance._runtime_strategy == "observation_only"
    assert instance._runtime_strategy_reason == "canonical_runtime_shadow_artifact_required"
    assert instance._strategy.get_status()["signal_emission_enabled"] is False
    assert instance._strategy.get_status()["requested_strategy"] == requested_strategy


def test_declared_observation_runtime_remains_non_signalling(tmp_path, monkeypatch):
    instance = _instance(tmp_path, monkeypatch, "observation_only")

    instance._init_strategy()

    status = instance.get_status()
    assert isinstance(instance._strategy, ObservationOnlyStrategyAsync)
    assert status["strategy"] == "observation_only"
    assert status["runtime_strategy"] == "observation_only"
    assert status["runtime_strategy_reason"] == "runtime_observation_only"
    assert instance._strategy.get_status()["signal_emission_enabled"] is False
