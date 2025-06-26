import pandas as pd
import numpy as np
import sys
import os
from typing import Dict, Any, Optional, Callable
from datetime import datetime, timedelta

# Add the project root to the path
sys.path.append('/root/Projet_AUTOBOT/src')

from autobot.trading.live_data_pipeline import live_pipeline

class RealBacktestEngine:
    """Real backtest engine using live market data"""
    
    def __init__(self):
        self.pipeline = live_pipeline
    
    def run_strategy_backtest(self, strategy_name: str, symbol: str = "BTCUSDT", 
                            periods: int = 100, initial_capital: float = 500.0,
                            params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Run backtest with real market data"""
        try:
            if '/' in symbol and any(fx in symbol for fx in ['EUR', 'GBP', 'JPY', 'AUD', 'CAD', 'CHF', 'NZD']):
                df = self.pipeline.get_forex_data(symbol, periods)
            elif any(commodity in symbol for commodity in ['XAU', 'XAG', 'WTI', 'NG', 'XPT']):
                df = self.pipeline.get_commodity_data(symbol, periods)
            else:
                df = self.pipeline.get_historical_data(symbol, periods)
            
            if df.empty:
                return {
                    'error': 'Failed to fetch market data',
                    'final_capital': initial_capital,
                    'total_return': 0.0,
                    'max_drawdown': 0.0,
                    'sharpe_ratio': 0.0,
                    'total_trades': 0
                }
            
            # Apply trading strategy
            strategy_results = self._apply_strategy(df, strategy_name, params or {})
            
            if strategy_results is None or strategy_results.empty:
                return {
                    'error': 'Strategy execution failed',
                    'final_capital': initial_capital,
                    'total_return': 0.0,
                    'max_drawdown': 0.0,
                    'sharpe_ratio': 0.0,
                    'total_trades': 0
                }
            
            # Calculate performance metrics
            metrics = self._calculate_performance_metrics(
                strategy_results, initial_capital
            )
            
            return {
                'symbol': symbol,
                'strategy': strategy_name,
                'periods': len(df),
                'initial_capital': initial_capital,
                'final_capital': metrics['final_capital'],
                'total_return': metrics['total_return'],
                'daily_return': metrics['daily_return'],
                'max_drawdown': metrics['max_drawdown'],
                'sharpe_ratio': metrics['sharpe_ratio'],
                'total_trades': metrics['total_trades'],
                'win_rate': metrics['win_rate'],
                'equity_curve': metrics['equity_curve'],
                'trades': metrics['trades'],
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"Backtest error: {e}")
            return {
                'error': f'Backtest failed: {str(e)}',
                'final_capital': initial_capital,
                'total_return': 0.0,
                'max_drawdown': 0.0,
                'sharpe_ratio': 0.0,
                'total_trades': 0
            }
    
    def _apply_strategy(self, df: pd.DataFrame, strategy_name: str, 
                       params: Dict[str, Any]) -> Optional[pd.DataFrame]:
        """Apply trading strategy to market data"""
        try:
            if strategy_name == "moving_average_crossover":
                return self._moving_average_strategy(df, params)
            elif strategy_name == "rsi_strategy":
                return self._rsi_strategy(df, params)
            elif strategy_name == "macd_strategy":
                return self._macd_strategy(df, params)
            elif strategy_name == "carry_trade":
                return self._carry_trade_strategy(df, params)
            elif strategy_name == "currency_correlation":
                return self._currency_correlation_strategy(df, params)
            elif strategy_name == "economic_indicator":
                return self._economic_indicator_strategy(df, params)
            elif strategy_name == "commodity_momentum":
                return self._commodity_momentum_strategy(df, params)
            else:
                return self._moving_average_strategy(df, params)
                
        except Exception as e:
            print(f"Strategy application error: {e}")
            return None
    
    def _moving_average_strategy(self, df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
        """Moving Average Crossover Strategy"""
        fast_period = params.get('fast_period', 10)
        slow_period = params.get('slow_period', 50)
        
        df = df.copy()
        df['ma_fast'] = df['close'].rolling(window=fast_period).mean()
        df['ma_slow'] = df['close'].rolling(window=slow_period).mean()
        
        # Generate signals
        df['signal'] = 0
        df.loc[df['ma_fast'] > df['ma_slow'], 'signal'] = 1
        df.loc[df['ma_fast'] < df['ma_slow'], 'signal'] = -1
        
        return df
    
    def _rsi_strategy(self, df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
        """RSI Strategy"""
        rsi_period = params.get('rsi_period', 14)
        overbought = params.get('overbought', 70)
        oversold = params.get('oversold', 30)
        
        df = df.copy()
        
        # Calculate RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # Generate signals
        df['signal'] = 0
        df.loc[df['rsi'] < oversold, 'signal'] = 1  # Buy signal
        df.loc[df['rsi'] > overbought, 'signal'] = -1  # Sell signal
        
        return df
    
    def _macd_strategy(self, df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
        """MACD Strategy"""
        fast_period = params.get('fast_period', 12)
        slow_period = params.get('slow_period', 26)
        signal_period = params.get('signal_period', 9)
        
        df = df.copy()
        
        # Calculate MACD
        ema_fast = df['close'].ewm(span=fast_period).mean()
        ema_slow = df['close'].ewm(span=slow_period).mean()
        df['macd'] = ema_fast - ema_slow
        df['macd_signal'] = df['macd'].ewm(span=signal_period).mean()
        df['macd_histogram'] = df['macd'] - df['macd_signal']
        
        # Generate signals
        df['signal'] = 0
        df.loc[df['macd'] > df['macd_signal'], 'signal'] = 1
        df.loc[df['macd'] < df['macd_signal'], 'signal'] = -1
        
        return df
    
    def _carry_trade_strategy(self, df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
        """Carry Trade Strategy for forex"""
        interest_rate_diff = params.get('interest_rate_diff', 0.02)  # 2% difference
        
        df = df.copy()
        df['returns'] = df['close'].pct_change()
        df['volatility'] = df['returns'].rolling(window=20).std()
        
        df['signal'] = 0
        df.loc[df['volatility'] < df['volatility'].quantile(0.3), 'signal'] = 1 if interest_rate_diff > 0 else -1
        
        return df

    def _currency_correlation_strategy(self, df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
        """Currency correlation strategy"""
        correlation_threshold = params.get('correlation_threshold', 0.7)
        
        df = df.copy()
        df['returns'] = df['close'].pct_change()
        df['ma_20'] = df['close'].rolling(window=20).mean()
        df['ma_50'] = df['close'].rolling(window=50).mean()
        
        df['signal'] = 0
        df.loc[df['ma_20'] > df['ma_50'], 'signal'] = 1
        df.loc[df['ma_20'] < df['ma_50'], 'signal'] = -1
        
        return df

    def _economic_indicator_strategy(self, df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
        """Strategy based on economic indicators"""
        df = df.copy()
        
        momentum_period = params.get('momentum_period', 14)
        df['momentum'] = df['close'].pct_change(momentum_period)
        df['ma_momentum'] = df['momentum'].rolling(window=5).mean()
        
        df['signal'] = 0
        df.loc[df['ma_momentum'] > 0, 'signal'] = 1
        df.loc[df['ma_momentum'] < 0, 'signal'] = -1
        
        return df
    
    def _commodity_momentum_strategy(self, df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
        """Momentum strategy optimized for commodities"""
        df = df.copy()
        
        momentum_period = params.get('momentum_period', 21)  # Longer period for commodities
        volatility_period = params.get('volatility_period', 14)
        
        df['returns'] = df['close'].pct_change()
        df['momentum'] = df['close'].pct_change(momentum_period)
        df['volatility'] = df['returns'].rolling(window=volatility_period).std()
        
        df['vol_adj_momentum'] = df['momentum'] / (df['volatility'] + 1e-8)  # Avoid division by zero
        
        df['signal'] = 0
        df.loc[df['vol_adj_momentum'] > df['vol_adj_momentum'].quantile(0.7), 'signal'] = 1
        df.loc[df['vol_adj_momentum'] < df['vol_adj_momentum'].quantile(0.3), 'signal'] = -1
        
        return df
    
    def _calculate_performance_metrics(self, df: pd.DataFrame,
                                     initial_capital: float) -> Dict[str, Any]:
        """Calculate comprehensive performance metrics"""
        df = df.copy()
        
        # Calculate returns
        df['returns'] = df['close'].pct_change()
        df['strategy_returns'] = df['signal'].shift(1) * df['returns']
        df['equity'] = initial_capital * (1 + df['strategy_returns'].fillna(0)).cumprod()
        
        # Final capital
        final_capital = df['equity'].iloc[-1]
        total_return = (final_capital - initial_capital) / initial_capital * 100
        
        # Daily return (assuming hourly data, convert to daily)
        daily_return = total_return / (len(df) / 24) if len(df) > 24 else total_return
        
        # Maximum drawdown
        df['peak'] = df['equity'].cummax()
        df['drawdown'] = (df['peak'] - df['equity']) / df['peak'] * 100
        max_drawdown = df['drawdown'].max()
        
        # Sharpe ratio
        strategy_returns = df['strategy_returns'].fillna(0)
        sharpe_ratio = 0.0
        if strategy_returns.std() > 0:
            sharpe_ratio = (strategy_returns.mean() / strategy_returns.std()) * np.sqrt(252)
        
        # Trade analysis
        df['position_change'] = df['signal'].diff()
        trades = []
        total_trades = 0
        winning_trades = 0
        
        # Count trades and calculate win rate
        for i in range(1, len(df)):
            if abs(df['position_change'].iloc[i]) > 0:
                total_trades += 1
                if df['strategy_returns'].iloc[i] > 0:
                    winning_trades += 1
                
                trades.append({
                    'timestamp': str(df.index[i]),
                    'signal': int(df['signal'].iloc[i]),
                    'price': float(df['close'].iloc[i]),
                    'return': float(df['strategy_returns'].iloc[i])
                })
        
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        return {
            'final_capital': float(final_capital),
            'total_return': float(total_return),
            'daily_return': float(daily_return),
            'max_drawdown': float(max_drawdown),
            'sharpe_ratio': float(sharpe_ratio),
            'total_trades': int(total_trades),
            'win_rate': float(win_rate),
            'equity_curve': df['equity'].tolist(),
            'trades': trades[-10:]  # Last 10 trades
        }

# Global backtest engine instance
real_backtest_engine = RealBacktestEngine()

def run_backtest(df, strategy_fn, initial_capital=500):
    """Legacy function for compatibility"""
    if df is None or len(df) == 0:
        raise ValueError("Les données sont vides.")
    
    # Use the real backtest engine
    return real_backtest_engine.run_strategy_backtest(
        "moving_average_crossover", "BTCUSDT", len(df), initial_capital
    )
