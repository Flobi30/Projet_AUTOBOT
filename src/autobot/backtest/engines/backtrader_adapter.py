"""
Backtrader Engine Adapter

Adapter for the Backtrader library, providing event-driven backtesting
with more realistic execution simulation.
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

# Try to import backtrader
try:
    import backtrader as bt
    BACKTRADER_AVAILABLE = True
except ImportError:
    bt = None
    BACKTRADER_AVAILABLE = False


class BacktraderEngine(BaseEngine):
    """
    Backtrader-based backtest engine.
    
    Features:
    - Event-driven simulation
    - Multiple order types (market, limit, stop)
    - Realistic broker simulation
    - Position sizing
    - Multiple timeframes
    
    Requirements:
    - backtrader library must be installed
    """
    
    @classmethod
    def get_capabilities(cls) -> EngineCapabilities:
        return EngineCapabilities(
            name="backtrader",
            supports_tick_data=False,
            supports_l2_data=False,
            supports_partial_fills=True,
            supports_market_impact=False,
            supports_latency_simulation=True,
            min_timeframe="1m",
            max_timeframe="1M",
            supported_order_types=[
                OrderType.MARKET,
                OrderType.LIMIT,
                OrderType.STOP,
                OrderType.STOP_LIMIT,
            ],
            vectorized=False,
            multi_asset=True,
        )
    
    @classmethod
    def is_available(cls) -> bool:
        return BACKTRADER_AVAILABLE
    
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
        Run a backtest using Backtrader.
        
        Args:
            data: OHLCV DataFrame
            strategy_fn: Function returning signal series
            initial_capital: Starting capital
            commission: Commission rate
            slippage: Slippage rate (used as percentage)
            
        Returns:
            Dict with metrics, trades, equity_curve, signals
        """
        if not BACKTRADER_AVAILABLE:
            raise ImportError(
                "Backtrader is not installed. "
                "Install it with: pip install backtrader"
            )
        
        self.validate_data(data)
        
        # Pre-generate signals
        signals = strategy_fn(data)
        
        # Create Cerebro engine
        cerebro = bt.Cerebro()
        
        # Add data feed
        bt_data = self._create_data_feed(data)
        cerebro.adddata(bt_data)
        
        # Create and add strategy
        strategy_class = self._create_strategy_class(signals)
        cerebro.addstrategy(strategy_class)
        
        # Set broker parameters
        cerebro.broker.setcash(initial_capital)
        cerebro.broker.setcommission(commission=commission)
        
        # Add slippage
        cerebro.broker.set_slippage_perc(slippage)
        
        # Add analyzers
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
        cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
        cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
        cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
        
        # Run backtest
        results = cerebro.run()
        strat = results[0]
        
        # Extract results
        return self._extract_results(
            strat,
            initial_capital,
            signals,
            data,
        )
    
    def _create_data_feed(self, data: pd.DataFrame) -> 'bt.feeds.PandasData':
        """Create a Backtrader data feed from pandas DataFrame."""
        # Ensure we have all required columns
        df = data.copy()
        
        # Add missing columns with defaults
        if 'open' not in df.columns:
            df['open'] = df['close']
        if 'high' not in df.columns:
            df['high'] = df['close']
        if 'low' not in df.columns:
            df['low'] = df['close']
        if 'volume' not in df.columns:
            df['volume'] = 0
        
        # Ensure datetime index
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
        
        return bt.feeds.PandasData(dataname=df)
    
    def _create_strategy_class(self, signals: pd.Series) -> type:
        """Create a Backtrader strategy class that follows pre-computed signals."""
        
        class SignalStrategy(bt.Strategy):
            params = (('signals', signals),)
            
            def __init__(self):
                self.signal_series = self.params.signals
                self.order = None
                self.trade_list = []
                self.equity_history = []
            
            def next(self):
                # Record equity
                self.equity_history.append(self.broker.getvalue())
                
                # Get current signal
                current_idx = len(self) - 1
                if current_idx >= len(self.signal_series):
                    return
                
                signal = self.signal_series.iloc[current_idx]
                
                # Skip if order pending
                if self.order:
                    return
                
                # Execute based on signal
                if not self.position:
                    if signal > 0:
                        self.order = self.buy()
                    elif signal < 0:
                        self.order = self.sell()
                else:
                    if self.position.size > 0 and signal <= 0:
                        self.order = self.close()
                        if signal < 0:
                            self.order = self.sell()
                    elif self.position.size < 0 and signal >= 0:
                        self.order = self.close()
                        if signal > 0:
                            self.order = self.buy()
            
            def notify_order(self, order):
                if order.status in [order.Completed]:
                    self.order = None
            
            def notify_trade(self, trade):
                if trade.isclosed:
                    self.trade_list.append({
                        'pnl': trade.pnl,
                        'pnlcomm': trade.pnlcomm,
                        'size': trade.size,
                    })
        
        return SignalStrategy
    
    def _extract_results(
        self,
        strat: 'bt.Strategy',
        initial_capital: float,
        signals: pd.Series,
        data: pd.DataFrame,
    ) -> Dict[str, Any]:
        """Extract results from Backtrader strategy."""
        # Get analyzers
        trade_analyzer = strat.analyzers.trades.get_analysis()
        sharpe_analyzer = strat.analyzers.sharpe.get_analysis()
        drawdown_analyzer = strat.analyzers.drawdown.get_analysis()
        
        # Build equity curve
        equity_curve = pd.Series(
            strat.equity_history,
            index=data.index[:len(strat.equity_history)]
        )
        
        # Extract trades
        trades = []
        for i, trade_data in enumerate(strat.trade_list):
            trades.append(TradeRecord(
                entry_time=i,
                exit_time=i,
                entry_price=0,  # Not easily available
                exit_price=0,
                size=abs(trade_data.get('size', 1)),
                side='long' if trade_data.get('size', 1) > 0 else 'short',
                pnl=trade_data.get('pnlcomm', 0),
                pnl_pct=0,
                commission=trade_data.get('pnl', 0) - trade_data.get('pnlcomm', 0),
                slippage=0,
            ))
        
        # Calculate metrics
        if len(equity_curve) > 0:
            metrics = self.calculate_metrics(equity_curve, trades, initial_capital)
        else:
            # Fallback metrics
            metrics = BacktestMetrics(
                final_equity=initial_capital,
                total_pnl=0,
                total_return_pct=0,
                max_drawdown=0,
                max_drawdown_pct=0,
                sharpe_ratio=sharpe_analyzer.get('sharperatio', 0) or 0,
                sortino_ratio=0,
                calmar_ratio=0,
                win_rate=0,
                profit_factor=0,
                total_trades=trade_analyzer.get('total', {}).get('total', 0),
                winning_trades=trade_analyzer.get('won', {}).get('total', 0),
                losing_trades=trade_analyzer.get('lost', {}).get('total', 0),
                avg_trade_pnl=0,
                avg_win=0,
                avg_loss=0,
                max_consecutive_wins=0,
                max_consecutive_losses=0,
                avg_trade_duration=0,
                exposure_time_pct=0,
            )
        
        return {
            "metrics": metrics,
            "trades": trades,
            "equity_curve": equity_curve,
            "signals": signals,
        }


def run_backtrader_backtest(
    data: pd.DataFrame,
    strategy_fn: Callable[[pd.DataFrame], pd.Series],
    initial_capital: float = 500.0,
    commission: float = 0.001,
    slippage: float = 0.0005,
) -> Dict[str, Any]:
    """
    Convenience function to run a Backtrader backtest.
    
    Args:
        data: OHLCV DataFrame
        strategy_fn: Strategy function returning signals
        initial_capital: Starting capital
        commission: Commission rate
        slippage: Slippage rate
        
    Returns:
        Backtest results dict
    """
    engine = BacktraderEngine()
    return engine.run(
        data=data,
        strategy_fn=strategy_fn,
        initial_capital=initial_capital,
        commission=commission,
        slippage=slippage,
    )
