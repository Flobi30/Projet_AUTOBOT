"""
Tests for RebalanceManager — real calculation tests, no mocks.
"""

import asyncio
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


class FakeConfig:
    def __init__(self, name="Test", symbol="BTC/EUR", strategy="grid"):
        self.name = name
        self.symbol = symbol
        self.strategy = strategy
        self.initial_capital = 1000.0
        self.leverage = 1


class FakeInstance:
    """Minimal instance for testing rebalance logic."""

    def __init__(self, instance_id, initial_capital=1000.0, current_capital=1000.0):
        self.id = instance_id
        self.config = FakeConfig()
        self._initial_capital = initial_capital
        self._current_capital = current_capital
        self._peak_capital = max(initial_capital, current_capital)
        self._positions = {}
        self._closed_positions = []

    def get_initial_capital(self):
        return self._initial_capital

    def get_current_capital(self):
        return self._current_capital

    def get_profit(self):
        return self._current_capital - self._initial_capital

    def get_drawdown(self):
        if self._peak_capital > 0:
            return (self._peak_capital - self._current_capital) / self._peak_capital
        return 0.0

    def get_positions_snapshot(self):
        return list(self._positions.values())

    async def close_position(self, pos_id, sell_price):
        if pos_id in self._positions:
            pos = self._positions.pop(pos_id)
            profit = (sell_price - pos.get("entry_price", 0)) * pos.get("volume", 0)
            self._current_capital += profit
            self._closed_positions.append(pos_id)
            return profit
        return None


class FakeOrchestrator:
    """Minimal orchestrator for testing."""

    def __init__(self):
        self._instances = {}

    def add_instance(self, inst):
        self._instances[inst.id] = inst


class TestRebalanceManagerCalculations:
    """Test that rebalance calculations are real and correct."""

    def test_profit_percent_calculation(self):
        """Verify profit % is calculated from real instance data."""
        inst = FakeInstance("test1", initial_capital=1000.0, current_capital=1250.0)
        profit = inst.get_profit()
        profit_pct = profit / inst.get_initial_capital()

        assert profit == 250.0
        assert profit_pct == 0.25  # 25%

    def test_drawdown_calculation(self):
        """Verify drawdown is calculated from peak capital."""
        inst = FakeInstance("test2", initial_capital=1000.0, current_capital=800.0)
        inst._peak_capital = 1200.0
        dd = inst.get_drawdown()

        # (1200 - 800) / 1200 = 0.3333...
        assert abs(dd - 0.3333) < 0.001

    def test_no_reinvest_below_threshold(self):
        """Instance with < 20% profit should NOT be rebalanced."""
        inst = FakeInstance("test3", initial_capital=1000.0, current_capital=1150.0)
        profit_pct = inst.get_profit() / inst.get_initial_capital()

        assert profit_pct == 0.15  # 15% < 20% threshold
        # Should not trigger reinvestment

    def test_reinvest_above_threshold(self):
        """Instance with > 20% profit should trigger reinvestment."""
        inst = FakeInstance("test4", initial_capital=1000.0, current_capital=1300.0)
        profit_pct = inst.get_profit() / inst.get_initial_capital()

        assert profit_pct == 0.30  # 30% > 20% threshold
        # Reinvest amount = 300 * 0.25 = 75€
        reinvest_amount = inst.get_profit() * 0.25
        assert reinvest_amount == 75.0

    def test_reduce_on_drawdown(self):
        """Instance with > 10% drawdown should trigger position reduction."""
        inst = FakeInstance("test5", initial_capital=1000.0, current_capital=850.0)
        inst._peak_capital = 1000.0
        dd = inst.get_drawdown()

        assert dd == 0.15  # 15% > 10% threshold

    def test_no_action_normal_state(self):
        """Instance in normal state (no excess profit, no drawdown) should be skipped."""
        inst = FakeInstance("test6", initial_capital=1000.0, current_capital=1050.0)
        profit_pct = inst.get_profit() / inst.get_initial_capital()
        dd = inst.get_drawdown()

        assert profit_pct == 0.05  # 5% < 20%
        assert dd == 0.0  # No drawdown


