"""
Continuous Backtesting System for AUTOBOT
Phase 9 Implementation - Walk-Forward Analysis
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
import logging
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import multiprocessing

logger = logging.getLogger(__name__)

class ContinuousBacktester:
    """
    Continuous backtesting system with walk-forward analysis.
    Optimized for AMD Ryzen 7 PRO 8700GE multi-core processing.
    """
    
    def __init__(self, training_window: int = 252, testing_window: int = 63, 
                 rebalance_frequency: int = 21):
        self.training_window = training_window
        self.testing_window = testing_window
        self.rebalance_frequency = rebalance_frequency
        self.cpu_count = min(multiprocessing.cpu_count(), 16)
        self.backtest_results = []
        
    def run_walk_forward_analysis(self, df: pd.DataFrame, strategy_func, 
                                parameter_ranges: Dict[str, Tuple[float, float]]) -> Dict[str, Any]:
        """Run walk-forward analysis with continuous parameter optimization"""
        results = []
        total_periods = len(df) - self.training_window - self.testing_window
        
        for i in range(0, total_periods, self.rebalance_frequency):
            train_start = i
            train_end = i + self.training_window
            test_start = train_end
            test_end = test_start + self.testing_window
            
            if test_end > len(df):
                break
            
            train_data = df.iloc[train_start:train_end]
            test_data = df.iloc[test_start:test_end]
            
            optimal_params = self._optimize_parameters(train_data, strategy_func, parameter_ranges)
            
            test_results = self._backtest_period(test_data, strategy_func, optimal_params)
            
            period_result = {
                'period': i // self.rebalance_frequency,
                'train_start': train_start,
                'train_end': train_end,
                'test_start': test_start,
                'test_end': test_end,
                'optimal_params': optimal_params,
                'test_results': test_results
            }
            
            results.append(period_result)
            logger.info(f"Completed walk-forward period {len(results)}/{total_periods // self.rebalance_frequency}")
        
        return self._aggregate_results(results)
    
    def _optimize_parameters(self, train_data: pd.DataFrame, strategy_func, 
                           parameter_ranges: Dict[str, Tuple[float, float]]) -> Dict[str, float]:
        """Optimize parameters using training data"""
        from genetic_optimizer import GeneticOptimizer
        
        optimizer = GeneticOptimizer(population_size=30, generations=50)
        optimal_params = optimizer.evolve_parameters(train_data, parameter_ranges)
        
        return optimal_params
    
    def _backtest_period(self, test_data: pd.DataFrame, strategy_func, 
                        params: Dict[str, float]) -> Dict[str, float]:
        """Backtest strategy on test period"""
        try:
            strategy_returns = strategy_func(test_data, params)
            
            total_return = (1 + strategy_returns).prod() - 1
            volatility = strategy_returns.std() * np.sqrt(252)
            sharpe_ratio = strategy_returns.mean() / strategy_returns.std() * np.sqrt(252) if strategy_returns.std() > 0 else 0
            max_drawdown = self._calculate_max_drawdown(strategy_returns)
            
            return {
                'total_return': total_return,
                'volatility': volatility,
                'sharpe_ratio': sharpe_ratio,
                'max_drawdown': max_drawdown,
                'win_rate': (strategy_returns > 0).mean(),
                'trade_count': len(strategy_returns)
            }
        except Exception as e:
            logger.error(f"Backtest period failed: {e}")
            return {
                'total_return': -1.0,
                'volatility': 1.0,
                'sharpe_ratio': -1.0,
                'max_drawdown': 1.0,
                'win_rate': 0.0,
                'trade_count': 0
            }
    
    def _calculate_max_drawdown(self, returns: pd.Series) -> float:
        """Calculate maximum drawdown"""
        cumulative = (1 + returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        return abs(drawdown.min())
    
    def _aggregate_results(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate walk-forward results"""
        if not results:
            return {}
        
        all_returns = []
        all_sharpe_ratios = []
        all_max_drawdowns = []
        all_win_rates = []
        
        for result in results:
            test_results = result['test_results']
            all_returns.append(test_results['total_return'])
            all_sharpe_ratios.append(test_results['sharpe_ratio'])
            all_max_drawdowns.append(test_results['max_drawdown'])
            all_win_rates.append(test_results['win_rate'])
        
        aggregated = {
            'total_periods': len(results),
            'avg_return': np.mean(all_returns),
            'avg_sharpe_ratio': np.mean(all_sharpe_ratios),
            'avg_max_drawdown': np.mean(all_max_drawdowns),
            'avg_win_rate': np.mean(all_win_rates),
            'return_std': np.std(all_returns),
            'consistency_score': len([r for r in all_returns if r > 0]) / len(all_returns),
            'parameter_stability': self._calculate_parameter_stability(results)
        }
        
        return aggregated
    
    def _calculate_parameter_stability(self, results: List[Dict[str, Any]]) -> float:
        """Calculate parameter stability across periods"""
        if len(results) < 2:
            return 1.0
        
        param_variations = []
        param_names = list(results[0]['optimal_params'].keys())
        
        for param_name in param_names:
            param_values = [result['optimal_params'][param_name] for result in results]
            param_std = np.std(param_values)
            param_mean = np.mean(param_values)
            
            if param_mean != 0:
                coefficient_of_variation = param_std / abs(param_mean)
                param_variations.append(coefficient_of_variation)
        
        if param_variations:
            avg_variation = np.mean(param_variations)
            stability_score = 1 / (1 + avg_variation)
            return stability_score
        
        return 1.0
    
    def run_continuous_monitoring(self, df: pd.DataFrame, strategy_func, 
                                 current_params: Dict[str, float]) -> Dict[str, Any]:
        """Run continuous monitoring of strategy performance"""
        recent_data = df.tail(self.testing_window)
        
        current_performance = self._backtest_period(recent_data, strategy_func, current_params)
        
        performance_threshold = 0.05
        if current_performance['sharpe_ratio'] < performance_threshold:
            logger.warning("Strategy performance degraded, triggering reoptimization")
            
            train_data = df.tail(self.training_window)
            parameter_ranges = self._get_default_parameter_ranges()
            new_params = self._optimize_parameters(train_data, strategy_func, parameter_ranges)
            
            return {
                'reoptimization_triggered': True,
                'old_params': current_params,
                'new_params': new_params,
                'current_performance': current_performance
            }
        
        return {
            'reoptimization_triggered': False,
            'current_params': current_params,
            'current_performance': current_performance
        }
    
    def _get_default_parameter_ranges(self) -> Dict[str, Tuple[float, float]]:
        """Get default parameter ranges for optimization"""
        return {
            'ma_short': (3, 10),
            'ma_long': (10, 25),
            'rsi_period': (10, 20),
            'rsi_oversold': (20, 35),
            'rsi_overbought': (65, 80)
        }
