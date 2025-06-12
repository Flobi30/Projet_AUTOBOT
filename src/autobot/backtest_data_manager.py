"""
Centralized Backtest Data Manager for AUTOBOT

This module provides centralized management for backtest data from HFT, e-commerce, 
and arbitrage modules, with persistent storage and learning metrics.
"""

import json
import os
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging
import numpy as np

logger = logging.getLogger(__name__)

class BacktestDataManager:
    """Centralized manager for backtest data from HFT, e-commerce, and arbitrage modules."""
    
    def __init__(self, data_file: str = "config/backtest_history.json"):
        self.data_file = data_file
        self.ensure_data_file_exists()
    
    def ensure_data_file_exists(self):
        """Ensure the backtest data file exists."""
        os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
        if not os.path.exists(self.data_file):
            initial_data = {
                "hft_backtests": [],
                "ecommerce_backtests": [],
                "arbitrage_backtests": [],
                "learning_metrics": {
                    "total_backtests": 0,
                    "average_performance": 0,
                    "best_strategies": {},
                    "performance_trend": []
                },
                "global_settings": {
                    "target_daily_return": 0.10,
                    "learning_enabled": True
                }
            }
            with open(self.data_file, 'w') as f:
                json.dump(initial_data, f, indent=2)
    
    def add_backtest_result(self, domain: str, result: Dict[str, Any]) -> bool:
        """Add a backtest result for a specific domain."""
        try:
            with open(self.data_file, 'r') as f:
                data = json.load(f)
            
            result["timestamp"] = datetime.now().isoformat()
            result["domain"] = domain
            
            domain_key = f"{domain}_backtests"
            if domain_key not in data:
                data[domain_key] = []
            
            data[domain_key].append(result)
            
            self._update_learning_metrics(data, result)
            
            with open(self.data_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.info(f"Added {domain} backtest result: {result.get('total_return', 0):.2f}% return")
            return True
        except Exception as e:
            logger.error(f"Error adding backtest result: {str(e)}")
            return False
    
    def get_centralized_data(self) -> Dict[str, Any]:
        """Get all centralized backtest data."""
        try:
            with open(self.data_file, 'r') as f:
                data = json.load(f)
            
            all_backtests = []
            for domain in ["hft", "ecommerce", "arbitrage"]:
                all_backtests.extend(data.get(f"{domain}_backtests", []))
            
            return {
                "hft_backtests": data.get("hft_backtests", []),
                "ecommerce_backtests": data.get("ecommerce_backtests", []),
                "arbitrage_backtests": data.get("arbitrage_backtests", []),
                "all_backtests": all_backtests,
                "learning_metrics": data.get("learning_metrics", {}),
                "total_backtests": len(all_backtests),
                "performance_summary": self._calculate_performance_summary(all_backtests)
            }
        except Exception as e:
            logger.error(f"Error reading backtest data: {str(e)}")
            return self._get_default_data()
    
    def _update_learning_metrics(self, data: Dict[str, Any], new_result: Dict[str, Any]):
        """Update learning metrics with new backtest result."""
        metrics = data.get("learning_metrics", {})
        metrics["total_backtests"] = metrics.get("total_backtests", 0) + 1
        
        performance = new_result.get("total_return", 0)
        trend = metrics.get("performance_trend", [])
        trend.append({
            "timestamp": new_result["timestamp"],
            "performance": performance,
            "domain": new_result["domain"]
        })
        
        if len(trend) > 100:
            trend = trend[-100:]
        
        metrics["performance_trend"] = trend
        
        if trend:
            metrics["average_performance"] = np.mean([t["performance"] for t in trend])
        
        strategy_name = new_result.get("strategy", "Unknown")
        domain = new_result["domain"]
        
        if domain not in metrics.get("best_strategies", {}):
            if "best_strategies" not in metrics:
                metrics["best_strategies"] = {}
            metrics["best_strategies"][domain] = {
                "strategy": strategy_name,
                "performance": performance,
                "timestamp": new_result["timestamp"]
            }
        elif performance > metrics["best_strategies"][domain].get("performance", 0):
            metrics["best_strategies"][domain] = {
                "strategy": strategy_name,
                "performance": performance,
                "timestamp": new_result["timestamp"]
            }
        
        data["learning_metrics"] = metrics
    
    def _calculate_performance_summary(self, backtests: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate performance summary from all backtests."""
        if not backtests:
            return {
                "total_return": 0,
                "average_return": 0,
                "win_rate": 0,
                "best_strategy": None,
                "total_backtests": 0
            }
        
        returns = [b.get("total_return", 0) for b in backtests]
        winning_backtests = [b for b in backtests if b.get("total_return", 0) > 0]
        
        best_backtest = max(backtests, key=lambda x: x.get("total_return", 0))
        
        return {
            "total_return": sum(returns),
            "average_return": np.mean(returns),
            "win_rate": len(winning_backtests) / len(backtests) * 100,
            "best_strategy": best_backtest,
            "total_backtests": len(backtests),
            "max_return": max(returns),
            "min_return": min(returns),
            "std_return": np.std(returns)
        }
    
    def _get_default_data(self) -> Dict[str, Any]:
        """Get default data structure."""
        return {
            "hft_backtests": [],
            "ecommerce_backtests": [],
            "arbitrage_backtests": [],
            "all_backtests": [],
            "learning_metrics": {
                "total_backtests": 0,
                "average_performance": 0,
                "best_strategies": {},
                "performance_trend": []
            },
            "total_backtests": 0,
            "performance_summary": {
                "total_return": 0,
                "average_return": 0,
                "win_rate": 0,
                "best_strategy": None,
                "total_backtests": 0
            }
        }
    
    def get_domain_performance(self, domain: str) -> Dict[str, Any]:
        """Get performance metrics for a specific domain."""
        try:
            data = self.get_centralized_data()
            domain_backtests = data.get(f"{domain}_backtests", [])
            
            if not domain_backtests:
                return {
                    "domain": domain,
                    "total_backtests": 0,
                    "average_return": 0,
                    "win_rate": 0,
                    "best_performance": 0
                }
            
            returns = [b.get("total_return", 0) for b in domain_backtests]
            winning_tests = [b for b in domain_backtests if b.get("total_return", 0) > 0]
            
            return {
                "domain": domain,
                "total_backtests": len(domain_backtests),
                "average_return": np.mean(returns),
                "win_rate": len(winning_tests) / len(domain_backtests) * 100,
                "best_performance": max(returns),
                "worst_performance": min(returns),
                "recent_performance": np.mean(returns[-10:]) if len(returns) >= 10 else np.mean(returns)
            }
        except Exception as e:
            logger.error(f"Error getting domain performance for {domain}: {str(e)}")
            return {
                "domain": domain,
                "total_backtests": 0,
                "average_return": 0,
                "win_rate": 0,
                "best_performance": 0
            }
    
    def calculate_potential_gains_losses(self, investment_amount: float = 1000.0) -> Dict[str, Any]:
        """Calculate potential gains and losses based on historical backtest performance."""
        try:
            data = self.get_centralized_data()
            performance_summary = data["performance_summary"]
            
            if performance_summary["total_backtests"] == 0:
                return {
                    "investment_amount": investment_amount,
                    "potential_gain": 0,
                    "potential_loss": 0,
                    "expected_return": 0,
                    "confidence_level": 0
                }
            
            avg_return = performance_summary["average_return"] / 100  # Convert to decimal
            max_return = performance_summary["max_return"] / 100
            min_return = performance_summary["min_return"] / 100
            
            potential_gain = investment_amount * max_return
            potential_loss = investment_amount * abs(min_return) if min_return < 0 else 0
            expected_return = investment_amount * avg_return
            
            win_rate = performance_summary["win_rate"]
            total_tests = performance_summary["total_backtests"]
            confidence_level = min(95, (win_rate * 0.7) + (min(total_tests, 100) * 0.3))
            
            return {
                "investment_amount": investment_amount,
                "potential_gain": potential_gain,
                "potential_loss": potential_loss,
                "expected_return": expected_return,
                "confidence_level": confidence_level,
                "win_rate": win_rate,
                "total_backtests": total_tests
            }
        except Exception as e:
            logger.error(f"Error calculating potential gains/losses: {str(e)}")
            return {
                "investment_amount": investment_amount,
                "potential_gain": 0,
                "potential_loss": 0,
                "expected_return": 0,
                "confidence_level": 0
            }

backtest_data_manager = BacktestDataManager()

def get_centralized_backtest_data() -> Dict[str, Any]:
    """Get centralized backtest data."""
    return backtest_data_manager.get_centralized_data()

def add_backtest_result(domain: str, result: Dict[str, Any]) -> bool:
    """Add a backtest result."""
    return backtest_data_manager.add_backtest_result(domain, result)

def get_domain_performance(domain: str) -> Dict[str, Any]:
    """Get performance for a specific domain."""
    return backtest_data_manager.get_domain_performance(domain)

def calculate_potential_gains_losses(investment_amount: float = 1000.0) -> Dict[str, Any]:
    """Calculate potential gains and losses."""
    return backtest_data_manager.calculate_potential_gains_losses(investment_amount)
