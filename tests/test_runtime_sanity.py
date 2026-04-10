"""Runtime sanity checks (consolidated).

Goal: keep a compact, high-signal test surface for orchestrator hardening.
"""

from types import SimpleNamespace

from autobot.v2.orchestrator_async import OrchestratorAsync
from autobot.v2.rebalance_manager import RebalanceManager


class _DummyOrchestrator:
    def __init__(self):
        self._instances = {}


class _FakeModuleManager:
    def __init__(self, mapping):
        self._mapping = mapping

    def get(self, name):
        return self._mapping.get(name)


def test_rebalance_manager_smoke():
    manager = RebalanceManager(_DummyOrchestrator())
    assert manager.REINVEST_PERCENT == 0.25
    assert manager.REDUCE_PERCENT == 0.50


def test_reuse_module_manager_instances_overrides_enabled_modules():
    orch = object.__new__(OrchestratorAsync)

    orch.strategy_ensemble = object()
    orch.momentum = object()
    orch.xgboost = object()
    orch.sentiment = object()
    orch.heuristic_predictor = object()
    orch.onchain_data = object()

    shared_strategy = SimpleNamespace(name="strategy")
    shared_momentum = SimpleNamespace(name="momentum")
    shared_xgb = SimpleNamespace(name="xgb")

    orch.module_manager = _FakeModuleManager(
        {
            "strategy_ensemble": shared_strategy,
            "momentum_scoring": shared_momentum,
            "xgboost_predictor": shared_xgb,
        }
    )

    previous_sentiment = orch.sentiment
    orch._reuse_module_manager_instances()

    assert orch.strategy_ensemble is shared_strategy
    assert orch.momentum is shared_momentum
    assert orch.xgboost is shared_xgb
    assert orch.sentiment is previous_sentiment
