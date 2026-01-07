"""
Base Engine Interface for AUTOBOT Backtest System

All backtest engines must implement this interface.
"""

import pandas as pd
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass
from enum import Enum


class OrderType(Enum):
    """Order types supported by engines"""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    OCO = "oco"  # One-Cancels-Other


@dataclass
class EngineCapabilities:
    """Capabilities of a backtest engine"""
    name: str
    supports_tick_data: bool = False
    supports_l2_data: bool = False
    supports_partial_fills: bool = False
    supports_market_impact: bool = False
    supports_latency_simulation: bool = False
    min_timeframe: str = "1h"
    max_timeframe: str = "1M"
    supported_order_types: List[OrderType] = None
    vectorized: bool = False
    multi_asset: bool = False
    
    def __post_init__(self):
        if self.supported_order_types is None:
            self.supported_order_types = [OrderType.MARKET]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "supports_tick_data": self.supports_tick_data,
            "supports_l2_data": self.supports_l2_data,
            "supports_partial_fills": self.supports_partial_fills,
            "supports_market_impact": self.supports_market_impact,
            "supports_latency_simulation": self.supports_latency_simulation,
            "min_timeframe": self.min_timeframe,
            "max_timeframe": self.max_timeframe,
            "supported_order_types": [ot.value for ot in self.supported_order_types],
            "vectorized": self.vectorized,
            "multi_asset": self.multi_asset,
        }


@dataclass
class TradeRecord:
    """Record of a single trade"""
    entry_time: Any
    exit_time: Any
    entry_price: float
    exit_price: float
    size: float
    side: str  # 'long' or 'short'
    pnl: float
    pnl_pct: float
    commission: float = 0.0
    slippage: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_time": str(self.entry_time),
            "exit_time": str(self.exit_time),
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "size": self.size,
            "side": self.side,
            "pnl": self.pnl,
            "pnl_pct": self.pnl_pct,
            "commission": self.commission,
            "slippage": self.slippage,
        }


@dataclass
class BacktestMetrics:
    """Metrics from a backtest run"""
    final_equity: float
    total_pnl: float
    total_return_pct: float
    max_drawdown: float
    max_drawdown_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    win_rate: float
    profit_factor: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_trade_pnl: float
    avg_win: float
    avg_loss: float
    max_consecutive_wins: int
    max_consecutive_losses: int
    avg_trade_duration: float  # in periods
    exposure_time_pct: float  # % of time in market
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "final_equity": self.final_equity,
            "total_pnl": self.total_pnl,
            "total_return_pct": self.total_return_pct,
            "max_drawdown": self.max_drawdown,
            "max_drawdown_pct": self.max_drawdown_pct,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "calmar_ratio": self.calmar_ratio,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "avg_trade_pnl": self.avg_trade_pnl,
            "avg_win": self.avg_win,
            "avg_loss": self.avg_loss,
            "max_consecutive_wins": self.max_consecutive_wins,
            "max_consecutive_losses": self.max_consecutive_losses,
            "avg_trade_duration": self.avg_trade_duration,
            "exposure_time_pct": self.exposure_time_pct,
        }


