"""Runtime sanity checks (consolidated).

Goal: keep a compact, high-signal test surface for orchestrator hardening.
"""

import asyncio

import pytest
from types import SimpleNamespace

from autobot.v2.orchestrator_async import OrchestratorAsync
from autobot.v2.instance_async import TradingInstanceAsync
from autobot.v2.modules.black_swan import BlackSwanCatcher
from autobot.v2.rebalance_manager import RebalanceManager
from autobot.v2.strategies.grid_async import GridStrategyAsync


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


class _FakeGridInstance:
    def __init__(self, available: float, positions=None):
        self.config = SimpleNamespace(symbol="XETHZEUR")
        self.orchestrator = SimpleNamespace(
            module_manager=_FakeModuleManager({}),
            ws_client=SimpleNamespace(is_data_fresh=lambda: True),
        )
        self._available = available
        self._positions = positions or []
        self._trades = []

    def get_available_capital(self):
        return self._available

    def get_positions_snapshot(self):
        return self._positions

    def get_current_capital(self):
        return 100.0

    def get_profit_factor_days(self, _days):
        return 1.0


class _FakePersistence:
    async def recover_positions(self, instance_id, symbol=None):
        assert symbol == "XETHZEUR"
        return [
            {
                "id": "pos-1",
                "buy_price": 100.0,
                "volume": 0.25,
                "status": "open",
                "open_time": "2026-05-02T12:00:00+00:00",
                "metadata": '{"buy_txid":"buy-1","buy_fee":0.04,"buy_fee_source":"paper"}',
            }
        ]

    async def recover_instance_state(self, instance_id):
        return {"current_capital": 500.0, "win_count": 2, "loss_count": 1}


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


def test_instance_recovery_decodes_json_metadata_and_rebuilds_allocated_capital():
    inst = object.__new__(TradingInstanceAsync)
    inst.id = "inst-1"
    inst.config = SimpleNamespace(symbol="XETHZEUR")
    inst._persistence = _FakePersistence()
    inst._positions = {}
    inst._allocated_capital = 0.0
    inst._current_capital = 0.0
    inst._win_count = 0
    inst._loss_count = 0
    inst._position_fee_hints = {}
    inst._execution_fee_cache = {}
    inst._lock = asyncio.Lock()

    asyncio.run(inst.recover_state())

    assert inst._current_capital == 500.0
    assert inst._allocated_capital == pytest.approx(25.0)
    assert inst._positions["pos-1"].buy_txid == "buy-1"
    assert inst._position_fee_hints["pos-1"]["buy_fee"] == pytest.approx(0.04)
    assert inst._execution_fee_cache["buy-1"]["source"] == "paper"


def test_grid_pauses_buy_when_recovered_positions_exhaust_available_capital():
    inst = _FakeGridInstance(available=-21.21)

    strategy = GridStrategyAsync(
        inst,
        {
            "center_price": 100.0,
            "max_positions": 10,
            "enable_dgt": False,
            "kelly_active": False,
        },
    )

    assert strategy._grid_initialized is True
    assert strategy._runtime_capital_per_level == 0.0
    assert strategy._calculate_kelly_cpl(100.0) == 0.0


def test_grid_reconnects_recovered_positions_to_open_levels():
    inst = _FakeGridInstance(
        available=100.0,
        positions=[
            {
                "status": "open",
                "entry_price": 98.0,
                "volume": 0.25,
                "open_time": "2026-05-02T12:00:00+00:00",
            }
        ],
    )
    strategy = GridStrategyAsync(
        inst,
        {
            "center_price": 100.0,
            "range_percent": 4.0,
            "num_levels": 5,
            "max_positions": 5,
            "enable_dgt": False,
            "kelly_active": False,
        },
    )

    strategy._sync_open_levels_from_instance_positions()

    nearest = strategy._find_nearest_level(98.0)
    assert strategy.open_levels[nearest]["entry_price"] == pytest.approx(98.0)
    assert strategy.open_levels[nearest]["volume"] == pytest.approx(0.25)
    assert strategy.open_levels[nearest]["recovered"] is True
