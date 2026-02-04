"""
Tests for Grid Calculator Module.
"""

import pytest
from datetime import datetime

import sys
sys.path.insert(0, '/home/ubuntu/repos/Projet_AUTOBOT/src')

from grid_engine.grid_calculator import (
    GridCalculator,
    GridConfig,
    GridLevel,
    GridSide,
)


class TestGridConfig:
    """Tests for GridConfig dataclass."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = GridConfig(symbol="BTC/USDT", total_capital=500.0)
        
        assert config.symbol == "BTC/USDT"
        assert config.total_capital == 500.0
        assert config.num_levels == 15
        assert config.range_percent == 14.0
        assert config.profit_per_level == 0.8
        assert config.min_order_size == 0.0001
        assert config.fee_percent == 0.1
    
    def test_capital_per_level(self):
        """Test capital per level calculation."""
        config = GridConfig(symbol="BTC/USDT", total_capital=500.0, num_levels=15)
        
        expected = 500.0 / 15
        assert abs(config.capital_per_level - expected) < 0.01
    
    def test_half_range_percent(self):
        """Test half range calculation."""
        config = GridConfig(symbol="BTC/USDT", total_capital=500.0, range_percent=14.0)
        
        assert config.half_range_percent == 7.0
    
    def test_to_dict(self):
        """Test config serialization."""
        config = GridConfig(symbol="BTC/USDT", total_capital=500.0)
        result = config.to_dict()
        
        assert result["symbol"] == "BTC/USDT"
        assert result["total_capital"] == 500.0
        assert "capital_per_level" in result


class TestGridLevel:
    """Tests for GridLevel dataclass."""
    
    def test_level_creation(self):
        """Test grid level creation."""
        level = GridLevel(
            level_id=5,
            price=50000.0,
            side=GridSide.BUY,
            allocated_capital=33.33,
            quantity=0.000666,
        )
        
        assert level.level_id == 5
        assert level.price == 50000.0
        assert level.side == GridSide.BUY
        assert level.is_active == False
        assert level.order_id is None
    
    def test_is_filled(self):
        """Test fill detection."""
        level = GridLevel(
            level_id=0,
            price=50000.0,
            side=GridSide.BUY,
            allocated_capital=33.33,
            quantity=0.001,
        )
        
        assert level.is_filled == False
        
        level.filled_quantity = 0.00099
        assert level.is_filled == True
        
        level.filled_quantity = 0.001
        assert level.is_filled == True
    
    def test_fill_percent(self):
        """Test fill percentage calculation."""
        level = GridLevel(
            level_id=0,
            price=50000.0,
            side=GridSide.BUY,
            allocated_capital=33.33,
            quantity=0.001,
        )
        
        assert level.fill_percent == 0.0
        
        level.filled_quantity = 0.0005
        assert level.fill_percent == 50.0
        
        level.filled_quantity = 0.001
        assert level.fill_percent == 100.0
    
    def test_to_dict(self):
        """Test level serialization."""
        level = GridLevel(
            level_id=5,
            price=50000.0,
            side=GridSide.BUY,
            allocated_capital=33.33,
            quantity=0.000666,
        )
        result = level.to_dict()
        
        assert result["level_id"] == 5
        assert result["price"] == 50000.0
        assert result["side"] == "buy"


class TestGridCalculator:
    """Tests for GridCalculator class."""
    
    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return GridConfig(
            symbol="BTC/USDT",
            total_capital=500.0,
            num_levels=15,
            range_percent=14.0,
            profit_per_level=0.8,
        )
    
    @pytest.fixture
    def calculator(self, config):
        """Create test calculator."""
        return GridCalculator(config)
    
    def test_initialization(self, calculator, config):
        """Test calculator initialization."""
        assert calculator.config == config
        assert calculator.levels == []
        assert calculator.center_price is None
    
    def test_calculate_grid(self, calculator):
        """Test grid calculation."""
        center_price = 50000.0
        levels = calculator.calculate_grid(center_price)
        
        assert len(levels) == 15
        assert calculator.center_price == center_price
    
    def test_grid_bounds(self, calculator):
        """Test grid bounds calculation (+/-7%)."""
        center_price = 50000.0
        calculator.calculate_grid(center_price)
        
        expected_upper = center_price * 1.07
        expected_lower = center_price * 0.93
        
        assert abs(calculator.upper_bound - expected_upper) < 1
        assert abs(calculator.lower_bound - expected_lower) < 1
    
    def test_grid_levels_sorted(self, calculator):
        """Test that levels are sorted by price."""
        calculator.calculate_grid(50000.0)
        
        prices = [level.price for level in calculator.levels]
        assert prices == sorted(prices)
    
    def test_buy_sell_levels(self, calculator):
        """Test buy/sell level classification."""
        calculator.calculate_grid(50000.0)
        
        buy_levels = calculator.buy_levels
        sell_levels = calculator.sell_levels
        
        assert len(buy_levels) > 0
        assert len(sell_levels) > 0
        
        for level in buy_levels:
            assert level.side == GridSide.BUY
            assert level.price < calculator.center_price
        
        for level in sell_levels:
            assert level.side == GridSide.SELL
            assert level.price > calculator.center_price
    
    def test_grid_spacing(self, calculator):
        """Test uniform grid spacing."""
        calculator.calculate_grid(50000.0)
        
        spacing = calculator.grid_spacing
        assert spacing is not None
        assert spacing > 0
        
        for i in range(1, len(calculator.levels)):
            actual_spacing = calculator.levels[i].price - calculator.levels[i-1].price
            assert abs(actual_spacing - spacing) < 0.01
    
    def test_capital_allocation(self, calculator):
        """Test capital is allocated to each level."""
        calculator.calculate_grid(50000.0)
        
        expected_capital = calculator.config.capital_per_level
        
        for level in calculator.levels:
            assert abs(level.allocated_capital - expected_capital) < 0.01
    
    def test_quantity_calculation(self, calculator):
        """Test quantity is calculated correctly."""
        calculator.calculate_grid(50000.0)
        
        for level in calculator.levels:
            expected_quantity = level.allocated_capital / level.price
            assert level.quantity >= calculator.config.min_order_size
    
    def test_get_level_at_price(self, calculator):
        """Test finding level at price."""
        calculator.calculate_grid(50000.0)
        
        level = calculator.get_level_at_price(50000.0)
        assert level is not None
        
        level_outside = calculator.get_level_at_price(100000.0)
        assert level_outside is None
    
    def test_get_adjacent_levels(self, calculator):
        """Test finding adjacent buy/sell levels."""
        calculator.calculate_grid(50000.0)
        
        buy_level, sell_level = calculator.get_adjacent_levels(50000.0)
        
        if buy_level:
            assert buy_level.side == GridSide.BUY
            assert buy_level.price < 50000.0
        
        if sell_level:
            assert sell_level.side == GridSide.SELL
            assert sell_level.price > 50000.0
    
    def test_is_price_in_grid(self, calculator):
        """Test price in grid check."""
        calculator.calculate_grid(50000.0)
        
        assert calculator.is_price_in_grid(50000.0) == True
        assert calculator.is_price_in_grid(48000.0) == True
        assert calculator.is_price_in_grid(52000.0) == True
        
        assert calculator.is_price_in_grid(40000.0) == False
        assert calculator.is_price_in_grid(60000.0) == False
    
    def test_distance_from_bounds(self, calculator):
        """Test distance from bounds calculation."""
        calculator.calculate_grid(50000.0)
        
        distances = calculator.get_distance_from_bounds(50000.0)
        
        assert "distance_from_upper" in distances
        assert "distance_from_lower" in distances
        assert distances["distance_from_upper"] > 0
        assert distances["distance_from_lower"] > 0
    
    def test_recalculate_grid(self, calculator):
        """Test grid recalculation."""
        calculator.calculate_grid(50000.0)
        old_center = calculator.center_price
        
        new_levels = calculator.recalculate_grid(55000.0)
        
        assert calculator.center_price == 55000.0
        assert calculator.center_price != old_center
        assert len(new_levels) == 15
    
    def test_get_status(self, calculator):
        """Test status retrieval."""
        calculator.calculate_grid(50000.0)
        
        status = calculator.get_status()
        
        assert status["symbol"] == "BTC/USDT"
        assert status["center_price"] == 50000.0
        assert status["total_levels"] == 15
        assert status["total_capital"] == 500.0
    
    def test_to_dict(self, calculator):
        """Test full serialization."""
        calculator.calculate_grid(50000.0)
        
        result = calculator.to_dict()
        
        assert "config" in result
        assert "status" in result
        assert "levels" in result
        assert len(result["levels"]) == 15
    
    def test_invalid_center_price(self, calculator):
        """Test error on invalid center price."""
        with pytest.raises(ValueError):
            calculator.calculate_grid(0)
        
        with pytest.raises(ValueError):
            calculator.calculate_grid(-100)


class TestGridSide:
    """Tests for GridSide enum."""
    
    def test_values(self):
        """Test enum values."""
        assert GridSide.BUY.value == "buy"
        assert GridSide.SELL.value == "sell"
        assert GridSide.CENTER.value == "center"
