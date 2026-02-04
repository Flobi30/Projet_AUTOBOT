"""
Tests for Position Tracker Module.
"""

import pytest
from datetime import datetime, timedelta

import sys
sys.path.insert(0, '/home/ubuntu/repos/Projet_AUTOBOT/src')

from grid_engine.grid_calculator import GridSide
from grid_engine.position_tracker import (
    PositionTracker,
    GridPosition,
    TradeRecord,
    TradeType,
)


class TestTradeType:
    """Tests for TradeType enum."""
    
    def test_values(self):
        """Test enum values."""
        assert TradeType.GRID_BUY.value == "grid_buy"
        assert TradeType.GRID_SELL.value == "grid_sell"
        assert TradeType.REBALANCE.value == "rebalance"
        assert TradeType.EMERGENCY_CLOSE.value == "emergency_close"


class TestTradeRecord:
    """Tests for TradeRecord dataclass."""
    
    def test_trade_creation(self):
        """Test trade record creation."""
        trade = TradeRecord(
            trade_id="trade-001",
            trade_type=TradeType.GRID_BUY,
            side=GridSide.BUY,
            symbol="BTC/USDT",
            quantity=0.001,
            price=50000.0,
            level_id=5,
        )
        
        assert trade.trade_id == "trade-001"
        assert trade.trade_type == TradeType.GRID_BUY
        assert trade.side == GridSide.BUY
        assert trade.quantity == 0.001
        assert trade.price == 50000.0
    
    def test_trade_value(self):
        """Test trade value calculation."""
        trade = TradeRecord(
            trade_id="trade-001",
            trade_type=TradeType.GRID_BUY,
            side=GridSide.BUY,
            symbol="BTC/USDT",
            quantity=0.001,
            price=50000.0,
            level_id=5,
        )
        
        assert trade.value == 50.0
    
    def test_trade_with_fee(self):
        """Test trade with fee."""
        trade = TradeRecord(
            trade_id="trade-001",
            trade_type=TradeType.GRID_BUY,
            side=GridSide.BUY,
            symbol="BTC/USDT",
            quantity=0.001,
            price=50000.0,
            level_id=5,
            fee=0.05,
        )
        
        assert trade.fee == 0.05
    
    def test_to_dict(self):
        """Test trade serialization."""
        trade = TradeRecord(
            trade_id="trade-001",
            trade_type=TradeType.GRID_BUY,
            side=GridSide.BUY,
            symbol="BTC/USDT",
            quantity=0.001,
            price=50000.0,
            level_id=5,
        )
        
        result = trade.to_dict()
        
        assert result["trade_id"] == "trade-001"
        assert result["trade_type"] == "grid_buy"
        assert result["side"] == "buy"


class TestGridPosition:
    """Tests for GridPosition dataclass."""
    
    def test_position_creation(self):
        """Test position creation."""
        position = GridPosition(
            position_id="pos-001",
            level_id=5,
            symbol="BTC/USDT",
            quantity=0.001,
            entry_price=50000.0,
        )
        
        assert position.position_id == "pos-001"
        assert position.level_id == 5
        assert position.quantity == 0.001
        assert position.entry_price == 50000.0
        assert position.current_price == 50000.0
    
    def test_market_value(self):
        """Test market value calculation."""
        position = GridPosition(
            position_id="pos-001",
            level_id=5,
            symbol="BTC/USDT",
            quantity=0.001,
            entry_price=50000.0,
            current_price=51000.0,
        )
        
        assert position.market_value == 51.0
    
    def test_cost_basis(self):
        """Test cost basis calculation."""
        position = GridPosition(
            position_id="pos-001",
            level_id=5,
            symbol="BTC/USDT",
            quantity=0.001,
            entry_price=50000.0,
        )
        
        assert position.cost_basis == 50.0
    
    def test_unrealized_pnl(self):
        """Test unrealized P&L calculation."""
        position = GridPosition(
            position_id="pos-001",
            level_id=5,
            symbol="BTC/USDT",
            quantity=0.001,
            entry_price=50000.0,
            current_price=51000.0,
        )
        
        assert position.unrealized_pnl == 1.0
        
        position.current_price = 49000.0
        assert position.unrealized_pnl == -1.0
    
    def test_pnl_percent(self):
        """Test P&L percentage calculation."""
        position = GridPosition(
            position_id="pos-001",
            level_id=5,
            symbol="BTC/USDT",
            quantity=0.001,
            entry_price=50000.0,
            current_price=51000.0,
        )
        
        assert position.pnl_percent == 2.0
    
    def test_to_dict(self):
        """Test position serialization."""
        position = GridPosition(
            position_id="pos-001",
            level_id=5,
            symbol="BTC/USDT",
            quantity=0.001,
            entry_price=50000.0,
        )
        
        result = position.to_dict()
        
        assert result["position_id"] == "pos-001"
        assert result["level_id"] == 5
        assert "unrealized_pnl" in result


