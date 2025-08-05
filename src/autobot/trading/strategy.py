from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd

class Strategy(ABC):
    """
    Abstract base class for all trading strategies.
    """
    def __init__(self, name: str, parameters: Dict[str, Any] = None):
        self.name = name
        self.parameters = parameters or {}
        
    @abstractmethod
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Generate trading signals based on market data.
        
        Args:
            data: DataFrame with market data (OHLCV)
            
        Returns:
            DataFrame with added signal column
        """
        pass
    
    def calculate_metrics(self, data: pd.DataFrame) -> Dict[str, float]:
        """
        Calculate performance metrics for the strategy.
        
        Args:
            data: DataFrame with signals and price data
            
        Returns:
            Dictionary of performance metrics
        """
        if 'signal' not in data.columns or len(data) < 2:
            return {'profit': 0.0, 'max_drawdown': 0.0, 'sharpe': 0.0}
        
        data = data.copy()
        data['returns'] = data['close'].pct_change()
        data['strategy_returns'] = data['signal'].shift(1) * data['returns']
        
        total_return = (1 + data['strategy_returns'].fillna(0)).prod() - 1
        daily_returns = data['strategy_returns'].fillna(0)
        
        sharpe = 0.0
        if daily_returns.std() > 0:
            sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252)
        
        cum_returns = (1 + daily_returns).cumprod()
        running_max = cum_returns.cummax()
        drawdown = (cum_returns / running_max) - 1
        max_drawdown = drawdown.min()
        
        return {
            'profit': total_return,
            'max_drawdown': max_drawdown,
            'sharpe': sharpe
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert strategy to dictionary for serialization.
        """
        return {
            'name': self.name,
            'parameters': self.parameters
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        """
        Create strategy from dictionary.
        """
        return cls(name=data['name'], parameters=data['parameters'])


class MovingAverageStrategy(Strategy):
    """
    Simple moving average crossover strategy.
    """
    def __init__(self, short_window: int = 50, long_window: int = 200):
        super().__init__(
            name="MovingAverageCrossover",
            parameters={
                'short_window': short_window,
                'long_window': long_window
            }
        )
        self.short_window = short_window
        self.long_window = long_window
    
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Generate buy/sell signals based on moving average crossover.
        
        Args:
            data: DataFrame with OHLCV data
            
        Returns:
            DataFrame with added signal column (1 for buy, -1 for sell, 0 for hold)
        """
        if len(data) < self.long_window:
            raise ValueError(f"Data length ({len(data)}) is less than long_window ({self.long_window})")
        
        data = data.copy()
        
        data['short_ma'] = data['close'].rolling(window=self.short_window, min_periods=1).mean()
        data['long_ma'] = data['close'].rolling(window=self.long_window, min_periods=1).mean()
        
        data['signal'] = 0
        
        data.loc[data['short_ma'] > data['long_ma'], 'signal'] = 1  # Buy signal
        data.loc[data['short_ma'] < data['long_ma'], 'signal'] = -1  # Sell signal
        
        return data


class RSIStrategy(Strategy):
    """
    Relative Strength Index (RSI) strategy.
    """
    def __init__(self, rsi_period: int = 21, overbought: int = 75, oversold: int = 25, 
                 stop_loss_pct: float = 0.05, take_profit_pct: float = 0.10):
        super().__init__(
            name="RSIStrategy",
            parameters={
                'rsi_period': rsi_period,
                'overbought': overbought,
                'oversold': oversold,
                'stop_loss_pct': stop_loss_pct,
                'take_profit_pct': take_profit_pct
            }
        )
        self.rsi_period = rsi_period
        self.overbought = overbought
        self.oversold = oversold
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
    
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Generate buy/sell signals based on RSI indicator.
        
        Args:
            data: DataFrame with OHLCV data
            
        Returns:
            DataFrame with added signal column (1 for buy, -1 for sell, 0 for hold)
        """
        if len(data) < self.rsi_period:
            raise ValueError(f"Data length ({len(data)}) is less than rsi_period ({self.rsi_period})")
        
        data = data.copy()
        
        delta = data['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        
        rs = gain / loss
        data['rsi'] = 100 - (100 / (1 + rs))
        
        data['signal'] = 0
        
        data.loc[data['rsi'] < self.oversold, 'signal'] = 1  # Buy when oversold
        data.loc[data['rsi'] > self.overbought, 'signal'] = -1  # Sell when overbought
        
        return data


class BollingerBandsStrategy(Strategy):
    """
    Bollinger Bands trading strategy.
    """
    def __init__(self, window: int = 25, num_std: float = 2.5, 
                 stop_loss_pct: float = 0.04, take_profit_pct: float = 0.08):
        super().__init__(
            name="BollingerBands",
            parameters={
                'window': window,
                'num_std': num_std,
                'stop_loss_pct': stop_loss_pct,
                'take_profit_pct': take_profit_pct
            }
        )
        self.window = window
        self.num_std = num_std
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
    
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Generate buy/sell signals based on Bollinger Bands.
        
        Args:
            data: DataFrame with OHLCV data
            
        Returns:
            DataFrame with added signal column (1 for buy, -1 for sell, 0 for hold)
        """
        if len(data) < self.window:
            raise ValueError(f"Data length ({len(data)}) is less than window ({self.window})")
        
        data = data.copy()
        
        # Calculate Bollinger Bands
        data['middle_band'] = data['close'].rolling(window=self.window).mean()
        rolling_std = data['close'].rolling(window=self.window).std()
        data['upper_band'] = data['middle_band'] + (rolling_std * self.num_std)
        data['lower_band'] = data['middle_band'] - (rolling_std * self.num_std)
        
        # Calculate Bandwidth and %B
        data['bandwidth'] = (data['upper_band'] - data['lower_band']) / data['middle_band']
        data['percent_b'] = (data['close'] - data['lower_band']) / (data['upper_band'] - data['lower_band'])
        
        data['signal'] = 0
        
        data.loc[data['close'] < data['lower_band'], 'signal'] = 1
        
        data.loc[data['close'] > data['upper_band'], 'signal'] = -1
        
        data.loc[(data['percent_b'] > 0.05) & (data['percent_b'].shift(1) <= 0.05), 'signal'] = 1
        
        data.loc[(data['percent_b'] < 0.95) & (data['percent_b'].shift(1) >= 0.95), 'signal'] = -1
        
        return data


class MACDStrategy(Strategy):
    """
    Moving Average Convergence Divergence (MACD) strategy.
    """
    def __init__(self, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9):
        super().__init__(
            name="MACD",
            parameters={
                'fast_period': fast_period,
                'slow_period': slow_period,
                'signal_period': signal_period
            }
        )
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period
    
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Generate buy/sell signals based on MACD indicator.
        
        Args:
            data: DataFrame with OHLCV data
            
        Returns:
            DataFrame with added signal column (1 for buy, -1 for sell, 0 for hold)
        """
        if len(data) < self.slow_period + self.signal_period:
            raise ValueError(f"Data length ({len(data)}) is less than required minimum ({self.slow_period + self.signal_period})")
        
        data = data.copy()
        
        # Calculate MACD
        data['ema_fast'] = data['close'].ewm(span=self.fast_period, adjust=False).mean()
        data['ema_slow'] = data['close'].ewm(span=self.slow_period, adjust=False).mean()
        data['macd'] = data['ema_fast'] - data['ema_slow']
        data['signal_line'] = data['macd'].ewm(span=self.signal_period, adjust=False).mean()
        data['histogram'] = data['macd'] - data['signal_line']
        
        data['signal'] = 0
        
        data.loc[(data['macd'] > data['signal_line']) & (data['macd'].shift(1) <= data['signal_line'].shift(1)), 'signal'] = 1
        
        data.loc[(data['macd'] < data['signal_line']) & (data['macd'].shift(1) >= data['signal_line'].shift(1)), 'signal'] = -1
        
        data.loc[(data['histogram'] > 0) & (data['histogram'].shift(1) <= 0), 'signal'] = 1
        
        data.loc[(data['histogram'] < 0) & (data['histogram'].shift(1) >= 0), 'signal'] = -1
        
        return data


class VolumeWeightedMAStrategy(Strategy):
    """
    Volume-Weighted Moving Average (VWMA) strategy.
    """
    def __init__(self, short_window: int = 20, long_window: int = 50):
        super().__init__(
            name="VolumeWeightedMA",
            parameters={
                'short_window': short_window,
                'long_window': long_window
            }
        )
        self.short_window = short_window
        self.long_window = long_window
    
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Generate buy/sell signals based on Volume-Weighted Moving Average crossover.
        
        Args:
            data: DataFrame with OHLCV data
            
        Returns:
            DataFrame with added signal column (1 for buy, -1 for sell, 0 for hold)
        """
        if len(data) < self.long_window:
            raise ValueError(f"Data length ({len(data)}) is less than long_window ({self.long_window})")
        
        if 'volume' not in data.columns:
            raise ValueError("Volume data is required for VWMA strategy")
        
        data = data.copy()
        
        # Calculate Volume-Weighted Moving Averages
        data['pv'] = data['close'] * data['volume']
        
        data['short_vwma'] = data['pv'].rolling(window=self.short_window).sum() / data['volume'].rolling(window=self.short_window).sum()
        data['long_vwma'] = data['pv'].rolling(window=self.long_window).sum() / data['volume'].rolling(window=self.long_window).sum()
        
        # Calculate VWMA slope for trend strength
        data['short_vwma_slope'] = data['short_vwma'].diff(5) / data['short_vwma'].shift(5)
        data['long_vwma_slope'] = data['long_vwma'].diff(10) / data['long_vwma'].shift(10)
        
        data['signal'] = 0
        
        data.loc[data['short_vwma'] > data['long_vwma'], 'signal'] = 1
        data.loc[data['short_vwma'] < data['long_vwma'], 'signal'] = -1
        
        data.loc[(data['signal'] == 1) & (data['short_vwma_slope'] < 0), 'signal'] = 0  # Weak uptrend
        data.loc[(data['signal'] == -1) & (data['short_vwma_slope'] > 0), 'signal'] = 0  # Weak downtrend
        
        data.loc[(data['signal'] == 1) & (data['short_vwma_slope'] > 0.01) & (data['long_vwma_slope'] > 0), 'signal'] = 2  # Strong buy
        data.loc[(data['signal'] == -1) & (data['short_vwma_slope'] < -0.01) & (data['long_vwma_slope'] < 0), 'signal'] = -2  # Strong sell
        
        return data


class AdaptiveMultiStrategySystem(Strategy):
    """
    Adaptive Multi-Strategy System that combines multiple strategies with dynamic weighting.
    """
    def __init__(self, strategies: List[Strategy] = None, lookback_period: int = 20):
        self.strategies = strategies or [
            MovingAverageStrategy(),
            RSIStrategy(),
            BollingerBandsStrategy(),
            MACDStrategy()
        ]
        self.lookback_period = lookback_period
        
        strategy_names = [s.name for s in self.strategies]
        
        super().__init__(
            name="AdaptiveMultiStrategy",
            parameters={
                'strategies': strategy_names,
                'lookback_period': lookback_period
            }
        )
    
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Generate buy/sell signals by combining multiple strategies with dynamic weighting.
        
        Args:
            data: DataFrame with OHLCV data
            
        Returns:
            DataFrame with added signal column (1 for buy, -1 for sell, 0 for hold)
        """
        if len(data) < self.lookback_period:
            raise ValueError(f"Data length ({len(data)}) is less than lookback_period ({self.lookback_period})")
        
        data = data.copy()
        
        strategy_signals = {}
        strategy_performance = {}
        
        for strategy in self.strategies:
            try:
                strategy_data = strategy.generate_signals(data)
                strategy_signals[strategy.name] = strategy_data['signal']
                
                # Calculate recent performance for each strategy
                if len(strategy_data) > self.lookback_period:
                    recent_data = strategy_data.iloc[-self.lookback_period:]
                    recent_data['strategy_returns'] = recent_data['signal'].shift(1) * recent_data['close'].pct_change()
                    cumulative_return = (1 + recent_data['strategy_returns'].fillna(0)).prod() - 1
                    strategy_performance[strategy.name] = max(cumulative_return, 0)  # Only consider positive performance
                else:
                    strategy_performance[strategy.name] = 1.0  # Default equal weight
            except Exception as e:
                continue
        
        if not strategy_signals:
            data['signal'] = 0
            return data
        
        total_performance = sum(strategy_performance.values())
        if total_performance > 0:
            weights = {name: perf / total_performance for name, perf in strategy_performance.items()}
        else:
            weights = {name: 1.0 / len(strategy_performance) for name in strategy_performance}
        
        data['signal'] = 0
        for name, signal in strategy_signals.items():
            if name in weights:
                data['signal'] += signal * weights[name]
        
        data['signal_strength'] = data['signal'].abs()
        data.loc[data['signal'] > 0.3, 'signal'] = 1
        data.loc[data['signal'] < -0.3, 'signal'] = -1
        data.loc[(data['signal'] >= -0.3) & (data['signal'] <= 0.3), 'signal'] = 0
        
        data.loc[data['signal'] > 0.7, 'signal'] = 2
        data.loc[data['signal'] < -0.7, 'signal'] = -2
        
        return data
