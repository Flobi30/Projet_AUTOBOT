"""
Prediction-based trading strategies for AUTOBOT.
Leverages the advanced prediction module to generate trading signals.
"""
import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional, Union
from datetime import datetime, timedelta

from ..prediction.engine import PredictionEngine, create_prediction_engine
from .strategy import Strategy

logger = logging.getLogger(__name__)

class PredictionBasedStrategy(Strategy):
    """
    Trading strategy based on machine learning predictions.
    Uses the prediction module to forecast price movements and generate signals.
    """
    def __init__(
        self,
        model_name: str = "default",
        model_type: str = "LSTMModel",
        threshold: float = 0.5,
        confidence_threshold: float = 0.7,
        lookback_window: int = 60,
        prediction_horizon: int = 3
    ):
        """
        Initialize the prediction-based strategy.
        
        Args:
            model_name: Name of the prediction model
            model_type: Type of the prediction model
            threshold: Threshold for buy/sell signals
            confidence_threshold: Threshold for high-confidence signals
            lookback_window: Number of periods to look back for prediction
            prediction_horizon: Number of periods to predict ahead
        """
        super().__init__(
            name="PredictionBased",
            parameters={
                'model_name': model_name,
                'model_type': model_type,
                'threshold': threshold,
                'confidence_threshold': confidence_threshold,
                'lookback_window': lookback_window,
                'prediction_horizon': prediction_horizon
            }
        )
        
        self.model_name = model_name
        self.model_type = model_type
        self.threshold = threshold
        self.confidence_threshold = confidence_threshold
        self.lookback_window = lookback_window
        self.prediction_horizon = prediction_horizon
        
        self.prediction_engine = None
        self.is_initialized = False
    
    def initialize(self) -> None:
        """Initialize the prediction engine."""
        if self.is_initialized:
            return
        
        logger.info(f"Initializing prediction-based strategy with model {self.model_name}")
        
        self.prediction_engine = create_prediction_engine({
            'model_name': self.model_name,
            'model_type': self.model_type,
            'feature_params': {
                'sequence_length': self.lookback_window,
                'prediction_horizon': self.prediction_horizon
            }
        })
        
        self.is_initialized = True
    
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Generate buy/sell signals based on price predictions.
        
        Args:
            data: DataFrame with OHLCV data
            
        Returns:
            DataFrame with added signal column (1 for buy, -1 for sell, 0 for hold)
        """
        if len(data) < self.lookback_window:
            raise ValueError(f"Data length ({len(data)}) is less than lookback_window ({self.lookback_window})")
        
        self.initialize()
        
        data = data.copy()
        
        if not self.prediction_engine.model.is_trained:
            train_size = int(len(data) * 0.7)
            train_data = data.iloc[:train_size]
            
            logger.info(f"Training prediction model with {len(train_data)} samples")
            self.prediction_engine.train(train_data)
        
        data['signal'] = 0
        data['prediction'] = np.nan
        data['confidence'] = np.nan
        
        for i in range(self.lookback_window, len(data)):
            try:
                window_data = data.iloc[i-self.lookback_window:i]
                
                result = self.prediction_engine.predict(window_data)
                
                prediction_value = result.get_prediction(0)
                confidence_value = result.get_confidence(0) if result.confidence is not None else 0.5
                
                data.loc[data.index[i], 'prediction'] = prediction_value
                data.loc[data.index[i], 'confidence'] = confidence_value
                
                if prediction_value > self.threshold:
                    data.loc[data.index[i], 'signal'] = 1  # Buy signal
                    
                    if confidence_value > self.confidence_threshold:
                        data.loc[data.index[i], 'signal'] = 2
                
                elif prediction_value < -self.threshold:
                    data.loc[data.index[i], 'signal'] = -1  # Sell signal
                    
                    if confidence_value > self.confidence_threshold:
                        data.loc[data.index[i], 'signal'] = -2
            
            except Exception as e:
                logger.error(f"Error generating prediction at index {i}: {str(e)}")
                continue
        
        return data


class HybridPredictionStrategy(Strategy):
    """
    Hybrid strategy that combines traditional technical indicators with ML predictions.
    """
    def __init__(
        self,
        base_strategies: List[Strategy] = None,
        prediction_strategy: Optional[PredictionBasedStrategy] = None,
        prediction_weight: float = 0.5,
        adaptive_weight: bool = True,
        lookback_period: int = 20
    ):
        """
        Initialize the hybrid prediction strategy.
        
        Args:
            base_strategies: List of traditional strategies to combine
            prediction_strategy: Prediction-based strategy
            prediction_weight: Weight to give to the prediction strategy
            adaptive_weight: Whether to adapt weights based on performance
            lookback_period: Period to look back for performance evaluation
        """
        self.base_strategies = base_strategies or []
        self.prediction_strategy = prediction_strategy or PredictionBasedStrategy()
        self.prediction_weight = prediction_weight
        self.adaptive_weight = adaptive_weight
        self.lookback_period = lookback_period
        
        strategy_names = [s.name for s in self.base_strategies] + [self.prediction_strategy.name]
        
        super().__init__(
            name="HybridPrediction",
            parameters={
                'base_strategies': strategy_names,
                'prediction_weight': prediction_weight,
                'adaptive_weight': adaptive_weight,
                'lookback_period': lookback_period
            }
        )
    
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Generate buy/sell signals by combining traditional strategies with ML predictions.
        
        Args:
            data: DataFrame with OHLCV data
            
        Returns:
            DataFrame with added signal column (1 for buy, -1 for sell, 0 for hold)
        """
        if len(data) < self.lookback_period:
            raise ValueError(f"Data length ({len(data)}) is less than lookback_period ({self.lookback_period})")
        
        data = data.copy()
        
        base_signals = {}
        base_performance = {}
        
        for strategy in self.base_strategies:
            try:
                strategy_data = strategy.generate_signals(data)
                base_signals[strategy.name] = strategy_data['signal']
                
                if len(strategy_data) > self.lookback_period:
                    recent_data = strategy_data.iloc[-self.lookback_period:]
                    recent_data['strategy_returns'] = recent_data['signal'].shift(1) * recent_data['close'].pct_change()
                    cumulative_return = (1 + recent_data['strategy_returns'].fillna(0)).prod() - 1
                    base_performance[strategy.name] = max(cumulative_return, 0)
                else:
                    base_performance[strategy.name] = 1.0
            except Exception as e:
                logger.error(f"Error generating signals for {strategy.name}: {str(e)}")
                continue
        
        try:
            prediction_data = self.prediction_strategy.generate_signals(data)
            prediction_signal = prediction_data['signal']
            
            if len(prediction_data) > self.lookback_period:
                recent_data = prediction_data.iloc[-self.lookback_period:]
                recent_data['strategy_returns'] = recent_data['signal'].shift(1) * recent_data['close'].pct_change()
                cumulative_return = (1 + recent_data['strategy_returns'].fillna(0)).prod() - 1
                prediction_performance = max(cumulative_return, 0)
            else:
                prediction_performance = 1.0
        except Exception as e:
            logger.error(f"Error generating signals for prediction strategy: {str(e)}")
            prediction_signal = pd.Series(0, index=data.index)
            prediction_performance = 0.0
        
        base_weight = 1.0 - self.prediction_weight
        
        if self.adaptive_weight and sum(base_performance.values()) > 0:
            total_base_performance = sum(base_performance.values())
            base_weights = {name: (perf / total_base_performance) * base_weight 
                           for name, perf in base_performance.items()}
            
            total_performance = total_base_performance + prediction_performance
            prediction_weight = prediction_performance / total_performance
        else:
            base_weights = {name: base_weight / len(base_performance) 
                           for name in base_performance}
            prediction_weight = self.prediction_weight
        
        data['signal'] = 0
        
        for name, signal in base_signals.items():
            if name in base_weights:
                data['signal'] += signal * base_weights[name]
        
        data['signal'] += prediction_signal * prediction_weight
        
        data['signal_strength'] = data['signal'].abs()
        data.loc[data['signal'] > 0.3, 'signal'] = 1
        data.loc[data['signal'] < -0.3, 'signal'] = -1
        data.loc[(data['signal'] >= -0.3) & (data['signal'] <= 0.3), 'signal'] = 0
        
        data.loc[data['signal'] > 0.7, 'signal'] = 2
        data.loc[data['signal'] < -0.7, 'signal'] = -2
        
        return data


