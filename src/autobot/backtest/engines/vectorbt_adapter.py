"""
VectorBT Engine Adapter

Adapter for the vectorbt library, providing high-performance
vectorized backtesting with advanced analytics.
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Callable, List, Optional
import logging

from autobot.backtest.engines.base import (
    BaseEngine,
    EngineCapabilities,
    OrderType,
    TradeRecord,
    BacktestMetrics,
)

logger = logging.getLogger(__name__)

# Try to import vectorbt
try:
    import vectorbt as vbt
    VECTORBT_AVAILABLE = True
except ImportError:
    vbt = None
    VECTORBT_AVAILABLE = False


class VectorbtEngine(BaseEngine):
    """
    VectorBT-based backtest engine.
    
    Features:
    - Ultra-fast vectorized operations
    - Built-in performance analytics
    - Parameter optimization support
    - Portfolio-level analysis
    - Advanced visualization
    
    Requirements:
    - vectorbt library must be installed
    """
    
    @classmethod
    def get_capabilities(cls) -> EngineCapabilities:
        return EngineCapabilities(
            name="vectorbt",
            supports_tick_data=False,
            supports_l2_data=False,
            supports_partial_fills=False,
            supports_market_impact=False,
            supports_latency_simulation=False,
            min_timeframe="1m",
            max_timeframe="1M",
            supported_order_types=[OrderType.MARKET],
            vectorized=True,
            multi_asset=True,
        )
    
    @classmethod
    def is_available(cls) -> bool:
        return VECTORBT_AVAILABLE
    
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
        Run a backtest using VectorBT.
        
        Args:
            data: OHLCV DataFrame
            strategy_fn: Function returning signal series
            initial_capital: Starting capital
            commission: Commission rate (as percentage)
            slippage: Slippage rate (as percentage)
            
        Returns:
            Dict with metrics, trades, equity_curve, signals
        """
        if not VECTORBT_AVAILABLE:
            raise ImportError(
                "VectorBT is not installed. "
                "Install it with: pip install vectorbt"
            )
        
        self.validate_data(data)
        
        # Generate signals
        signals = strategy_fn(data)
        
        # Convert signals to entries and exits
        entries, exits = self._signals_to_entries_exits(signals)
        
        # Create portfolio
        close_prices = data['close']
        
        # Run backtest with vectorbt
        portfolio = vbt.Portfolio.from_signals(
            close=close_prices,
            entries=entries,
            exits=exits,
            init_cash=initial_capital,
            fees=commission,
            slippage=slippage,
            freq='1D',  # Will be adjusted based on data
        )
        
        # Extract results
        return self._extract_results(portfolio, signals, initial_capital)
    
    def _signals_to_entries_exits(
        self,
        signals: pd.Series,
    ) -> tuple:
        """Convert signal series to entry/exit boolean series."""
        # Entry when signal changes from 0 or negative to positive
        entries = (signals > 0) & (signals.shift(1) <= 0)
        
        # Exit when signal changes from positive to 0 or negative
        exits = (signals <= 0) & (signals.shift(1) > 0)
        
        return entries, exits
    
    def _extract_results(
        self,
        portfolio: 'vbt.Portfolio',
        signals: pd.Series,
        initial_capital: float,
    ) -> Dict[str, Any]:
        """Extract results from VectorBT portfolio."""
        # Get equity curve
        equity_curve = portfolio.value()
        
        # Get trades
        trades_df = portfolio.trades.records_readable
        trades = []
        
        if len(trades_df) > 0:
            for _, row in trades_df.iterrows():
                trades.append(TradeRecord(
                    entry_time=row.get('Entry Timestamp', row.get('Entry Index', 0)),
                    exit_time=row.get('Exit Timestamp', row.get('Exit Index', 0)),
                    entry_price=row.get('Entry Price', 0),
                    exit_price=row.get('Exit Price', 0),
                    size=row.get('Size', 1),
                    side='long' if row.get('Direction', 'Long') == 'Long' else 'short',
                    pnl=row.get('PnL', 0),
                    pnl_pct=row.get('Return', 0) * 100,
                    commission=row.get('Entry Fees', 0) + row.get('Exit Fees', 0),
                    slippage=0,
                ))
        
        # Get stats
        stats = portfolio.stats()
        
        # Build metrics
        metrics = BacktestMetrics(
            final_equity=float(equity_curve.iloc[-1]) if len(equity_curve) > 0 else initial_capital,
            total_pnl=float(stats.get('Total Return [$]', 0)),
            total_return_pct=float(stats.get('Total Return [%]', 0)),
            max_drawdown=float(stats.get('Max Drawdown [$]', 0)),
            max_drawdown_pct=float(stats.get('Max Drawdown [%]', 0)),
            sharpe_ratio=float(stats.get('Sharpe Ratio', 0)),
            sortino_ratio=float(stats.get('Sortino Ratio', 0)),
            calmar_ratio=float(stats.get('Calmar Ratio', 0)),
            win_rate=float(stats.get('Win Rate [%]', 0)),
            profit_factor=float(stats.get('Profit Factor', 0)),
            total_trades=int(stats.get('Total Trades', 0)),
            winning_trades=int(stats.get('Winning Trades', 0)),
            losing_trades=int(stats.get('Losing Trades', 0)),
            avg_trade_pnl=float(stats.get('Avg Trade PnL [$]', 0)),
            avg_win=float(stats.get('Avg Winning Trade [%]', 0)),
            avg_loss=float(stats.get('Avg Losing Trade [%]', 0)),
            max_consecutive_wins=int(stats.get('Max Consecutive Wins', 0)),
            max_consecutive_losses=int(stats.get('Max Consecutive Losses', 0)),
            avg_trade_duration=float(stats.get('Avg Trade Duration', 0)),
            exposure_time_pct=float(stats.get('Exposure Time [%]', 0)),
        )
        
        return {
            "metrics": metrics,
            "trades": trades,
            "equity_curve": equity_curve,
            "signals": signals,
            "portfolio": portfolio,  # Include full portfolio for advanced analysis
        }
    
    def optimize(
        self,
        data: pd.DataFrame,
        strategy_fn: Callable,
        param_grid: Dict[str, List[Any]],
        initial_capital: float = 500.0,
        commission: float = 0.001,
        slippage: float = 0.0005,
        metric: str = 'sharpe_ratio',
    ) -> Dict[str, Any]:
        """
        Optimize strategy parameters using VectorBT's built-in optimization.
        
        Args:
            data: OHLCV DataFrame
            strategy_fn: Strategy function that accepts parameters
            param_grid: Dictionary of parameter names to lists of values
            initial_capital: Starting capital
            commission: Commission rate
            slippage: Slippage rate
            metric: Metric to optimize ('sharpe_ratio', 'total_return', etc.)
            
        Returns:
            Dict with best parameters and results
        """
        if not VECTORBT_AVAILABLE:
            raise ImportError("VectorBT is not installed")
        
        best_result = None
        best_params = None
        best_metric = float('-inf')
        
        # Simple grid search (VectorBT has more advanced methods)
        from itertools import product
        
        param_names = list(param_grid.keys())
        param_values = list(param_grid.values())
        
        for values in product(*param_values):
            params = dict(zip(param_names, values))
            
            # Run backtest with these parameters
            def param_strategy(df):
                return strategy_fn(df, **params)
            
            try:
                result = self.run(
                    data=data,
                    strategy_fn=param_strategy,
                    initial_capital=initial_capital,
                    commission=commission,
                    slippage=slippage,
                )
                
                # Get metric value
                metrics = result['metrics']
                metric_value = getattr(metrics, metric, 0)
                
                if metric_value > best_metric:
                    best_metric = metric_value
                    best_params = params
                    best_result = result
                    
            except Exception as e:
                logger.warning(f"Optimization failed for params {params}: {e}")
                continue
        
        return {
            "best_params": best_params,
            "best_metric": best_metric,
            "best_result": best_result,
        }


def run_vectorbt_backtest(
    data: pd.DataFrame,
    strategy_fn: Callable[[pd.DataFrame], pd.Series],
    initial_capital: float = 500.0,
    commission: float = 0.001,
    slippage: float = 0.0005,
) -> Dict[str, Any]:
    """
    Convenience function to run a VectorBT backtest.
    
    Args:
        data: OHLCV DataFrame
        strategy_fn: Strategy function returning signals
        initial_capital: Starting capital
        commission: Commission rate
        slippage: Slippage rate
        
    Returns:
        Backtest results dict
    """
    engine = VectorbtEngine()
    return engine.run(
        data=data,
        strategy_fn=strategy_fn,
        initial_capital=initial_capital,
        commission=commission,
        slippage=slippage,
    )
