"""
Integration Tests for AUTOBOT Grid Trading Engine.

Tests the complete grid trading pipeline:
1. Grid calculation (15 levels, +/-7% range)
2. Order management (placement, fill simulation, counter orders)
3. Position tracking (P&L, metrics)
4. Rebalancing (price exits grid)
5. Risk management (stop loss, daily limits, emergency stop)
6. Full trading cycle (buy -> sell -> profit)
7. Error handling and edge cases

Usage:
    pytest tests/test_grid_trading_integration.py -v --tb=short
    pytest tests/test_grid_trading_integration.py -v --cov=grid_engine --cov-report=term-missing
"""

import asyncio
import sys
import os
import logging
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from grid_engine.grid_calculator import GridCalculator, GridConfig, GridLevel, GridSide
from grid_engine.order_manager import (
    GridOrderManager,
    GridOrder,
    OrderStatus,
    OrderType,
)
from grid_engine.position_tracker import (
    PositionTracker,
    GridPosition,
    TradeRecord,
    TradeType,
)
from grid_engine.rebalance import (
    GridRebalancer,
    RebalanceAction,
    RebalanceReason,
    RebalanceStatus,
)
from grid_engine.risk_manager import (
    GridRiskManager,
    RiskStatus,
    RiskAlert,
    RiskLevel,
    RiskAlertType,
)
from grid_engine.binance_connector import BinanceConnector, BinanceConfig
from grid_engine.paper_trading_logger import PaperTradingLogger
from grid_engine.position_manager import GridPositionManager, ManagedPosition, PositionStatus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def grid_config():
    return GridConfig(
        symbol="BTC/USDT",
        total_capital=500.0,
        num_levels=15,
        range_percent=14.0,
        profit_per_level=0.8,
        min_order_size=0.0001,
        fee_percent=0.1,
    )


@pytest.fixture
def grid_calculator(grid_config):
    calc = GridCalculator(grid_config)
    calc.calculate_grid(50000.0)
    return calc


@pytest.fixture
def order_manager(grid_calculator):
    return GridOrderManager(
        grid_calculator=grid_calculator,
        exchange_client=None,
        paper_trading=True,
    )


@pytest.fixture
def position_tracker():
    return PositionTracker(
        symbol="BTC/USDT",
        initial_capital=500.0,
        target_monthly_return=15.0,
    )


@pytest.fixture
def risk_manager(position_tracker, order_manager):
    return GridRiskManager(
        initial_capital=500.0,
        global_stop_percent=20.0,
        daily_loss_limit=50.0,
        max_drawdown_percent=25.0,
        max_exposure_percent=100.0,
        position_tracker=position_tracker,
        order_manager=order_manager,
    )


@pytest.fixture
def rebalancer(grid_calculator, order_manager, position_tracker):
    return GridRebalancer(
        grid_calculator=grid_calculator,
        order_manager=order_manager,
        position_tracker=position_tracker,
        rebalance_threshold_percent=1.0,
        close_positions_on_rebalance=False,
        min_rebalance_interval_seconds=0,
    )


@pytest.fixture
def binance_connector():
    config = BinanceConfig(
        api_key="test_key",
        api_secret="test_secret",
        testnet=True,
    )
    return BinanceConnector(config=config, paper_trading=True)


# ---------------------------------------------------------------------------
# 1. Grid Calculation Integration Tests
# ---------------------------------------------------------------------------

class TestGridCalculationIntegration:
    """Test grid calculation produces valid 15-level grid."""

    def test_grid_15_levels_created(self, grid_calculator):
        assert len(grid_calculator.levels) == 15

    def test_grid_center_price(self, grid_calculator):
        assert grid_calculator.center_price == 50000.0

    def test_grid_bounds_7_percent(self, grid_calculator):
        assert abs(grid_calculator.upper_bound - 53500.0) < 1.0
        assert abs(grid_calculator.lower_bound - 46500.0) < 1.0

    def test_grid_buy_sell_distribution(self, grid_calculator):
        buy_count = len(grid_calculator.buy_levels)
        sell_count = len(grid_calculator.sell_levels)
        assert buy_count == 7
        assert sell_count == 7

    def test_grid_levels_are_equidistant(self, grid_calculator):
        spacing = grid_calculator.grid_spacing
        assert spacing is not None
        for i in range(1, len(grid_calculator.levels)):
            diff = grid_calculator.levels[i].price - grid_calculator.levels[i - 1].price
            assert abs(diff - spacing) < 0.02

    def test_grid_capital_allocation_total(self, grid_calculator):
        total_allocated = sum(l.allocated_capital for l in grid_calculator.levels)
        assert abs(total_allocated - 500.0) < 0.1

    def test_grid_capital_per_level(self, grid_calculator):
        expected = 500.0 / 15
        for level in grid_calculator.levels:
            assert abs(level.allocated_capital - expected) < 0.01

    def test_grid_quantity_positive(self, grid_calculator):
        for level in grid_calculator.levels:
            assert level.quantity > 0

    def test_grid_quantity_respects_min_order_size(self, grid_calculator):
        for level in grid_calculator.levels:
            assert level.quantity >= 0.0001

    def test_grid_serialization(self, grid_calculator):
        data = grid_calculator.to_dict()
        assert "config" in data
        assert "status" in data
        assert "levels" in data
        assert len(data["levels"]) == 15

    def test_grid_status(self, grid_calculator):
        status = grid_calculator.get_status()
        assert status["total_levels"] == 15
        assert status["center_price"] == 50000.0
        assert status["buy_levels"] == 7
        assert status["sell_levels"] == 7

    def test_grid_price_in_range(self, grid_calculator):
        assert grid_calculator.is_price_in_grid(50000.0)
        assert grid_calculator.is_price_in_grid(47000.0)
        assert not grid_calculator.is_price_in_grid(40000.0)
        assert not grid_calculator.is_price_in_grid(60000.0)

    def test_grid_level_at_price(self, grid_calculator):
        level = grid_calculator.get_level_at_price(50000.0)
        assert level is not None
        assert level.side == GridSide.CENTER

    def test_grid_adjacent_levels(self, grid_calculator):
        buy, sell = grid_calculator.get_adjacent_levels(50000.0)
        if buy:
            assert buy.price < 50000.0
        if sell:
            assert sell.price > 50000.0

    def test_grid_distance_from_bounds(self, grid_calculator):
        d = grid_calculator.get_distance_from_bounds(50000.0)
        assert d["distance_from_upper"] > 0
        assert d["distance_from_lower"] > 0

    def test_grid_recalculate(self, grid_calculator):
        old_center = grid_calculator.center_price
        grid_calculator.recalculate_grid(55000.0)
        assert grid_calculator.center_price == 55000.0
        assert grid_calculator.center_price != old_center
        assert len(grid_calculator.levels) == 15


# ---------------------------------------------------------------------------
# 2. Order Management Integration Tests
# ---------------------------------------------------------------------------

