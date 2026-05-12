from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from autobot.v2.instance_async import TradingInstanceAsync
from autobot.v2.orchestrator_async import OrchestratorAsync
from autobot.v2.paper_capital_reallocator import (
    PaperCapitalReallocator,
    PaperCapitalRebalanceConfig,
    PaperInstanceCapital,
)


pytestmark = pytest.mark.unit


class _Persistence:
    def __init__(self):
        self.saved = []

    async def save_instance_state(self, *args, **kwargs):
        self.saved.append((args, kwargs))
        return True


def _capital_instance(*, current=120.0, initial=100.0, allocated=0.0):
    inst = object.__new__(TradingInstanceAsync)
    inst.id = "inst-a"
    inst.config = SimpleNamespace(initial_capital=initial)
    inst.status = SimpleNamespace(value="running")
    inst._current_capital = current
    inst._initial_capital = initial
    inst._allocated_capital = allocated
    inst._peak_capital = max(current, initial)
    inst._win_count = 0
    inst._loss_count = 0
    inst._lock = asyncio.Lock()
    inst._persistence = _Persistence()
    return inst


class _BudgetInstance:
    def __init__(self, instance_id: str, *, current: float, allocated: float = 0.0):
        self.id = instance_id
        self._current = current
        self._allocated = allocated

    def is_running(self):
        return True

    def get_current_capital(self):
        return self._current

    def get_available_capital(self):
        return self._current - self._allocated

    async def adjust_paper_budget(self, delta: float, reason: str = "unit_test"):
        if delta < 0:
            free = max(0.0, self.get_available_capital())
            delta = -min(abs(delta), free)
        self._current = max(0.0, self._current + delta)
        return delta


def test_reallocator_moves_budget_toward_best_scored_engine():
    reallocator = PaperCapitalReallocator(
        PaperCapitalRebalanceConfig(
            min_instance_eur=25.0,
            min_transfer_eur=5.0,
            max_move_pct=50.0,
            min_weight=0.05,
            max_weight=0.70,
            reserve_cash_pct=0.0,
        )
    )

    plan = reallocator.build_plan(
        [
            PaperInstanceCapital("weak", "ADAEUR", 100.0, 0.0, 100.0, opportunity_score=20.0, profit_factor=0.9),
            PaperInstanceCapital("strong", "TRXEUR", 100.0, 0.0, 100.0, opportunity_score=95.0, profit_factor=2.4),
        ]
    )

    targets = {target.instance_id: target for target in plan.targets}
    assert targets["strong"].target_capital > targets["weak"].target_capital
    assert plan.transfers
    assert plan.transfers[0].from_instance_id == "weak"
    assert plan.transfers[0].to_instance_id == "strong"


def test_reallocator_realized_health_overrides_stale_profit_factor():
    reallocator = PaperCapitalReallocator(
        PaperCapitalRebalanceConfig(
            min_instance_eur=25.0,
            min_transfer_eur=5.0,
            max_move_pct=50.0,
            min_weight=0.05,
            max_weight=0.70,
            reserve_cash_pct=0.0,
            health_weight_pct=35.0,
            min_health_closed_trades=20,
            weak_health_multiplier=0.45,
        )
    )

    plan = reallocator.build_plan(
        [
            PaperInstanceCapital(
                "stale_pf",
                "XXLMZEUR",
                100.0,
                0.0,
                100.0,
                opportunity_score=95.0,
                profit_factor=999.99,
                health_score=8.0,
                health_status="weak",
                health_closed_trades=42,
                health_net_pnl_eur=-2.6,
            ),
            PaperInstanceCapital(
                "realized_winner",
                "TRXEUR",
                100.0,
                0.0,
                100.0,
                opportunity_score=60.0,
                profit_factor=1.1,
                health_score=90.0,
                health_status="healthy",
                health_closed_trades=23,
                health_net_pnl_eur=1.9,
            ),
        ]
    )

    targets = {target.instance_id: target for target in plan.targets}
    assert targets["realized_winner"].score > targets["stale_pf"].score
    assert targets["realized_winner"].target_capital > targets["stale_pf"].target_capital
    assert plan.transfers
    assert plan.transfers[0].from_instance_id == "stale_pf"
    assert plan.transfers[0].to_instance_id == "realized_winner"