class StrategyManager:
    """
    Manager for trading strategies.
    Provides a unified interface for creating, managing, and using strategies.
    """
    def __init__(self):
        """Initialize the strategy manager."""
        self.strategies = {}
        self.active_strategy = None
    
    def register_strategy(self, strategy: Strategy) -> None:
        """
        Register a strategy.
        
        Args:
            strategy: Strategy to register
        """
        self.strategies[strategy.name] = strategy
        logger.info(f"Registered strategy: {strategy.name}")
    
    def get_strategy(self, name: str) -> Optional[Strategy]:
        """
        Get a strategy by name.
        
        Args:
            name: Strategy name
            
        Returns:
            Strategy if found, None otherwise
        """
        return self.strategies.get(name)
    
    def set_active_strategy(self, name: str) -> None:
        """
        Set the active strategy.
        
        Args:
            name: Strategy name
        """
        if name in self.strategies:
            self.active_strategy = self.strategies[name]
            logger.info(f"Set active strategy to {name}")
        else:
            raise ValueError(f"Strategy {name} not found")
    
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Generate signals using the active strategy.
        
        Args:
            data: DataFrame with OHLCV data
            
        Returns:
            DataFrame with added signal column
        """
        if self.active_strategy is None:
            raise ValueError("No active strategy set")
        
        return self.active_strategy.generate_signals(data)
    
    def create_prediction_strategy(
        self,
        model_name: str = "default",
        model_type: str = "LSTMModel",
        threshold: float = 0.5,
        confidence_threshold: float = 0.7
    ) -> PredictionBasedStrategy:
        """
        Create a prediction-based strategy.
        
        Args:
            model_name: Name of the prediction model
            model_type: Type of the prediction model
            threshold: Threshold for buy/sell signals
            confidence_threshold: Threshold for high-confidence signals
            
        Returns:
            Created strategy
        """
        strategy = PredictionBasedStrategy(
            model_name=model_name,
            model_type=model_type,
            threshold=threshold,
            confidence_threshold=confidence_threshold
        )
        
        self.register_strategy(strategy)
        return strategy
    
    def create_hybrid_strategy(
        self,
        base_strategy_names: List[str] = None,
        prediction_strategy_name: str = None,
        prediction_weight: float = 0.5
    ) -> HybridPredictionStrategy:
        """
        Create a hybrid prediction strategy.
        
        Args:
            base_strategy_names: Names of base strategies
            prediction_strategy_name: Name of prediction strategy
            prediction_weight: Weight to give to the prediction strategy
            
        Returns:
            Created strategy
        """
        base_strategies = []
        if base_strategy_names:
            for name in base_strategy_names:
                strategy = self.get_strategy(name)
                if strategy:
                    base_strategies.append(strategy)
        
        prediction_strategy = None
        if prediction_strategy_name:
            prediction_strategy = self.get_strategy(prediction_strategy_name)
            if not prediction_strategy:
                prediction_strategy = self.create_prediction_strategy()
        else:
            prediction_strategy = self.create_prediction_strategy()
        
        strategy = HybridPredictionStrategy(
            base_strategies=base_strategies,
            prediction_strategy=prediction_strategy,
            prediction_weight=prediction_weight
        )
        
        self.register_strategy(strategy)
        return strategy
    
    def get_available_strategies(self) -> List[Dict[str, Any]]:
        """
        Get information about available strategies.
        
        Returns:
            List of strategy information
        """
        return [
            {
                'name': strategy.name,
                'parameters': strategy.parameters,
                'active': strategy == self.active_strategy
            }
            for strategy in self.strategies.values()
        ]
    
    def evaluate_all_strategies(self, data: pd.DataFrame) -> Dict[str, Dict[str, float]]:
        """
        Evaluate all registered strategies.
        
        Args:
            data: DataFrame with OHLCV data
            
        Returns:
            Dictionary of strategy metrics
        """
        results = {}
        
        for name, strategy in self.strategies.items():
            try:
                strategy_data = strategy.generate_signals(data)
                metrics = strategy.calculate_metrics(strategy_data)
                results[name] = metrics
            except Exception as e:
                logger.error(f"Error evaluating strategy {name}: {str(e)}")
                results[name] = {'error': str(e)}
        
        return results
    
    def get_best_strategy(self, data: pd.DataFrame, metric: str = 'profit') -> str:
        """
        Get the best strategy based on a metric.
        
        Args:
            data: DataFrame with OHLCV data
            metric: Metric to use for comparison
            
        Returns:
            Name of the best strategy
        """
        results = self.evaluate_all_strategies(data)
        
        best_strategy = None
        best_value = float('-inf')
        
        for name, metrics in results.items():
            if metric in metrics and metrics[metric] > best_value:
                best_value = metrics[metric]
                best_strategy = name
        
        return best_strategy

_strategy_manager = StrategyManager()

def get_strategy_manager() -> StrategyManager:
    """
    Get the global strategy manager instance.
    
    Returns:
        StrategyManager instance
    """
    return _strategy_manager