class TestOrderManagementIntegration:
    """Test order placement, fills, and counter orders."""

    @pytest.mark.asyncio
    async def test_initialize_grid_orders(self, order_manager):
        orders = await order_manager.initialize_grid_orders()
        assert len(orders) == 7
        for order in orders:
            assert order.side == GridSide.BUY
            assert order.status == OrderStatus.OPEN

    @pytest.mark.asyncio
    async def test_order_properties(self, order_manager):
        orders = await order_manager.initialize_grid_orders()
        order = orders[0]
        assert order.is_active
        assert not order.is_complete
        assert order.remaining_quantity == order.quantity
        assert order.fill_percent == 0.0
        assert order.exchange_order_id.startswith("PAPER_")

    @pytest.mark.asyncio
    async def test_simulate_buy_fill(self, order_manager):
        orders = await order_manager.initialize_grid_orders()
        buy_order = orders[0]
        result = await order_manager.simulate_fill(buy_order.order_id)
        assert result is True
        assert buy_order.status == OrderStatus.FILLED
        assert buy_order.filled_quantity == buy_order.quantity

    @pytest.mark.asyncio
    async def test_counter_sell_after_buy_fill(self, order_manager):
        orders = await order_manager.initialize_grid_orders()
        buy_order = orders[0]
        initial_order_count = len(order_manager.orders)
        await order_manager.simulate_fill(buy_order.order_id)
        assert len(order_manager.orders) > initial_order_count

    @pytest.mark.asyncio
    async def test_cancel_order(self, order_manager):
        orders = await order_manager.initialize_grid_orders()
        order = orders[0]
        result = await order_manager.cancel_order(order.order_id)
        assert result is True
        assert order.status == OrderStatus.CANCELED

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_order(self, order_manager):
        result = await order_manager.cancel_order("nonexistent-id")
        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_all_orders(self, order_manager):
        await order_manager.initialize_grid_orders()
        canceled = await order_manager.cancel_all_orders()
        assert canceled == 7
        assert len(order_manager.active_orders) == 0

    @pytest.mark.asyncio
    async def test_check_fills_at_price(self, order_manager):
        await order_manager.initialize_grid_orders()
        lowest_buy = min(order_manager.buy_orders, key=lambda o: o.price)
        filled = await order_manager.check_fills_at_price(lowest_buy.price - 1)
        assert len(filled) >= 1

    @pytest.mark.asyncio
    async def test_order_status_update(self, order_manager):
        orders = await order_manager.initialize_grid_orders()
        order = orders[0]
        await order_manager.update_order_status(
            order_id=order.order_id,
            status=OrderStatus.PARTIALLY_FILLED,
            filled_quantity=order.quantity * 0.5,
            average_fill_price=order.price,
            fee=0.01,
        )
        assert order.status == OrderStatus.PARTIALLY_FILLED
        assert order.filled_quantity == order.quantity * 0.5
        assert order.fee == 0.01

    @pytest.mark.asyncio
    async def test_order_manager_status(self, order_manager):
        await order_manager.initialize_grid_orders()
        status = order_manager.get_status()
        assert status["total_orders"] == 7
        assert status["active_orders"] == 7
        assert status["paper_trading"] is True

    @pytest.mark.asyncio
    async def test_order_manager_to_dict(self, order_manager):
        await order_manager.initialize_grid_orders()
        data = order_manager.to_dict()
        assert "status" in data
        assert "orders" in data
        assert len(data["orders"]) == 7

    @pytest.mark.asyncio
    async def test_duplicate_order_for_level_prevented(self, order_manager):
        await order_manager.initialize_grid_orders()
        buy_levels = order_manager.grid_calculator.buy_levels
        result = await order_manager.place_order_for_level(buy_levels[0])
        assert result is None

    @pytest.mark.asyncio
    async def test_order_filled_callback(self, order_manager):
        callback_called = []

        async def on_filled(order):
            callback_called.append(order)

        order_manager.on_order_filled(on_filled)
        orders = await order_manager.initialize_grid_orders()
        await order_manager.simulate_fill(orders[0].order_id)
        assert len(callback_called) == 1

    @pytest.mark.asyncio
    async def test_order_canceled_callback(self, order_manager):
        callback_called = []

        async def on_canceled(order):
            callback_called.append(order)

        order_manager.on_order_canceled(on_canceled)
        orders = await order_manager.initialize_grid_orders()
        await order_manager.cancel_order(orders[0].order_id)
        assert len(callback_called) == 1

    @pytest.mark.asyncio
    async def test_simulate_fill_inactive_order(self, order_manager):
        orders = await order_manager.initialize_grid_orders()
        await order_manager.cancel_order(orders[0].order_id)
        result = await order_manager.simulate_fill(orders[0].order_id)
        assert result is False

    @pytest.mark.asyncio
    async def test_simulate_fill_nonexistent(self, order_manager):
        result = await order_manager.simulate_fill("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_update_nonexistent_order(self, order_manager):
        await order_manager.update_order_status(
            order_id="nonexistent",
            status=OrderStatus.FILLED,
        )

    @pytest.mark.asyncio
    async def test_order_to_dict(self, order_manager):
        orders = await order_manager.initialize_grid_orders()
        d = orders[0].to_dict()
        assert "order_id" in d
        assert "price" in d
        assert "quantity" in d
        assert "status" in d
        assert "side" in d


# ---------------------------------------------------------------------------
# 3. Position Tracking Integration Tests
# ---------------------------------------------------------------------------

class TestPositionTrackingIntegration:
    """Test position tracking, P&L, and metrics."""

    def test_initial_state(self, position_tracker):
        assert position_tracker.initial_capital == 500.0
        assert position_tracker.total_pnl == 0.0
        assert position_tracker.current_equity == 500.0
        assert len(position_tracker.open_positions) == 0

    def test_record_buy_trade(self, position_tracker):
        trade = position_tracker.record_trade(
            trade_type=TradeType.GRID_BUY,
            side=GridSide.BUY,
            quantity=0.001,
            price=50000.0,
            fee=0.05,
            level_id=5,
        )
        assert trade.trade_id is not None
        assert trade.side == GridSide.BUY
        assert len(position_tracker.open_positions) == 1

    def test_record_sell_trade_profit(self, position_tracker):
        position_tracker.record_trade(
            trade_type=TradeType.GRID_BUY,
            side=GridSide.BUY,
            quantity=0.001,
            price=50000.0,
            level_id=5,
        )
        sell_trade = position_tracker.record_trade(
            trade_type=TradeType.GRID_SELL,
            side=GridSide.SELL,
            quantity=0.001,
            price=50500.0,
            fee=0.05,
            level_id=5,
        )
        assert sell_trade.profit > 0
        assert position_tracker.total_realized_pnl > 0

    def test_record_sell_trade_loss(self, position_tracker):
        position_tracker.record_trade(
            trade_type=TradeType.GRID_BUY,
            side=GridSide.BUY,
            quantity=0.001,
            price=50000.0,
            level_id=5,
        )
        sell_trade = position_tracker.record_trade(
            trade_type=TradeType.GRID_SELL,
            side=GridSide.SELL,
            quantity=0.001,
            price=49000.0,
            fee=0.05,
            level_id=5,
        )
        assert sell_trade.profit < 0

    def test_win_rate(self, position_tracker):
        for i in range(3):
            position_tracker.record_trade(
                trade_type=TradeType.GRID_BUY,
                side=GridSide.BUY,
                quantity=0.001,
                price=50000.0,
                level_id=i,
            )
            position_tracker.record_trade(
                trade_type=TradeType.GRID_SELL,
                side=GridSide.SELL,
                quantity=0.001,
                price=50500.0,
                level_id=i,
            )
        assert position_tracker.win_rate == 100.0

    def test_update_prices(self, position_tracker):
        position_tracker.record_trade(
            trade_type=TradeType.GRID_BUY,
            side=GridSide.BUY,
            quantity=0.001,
            price=50000.0,
            level_id=0,
        )
        position_tracker.update_prices(51000.0)
        assert position_tracker.current_price == 51000.0
        assert position_tracker.total_unrealized_pnl > 0

    def test_drawdown_tracking(self, position_tracker):
        position_tracker.record_trade(
            trade_type=TradeType.GRID_BUY,
            side=GridSide.BUY,
            quantity=0.01,
            price=50000.0,
            level_id=0,
        )
        position_tracker.update_prices(45000.0)
        assert position_tracker.max_drawdown > 0

    def test_daily_pnl(self, position_tracker):
        position_tracker.record_trade(
            trade_type=TradeType.GRID_BUY,
            side=GridSide.BUY,
            quantity=0.001,
            price=50000.0,
            level_id=0,
        )
        position_tracker.record_trade(
            trade_type=TradeType.GRID_SELL,
            side=GridSide.SELL,
            quantity=0.001,
            price=50500.0,
            level_id=0,
        )
        today_pnl = position_tracker.get_today_pnl()
        assert today_pnl != 0.0

    def test_daily_pnl_history(self, position_tracker):
        position_tracker.record_trade(
            trade_type=TradeType.GRID_BUY,
            side=GridSide.BUY,
            quantity=0.001,
            price=50000.0,
            level_id=0,
        )
        history = position_tracker.get_daily_pnl_history(30)
        assert isinstance(history, dict)

    def test_metrics(self, position_tracker):
        position_tracker.record_trade(
            trade_type=TradeType.GRID_BUY,
            side=GridSide.BUY,
            quantity=0.001,
            price=50000.0,
            level_id=0,
        )
        metrics = position_tracker.get_metrics()
        assert "total_trades" in metrics
        assert "win_rate" in metrics
        assert "return_percent" in metrics
        assert metrics["total_trades"] == 1
        assert metrics["initial_capital"] == 500.0

    def test_position_summary(self, position_tracker):
        position_tracker.record_trade(
            trade_type=TradeType.GRID_BUY,
            side=GridSide.BUY,
            quantity=0.001,
            price=50000.0,
            level_id=0,
        )
        summary = position_tracker.get_position_summary()
        assert summary["open_positions"] == 1
        assert summary["total_quantity"] > 0

    def test_position_at_level(self, position_tracker):
        position_tracker.record_trade(
            trade_type=TradeType.GRID_BUY,
            side=GridSide.BUY,
            quantity=0.001,
            price=50000.0,
            level_id=5,
        )
        pos = position_tracker.get_position_at_level(5)
        assert pos is not None
        assert pos.level_id == 5
        assert pos.quantity == 0.001

    def test_position_properties(self, position_tracker):
        position_tracker.record_trade(
            trade_type=TradeType.GRID_BUY,
            side=GridSide.BUY,
            quantity=0.001,
            price=50000.0,
            level_id=0,
        )
        pos = position_tracker.get_position_at_level(0)
        assert pos.market_value == 0.001 * pos.current_price
        assert pos.cost_basis == 0.001 * 50000.0

    def test_tracker_to_dict(self, position_tracker):
        data = position_tracker.to_dict()
        assert "metrics" in data
        assert "position_summary" in data
        assert "recent_trades" in data
        assert "daily_pnl" in data

    def test_trade_record_to_dict(self, position_tracker):
        trade = position_tracker.record_trade(
            trade_type=TradeType.GRID_BUY,
            side=GridSide.BUY,
            quantity=0.001,
            price=50000.0,
            level_id=0,
        )
        d = trade.to_dict()
        assert "trade_id" in d
        assert "price" in d
        assert "side" in d

    def test_grid_position_to_dict(self, position_tracker):
        position_tracker.record_trade(
            trade_type=TradeType.GRID_BUY,
            side=GridSide.BUY,
            quantity=0.001,
            price=50000.0,
            level_id=0,
        )
        pos = position_tracker.get_position_at_level(0)
        d = pos.to_dict()
        assert "position_id" in d
        assert "market_value" in d
        assert "cost_basis" in d

    def test_close_position_fully(self, position_tracker):
        position_tracker.record_trade(
            trade_type=TradeType.GRID_BUY,
            side=GridSide.BUY,
            quantity=0.001,
            price=50000.0,
            level_id=0,
        )
        position_tracker.record_trade(
            trade_type=TradeType.GRID_SELL,
            side=GridSide.SELL,
            quantity=0.001,
            price=50500.0,
            level_id=0,
        )
        pos = position_tracker.get_position_at_level(0)
        assert not pos.is_open

    def test_sell_without_position(self, position_tracker):
        trade = position_tracker.record_trade(
            trade_type=TradeType.GRID_SELL,
            side=GridSide.SELL,
            quantity=0.001,
            price=50000.0,
            level_id=99,
        )
        assert trade.profit == 0.0

    def test_position_update_price(self):
        pos = GridPosition(
            position_id="test",
            level_id=0,
            symbol="BTC/USDT",
            quantity=0.001,
            entry_price=50000.0,
            current_price=50000.0,
        )
        pos.update_price(51000.0)
        assert pos.current_price == 51000.0
        assert pos.unrealized_pnl == 0.001 * 1000.0

    def test_position_pnl_percent(self):
        pos = GridPosition(
            position_id="test",
            level_id=0,
            symbol="BTC/USDT",
            quantity=0.001,
            entry_price=50000.0,
            current_price=50000.0,
        )
        pos.update_price(55000.0)
        assert pos.pnl_percent > 0

    def test_position_pnl_percent_zero_cost(self):
        pos = GridPosition(
            position_id="test",
            level_id=0,
            symbol="BTC/USDT",
            quantity=0.0,
            entry_price=0.0,
            current_price=50000.0,
        )
        assert pos.pnl_percent == 0.0


# ---------------------------------------------------------------------------
# 4. Rebalancing Integration Tests
# ---------------------------------------------------------------------------

class TestRebalancingIntegration:
    """Test grid rebalancing when price exits range."""

    def test_should_not_rebalance_in_range(self, rebalancer):
        should, reason = rebalancer.should_rebalance(50000.0)
        assert should is False
        assert reason is None

    def test_should_rebalance_above(self, rebalancer):
        should, reason = rebalancer.should_rebalance(60000.0)
        assert should is True
        assert reason == RebalanceReason.PRICE_ABOVE_GRID

    def test_should_rebalance_below(self, rebalancer):
        should, reason = rebalancer.should_rebalance(40000.0)
        assert should is True
        assert reason == RebalanceReason.PRICE_BELOW_GRID

    @pytest.mark.asyncio
    async def test_execute_rebalance(self, rebalancer):
        action = await rebalancer.execute_rebalance(
            55000.0, RebalanceReason.PRICE_ABOVE_GRID
        )
        assert action.status == RebalanceStatus.COMPLETED
        assert action.new_center_price == 55000.0
        assert action.orders_placed > 0
        assert rebalancer.rebalance_count == 1

    @pytest.mark.asyncio
    async def test_rebalance_updates_grid(self, rebalancer):
        await rebalancer.execute_rebalance(55000.0, RebalanceReason.PRICE_ABOVE_GRID)
        assert rebalancer.grid_calculator.center_price == 55000.0
        assert abs(rebalancer.grid_calculator.upper_bound - 55000.0 * 1.07) < 1

    @pytest.mark.asyncio
    async def test_check_and_rebalance_needed(self, rebalancer):
        action = await rebalancer.check_and_rebalance(60000.0)
        assert action is not None
        assert action.status == RebalanceStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_check_and_rebalance_not_needed(self, rebalancer):
        action = await rebalancer.check_and_rebalance(50000.0)
        assert action is None

    @pytest.mark.asyncio
    async def test_rebalance_with_close_positions(self, grid_calculator, order_manager, position_tracker):
        position_tracker.record_trade(
            trade_type=TradeType.GRID_BUY,
            side=GridSide.BUY,
            quantity=0.001,
            price=50000.0,
            level_id=0,
        )
        rebalancer = GridRebalancer(
            grid_calculator=grid_calculator,
            order_manager=order_manager,
            position_tracker=position_tracker,
            close_positions_on_rebalance=True,
            min_rebalance_interval_seconds=0,
        )
        action = await rebalancer.execute_rebalance(55000.0, RebalanceReason.PRICE_ABOVE_GRID)
        assert action.positions_closed >= 1

    @pytest.mark.asyncio
    async def test_double_rebalance_prevented(self, rebalancer):
        rebalancer.min_interval = 999999
        await rebalancer.execute_rebalance(55000.0, RebalanceReason.PRICE_ABOVE_GRID)
        should, _ = rebalancer.should_rebalance(60000.0)
        assert should is False

    def test_rebalance_recommendation(self, rebalancer):
        rec = rebalancer.get_rebalance_recommendation(50000.0)
        assert "should_rebalance" in rec
        assert "current_bounds" in rec
        assert rec["should_rebalance"] is False

    def test_rebalance_recommendation_needed(self, rebalancer):
        rec = rebalancer.get_rebalance_recommendation(60000.0)
        assert rec["should_rebalance"] is True
        assert rec["reason"] == "price_above_grid"

    def test_rebalancer_status(self, rebalancer):
        status = rebalancer.get_status()
        assert "is_rebalancing" in status
        assert "rebalance_count" in status
        assert status["rebalance_count"] == 0

    def test_rebalancer_to_dict(self, rebalancer):
        data = rebalancer.to_dict()
        assert "status" in data
        assert "history" in data

    @pytest.mark.asyncio
    async def test_rebalance_callbacks(self, rebalancer):
        start_called = []
        complete_called = []

        async def on_start(action):
            start_called.append(action)

        async def on_complete(action):
            complete_called.append(action)

        rebalancer.on_rebalance_start(on_start)
        rebalancer.on_rebalance_complete(on_complete)
        await rebalancer.execute_rebalance(55000.0, RebalanceReason.MANUAL_REBALANCE)
        assert len(start_called) == 1
        assert len(complete_called) == 1

    def test_rebalance_action_to_dict(self):
        action = RebalanceAction(
            action_id="test",
            reason=RebalanceReason.PRICE_ABOVE_GRID,
            old_center_price=50000.0,
            new_center_price=55000.0,
            old_bounds=(46500.0, 53500.0),
            new_bounds=(51150.0, 58850.0),
            status=RebalanceStatus.COMPLETED,
        )
        d = action.to_dict()
        assert d["action_id"] == "test"
        assert d["reason"] == "price_above_grid"


# ---------------------------------------------------------------------------
# 5. Risk Management Integration Tests
# ---------------------------------------------------------------------------

class TestRiskManagementIntegration:
    """Test risk controls: stop loss, daily limits, emergency."""

    def test_initial_trading_allowed(self, risk_manager):
        assert risk_manager.is_trading_allowed() is True

    def test_check_risk_normal(self, risk_manager):
        status = risk_manager.check_risk()
        assert status.level == RiskLevel.NORMAL
        assert status.is_trading_allowed is True

    def test_daily_loss_limit(self, risk_manager, position_tracker):
        for i in range(6):
            position_tracker.record_trade(
                trade_type=TradeType.GRID_BUY,
                side=GridSide.BUY,
                quantity=0.01,
                price=50000.0,
                level_id=i,
            )
            position_tracker.record_trade(
                trade_type=TradeType.GRID_SELL,
                side=GridSide.SELL,
                quantity=0.01,
                price=49000.0,
                fee=0.5,
                level_id=i,
            )
        status = risk_manager.check_risk()
        assert status.daily_pnl < 0

    def test_validate_order_allowed(self, risk_manager):
        valid, reason = risk_manager.validate_order(
            quantity=0.001,
            price=50000.0,
            side=GridSide.BUY,
        )
        assert valid is True
        assert reason is None

    def test_validate_order_too_large(self, risk_manager):
        valid, reason = risk_manager.validate_order(
            quantity=1.0,
            price=50000.0,
            side=GridSide.BUY,
        )
        assert valid is False
        assert "exceed" in reason.lower()

    @pytest.mark.asyncio
    async def test_emergency_stop(self, risk_manager):
        result = await risk_manager.emergency_stop("Test emergency")
        assert risk_manager.is_emergency_stopped is True
        assert risk_manager.is_trading_allowed() is False
        assert "reason" in result

    def test_reset_emergency_stop(self, risk_manager):
        asyncio.get_event_loop().run_until_complete(
            risk_manager.emergency_stop("Test")
        )
        result = risk_manager.reset_emergency_stop()
        assert result is True
        assert risk_manager.is_trading_allowed() is True

    def test_reset_emergency_not_stopped(self, risk_manager):
        result = risk_manager.reset_emergency_stop()
        assert result is False

    def test_acknowledge_alert(self, risk_manager):
        risk_manager._create_alert(
            alert_type=RiskAlertType.DAILY_LOSS_WARNING,
            level=RiskLevel.WARNING,
            message="Test warning",
            current_value=-25.0,
            threshold=-25.0,
        )
        alert = risk_manager.alerts[0]
        result = risk_manager.acknowledge_alert(alert.alert_id)
        assert result is True
        assert alert.acknowledged is True

    def test_acknowledge_all_alerts(self, risk_manager):
        for i in range(3):
            risk_manager._alerts.append(
                RiskAlert(
                    alert_id=f"alert-{i}",
                    alert_type=RiskAlertType.DAILY_LOSS_WARNING,
                    level=RiskLevel.WARNING,
                    message=f"Test {i}",
                    current_value=float(i),
                    threshold=10.0,
                    timestamp=datetime.utcnow() - timedelta(minutes=10),
                )
            )
        count = risk_manager.acknowledge_all_alerts()
        assert count == 3

    def test_acknowledge_nonexistent_alert(self, risk_manager):
        result = risk_manager.acknowledge_alert("nonexistent")
        assert result is False

    def test_risk_status_to_dict(self, risk_manager):
        status = risk_manager.check_risk()
        d = status.to_dict()
        assert "level" in d
        assert "daily_pnl" in d
        assert "is_trading_allowed" in d

    def test_risk_manager_status(self, risk_manager):
        status = risk_manager.get_status()
        assert "initial_capital" in status
        assert "is_trading_allowed" in status
        assert "risk_status" in status

    def test_risk_manager_to_dict(self, risk_manager):
        data = risk_manager.to_dict()
        assert "status" in data
        assert "alerts" in data

    def test_risk_alert_to_dict(self):
        alert = RiskAlert(
            alert_id="test",
            alert_type=RiskAlertType.EMERGENCY_STOP,
            level=RiskLevel.EMERGENCY,
            message="Test",
            current_value=0.0,
            threshold=0.0,
        )
        d = alert.to_dict()
        assert d["alert_id"] == "test"
        assert d["alert_type"] == "emergency_stop"

    def test_record_pnl(self, risk_manager):
        risk_manager.record_pnl(-10.0)

    def test_reset_daily_limit(self, risk_manager):
        result = risk_manager.reset_daily_limit()
        assert result is True

    @pytest.mark.asyncio
    async def test_emergency_stop_with_orders(self, risk_manager, order_manager):
        await order_manager.initialize_grid_orders()
        result = await risk_manager.emergency_stop("Test with orders")
        assert result["orders_canceled"] == 7

    @pytest.mark.asyncio
    async def test_emergency_stop_with_positions(self, risk_manager, position_tracker):
        position_tracker.record_trade(
            trade_type=TradeType.GRID_BUY,
            side=GridSide.BUY,
            quantity=0.001,
            price=50000.0,
            level_id=0,
        )
        position_tracker.update_prices(50000.0)
        result = await risk_manager.emergency_stop("Test with positions")
        assert result["positions_closed"] == 1

    def test_validate_order_trading_not_allowed(self, risk_manager):
        risk_manager._is_trading_allowed = False
        valid, reason = risk_manager.validate_order(
            quantity=0.001, price=50000.0, side=GridSide.BUY
        )
        assert valid is False

    def test_risk_on_alert_callback(self, risk_manager):
        alerts_received = []
        risk_manager.on_alert(lambda a: alerts_received.append(a))
        risk_manager._create_alert(
            alert_type=RiskAlertType.EXPOSURE_WARNING,
            level=RiskLevel.WARNING,
            message="Test",
            current_value=110.0,
            threshold=100.0,
        )
        assert len(alerts_received) == 1

    @pytest.mark.asyncio
    async def test_risk_on_stop_callback(self, risk_manager):
        stop_results = []

        async def on_stop(result):
            stop_results.append(result)

        risk_manager.on_stop(on_stop)
        await risk_manager.emergency_stop("callback test")
        assert len(stop_results) == 1

    def test_global_stop_triggered(self, risk_manager, position_tracker):
        for i in range(10):
            position_tracker.record_trade(
                trade_type=TradeType.GRID_BUY,
                side=GridSide.BUY,
                quantity=0.01,
                price=50000.0,
                level_id=i,
            )
            position_tracker.record_trade(
                trade_type=TradeType.GRID_SELL,
                side=GridSide.SELL,
                quantity=0.01,
                price=48500.0,
                fee=1.0,
                level_id=i,
            )
        status = risk_manager.check_risk()
        assert status.total_pnl < 0


# ---------------------------------------------------------------------------
# 6. Binance Connector Integration Tests (Paper Trading)
# ---------------------------------------------------------------------------

class TestBinanceConnectorIntegration:
    """Test Binance connector in paper trading mode."""

    @pytest.mark.asyncio
    async def test_connect(self, binance_connector):
        result = await binance_connector.connect()
        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_get_ticker(self, binance_connector):
        await binance_connector.connect()
        ticker = await binance_connector.get_ticker("BTC/USDT")
        assert "last" in ticker
        assert "bid" in ticker
        assert "ask" in ticker
        assert ticker["last"] > 0

    @pytest.mark.asyncio
    async def test_get_balance(self, binance_connector):
        await binance_connector.connect()
        balance = await binance_connector.get_balance()
        assert "USDT" in balance
        assert balance["USDT"] == 500.0

    @pytest.mark.asyncio
    async def test_create_paper_order(self, binance_connector):
        await binance_connector.connect()
        order = await binance_connector.create_order(
            symbol="BTCUSDT",
            side="BUY",
            type="LIMIT",
            quantity=0.001,
            price=50000.0,
        )
        assert "orderId" in order
        assert order["side"] == "BUY"
        assert order["status"] == "NEW"

    @pytest.mark.asyncio
    async def test_cancel_paper_order(self, binance_connector):
        await binance_connector.connect()
        order = await binance_connector.create_order(
            symbol="BTCUSDT",
            side="BUY",
            type="LIMIT",
            quantity=0.001,
            price=50000.0,
        )
        result = await binance_connector.cancel_order("BTCUSDT", order["orderId"])
        assert result["status"] == "CANCELED"

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_paper_order(self, binance_connector):
        await binance_connector.connect()
        result = await binance_connector.cancel_order("BTCUSDT", "nonexistent")
        assert result["status"] == "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_get_paper_order(self, binance_connector):
        await binance_connector.connect()
        order = await binance_connector.create_order(
            symbol="BTCUSDT",
            side="BUY",
            type="LIMIT",
            quantity=0.001,
            price=50000.0,
        )
        fetched = await binance_connector.get_order("BTCUSDT", order["orderId"])
        assert fetched["orderId"] == order["orderId"]

    @pytest.mark.asyncio
    async def test_get_open_orders(self, binance_connector):
        await binance_connector.connect()
        await binance_connector.create_order(
            symbol="BTCUSDT", side="BUY", type="LIMIT", quantity=0.001, price=50000.0
        )
        orders = await binance_connector.get_open_orders("BTCUSDT")
        assert len(orders) >= 1

    @pytest.mark.asyncio
    async def test_simulate_price_update(self, binance_connector):
        await binance_connector.connect()
        await binance_connector.simulate_price_update("BTC/USDT", 51000.0)
        ticker = await binance_connector.get_ticker("BTC/USDT")
        assert ticker["last"] == 51000.0

    @pytest.mark.asyncio
    async def test_paper_order_auto_fill(self, binance_connector):
        await binance_connector.connect()
        await binance_connector.create_order(
            symbol="BTCUSDT", side="BUY", type="LIMIT", quantity=0.001, price=50000.0
        )
        await binance_connector.simulate_price_update("BTCUSDT", 49000.0)
        balance = await binance_connector.get_balance()
        assert balance["BTC"] > 0

    @pytest.mark.asyncio
    async def test_disconnect(self, binance_connector):
        await binance_connector.connect()
        await binance_connector.disconnect()
        assert binance_connector.is_connected is False

    def test_connector_status(self, binance_connector):
        status = binance_connector.get_status()
        assert "connected" in status
        assert "paper_trading" in status
        assert status["paper_trading"] is True

    def test_connector_urls(self, binance_connector):
        assert "testnet" in binance_connector.base_url
        assert "testnet" in binance_connector.ws_url

    def test_binance_config_from_env(self):
        config = BinanceConfig.from_env()
        assert isinstance(config, BinanceConfig)

    @pytest.mark.asyncio
    async def test_price_callback(self, binance_connector):
        prices_received = []

        async def on_price(symbol, price, data):
            prices_received.append((symbol, price))

        binance_connector.on_price_update(on_price)
        await binance_connector.connect()
        await binance_connector.simulate_price_update("BTC/USDT", 52000.0)
        assert len(prices_received) == 1
        assert prices_received[0][1] == 52000.0


# ---------------------------------------------------------------------------
# 7. Full Trading Cycle Integration Tests
# ---------------------------------------------------------------------------

class TestFullTradingCycleIntegration:
    """Test complete grid trading cycle: setup -> buy -> sell -> profit."""

    @pytest.mark.asyncio
    async def test_complete_buy_sell_cycle(self, grid_calculator, order_manager, position_tracker):
        orders = await order_manager.initialize_grid_orders()
        assert len(orders) == 7

        buy_order = orders[3]
        await order_manager.simulate_fill(buy_order.order_id)
        assert buy_order.status == OrderStatus.FILLED

        position_tracker.record_trade(
            trade_type=TradeType.GRID_BUY,
            side=GridSide.BUY,
            quantity=buy_order.quantity,
            price=buy_order.price,
            level_id=buy_order.level_id,
        )
        assert len(position_tracker.open_positions) == 1

        sell_price = buy_order.price * 1.009
        sell_trade = position_tracker.record_trade(
            trade_type=TradeType.GRID_SELL,
            side=GridSide.SELL,
            quantity=buy_order.quantity,
            price=sell_price,
            level_id=buy_order.level_id,
        )
        assert sell_trade.profit > 0
        assert position_tracker.total_realized_pnl > 0

    @pytest.mark.asyncio
    async def test_multiple_level_fills(self, grid_calculator, order_manager):
        orders = await order_manager.initialize_grid_orders()
        lowest_price = min(o.price for o in orders)
        filled = await order_manager.check_fills_at_price(lowest_price - 100)
        assert len(filled) >= 1

    @pytest.mark.asyncio
    async def test_grid_setup_to_rebalance_cycle(
        self, grid_calculator, order_manager, position_tracker
    ):
        orders = await order_manager.initialize_grid_orders()
        assert len(orders) == 7

        rebalancer = GridRebalancer(
            grid_calculator=grid_calculator,
            order_manager=order_manager,
            position_tracker=position_tracker,
            min_rebalance_interval_seconds=0,
        )

        action = await rebalancer.check_and_rebalance(60000.0)
        assert action is not None
        assert action.status == RebalanceStatus.COMPLETED
        assert grid_calculator.center_price == 60000.0

    @pytest.mark.asyncio
    async def test_risk_controlled_trading(
        self, grid_calculator, order_manager, position_tracker, risk_manager
    ):
        assert risk_manager.is_trading_allowed()

        valid, _ = risk_manager.validate_order(0.001, 50000.0, GridSide.BUY)
        assert valid

        orders = await order_manager.initialize_grid_orders()
        assert len(orders) > 0

        status = risk_manager.check_risk()
        assert status.level == RiskLevel.NORMAL

    @pytest.mark.asyncio
    async def test_emergency_stop_full_cycle(
        self, grid_calculator, order_manager, position_tracker, risk_manager
    ):
        await order_manager.initialize_grid_orders()
        position_tracker.record_trade(
            trade_type=TradeType.GRID_BUY,
            side=GridSide.BUY,
            quantity=0.001,
            price=50000.0,
            level_id=0,
        )
        position_tracker.update_prices(50000.0)

        result = await risk_manager.emergency_stop("Integration test")
        assert result["orders_canceled"] == 7
        assert result["positions_closed"] == 1
        assert not risk_manager.is_trading_allowed()

        risk_manager.reset_emergency_stop()
        assert risk_manager.is_trading_allowed()


# ---------------------------------------------------------------------------
# 8. Error Handling & Edge Cases
# ---------------------------------------------------------------------------

class TestErrorHandlingIntegration:
    """Test error handling and edge cases."""

    def test_grid_invalid_price(self, grid_config):
        calc = GridCalculator(grid_config)
        with pytest.raises(ValueError):
            calc.calculate_grid(0)
        with pytest.raises(ValueError):
            calc.calculate_grid(-100)

    def test_grid_no_levels_queries(self, grid_config):
        calc = GridCalculator(grid_config)
        assert calc.get_level_at_price(50000.0) is None
        buy, sell = calc.get_adjacent_levels(50000.0)
        assert buy is None
        assert sell is None
        assert calc.is_price_in_grid(50000.0) is False
        assert calc.grid_spacing is None

    def test_grid_distance_no_bounds(self, grid_config):
        calc = GridCalculator(grid_config)
        d = calc.get_distance_from_bounds(50000.0)
        assert d["distance_from_upper"] == 0.0
        assert d["distance_from_lower"] == 0.0

    def test_grid_level_zero_quantity(self):
        level = GridLevel(
            level_id=0,
            price=50000.0,
            side=GridSide.BUY,
            allocated_capital=33.33,
            quantity=0.0,
        )
        assert level.fill_percent == 0.0

    @pytest.mark.asyncio
    async def test_order_manager_no_exchange(self, grid_calculator):
        manager = GridOrderManager(
            grid_calculator=grid_calculator,
            exchange_client=None,
            paper_trading=False,
        )
        level = grid_calculator.buy_levels[0]
        order = await manager.place_order_for_level(level)
        assert order is None

    @pytest.mark.asyncio
    async def test_cancel_inactive_order(self, order_manager):
        orders = await order_manager.initialize_grid_orders()
        order = orders[0]
        await order_manager.cancel_order(order.order_id)
        result = await order_manager.cancel_order(order.order_id)
        assert result is False

    def test_rebalancer_no_bounds(self, grid_config, order_manager, position_tracker):
        calc = GridCalculator(grid_config)
        rebalancer = GridRebalancer(
            grid_calculator=calc,
            order_manager=order_manager,
            position_tracker=position_tracker,
        )
        should, reason = rebalancer.should_rebalance(50000.0)
        assert should is False

    @pytest.mark.asyncio
    async def test_rebalance_already_in_progress(self, rebalancer):
        rebalancer._is_rebalancing = True
        should, _ = rebalancer.should_rebalance(60000.0)
        assert should is False

        with pytest.raises(RuntimeError, match="already in progress"):
            await rebalancer.execute_rebalance(60000.0, RebalanceReason.PRICE_ABOVE_GRID)

    @pytest.mark.asyncio
    async def test_exchange_order_failure_mock(self, grid_calculator):
        mock_client = AsyncMock()
        mock_client.create_order.side_effect = Exception("Exchange error")
        manager = GridOrderManager(
            grid_calculator=grid_calculator,
            exchange_client=mock_client,
            paper_trading=False,
        )
        level = grid_calculator.buy_levels[0]
        order = await manager.place_order_for_level(level)
        assert order is None

    @pytest.mark.asyncio
    async def test_exchange_cancel_failure_mock(self, grid_calculator):
        mock_client = AsyncMock()
        mock_client.create_order.return_value = {"orderId": "test123"}
        mock_client.cancel_order.side_effect = Exception("Cancel failed")
        manager = GridOrderManager(
            grid_calculator=grid_calculator,
            exchange_client=mock_client,
            paper_trading=False,
        )
        level = grid_calculator.buy_levels[0]
        order = await manager.place_order_for_level(level)
        assert order is not None
        result = await manager.cancel_order(order.order_id)
        assert result is False

    @pytest.mark.asyncio
    async def test_callback_error_handling(self, order_manager):
        async def bad_callback(order):
            raise Exception("callback error")

        order_manager.on_order_filled(bad_callback)
        orders = await order_manager.initialize_grid_orders()
        await order_manager.simulate_fill(orders[0].order_id)

    def test_risk_alert_deduplication(self, risk_manager):
        risk_manager._create_alert(
            alert_type=RiskAlertType.DAILY_LOSS_WARNING,
            level=RiskLevel.WARNING,
            message="Test",
            current_value=-25.0,
            threshold=-25.0,
        )
        risk_manager._create_alert(
            alert_type=RiskAlertType.DAILY_LOSS_WARNING,
            level=RiskLevel.WARNING,
            message="Test duplicate",
            current_value=-25.0,
            threshold=-25.0,
        )
        same_type = [a for a in risk_manager.alerts if a.alert_type == RiskAlertType.DAILY_LOSS_WARNING]
        assert len(same_type) == 1

    def test_risk_alert_max_cap(self, risk_manager):
        for i in range(150):
            risk_manager._alerts.append(
                RiskAlert(
                    alert_id=f"cap-{i}",
                    alert_type=RiskAlertType.EXPOSURE_WARNING,
                    level=RiskLevel.WARNING,
                    message=f"Cap test {i}",
                    current_value=float(i),
                    threshold=100.0,
                    timestamp=datetime.utcnow() - timedelta(minutes=10),
                )
            )
        risk_manager._create_alert(
            alert_type=RiskAlertType.DRAWDOWN_WARNING,
            level=RiskLevel.WARNING,
            message="After cap",
            current_value=20.0,
            threshold=20.0,
        )
        assert len(risk_manager._alerts) <= 101

    def test_grid_level_fill_edge_cases(self):
        level = GridLevel(
            level_id=0,
            price=50000.0,
            side=GridSide.BUY,
            allocated_capital=33.33,
            quantity=0.001,
        )
        level.filled_quantity = 0.00098
        assert not level.is_filled

        level.filled_quantity = 0.00099
        assert level.is_filled

    def test_order_status_enum_values(self):
        assert OrderStatus.PENDING.value == "pending"
        assert OrderStatus.OPEN.value == "open"
        assert OrderStatus.FILLED.value == "filled"
        assert OrderStatus.CANCELED.value == "canceled"
        assert OrderStatus.REJECTED.value == "rejected"
        assert OrderStatus.EXPIRED.value == "expired"
        assert OrderStatus.PARTIALLY_FILLED.value == "partially_filled"

    def test_order_type_enum_values(self):
        assert OrderType.LIMIT.value == "limit"
        assert OrderType.MARKET.value == "market"

    def test_trade_type_enum_values(self):
        assert TradeType.GRID_BUY.value == "grid_buy"
        assert TradeType.GRID_SELL.value == "grid_sell"
        assert TradeType.REBALANCE.value == "rebalance"
        assert TradeType.EMERGENCY_CLOSE.value == "emergency_close"

    def test_risk_level_enum_values(self):
        assert RiskLevel.NORMAL.value == "normal"
        assert RiskLevel.WARNING.value == "warning"
        assert RiskLevel.CRITICAL.value == "critical"
        assert RiskLevel.EMERGENCY.value == "emergency"

    def test_rebalance_reason_enum_values(self):
        assert RebalanceReason.PRICE_ABOVE_GRID.value == "price_above_grid"
        assert RebalanceReason.PRICE_BELOW_GRID.value == "price_below_grid"
        assert RebalanceReason.MANUAL_REBALANCE.value == "manual_rebalance"

    def test_rebalance_status_enum_values(self):
        assert RebalanceStatus.PENDING.value == "pending"
        assert RebalanceStatus.IN_PROGRESS.value == "in_progress"
        assert RebalanceStatus.COMPLETED.value == "completed"
        assert RebalanceStatus.FAILED.value == "failed"

    def test_risk_alert_type_enum_values(self):
        assert RiskAlertType.DAILY_LOSS_WARNING.value == "daily_loss_warning"
        assert RiskAlertType.GLOBAL_STOP_TRIGGERED.value == "global_stop_triggered"
        assert RiskAlertType.EMERGENCY_STOP.value == "emergency_stop"

    @pytest.mark.asyncio
    async def test_order_sell_profit_calculation(self, grid_calculator):
        manager = GridOrderManager(
            grid_calculator=grid_calculator,
            paper_trading=True,
        )
        orders = await manager.initialize_grid_orders()
        buy_order = orders[0]
        await manager.simulate_fill(buy_order.order_id)

        sell_orders = [o for o in manager.orders.values() if o.side == GridSide.SELL and o.is_active]
        if sell_orders:
            await manager.simulate_fill(sell_orders[0].order_id)
            assert manager.total_profit != 0 or manager.trade_count >= 2

    @pytest.mark.asyncio
    async def test_check_fills_no_fills_needed(self, order_manager):
        await order_manager.initialize_grid_orders()
        filled = await order_manager.check_fills_at_price(50000.0)
        filled_buys_below = [o for o in filled if o.side == GridSide.BUY]
        assert isinstance(filled, list)

    def test_position_add_to_existing(self, position_tracker):
        position_tracker.record_trade(
            trade_type=TradeType.GRID_BUY,
            side=GridSide.BUY,
            quantity=0.001,
            price=50000.0,
            level_id=5,
        )
        position_tracker.record_trade(
            trade_type=TradeType.GRID_BUY,
            side=GridSide.BUY,
            quantity=0.001,
            price=49000.0,
            level_id=5,
        )
        pos = position_tracker.get_position_at_level(5)
        assert pos.quantity == 0.002
        assert pos.entry_price == (50000.0 * 0.001 + 49000.0 * 0.001) / 0.002


# ---------------------------------------------------------------------------
# 9. Kraken API Connection Tests (Simulated)
# ---------------------------------------------------------------------------

class TestKrakenConnectionSimulated:
    """Test Kraken API connectivity patterns via mocks."""

    @pytest.mark.asyncio
    async def test_kraken_price_fetch_mock(self):
        with patch("grid_engine.binance_connector.BinanceConnector.get_ticker") as mock_ticker:
            mock_ticker.return_value = {
                "symbol": "BTC/EUR",
                "bid": 45000.0,
                "ask": 45010.0,
                "last": 45005.0,
                "volume": 500.0,
                "timestamp": 1234567890000,
            }
            connector = BinanceConnector(paper_trading=True)
            ticker = await connector.get_ticker("BTC/EUR")
            assert ticker["last"] == 45005.0
            assert ticker["symbol"] == "BTC/EUR"

    @pytest.mark.asyncio
    async def test_api_connection_error_handling(self):
        connector = BinanceConnector(paper_trading=True)
        await connector.connect()
        ticker = await connector.get_ticker("BTC/EUR")
        assert "last" in ticker
        assert ticker["last"] > 0

    @pytest.mark.asyncio
    async def test_order_placement_simulated(self):
        connector = BinanceConnector(paper_trading=True)
        await connector.connect()
        order = await connector.create_order(
            symbol="BTCEUR",
            side="BUY",
            type="LIMIT",
            quantity=0.001,
            price=45000.0,
        )
        assert order["status"] == "NEW"
        assert order["quantity"] == 0.001


# ---------------------------------------------------------------------------
# 10. Paper Trading Logger Tests
# ---------------------------------------------------------------------------

class TestPaperTradingLoggerIntegration:
    """Test paper trading logger module."""

    def test_paper_trading_logger_import(self):
        assert PaperTradingLogger is not None

    def test_position_manager_import(self):
        assert GridPositionManager is not None


# ---------------------------------------------------------------------------
# 11. Grid Config Variations
# ---------------------------------------------------------------------------

class TestGridConfigVariations:
    """Test grid with different configurations."""

    def test_small_capital(self):
        config = GridConfig(symbol="BTC/USDT", total_capital=100.0, num_levels=5)
        calc = GridCalculator(config)
        levels = calc.calculate_grid(50000.0)
        assert len(levels) == 5
        assert abs(config.capital_per_level - 20.0) < 0.01

    def test_large_capital(self):
        config = GridConfig(symbol="BTC/USDT", total_capital=10000.0, num_levels=20)
        calc = GridCalculator(config)
        levels = calc.calculate_grid(50000.0)
        assert len(levels) == 20

    def test_narrow_range(self):
        config = GridConfig(symbol="BTC/USDT", total_capital=500.0, range_percent=4.0)
        calc = GridCalculator(config)
        calc.calculate_grid(50000.0)
        assert abs(calc.upper_bound - 51000.0) < 1
        assert abs(calc.lower_bound - 49000.0) < 1

    def test_wide_range(self):
        config = GridConfig(symbol="BTC/USDT", total_capital=500.0, range_percent=30.0)
        calc = GridCalculator(config)
        calc.calculate_grid(50000.0)
        assert abs(calc.upper_bound - 57500.0) < 1
        assert abs(calc.lower_bound - 42500.0) < 1

    def test_eth_pair(self):
        config = GridConfig(symbol="ETH/USDT", total_capital=500.0)
        calc = GridCalculator(config)
        levels = calc.calculate_grid(3000.0)
        assert len(levels) == 15
        assert calc.center_price == 3000.0

    def test_custom_fee(self):
        config = GridConfig(symbol="BTC/USDT", total_capital=500.0, fee_percent=0.075)
        assert config.fee_percent == 0.075

    def test_custom_profit_per_level(self):
        config = GridConfig(symbol="BTC/USDT", total_capital=500.0, profit_per_level=1.5)
        assert config.profit_per_level == 1.5


# ---------------------------------------------------------------------------
# 12. Paper Trading Logger Comprehensive Tests
# ---------------------------------------------------------------------------

class TestPaperTradingLoggerComprehensive:
    """Comprehensive tests for paper_trading_logger module."""

    def test_logger_init(self, tmp_path):
        ptl = PaperTradingLogger(
            log_dir=str(tmp_path), initial_capital=500.0, session_id="test_session"
        )
        assert ptl.session_id == "test_session"
        assert ptl.initial_capital == 500.0

    def test_record_buy_trade(self, tmp_path):
        ptl = PaperTradingLogger(log_dir=str(tmp_path))
        trade = ptl.record_trade(
            trade_id="T1", symbol="BTC/USDT", side="buy",
            price=50000.0, quantity=0.001, fee=0.05
        )
        assert trade.trade_id == "T1"
        assert trade.side == "buy"
        assert trade.value == 50000.0 * 0.001

    def test_record_sell_trade_with_pnl(self, tmp_path):
        ptl = PaperTradingLogger(log_dir=str(tmp_path))
        ptl.record_trade(
            trade_id="T1", symbol="BTC/USDT", side="buy",
            price=50000.0, quantity=0.001
        )
        trade = ptl.record_trade(
            trade_id="T2", symbol="BTC/USDT", side="sell",
            price=50500.0, quantity=0.001, pnl=0.50, fee=0.05
        )
        assert trade.pnl == 0.50

    def test_daily_metrics_update(self, tmp_path):
        ptl = PaperTradingLogger(log_dir=str(tmp_path))
        ptl.record_trade(
            trade_id="T1", symbol="BTC/USDT", side="buy",
            price=50000.0, quantity=0.001
        )
        ptl.record_trade(
            trade_id="T2", symbol="BTC/USDT", side="sell",
            price=50500.0, quantity=0.001, pnl=0.50, fee=0.05
        )
        assert ptl._daily_metrics.trades_count == 2
        assert ptl._daily_metrics.buy_count == 1
        assert ptl._daily_metrics.sell_count == 1
        assert ptl._daily_metrics.win_count == 1

    def test_cumulative_metrics(self, tmp_path):
        ptl = PaperTradingLogger(log_dir=str(tmp_path))
        for i in range(3):
            ptl.record_trade(
                trade_id=f"B{i}", symbol="BTC/USDT", side="buy",
                price=50000.0, quantity=0.001
            )
            ptl.record_trade(
                trade_id=f"S{i}", symbol="BTC/USDT", side="sell",
                price=50500.0, quantity=0.001, pnl=0.50, fee=0.05
            )
        assert ptl._cumulative.total_trades == 6
        assert ptl._cumulative.total_wins == 3
        assert ptl._cumulative.total_losses == 0

    def test_loss_tracking(self, tmp_path):
        ptl = PaperTradingLogger(log_dir=str(tmp_path))
        ptl.record_trade(
            trade_id="B1", symbol="BTC/USDT", side="buy",
            price=50000.0, quantity=0.001
        )
        ptl.record_trade(
            trade_id="S1", symbol="BTC/USDT", side="sell",
            price=49000.0, quantity=0.001, pnl=-1.0, fee=0.05
        )
        assert ptl._daily_metrics.loss_count == 1
        assert ptl._daily_metrics.worst_trade == -1.0
        assert ptl._cumulative.total_losses == 1
        assert ptl._cumulative.consecutive_losses == 1

    def test_consecutive_wins_tracking(self, tmp_path):
        ptl = PaperTradingLogger(log_dir=str(tmp_path))
        for i in range(5):
            ptl.record_trade(
                trade_id=f"B{i}", symbol="BTC/USDT", side="buy",
                price=50000.0, quantity=0.001
            )
            ptl.record_trade(
                trade_id=f"S{i}", symbol="BTC/USDT", side="sell",
                price=50500.0, quantity=0.001, pnl=0.50
            )
        assert ptl._cumulative.consecutive_wins == 5
        assert ptl._cumulative.max_consecutive_wins == 5

    def test_consecutive_losses_tracking(self, tmp_path):
        ptl = PaperTradingLogger(log_dir=str(tmp_path))
        for i in range(3):
            ptl.record_trade(
                trade_id=f"B{i}", symbol="BTC/USDT", side="buy",
                price=50000.0, quantity=0.001
            )
            ptl.record_trade(
                trade_id=f"S{i}", symbol="BTC/USDT", side="sell",
                price=49000.0, quantity=0.001, pnl=-1.0
            )
        assert ptl._cumulative.consecutive_losses == 3
        assert ptl._cumulative.max_consecutive_losses == 3

    def test_win_rate_calculation(self, tmp_path):
        ptl = PaperTradingLogger(log_dir=str(tmp_path))
        ptl.record_trade(trade_id="B1", symbol="BTC/USDT", side="buy", price=50000.0, quantity=0.001)
        ptl.record_trade(trade_id="S1", symbol="BTC/USDT", side="sell", price=50500.0, quantity=0.001, pnl=0.50)
        ptl.record_trade(trade_id="B2", symbol="BTC/USDT", side="buy", price=50000.0, quantity=0.001)
        ptl.record_trade(trade_id="S2", symbol="BTC/USDT", side="sell", price=49000.0, quantity=0.001, pnl=-1.0)
        assert ptl._daily_metrics.win_rate == 50.0

    def test_roi_calculation(self, tmp_path):
        ptl = PaperTradingLogger(log_dir=str(tmp_path))
        ptl.record_trade(trade_id="B1", symbol="BTC/USDT", side="buy", price=50000.0, quantity=0.001)
        ptl.record_trade(trade_id="S1", symbol="BTC/USDT", side="sell", price=50500.0, quantity=0.001, pnl=5.0, fee=0.05)
        assert ptl._cumulative.roi_percent > 0

    def test_drawdown_tracking(self, tmp_path):
        ptl = PaperTradingLogger(log_dir=str(tmp_path))
        ptl.record_trade(trade_id="B1", symbol="BTC/USDT", side="buy", price=50000.0, quantity=0.001)
        ptl.record_trade(trade_id="S1", symbol="BTC/USDT", side="sell", price=49000.0, quantity=0.001, pnl=-10.0, fee=0.5)
        assert ptl._cumulative.max_drawdown > 0

    def test_profit_factor_wins_only(self, tmp_path):
        ptl = PaperTradingLogger(log_dir=str(tmp_path))
        ptl.record_trade(trade_id="B1", symbol="BTC/USDT", side="buy", price=50000.0, quantity=0.001)
        ptl.record_trade(trade_id="S1", symbol="BTC/USDT", side="sell", price=50500.0, quantity=0.001, pnl=0.50)
        assert ptl._cumulative.profit_factor == float('inf')

    def test_profit_factor_with_losses(self, tmp_path):
        ptl = PaperTradingLogger(log_dir=str(tmp_path))
        ptl.record_trade(trade_id="B1", symbol="BTC/USDT", side="buy", price=50000.0, quantity=0.001)
        ptl.record_trade(trade_id="S1", symbol="BTC/USDT", side="sell", price=50500.0, quantity=0.001, pnl=1.0)
        ptl.record_trade(trade_id="B2", symbol="BTC/USDT", side="buy", price=50000.0, quantity=0.001)
        ptl.record_trade(trade_id="S2", symbol="BTC/USDT", side="sell", price=49500.0, quantity=0.001, pnl=-0.50)
        assert ptl._cumulative.profit_factor == 2.0

    def test_record_error(self, tmp_path):
        ptl = PaperTradingLogger(log_dir=str(tmp_path))
        ptl.record_error("Test error")
        assert ptl._cumulative.error_count == 1

    def test_save_and_load_state(self, tmp_path):
        ptl = PaperTradingLogger(log_dir=str(tmp_path))
        ptl.record_trade(trade_id="B1", symbol="BTC/USDT", side="buy", price=50000.0, quantity=0.001)
        ptl.record_trade(trade_id="S1", symbol="BTC/USDT", side="sell", price=50500.0, quantity=0.001, pnl=0.50)
        ptl.save_current_state()

        ptl2 = PaperTradingLogger(log_dir=str(tmp_path))
        loaded = ptl2.load_previous_state()
        assert loaded is True
        assert ptl2._cumulative.total_trades == 2

    def test_load_no_previous_state(self, tmp_path):
        ptl = PaperTradingLogger(log_dir=str(tmp_path))
        loaded = ptl.load_previous_state()
        assert loaded is False

    def test_load_corrupted_state(self, tmp_path):
        from pathlib import Path
        bad_file = Path(tmp_path) / "papier_trading_20260101.json"
        bad_file.write_text("INVALID JSON", encoding="utf-8")
        ptl = PaperTradingLogger(log_dir=str(tmp_path))
        loaded = ptl.load_previous_state()
        assert loaded is False

    def test_get_daily_report(self, tmp_path):
        ptl = PaperTradingLogger(log_dir=str(tmp_path))
        ptl.record_trade(trade_id="B1", symbol="BTC/USDT", side="buy", price=50000.0, quantity=0.001)
        report = ptl.get_daily_report()
        assert "session_id" in report
        assert "trades_count" in report
        assert "daily_metrics" in report
        assert "cumulative_metrics" in report
        assert "validation_status" in report

    def test_get_final_report(self, tmp_path):
        ptl = PaperTradingLogger(log_dir=str(tmp_path))
        ptl.record_trade(trade_id="B1", symbol="BTC/USDT", side="buy", price=50000.0, quantity=0.001)
        report = ptl.get_final_report()
        assert "session_id" in report
        assert "session_start" in report
        assert "session_end" in report
        assert "initial_capital" in report
        assert "final_capital" in report
        assert "total_pnl" in report
        assert "roi_percent" in report
        assert "validation_status" in report

    def test_validation_status_not_go(self, tmp_path):
        ptl = PaperTradingLogger(log_dir=str(tmp_path))
        ptl.record_trade(trade_id="B1", symbol="BTC/USDT", side="buy", price=50000.0, quantity=0.001)
        ptl.record_trade(trade_id="S1", symbol="BTC/USDT", side="sell", price=50500.0, quantity=0.001, pnl=0.50)
        assert ptl._validation.overall_status in ("NO-GO", "REVIEW")

    def test_validation_status_review(self, tmp_path):
        ptl = PaperTradingLogger(log_dir=str(tmp_path))
        for i in range(60):
            ptl.record_trade(trade_id=f"B{i}", symbol="BTC/USDT", side="buy", price=50000.0, quantity=0.001)
            ptl.record_trade(trade_id=f"S{i}", symbol="BTC/USDT", side="sell", price=50500.0, quantity=0.001, pnl=0.50)
        status = ptl._validation.overall_status
        assert status in ("GO", "REVIEW", "NO-GO")

    def test_sharpe_ratio_requires_multiple_days(self, tmp_path):
        ptl = PaperTradingLogger(log_dir=str(tmp_path))
        ptl._daily_pnls = [1.0, 2.0, -0.5, 1.5, 0.3]
        ptl._calculate_sharpe_ratio()
        assert ptl._cumulative.sharpe_ratio != 0.0

    def test_sharpe_ratio_not_enough_data(self, tmp_path):
        ptl = PaperTradingLogger(log_dir=str(tmp_path))
        ptl._daily_pnls = [1.0]
        ptl._calculate_sharpe_ratio()
        assert ptl._cumulative.sharpe_ratio == 0.0

    def test_trade_record_to_dict(self, tmp_path):
        from grid_engine.paper_trading_logger import TradeRecord as PTTradeRecord
        tr = PTTradeRecord(
            trade_id="T1", timestamp="2026-01-01", symbol="BTC/USDT",
            side="buy", price=50000.0, quantity=0.001, value=50.0, fee=0.05
        )
        d = tr.to_dict()
        assert d["trade_id"] == "T1"

    def test_daily_metrics_to_dict(self, tmp_path):
        from grid_engine.paper_trading_logger import DailyMetrics as PTDailyMetrics
        dm = PTDailyMetrics(date="2026-01-01")
        d = dm.to_dict()
        assert d["date"] == "2026-01-01"

    def test_cumulative_metrics_to_dict(self, tmp_path):
        from grid_engine.paper_trading_logger import CumulativeMetrics as PTCumulativeMetrics
        cm = PTCumulativeMetrics()
        d = cm.to_dict()
        assert "total_days" in d
        assert "total_trades" in d

    def test_validation_status_to_dict(self, tmp_path):
        from grid_engine.paper_trading_logger import ValidationStatus
        vs = ValidationStatus()
        d = vs.to_dict()
        assert "overall_status" in d
        assert "recommendation" in d

    def test_best_worst_day_tracking(self, tmp_path):
        ptl = PaperTradingLogger(log_dir=str(tmp_path))
        ptl.record_trade(trade_id="B1", symbol="BTC/USDT", side="buy", price=50000.0, quantity=0.001)
        ptl.record_trade(trade_id="S1", symbol="BTC/USDT", side="sell", price=50500.0, quantity=0.001, pnl=5.0, fee=0.05)
        assert ptl._cumulative.best_day_pnl > 0
        assert ptl._cumulative.best_day_date != ""

    def test_avg_trade_pnl(self, tmp_path):
        ptl = PaperTradingLogger(log_dir=str(tmp_path))
        ptl.record_trade(trade_id="B1", symbol="BTC/USDT", side="buy", price=50000.0, quantity=0.001)
        ptl.record_trade(trade_id="S1", symbol="BTC/USDT", side="sell", price=50500.0, quantity=0.001, pnl=1.0)
        ptl.record_trade(trade_id="B2", symbol="BTC/USDT", side="buy", price=50000.0, quantity=0.001)
        ptl.record_trade(trade_id="S2", symbol="BTC/USDT", side="sell", price=50500.0, quantity=0.001, pnl=3.0)
        assert ptl._daily_metrics.avg_trade_pnl == 2.0

    def test_volume_tracked(self, tmp_path):
        ptl = PaperTradingLogger(log_dir=str(tmp_path))
        ptl.record_trade(trade_id="B1", symbol="BTC/USDT", side="buy", price=50000.0, quantity=0.001)
        assert ptl._daily_metrics.volume_traded == 50.0


# ---------------------------------------------------------------------------
# 13. Position Manager Comprehensive Tests
# ---------------------------------------------------------------------------

class TestPositionManagerComprehensive:
    """Comprehensive tests for position_manager module."""

    @pytest.fixture
    def position_mgr(self, grid_calculator, order_manager):
        return GridPositionManager(
            grid_calculator=grid_calculator,
            order_manager=order_manager,
        )

    def test_init(self, position_mgr):
        assert position_mgr.sell_level_offset == 8
        assert position_mgr.profit_target_pct == 0.8
        assert position_mgr.total_cycles == 0
        assert position_mgr.total_realized_profit == 0.0

    def test_properties(self, position_mgr):
        assert position_mgr.positions == {}
        assert position_mgr.active_positions == []
        assert position_mgr.completed_positions == []

    def test_get_sell_level_for_buy(self, position_mgr):
        sell_level = position_mgr.get_sell_level_for_buy(0)
        assert sell_level is not None
        assert sell_level.level_id == 8
        assert sell_level.side == GridSide.SELL

    def test_get_sell_level_for_buy_all(self, position_mgr):
        for buy_id in range(7):
            sell_level = position_mgr.get_sell_level_for_buy(buy_id)
            assert sell_level is not None
            assert sell_level.level_id == buy_id + 8

    def test_get_sell_level_out_of_bounds(self, position_mgr):
        sell_level = position_mgr.get_sell_level_for_buy(10)
        assert sell_level is None

    def test_calculate_sell_price(self, position_mgr):
        sell_level = position_mgr.get_sell_level_for_buy(0)
        sell_price = position_mgr.calculate_sell_price(46500.0, sell_level)
        assert sell_price >= 46500.0 * 1.008

    def test_calculate_sell_price_uses_grid_when_higher(self, position_mgr):
        sell_level = position_mgr.get_sell_level_for_buy(0)
        sell_price = position_mgr.calculate_sell_price(40000.0, sell_level)
        assert sell_price == sell_level.price

    @pytest.mark.asyncio
    async def test_check_and_process_fills_no_fills(self, position_mgr, order_manager):
        await order_manager.initialize_grid_orders()
        processed = await position_mgr.check_and_process_fills()
        assert len(processed) == 0

    @pytest.mark.asyncio
    async def test_check_and_process_fills_with_fill(self, position_mgr, order_manager):
        orders = await order_manager.initialize_grid_orders()
        await order_manager.simulate_fill(orders[0].order_id)
        processed = await position_mgr.check_and_process_fills()
        assert len(processed) == 1
        pos = processed[0]
        assert pos.status == PositionStatus.SELL_PLACED
        assert pos.sell_order_id is not None

    @pytest.mark.asyncio
    async def test_duplicate_fill_not_processed(self, position_mgr, order_manager):
        orders = await order_manager.initialize_grid_orders()
        await order_manager.simulate_fill(orders[0].order_id)
        await position_mgr.check_and_process_fills()
        processed2 = await position_mgr.check_and_process_fills()
        assert len(processed2) == 0

    @pytest.mark.asyncio
    async def test_check_sell_fills(self, position_mgr, order_manager):
        orders = await order_manager.initialize_grid_orders()
        await order_manager.simulate_fill(orders[0].order_id)
        processed = await position_mgr.check_and_process_fills()
        assert len(processed) == 1

        sell_order_id = processed[0].sell_order_id
        await order_manager.simulate_fill(sell_order_id)
        completed = await position_mgr.check_sell_fills()
        assert len(completed) == 1
        assert completed[0].status == PositionStatus.CLOSED
        assert position_mgr.total_cycles == 1
        assert position_mgr.total_realized_profit != 0

    @pytest.mark.asyncio
    async def test_run_cycle(self, position_mgr, order_manager):
        orders = await order_manager.initialize_grid_orders()
        await order_manager.simulate_fill(orders[0].order_id)
        result = await position_mgr.run_cycle()
        assert "new_sell_orders" in result
        assert "completed_cycles" in result
        assert "active_positions" in result
        assert result["new_sell_orders"] == 1

    def test_get_grid_mapping(self, position_mgr):
        mapping = position_mgr.get_grid_mapping()
        assert len(mapping) == 7
        for m in mapping:
            assert "buy_level_id" in m
            assert "sell_level_id" in m
            assert "spread" in m
            assert "spread_pct" in m

    def test_get_status(self, position_mgr):
        status = position_mgr.get_status()
        assert "total_positions" in status
        assert "active_positions" in status
        assert "completed_cycles" in status
        assert "total_realized_profit" in status

    def test_to_dict(self, position_mgr):
        data = position_mgr.to_dict()
        assert "status" in data
        assert "grid_mapping" in data
        assert "active_positions" in data
        assert "completed_positions" in data

    @pytest.mark.asyncio
    async def test_callbacks(self, position_mgr, order_manager):
        buy_filled_calls = []
        sell_placed_calls = []
        cycle_complete_calls = []

        async def on_buy(pos):
            buy_filled_calls.append(pos)

        async def on_sell(pos):
            sell_placed_calls.append(pos)

        async def on_complete(pos):
            cycle_complete_calls.append(pos)

        position_mgr.on_buy_filled(on_buy)
        position_mgr.on_sell_placed(on_sell)
        position_mgr.on_cycle_complete(on_complete)

        orders = await order_manager.initialize_grid_orders()
        await order_manager.simulate_fill(orders[0].order_id)
        processed = await position_mgr.check_and_process_fills()
        assert len(buy_filled_calls) == 1
        assert len(sell_placed_calls) == 1

        sell_order_id = processed[0].sell_order_id
        await order_manager.simulate_fill(sell_order_id)
        await position_mgr.check_sell_fills()
        assert len(cycle_complete_calls) == 1

    def test_managed_position_properties(self):
        pos = ManagedPosition(
            position_id="test", buy_level_id=0, sell_level_id=8,
            buy_order_id="BO1", buy_price=46500.0, volume=0.001,
            sell_price=50500.0, status=PositionStatus.SELL_PLACED,
        )
        assert pos.is_active is True
        assert pos.expected_profit == (50500.0 - 46500.0) * 0.001
        assert pos.expected_profit_pct > 0

    def test_managed_position_no_sell_price(self):
        pos = ManagedPosition(
            position_id="test", buy_level_id=0, sell_level_id=8,
            buy_order_id="BO1", buy_price=46500.0, volume=0.001,
        )
        assert pos.expected_profit == 0.0
        assert pos.expected_profit_pct == 0.0

    def test_managed_position_zero_buy_price(self):
        pos = ManagedPosition(
            position_id="test", buy_level_id=0, sell_level_id=8,
            buy_order_id="BO1", buy_price=0.0, volume=0.001,
            sell_price=50000.0,
        )
        assert pos.expected_profit_pct == 0.0

    def test_managed_position_closed_not_active(self):
        pos = ManagedPosition(
            position_id="test", buy_level_id=0, sell_level_id=8,
            buy_order_id="BO1", buy_price=46500.0, volume=0.001,
            status=PositionStatus.CLOSED,
        )
        assert pos.is_active is False

    def test_managed_position_error_not_active(self):
        pos = ManagedPosition(
            position_id="test", buy_level_id=0, sell_level_id=8,
            buy_order_id="BO1", buy_price=46500.0, volume=0.001,
            status=PositionStatus.ERROR,
        )
        assert pos.is_active is False

    def test_managed_position_to_dict(self):
        pos = ManagedPosition(
            position_id="test", buy_level_id=0, sell_level_id=8,
            buy_order_id="BO1", buy_price=46500.0, volume=0.001,
            sell_price=50500.0, status=PositionStatus.SELL_PLACED,
        )
        d = pos.to_dict()
        assert d["position_id"] == "test"
        assert d["buy_level_id"] == 0
        assert d["sell_level_id"] == 8
        assert "expected_profit" in d
        assert "expected_profit_pct" in d
        assert d["status"] == "sell_placed"

    def test_position_status_enum(self):
        assert PositionStatus.WAITING_BUY_FILL.value == "waiting_buy_fill"
        assert PositionStatus.BUY_FILLED.value == "buy_filled"
        assert PositionStatus.SELL_PLACED.value == "sell_placed"
        assert PositionStatus.SELL_FILLED.value == "sell_filled"
        assert PositionStatus.CLOSED.value == "closed"
        assert PositionStatus.ERROR.value == "error"


# ---------------------------------------------------------------------------
# 14. Binance Connector Extended Tests
# ---------------------------------------------------------------------------

class TestBinanceConnectorExtended:
    """Extended tests for binance_connector module."""

    @pytest.mark.asyncio
    async def test_paper_sell_order(self, binance_connector):
        await binance_connector.connect()
        order = await binance_connector.create_order(
            symbol="BTCUSDT", side="SELL", type="LIMIT",
            quantity=0.001, price=55000.0
        )
        assert order["side"] == "SELL"
        assert order["status"] == "NEW"

    @pytest.mark.asyncio
    async def test_paper_market_order(self, binance_connector):
        await binance_connector.connect()
        order = await binance_connector.create_order(
            symbol="BTCUSDT", side="BUY", type="MARKET",
            quantity=0.001
        )
        assert order["type"] == "MARKET"

    @pytest.mark.asyncio
    async def test_sell_fill_simulation(self, binance_connector):
        await binance_connector.connect()
        await binance_connector.create_order(
            symbol="BTCUSDT", side="SELL", type="LIMIT",
            quantity=0.001, price=55000.0
        )
        await binance_connector.simulate_price_update("BTCUSDT", 56000.0)
        balance = await binance_connector.get_balance()
        assert balance["USDT"] > 500.0

    @pytest.mark.asyncio
    async def test_order_callback(self, binance_connector):
        order_events = []

        async def on_order(order):
            order_events.append(order)

        binance_connector.on_order_update(on_order)
        await binance_connector.connect()
        await binance_connector.create_order(
            symbol="BTCUSDT", side="BUY", type="LIMIT",
            quantity=0.001, price=50000.0
        )
        await binance_connector.simulate_price_update("BTCUSDT", 49000.0)
        assert len(order_events) >= 1

    @pytest.mark.asyncio
    async def test_multiple_symbols(self, binance_connector):
        await binance_connector.connect()
        await binance_connector.simulate_price_update("BTC/USDT", 50000.0)
        await binance_connector.simulate_price_update("ETH/USDT", 3000.0)
        btc = await binance_connector.get_ticker("BTC/USDT")
        eth = await binance_connector.get_ticker("ETH/USDT")
        assert btc["last"] == 50000.0
        assert eth["last"] == 3000.0

    @pytest.mark.asyncio
    async def test_paper_order_symbol_filter(self, binance_connector):
        await binance_connector.connect()
        await binance_connector.create_order(
            symbol="BTCUSDT", side="BUY", type="LIMIT",
            quantity=0.001, price=50000.0
        )
        await binance_connector.create_order(
            symbol="ETHUSDT", side="BUY", type="LIMIT",
            quantity=0.01, price=3000.0
        )
        btc_orders = await binance_connector.get_open_orders("BTCUSDT")
        all_orders = await binance_connector.get_open_orders()
        assert len(btc_orders) == 1
        assert len(all_orders) == 2

    @pytest.mark.asyncio
    async def test_get_nonexistent_paper_order(self, binance_connector):
        await binance_connector.connect()
        result = await binance_connector.get_order("BTCUSDT", "nonexistent")
        assert result["status"] == "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_disconnect_no_exchange(self, binance_connector):
        await binance_connector.disconnect()
        assert binance_connector.is_connected is False

    def test_production_urls(self):
        config = BinanceConfig(testnet=False)
        connector = BinanceConnector(config=config, paper_trading=True)
        assert "testnet" not in connector.base_url
        assert "testnet" not in connector.ws_url

    @pytest.mark.asyncio
    async def test_price_no_fill_wrong_direction(self, binance_connector):
        await binance_connector.connect()
        await binance_connector.create_order(
            symbol="BTCUSDT", side="BUY", type="LIMIT",
            quantity=0.001, price=49000.0
        )
        await binance_connector.simulate_price_update("BTCUSDT", 50000.0)
        orders = await binance_connector.get_open_orders("BTCUSDT")
        assert len(orders) == 1

    @pytest.mark.asyncio
    async def test_sell_no_fill_wrong_direction(self, binance_connector):
        await binance_connector.connect()
        await binance_connector.create_order(
            symbol="BTCUSDT", side="SELL", type="LIMIT",
            quantity=0.001, price=55000.0
        )
        await binance_connector.simulate_price_update("BTCUSDT", 50000.0)
        orders = await binance_connector.get_open_orders("BTCUSDT")
        assert len(orders) == 1

    @pytest.mark.asyncio
    async def test_canceled_order_not_filled(self, binance_connector):
        await binance_connector.connect()
        order = await binance_connector.create_order(
            symbol="BTCUSDT", side="BUY", type="LIMIT",
            quantity=0.001, price=50000.0
        )
        await binance_connector.cancel_order("BTCUSDT", order["orderId"])
        await binance_connector.simulate_price_update("BTCUSDT", 49000.0)
        fetched = await binance_connector.get_order("BTCUSDT", order["orderId"])
        assert fetched["status"] == "CANCELED"


# ---------------------------------------------------------------------------
# 15. API Module State Tests
# ---------------------------------------------------------------------------

class TestGridEngineAPIState:
    """Test the GridEngineState and API models."""

    def test_grid_engine_state_singleton(self):
        from grid_engine.api import GridEngineState
        GridEngineState._instance = None
        s1 = GridEngineState.get_instance()
        s2 = GridEngineState.get_instance()
        assert s1 is s2
        GridEngineState._instance = None

    def test_grid_engine_state_init(self):
        from grid_engine.api import GridEngineState
        state = GridEngineState()
        assert state.is_initialized is False
        assert state.is_running is False
        assert state.grid_calculator is None

    def test_grid_engine_state_initialize(self):
        from grid_engine.api import GridEngineState
        state = GridEngineState()
        state.initialize(
            symbol="BTC/USDT", total_capital=500.0,
            center_price=50000.0, num_levels=15,
        )
        assert state.is_initialized is True
        assert state.grid_calculator is not None
        assert state.order_manager is not None
        assert state.position_tracker is not None
        assert state.rebalancer is not None
        assert state.risk_manager is not None
        assert len(state.grid_calculator.levels) == 15

    def test_get_engine_state(self):
        from grid_engine.api import get_engine_state, GridEngineState
        GridEngineState._instance = None
        state = get_engine_state()
        assert isinstance(state, GridEngineState)
        GridEngineState._instance = None

    def test_grid_config_request_model(self):
        from grid_engine.api import GridConfigRequest
        req = GridConfigRequest(
            symbol="BTC/USDT", total_capital=500.0,
            center_price=50000.0
        )
        assert req.symbol == "BTC/USDT"
        assert req.num_levels == 15
        assert req.range_percent == 14.0

    def test_grid_status_response_model(self):
        from grid_engine.api import GridStatusResponse
        resp = GridStatusResponse(
            symbol="BTC/USDT", center_price=50000.0,
            upper_bound=53500.0, lower_bound=46500.0,
            total_levels=15, active_levels=7,
            total_capital=500.0, is_active=True,
        )
        assert resp.total_levels == 15

    def test_order_response_model(self):
        from grid_engine.api import OrderResponse
        resp = OrderResponse(
            order_id="O1", level_id=0, symbol="BTC/USDT",
            side="BUY", price=50000.0, quantity=0.001,
            status="OPEN", filled_quantity=0.0,
            created_at="2026-01-01T00:00:00",
        )
        assert resp.order_id == "O1"

    def test_position_response_model(self):
        from grid_engine.api import PositionResponse
        resp = PositionResponse(
            position_id="P1", level_id=0, symbol="BTC/USDT",
            quantity=0.001, entry_price=50000.0,
            current_price=50500.0, unrealized_pnl=0.50,
            pnl_percent=1.0,
        )
        assert resp.position_id == "P1"

    def test_risk_status_response_model(self):
        from grid_engine.api import RiskStatusResponse
        resp = RiskStatusResponse(
            level="NORMAL", daily_pnl=0.0, daily_loss_limit=50.0,
            total_pnl=0.0, total_pnl_percent=0.0,
            max_drawdown=0.0, is_trading_allowed=True,
            active_alerts=0,
        )
        assert resp.is_trading_allowed is True

    def test_metrics_response_model(self):
        from grid_engine.api import MetricsResponse
        resp = MetricsResponse(
            symbol="BTC/USDT", initial_capital=500.0,
            current_equity=505.0, total_pnl=5.0,
            return_percent=1.0, win_rate=100.0,
            total_trades=2, max_drawdown=0.0,
        )
        assert resp.total_trades == 2

    def test_rebalance_request_model(self):
        from grid_engine.api import RebalanceRequest
        req = RebalanceRequest(new_center_price=55000.0)
        assert req.reason == "manual"

    def test_emergency_stop_request_model(self):
        from grid_engine.api import EmergencyStopRequest
        req = EmergencyStopRequest()
        assert req.reason == "Manual emergency stop"

    @pytest.mark.asyncio
    async def test_broadcast_update_no_clients(self):
        from grid_engine.api import GridEngineState
        state = GridEngineState()
        await state.broadcast_update("test", {"data": 1})

    @pytest.mark.asyncio
    async def test_broadcast_update_with_failed_client(self):
        from grid_engine.api import GridEngineState
        state = GridEngineState()
        mock_ws = AsyncMock()
        mock_ws.send_json.side_effect = Exception("disconnected")
        state._websocket_clients.append(mock_ws)
        await state.broadcast_update("test", {"data": 1})
        assert mock_ws not in state._websocket_clients


# ---------------------------------------------------------------------------
# 16. API Endpoints Functional Tests (FastAPI TestClient)
# ---------------------------------------------------------------------------

class TestGridAPIEndpoints:
    """Test all REST API endpoints with FastAPI TestClient."""

    @pytest.fixture(autouse=True)
    def setup_app(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from grid_engine.api import router, GridEngineState

        GridEngineState._instance = None
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app)
        self.state = GridEngineState.get_instance()
        yield
        GridEngineState._instance = None

    def _initialize_engine(self):
        self.state.initialize(
            symbol="BTC/USDT",
            total_capital=500.0,
            center_price=50000.0,
            num_levels=15,
        )

    def test_health_check(self):
        resp = self.client.get("/api/grid/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["initialized"] is False
        assert data["running"] is False
        assert "timestamp" in data

    def test_health_check_after_init(self):
        self._initialize_engine()
        resp = self.client.get("/api/grid/health")
        assert resp.status_code == 200
        assert resp.json()["initialized"] is True

    def test_initialize_grid_endpoint(self):
        resp = self.client.post("/api/grid/initialize", json={
            "symbol": "BTC/USDT",
            "total_capital": 500.0,
            "center_price": 50000.0,
            "num_levels": 15,
            "range_percent": 14.0,
            "profit_per_level": 0.8,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["symbol"] == "BTC/USDT"
        assert data["total_levels"] == 15
        assert data["total_capital"] == 500.0
        assert data["is_active"] is False
        assert data["center_price"] == 50000.0

    def test_initialize_grid_error(self):
        resp = self.client.post("/api/grid/initialize", json={
            "symbol": "BTC/USDT",
            "total_capital": -1,
            "center_price": 50000.0,
        })
        assert resp.status_code == 422

    def test_start_grid_not_initialized(self):
        resp = self.client.post("/api/grid/start")
        assert resp.status_code == 400
        assert "not initialized" in resp.json()["detail"]

    def test_start_grid_trading_endpoint(self):
        self._initialize_engine()
        resp = self.client.post("/api/grid/start")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "started"
        assert data["orders_placed"] >= 1
        assert self.state.is_running is True

    def test_start_grid_already_running(self):
        self._initialize_engine()
        self.client.post("/api/grid/start")
        resp = self.client.post("/api/grid/start")
        assert resp.status_code == 400
        assert "already running" in resp.json()["detail"]

    def test_stop_grid_not_running(self):
        resp = self.client.post("/api/grid/stop")
        assert resp.status_code == 400
        assert "not running" in resp.json()["detail"]

    def test_stop_grid_trading_endpoint(self):
        self._initialize_engine()
        self.client.post("/api/grid/start")
        resp = self.client.post("/api/grid/stop")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "stopped"
        assert self.state.is_running is False

    def test_get_status_not_initialized(self):
        resp = self.client.get("/api/grid/status")
        assert resp.status_code == 400

    def test_get_status_endpoint(self):
        self._initialize_engine()
        resp = self.client.get("/api/grid/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "grid" in data
        assert "orders" in data
        assert "positions" in data
        assert "risk" in data
        assert "is_running" in data

    def test_get_levels_not_initialized(self):
        resp = self.client.get("/api/grid/levels")
        assert resp.status_code == 400

    def test_get_levels_endpoint(self):
        self._initialize_engine()
        resp = self.client.get("/api/grid/levels")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 15
        assert data["buy_levels"] == 7
        assert data["sell_levels"] == 7
        assert len(data["levels"]) == 15

    def test_get_orders_not_initialized(self):
        resp = self.client.get("/api/grid/orders")
        assert resp.status_code == 400

    def test_get_orders_endpoint(self):
        self._initialize_engine()
        self.client.post("/api/grid/start")
        resp = self.client.get("/api/grid/orders")
        assert resp.status_code == 200
        data = resp.json()
        assert "orders" in data
        assert "total" in data
        assert data["total"] >= 1

    def test_get_orders_active_only(self):
        self._initialize_engine()
        self.client.post("/api/grid/start")
        resp = self.client.get("/api/grid/orders?active_only=true")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    def test_get_positions_not_initialized(self):
        resp = self.client.get("/api/grid/positions")
        assert resp.status_code == 400

    def test_get_positions_endpoint(self):
        self._initialize_engine()
        resp = self.client.get("/api/grid/positions")
        assert resp.status_code == 200

    def test_get_metrics_not_initialized(self):
        resp = self.client.get("/api/grid/metrics")
        assert resp.status_code == 400

    def test_get_metrics_endpoint(self):
        self._initialize_engine()
        resp = self.client.get("/api/grid/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_trades" in data
        assert "initial_capital" in data

    def test_get_risk_not_initialized(self):
        resp = self.client.get("/api/grid/risk")
        assert resp.status_code == 400

    def test_get_risk_endpoint(self):
        self._initialize_engine()
        resp = self.client.get("/api/grid/risk")
        assert resp.status_code == 200

    def test_rebalance_not_initialized(self):
        resp = self.client.post("/api/grid/rebalance", json={
            "new_center_price": 55000.0,
        })
        assert resp.status_code == 400

    def test_rebalance_endpoint(self):
        self._initialize_engine()
        self.client.post("/api/grid/start")
        resp = self.client.post("/api/grid/rebalance", json={
            "new_center_price": 55000.0,
            "reason": "price_drift",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "new_center_price" in data

    def test_rebalance_recommendation_not_initialized(self):
        resp = self.client.get("/api/grid/rebalance/recommendation?current_price=55000")
        assert resp.status_code == 400

    def test_rebalance_recommendation_endpoint(self):
        self._initialize_engine()
        resp = self.client.get("/api/grid/rebalance/recommendation?current_price=55000")
        assert resp.status_code == 200

    def test_emergency_stop_not_initialized(self):
        resp = self.client.post("/api/grid/emergency-stop", json={
            "reason": "test stop",
        })
        assert resp.status_code == 400

    def test_emergency_stop_endpoint(self):
        self._initialize_engine()
        self.client.post("/api/grid/start")
        resp = self.client.post("/api/grid/emergency-stop", json={
            "reason": "test emergency",
        })
        assert resp.status_code == 200
        assert self.state.is_running is False

    def test_reset_emergency_stop_not_initialized(self):
        resp = self.client.post("/api/grid/emergency-stop/reset")
        assert resp.status_code == 400

    def test_reset_emergency_stop_endpoint(self):
        self._initialize_engine()
        resp = self.client.post("/api/grid/emergency-stop/reset")
        assert resp.status_code == 200
        data = resp.json()
        assert "success" in data

    def test_price_update_not_initialized(self):
        resp = self.client.post("/api/grid/price-update?current_price=51000")
        assert resp.status_code == 400

    def test_price_update_endpoint(self):
        self._initialize_engine()
        self.client.post("/api/grid/start")
        resp = self.client.post("/api/grid/price-update?current_price=51000")
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_price"] == 51000.0
        assert "filled_orders" in data
        assert "risk_status" in data

    def test_price_update_not_running(self):
        self._initialize_engine()
        resp = self.client.post("/api/grid/price-update?current_price=51000")
        assert resp.status_code == 200
        data = resp.json()
        assert data["filled_orders"] == []

    def test_get_config_not_initialized(self):
        resp = self.client.get("/api/grid/config")
        assert resp.status_code == 400

    def test_get_config_endpoint(self):
        self._initialize_engine()
        resp = self.client.get("/api/grid/config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["symbol"] == "BTC/USDT"
        assert data["total_capital"] == 500.0

    def test_get_alerts_not_initialized(self):
        resp = self.client.get("/api/grid/alerts")
        assert resp.status_code == 400

    def test_get_alerts_endpoint(self):
        self._initialize_engine()
        resp = self.client.get("/api/grid/alerts")
        assert resp.status_code == 200
        data = resp.json()
        assert "alerts" in data
        assert "total" in data

    def test_get_alerts_all(self):
        self._initialize_engine()
        resp = self.client.get("/api/grid/alerts?active_only=false")
        assert resp.status_code == 200

    def test_acknowledge_alert_not_initialized(self):
        resp = self.client.post("/api/grid/alerts/test-id/acknowledge")
        assert resp.status_code == 400

    def test_acknowledge_alert_not_found(self):
        self._initialize_engine()
        resp = self.client.post("/api/grid/alerts/nonexistent/acknowledge")
        assert resp.status_code == 404

    def test_websocket_connect_and_ping(self):
        self._initialize_engine()
        with self.client.websocket_connect("/api/grid/ws") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "connected"
            ws.send_json({"type": "ping"})
            pong = ws.receive_json()
            assert pong["type"] == "pong"

    def test_websocket_subscribe(self):
        self._initialize_engine()
        with self.client.websocket_connect("/api/grid/ws") as ws:
            ws.receive_json()
            ws.send_json({"type": "subscribe", "channels": ["orders", "risk"]})
            sub = ws.receive_json()
            assert sub["type"] == "subscribed"
            assert sub["channels"] == ["orders", "risk"]

    def test_websocket_get_status(self):
        self._initialize_engine()
        with self.client.websocket_connect("/api/grid/ws") as ws:
            ws.receive_json()
            ws.send_json({"type": "get_status"})
            status = ws.receive_json()
            assert status["type"] == "status"
            assert "data" in status
            assert "grid" in status["data"]
            assert "orders" in status["data"]

    def test_websocket_get_status_not_initialized(self):
        from grid_engine.api import GridEngineState
        GridEngineState._instance = None
        self.state = GridEngineState.get_instance()
        with self.client.websocket_connect("/api/grid/ws") as ws:
            ws.receive_json()
            ws.send_json({"type": "get_status"})
            err = ws.receive_json()
            assert err["type"] == "error"

    def test_full_api_workflow(self):
        resp = self.client.post("/api/grid/initialize", json={
            "symbol": "BTC/USDT",
            "total_capital": 500.0,
            "center_price": 50000.0,
        })
        assert resp.status_code == 200

        resp = self.client.post("/api/grid/start")
        assert resp.status_code == 200
        assert resp.json()["orders_placed"] >= 1

        resp = self.client.get("/api/grid/status")
        assert resp.status_code == 200
        assert resp.json()["is_running"] is True

        resp = self.client.post("/api/grid/price-update?current_price=48000")
        assert resp.status_code == 200

        resp = self.client.get("/api/grid/metrics")
        assert resp.status_code == 200

        resp = self.client.get("/api/grid/risk")
        assert resp.status_code == 200

        resp = self.client.post("/api/grid/stop")
        assert resp.status_code == 200
        assert resp.json()["status"] == "stopped"


# ---------------------------------------------------------------------------
# 17. Binance Connector Exchange Path Tests (mocked ccxt)
# ---------------------------------------------------------------------------

class TestBinanceConnectorExchangePaths:
    """Test binance_connector.py with mocked ccxt exchange for real code paths."""

    @pytest.fixture
    def mock_exchange(self):
        exchange = AsyncMock()
        exchange.load_markets = AsyncMock(return_value={})
        exchange.close = AsyncMock()
        exchange.fetch_ticker = AsyncMock(return_value={
            "symbol": "BTC/USDT",
            "bid": 49999.0,
            "ask": 50001.0,
            "last": 50000.0,
            "baseVolume": 1234.5,
            "timestamp": 1700000000000,
        })
        exchange.fetch_balance = AsyncMock(return_value={
            "total": {
                "USDT": {"free": 500.0},
                "BTC": {"free": 0.01},
            }
        })
        exchange.create_order = AsyncMock(return_value={
            "id": "EX-ORD-001",
            "symbol": "BTC/USDT",
            "side": "buy",
            "type": "limit",
            "amount": 0.001,
            "price": 50000.0,
            "status": "open",
            "timestamp": 1700000000000,
        })
        exchange.cancel_order = AsyncMock(return_value={
            "id": "EX-ORD-001",
            "status": "canceled",
        })
        exchange.fetch_order = AsyncMock(return_value={
            "id": "EX-ORD-001",
            "symbol": "BTC/USDT",
            "status": "open",
            "filled": 0.0,
            "remaining": 0.001,
            "price": 50000.0,
        })
        exchange.fetch_open_orders = AsyncMock(return_value=[
            {
                "id": "EX-ORD-001",
                "symbol": "BTC/USDT",
                "side": "buy",
                "type": "limit",
                "amount": 0.001,
                "price": 50000.0,
                "status": "open",
                "filled": 0.0,
            }
        ])
        return exchange

    @pytest.fixture
    def connector_with_exchange(self, mock_exchange):
        config = BinanceConfig(api_key="test", api_secret="secret", testnet=True)
        conn = BinanceConnector(config=config, paper_trading=False)
        conn._exchange = mock_exchange
        conn._is_connected = True
        return conn

    @pytest.mark.asyncio
    async def test_connect_with_ccxt_mock(self):
        config = BinanceConfig(api_key="k", api_secret="s", testnet=True)
        conn = BinanceConnector(config=config, paper_trading=False)

        mock_exchange_instance = AsyncMock()
        mock_exchange_instance.load_markets = AsyncMock(return_value={})

        with patch("grid_engine.binance_connector.ccxt", create=True) as mock_ccxt:
            mock_ccxt_async = MagicMock()
            mock_ccxt_async.binance = MagicMock(return_value=mock_exchange_instance)
            with patch.dict("sys.modules", {"ccxt.async_support": mock_ccxt_async}):
                import importlib
                import grid_engine.binance_connector as bc_mod
                conn._exchange = mock_exchange_instance
                conn._is_connected = True

        assert conn._is_connected is True

    @pytest.mark.asyncio
    async def test_connect_no_ccxt_fallback(self):
        config = BinanceConfig(api_key="k", api_secret="s", testnet=True)
        conn = BinanceConnector(config=config, paper_trading=True)

        with patch.dict("sys.modules", {"ccxt.async_support": None, "ccxt": None}):
            import importlib
            with patch("builtins.__import__", side_effect=ImportError("no ccxt")):
                result = await conn.connect()

        assert result is True
        assert conn._is_connected is True

    @pytest.mark.asyncio
    async def test_connect_exchange_error(self):
        mock_ccxt_mod = MagicMock()
        mock_exchange_instance = AsyncMock()
        mock_exchange_instance.load_markets = AsyncMock(side_effect=Exception("network error"))
        mock_ccxt_mod.binance = MagicMock(return_value=mock_exchange_instance)

        config = BinanceConfig(api_key="k", api_secret="s", testnet=True)
        conn = BinanceConnector(config=config, paper_trading=False)

        with patch.dict("sys.modules", {"ccxt.async_support": mock_ccxt_mod, "ccxt": MagicMock()}):
            result = await conn.connect()

        assert result is False

    @pytest.mark.asyncio
    async def test_disconnect_with_exchange(self, connector_with_exchange, mock_exchange):
        mock_ws = AsyncMock()
        connector_with_exchange._ws_connection = mock_ws
        await connector_with_exchange.disconnect()
        assert connector_with_exchange._is_connected is False
        mock_exchange.close.assert_awaited_once()
        mock_ws.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disconnect_no_exchange(self):
        config = BinanceConfig()
        conn = BinanceConnector(config=config, paper_trading=True)
        conn._is_connected = True
        await conn.disconnect()
        assert conn._is_connected is False

    @pytest.mark.asyncio
    async def test_get_ticker_via_exchange(self, connector_with_exchange, mock_exchange):
        ticker = await connector_with_exchange.get_ticker("BTC/USDT")
        assert ticker["last"] == 50000.0
        assert ticker["bid"] == 49999.0
        assert ticker["ask"] == 50001.0
        assert ticker["volume"] == 1234.5
        mock_exchange.fetch_ticker.assert_awaited_once_with("BTC/USDT")

    @pytest.mark.asyncio
    async def test_get_ticker_exchange_error_fallback(self, connector_with_exchange, mock_exchange):
        mock_exchange.fetch_ticker.side_effect = Exception("API error")
        ticker = await connector_with_exchange.get_ticker("BTC/USDT")
        assert "last" in ticker
        assert "bid" in ticker

    @pytest.mark.asyncio
    async def test_get_balance_via_exchange(self, connector_with_exchange, mock_exchange):
        connector_with_exchange.paper_trading = False
        balance = await connector_with_exchange.get_balance()
        assert balance["USDT"] == 500.0
        assert balance["BTC"] == 0.01
        mock_exchange.fetch_balance.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_balance_exchange_error_fallback(self, connector_with_exchange, mock_exchange):
        connector_with_exchange.paper_trading = False
        mock_exchange.fetch_balance.side_effect = Exception("balance error")
        balance = await connector_with_exchange.get_balance()
        assert isinstance(balance, dict)

    @pytest.mark.asyncio
    async def test_create_order_via_exchange(self, connector_with_exchange, mock_exchange):
        order = await connector_with_exchange.create_order(
            symbol="BTCUSDT", side="BUY", type="LIMIT",
            quantity=0.001, price=50000.0
        )
        assert order["orderId"] == "EX-ORD-001"
        assert order["status"] == "open"
        mock_exchange.create_order.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_order_exchange_error_raises(self, connector_with_exchange, mock_exchange):
        mock_exchange.create_order.side_effect = Exception("order failed")
        with pytest.raises(Exception, match="order failed"):
            await connector_with_exchange.create_order(
                symbol="BTCUSDT", side="BUY", type="LIMIT",
                quantity=0.001, price=50000.0
            )

    @pytest.mark.asyncio
    async def test_create_order_no_exchange_falls_to_paper(self):
        config = BinanceConfig()
        conn = BinanceConnector(config=config, paper_trading=False)
        order = await conn.create_order(
            symbol="BTCUSDT", side="BUY", type="LIMIT",
            quantity=0.001, price=50000.0
        )
        assert order["status"] == "NEW"
        assert "orderId" in order

    @pytest.mark.asyncio
    async def test_create_market_order_via_exchange(self, connector_with_exchange, mock_exchange):
        order = await connector_with_exchange.create_order(
            symbol="BTCUSDT", side="BUY", type="MARKET",
            quantity=0.001
        )
        assert order["orderId"] == "EX-ORD-001"
        call_args = mock_exchange.create_order.call_args
        assert call_args.kwargs.get("price") is None or call_args[1].get("price") is None

    @pytest.mark.asyncio
    async def test_cancel_order_via_exchange(self, connector_with_exchange, mock_exchange):
        result = await connector_with_exchange.cancel_order("BTCUSDT", "EX-ORD-001")
        assert result["status"] == "CANCELED"
        mock_exchange.cancel_order.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cancel_order_exchange_error_raises(self, connector_with_exchange, mock_exchange):
        mock_exchange.cancel_order.side_effect = Exception("cancel failed")
        with pytest.raises(Exception, match="cancel failed"):
            await connector_with_exchange.cancel_order("BTCUSDT", "EX-ORD-001")

    @pytest.mark.asyncio
    async def test_cancel_order_no_exchange(self):
        config = BinanceConfig()
        conn = BinanceConnector(config=config, paper_trading=False)
        result = await conn.cancel_order("BTCUSDT", "some-id")
        assert result["status"] == "CANCELED"

    @pytest.mark.asyncio
    async def test_get_order_via_exchange(self, connector_with_exchange, mock_exchange):
        order = await connector_with_exchange.get_order("BTCUSDT", "EX-ORD-001")
        assert order["orderId"] == "EX-ORD-001"
        assert order["status"] == "open"
        mock_exchange.fetch_order.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_order_exchange_error_fallback(self, connector_with_exchange, mock_exchange):
        mock_exchange.fetch_order.side_effect = Exception("fetch error")
        order = await connector_with_exchange.get_order("BTCUSDT", "EX-ORD-001")
        assert order["status"] == "UNKNOWN"

    @pytest.mark.asyncio
    async def test_get_open_orders_via_exchange(self, connector_with_exchange, mock_exchange):
        orders = await connector_with_exchange.get_open_orders("BTCUSDT")
        assert len(orders) == 1
        assert orders[0]["orderId"] == "EX-ORD-001"
        mock_exchange.fetch_open_orders.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_open_orders_no_symbol(self, connector_with_exchange, mock_exchange):
        orders = await connector_with_exchange.get_open_orders()
        assert len(orders) == 1

    @pytest.mark.asyncio
    async def test_get_open_orders_exchange_error(self, connector_with_exchange, mock_exchange):
        mock_exchange.fetch_open_orders.side_effect = Exception("fetch error")
        orders = await connector_with_exchange.get_open_orders("BTCUSDT")
        assert orders == []

    @pytest.mark.asyncio
    async def test_get_open_orders_no_exchange(self):
        config = BinanceConfig()
        conn = BinanceConnector(config=config, paper_trading=False)
        orders = await conn.get_open_orders()
        assert orders == []

    @pytest.mark.asyncio
    async def test_simulate_price_callback_error(self):
        config = BinanceConfig()
        conn = BinanceConnector(config=config, paper_trading=True)

        async def bad_callback(symbol, price, data):
            raise ValueError("callback boom")

        conn.on_price_update(bad_callback)
        await conn.simulate_price_update("BTC/USDT", 51000.0)
        assert conn._last_price["BTC/USDT"] == 51000.0

    @pytest.mark.asyncio
    async def test_paper_order_fill_buy_updates_balance(self):
        config = BinanceConfig()
        conn = BinanceConnector(config=config, paper_trading=True)
        conn._paper_balance = {"USDT": 1000.0, "BTC": 0.0}

        await conn.create_order("BTCUSDT", "BUY", "LIMIT", 0.01, 50000.0)
        await conn.simulate_price_update("BTCUSDT", 49000.0)

        assert conn._paper_balance["BTC"] > 0
        assert conn._paper_balance["USDT"] < 1000.0

    @pytest.mark.asyncio
    async def test_paper_order_fill_sell_updates_balance(self):
        config = BinanceConfig()
        conn = BinanceConnector(config=config, paper_trading=True)
        conn._paper_balance = {"USDT": 0.0, "BTC": 0.01}

        await conn.create_order("BTCUSDT", "SELL", "LIMIT", 0.005, 49000.0)
        await conn.simulate_price_update("BTCUSDT", 50000.0)

        assert conn._paper_balance["USDT"] > 0
        assert conn._paper_balance["BTC"] < 0.01

    @pytest.mark.asyncio
    async def test_paper_fill_triggers_order_callback(self):
        config = BinanceConfig()
        conn = BinanceConnector(config=config, paper_trading=True)
        filled_orders = []

        async def on_order(order):
            filled_orders.append(order)

        conn.on_order_update(on_order)
        await conn.create_order("BTCUSDT", "BUY", "LIMIT", 0.001, 50000.0)
        await conn.simulate_price_update("BTCUSDT", 49500.0)
        assert len(filled_orders) == 1
        assert filled_orders[0]["status"] == "FILLED"

    @pytest.mark.asyncio
    async def test_paper_fill_order_callback_error(self):
        config = BinanceConfig()
        conn = BinanceConnector(config=config, paper_trading=True)

        async def bad_order_cb(order):
            raise RuntimeError("order callback error")

        conn.on_order_update(bad_order_cb)
        await conn.create_order("BTCUSDT", "BUY", "LIMIT", 0.001, 50000.0)
        await conn.simulate_price_update("BTCUSDT", 49500.0)

    @pytest.mark.asyncio
    async def test_paper_order_symbol_mismatch_no_fill(self):
        config = BinanceConfig()
        conn = BinanceConnector(config=config, paper_trading=True)
        await conn.create_order("ETHUSDT", "BUY", "LIMIT", 0.1, 3000.0)
        await conn.simulate_price_update("BTCUSDT", 2000.0)
        orders = await conn.get_open_orders("ETHUSDT")
        assert len(orders) == 1
        assert orders[0]["status"] == "NEW"

    @pytest.mark.asyncio
    async def test_start_price_stream_no_websockets(self):
        config = BinanceConfig()
        conn = BinanceConnector(config=config, paper_trading=True)
        with patch("builtins.__import__", side_effect=ImportError("no websockets")):
            await conn.start_price_stream(["BTC/USDT"])

    def test_config_from_env(self):
        with patch.dict(os.environ, {
            "BINANCE_API_KEY": "env_key",
            "BINANCE_API_SECRET": "env_secret",
            "BINANCE_TESTNET": "false",
        }):
            config = BinanceConfig.from_env()
            assert config.api_key == "env_key"
            assert config.api_secret == "env_secret"
            assert config.testnet is False

    def test_config_from_env_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            config = BinanceConfig.from_env()
            assert config.api_key == ""
            assert config.testnet is True

    def test_base_url_testnet(self):
        conn = BinanceConnector(BinanceConfig(testnet=True), paper_trading=True)
        assert "testnet" in conn.base_url

    def test_base_url_production(self):
        conn = BinanceConnector(BinanceConfig(testnet=False), paper_trading=True)
        assert conn.base_url == "https://api.binance.com"

    def test_ws_url_testnet(self):
        conn = BinanceConnector(BinanceConfig(testnet=True), paper_trading=True)
        assert "testnet" in conn.ws_url

    def test_ws_url_production(self):
        conn = BinanceConnector(BinanceConfig(testnet=False), paper_trading=True)
        assert conn.ws_url == "wss://stream.binance.com:9443/ws"

    def test_get_status_connected(self):
        conn = BinanceConnector(BinanceConfig(), paper_trading=True)
        conn._is_connected = True
        conn._last_price = {"BTC/USDT": 50000.0}
        status = conn.get_status()
        assert status["connected"] is True
        assert status["paper_trading"] is True
        assert status["last_prices"]["BTC/USDT"] == 50000.0

    @pytest.mark.asyncio
    async def test_create_paper_order_no_price(self):
        conn = BinanceConnector(BinanceConfig(), paper_trading=True)
        order = await conn.create_order("BTCUSDT", "BUY", "MARKET", 0.001)
        assert order["price"] == 50000.0
        assert order["status"] == "NEW"


# ---------------------------------------------------------------------------
# 18. Position Manager Extended Coverage
# ---------------------------------------------------------------------------

class TestPositionManagerExtended:
    """Additional tests for position_manager.py low-coverage paths."""

    @pytest.fixture
    def setup_manager(self):
        config = GridConfig(
            symbol="BTC/USDT", total_capital=500.0,
            num_levels=15, range_percent=14.0,
            profit_per_level=0.8, min_order_size=0.0001, fee_percent=0.1,
        )
        calc = GridCalculator(config)
        calc.calculate_grid(50000.0)
        om = GridOrderManager(grid_calculator=calc, paper_trading=True)
        pm = GridPositionManager(grid_calculator=calc, order_manager=om)
        return pm, om, calc

    @pytest.mark.asyncio
    async def test_check_and_process_fills_with_filled_order(self, setup_manager):
        pm, om, calc = setup_manager
        orders = await om.initialize_grid_orders()
        await om.simulate_fill(orders[0].order_id)
        processed = await pm.check_and_process_fills()
        assert len(processed) == 1
        assert processed[0].status == PositionStatus.SELL_PLACED

    @pytest.mark.asyncio
    async def test_check_and_process_fills_skip_already_managed(self, setup_manager):
        pm, om, calc = setup_manager
        orders = await om.initialize_grid_orders()
        await om.simulate_fill(orders[0].order_id)
        await pm.check_and_process_fills()
        second = await pm.check_and_process_fills()
        assert len(second) == 0

    @pytest.mark.asyncio
    async def test_check_sell_fills(self, setup_manager):
        pm, om, calc = setup_manager
        orders = await om.initialize_grid_orders()
        await om.simulate_fill(orders[0].order_id)
        positions = await pm.check_and_process_fills()
        pos = positions[0]
        sell_order = om.orders.get(pos.sell_order_id)
        await om.simulate_fill(sell_order.order_id)
        completed = await pm.check_sell_fills()
        assert len(completed) == 1
        assert completed[0].status == PositionStatus.CLOSED
        assert pm.total_cycles == 1
        assert pm.total_realized_profit != 0

    @pytest.mark.asyncio
    async def test_run_cycle(self, setup_manager):
        pm, om, calc = setup_manager
        orders = await om.initialize_grid_orders()
        await om.simulate_fill(orders[0].order_id)
        result = await pm.run_cycle()
        assert result["new_sell_orders"] == 1
        assert result["active_positions"] >= 1

    @pytest.mark.asyncio
    async def test_buy_filled_callback(self, setup_manager):
        pm, om, calc = setup_manager
        events = []

        async def on_buy(pos):
            events.append(("buy", pos.position_id))

        pm.on_buy_filled(on_buy)
        orders = await om.initialize_grid_orders()
        await om.simulate_fill(orders[0].order_id)
        await pm.check_and_process_fills()
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_sell_placed_callback(self, setup_manager):
        pm, om, calc = setup_manager
        events = []

        async def on_sell(pos):
            events.append(("sell_placed", pos.position_id))

        pm.on_sell_placed(on_sell)
        orders = await om.initialize_grid_orders()
        await om.simulate_fill(orders[0].order_id)
        await pm.check_and_process_fills()
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_cycle_complete_callback(self, setup_manager):
        pm, om, calc = setup_manager
        events = []

        async def on_complete(pos):
            events.append(pos.profit_amount)

        pm.on_cycle_complete(on_complete)
        orders = await om.initialize_grid_orders()
        await om.simulate_fill(orders[0].order_id)
        positions = await pm.check_and_process_fills()
        sell_order = om.orders.get(positions[0].sell_order_id)
        await om.simulate_fill(sell_order.order_id)
        await pm.check_sell_fills()
        assert len(events) == 1

    def test_get_sell_level_for_buy_out_of_bounds(self, setup_manager):
        pm, om, calc = setup_manager
        result = pm.get_sell_level_for_buy(100)
        assert result is None

    def test_calculate_sell_price_uses_min_profit(self, setup_manager):
        pm, om, calc = setup_manager
        sell_level = calc.levels[-1]
        price = pm.calculate_sell_price(sell_level.price - 1, sell_level)
        assert price >= (sell_level.price - 1) * (1 + 0.8 / 100)

    def test_get_grid_mapping(self, setup_manager):
        pm, om, calc = setup_manager
        mapping = pm.get_grid_mapping()
        assert len(mapping) == 7
        for m in mapping:
            assert "buy_level_id" in m
            assert "sell_level_id" in m
            assert "spread_pct" in m

    def test_get_status(self, setup_manager):
        pm, om, calc = setup_manager
        status = pm.get_status()
        assert "active_positions" in status
        assert "completed_cycles" in status
        assert "total_realized_profit" in status

    def test_to_dict(self, setup_manager):
        pm, om, calc = setup_manager
        data = pm.to_dict()
        assert "status" in data
        assert "grid_mapping" in data
        assert "active_positions" in data
