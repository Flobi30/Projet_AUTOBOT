"""
AUTOBOT Withdrawal Analyzer

This module implements an intelligent withdrawal system that analyzes the consequences
of withdrawals on system performance, scalability, and instance protection. It suggests
optimal withdrawal amounts to minimize impact on the system's operations.
"""

import logging
import numpy as np
from typing import Dict, List, Optional, Tuple, Union, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class WithdrawalImpact:
    """Represents the impact of a withdrawal on the system."""
    
    def __init__(self, 
                 scalability_impact: float = 0.0,
                 performance_impact: float = 0.0,
                 instance_risk: float = 0.0,
                 profit_impact: float = 0.0,
                 overall_safety: float = 1.0):
        """
        Initialize a WithdrawalImpact object.
        
        Args:
            scalability_impact: Impact on system scalability (0.0-1.0, higher is worse)
            performance_impact: Impact on system performance (0.0-1.0, higher is worse)
            instance_risk: Risk to instances (0.0-1.0, higher is worse)
            profit_impact: Impact on profit generation (0.0-1.0, higher is worse)
            overall_safety: Overall safety of the withdrawal (0.0-1.0, higher is safer)
        """
        self.scalability_impact = max(0.0, min(1.0, scalability_impact))
        self.performance_impact = max(0.0, min(1.0, performance_impact))
        self.instance_risk = max(0.0, min(1.0, instance_risk))
        self.profit_impact = max(0.0, min(1.0, profit_impact))
        self.overall_safety = max(0.0, min(1.0, overall_safety))
    
    def to_dict(self) -> Dict[str, float]:
        """Convert the impact to a dictionary."""
        return {
            "scalability_impact": self.scalability_impact,
            "performance_impact": self.performance_impact,
            "instance_risk": self.instance_risk,
            "profit_impact": self.profit_impact,
            "overall_safety": self.overall_safety
        }
    
    def get_impact_level(self) -> str:
        """Get a human-readable impact level."""
        if self.overall_safety >= 0.8:
            return "SAFE"
        elif self.overall_safety >= 0.6:
            return "MODERATE"
        elif self.overall_safety >= 0.4:
            return "CAUTION"
        elif self.overall_safety >= 0.2:
            return "HIGH RISK"
        else:
            return "CRITICAL"
    
    def get_color_code(self) -> str:
        """Get a color code for the impact level."""
        if self.overall_safety >= 0.8:
            return "#00C853"  # Green
        elif self.overall_safety >= 0.6:
            return "#AEEA00"  # Light Green
        elif self.overall_safety >= 0.4:
            return "#FFD600"  # Yellow
        elif self.overall_safety >= 0.2:
            return "#FF6D00"  # Orange
        else:
            return "#D50000"  # Red

