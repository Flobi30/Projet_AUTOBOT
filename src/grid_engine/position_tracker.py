"""
Position Tracker Module for AUTOBOT Grid Trading Engine.

Tracks positions, P&L, and performance metrics for grid trading.
Provides real-time updates and historical trade records.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any
import uuid

from .grid_calculator import GridSide

logger = logging.getLogger(__name__)


class TradeType(Enum):
    """Type of trade."""
    GRID_BUY = "grid_buy"
    GRID_SELL = "grid_sell"
    REBALANCE = "rebalance"
    EMERGENCY_CLOSE = "emergency_close"


@dataclass
class TradeRecord:
    """
    Record of a completed trade.
    
    Attributes:
        trade_id: Unique trade identifier
        symbol: Trading pair
        trade_type: Type of trade
        side: Buy or sell
        quantity: Trade quantity
        entry_price: Entry price
        exit_price: Exit price (for completed round trips)
        profit: Profit/loss from trade
        fee: Trading fee
        level_id: Associated grid level
        timestamp: Trade timestamp
    """
    trade_id: str
    symbol: str
    trade_type: TradeType
    side: GridSide
    quantity: float
    price: float
    fee: float = 0.0
    level_id: Optional[int] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    related_trade_id: Optional[str] = None
    profit: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "trade_type": self.trade_type.value,
            "side": self.side.value,
            "quantity": self.quantity,
            "price": self.price,
            "fee": self.fee,
            "level_id": self.level_id,
            "timestamp": self.timestamp.isoformat(),
            "related_trade_id": self.related_trade_id,
            "profit": self.profit,
        }


@dataclass
class GridPosition:
    """
    Represents a position held at a grid level.
    
    Attributes:
        position_id: Unique position identifier
        level_id: Grid level ID
        symbol: Trading pair
        quantity: Position size
        entry_price: Average entry price
        current_price: Current market price
        unrealized_pnl: Unrealized profit/loss
        realized_pnl: Realized profit/loss
        is_open: Whether position is open
    """
    position_id: str
    level_id: int
    symbol: str
    quantity: float
    entry_price: float
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    is_open: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def market_value(self) -> float:
        """Get current market value of position."""
        return self.quantity * self.current_price
    
    @property
    def cost_basis(self) -> float:
        """Get cost basis of position."""
        return self.quantity * self.entry_price
    
    @property
    def total_pnl(self) -> float:
        """Get total P&L (realized + unrealized)."""
        return self.realized_pnl + self.unrealized_pnl
    
    @property
    def pnl_percent(self) -> float:
        """Get P&L as percentage of cost basis."""
        if self.cost_basis == 0:
            return 0.0
        return (self.total_pnl / self.cost_basis) * 100
    
    def update_price(self, current_price: float) -> None:
        """Update current price and recalculate unrealized P&L."""
        self.current_price = current_price
        self.unrealized_pnl = (current_price - self.entry_price) * self.quantity
        self.updated_at = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "position_id": self.position_id,
            "level_id": self.level_id,
            "symbol": self.symbol,
            "quantity": self.quantity,
            "entry_price": self.entry_price,
            "current_price": self.current_price,
            "market_value": self.market_value,
            "cost_basis": self.cost_basis,
            "unrealized_pnl": round(self.unrealized_pnl, 4),
            "realized_pnl": round(self.realized_pnl, 4),
            "total_pnl": round(self.total_pnl, 4),
            "pnl_percent": round(self.pnl_percent, 2),
            "is_open": self.is_open,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class PositionTracker:
    """
    Tracks all positions and performance metrics for grid trading.
    
    Responsibilities:
    - Track open positions at each grid level
    - Calculate real-time P&L
    - Record trade history
    - Provide performance metrics
    
    Example:
        tracker = PositionTracker(symbol="BTC/USDT", initial_capital=500.0)
        
        # Record a buy trade
        tracker.record_trade(
            trade_type=TradeType.GRID_BUY,
            side=GridSide.BUY,
            quantity=0.001,
            price=50000.0,
            level_id=5
        )
        
        # Update prices
        tracker.update_prices(current_price=50500.0)
        
        # Get metrics
        metrics = tracker.get_metrics()
    """
    
    def __init__(
        self,
        symbol: str,
        initial_capital: float,
        target_monthly_return: float = 15.0
    ):
        """
        Initialize position tracker.
        
        Args:
            symbol: Trading pair
            initial_capital: Starting capital
            target_monthly_return: Target monthly return percentage
        """
        self.symbol = symbol
        self.initial_capital = initial_capital
        self.target_monthly_return = target_monthly_return
        
        self._positions: Dict[int, GridPosition] = {}  # level_id -> position
        self._trades: List[TradeRecord] = []
        self._current_price: float = 0.0
        self._start_time: datetime = datetime.utcnow()
        
        self._total_realized_pnl: float = 0.0
        self._total_fees: float = 0.0
        self._winning_trades: int = 0
        self._losing_trades: int = 0
        self._max_drawdown: float = 0.0
        self._peak_equity: float = initial_capital
        
        self._daily_pnl: Dict[str, float] = {}  # date string -> pnl
        
        logger.info(
            f"PositionTracker initialized for {symbol} "
            f"with {initial_capital}€ capital"
        )
    
    @property
    def positions(self) -> Dict[int, GridPosition]:
        """Get all positions."""
        return self._positions
    
    @property
    def open_positions(self) -> List[GridPosition]:
        """Get open positions."""
        return [p for p in self._positions.values() if p.is_open]
    
    @property
    def trades(self) -> List[TradeRecord]:
        """Get all trade records."""
        return self._trades
    
    @property
    def current_price(self) -> float:
        """Get current market price."""
        return self._current_price
    
    @property
    def total_unrealized_pnl(self) -> float:
        """Get total unrealized P&L across all positions."""
        return sum(p.unrealized_pnl for p in self.open_positions)
    
    @property
    def total_realized_pnl(self) -> float:
        """Get total realized P&L."""
        return self._total_realized_pnl
    
    @property
    def total_pnl(self) -> float:
        """Get total P&L (realized + unrealized)."""
        return self._total_realized_pnl + self.total_unrealized_pnl
    
    @property
    def current_equity(self) -> float:
        """Get current equity (initial capital + total P&L)."""
        return self.initial_capital + self.total_pnl
    
    @property
    def return_percent(self) -> float:
        """Get return as percentage of initial capital."""
        return (self.total_pnl / self.initial_capital) * 100
    
    @property
    def win_rate(self) -> float:
        """Get win rate as percentage."""
        total = self._winning_trades + self._losing_trades
        if total == 0:
            return 0.0
        return (self._winning_trades / total) * 100
    
    @property
    def max_drawdown(self) -> float:
        """Get maximum drawdown percentage."""
        return self._max_drawdown
    
    def record_trade(
        self,
        trade_type: TradeType,
        side: GridSide,
        quantity: float,
        price: float,
        fee: float = 0.0,
        level_id: Optional[int] = None,
        related_trade_id: Optional[str] = None
    ) -> TradeRecord:
        """
        Record a trade and update positions.
        
        Args:
            trade_type: Type of trade
            side: Buy or sell
            quantity: Trade quantity
            price: Trade price
            fee: Trading fee
            level_id: Associated grid level
            related_trade_id: ID of related trade (for round trips)
            
        Returns:
            Created TradeRecord
        """
        trade = TradeRecord(
            trade_id=str(uuid.uuid4()),
            symbol=self.symbol,
            trade_type=trade_type,
            side=side,
            quantity=quantity,
            price=price,
            fee=fee,
            level_id=level_id,
            related_trade_id=related_trade_id,
        )
        
        self._total_fees += fee
        
        if side == GridSide.BUY:
            self._open_position(trade)
        elif side == GridSide.SELL:
            profit = self._close_position(trade)
            trade.profit = profit
            
            if profit > 0:
                self._winning_trades += 1
            elif profit < 0:
                self._losing_trades += 1
        
        self._trades.append(trade)
        self._update_daily_pnl(trade)
        self._update_drawdown()
        
        logger.info(
            f"Recorded trade: {side.value} {quantity} @ {price}, "
            f"fee={fee}, profit={trade.profit:.4f}"
        )
        
        return trade
    
    def _open_position(self, trade: TradeRecord) -> None:
        """Open or add to a position."""
        level_id = trade.level_id or 0
        
        if level_id in self._positions:
            position = self._positions[level_id]
            total_cost = (position.quantity * position.entry_price) + (trade.quantity * trade.price)
            total_quantity = position.quantity + trade.quantity
            position.entry_price = total_cost / total_quantity
            position.quantity = total_quantity
            position.updated_at = datetime.utcnow()
        else:
            position = GridPosition(
                position_id=str(uuid.uuid4()),
                level_id=level_id,
                symbol=self.symbol,
                quantity=trade.quantity,
                entry_price=trade.price,
                current_price=trade.price,
            )
            self._positions[level_id] = position
    
    def _close_position(self, trade: TradeRecord) -> float:
        """Close or reduce a position and calculate profit."""
        level_id = trade.level_id or 0
        
        if level_id not in self._positions:
            logger.warning(f"No position found for level {level_id}")
            return 0.0
        
        position = self._positions[level_id]
        
        sell_quantity = min(trade.quantity, position.quantity)
        profit = (trade.price - position.entry_price) * sell_quantity - trade.fee
        
        position.realized_pnl += profit
        self._total_realized_pnl += profit
        
        position.quantity -= sell_quantity
        
        if position.quantity <= 0.00000001:  # Effectively zero
            position.is_open = False
            position.quantity = 0
        
        position.updated_at = datetime.utcnow()
        
        return profit
    
    def _update_daily_pnl(self, trade: TradeRecord) -> None:
        """Update daily P&L tracking."""
        date_key = trade.timestamp.strftime("%Y-%m-%d")
        
        if date_key not in self._daily_pnl:
            self._daily_pnl[date_key] = 0.0
        
        self._daily_pnl[date_key] += trade.profit - trade.fee
    
    def _update_drawdown(self) -> None:
        """Update maximum drawdown calculation."""
        current_equity = self.current_equity
        
        if current_equity > self._peak_equity:
            self._peak_equity = current_equity
        
        if self._peak_equity > 0:
            drawdown = ((self._peak_equity - current_equity) / self._peak_equity) * 100
            if drawdown > self._max_drawdown:
                self._max_drawdown = drawdown
    
    def update_prices(self, current_price: float) -> None:
        """
        Update current price and recalculate unrealized P&L.
        
        Args:
            current_price: Current market price
        """
        self._current_price = current_price
        
        for position in self.open_positions:
            position.update_price(current_price)
        
        self._update_drawdown()
    
    def get_position_at_level(self, level_id: int) -> Optional[GridPosition]:
        """Get position at a specific grid level."""
        return self._positions.get(level_id)
    
    def get_today_pnl(self) -> float:
        """Get today's P&L."""
        today_key = datetime.utcnow().strftime("%Y-%m-%d")
        return self._daily_pnl.get(today_key, 0.0)
    
    def get_daily_pnl_history(self, days: int = 30) -> Dict[str, float]:
        """Get daily P&L history for the last N days."""
        cutoff = datetime.utcnow() - timedelta(days=days)
        cutoff_key = cutoff.strftime("%Y-%m-%d")
        
        return {
            date: pnl
            for date, pnl in sorted(self._daily_pnl.items())
            if date >= cutoff_key
        }
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Get comprehensive performance metrics.
        
        Returns:
            Dictionary with all metrics
        """
        total_trades = len(self._trades)
        buy_trades = len([t for t in self._trades if t.side == GridSide.BUY])
        sell_trades = len([t for t in self._trades if t.side == GridSide.SELL])
        
        running_days = (datetime.utcnow() - self._start_time).days or 1
        daily_return = self.return_percent / running_days
        projected_monthly = daily_return * 30
        
        avg_profit_per_trade = 0.0
        if self._winning_trades + self._losing_trades > 0:
            avg_profit_per_trade = self._total_realized_pnl / (self._winning_trades + self._losing_trades)
        
        return {
            "symbol": self.symbol,
            "initial_capital": self.initial_capital,
            "current_equity": round(self.current_equity, 2),
            "total_pnl": round(self.total_pnl, 2),
            "realized_pnl": round(self._total_realized_pnl, 2),
            "unrealized_pnl": round(self.total_unrealized_pnl, 2),
            "total_fees": round(self._total_fees, 4),
            "net_pnl": round(self.total_pnl - self._total_fees, 2),
            "return_percent": round(self.return_percent, 2),
            "daily_return_percent": round(daily_return, 2),
            "projected_monthly_return": round(projected_monthly, 2),
            "target_monthly_return": self.target_monthly_return,
            "on_track": projected_monthly >= self.target_monthly_return,
            "total_trades": total_trades,
            "buy_trades": buy_trades,
            "sell_trades": sell_trades,
            "winning_trades": self._winning_trades,
            "losing_trades": self._losing_trades,
            "win_rate": round(self.win_rate, 1),
            "avg_profit_per_trade": round(avg_profit_per_trade, 4),
            "max_drawdown": round(self._max_drawdown, 2),
            "open_positions": len(self.open_positions),
            "today_pnl": round(self.get_today_pnl(), 2),
            "running_days": running_days,
            "start_time": self._start_time.isoformat(),
        }
    
    def get_position_summary(self) -> Dict[str, Any]:
        """Get summary of all positions."""
        total_quantity = sum(p.quantity for p in self.open_positions)
        total_cost = sum(p.cost_basis for p in self.open_positions)
        total_value = sum(p.market_value for p in self.open_positions)
        
        return {
            "open_positions": len(self.open_positions),
            "total_quantity": round(total_quantity, 8),
            "total_cost_basis": round(total_cost, 2),
            "total_market_value": round(total_value, 2),
            "total_unrealized_pnl": round(self.total_unrealized_pnl, 2),
            "positions": [p.to_dict() for p in self.open_positions],
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert tracker state to dictionary."""
        return {
            "metrics": self.get_metrics(),
            "position_summary": self.get_position_summary(),
            "recent_trades": [t.to_dict() for t in self._trades[-50:]],
            "daily_pnl": self.get_daily_pnl_history(30),
        }
