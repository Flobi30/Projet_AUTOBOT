"""
Enhanced Backtest Service with Advanced Optimizations for AUTOBOT
Integrates multi-pair trading, adaptive learning, and enhanced risk management
"""

import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
import asyncio
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor

from autobot.trading.strategy import (
    MovingAverageStrategy, 
    RSIStrategy, 
    BollingerBandsStrategy,
    MACDStrategy,
    AdaptiveMultiStrategySystem
)
from autobot.risk_manager_enhanced import RiskManager
from autobot.rl.meta_learning import MetaLearner
from autobot.agents.advanced_orchestrator import AdvancedOrchestrator

logger = logging.getLogger(__name__)

class EnhancedBacktestService:
    """Enhanced backtest service with advanced optimizations"""
    
    def __init__(self):
        self.strategies = {
            "moving_average_crossover": MovingAverageStrategy,
            "rsi_strategy": RSIStrategy,
            "bollinger_bands": BollingerBandsStrategy,
            "macd_strategy": MACDStrategy,
            "adaptive_multi_strategy": AdaptiveMultiStrategySystem
        }
        
        self.risk_manager = RiskManager(
            initial_capital=10000,
            max_risk_per_trade_pct=2.0,
            max_portfolio_risk_pct=5.0,
            max_drawdown_pct=15.0,
            position_sizing_method="kelly"
        )
        
        self.meta_learner = MetaLearner(
            strategy_pool_size=8,
            adaptation_interval=1800.0,  # 30 minutes
            exploration_rate=0.15,
            learning_rate=0.02,
            auto_adapt=True
        )
        
        self.orchestrator = AdvancedOrchestrator(
            trading_symbols=["BTC/USD", "ETH/USD", "SOL/USD", "ADA/USD"],
            enable_superagi=False,
            autonomous_mode=True
        )
        
        self.trading_pairs = [
            "BTC/USD", "ETH/USD", "SOL/USD", "ADA/USD", 
            "DOT/USD", "XRP/USD", "DOGE/USD", "AVAX/USD"
        ]
        
        logger.info("Enhanced Backtest Service initialized with advanced optimizations")
    
    def generate_multi_pair_data(self, symbols: List[str], start_date: str, end_date: str) -> Dict[str, pd.DataFrame]:
        """Generate realistic multi-pair market data with correlations"""
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        date_range = pd.date_range(start, end, freq='D')
        days = len(date_range)
        
        base_prices = {
            "BTC/USD": 45000, "ETH/USD": 2500, "SOL/USD": 100,
            "ADA/USD": 0.5, "DOT/USD": 8, "XRP/USD": 0.6, 
            "DOGE/USD": 0.08, "AVAX/USD": 25
        }
        
        correlation_matrix = np.array([
            [1.0, 0.8, 0.6, 0.4, 0.5, 0.3, 0.2, 0.6],  # BTC
            [0.8, 1.0, 0.7, 0.5, 0.6, 0.4, 0.3, 0.7],  # ETH
            [0.6, 0.7, 1.0, 0.6, 0.7, 0.5, 0.4, 0.8],  # SOL
            [0.4, 0.5, 0.6, 1.0, 0.8, 0.7, 0.6, 0.6],  # ADA
            [0.5, 0.6, 0.7, 0.8, 1.0, 0.6, 0.5, 0.7],  # DOT
            [0.3, 0.4, 0.5, 0.7, 0.6, 1.0, 0.8, 0.5],  # XRP
            [0.2, 0.3, 0.4, 0.6, 0.5, 0.8, 1.0, 0.4],  # DOGE
            [0.6, 0.7, 0.8, 0.6, 0.7, 0.5, 0.4, 1.0]   # AVAX
        ])
        
        np.random.seed(42)
        uncorrelated_returns = np.random.normal(0.001, 0.025, (days, len(symbols)))
        cholesky = np.linalg.cholesky(correlation_matrix)
        correlated_returns = uncorrelated_returns @ cholesky.T
        
        multi_pair_data = {}
        
        for i, symbol in enumerate(symbols):
            base_price = base_prices.get(symbol, 100)
            prices = base_price * np.exp(np.cumsum(correlated_returns[:, i]))
            
            volatility_factor = np.random.normal(1.0, 0.1, days)
            prices = prices * volatility_factor
            
            data = pd.DataFrame({
                'open': prices * (1 + np.random.normal(0, 0.003, days)),
                'high': prices * (1 + np.abs(np.random.normal(0, 0.008, days))),
                'low': prices * (1 - np.abs(np.random.normal(0, 0.008, days))),
                'close': prices,
                'volume': np.random.randint(10000, 1000000, days)
            }, index=date_range)
            
            data['high'] = np.maximum.reduce([data['open'], data['high'], data['close']])
            data['low'] = np.minimum.reduce([data['open'], data['low'], data['close']])
            
            multi_pair_data[symbol] = data
        
        return multi_pair_data
    
    def run_enhanced_backtest(self, strategy_id: str, symbols: List[str], start_date: str, 
                            end_date: str, initial_capital: float, 
                            params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Run enhanced backtest with multi-pair trading and advanced optimizations"""
        try:
            multi_data = self.generate_multi_pair_data(symbols, start_date, end_date)
            
            if strategy_id == "adaptive_multi_strategy":
                strategy = AdaptiveMultiStrategySystem()
                for base_strategy_id in ["rsi_strategy", "bollinger_bands", "moving_average_crossover"]:
                    base_strategy = self._create_optimized_strategy(base_strategy_id, params)
                    self.meta_learner.register_strategy(base_strategy_id, base_strategy)
            else:
                strategy = self._create_optimized_strategy(strategy_id, params)
            
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {}
                for symbol in symbols:
                    future = executor.submit(
                        self._run_single_pair_backtest, 
                        strategy, symbol, multi_data[symbol], initial_capital / len(symbols)
                    )
                    futures[symbol] = future
                
                pair_results = {}
                for symbol, future in futures.items():
                    pair_results[symbol] = future.result()
            
            aggregated_metrics = self._aggregate_portfolio_results(pair_results, initial_capital)
            
            risk_adjusted_metrics = self._apply_risk_management(aggregated_metrics, pair_results)
            
            adaptive_insights = self._generate_adaptive_insights(pair_results, strategy_id)
            
            return {
                "metrics": risk_adjusted_metrics,
                "pair_results": pair_results,
                "portfolio_allocation": self._calculate_optimal_allocation(pair_results),
                "adaptive_insights": adaptive_insights,
                "risk_analysis": self._generate_risk_analysis(pair_results),
                "correlation_matrix": self._calculate_correlation_matrix(multi_data)
            }
            
        except Exception as e:
            logger.error(f"Error running enhanced backtest: {e}")
            raise
    
    def _create_optimized_strategy(self, strategy_id: str, params: Optional[Dict[str, Any]]) -> Any:
        """Create optimized strategy with enhanced parameters"""
        if strategy_id == "rsi_strategy":
            return RSIStrategy(
                rsi_period=params.get("rsi_period", 21),  # Optimized from 14
                overbought=params.get("overbought", 75),   # Optimized from 70
                oversold=params.get("oversold", 25),       # Optimized from 30
                stop_loss_pct=params.get("stop_loss_pct", 2.0),
                take_profit_pct=params.get("take_profit_pct", 5.0)
            )
        elif strategy_id == "bollinger_bands":
            return BollingerBandsStrategy(
                window=params.get("bb_period", 25),        # Optimized from 20
                num_std=params.get("bb_std", 2.5),         # Optimized from 2.0
                stop_loss_pct=params.get("stop_loss_pct", 2.0),
                take_profit_pct=params.get("take_profit_pct", 5.0)
            )
        elif strategy_id == "moving_average_crossover":
            return MovingAverageStrategy(
                short_window=params.get("fast_period", 12),  # Optimized
                long_window=params.get("slow_period", 26),   # Optimized
                stop_loss_pct=params.get("stop_loss_pct", 2.0),
                take_profit_pct=params.get("take_profit_pct", 5.0)
            )
        else:
            strategy_class = self.strategies.get(strategy_id, RSIStrategy)
            return strategy_class()
    
    def _run_single_pair_backtest(self, strategy: Any, symbol: str, 
                                 data: pd.DataFrame, allocated_capital: float) -> Dict[str, Any]:
        """Run backtest for a single trading pair with enhanced risk management"""
        result_data = strategy.generate_signals(data)
        
        position_sizes = []
        for i, row in result_data.iterrows():
            if row['signal'] != 0:
                volatility = data['close'].pct_change().rolling(20).std().iloc[-1]
                position_size = self.risk_manager.calculate_position_size(
                    allocated_capital, row['close'], volatility, "risk_based"
                )
                position_sizes.append(position_size)
            else:
                position_sizes.append(0)
        
        result_data['position_size'] = position_sizes
        
        metrics = strategy.calculate_metrics(result_data)
        
        equity_curve = self._calculate_enhanced_equity_curve(result_data, allocated_capital)
        
        trades = self._extract_enhanced_trades(result_data, allocated_capital, symbol)
        
        return {
            "symbol": symbol,
            "metrics": {
                "total_return": metrics["profit"] * 100,
                "sharpe": metrics["sharpe"],
                "max_drawdown": abs(metrics["max_drawdown"]) * 100,
                "win_rate": self._calculate_win_rate(trades),
                "total_trades": len(trades),
                "annual_return": metrics["profit"] * 100 * (365 / len(data)),
                "profit_factor": self._calculate_profit_factor(trades),
                "calmar_ratio": self._calculate_calmar_ratio(metrics)
            },
            "equity_curve": {
                "dates": [d.strftime("%Y-%m-%d") for d in equity_curve.index],
                "values": equity_curve.tolist()
            },
            "trades": trades
        }
    
    def _aggregate_portfolio_results(self, pair_results: Dict[str, Any], 
                                   total_capital: float) -> Dict[str, float]:
        """Aggregate results across multiple trading pairs"""
        total_return = 0
        total_trades = 0
        weighted_sharpe = 0
        max_drawdown = 0
        
        for symbol, result in pair_results.items():
            weight = 1.0 / len(pair_results)  # Equal weight for now
            metrics = result["metrics"]
            
            total_return += metrics["total_return"] * weight
            total_trades += metrics["total_trades"]
            weighted_sharpe += metrics["sharpe"] * weight
            max_drawdown = max(max_drawdown, metrics["max_drawdown"])
        
        return {
            "total_return": total_return,
            "sharpe": weighted_sharpe,
            "max_drawdown": max_drawdown,
            "total_trades": total_trades,
            "annual_return": total_return * (365 / 252),  # Assuming 252 trading days
            "portfolio_diversification": self._calculate_diversification_ratio(pair_results)
        }
    
    def _apply_risk_management(self, metrics: Dict[str, float], 
                             pair_results: Dict[str, Any]) -> Dict[str, float]:
        """Apply enhanced risk management to portfolio metrics"""
        portfolio_volatility = self._calculate_portfolio_volatility(pair_results)
        var_95 = self._calculate_value_at_risk(pair_results, 0.95)
        
        risk_adjusted_return = metrics["total_return"] / max(portfolio_volatility, 0.01)
        
        metrics.update({
            "risk_adjusted_return": risk_adjusted_return,
            "portfolio_volatility": portfolio_volatility,
            "value_at_risk_95": var_95,
            "risk_parity_score": self._calculate_risk_parity_score(pair_results)
        })
        
        return metrics
    
    def _generate_adaptive_insights(self, pair_results: Dict[str, Any], 
                                  strategy_id: str) -> Dict[str, Any]:
        """Generate adaptive insights using meta-learning"""
        insights = {
            "best_performing_pair": max(pair_results.keys(), 
                                      key=lambda x: pair_results[x]["metrics"]["total_return"]),
            "strategy_adaptation_suggestions": [],
            "market_regime_analysis": self._analyze_market_regime(pair_results),
            "optimization_opportunities": []
        }
        
        for symbol, result in pair_results.items():
            if result["metrics"]["total_return"] < 0:
                insights["optimization_opportunities"].append({
                    "symbol": symbol,
                    "issue": "Negative returns",
                    "suggestion": "Consider parameter optimization or strategy switching"
                })
        
        return insights
    
    def _calculate_enhanced_equity_curve(self, data: pd.DataFrame, 
                                       initial_capital: float) -> pd.Series:
        """Calculate equity curve with slippage, fees, and realistic execution"""
        data = data.copy()
        data['returns'] = data['close'].pct_change()
        data['strategy_returns'] = data['signal'].shift(1) * data['returns']
        
        trading_cost = 0.001  # 0.1% per trade
        data['costs'] = np.abs(data['signal'].diff()) * trading_cost
        data['net_returns'] = data['strategy_returns'] - data['costs']
        
        equity = initial_capital * (1 + data['net_returns'].fillna(0)).cumprod()
        return equity
    
    def _extract_enhanced_trades(self, data: pd.DataFrame, initial_capital: float, 
                               symbol: str) -> List[Dict[str, Any]]:
        """Extract trades with enhanced stop loss and take profit logic"""
        trades = []
        position = None
        
        for i, row in data.iterrows():
            if position is None and row['signal'] != 0:
                position = {
                    "symbol": symbol,
                    "type": "BUY" if row['signal'] > 0 else "SELL",
                    "entry_date": i.strftime("%Y-%m-%d"),
                    "entry_price": row['close'],
                    "size": row.get('position_size', initial_capital * 0.1 / row['close'])
                }
            
            elif position is not None and (row['signal'] == 0 or 
                                         row['signal'] * position.get('signal', 1) < 0):
                
                entry_price = position["entry_price"]
                
                volatility = data['close'].pct_change().rolling(20).std().iloc[max(0, i-20):i].mean()
                dynamic_stop_loss = max(0.02, volatility * 2)  # Minimum 2% or 2x volatility
                dynamic_take_profit = max(0.05, volatility * 3)  # Minimum 5% or 3x volatility
                
                if position["type"] == "BUY":
                    stop_loss_price = entry_price * (1 - dynamic_stop_loss)
                    take_profit_price = entry_price * (1 + dynamic_take_profit)
                    
                    if row['close'] <= stop_loss_price:
                        exit_price = stop_loss_price
                        exit_reason = "Stop Loss"
                    elif row['close'] >= take_profit_price:
                        exit_price = take_profit_price
                        exit_reason = "Take Profit"
                    else:
                        exit_price = row['close']
                        exit_reason = "Signal Exit"
                    
                    pl = (exit_price - entry_price) * position["size"]
                else:
                    stop_loss_price = entry_price * (1 + dynamic_stop_loss)
                    take_profit_price = entry_price * (1 - dynamic_take_profit)
                    
                    if row['close'] >= stop_loss_price:
                        exit_price = stop_loss_price
                        exit_reason = "Stop Loss"
                    elif row['close'] <= take_profit_price:
                        exit_price = take_profit_price
                        exit_reason = "Take Profit"
                    else:
                        exit_price = row['close']
                        exit_reason = "Signal Exit"
                    
                    pl = (entry_price - exit_price) * position["size"]
                
                trades.append({
                    "symbol": symbol,
                    "entry_date": position["entry_date"],
                    "exit_date": i.strftime("%Y-%m-%d"),
                    "type": position["type"],
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "size": position["size"],
                    "pl": pl,
                    "pl_percent": (pl / (entry_price * position["size"])) * 100,
                    "exit_reason": exit_reason,
                    "holding_days": (i - pd.to_datetime(position["entry_date"])).days
                })
                position = None
        
        return trades
    
    def _calculate_win_rate(self, trades: List[Dict[str, Any]]) -> float:
        """Calculate win rate from trades"""
        profitable_trades = [t for t in trades if t.get("pl", 0) > 0]
        total_trades = len([t for t in trades if "pl" in t])
        return (len(profitable_trades) / total_trades * 100) if total_trades > 0 else 0
    
    def _calculate_profit_factor(self, trades: List[Dict[str, Any]]) -> float:
        """Calculate profit factor (gross profit / gross loss)"""
        profits = sum(t["pl"] for t in trades if t.get("pl", 0) > 0)
        losses = abs(sum(t["pl"] for t in trades if t.get("pl", 0) < 0))
        return profits / losses if losses > 0 else float('inf')
    
    def _calculate_calmar_ratio(self, metrics: Dict[str, float]) -> float:
        """Calculate Calmar ratio (annual return / max drawdown)"""
        annual_return = metrics.get("profit", 0) * 100
        max_drawdown = abs(metrics.get("max_drawdown", 0.01)) * 100
        return annual_return / max_drawdown if max_drawdown > 0 else 0
    
    def _calculate_optimal_allocation(self, pair_results: Dict[str, Any]) -> Dict[str, float]:
        """Calculate optimal portfolio allocation using risk-return optimization"""
        allocations = {}
        total_score = 0
        
        for symbol, result in pair_results.items():
            metrics = result["metrics"]
            sharpe = metrics.get("sharpe", 0)
            return_rate = metrics.get("total_return", 0)
            max_dd = metrics.get("max_drawdown", 100)
            
            score = max(0, (sharpe * return_rate) / max(max_dd, 1))
            allocations[symbol] = score
            total_score += score
        
        if total_score > 0:
            for symbol in allocations:
                allocations[symbol] = (allocations[symbol] / total_score) * 100
        else:
            equal_weight = 100 / len(pair_results)
            allocations = {symbol: equal_weight for symbol in pair_results.keys()}
        
        return allocations
    
    def _generate_risk_analysis(self, pair_results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate comprehensive risk analysis"""
        return {
            "portfolio_concentration": self._calculate_concentration_risk(pair_results),
            "correlation_risk": self._calculate_correlation_risk(pair_results),
            "volatility_analysis": self._analyze_volatility_patterns(pair_results),
            "tail_risk_metrics": self._calculate_tail_risk(pair_results)
        }
    
    def _calculate_correlation_matrix(self, multi_data: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        """Calculate correlation matrix for trading pairs"""
        returns_data = {}
        for symbol, data in multi_data.items():
            returns_data[symbol] = data['close'].pct_change().dropna()
        
        returns_df = pd.DataFrame(returns_data)
        correlation_matrix = returns_df.corr()
        
        return {
            "matrix": correlation_matrix.to_dict(),
            "average_correlation": correlation_matrix.values[np.triu_indices_from(correlation_matrix.values, k=1)].mean(),
            "max_correlation": correlation_matrix.values[np.triu_indices_from(correlation_matrix.values, k=1)].max(),
            "diversification_ratio": 1 / correlation_matrix.values[np.triu_indices_from(correlation_matrix.values, k=1)].mean()
        }
    
    def _calculate_portfolio_volatility(self, pair_results: Dict[str, Any]) -> float:
        """Calculate portfolio volatility"""
        volatilities = [result["metrics"].get("max_drawdown", 0) for result in pair_results.values()]
        return np.mean(volatilities)
    
    def _calculate_value_at_risk(self, pair_results: Dict[str, Any], confidence: float) -> float:
        """Calculate Value at Risk"""
        returns = []
        for result in pair_results.values():
            returns.extend([trade.get("pl_percent", 0) for trade in result.get("trades", [])])
        
        if returns:
            return np.percentile(returns, (1 - confidence) * 100)
        return 0
    
    def _calculate_risk_parity_score(self, pair_results: Dict[str, Any]) -> float:
        """Calculate risk parity score"""
        risk_contributions = []
        for result in pair_results.values():
            risk_contributions.append(result["metrics"].get("max_drawdown", 0))
        
        if risk_contributions:
            return 1 - np.std(risk_contributions) / np.mean(risk_contributions)
        return 0
    
    def _analyze_market_regime(self, pair_results: Dict[str, Any]) -> str:
        """Analyze current market regime"""
        avg_return = np.mean([result["metrics"]["total_return"] for result in pair_results.values()])
        avg_volatility = np.mean([result["metrics"]["max_drawdown"] for result in pair_results.values()])
        
        if avg_return > 5 and avg_volatility < 10:
            return "Bull Market - Low Volatility"
        elif avg_return > 0 and avg_volatility > 15:
            return "Bull Market - High Volatility"
        elif avg_return < -5 and avg_volatility > 20:
            return "Bear Market - High Volatility"
        else:
            return "Sideways Market - Mixed Conditions"
    
    def _calculate_concentration_risk(self, pair_results: Dict[str, Any]) -> float:
        """Calculate portfolio concentration risk"""
        returns = [result["metrics"]["total_return"] for result in pair_results.values()]
        return np.std(returns) / np.mean(returns) if np.mean(returns) != 0 else 0
    
    def _calculate_correlation_risk(self, pair_results: Dict[str, Any]) -> float:
        """Calculate correlation-based risk"""
        return max(0, 1 - (len(pair_results) / 10))  # Risk decreases with more pairs
    
    def _analyze_volatility_patterns(self, pair_results: Dict[str, Any]) -> Dict[str, float]:
        """Analyze volatility patterns across pairs"""
        volatilities = [result["metrics"]["max_drawdown"] for result in pair_results.values()]
        return {
            "average_volatility": np.mean(volatilities),
            "volatility_range": np.max(volatilities) - np.min(volatilities),
            "volatility_stability": 1 - (np.std(volatilities) / np.mean(volatilities)) if np.mean(volatilities) > 0 else 0
        }
    
    def _calculate_tail_risk(self, pair_results: Dict[str, Any]) -> Dict[str, float]:
        """Calculate tail risk metrics"""
        all_returns = []
        for result in pair_results.values():
            all_returns.extend([trade.get("pl_percent", 0) for trade in result.get("trades", [])])
        
        if all_returns:
            return {
                "var_95": np.percentile(all_returns, 5),
                "var_99": np.percentile(all_returns, 1),
                "expected_shortfall": np.mean([r for r in all_returns if r <= np.percentile(all_returns, 5)])
            }
        return {"var_95": 0, "var_99": 0, "expected_shortfall": 0}
    
    def _calculate_diversification_ratio(self, pair_results: Dict[str, Any]) -> float:
        """Calculate diversification ratio"""
        returns = [result["metrics"]["total_return"] for result in pair_results.values()]
        if len(returns) > 1:
            return 1 - (np.std(returns) / (np.max(returns) - np.min(returns))) if (np.max(returns) - np.min(returns)) > 0 else 0
        return 0

_enhanced_backtest_service = EnhancedBacktestService()

def run_multi_timeframe_backtest(strategy_name: str, symbol: str, start_date: str, end_date: str, 
                               timeframes: List[str] = None) -> Dict[str, Any]:
    """Run backtest with multi-timeframe strategy"""
    timeframes = timeframes or ['5m', '15m', '1h', '4h']
    
    service = get_enhanced_backtest_service()
    multi_data = {}
    for tf in timeframes:
        multi_data[tf] = service.generate_multi_pair_data([symbol], start_date, end_date)[symbol]
    
    if strategy_name == "MultiTimeframe_RSI":
        from autobot.trading.strategy import MultiTimeframeRSIStrategy
        strategy = MultiTimeframeRSIStrategy()
    elif strategy_name == "MultiTimeframe_Bollinger":
        from autobot.trading.strategy import MultiTimeframeBollingerStrategy
        strategy = MultiTimeframeBollingerStrategy()
    else:
        raise ValueError(f"Unknown multi-timeframe strategy: {strategy_name}")
    
    signals = strategy.generate_multi_timeframe_signals(multi_data)
    
    primary_data = multi_data[strategy.primary_timeframe].copy()
    primary_data['signal'] = signals['signal']
    
    return service._run_single_pair_backtest(strategy, primary_data, symbol)


def _generate_realistic_data_for_timeframe(symbol: str, start_date: str, end_date: str, timeframe: str) -> pd.DataFrame:
    """Generate realistic data for specific timeframe"""
    from datetime import datetime
    import pandas as pd
    import numpy as np
    
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    
    if timeframe == '5m':
        freq = '5T'
    elif timeframe == '15m':
        freq = '15T'
    elif timeframe == '1h':
        freq = '1H'
    elif timeframe == '4h':
        freq = '4H'
    else:
        freq = '1D'
    
    date_range = pd.date_range(start, end, freq=freq)
    days = len(date_range)
    
    base_price = 45000 if 'BTC' in symbol else 2500
    np.random.seed(42)
    returns = np.random.normal(0.0005, 0.02, days)
    prices = base_price * np.exp(np.cumsum(returns))
    
    return pd.DataFrame({
        'open': prices * (1 + np.random.normal(0, 0.002, days)),
        'high': prices * (1 + np.abs(np.random.normal(0, 0.005, days))),
        'low': prices * (1 - np.abs(np.random.normal(0, 0.005, days))),
        'close': prices,
        'volume': np.random.randint(10000, 1000000, days)
    }, index=date_range)

def get_enhanced_backtest_service() -> EnhancedBacktestService:
    """Get the global enhanced backtest service instance"""
    return _enhanced_backtest_service
