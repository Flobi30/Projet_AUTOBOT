"""
Learning system that improves AUTOBOT strategies based on backtest results.
"""
import time
import logging
import numpy as np
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import json

logger = logging.getLogger(__name__)

class BacktestLearningSystem:
    """System that learns from backtest results to improve strategy performance."""
    
    def __init__(self, learning_threshold: int = 10, improvement_target: float = 0.10):
        self.learning_threshold = learning_threshold  # Minimum backtests before learning
        self.improvement_target = improvement_target  # Target daily return (10%)
        self.running = False
        self.learning_thread = None
    
    def start(self):
        """Start the learning system."""
        if self.running:
            return
        
        self.running = True
        try:
            from .thread_management import create_managed_thread, is_shutdown_requested
            
            self.learning_thread = create_managed_thread(
                name="backtest_learning_system",
                target=self._learning_loop,
                daemon=True,
                auto_start=True
            )
            logger.info("Backtest learning system started")
        except Exception as e:
            logger.error(f"Error starting learning system: {str(e)}")
            self.running = False
    
    def stop(self):
        """Stop the learning system."""
        self.running = False
        if self.learning_thread:
            try:
                self.learning_thread.stop()
            except:
                pass
        logger.info("Backtest learning system stopped")
    
    def _learning_loop(self):
        """Main learning loop that analyzes backtest data and triggers training."""
        from .thread_management import is_shutdown_requested
        
        while self.running and not is_shutdown_requested():
            try:
                from .backtest_data_manager import backtest_data_manager
                
                data = backtest_data_manager.get_centralized_data()
                
                if data["total_backtests"] >= self.learning_threshold:
                    analysis = self._analyze_performance(data)
                    
                    if analysis["needs_improvement"]:
                        self._trigger_learning(analysis)
                
                for _ in range(3600):
                    if not self.running or is_shutdown_requested():
                        break
                    time.sleep(1)
                
            except Exception as e:
                logger.error(f"Error in learning loop: {str(e)}")
                time.sleep(300)  # Wait 5 minutes on error
    
    def _analyze_performance(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze backtest performance to determine if learning is needed."""
        performance_summary = data["performance_summary"]
        learning_metrics = data["learning_metrics"]
        
        recent_trend = self._calculate_recent_trend(learning_metrics.get("performance_trend", []))
        
        current_performance = performance_summary.get("average_return", 0)
        target_daily_return = self.improvement_target * 100  # Convert to percentage
        
        needs_improvement = (
            current_performance < target_daily_return or
            recent_trend["is_declining"] or
            performance_summary.get("win_rate", 0) < 60
        )
        
        return {
            "needs_improvement": needs_improvement,
            "current_performance": current_performance,
            "target_performance": target_daily_return,
            "recent_trend": recent_trend,
            "win_rate": performance_summary.get("win_rate", 0),
            "best_domain": self._identify_best_domain(data),
            "worst_domain": self._identify_worst_domain(data)
        }
    
    def _calculate_recent_trend(self, trend_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate recent performance trend."""
        if len(trend_data) < 5:
            return {"is_declining": False, "trend_slope": 0, "recent_average": 0}
        
        recent_data = trend_data[-10:]
        performances = [d["performance"] for d in recent_data]
        
        x = np.arange(len(performances))
        slope = np.polyfit(x, performances, 1)[0]
        
        return {
            "is_declining": slope < -0.01,  # Declining if slope < -0.01
            "trend_slope": slope,
            "recent_average": np.mean(performances)
        }
    
    def _identify_best_domain(self, data: Dict[str, Any]) -> str:
        """Identify the best performing domain."""
        domain_performance = {}
        
        for domain in ["hft", "ecommerce", "arbitrage"]:
            backtests = data.get(f"{domain}_backtests", [])
            if backtests:
                avg_return = np.mean([b.get("total_return", 0) for b in backtests])
                domain_performance[domain] = avg_return
        
        return max(domain_performance, key=domain_performance.get) if domain_performance else "hft"
    
    def _identify_worst_domain(self, data: Dict[str, Any]) -> str:
        """Identify the worst performing domain."""
        domain_performance = {}
        
        for domain in ["hft", "ecommerce", "arbitrage"]:
            backtests = data.get(f"{domain}_backtests", [])
            if backtests:
                avg_return = np.mean([b.get("total_return", 0) for b in backtests])
                domain_performance[domain] = avg_return
        
        return min(domain_performance, key=domain_performance.get) if domain_performance else "ecommerce"
    
    def _trigger_learning(self, analysis: Dict[str, Any]):
        """Trigger learning/training based on analysis."""
        try:
            from .rl.train import start_training
            
            worst_domain = analysis["worst_domain"]
            
            job_id = start_training(
                symbol="BTC/USDT",
                timeframe="1h",
                episodes=100,
                background=True
            )
            
            logger.info(f"Learning triggered for {worst_domain} domain. Training job: {job_id}")
            logger.info(f"Current performance: {analysis['current_performance']:.2f}%, Target: {analysis['target_performance']:.2f}%")
            
        except Exception as e:
            logger.error(f"Error triggering learning: {str(e)}")
    
    def get_learning_status(self) -> Dict[str, Any]:
        """Get current learning system status."""
        try:
            from .backtest_data_manager import backtest_data_manager
            data = backtest_data_manager.get_centralized_data()
            
            return {
                "running": self.running,
                "total_backtests": data["total_backtests"],
                "learning_threshold": self.learning_threshold,
                "improvement_target": self.improvement_target * 100,
                "current_performance": data["performance_summary"].get("average_return", 0),
                "learning_ready": data["total_backtests"] >= self.learning_threshold
            }
        except Exception as e:
            logger.error(f"Error getting learning status: {str(e)}")
            return {
                "running": self.running,
                "total_backtests": 0,
                "learning_threshold": self.learning_threshold,
                "improvement_target": self.improvement_target * 100,
                "current_performance": 0,
                "learning_ready": False
            }

learning_system = BacktestLearningSystem()

def start_learning_system():
    """Start the learning system."""
    learning_system.start()

def stop_learning_system():
    """Stop the learning system."""
    learning_system.stop()

def get_learning_status() -> Dict[str, Any]:
    """Get learning system status."""
    return learning_system.get_learning_status()
