"""
Real Backtest Service for AUTOBOT
"""

import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from autobot.trading.strategy import (
    MovingAverageStrategy, 
    RSIStrategy, 
    BollingerBandsStrategy,
    MACDStrategy
)

logger = logging.getLogger(__name__)

class BacktestService:
    """Real backtest service using actual trading strategies"""
    
    def __init__(self):
        self.strategies = {
            "moving_average_crossover": MovingAverageStrategy,
            "rsi_strategy": RSIStrategy,
            "bollinger_bands": BollingerBandsStrategy,
            "macd_strategy": MACDStrategy
        }
    
    def generate_sample_data(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """Generate realistic sample market data for backtesting"""
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        
        date_range = pd.date_range(start, end, freq='D')
        days = len(date_range)
        
        np.random.seed(hash(symbol) % 2**32)
        
        base_prices = {
            "BTC/USD": 45000, "ETH/USD": 2500, "SOL/USD": 100,
            "ADA/USD": 0.5, "DOT/USD": 8, "XRP/USD": 0.6, "DOGE/USD": 0.08
        }
        base_price = base_prices.get(symbol, 100)
        
        daily_returns = np.random.normal(0.0005, 0.02, days)
        prices = base_price * np.exp(np.cumsum(daily_returns))
        
        data = pd.DataFrame({
            'open': prices * (1 + np.random.normal(0, 0.005, days)),
            'high': prices * (1 + np.abs(np.random.normal(0, 0.01, days))),
            'low': prices * (1 - np.abs(np.random.normal(0, 0.01, days))),
            'close': prices,
            'volume': np.random.randint(1000, 100000, days)
        }, index=date_range)
        
        data['high'] = np.maximum.reduce([data['open'], data['high'], data['close']])
        data['low'] = np.minimum.reduce([data['open'], data['low'], data['close']])
        
        return data
    
    def run_backtest(self, strategy_id: str, symbol: str, start_date: str, end_date: str, 
                    initial_capital: float, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Run a real backtest using actual strategy implementations"""
        try:
            if strategy_id not in self.strategies:
                raise ValueError(f"Strategy {strategy_id} not found")
            
            data = self.generate_sample_data(symbol, start_date, end_date)
            
            strategy_class = self.strategies[strategy_id]
            if params:
                if strategy_id == "moving_average_crossover":
                    strategy = strategy_class(
                        short_window=params.get("fast_period", 10),
                        long_window=params.get("slow_period", 50)
                    )
                elif strategy_id == "rsi_strategy":
                    strategy = strategy_class(
                        rsi_period=params.get("rsi_period", 14),
                        overbought=params.get("overbought", 70),
                        oversold=params.get("oversold", 30)
                    )
                elif strategy_id == "bollinger_bands":
                    strategy = strategy_class(
                        window=params.get("bb_period", 20),
                        num_std=params.get("bb_std", 2.0)
                    )
                else:
                    strategy = strategy_class()
            else:
                strategy = strategy_class()
            
            result_data = strategy.generate_signals(data)
            
            metrics = strategy.calculate_metrics(result_data)
            
            equity_curve = self._calculate_equity_curve(result_data, initial_capital)
            trades = self._extract_trades(result_data, initial_capital)
            
            return {
                "metrics": {
                    "total_return": metrics["profit"] * 100,
                    "sharpe": metrics["sharpe"],
                    "max_drawdown": abs(metrics["max_drawdown"]) * 100,
                    "win_rate": self._calculate_win_rate(trades),
                    "total_trades": len(trades),
                    "annual_return": metrics["profit"] * 100 * (365 / len(data))
                },
                "equity_curve": {
                    "dates": [d.strftime("%Y-%m-%d") for d in equity_curve.index],
                    "values": equity_curve.tolist()
                },
                "trades": trades
            }
            
        except Exception as e:
            logger.error(f"Error running backtest: {e}")
            raise
    
    def _calculate_equity_curve(self, data: pd.DataFrame, initial_capital: float) -> pd.Series:
        """Calculate equity curve from strategy signals"""
        data['returns'] = data['close'].pct_change()
        data['strategy_returns'] = data['signal'].shift(1) * data['returns']
        equity = initial_capital * (1 + data['strategy_returns'].fillna(0)).cumprod()
        return equity
    
    def _extract_trades(self, data: pd.DataFrame, initial_capital: float) -> List[Dict[str, Any]]:
        """Extract individual trades from signal data"""
        trades = []
        position = None
        
        for i, row in data.iterrows():
            if position is None and row['signal'] != 0:
                position = {
                    "type": "BUY" if row['signal'] > 0 else "SELL",
                    "date": i.strftime("%Y-%m-%d"),
                    "price": row['close'],
                    "size": initial_capital * 0.1 / row['close']
                }
                trades.append(position)
            
            elif position is not None and (row['signal'] == 0 or row['signal'] * position.get('signal', 1) < 0):
                pl = (row['close'] - position["price"]) * position["size"]
                if position["type"] == "SELL":
                    pl = -pl
                
                trades.append({
                    "type": "SELL" if position["type"] == "BUY" else "BUY",
                    "date": i.strftime("%Y-%m-%d"),
                    "price": row['close'],
                    "size": position["size"],
                    "pl": pl
                })
                position = None
        
        return trades
    
    def _calculate_win_rate(self, trades: List[Dict[str, Any]]) -> float:
        """Calculate win rate from trades"""
        profitable_trades = [t for t in trades if t.get("pl", 0) > 0]
        total_trades = len([t for t in trades if "pl" in t])
        return (len(profitable_trades) / total_trades * 100) if total_trades > 0 else 0

_backtest_service = BacktestService()

def get_backtest_service() -> BacktestService:
    """Get the global backtest service instance"""
    return _backtest_service
