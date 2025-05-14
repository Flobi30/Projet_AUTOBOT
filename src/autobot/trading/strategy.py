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
    def __init__(self, rsi_period: int = 14, overbought: int = 70, oversold: int = 30):
        super().__init__(
            name="RSIStrategy",
            parameters={
                'rsi_period': rsi_period,
                'overbought': overbought,
                'oversold': oversold
            }
        )
        self.rsi_period = rsi_period
        self.overbought = overbought
        self.oversold = oversold
    
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
    def __init__(self, window: int = 20, num_std: float = 2.0):
        super().__init__(
            name="BollingerBands",
            parameters={
                'window': window,
                'num_std': num_std
            }
        )
        self.window = window
        self.num_std = num_std
    
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