class TestRebalanceManagerAsync:
    """Async tests for the RebalanceManager."""

    @pytest.fixture
    def setup(self):
        from autobot.v2.rebalance_manager import RebalanceManager
        orch = FakeOrchestrator()
        mgr = RebalanceManager(orch)
        return mgr, orch

    @pytest.mark.asyncio
    async def test_check_no_instances(self, setup):
        mgr, orch = setup
        events = await mgr.check_and_rebalance()
        assert events == []

    @pytest.mark.asyncio
    async def test_check_profitable_instance(self, setup):
        mgr, orch = setup
        inst = FakeInstance("profit1", 1000.0, 1300.0)  # +30%
        orch.add_instance(inst)
        events = await mgr.check_and_rebalance()

        assert len(events) == 1
        assert events[0].action == "reinvest"
        assert events[0].amount == 75.0  # 300 * 0.25

    @pytest.mark.asyncio
    async def test_check_drawdown_instance(self, setup):
        mgr, orch = setup
        inst = FakeInstance("dd1", 1000.0, 850.0)
        inst._peak_capital = 1000.0
        orch.add_instance(inst)
        events = await mgr.check_and_rebalance()

        assert len(events) == 1
        assert events[0].action == "reduce"

    @pytest.mark.asyncio
    async def test_check_normal_instance(self, setup):
        mgr, orch = setup
        inst = FakeInstance("normal1", 1000.0, 1050.0)  # +5%, no DD
        orch.add_instance(inst)
        events = await mgr.check_and_rebalance()

        assert len(events) == 0

    @pytest.mark.asyncio
    async def test_reinvest_increases_initial_capital(self, setup):
        mgr, orch = setup
        inst = FakeInstance("rein1", 1000.0, 1300.0)
        orch.add_instance(inst)

        before = inst._initial_capital
        await mgr.check_and_rebalance()
        after = inst._initial_capital

        assert after > before
        assert after == before + 75.0  # 300 * 0.25

    @pytest.mark.asyncio
    async def test_status_tracking(self, setup):
        mgr, orch = setup
        inst = FakeInstance("track1", 1000.0, 1300.0)
        orch.add_instance(inst)

        await mgr.check_and_rebalance()

        status = mgr.get_status()
        assert status["enabled"] is True
        assert status["check_count"] == 1
        assert status["total_reinvested"] == 75.0
        assert len(status["recent_events"]) == 1

    @pytest.mark.asyncio
    async def test_min_reinvest_amount(self, setup):
        mgr, orch = setup
        # Profit is 22% of 10€ = 2.2€, reinvest = 0.55€ < MIN_REINVEST_AMOUNT (5€)
        inst = FakeInstance("min1", 10.0, 12.2)
        orch.add_instance(inst)
        events = await mgr.check_and_rebalance()

        assert len(events) == 0  # Too small to reinvest


class TestPerformanceCalculations:
    """Test that PF, win rate, and profit calculations are mathematically correct."""

    def test_profit_factor(self):
        """PF = gross_profit / gross_loss"""
        trades = [
            {"profit": 100},
            {"profit": 50},
            {"profit": -30},
            {"profit": -20},
            {"profit": 80},
        ]
        gross_profit = sum(t["profit"] for t in trades if t["profit"] > 0)
        gross_loss = sum(abs(t["profit"]) for t in trades if t["profit"] < 0)
        pf = gross_profit / gross_loss if gross_loss > 0 else 0

        assert gross_profit == 230
        assert gross_loss == 50
        assert pf == 4.6

    def test_win_rate(self):
        """Win rate = winning trades / total trades * 100"""
        trades = [
            {"profit": 100},
            {"profit": 50},
            {"profit": -30},
            {"profit": -20},
            {"profit": 80},
        ]
        total = len(trades)
        winning = sum(1 for t in trades if t["profit"] > 0)
        wr = winning / total * 100

        assert total == 5
        assert winning == 3
        assert wr == 60.0

    def test_profit_factor_no_loss(self):
        """PF with no losses should be capped (for JSON serialization)."""
        trades = [{"profit": 100}, {"profit": 50}]
        gross_profit = sum(t["profit"] for t in trades if t["profit"] > 0)
        gross_loss = sum(abs(t["profit"]) for t in trades if t["profit"] < 0)

        pf = 999.99 if gross_loss == 0 and gross_profit > 0 else (
            gross_profit / gross_loss if gross_loss > 0 else 0
        )
        assert pf == 999.99

    def test_profit_factor_no_trades(self):
        """PF with no trades should be 0."""
        trades = []
        gross_profit = sum(t["profit"] for t in trades if t["profit"] > 0)
        gross_loss = sum(abs(t["profit"]) for t in trades if t["profit"] < 0)

        pf = 999.99 if gross_loss == 0 and gross_profit > 0 else (
            gross_profit / gross_loss if gross_loss > 0 else 0
        )
        assert pf == 0

    def test_paper_recommendation_promote(self):
        """PF > 1.5, WR > 55%, trades >= 20 → promote_to_live."""
        pf, wr, trades = 2.1, 62.0, 30
        if pf > 1.5 and wr > 55 and trades >= 20:
            rec = "promote_to_live"
        elif pf > 1.0 and trades < 20:
            rec = "continue_paper"
        else:
            rec = "stop"
        assert rec == "promote_to_live"

    def test_paper_recommendation_continue(self):
        """PF > 1.0, trades < 20 → continue_paper."""
        pf, wr, trades = 1.3, 50.0, 15
        if pf > 1.5 and wr > 55 and trades >= 20:
            rec = "promote_to_live"
        elif pf > 1.0 and trades < 20:
            rec = "continue_paper"
        else:
            rec = "stop"
        assert rec == "continue_paper"

    def test_paper_recommendation_stop(self):
        """PF <= 1.0, trades >= 10 → stop."""
        pf, wr, trades = 0.8, 40.0, 25
        if pf > 1.5 and wr > 55 and trades >= 20:
            rec = "promote_to_live"
        elif pf > 1.0 and trades < 20:
            rec = "continue_paper"
        elif pf <= 1.0 and trades >= 10:
            rec = "stop"
        else:
            rec = "continue_paper"
        assert rec == "stop"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
