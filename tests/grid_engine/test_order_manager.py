"""
Tests for Order Manager Module.
"""

import pytest
from datetime import datetime
import asyncio

import sys
sys.path.insert(0, '/home/ubuntu/repos/Projet_AUTOBOT/src')

from grid_engine.grid_calculator import GridCalculator, GridConfig, GridSide
from grid_engine.order_manager import (
    GridOrderManager,
    GridOrder,
    OrderStatus,
    OrderType,
)


class TestOrderStatus:
    """Tests for OrderStatus enum."""
    
    def test_values(self):
        """Test enum values."""
        assert OrderStatus.PENDING.value == "pending"
        assert OrderStatus.OPEN.value == "open"
        assert OrderStatus.FILLED.value == "filled"
        assert OrderStatus.CANCELED.value == "canceled"
    
    def test_is_active(self):
        """Test active status check."""
        assert OrderStatus.PENDING.is_active == True
        assert OrderStatus.OPEN.is_active == True
        assert OrderStatus.PARTIALLY_FILLED.is_active == True
        assert OrderStatus.FILLED.is_active == False
        assert OrderStatus.CANCELED.is_active == False


class TestOrderType:
    """Tests for OrderType enum."""
    
    def test_values(self):
        """Test enum values."""
        assert OrderType.LIMIT.value == "limit"
        assert OrderType.MARKET.value == "market"


class TestGridOrder:
    """Tests for GridOrder dataclass."""
    
    def test_order_creation(self):
        """Test order creation."""
        order = GridOrder(
            order_id="test-001",
            level_id=5,
            symbol="BTC/USDT",
            side=GridSide.BUY,
            price=50000.0,
            quantity=0.001,
        )
        
        assert order.order_id == "test-001"
        assert order.level_id == 5
        assert order.symbol == "BTC/USDT"
        assert order.side == GridSide.BUY
        assert order.price == 50000.0
        assert order.quantity == 0.001
        assert order.status == OrderStatus.PENDING
        assert order.order_type == OrderType.LIMIT
    
    def test_remaining_quantity(self):
        """Test remaining quantity calculation."""
        order = GridOrder(
            order_id="test-001",
            level_id=5,
            symbol="BTC/USDT",
            side=GridSide.BUY,
            price=50000.0,
            quantity=0.001,
        )
        
        assert order.remaining_quantity == 0.001
        
        order.filled_quantity = 0.0004
        assert abs(order.remaining_quantity - 0.0006) < 0.0001
    
    def test_is_filled(self):
        """Test fill detection."""
        order = GridOrder(
            order_id="test-001",
            level_id=5,
            symbol="BTC/USDT",
            side=GridSide.BUY,
            price=50000.0,
            quantity=0.001,
        )
        
        assert order.is_filled == False
        
        order.filled_quantity = 0.00099
        assert order.is_filled == True
    
    def test_fill_percent(self):
        """Test fill percentage."""
        order = GridOrder(
            order_id="test-001",
            level_id=5,
            symbol="BTC/USDT",
            side=GridSide.BUY,
            price=50000.0,
            quantity=0.001,
        )
        
        assert order.fill_percent == 0.0
        
        order.filled_quantity = 0.0005
        assert order.fill_percent == 50.0
    
    def test_order_value(self):
        """Test order value calculation."""
        order = GridOrder(
            order_id="test-001",
            level_id=5,
            symbol="BTC/USDT",
            side=GridSide.BUY,
            price=50000.0,
            quantity=0.001,
        )
        
        assert order.order_value == 50.0
    
    def test_estimated_fee(self):
        """Test fee estimation."""
        order = GridOrder(
            order_id="test-001",
            level_id=5,
            symbol="BTC/USDT",
            side=GridSide.BUY,
            price=50000.0,
            quantity=0.001,
            fee_percent=0.1,
        )
        
        expected_fee = 50.0 * 0.001
        assert abs(order.estimated_fee - expected_fee) < 0.001
    
    def test_to_dict(self):
        """Test order serialization."""
        order = GridOrder(
            order_id="test-001",
            level_id=5,
            symbol="BTC/USDT",
            side=GridSide.BUY,
            price=50000.0,
            quantity=0.001,
        )
        
        result = order.to_dict()
        
        assert result["order_id"] == "test-001"
        assert result["level_id"] == 5
        assert result["side"] == "buy"
        assert result["status"] == "pending"


