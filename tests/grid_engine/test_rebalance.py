"""
Tests for Rebalance Module.
"""

import pytest
from datetime import datetime, timedelta

import sys
sys.path.insert(0, '/home/ubuntu/repos/Projet_AUTOBOT/src')

from grid_engine.grid_calculator import GridCalculator, GridConfig, GridSide
from grid_engine.order_manager import GridOrderManager
from grid_engine.position_tracker import PositionTracker, TradeType
from grid_engine.rebalance import (
    GridRebalancer,
    RebalanceAction,
    RebalanceReason,
    RebalanceStatus,
)


class TestRebalanceReason:
    """Tests for RebalanceReason enum."""
    
    def test_values(self):
        """Test enum values."""
        assert RebalanceReason.PRICE_ABOVE_GRID.value == "price_above_grid"
        assert RebalanceReason.PRICE_BELOW_GRID.value == "price_below_grid"
        assert RebalanceReason.MANUAL_REBALANCE.value == "manual_rebalance"
        assert RebalanceReason.SCHEDULED_REBALANCE.value == "scheduled_rebalance"


class TestRebalanceStatus:
    """Tests for RebalanceStatus enum."""
    
    def test_values(self):
        """Test enum values."""
        assert RebalanceStatus.PENDING.value == "pending"
        assert RebalanceStatus.IN_PROGRESS.value == "in_progress"
        assert RebalanceStatus.COMPLETED.value == "completed"
        assert RebalanceStatus.FAILED.value == "failed"


class TestRebalanceAction:
    """Tests for RebalanceAction dataclass."""
    
    def test_action_creation(self):
        """Test rebalance action creation."""
        action = RebalanceAction(
            action_id="rebal-001",
            reason=RebalanceReason.PRICE_ABOVE_GRID,
            old_center_price=50000.0,
            new_center_price=55000.0,
            price_at_trigger=55500.0,
        )
        
        assert action.action_id == "rebal-001"
        assert action.reason == RebalanceReason.PRICE_ABOVE_GRID
        assert action.old_center_price == 50000.0
        assert action.new_center_price == 55000.0
        assert action.status == RebalanceStatus.PENDING
    
    def test_price_change_percent(self):
        """Test price change percentage calculation."""
        action = RebalanceAction(
            action_id="rebal-001",
            reason=RebalanceReason.PRICE_ABOVE_GRID,
            old_center_price=50000.0,
            new_center_price=55000.0,
            price_at_trigger=55500.0,
        )
        
        assert action.price_change_percent == 10.0
    
    def test_to_dict(self):
        """Test action serialization."""
        action = RebalanceAction(
            action_id="rebal-001",
            reason=RebalanceReason.PRICE_ABOVE_GRID,
            old_center_price=50000.0,
            new_center_price=55000.0,
            price_at_trigger=55500.0,
        )
        
        result = action.to_dict()
        
        assert result["action_id"] == "rebal-001"
        assert result["reason"] == "price_above_grid"
        assert result["status"] == "pending"


