"""
Meta-learning module for AUTOBOT.

This module provides advanced meta-learning capabilities for AUTOBOT's
reinforcement learning system, enabling it to adapt to changing market
conditions and optimize trading strategies in real-time.
"""

import time
import logging
import threading
import json
import os
import random
import numpy as np
from typing import Dict, List, Any, Optional, Tuple, Callable, Union
from datetime import datetime, timedelta
from collections import deque

logger = logging.getLogger(__name__)

_meta_learning_active = False

class MetaLearner:
    """
    Meta-learning system for AUTOBOT.
    
    This class provides advanced meta-learning capabilities for AUTOBOT's
    reinforcement learning system, enabling it to adapt to changing market
    conditions and optimize trading strategies in real-time.
    """
    
    def __init__(
        self,
        strategy_pool_size: int = 5,
        adaptation_interval: float = 3600.0,
        exploration_rate: float = 0.1,
        learning_rate: float = 0.01,
        performance_window: int = 100,
        auto_adapt: bool = True,
        visible_interface: bool = True
    ):
        """
        Initialize the meta-learner.
        
        Args:
            strategy_pool_size: Number of strategies to maintain in the pool
            adaptation_interval: Interval in seconds between adaptations
            exploration_rate: Rate of exploration for new strategies
            learning_rate: Learning rate for strategy updates
            performance_window: Window size for performance tracking
            auto_adapt: Whether to automatically adapt strategies
            visible_interface: Whether to show adaptation messages in the interface
        """
        self.strategy_pool_size = strategy_pool_size
        self.adaptation_interval = adaptation_interval
        self.exploration_rate = exploration_rate
        self.learning_rate = learning_rate
        self.performance_window = performance_window
        self.auto_adapt = auto_adapt
        self.visible_interface = visible_interface
        
        self._strategy_pool = {}
        self._strategy_performance = {}
        self._market_conditions = {}
        self._adaptation_history = []
        self._monitoring_thread = None
        self._lock = threading.Lock()
        
        self._initialize_strategy_pool()
        
        if auto_adapt:
            self.start_adaptation()
    
    def _initialize_strategy_pool(self) -> None:
        """Initialize the strategy pool with default strategies."""
        default_strategies = [
            {
                "name": "momentum",
                "params": {
                    "window_size": 20,
                    "threshold": 0.02,
                    "stop_loss": 0.05,
                    "take_profit": 0.1
                }
            },
            {
                "name": "mean_reversion",
                "params": {
                    "window_size": 50,
                    "std_dev": 2.0,
                    "max_holding_time": 24
                }
            },
            {
                "name": "breakout",
                "params": {
                    "window_size": 100,
                    "threshold": 0.03,
                    "confirmation_candles": 3
                }
            },
            {
                "name": "trend_following",
                "params": {
                    "fast_period": 10,
                    "slow_period": 50,
                    "signal_period": 9
                }
            },
            {
                "name": "grid_trading",
                "params": {
                    "grid_levels": 10,
                    "grid_spacing": 0.01,
                    "total_investment": 1.0
                }
            }
        ]
        
        for strategy in default_strategies:
            self.register_strategy(
                strategy["name"],
                strategy["params"],
                initial_weight=1.0 / len(default_strategies)
            )
    
    def register_strategy(
        self,
        name: str,
        params: Dict[str, Any],
        initial_weight: float = 0.1
    ) -> None:
        """
        Register a new strategy in the pool.
        
        Args:
            name: Name of the strategy
            params: Parameters of the strategy
            initial_weight: Initial weight of the strategy
        """
        with self._lock:
            strategy_id = f"{name}_{int(time.time())}"
            
            self._strategy_pool[strategy_id] = {
                "name": name,
                "params": params.copy(),
                "weight": initial_weight,
                "created_at": time.time(),
                "updated_at": time.time(),
                "generation": 1
            }
            
            self._strategy_performance[strategy_id] = {
                "returns": deque(maxlen=self.performance_window),
                "sharpe": deque(maxlen=self.performance_window),
                "drawdown": deque(maxlen=self.performance_window),
                "win_rate": deque(maxlen=self.performance_window),
                "last_updated": 0
            }
            
            if self.visible_interface:
                logger.info(f"Registered strategy: {name} (ID: {strategy_id})")
            else:
                logger.debug(f"Registered strategy: {name} (ID: {strategy_id})")
            
            self._normalize_weights()
    
    def _normalize_weights(self) -> None:
        """Normalize strategy weights to sum to 1.0."""
        total_weight = sum(strategy["weight"] for strategy in self._strategy_pool.values())
        
        if total_weight > 0:
            for strategy_id in self._strategy_pool:
                self._strategy_pool[strategy_id]["weight"] /= total_weight
    
    def start_adaptation(self) -> None:
        """Start the adaptation thread."""
        global _meta_learning_active
        
        if _meta_learning_active:
            return
            
        _meta_learning_active = True
        
        if self._monitoring_thread is None or not self._monitoring_thread.is_alive():
            self._monitoring_thread = threading.Thread(
                target=self._adaptation_loop,
                daemon=True
            )
            self._monitoring_thread.start()
            
            if self.visible_interface:
                logger.info("Started meta-learning adaptation")
            else:
                logger.debug("Started meta-learning adaptation")
    
    def stop_adaptation(self) -> None:
        """Stop the adaptation thread."""
        global _meta_learning_active
        _meta_learning_active = False
        
        if self.visible_interface:
            logger.info("Stopped meta-learning adaptation")
        else:
            logger.debug("Stopped meta-learning adaptation")
    
    def _adaptation_loop(self) -> None:
        """Background loop for adapting strategies."""
        global _meta_learning_active
        
        while _meta_learning_active:
            try:
                time.sleep(10)
                
                current_time = time.time()
                last_adaptation = self._get_last_adaptation_time()
                
                if current_time - last_adaptation >= self.adaptation_interval:
                    self._adapt_strategies()
                
            except Exception as e:
                logger.error(f"Error in meta-learning adaptation: {str(e)}")
                time.sleep(60)  # Sleep longer on error
    
    def _get_last_adaptation_time(self) -> float:
        """
        Get the time of the last adaptation.
        
        Returns:
            float: Time of the last adaptation
        """
        if not self._adaptation_history:
            return 0
        
        return self._adaptation_history[-1]["timestamp"]
    
    def _adapt_strategies(self) -> None:
        """Adapt strategies based on performance."""
        with self._lock:
            if not any(perf["returns"] for perf in self._strategy_performance.values()):
                return
            
            market_conditions = self._get_market_conditions()
            
            self._update_strategy_weights()
            
            self._generate_new_strategies()
            
            self._prune_strategies()
            
            self._adaptation_history.append({
                "timestamp": time.time(),
                "market_conditions": market_conditions,
                "strategies": {
                    strategy_id: {
                        "name": strategy["name"],
                        "weight": strategy["weight"],
                        "generation": strategy["generation"]
                    }
                    for strategy_id, strategy in self._strategy_pool.items()
                }
            })
            
            if self.visible_interface:
                logger.info("Adapted strategies based on performance")
            else:
                logger.debug("Adapted strategies based on performance")
    
    def _get_market_conditions(self) -> Dict[str, Any]:
        """
        Get current market conditions.
        
        Returns:
            Dict: Current market conditions
        """
        return {
            "volatility": random.uniform(0.01, 0.05),
            "trend": random.uniform(-1.0, 1.0),
            "volume": random.uniform(0.5, 2.0),
            "timestamp": time.time()
        }
    
    def _update_strategy_weights(self) -> None:
        """Update strategy weights based on performance."""
        scores = {}
        
        for strategy_id, performance in self._strategy_performance.items():
            if strategy_id not in self._strategy_pool:
                continue
                
            if not performance["returns"]:
                scores[strategy_id] = 0
                continue
            
            avg_return = np.mean(performance["returns"])
            avg_sharpe = np.mean(performance["sharpe"]) if performance["sharpe"] else 0
            avg_drawdown = np.mean(performance["drawdown"]) if performance["drawdown"] else 0
            avg_win_rate = np.mean(performance["win_rate"]) if performance["win_rate"] else 0
            
            score = (
                avg_return * 0.4 +
                avg_sharpe * 0.3 +
                (1.0 - avg_drawdown) * 0.2 +
                avg_win_rate * 0.1
            )
            
            scores[strategy_id] = max(0, score)  # Ensure non-negative
        
        total_score = sum(scores.values())
        
        if total_score > 0:
            for strategy_id, score in scores.items():
                old_weight = self._strategy_pool[strategy_id]["weight"]
                new_weight = score / total_score
                
                self._strategy_pool[strategy_id]["weight"] = (
                    old_weight * (1 - self.learning_rate) +
                    new_weight * self.learning_rate
                )
                
                self._strategy_pool[strategy_id]["updated_at"] = time.time()
        
        self._normalize_weights()
    
    def _generate_new_strategies(self) -> None:
        """Generate new strategies through mutation and crossover."""
        if len(self._strategy_pool) >= self.strategy_pool_size * 2:
            return
        
        if random.random() > self.exploration_rate:
            return
        
        sorted_strategies = sorted(
            self._strategy_pool.items(),
            key=lambda x: x[1]["weight"],
            reverse=True
        )
        
        if len(sorted_strategies) < 2:
            return
        
        parent1 = sorted_strategies[0][1]
        parent2 = sorted_strategies[1][1]
        
        child_name = parent1["name"]
        child_params = {}
        
        for param in set(parent1["params"].keys()) | set(parent2["params"].keys()):
            if param in parent1["params"] and param in parent2["params"]:
                if isinstance(parent1["params"][param], (int, float)) and isinstance(parent2["params"][param], (int, float)):
                    weight1 = parent1["weight"] / (parent1["weight"] + parent2["weight"])
                    child_params[param] = (
                        parent1["params"][param] * weight1 +
                        parent2["params"][param] * (1 - weight1)
                    )
                    
                    if isinstance(parent1["params"][param], int) and isinstance(parent2["params"][param], int):
                        child_params[param] = int(round(child_params[param]))
                else:
                    child_params[param] = random.choice([parent1["params"][param], parent2["params"][param]])
            elif param in parent1["params"]:
                child_params[param] = parent1["params"][param]
            else:
                child_params[param] = parent2["params"][param]
        
        for param in child_params:
            if isinstance(child_params[param], (int, float)):
                if random.random() < 0.3:  # 30% chance of mutation
                    mutation_factor = random.uniform(0.8, 1.2)  # ±20%
                    child_params[param] *= mutation_factor
                    
                    if isinstance(child_params[param], int):
                        child_params[param] = int(round(child_params[param]))
        
        generation = max(parent1["generation"], parent2["generation"]) + 1
        child_name = f"{child_name}_gen{generation}"
        
        self.register_strategy(
            child_name,
            child_params,
            initial_weight=0.05  # Start with a small weight
        )
        
        if self.visible_interface:
            logger.info(f"Generated new strategy: {child_name}")
        else:
            logger.debug(f"Generated new strategy: {child_name}")
    
    def _prune_strategies(self) -> None:
        """Prune underperforming strategies."""
        if len(self._strategy_pool) <= self.strategy_pool_size:
            return
        
        sorted_strategies = sorted(
            self._strategy_pool.items(),
            key=lambda x: x[1]["weight"]
        )
        
        strategies_to_remove = sorted_strategies[:len(sorted_strategies) - self.strategy_pool_size]
        
        for strategy_id, _ in strategies_to_remove:
            if self.visible_interface:
                logger.info(f"Pruned strategy: {self._strategy_pool[strategy_id]['name']} (ID: {strategy_id})")
            else:
                logger.debug(f"Pruned strategy: {self._strategy_pool[strategy_id]['name']} (ID: {strategy_id})")
            
            del self._strategy_pool[strategy_id]
            del self._strategy_performance[strategy_id]
        
        self._normalize_weights()
    
    def update_performance(
        self,
        strategy_id: str,
        returns: float,
        sharpe: float = None,
        drawdown: float = None,
        win_rate: float = None
    ) -> None:
        """
        Update performance metrics for a strategy.
        
        Args:
            strategy_id: ID of the strategy
            returns: Return of the strategy
            sharpe: Sharpe ratio of the strategy
            drawdown: Maximum drawdown of the strategy
            win_rate: Win rate of the strategy
        """
        with self._lock:
            if strategy_id not in self._strategy_performance:
                return
            
            performance = self._strategy_performance[strategy_id]
            
            performance["returns"].append(returns)
            
            if sharpe is not None:
                performance["sharpe"].append(sharpe)
            
            if drawdown is not None:
                performance["drawdown"].append(drawdown)
            
            if win_rate is not None:
                performance["win_rate"].append(win_rate)
            
            performance["last_updated"] = time.time()
    
    def get_strategy(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a strategy by ID.
        
        Args:
            strategy_id: ID of the strategy
            
        Returns:
            Dict: Strategy information
        """
        with self._lock:
            if strategy_id not in self._strategy_pool:
                return None
            
            return self._strategy_pool[strategy_id].copy()
    
    def get_all_strategies(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all strategies.
        
        Returns:
            Dict: All strategies
        """
        with self._lock:
            return {
                strategy_id: strategy.copy()
                for strategy_id, strategy in self._strategy_pool.items()
            }
    
    def get_best_strategy(self) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Get the best strategy based on weight.
        
        Returns:
            Tuple: Strategy ID and information
        """
        with self._lock:
            if not self._strategy_pool:
                return None
            
            best_strategy_id = max(
                self._strategy_pool.keys(),
                key=lambda x: self._strategy_pool[x]["weight"]
            )
            
            return best_strategy_id, self._strategy_pool[best_strategy_id].copy()
    
    def get_weighted_strategy(self) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Get a strategy randomly weighted by performance.
        
        Returns:
            Tuple: Strategy ID and information
        """
        with self._lock:
            if not self._strategy_pool:
                return None
            
            strategies = list(self._strategy_pool.keys())
            weights = [self._strategy_pool[s]["weight"] for s in strategies]
            
            selected_id = np.random.choice(strategies, p=weights)
            
            return selected_id, self._strategy_pool[selected_id].copy()
    
    def get_adaptation_history(self) -> List[Dict[str, Any]]:
        """
        Get adaptation history.
        
        Returns:
            List: Adaptation history
        """
        with self._lock:
            return self._adaptation_history.copy()
    
    def get_performance_stats(self, strategy_id: str = None) -> Dict[str, Any]:
        """
        Get performance statistics.
        
        Args:
            strategy_id: ID of the strategy, or None for all strategies
            
        Returns:
            Dict: Performance statistics
        """
        with self._lock:
            if strategy_id is not None:
                if strategy_id not in self._strategy_performance:
                    return {}
                
                performance = self._strategy_performance[strategy_id]
                
                return {
                    "returns": {
                        "mean": np.mean(performance["returns"]) if performance["returns"] else 0,
                        "std": np.std(performance["returns"]) if performance["returns"] else 0,
                        "min": min(performance["returns"]) if performance["returns"] else 0,
                        "max": max(performance["returns"]) if performance["returns"] else 0
                    },
                    "sharpe": np.mean(performance["sharpe"]) if performance["sharpe"] else 0,
                    "drawdown": np.mean(performance["drawdown"]) if performance["drawdown"] else 0,
                    "win_rate": np.mean(performance["win_rate"]) if performance["win_rate"] else 0,
                    "last_updated": performance["last_updated"]
                }
            else:
                result = {}
                
                for s_id, performance in self._strategy_performance.items():
                    if s_id not in self._strategy_pool:
                        continue
                    
                    result[s_id] = {
                        "name": self._strategy_pool[s_id]["name"],
                        "weight": self._strategy_pool[s_id]["weight"],
                        "returns": np.mean(performance["returns"]) if performance["returns"] else 0,
                        "sharpe": np.mean(performance["sharpe"]) if performance["sharpe"] else 0,
                        "drawdown": np.mean(performance["drawdown"]) if performance["drawdown"] else 0,
                        "win_rate": np.mean(performance["win_rate"]) if performance["win_rate"] else 0
                    }
                
                return result

def create_meta_learner(
    strategy_pool_size: int = 5,
    auto_adapt: bool = True,
    visible_interface: bool = True
) -> MetaLearner:
    """
    Create and return a meta-learner.
    
    Args:
        strategy_pool_size: Number of strategies to maintain in the pool
        auto_adapt: Whether to automatically adapt strategies
        visible_interface: Whether to show adaptation messages in the interface
        
    Returns:
        MetaLearner: New meta-learner instance
    """
    return MetaLearner(
        strategy_pool_size=strategy_pool_size,
        auto_adapt=auto_adapt,
        visible_interface=visible_interface
    )
