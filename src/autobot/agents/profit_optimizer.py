"""
Profit Optimizer for AUTOBOT.
Provides advanced optimization strategies for maximizing trading and e-commerce profits.
"""
import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional, Union, Callable, Tuple
from datetime import datetime, timedelta
import json
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor

from ..trading.prediction_strategy import get_strategy_manager
from ..prediction.engine import create_prediction_engine
from ..ecommerce.pricing_optimizer import PricingOptimizer
from .orchestrator import AgentOrchestrator

logger = logging.getLogger(__name__)

class ProfitOptimizer:
    """
    Advanced profit optimization system that coordinates trading and e-commerce strategies.
    Uses machine learning to dynamically allocate resources and optimize profit generation.
    """
    
    def __init__(
        self,
        config: Dict[str, Any] = None,
        trading_allocation: float = 0.7,
        ecommerce_allocation: float = 0.3,
        rebalance_interval: int = 24,  # hours
        risk_tolerance: float = 0.5,
        max_drawdown: float = 0.15,
        reinvestment_ratio: float = 0.8
    ):
        """
        Initialize the profit optimizer.
        
        Args:
            config: Configuration dictionary
            trading_allocation: Initial allocation to trading (0-1)
            ecommerce_allocation: Initial allocation to e-commerce (0-1)
            rebalance_interval: Hours between portfolio rebalancing
            risk_tolerance: Risk tolerance (0-1)
            max_drawdown: Maximum allowed drawdown before intervention
            reinvestment_ratio: Ratio of profits to reinvest
        """
        self.config = config or {}
        self.trading_allocation = trading_allocation
        self.ecommerce_allocation = ecommerce_allocation
        self.rebalance_interval = rebalance_interval
        self.risk_tolerance = risk_tolerance
        self.max_drawdown = max_drawdown
        self.reinvestment_ratio = reinvestment_ratio
        
        self.strategy_manager = get_strategy_manager()
        self.pricing_optimizer = PricingOptimizer()
        self.agent_orchestrator = AgentOrchestrator()
        
        self.prediction_engine = create_prediction_engine({
            "model_name": "profit_optimizer",
            "model_type": "EnsembleModel"
        })
        
        self.performance_history = {
            "trading": [],
            "ecommerce": [],
            "total": []
        }
        
        self.last_rebalance = datetime.now()
        self.initial_capital = self.config.get("initial_capital", 1000.0)
        self.current_capital = self.initial_capital
        
        self.is_running = False
        self.executor = ThreadPoolExecutor(max_workers=5)
    
    async def start(self):
        """Start the profit optimizer."""
        if self.is_running:
            logger.warning("Profit optimizer is already running")
            return
        
        logger.info("Starting profit optimizer")
        self.is_running = True
        
        await self.agent_orchestrator.start()
        
        asyncio.create_task(self._optimization_loop())
    
    async def stop(self):
        """Stop the profit optimizer."""
        if not self.is_running:
            logger.warning("Profit optimizer is not running")
            return
        
        logger.info("Stopping profit optimizer")
        self.is_running = False
        
        await self.agent_orchestrator.stop()
    
    async def _optimization_loop(self):
        """Main optimization loop."""
        while self.is_running:
            try:
                now = datetime.now()
                hours_since_rebalance = (now - self.last_rebalance).total_seconds() / 3600
                
                if hours_since_rebalance >= self.rebalance_interval:
                    await self._rebalance_portfolio()
                    self.last_rebalance = now
                
                if self._check_drawdown():
                    await self._risk_intervention()
                
                await self._update_performance()
                
                await self._optimize_trading()
                
                await self._optimize_ecommerce()
                
                await self._reinvest_profits()
                
                await asyncio.sleep(60 * 15)  # 15 minutes
            
            except Exception as e:
                logger.error(f"Error in optimization loop: {str(e)}")
                await asyncio.sleep(60)  # Sleep for 1 minute before retrying
    
    async def _rebalance_portfolio(self):
        """Rebalance the portfolio allocation between trading and e-commerce."""
        logger.info("Rebalancing portfolio")
        
        trading_performance = self._get_average_performance("trading", 30)  # Last 30 days
        ecommerce_performance = self._get_average_performance("ecommerce", 30)
        
        if trading_performance is None or ecommerce_performance is None:
            logger.info("Not enough performance data for rebalancing")
            return
        
        total_performance = trading_performance + ecommerce_performance
        
        if total_performance > 0:
            new_trading_allocation = trading_performance / total_performance
            new_ecommerce_allocation = ecommerce_performance / total_performance
            
            if self.risk_tolerance > 0.5:
                better_performer = "trading" if trading_performance > ecommerce_performance else "ecommerce"
                risk_factor = (self.risk_tolerance - 0.5) * 2  # 0-1 range
                
                if better_performer == "trading":
                    new_trading_allocation += (new_ecommerce_allocation * risk_factor * 0.5)
                    new_ecommerce_allocation -= (new_ecommerce_allocation * risk_factor * 0.5)
                else:
                    new_ecommerce_allocation += (new_trading_allocation * risk_factor * 0.5)
                    new_trading_allocation -= (new_trading_allocation * risk_factor * 0.5)
            
            new_trading_allocation = max(0.1, min(0.9, new_trading_allocation))
            new_ecommerce_allocation = 1.0 - new_trading_allocation
            
            logger.info(f"New allocation: Trading={new_trading_allocation:.2f}, E-commerce={new_ecommerce_allocation:.2f}")
            
            self.trading_allocation = new_trading_allocation
            self.ecommerce_allocation = new_ecommerce_allocation
            
            await self._apply_allocation()
    
    async def _apply_allocation(self):
        """Apply the current allocation to the system."""
        trading_capital = self.current_capital * self.trading_allocation
        
        ecommerce_capital = self.current_capital * self.ecommerce_allocation
        
        await self.agent_orchestrator.configure({
            "trading_allocation": self.trading_allocation,
            "ecommerce_allocation": self.ecommerce_allocation,
            "trading_capital": trading_capital,
            "ecommerce_capital": ecommerce_capital
        })
    
    def _check_drawdown(self) -> bool:
        """
        Check if the current drawdown exceeds the maximum allowed.
        
        Returns:
            True if drawdown exceeds maximum, False otherwise
        """
        if not self.performance_history["total"]:
            return False
        
        peak = max(self.performance_history["total"])
        current = self.performance_history["total"][-1]
        
        if peak == 0:
            return False
        
        drawdown = (peak - current) / peak
        
        return drawdown > self.max_drawdown
    
    async def _risk_intervention(self):
        """Intervene to reduce risk when drawdown exceeds maximum."""
        logger.warning(f"Maximum drawdown exceeded. Implementing risk intervention.")
        
        await self._reduce_trading_risk()
        
        await self._adjust_ecommerce_pricing()
        
        self.reinvestment_ratio *= 0.5
        
        asyncio.create_task(self._restore_normal_operations())
    
    async def _restore_normal_operations(self):
        """Restore normal operations after risk intervention."""
        await asyncio.sleep(60 * 60 * 24)
        
        self.reinvestment_ratio = self.config.get("reinvestment_ratio", 0.8)
        
        logger.info("Restored normal operations after risk intervention")
    
    async def _reduce_trading_risk(self):
        """Reduce risk in trading strategies."""
        conservative_strategy = self.strategy_manager.get_strategy("MovingAverageStrategy")
        if conservative_strategy:
            self.strategy_manager.set_active_strategy("MovingAverageStrategy")
        
        pass
    
    async def _adjust_ecommerce_pricing(self):
        """Adjust e-commerce pricing to be more conservative."""
        self.pricing_optimizer.set_mode("conservative")
    
    async def _update_performance(self):
        """Update performance metrics."""
        trading_performance = await self._get_trading_performance()
        
        ecommerce_performance = await self._get_ecommerce_performance()
        
        total_performance = (trading_performance * self.trading_allocation + 
                            ecommerce_performance * self.ecommerce_allocation)
        
        self.performance_history["trading"].append(trading_performance)
        self.performance_history["ecommerce"].append(ecommerce_performance)
        self.performance_history["total"].append(total_performance)
        
        max_history = 365
        if len(self.performance_history["trading"]) > max_history:
            self.performance_history["trading"] = self.performance_history["trading"][-max_history:]
            self.performance_history["ecommerce"] = self.performance_history["ecommerce"][-max_history:]
            self.performance_history["total"] = self.performance_history["total"][-max_history:]
        
        self.current_capital = self.initial_capital * (1 + total_performance)
    
    def _get_average_performance(self, category: str, days: int) -> Optional[float]:
        """
        Get average performance for a category over the specified number of days.
        
        Args:
            category: Performance category (trading, ecommerce, total)
            days: Number of days to average
            
        Returns:
            Average performance or None if not enough data
        """
        if category not in self.performance_history:
            return None
        
        history = self.performance_history[category]
        
        if len(history) < days:
            return None
        
        return sum(history[-days:]) / days
    
    async def _get_trading_performance(self) -> float:
        """
        Get current trading performance.
        
        Returns:
            Trading performance as a ratio
        """
        return 0.01  # 1% daily return
    
    async def _get_ecommerce_performance(self) -> float:
        """
        Get current e-commerce performance.
        
        Returns:
            E-commerce performance as a ratio
        """
        return 0.005  # 0.5% daily return
    
    async def _optimize_trading(self):
        """Optimize trading strategies."""
        market_data = await self._get_market_data()
        
        if market_data is None or market_data.empty:
            logger.warning("No market data available for trading optimization")
            return
        
        best_strategy = self.strategy_manager.get_best_strategy(market_data)
        
        if best_strategy:
            logger.info(f"Setting active strategy to {best_strategy}")
            self.strategy_manager.set_active_strategy(best_strategy)
        
        try:
            self.prediction_engine.train(market_data)
            logger.info("Trained prediction models with latest market data")
        except Exception as e:
            logger.error(f"Error training prediction models: {str(e)}")
    
    async def _get_market_data(self) -> Optional[pd.DataFrame]:
        """
        Get market data for optimization.
        
        Returns:
            Market data DataFrame or None if not available
        """
        return None
    
    async def _optimize_ecommerce(self):
        """Optimize e-commerce strategies."""
        inventory_data = await self._get_inventory_data()
        
        if inventory_data is None:
            logger.warning("No inventory data available for e-commerce optimization")
            return
        
        try:
            self.pricing_optimizer.optimize(inventory_data)
            logger.info("Optimized e-commerce pricing")
        except Exception as e:
            logger.error(f"Error optimizing e-commerce pricing: {str(e)}")
    
    async def _get_inventory_data(self) -> Optional[Dict[str, Any]]:
        """
        Get inventory data for optimization.
        
        Returns:
            Inventory data dictionary or None if not available
        """
        return None
    
    async def _reinvest_profits(self):
        """Reinvest profits according to the reinvestment ratio."""
        profits = self.current_capital - self.initial_capital
        
        if profits <= 0:
            return
        
        reinvestment = profits * self.reinvestment_ratio
        
        self.initial_capital += reinvestment
        
        trading_reinvestment = reinvestment * self.trading_allocation
        ecommerce_reinvestment = reinvestment * self.ecommerce_allocation
        
        logger.info(f"Reinvesting profits: Trading=${trading_reinvestment:.2f}, E-commerce=${ecommerce_reinvestment:.2f}")
        
        await self._apply_allocation()
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Get performance metrics.
        
        Returns:
            Dictionary of performance metrics
        """
        if not self.performance_history["total"]:
            return {
                "current_capital": self.current_capital,
                "initial_capital": self.initial_capital,
                "profit": 0,
                "roi": 0,
                "trading_allocation": self.trading_allocation,
                "ecommerce_allocation": self.ecommerce_allocation
            }
        
        current_performance = self.performance_history["total"][-1]
        profit = self.current_capital - self.initial_capital
        roi = profit / self.initial_capital
        
        if len(self.performance_history["total"]) >= 30:
            daily_returns = self.performance_history["total"][-30:]
            avg_daily_return = sum(daily_returns) / len(daily_returns)
            annualized_return = ((1 + avg_daily_return) ** 365) - 1
        else:
            avg_daily_return = 0
            annualized_return = 0
        
        peak = max(self.performance_history["total"])
        current = self.performance_history["total"][-1]
        drawdown = (peak - current) / peak if peak > 0 else 0
        
        return {
            "current_capital": self.current_capital,
            "initial_capital": self.initial_capital,
            "profit": profit,
            "roi": roi,
            "avg_daily_return": avg_daily_return,
            "annualized_return": annualized_return,
            "drawdown": drawdown,
            "trading_allocation": self.trading_allocation,
            "ecommerce_allocation": self.ecommerce_allocation
        }
    
    def save_state(self, path: str) -> str:
        """
        Save the optimizer state to a file.
        
        Args:
            path: Path to save the state
            
        Returns:
            Full path to the saved state
        """
        state = {
            "trading_allocation": self.trading_allocation,
            "ecommerce_allocation": self.ecommerce_allocation,
            "rebalance_interval": self.rebalance_interval,
            "risk_tolerance": self.risk_tolerance,
            "max_drawdown": self.max_drawdown,
            "reinvestment_ratio": self.reinvestment_ratio,
            "initial_capital": self.initial_capital,
            "current_capital": self.current_capital,
            "performance_history": self.performance_history,
            "last_rebalance": self.last_rebalance.isoformat()
        }
        
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        with open(path, 'w') as f:
            json.dump(state, f, indent=4)
        
        logger.info(f"Saved optimizer state to {path}")
        
        return path
    
    @classmethod
    def load_state(cls, path: str) -> 'ProfitOptimizer':
        """
        Load optimizer state from a file.
        
        Args:
            path: Path to the state file
            
        Returns:
            ProfitOptimizer instance
        """
        with open(path, 'r') as f:
            state = json.load(f)
        
        optimizer = cls(
            trading_allocation=state["trading_allocation"],
            ecommerce_allocation=state["ecommerce_allocation"],
            rebalance_interval=state["rebalance_interval"],
            risk_tolerance=state["risk_tolerance"],
            max_drawdown=state["max_drawdown"],
            reinvestment_ratio=state["reinvestment_ratio"]
        )
        
        optimizer.initial_capital = state["initial_capital"]
        optimizer.current_capital = state["current_capital"]
        optimizer.performance_history = state["performance_history"]
        optimizer.last_rebalance = datetime.fromisoformat(state["last_rebalance"])
        
        logger.info(f"Loaded optimizer state from {path}")
        
        return optimizer

_profit_optimizer = None

async def get_profit_optimizer(config: Dict[str, Any] = None) -> ProfitOptimizer:
    """
    Get the global profit optimizer instance.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        ProfitOptimizer instance
    """
    global _profit_optimizer
    
    if _profit_optimizer is None:
        _profit_optimizer = ProfitOptimizer(config)
    
    return _profit_optimizer
