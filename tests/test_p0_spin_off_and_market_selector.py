import pytest

import asyncio
from types import SimpleNamespace

from autobot.v2.market_analyzer import MarketQualityScore
from autobot.v2.market_selector import MarketSelector
from autobot.v2.markets import MarketType
from autobot.v2.orchestrator_async import OrchestratorAsync
from autobot.v2.validator import ValidationStatus


pytestmark = pytest.mark.integration

class _FakeParent:
    def __init__(self, capital: float, available: float, pf_30d: float) -> None:
        self.id = "parent-1"
        self._capital = capital
        self._available = available
        self._pf_30d = pf_30d

    def get_current_capital(self) -> float:
        return self._capital

    def get_available_capital(self) -> float:
        return self._available

    def get_profit_factor_days(self, days: int = 30) -> float:
        return self._pf_30d

    def get_volatility(self) -> float:
        return 0.01

    def record_spin_off(self, amount: float) -> None:
        self._capital -= amount
        self._available -= amount


class _FakePersistence:
    def __init__(self) -> None:
        self.last_lineage = None

    async def record_instance_lineage(self, **kwargs):
        self.last_lineage = kwargs
        return True


def test_check_spin_off_uses_dynamic_25_percent_split(monkeypatch) -> None:
    orch = object.__new__(OrchestratorAsync)
    orch._instances = {}
    orch._parent_children = {}
    orch._child_parent = {}
    orch._on_instance_spinoff = None
    orch.scalability_guard = None
    orch.running = False
    orch.paper_mode = True
    orch.parent_instance_id = "parent-1"
    orch.config = {"spin_off_threshold": 1800.0, "max_instances": 2000}
    orch.validator = SimpleNamespace(
        validate=lambda _action, _context: SimpleNamespace(
            status=ValidationStatus.GREEN
        )
    )
    fake_persistence = _FakePersistence()
    monkeypatch.setattr("autobot.v2.orchestrator_async.get_persistence", lambda: fake_persistence)

    async def _get_available_capital():
        return 10_000.0

    async def _create_instance_auto(parent_instance_id=None, initial_capital=0.0):
        return SimpleNamespace(
            id="child-1",
            is_running=lambda: True,
            config=SimpleNamespace(symbol="", strategy="grid"),
        )

    orch._get_available_capital = _get_available_capital
    orch.create_instance_auto = _create_instance_auto

    parent = _FakeParent(capital=2000.0, available=2000.0, pf_30d=1.8)
    child = asyncio.run(orch.check_spin_off(parent))

    assert child is not None
    assert parent.get_current_capital() == 1500.0
    assert orch._child_parent["child-1"] == "parent-1"
    assert "child-1" in orch._parent_children["parent-1"]
    assert fake_persistence.last_lineage["child_instance_id"] == "child-1"
    assert fake_persistence.last_lineage["generation"] == 1


def test_check_spin_off_starts_runtime_child(monkeypatch) -> None:
    orch = object.__new__(OrchestratorAsync)
    orch._instances = {}
    orch._parent_children = {}
    orch._child_parent = {}
    orch._on_instance_spinoff = None
    orch.scalability_guard = None
    orch.running = True
    orch.paper_mode = True
    orch.parent_instance_id = "parent-1"
    orch.config = {"spin_off_threshold": 1800.0, "max_instances": 2000}
    orch.validator = SimpleNamespace(
        validate=lambda _action, _context: SimpleNamespace(
            status=ValidationStatus.GREEN
        )
    )
    fake_persistence = _FakePersistence()
    monkeypatch.setattr("autobot.v2.orchestrator_async.get_persistence", lambda: fake_persistence)

    async def _get_available_capital():
        return 10_000.0

    class _FakeChild:
        id = "child-1"
        config = SimpleNamespace(symbol="", strategy="grid")

        def __init__(self) -> None:
            self.started = False

        def is_running(self) -> bool:
            return self.started

        async def start(self) -> None:
            self.started = True

    child_obj = _FakeChild()

    async def _create_instance_auto(parent_instance_id=None, initial_capital=0.0):
        return child_obj

    orch._get_available_capital = _get_available_capital
    orch.create_instance_auto = _create_instance_auto

    parent = _FakeParent(capital=2000.0, available=2000.0, pf_30d=1.8)
    child = asyncio.run(orch.check_spin_off(parent))

    assert child is child_obj
    assert child_obj.started is True
    assert fake_persistence.last_lineage["status"] == "active"


def test_market_selector_blocks_forex_by_default(monkeypatch) -> None:
    orch = SimpleNamespace(_instances={})
    selector = MarketSelector(orch)
    selector.allow_forex_for_spinoff = False

    monkeypatch.setattr("autobot.v2.market_selector.is_market_open", lambda _symbol: True)

    markets = [
        SimpleNamespace(
            symbol="EUR/USD",
            market_type=MarketType.FOREX,
            market_quality=MarketQualityScore.EXCELLENT,
            composite_score=95.0,
        ),
        SimpleNamespace(
            symbol="BTC/EUR",
            market_type=MarketType.CRYPTO,
            market_quality=MarketQualityScore.GOOD,
            composite_score=70.0,
        ),
    ]

    candidates = selector._filter_candidates(markets, current_markets={})
    assert len(candidates) == 1
    assert candidates[0].symbol == "BTC/EUR"