def test_reallocator_does_not_take_allocated_or_minimum_budget():
    reallocator = PaperCapitalReallocator(
        PaperCapitalRebalanceConfig(
            min_instance_eur=40.0,
            min_transfer_eur=5.0,
            max_move_pct=100.0,
            min_weight=0.01,
            max_weight=0.90,
            reserve_cash_pct=0.0,
        )
    )

    plan = reallocator.build_plan(
        [
            PaperInstanceCapital("protected", "XETHZEUR", 100.0, 97.0, 3.0, opportunity_score=5.0),
            PaperInstanceCapital("receiver", "TRXEUR", 100.0, 0.0, 100.0, opportunity_score=99.0, profit_factor=3.0),
        ]
    )

    protected = next(target for target in plan.targets if target.instance_id == "protected")
    assert protected.reducible_capital < reallocator.config.min_transfer_eur
    assert plan.transfers == []


def test_adjust_paper_budget_preserves_realized_profit():
    inst = _capital_instance(current=120.0, initial=100.0, allocated=20.0)

    moved = asyncio.run(inst.adjust_paper_budget(-30.0, reason="unit_test"))

    assert moved == pytest.approx(-30.0)
    assert inst.get_current_capital() == pytest.approx(90.0)
    assert inst.get_initial_capital() == pytest.approx(70.0)
    assert inst.get_profit() == pytest.approx(20.0)
    assert inst.config.initial_capital == pytest.approx(70.0)
    assert inst._persistence.saved[-1][1]["initial_capital"] == pytest.approx(70.0)


def test_adjust_paper_budget_never_withdraws_allocated_capital():
    inst = _capital_instance(current=100.0, initial=100.0, allocated=95.0)

    moved = asyncio.run(inst.adjust_paper_budget(-30.0, reason="unit_test"))

    assert moved == pytest.approx(-5.0)
    assert inst.get_current_capital() == pytest.approx(95.0)
    assert inst.get_available_capital() == pytest.approx(0.0)


def test_orchestrator_paper_signal_top_up_moves_only_free_budget():
    donor = _BudgetInstance("donor", current=100.0, allocated=0.0)
    receiver = _BudgetInstance("receiver", current=50.0, allocated=45.0)
    orch = object.__new__(OrchestratorAsync)
    orch.paper_mode = True
    orch._instances = {"donor": donor, "receiver": receiver}
    orch._capital_ops_lock = asyncio.Lock()
    orch.paper_capital_reallocator = PaperCapitalReallocator(
        PaperCapitalRebalanceConfig(
            min_instance_eur=25.0,
            min_transfer_eur=5.0,
            max_move_pct=50.0,
            reserve_cash_pct=0.0,
        )
    )
    orch._paper_capital_rebalance_last = {}

    result = asyncio.run(
        orch.request_paper_signal_budget_top_up(
            "receiver",
            10.0,
            preferred_transfer_eur=10.0,
        )
    )

    assert result["applied"] is True
    assert donor.get_current_capital() == pytest.approx(90.0)
    assert receiver.get_current_capital() == pytest.approx(60.0)
    assert receiver.get_available_capital() == pytest.approx(15.0)
    assert orch._paper_capital_rebalance_last["last_signal_top_up"]["applied"] is True


def test_orchestrator_paper_signal_top_up_does_not_take_allocated_budget():
    donor = _BudgetInstance("donor", current=100.0, allocated=98.0)
    receiver = _BudgetInstance("receiver", current=50.0, allocated=45.0)
    orch = object.__new__(OrchestratorAsync)
    orch.paper_mode = True
    orch._instances = {"donor": donor, "receiver": receiver}
    orch._capital_ops_lock = asyncio.Lock()
    orch.paper_capital_reallocator = PaperCapitalReallocator(
        PaperCapitalRebalanceConfig(
            min_instance_eur=25.0,
            min_transfer_eur=5.0,
            max_move_pct=100.0,
            reserve_cash_pct=0.0,
        )
    )

    result = asyncio.run(
        orch.request_paper_signal_budget_top_up(
            "receiver",
            10.0,
            preferred_transfer_eur=10.0,
        )
    )

    assert result["applied"] is False
    assert result["reason"] == "no_free_donor_budget"
    assert donor.get_current_capital() == pytest.approx(100.0)
    assert receiver.get_current_capital() == pytest.approx(50.0)
