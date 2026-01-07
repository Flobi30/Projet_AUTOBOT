"""
Simple Vectorized Backtest Engine

A fast, built-in backtest engine that uses vectorized operations.
Always available as it has no external dependencies.
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Callable, List

from autobot.backtest.engines.base import (
    BaseEngine,
    EngineCapabilities,
    OrderType,
    TradeRecord,
    BacktestMetrics,
)


class SimpleEngine(BaseEngine):
    """
    Simple vectorized backtest engine.
    
    Features:
    - Fast vectorized calculations using pandas/numpy
    - Basic commission and slippage modeling
    - Long and short positions
    - No external dependencies
    
    Limitations:
    - No tick-level simulation
    - No partial fills
    - No market impact modeling
    - Single asset only
    """
    
    @classmethod
    def get_capabilities(cls) -> EngineCapabilities:
        return EngineCapabilities(
            name="simple",
            supports_tick_data=False,
            supports_l2_data=False,
            supports_partial_fills=False,
            supports_market_impact=False,
            supports_latency_simulation=False,
            min_timeframe="1m",
            max_timeframe="1M",
            supported_order_types=[OrderType.MARKET],
            vectorized=True,
            multi_asset=False,
        )
    
    @classmethod
    def is_available(cls) -> bool:
        return True  # Always available
    
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
        Run a vectorized backtest.
        
        Args:
            data: OHLCV DataFrame
            strategy_fn: Function returning signal series (-1, 0, 1)
            initial_capital: Starting capital
            commission: Commission per trade
            slippage: Slippage per trade
            
        Returns:
            Dict with metrics, trades, equity_curve, signals
        """
        self.validate_data(data)
        
        df = data.copy()
        
        # Generate signals
        signals = strategy_fn(df)
        if signals is None or len(signals) == 0:
            raise ValueError("Strategy returned empty signals")
        
        df['signal'] = signals
        
        # Calculate returns
        df['price_return'] = df['close'].pct_change()
        
        # Calculate transaction costs on signal changes
        df['signal_change'] = df['signal'].diff().abs()
        df['transaction_cost'] = df['signal_change'] * (commission + slippage)
        
        # Strategy returns (signal from previous period applied to current return)
        df['strategy_return'] = (
            df['price_return'] * df['signal'].shift(1) - df['transaction_cost']
        )
        df['strategy_return'] = df['strategy_return'].fillna(0)
        
        # Calculate equity curve
        df['equity'] = initial_capital * (1 + df['strategy_return']).cumprod()
        
        # Extract trades
        trades = self._extract_trades(df, commission, slippage)
        
        # Calculate metrics
        metrics = self.calculate_metrics(df['equity'], trades, initial_capital)
        
        return {
            "metrics": metrics,
            "trades": trades,
            "equity_curve": df['equity'],
            "signals": df['signal'],
        }
    
    def _extract_trades(
        self,
        df: pd.DataFrame,
        commission: float,
        slippage: float,
    ) -> List[TradeRecord]:
        """Extract individual trades from the backtest."""
        trades = []
        in_trade = False
        entry_price = 0.0
        entry_idx = None
        position = 0
        size = 1.0  # Simplified: always trade 1 unit
        
        for idx, row in df.iterrows():
            signal = row.get('signal', 0)
            
            if not in_trade and signal != 0:
                # Enter trade
                in_trade = True
                entry_price = row['close']
                entry_idx = idx
                position = signal
                
            elif in_trade and (signal == 0 or signal != position):
                # Exit trade
                exit_price = row['close']
                
                if position > 0:  # Long
                    pnl = (exit_price - entry_price) * size
                else:  # Short
                    pnl = (entry_price - exit_price) * size
                
                # Subtract costs
                trade_commission = (entry_price + exit_price) * size * commission
                trade_slippage = (entry_price + exit_price) * size * slippage
                pnl -= (trade_commission + trade_slippage)
                
                pnl_pct = (pnl / (entry_price * size)) * 100
                
                trades.append(TradeRecord(
                    entry_time=entry_idx,
                    exit_time=idx,
                    entry_price=entry_price,
                    exit_price=exit_price,
                    size=size,
                    side='long' if position > 0 else 'short',
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    commission=trade_commission,
                    slippage=trade_slippage,
                ))
                
                in_trade = False
                entry_price = 0.0
                entry_idx = None
                
                # Check if entering new position
                if signal != 0:
                    in_trade = True
                    entry_price = row['close']
                    entry_idx = idx
                    position = signal
        
        return trades


def run_simple_backtest(
    data: pd.DataFrame,
    strategy_fn: Callable[[pd.DataFrame], pd.Series],
    initial_capital: float = 500.0,
    commission: float = 0.001,
    slippage: float = 0.0005,
) -> Dict[str, Any]:
    """
    Convenience function to run a simple backtest.
    
    Args:
        data: OHLCV DataFrame
        strategy_fn: Strategy function returning signals
        initial_capital: Starting capital
        commission: Commission rate
        slippage: Slippage rate
        
    Returns:
        Backtest results dict
    """
    engine = SimpleEngine()
    return engine.run(
        data=data,
        strategy_fn=strategy_fn,
        initial_capital=initial_capital,
        commission=commission,
        slippage=slippage,
    )
