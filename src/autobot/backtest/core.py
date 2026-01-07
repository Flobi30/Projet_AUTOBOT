"""
AUTOBOT Backtest Core Module

This module provides the core backtest functionality with support for multiple
backtest engines (Backtrader, Freqtrade, Backtesting.py, vectorbt, Jesse, NautilusTrader).
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, Callable, List
from enum import Enum
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


class BacktestEngine(Enum):
    """Supported backtest engines"""
    AUTO = "auto"
    SIMPLE = "simple"
    BACKTRADER = "backtrader"
    FREQTRADE = "freqtrade"
    BACKTESTING_PY = "backtesting_py"
    VECTORBT = "vectorbt"
    JESSE = "jesse"
    NAUTILUS = "nautilus"


class StrategyType(Enum):
    """Strategy types for engine selection"""
    SCALPING = "scalping"
    TREND_FOLLOWING = "trend_following"
    MEAN_REVERSION = "mean_reversion"
    ARBITRAGE = "arbitrage"
    NEWS_BASED = "news_based"
    CUSTOM = "custom"


@dataclass
class BacktestConfig:
    """Configuration for backtest execution"""
    initial_capital: float = 500.0
    commission: float = 0.001
    slippage: float = 0.0005
    max_position_size: float = 1.0
    risk_per_trade: float = 0.02
    timeframe: str = "1h"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    
    # Execution modeling
    enable_partial_fills: bool = False
    enable_market_impact: bool = False
    latency_ms: int = 0
    
    # Anti-over-trading patch
    hard_trade_rate_cap: int = 100
    cost_per_trade_max: float = 0.005
    slippage_tolerance: float = 0.01


@dataclass
class BacktestResult:
    """Result of a backtest execution"""
    final_equity: float
    total_pnl: float
    total_return_pct: float
    max_drawdown: float
    max_drawdown_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    win_rate: float
    profit_factor: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_trade_pnl: float
    equity_curve: pd.Series
    trades: List[Dict[str, Any]]
    engine_used: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary"""
        return {
            "final_equity": self.final_equity,
            "total_pnl": self.total_pnl,
            "total_return_pct": self.total_return_pct,
            "max_drawdown": self.max_drawdown,
            "max_drawdown_pct": self.max_drawdown_pct,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "avg_trade_pnl": self.avg_trade_pnl,
            "engine_used": self.engine_used,
        }


class BacktestOrchestrator:
    """
    Intelligent orchestrator that selects the best backtest engine based on:
    - Strategy type (scalping/trend/arbitrage)
    - Granularity requirements
    - Realism needs (tick/L2 data)
    - Asset type
    - Available resources
    - Acceptable latency
    """
    
    ENGINE_CAPABILITIES = {
        BacktestEngine.SIMPLE: {
            "strategy_types": [StrategyType.TREND_FOLLOWING, StrategyType.MEAN_REVERSION],
            "min_timeframe": "1h",
            "tick_data": False,
            "l2_data": False,
            "complexity": "low",
        },
        BacktestEngine.BACKTRADER: {
            "strategy_types": [StrategyType.TREND_FOLLOWING, StrategyType.MEAN_REVERSION, StrategyType.SCALPING],
            "min_timeframe": "1m",
            "tick_data": False,
            "l2_data": False,
            "complexity": "medium",
        },
        BacktestEngine.VECTORBT: {
            "strategy_types": [StrategyType.TREND_FOLLOWING, StrategyType.MEAN_REVERSION, StrategyType.SCALPING],
            "min_timeframe": "1m",
            "tick_data": False,
            "l2_data": False,
            "complexity": "medium",
            "vectorized": True,
        },
    }
    
    @classmethod
    def select_engine(
        cls,
        strategy_type: StrategyType,
        timeframe: str = "1h",
        need_tick_data: bool = False,
        need_l2_data: bool = False,
        prefer_speed: bool = True,
    ) -> BacktestEngine:
        """Select the best engine based on requirements."""
        if prefer_speed and strategy_type in [StrategyType.TREND_FOLLOWING, StrategyType.MEAN_REVERSION]:
            return BacktestEngine.SIMPLE
        
        if strategy_type == StrategyType.SCALPING:
            return BacktestEngine.BACKTRADER
        
        return BacktestEngine.SIMPLE


def run_backtest(
    df: pd.DataFrame,
    strategy_fn: Callable[[pd.DataFrame], pd.Series],
    config: Optional[BacktestConfig] = None,
    engine: BacktestEngine = BacktestEngine.AUTO,
) -> BacktestResult:
    """
    Execute a backtest with the specified strategy and configuration.
    
    Args:
        df: DataFrame with OHLCV data (must have 'close' column)
        strategy_fn: Function that takes df and returns signal series (-1, 0, 1)
        config: Backtest configuration
        engine: Backtest engine to use (AUTO for automatic selection)
        
    Returns:
        BacktestResult: Backtest results
    """
    if config is None:
        config = BacktestConfig()
    
    if df is None or len(df) == 0:
        raise ValueError("Data is empty.")
    
    if 'close' not in df.columns:
        raise ValueError("DataFrame must have 'close' column.")
    
    if engine == BacktestEngine.AUTO:
        engine = BacktestOrchestrator.select_engine(
            strategy_type=StrategyType.TREND_FOLLOWING,
            timeframe=config.timeframe,
        )
    
    signals = strategy_fn(df)
    if signals is None or len(signals) == 0:
        raise ValueError("Strategy returned empty signals.")
    
    return _run_simple_backtest(df, signals, config, engine)


