from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from autobot.v2.instance_async import TradingInstanceAsync
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
