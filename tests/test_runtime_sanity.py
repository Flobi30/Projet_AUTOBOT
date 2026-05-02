"""Runtime sanity checks (consolidated).

Goal: keep a compact, high-signal test surface for orchestrator hardening.
"""

import asyncio

import pytest
from types import SimpleNamespace

from autobot.v2.orchestrator_async import OrchestratorAsync
from autobot.v2.modules.black_swan import BlackSwanCatcher
from autobot.v2.rebalance_manager import RebalanceManager


pytestmark = pytest.mark.integration

class _DummyOrchestrator:
    def __init__(self):
        self._instances = {}


class _FakeModuleManager:
    def __init__(self, mapping):
        self._mapping = mapping

    def get(self, name):
        return self._mapping.get(name)


class _FakeInstance:
    def __init__(self, instance_id: str, symbol: str, price: float):
        self.id = instance_id
        self.config = SimpleNamespace(symbol=symbol)
        self._price = price

    def get_status(self):
        return {"last_price": self._price}


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


def test_black_swan_guard_uses_dynamic_per_symbol_catchers():
    orch = object.__new__(OrchestratorAsync)
    orch.paper_mode = True
    orch.black_swan = BlackSwanCatcher(lookback=50, sigma_threshold=3.0, cooldown_ticks=0)
    orch._black_swan_by_symbol = {}
    orch._journal_major_decision = lambda **kwargs: None
    orch._journal_rejected_opportunity = lambda **kwargs: None

    async def feed_prices():
        for _ in range(30):
            assert await orch._run_black_swan_guard(_FakeInstance("xrp", "XXRPZEUR", 0.50)) is False
            assert await orch._run_black_swan_guard(_FakeInstance("btc", "XXBTZEUR", 60000.0)) is False

    asyncio.run(feed_prices())

    assert set(orch._black_swan_by_symbol) == {"XXRPZEUR", "XXBTZEUR"}
    assert orch._black_swan_by_symbol["XXRPZEUR"] is not orch._black_swan_by_symbol["XXBTZEUR"]


def test_black_swan_paper_event_blocks_cycle_without_global_emergency_stop():
    class _EventCatcher:
        def on_price(self, price, volume=0.0):
            return {"type": "flash_pump", "severity": "CRITICAL", "return_pct": 99.0}

    orch = object.__new__(OrchestratorAsync)
    orch.paper_mode = True
    orch._get_black_swan_catcher = lambda symbol: _EventCatcher()
    orch._journal_major_decision = lambda **kwargs: None
    orch._journal_rejected_opportunity = lambda **kwargs: None

    async def fail_if_called():
        raise AssertionError("paper black swan must not stop every instance")

    orch._emergency_close_all = fail_if_called

    blocked = asyncio.run(orch._run_black_swan_guard(_FakeInstance("eth", "XETHZEUR", 2000.0)))

    assert blocked is True
