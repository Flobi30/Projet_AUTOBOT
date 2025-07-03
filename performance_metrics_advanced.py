"""
Advanced Performance Metrics for AUTOBOT
Phase 10 Implementation - Comprehensive Performance Analysis
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)

class AdvancedPerformanceMetrics:
    """
    Advanced performance metrics calculator including Sortino, Calmar ratios.
    Optimized for 1-5 second trading interval analysis.
    """
    
    def __init__(self, risk_free_rate: float = 0.02):
        self.risk_free_rate = risk_free_rate
        
    def calculate_comprehensive_metrics(self, returns: pd.Series, 
                                      benchmark_returns: Optional[pd.Series] = None) -> Dict[str, float]:
        """Calculate comprehensive performance metrics"""
        metrics = {}
        
        metrics.update(self._calculate_basic_metrics(returns))
        metrics.update(self._calculate_risk_adjusted_metrics(returns))
        metrics.update(self._calculate_drawdown_metrics(returns))
        metrics.update(self._calculate_trading_metrics(returns))
        
        if benchmark_returns is not None:
            metrics.update(self._calculate_relative_metrics(returns, benchmark_returns))
        
        return metrics
    
    def _calculate_basic_metrics(self, returns: pd.Series) -> Dict[str, float]:
        """Calculate basic performance metrics"""
        total_return = (1 + returns).prod() - 1
        annualized_return = (1 + returns.mean()) ** 252 - 1
        volatility = returns.std() * np.sqrt(252)
        
        return {
            'total_return': total_return,
            'annualized_return': annualized_return,
            'volatility': volatility,
            'mean_return': returns.mean(),
            'median_return': returns.median()
        }
    
    def _calculate_risk_adjusted_metrics(self, returns: pd.Series) -> Dict[str, float]:
        """Calculate risk-adjusted performance metrics"""
        excess_returns = returns - self.risk_free_rate / 252
        
        sharpe_ratio = excess_returns.mean() / returns.std() * np.sqrt(252) if returns.std() > 0 else 0
        
        downside_returns = returns[returns < 0]
        sortino_ratio = excess_returns.mean() / downside_returns.std() * np.sqrt(252) if len(downside_returns) > 0 and downside_returns.std() > 0 else 0
        
        max_drawdown = self._calculate_max_drawdown(returns)
        calmar_ratio = (returns.mean() * 252) / abs(max_drawdown) if max_drawdown != 0 else 0
        
        return {
            'sharpe_ratio': sharpe_ratio,
            'sortino_ratio': sortino_ratio,
            'calmar_ratio': calmar_ratio
        }
    
    def _calculate_drawdown_metrics(self, returns: pd.Series) -> Dict[str, float]:
        """Calculate drawdown-related metrics"""
        cumulative = (1 + returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        
        max_drawdown = abs(drawdown.min())
        avg_drawdown = abs(drawdown[drawdown < 0].mean()) if (drawdown < 0).any() else 0
        
        drawdown_periods = self._identify_drawdown_periods(drawdown)
        max_drawdown_duration = max([period['duration'] for period in drawdown_periods]) if drawdown_periods else 0
        avg_drawdown_duration = np.mean([period['duration'] for period in drawdown_periods]) if drawdown_periods else 0
        
        return {
            'max_drawdown': max_drawdown,
            'avg_drawdown': avg_drawdown,
            'max_drawdown_duration': max_drawdown_duration,
            'avg_drawdown_duration': avg_drawdown_duration,
            'drawdown_periods_count': len(drawdown_periods)
        }
    
    def _calculate_trading_metrics(self, returns: pd.Series) -> Dict[str, float]:
        """Calculate trading-specific metrics"""
        positive_returns = returns[returns > 0]
        negative_returns = returns[returns < 0]
        
        win_rate = len(positive_returns) / len(returns) if len(returns) > 0 else 0
        loss_rate = len(negative_returns) / len(returns) if len(returns) > 0 else 0
        
        avg_win = positive_returns.mean() if len(positive_returns) > 0 else 0
        avg_loss = abs(negative_returns.mean()) if len(negative_returns) > 0 else 0
        
        profit_factor = (positive_returns.sum() / abs(negative_returns.sum())) if negative_returns.sum() != 0 else float('inf')
        
        expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)
        
        return {
            'win_rate': win_rate,
            'loss_rate': loss_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'expectancy': expectancy,
            'total_trades': len(returns)
        }
    
    def _calculate_relative_metrics(self, returns: pd.Series, benchmark_returns: pd.Series) -> Dict[str, float]:
        """Calculate metrics relative to benchmark"""
        excess_returns = returns - benchmark_returns
        
        alpha = excess_returns.mean() * 252
        
        covariance = np.cov(returns, benchmark_returns)[0, 1]
        benchmark_variance = benchmark_returns.var()
        beta = covariance / benchmark_variance if benchmark_variance != 0 else 0
        
        tracking_error = excess_returns.std() * np.sqrt(252)
        information_ratio = alpha / tracking_error if tracking_error != 0 else 0
        
        return {
            'alpha': alpha,
            'beta': beta,
            'tracking_error': tracking_error,
            'information_ratio': information_ratio
        }
    
    def _calculate_max_drawdown(self, returns: pd.Series) -> float:
        """Calculate maximum drawdown"""
        cumulative = (1 + returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        return abs(drawdown.min())
    
    def _identify_drawdown_periods(self, drawdown: pd.Series) -> List[Dict[str, Any]]:
        """Identify individual drawdown periods"""
        periods = []
        in_drawdown = False
        start_idx = None
        
        for i, dd in enumerate(drawdown):
            if dd < 0 and not in_drawdown:
                in_drawdown = True
                start_idx = i
            elif dd >= 0 and in_drawdown:
                in_drawdown = False
                periods.append({
                    'start': start_idx,
                    'end': i - 1,
                    'duration': i - start_idx,
                    'depth': abs(drawdown.iloc[start_idx:i].min())
                })
        
        if in_drawdown and start_idx is not None:
            periods.append({
                'start': start_idx,
                'end': len(drawdown) - 1,
                'duration': len(drawdown) - start_idx,
                'depth': abs(drawdown.iloc[start_idx:].min())
            })
        
        return periods
    
    def generate_performance_report(self, returns: pd.Series, 
                                  benchmark_returns: Optional[pd.Series] = None) -> str:
        """Generate comprehensive performance report"""
        metrics = self.calculate_comprehensive_metrics(returns, benchmark_returns)
        
        report = "=== AUTOBOT Advanced Performance Report ===\n\n"
        
        report += "Basic Metrics:\n"
        report += f"Total Return: {metrics['total_return']:.2%}\n"
        report += f"Annualized Return: {metrics['annualized_return']:.2%}\n"
        report += f"Volatility: {metrics['volatility']:.2%}\n\n"
        
        report += "Risk-Adjusted Metrics:\n"
        report += f"Sharpe Ratio: {metrics['sharpe_ratio']:.3f}\n"
        report += f"Sortino Ratio: {metrics['sortino_ratio']:.3f}\n"
        report += f"Calmar Ratio: {metrics['calmar_ratio']:.3f}\n\n"
        
        report += "Drawdown Metrics:\n"
        report += f"Max Drawdown: {metrics['max_drawdown']:.2%}\n"
        report += f"Avg Drawdown: {metrics['avg_drawdown']:.2%}\n"
        report += f"Max Drawdown Duration: {metrics['max_drawdown_duration']} periods\n\n"
        
        report += "Trading Metrics:\n"
        report += f"Win Rate: {metrics['win_rate']:.2%}\n"
        report += f"Profit Factor: {metrics['profit_factor']:.2f}\n"
        report += f"Expectancy: {metrics['expectancy']:.4f}\n"
        report += f"Total Trades: {metrics['total_trades']}\n"
        
        if benchmark_returns is not None:
            report += "\nRelative Metrics:\n"
            report += f"Alpha: {metrics['alpha']:.2%}\n"
            report += f"Beta: {metrics['beta']:.3f}\n"
            report += f"Information Ratio: {metrics['information_ratio']:.3f}\n"
        
        return report