class BaseEngine(ABC):
    """
    Abstract base class for all backtest engines.
    
    All engines must implement:
    - run(): Execute the backtest
    - get_capabilities(): Return engine capabilities
    """
    
    @abstractmethod
    def run(
        self,
        data: pd.DataFrame,
        strategy_fn: Callable[[pd.DataFrame], pd.Series],
        initial_capital: float = 500.0,
        commission: float = 0.001,
        slippage: float = 0.0005,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Run a backtest with the given data and strategy.
        
        Args:
            data: OHLCV DataFrame with columns: open, high, low, close, volume
            strategy_fn: Function that takes data and returns signal series (-1, 0, 1)
            initial_capital: Starting capital
            commission: Commission per trade as fraction
            slippage: Slippage per trade as fraction
            **kwargs: Engine-specific parameters
            
        Returns:
            Dict containing:
                - metrics: BacktestMetrics
                - trades: List[TradeRecord]
                - equity_curve: pd.Series
                - signals: pd.Series
        """
        pass
    
    @classmethod
    @abstractmethod
    def get_capabilities(cls) -> EngineCapabilities:
        """Return the capabilities of this engine."""
        pass
    
    @classmethod
    def is_available(cls) -> bool:
        """Check if this engine is available (dependencies installed)."""
        return True
    
    @staticmethod
    def validate_data(data: pd.DataFrame) -> None:
        """Validate input data format."""
        required_columns = ['close']
        optional_columns = ['open', 'high', 'low', 'volume']
        
        if data is None or len(data) == 0:
            raise ValueError("Data is empty")
        
        for col in required_columns:
            if col not in data.columns:
                raise ValueError(f"Missing required column: {col}")
    
    @staticmethod
    def calculate_metrics(
        equity_curve: pd.Series,
        trades: List[TradeRecord],
        initial_capital: float,
    ) -> BacktestMetrics:
        """Calculate standard backtest metrics from equity curve and trades."""
        import numpy as np
        
        final_equity = equity_curve.iloc[-1]
        total_pnl = final_equity - initial_capital
        total_return_pct = (total_pnl / initial_capital) * 100
        
        # Drawdown
        cum_max = equity_curve.cummax()
        drawdown = cum_max - equity_curve
        drawdown_pct = (drawdown / cum_max) * 100
        max_drawdown = drawdown.max()
        max_drawdown_pct = drawdown_pct.max()
        
        # Returns
        returns = equity_curve.pct_change().dropna()
        returns_std = returns.std()
        returns_mean = returns.mean()
        
        # Sharpe ratio (annualized)
        sharpe_ratio = (returns_mean / returns_std) * np.sqrt(252) if returns_std != 0 else 0.0
        
        # Sortino ratio
        negative_returns = returns[returns < 0]
        downside_std = negative_returns.std() if len(negative_returns) > 0 else 0
        sortino_ratio = (returns_mean / downside_std) * np.sqrt(252) if downside_std != 0 else 0.0
        
        # Calmar ratio
        calmar_ratio = (total_return_pct / max_drawdown_pct) if max_drawdown_pct != 0 else 0.0
        
        # Trade statistics
        total_trades = len(trades)
        winning_trades = len([t for t in trades if t.pnl > 0])
        losing_trades = len([t for t in trades if t.pnl < 0])
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0
        
        wins = [t.pnl for t in trades if t.pnl > 0]
        losses = [t.pnl for t in trades if t.pnl < 0]
        
        gross_profit = sum(wins) if wins else 0
        gross_loss = abs(sum(losses)) if losses else 0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float('inf') if gross_profit > 0 else 0.0
        
        avg_trade_pnl = (total_pnl / total_trades) if total_trades > 0 else 0.0
        avg_win = (sum(wins) / len(wins)) if wins else 0.0
        avg_loss = (sum(losses) / len(losses)) if losses else 0.0
        
        # Consecutive wins/losses
        max_consecutive_wins = 0
        max_consecutive_losses = 0
        current_wins = 0
        current_losses = 0
        
        for trade in trades:
            if trade.pnl > 0:
                current_wins += 1
                current_losses = 0
                max_consecutive_wins = max(max_consecutive_wins, current_wins)
            else:
                current_losses += 1
                current_wins = 0
                max_consecutive_losses = max(max_consecutive_losses, current_losses)
        
        # Average trade duration (simplified)
        avg_trade_duration = 0.0  # Would need timestamp parsing
        
        # Exposure time
        exposure_time_pct = 0.0  # Would need signal analysis
        
        return BacktestMetrics(
            final_equity=final_equity,
            total_pnl=total_pnl,
            total_return_pct=total_return_pct,
            max_drawdown=max_drawdown,
            max_drawdown_pct=max_drawdown_pct,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            calmar_ratio=calmar_ratio,
            win_rate=win_rate,
            profit_factor=profit_factor,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            avg_trade_pnl=avg_trade_pnl,
            avg_win=avg_win,
            avg_loss=avg_loss,
            max_consecutive_wins=max_consecutive_wins,
            max_consecutive_losses=max_consecutive_losses,
            avg_trade_duration=avg_trade_duration,
            exposure_time_pct=exposure_time_pct,
        )