class WithdrawalAnalyzer:
    """
    Analyzes withdrawals and their impact on the system.
    
    This class provides methods to analyze the consequences of withdrawals
    on system performance, scalability, and instance protection. It suggests
    optimal withdrawal amounts to minimize impact on the system's operations.
    """
    
    def __init__(self, 
                 total_balance: float = 0.0,
                 active_instances: int = 1,
                 new_instance_count: int = 0,
                 instance_age_days: List[int] = None,
                 profit_per_day: float = 0.0,
                 min_instance_balance: float = 50.0,
                 scaling_factor: float = 1.0):
        """
        Initialize the WithdrawalAnalyzer.
        
        Args:
            total_balance: Total balance in the system
            active_instances: Number of active instances
            new_instance_count: Number of new instances (less than 7 days old)
            instance_age_days: List of instance ages in days
            profit_per_day: Average profit per day
            min_instance_balance: Minimum balance required per instance
            scaling_factor: Scaling factor for the system
        """
        self.total_balance = max(0.0, total_balance)
        self.active_instances = max(1, active_instances)
        self.new_instance_count = max(0, new_instance_count)
        self.instance_age_days = instance_age_days or [30]  # Default to one 30-day old instance
        self.profit_per_day = max(0.0, profit_per_day)
        self.min_instance_balance = max(10.0, min_instance_balance)
        self.scaling_factor = max(0.1, scaling_factor)
        
        self.balance_per_instance = self.total_balance / self.active_instances
        self.new_instance_ratio = self.new_instance_count / self.active_instances if self.active_instances > 0 else 0
        
        self.withdrawal_history: List[Dict[str, Any]] = []
    
    def update_system_metrics(self, 
                             total_balance: float,
                             active_instances: int,
                             new_instance_count: int,
                             instance_age_days: List[int],
                             profit_per_day: float):
        """
        Update system metrics.
        
        Args:
            total_balance: Total balance in the system
            active_instances: Number of active instances
            new_instance_count: Number of new instances (less than 7 days old)
            instance_age_days: List of instance ages in days
            profit_per_day: Average profit per day
        """
        self.total_balance = max(0.0, total_balance)
        self.active_instances = max(1, active_instances)
        self.new_instance_count = max(0, new_instance_count)
        self.instance_age_days = instance_age_days or [30]
        self.profit_per_day = max(0.0, profit_per_day)
        
        self.balance_per_instance = self.total_balance / self.active_instances
        self.new_instance_ratio = self.new_instance_count / self.active_instances if self.active_instances > 0 else 0
    
    def analyze_withdrawal(self, amount: float) -> WithdrawalImpact:
        """
        Analyze the impact of a withdrawal.
        
        Args:
            amount: Amount to withdraw
            
        Returns:
            WithdrawalImpact: Impact of the withdrawal
        """
        if amount <= 0:
            return WithdrawalImpact(
                scalability_impact=0.0,
                performance_impact=0.0,
                instance_risk=0.0,
                profit_impact=0.0,
                overall_safety=1.0
            )
        
        if amount >= self.total_balance:
            return WithdrawalImpact(
                scalability_impact=1.0,
                performance_impact=1.0,
                instance_risk=1.0,
                profit_impact=1.0,
                overall_safety=0.0
            )
        
        remaining_balance = self.total_balance - amount
        
        min_required_balance = self.active_instances * self.min_instance_balance
        scalability_impact = 0.0
        if remaining_balance < min_required_balance:
            scalability_impact = min(1.0, (min_required_balance - remaining_balance) / min_required_balance)
        
        performance_impact = (amount / self.total_balance) ** 2
        
        instance_risk = 0.0
        if self.new_instance_count > 0:
            avg_age = sum(self.instance_age_days) / len(self.instance_age_days)
            age_factor = max(0.0, min(1.0, 30 / avg_age if avg_age > 0 else 1.0))
            instance_risk = age_factor * (amount / self.total_balance)
        
        profit_impact = 0.0
        if self.profit_per_day > 0:
            profit_days = amount / self.profit_per_day if self.profit_per_day > 0 else float('inf')
            profit_impact = min(1.0, profit_days / 30)  # Cap at 30 days of profit
        
        overall_safety = 1.0 - (
            0.3 * scalability_impact +
            0.3 * performance_impact +
            0.2 * instance_risk +
            0.2 * profit_impact
        )
        
        return WithdrawalImpact(
            scalability_impact=scalability_impact,
            performance_impact=performance_impact,
            instance_risk=instance_risk,
            profit_impact=profit_impact,
            overall_safety=overall_safety
        )
    
    def suggest_optimal_withdrawal(self) -> Tuple[float, WithdrawalImpact]:
        """
        Suggest an optimal withdrawal amount.
        
        Returns:
            Tuple[float, WithdrawalImpact]: Optimal withdrawal amount and its impact
        """
        profit_suggestion = self.profit_per_day * 30 * 0.5  # 50% of monthly profit
        
        min_required_balance = self.active_instances * self.min_instance_balance
        balance_suggestion = max(0.0, self.total_balance - min_required_balance * 1.5)  # Keep 1.5x minimum
        
        age_adjustment = 1.0
        if self.new_instance_count > 0:
            avg_age = sum(self.instance_age_days) / len(self.instance_age_days)
            age_adjustment = min(1.0, avg_age / 30)  # Full withdrawal allowed at 30+ days
        
        suggested_amount = min(profit_suggestion, balance_suggestion) * age_adjustment
        
        suggested_amount = max(0.0, suggested_amount)
        
        impact = self.analyze_withdrawal(suggested_amount)
        
        return suggested_amount, impact
    
    def record_withdrawal(self, amount: float, impact: WithdrawalImpact):
        """
        Record a withdrawal in the history.
        
        Args:
            amount: Amount withdrawn
            impact: Impact of the withdrawal
        """
        self.withdrawal_history.append({
            "timestamp": datetime.now().isoformat(),
            "amount": amount,
            "impact": impact.to_dict(),
            "total_balance_before": self.total_balance,
            "total_balance_after": self.total_balance - amount,
            "active_instances": self.active_instances,
            "new_instance_count": self.new_instance_count
        })
        
        self.total_balance -= amount
        
        self.balance_per_instance = self.total_balance / self.active_instances if self.active_instances > 0 else 0
    
    def get_withdrawal_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get withdrawal history.
        
        Args:
            limit: Maximum number of history entries to return
            
        Returns:
            List[Dict[str, Any]]: Withdrawal history
        """
        return self.withdrawal_history[-limit:]
    
    def get_system_metrics(self) -> Dict[str, Any]:
        """
        Get current system metrics.
        
        Returns:
            Dict[str, Any]: Current system metrics
        """
        return {
            "total_balance": self.total_balance,
            "active_instances": self.active_instances,
            "new_instance_count": self.new_instance_count,
            "balance_per_instance": self.balance_per_instance,
            "new_instance_ratio": self.new_instance_ratio,
            "profit_per_day": self.profit_per_day,
            "min_instance_balance": self.min_instance_balance,
            "scaling_factor": self.scaling_factor
        }
    
    def simulate_withdrawal_impact(self, amounts: List[float]) -> List[Dict[str, Any]]:
        """
        Simulate the impact of different withdrawal amounts.
        
        Args:
            amounts: List of amounts to simulate
            
        Returns:
            List[Dict[str, Any]]: Impact of each amount
        """
        results = []
        
        for amount in amounts:
            impact = self.analyze_withdrawal(amount)
            results.append({
                "amount": amount,
                "impact": impact.to_dict(),
                "impact_level": impact.get_impact_level(),
                "color_code": impact.get_color_code()
            })
        
        return results
    
    def get_withdrawal_recommendations(self) -> Dict[str, Any]:
        """
        Get withdrawal recommendations.
        
        Returns:
            Dict[str, Any]: Withdrawal recommendations
        """
        optimal_amount, optimal_impact = self.suggest_optimal_withdrawal()
        
        if self.total_balance > 0:
            step = self.total_balance / 10
            amounts = [step * i for i in range(1, 11)]
        else:
            amounts = [0.0]
        
        simulations = self.simulate_withdrawal_impact(amounts)
        
        return {
            "optimal_amount": optimal_amount,
            "optimal_impact": optimal_impact.to_dict(),
            "optimal_impact_level": optimal_impact.get_impact_level(),
            "optimal_impact_color": optimal_impact.get_color_code(),
            "simulations": simulations,
            "system_metrics": self.get_system_metrics()
        }

_instance = None

def get_withdrawal_analyzer(
    total_balance: float = 0.0,
    active_instances: int = 1,
    new_instance_count: int = 0,
    instance_age_days: List[int] = None,
    profit_per_day: float = 0.0,
    min_instance_balance: float = 50.0,
    scaling_factor: float = 1.0
) -> WithdrawalAnalyzer:
    """
    Get the singleton instance of the WithdrawalAnalyzer.
    
    Args:
        total_balance: Total balance in the system
        active_instances: Number of active instances
        new_instance_count: Number of new instances (less than 7 days old)
        instance_age_days: List of instance ages in days
        profit_per_day: Average profit per day
        min_instance_balance: Minimum balance required per instance
        scaling_factor: Scaling factor for the system
        
    Returns:
        WithdrawalAnalyzer: Singleton instance of the WithdrawalAnalyzer
    """
    global _instance
    
    if _instance is None:
        _instance = WithdrawalAnalyzer(
            total_balance=total_balance,
            active_instances=active_instances,
            new_instance_count=new_instance_count,
            instance_age_days=instance_age_days,
            profit_per_day=profit_per_day,
            min_instance_balance=min_instance_balance,
            scaling_factor=scaling_factor
        )
    
    return _instance

def analyze_withdrawal(amount: float) -> Dict[str, Any]:
    """
    Analyze the impact of a withdrawal.
    
    Args:
        amount: Amount to withdraw
        
    Returns:
        Dict[str, Any]: Impact of the withdrawal
    """
    analyzer = get_withdrawal_analyzer()
    impact = analyzer.analyze_withdrawal(amount)
    
    return {
        "amount": amount,
        "impact": impact.to_dict(),
        "impact_level": impact.get_impact_level(),
        "color_code": impact.get_color_code()
    }

def suggest_optimal_withdrawal() -> Dict[str, Any]:
    """
    Suggest an optimal withdrawal amount.
    
    Returns:
        Dict[str, Any]: Optimal withdrawal amount and its impact
    """
    analyzer = get_withdrawal_analyzer()
    amount, impact = analyzer.suggest_optimal_withdrawal()
    
    return {
        "amount": amount,
        "impact": impact.to_dict(),
        "impact_level": impact.get_impact_level(),
        "color_code": impact.get_color_code()
    }

def get_withdrawal_recommendations() -> Dict[str, Any]:
    """
    Get withdrawal recommendations.
    
    Returns:
        Dict[str, Any]: Withdrawal recommendations
    """
    analyzer = get_withdrawal_analyzer()
    return analyzer.get_withdrawal_recommendations()