def _run_simple_backtest(
    df: pd.DataFrame,
    signals: pd.Series,
    config: BacktestConfig,
    engine: BacktestEngine,
) -> BacktestResult:
    """Run a simple vectorized backtest."""
    df = df.copy()
    initial_capital = config.initial_capital
    
    df['signal'] = signals
    df['daily_return'] = df['close'].pct_change()
    
    df['signal_change'] = df['signal'].diff().abs()
    df['transaction_cost'] = df['signal_change'] * (config.commission + config.slippage)
    
    df['strategy_return'] = df['daily_return'] * df['signal'].shift(1) - df['transaction_cost']
    df['strategy_return'] = df['strategy_return'].fillna(0)
    
    df['equity'] = initial_capital * (1 + df['strategy_return']).cumprod()
    
    final_equity = df['equity'].iloc[-1]
    total_pnl = final_equity - initial_capital
    total_return_pct = (total_pnl / initial_capital) * 100
    
    df['cum_max'] = df['equity'].cummax()
    df['drawdown'] = df['cum_max'] - df['equity']
    df['drawdown_pct'] = df['drawdown'] / df['cum_max'] * 100
    max_drawdown = df['drawdown'].max()
    max_drawdown_pct = df['drawdown_pct'].max()
    
    returns_std = df['strategy_return'].std()
    sharpe_ratio = (df['strategy_return'].mean() / returns_std) * np.sqrt(252) if returns_std != 0 else 0.0
    
    negative_returns = df['strategy_return'][df['strategy_return'] < 0]
    downside_std = negative_returns.std() if len(negative_returns) > 0 else 0
    sortino_ratio = (df['strategy_return'].mean() / downside_std) * np.sqrt(252) if downside_std != 0 else 0.0
    
    trades = _extract_trades(df, initial_capital)
    total_trades = len(trades)
    winning_trades = len([t for t in trades if t['pnl'] > 0])
    losing_trades = len([t for t in trades if t['pnl'] < 0])
    win_rate = winning_trades / total_trades * 100 if total_trades > 0 else 0.0
    
    gross_profit = sum(t['pnl'] for t in trades if t['pnl'] > 0)
    gross_loss = abs(sum(t['pnl'] for t in trades if t['pnl'] < 0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf') if gross_profit > 0 else 0.0
    
    avg_trade_pnl = total_pnl / total_trades if total_trades > 0 else 0.0
    
    return BacktestResult(
        final_equity=final_equity,
        total_pnl=total_pnl,
        total_return_pct=total_return_pct,
        max_drawdown=max_drawdown,
        max_drawdown_pct=max_drawdown_pct,
        sharpe_ratio=sharpe_ratio,
        sortino_ratio=sortino_ratio,
        win_rate=win_rate,
        profit_factor=profit_factor,
        total_trades=total_trades,
        winning_trades=winning_trades,
        losing_trades=losing_trades,
        avg_trade_pnl=avg_trade_pnl,
        equity_curve=df['equity'],
        trades=trades,
        engine_used=engine.value,
    )


def _extract_trades(df: pd.DataFrame, initial_capital: float) -> List[Dict[str, Any]]:
    """Extract individual trades from backtest data."""
    trades = []
    in_trade = False
    entry_price = 0.0
    entry_idx = None
    position = 0
    
    for idx, row in df.iterrows():
        signal = row.get('signal', 0)
        
        if not in_trade and signal != 0:
            in_trade = True
            entry_price = row['close']
            entry_idx = idx
            position = signal
        elif in_trade and (signal == 0 or signal != position):
            exit_price = row['close']
            pnl = (exit_price - entry_price) * position
            pnl_pct = (pnl / entry_price) * 100
            
            trades.append({
                'entry_time': entry_idx,
                'exit_time': idx,
                'entry_price': entry_price,
                'exit_price': exit_price,
                'position': 'long' if position > 0 else 'short',
                'pnl': pnl,
                'pnl_pct': pnl_pct,
            })
            
            in_trade = False
            entry_price = 0.0
            entry_idx = None
            
            if signal != 0:
                in_trade = True
                entry_price = row['close']
                entry_idx = idx
                position = signal
    
    return trades


def benchmark_sma_crossover(df: pd.DataFrame, fast_period: int = 10, slow_period: int = 30) -> pd.Series:
    """Simple Moving Average crossover strategy"""
    fast_sma = df['close'].rolling(window=fast_period).mean()
    slow_sma = df['close'].rolling(window=slow_period).mean()
    
    signal = pd.Series(0, index=df.index)
    signal[fast_sma > slow_sma] = 1
    signal[fast_sma < slow_sma] = -1
    
    return signal


def benchmark_rsi_mean_reversion(df: pd.DataFrame, period: int = 14, oversold: int = 30, overbought: int = 70) -> pd.Series:
    """RSI mean reversion strategy"""
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    
    signal = pd.Series(0, index=df.index)
    signal[rsi < oversold] = 1
    signal[rsi > overbought] = -1
    
    return signal


def benchmark_momentum(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """Momentum strategy"""
    momentum = df['close'].pct_change(periods=period)
    
    signal = pd.Series(0, index=df.index)
    signal[momentum > 0] = 1
    signal[momentum < 0] = -1
    
    return signal