class TestPositionTracker:
    """Tests for PositionTracker class."""
    
    @pytest.fixture
    def tracker(self):
        """Create test position tracker."""
        return PositionTracker(
            symbol="BTC/USDT",
            initial_capital=500.0
        )
    
    def test_initialization(self, tracker):
        """Test tracker initialization."""
        assert tracker.symbol == "BTC/USDT"
        assert tracker.initial_capital == 500.0
        assert tracker.current_price == 0.0
        assert tracker.total_pnl == 0.0
    
    def test_record_buy_trade(self, tracker):
        """Test recording a buy trade."""
        trade = tracker.record_trade(
            trade_type=TradeType.GRID_BUY,
            side=GridSide.BUY,
            quantity=0.001,
            price=50000.0,
            level_id=5,
        )
        
        assert trade is not None
        assert trade.trade_type == TradeType.GRID_BUY
        assert len(tracker.trades) == 1
        assert len(tracker.open_positions) == 1
    
    def test_record_sell_trade(self, tracker):
        """Test recording a sell trade that closes position."""
        tracker.record_trade(
            trade_type=TradeType.GRID_BUY,
            side=GridSide.BUY,
            quantity=0.001,
            price=50000.0,
            level_id=5,
        )
        
        sell_trade = tracker.record_trade(
            trade_type=TradeType.GRID_SELL,
            side=GridSide.SELL,
            quantity=0.001,
            price=50400.0,
            level_id=5,
        )
        
        assert sell_trade is not None
        assert sell_trade.profit > 0
        assert len(tracker.open_positions) == 0
    
    def test_update_prices(self, tracker):
        """Test price update."""
        tracker.record_trade(
            trade_type=TradeType.GRID_BUY,
            side=GridSide.BUY,
            quantity=0.001,
            price=50000.0,
            level_id=5,
        )
        
        tracker.update_prices(51000.0)
        
        assert tracker.current_price == 51000.0
        assert tracker.open_positions[0].current_price == 51000.0
    
    def test_total_pnl(self, tracker):
        """Test total P&L calculation."""
        tracker.record_trade(
            trade_type=TradeType.GRID_BUY,
            side=GridSide.BUY,
            quantity=0.001,
            price=50000.0,
            level_id=5,
        )
        
        tracker.record_trade(
            trade_type=TradeType.GRID_SELL,
            side=GridSide.SELL,
            quantity=0.001,
            price=50400.0,
            level_id=5,
        )
        
        assert tracker.realized_pnl > 0
    
    def test_unrealized_pnl(self, tracker):
        """Test unrealized P&L calculation."""
        tracker.record_trade(
            trade_type=TradeType.GRID_BUY,
            side=GridSide.BUY,
            quantity=0.001,
            price=50000.0,
            level_id=5,
        )
        
        tracker.update_prices(51000.0)
        
        assert tracker.unrealized_pnl == 1.0
    
    def test_win_rate(self, tracker):
        """Test win rate calculation."""
        tracker.record_trade(
            trade_type=TradeType.GRID_BUY,
            side=GridSide.BUY,
            quantity=0.001,
            price=50000.0,
            level_id=5,
        )
        tracker.record_trade(
            trade_type=TradeType.GRID_SELL,
            side=GridSide.SELL,
            quantity=0.001,
            price=50400.0,
            level_id=5,
        )
        
        tracker.record_trade(
            trade_type=TradeType.GRID_BUY,
            side=GridSide.BUY,
            quantity=0.001,
            price=50000.0,
            level_id=6,
        )
        tracker.record_trade(
            trade_type=TradeType.GRID_SELL,
            side=GridSide.SELL,
            quantity=0.001,
            price=49800.0,
            level_id=6,
        )
        
        assert tracker.win_rate == 50.0
    
    def test_max_drawdown(self, tracker):
        """Test max drawdown tracking."""
        tracker.record_trade(
            trade_type=TradeType.GRID_BUY,
            side=GridSide.BUY,
            quantity=0.001,
            price=50000.0,
            level_id=5,
        )
        
        tracker.update_prices(51000.0)
        tracker.update_prices(49000.0)
        
        assert tracker.max_drawdown > 0
    
    def test_get_metrics(self, tracker):
        """Test metrics retrieval."""
        tracker.record_trade(
            trade_type=TradeType.GRID_BUY,
            side=GridSide.BUY,
            quantity=0.001,
            price=50000.0,
            level_id=5,
        )
        
        metrics = tracker.get_metrics()
        
        assert "symbol" in metrics
        assert "initial_capital" in metrics
        assert "total_pnl" in metrics
        assert "return_percent" in metrics
        assert "win_rate" in metrics
        assert "total_trades" in metrics
    
    def test_get_position_summary(self, tracker):
        """Test position summary."""
        tracker.record_trade(
            trade_type=TradeType.GRID_BUY,
            side=GridSide.BUY,
            quantity=0.001,
            price=50000.0,
            level_id=5,
        )
        
        summary = tracker.get_position_summary()
        
        assert "open_positions" in summary
        assert "total_positions" in summary
        assert "total_market_value" in summary
    
    def test_get_today_pnl(self, tracker):
        """Test today's P&L calculation."""
        tracker.record_trade(
            trade_type=TradeType.GRID_BUY,
            side=GridSide.BUY,
            quantity=0.001,
            price=50000.0,
            level_id=5,
        )
        tracker.record_trade(
            trade_type=TradeType.GRID_SELL,
            side=GridSide.SELL,
            quantity=0.001,
            price=50400.0,
            level_id=5,
        )
        
        today_pnl = tracker.get_today_pnl()
        
        assert today_pnl > 0
    
    def test_callback_registration(self, tracker):
        """Test callback registration."""
        callback_called = []
        
        def on_trade(trade):
            callback_called.append(trade)
        
        tracker.on_trade(on_trade)
        
        tracker.record_trade(
            trade_type=TradeType.GRID_BUY,
            side=GridSide.BUY,
            quantity=0.001,
            price=50000.0,
            level_id=5,
        )
        
        assert len(callback_called) == 1
    
    def test_to_dict(self, tracker):
        """Test full serialization."""
        tracker.record_trade(
            trade_type=TradeType.GRID_BUY,
            side=GridSide.BUY,
            quantity=0.001,
            price=50000.0,
            level_id=5,
        )
        
        result = tracker.to_dict()
        
        assert "metrics" in result
        assert "positions" in result
        assert "trades" in result