class TestGridRebalancer:
    """Tests for GridRebalancer class."""
    
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
    
    @pytest.fixture
    def position_tracker(self):
        """Create test position tracker."""
        return PositionTracker(
            symbol="BTC/USDT",
            initial_capital=500.0
        )
    
    @pytest.fixture
    def rebalancer(self, grid_calculator, order_manager, position_tracker):
        """Create test rebalancer."""
        return GridRebalancer(
            grid_calculator=grid_calculator,
            order_manager=order_manager,
            position_tracker=position_tracker,
            rebalance_threshold_percent=1.0,
        )
    
    def test_initialization(self, rebalancer):
        """Test rebalancer initialization."""
        assert rebalancer.rebalance_threshold == 1.0
        assert rebalancer.min_rebalance_interval == 300
        assert len(rebalancer.rebalance_history) == 0
    
    def test_should_rebalance_price_above(self, rebalancer, grid_calculator):
        """Test rebalance detection when price above grid."""
        upper_bound = grid_calculator.upper_bound
        high_price = upper_bound * 1.02
        
        should, reason = rebalancer.should_rebalance(high_price)
        
        assert should == True
        assert reason == RebalanceReason.PRICE_ABOVE_GRID
    
    def test_should_rebalance_price_below(self, rebalancer, grid_calculator):
        """Test rebalance detection when price below grid."""
        lower_bound = grid_calculator.lower_bound
        low_price = lower_bound * 0.98
        
        should, reason = rebalancer.should_rebalance(low_price)
        
        assert should == True
        assert reason == RebalanceReason.PRICE_BELOW_GRID
    
    def test_should_not_rebalance_in_grid(self, rebalancer, grid_calculator):
        """Test no rebalance when price in grid."""
        center = grid_calculator.center_price
        
        should, reason = rebalancer.should_rebalance(center)
        
        assert should == False
        assert reason is None
    
    def test_min_interval_respected(self, rebalancer, grid_calculator):
        """Test minimum interval between rebalances."""
        action = RebalanceAction(
            action_id="rebal-001",
            reason=RebalanceReason.PRICE_ABOVE_GRID,
            old_center_price=50000.0,
            new_center_price=55000.0,
            price_at_trigger=55500.0,
            status=RebalanceStatus.COMPLETED,
        )
        rebalancer.rebalance_history.append(action)
        rebalancer._last_rebalance_time = datetime.utcnow()
        
        high_price = grid_calculator.upper_bound * 1.02
        should, reason = rebalancer.should_rebalance(high_price)
        
        assert should == False
    
    @pytest.mark.asyncio
    async def test_execute_rebalance(self, rebalancer, grid_calculator):
        """Test rebalance execution."""
        new_center = 55000.0
        
        action = await rebalancer.execute_rebalance(
            new_center_price=new_center,
            reason=RebalanceReason.MANUAL_REBALANCE
        )
        
        assert action is not None
        assert action.status == RebalanceStatus.COMPLETED
        assert action.new_center_price == new_center
        assert grid_calculator.center_price == new_center
    
    @pytest.mark.asyncio
    async def test_check_and_rebalance(self, rebalancer, grid_calculator):
        """Test automatic check and rebalance."""
        high_price = grid_calculator.upper_bound * 1.02
        
        action = await rebalancer.check_and_rebalance(high_price)
        
        assert action is not None
        assert action.reason == RebalanceReason.PRICE_ABOVE_GRID
    
    def test_get_rebalance_recommendation(self, rebalancer, grid_calculator):
        """Test rebalance recommendation."""
        high_price = grid_calculator.upper_bound * 1.02
        
        recommendation = rebalancer.get_rebalance_recommendation(high_price)
        
        assert "should_rebalance" in recommendation
        assert "reason" in recommendation
        assert "suggested_center_price" in recommendation
    
    def test_get_distance_from_bounds(self, rebalancer, grid_calculator):
        """Test distance from bounds calculation."""
        center = grid_calculator.center_price
        
        distances = rebalancer.get_distance_from_bounds(center)
        
        assert "distance_from_upper" in distances
        assert "distance_from_lower" in distances
        assert distances["distance_from_upper"] > 0
        assert distances["distance_from_lower"] > 0
    
    def test_callback_registration(self, rebalancer):
        """Test callback registration."""
        callback_called = []
        
        def on_rebalance(action):
            callback_called.append(action)
        
        rebalancer.on_rebalance(on_rebalance)
        
        assert len(rebalancer._on_rebalance_callbacks) == 1
    
    def test_get_status(self, rebalancer):
        """Test status retrieval."""
        status = rebalancer.get_status()
        
        assert "rebalance_threshold" in status
        assert "min_interval_seconds" in status
        assert "total_rebalances" in status
        assert "last_rebalance_time" in status
    
    def test_to_dict(self, rebalancer):
        """Test full serialization."""
        result = rebalancer.to_dict()
        
        assert "status" in result
        assert "history" in result