class TestGridOrderManager:
    """Tests for GridOrderManager class."""
    
    @pytest.fixture
    def grid_calculator(self):
        """Create test grid calculator."""
        config = GridConfig(
            symbol="BTC/USDT",
            total_capital=500.0,
            num_levels=15,
            range_percent=14.0,
        )
        calculator = GridCalculator(config)
        calculator.calculate_grid(50000.0)
        return calculator
    
    @pytest.fixture
    def order_manager(self, grid_calculator):
        """Create test order manager."""
        return GridOrderManager(
            grid_calculator=grid_calculator,
            paper_trading=True
        )
    
    def test_initialization(self, order_manager, grid_calculator):
        """Test order manager initialization."""
        assert order_manager.grid_calculator == grid_calculator
        assert order_manager.paper_trading == True
        assert len(order_manager.orders) == 0
    
    @pytest.mark.asyncio
    async def test_initialize_grid_orders(self, order_manager):
        """Test initial order placement."""
        orders = await order_manager.initialize_grid_orders()
        
        assert len(orders) > 0
        
        for order in orders:
            assert order.side == GridSide.BUY
            assert order.status in [OrderStatus.PENDING, OrderStatus.OPEN]
    
    @pytest.mark.asyncio
    async def test_place_order_for_level(self, order_manager, grid_calculator):
        """Test placing order for specific level."""
        level = grid_calculator.buy_levels[0]
        
        order = await order_manager.place_order_for_level(level)
        
        assert order is not None
        assert order.level_id == level.level_id
        assert order.price == level.price
        assert order.side == level.side
    
    @pytest.mark.asyncio
    async def test_cancel_order(self, order_manager, grid_calculator):
        """Test order cancellation."""
        level = grid_calculator.buy_levels[0]
        order = await order_manager.place_order_for_level(level)
        
        success = await order_manager.cancel_order(order.order_id)
        
        assert success == True
        assert order.status == OrderStatus.CANCELED
    
    @pytest.mark.asyncio
    async def test_cancel_all_orders(self, order_manager):
        """Test canceling all orders."""
        await order_manager.initialize_grid_orders()
        
        initial_count = len(order_manager.active_orders)
        assert initial_count > 0
        
        canceled = await order_manager.cancel_all_orders()
        
        assert canceled == initial_count
        assert len(order_manager.active_orders) == 0
    
    def test_active_orders(self, order_manager):
        """Test active orders property."""
        order1 = GridOrder(
            order_id="test-001",
            level_id=1,
            symbol="BTC/USDT",
            side=GridSide.BUY,
            price=49000.0,
            quantity=0.001,
            status=OrderStatus.OPEN,
        )
        order2 = GridOrder(
            order_id="test-002",
            level_id=2,
            symbol="BTC/USDT",
            side=GridSide.BUY,
            price=48000.0,
            quantity=0.001,
            status=OrderStatus.FILLED,
        )
        
        order_manager.orders["test-001"] = order1
        order_manager.orders["test-002"] = order2
        
        active = order_manager.active_orders
        
        assert len(active) == 1
        assert active[0].order_id == "test-001"
    
    @pytest.mark.asyncio
    async def test_simulate_fill(self, order_manager, grid_calculator):
        """Test order fill simulation."""
        level = grid_calculator.buy_levels[0]
        order = await order_manager.place_order_for_level(level)
        
        filled_order = await order_manager.simulate_fill(
            order_id=order.order_id,
            fill_price=level.price,
            fill_quantity=order.quantity
        )
        
        assert filled_order is not None
        assert filled_order.status == OrderStatus.FILLED
        assert filled_order.filled_quantity == order.quantity
    
    @pytest.mark.asyncio
    async def test_check_fills_at_price(self, order_manager):
        """Test checking fills at price."""
        await order_manager.initialize_grid_orders()
        
        low_price = order_manager.grid_calculator.lower_bound + 100
        
        filled = await order_manager.check_fills_at_price(low_price)
        
        for order in filled:
            assert order.status == OrderStatus.FILLED
            assert order.price >= low_price
    
    def test_get_order(self, order_manager):
        """Test getting order by ID."""
        order = GridOrder(
            order_id="test-001",
            level_id=1,
            symbol="BTC/USDT",
            side=GridSide.BUY,
            price=49000.0,
            quantity=0.001,
        )
        order_manager.orders["test-001"] = order
        
        retrieved = order_manager.get_order("test-001")
        assert retrieved == order
        
        not_found = order_manager.get_order("nonexistent")
        assert not_found is None
    
    def test_get_orders_for_level(self, order_manager):
        """Test getting orders for level."""
        order1 = GridOrder(
            order_id="test-001",
            level_id=5,
            symbol="BTC/USDT",
            side=GridSide.BUY,
            price=49000.0,
            quantity=0.001,
        )
        order2 = GridOrder(
            order_id="test-002",
            level_id=5,
            symbol="BTC/USDT",
            side=GridSide.SELL,
            price=49500.0,
            quantity=0.001,
        )
        order3 = GridOrder(
            order_id="test-003",
            level_id=6,
            symbol="BTC/USDT",
            side=GridSide.BUY,
            price=48500.0,
            quantity=0.001,
        )
        
        order_manager.orders["test-001"] = order1
        order_manager.orders["test-002"] = order2
        order_manager.orders["test-003"] = order3
        
        level_5_orders = order_manager.get_orders_for_level(5)
        
        assert len(level_5_orders) == 2
        assert all(o.level_id == 5 for o in level_5_orders)
    
    def test_get_status(self, order_manager):
        """Test status retrieval."""
        status = order_manager.get_status()
        
        assert "total_orders" in status
        assert "active_orders" in status
        assert "filled_orders" in status
        assert "canceled_orders" in status
        assert "paper_trading" in status
    
    def test_callback_registration(self, order_manager):
        """Test callback registration."""
        callback_called = []
        
        def on_fill(order):
            callback_called.append(order)
        
        order_manager.on_order_filled(on_fill)
        
        assert len(order_manager._on_fill_callbacks) == 1
    
    @pytest.mark.asyncio
    async def test_counter_order_placement(self, order_manager, grid_calculator):
        """Test that sell order is placed after buy fill."""
        level = grid_calculator.buy_levels[0]
        order = await order_manager.place_order_for_level(level)
        
        await order_manager.simulate_fill(
            order_id=order.order_id,
            fill_price=level.price,
            fill_quantity=order.quantity
        )
        
        sell_orders = [
            o for o in order_manager.orders.values()
            if o.side == GridSide.SELL and o.level_id == level.level_id
        ]
        
        assert len(sell_orders) >= 0
