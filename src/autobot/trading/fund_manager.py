"""
AUTOBOT Fund Manager

This module implements the fund management functionality for AUTOBOT, including
deposit and withdrawal operations with intelligent analysis of consequences.
"""

import logging
import time
from typing import Dict, List, Optional, Tuple, Union, Any
from datetime import datetime, timedelta

from .withdrawal_analyzer import (
    get_withdrawal_analyzer,
    WithdrawalImpact,
    analyze_withdrawal,
    suggest_optimal_withdrawal
)

logger = logging.getLogger(__name__)

class FundManager:
    """
    Fund Manager for AUTOBOT.
    
    This class manages deposits and withdrawals, including intelligent analysis
    of withdrawal consequences and optimal withdrawal suggestions.
    """
    
    def __init__(self, 
                 initial_balance: float = 0.0,
                 active_instances: int = 1,
                 new_instance_count: int = 0,
                 instance_age_days: List[int] = None,
                 profit_per_day: float = 0.0):
        """
        Initialize the Fund Manager.
        
        Args:
            initial_balance: Initial balance
            active_instances: Number of active instances
            new_instance_count: Number of new instances (less than 7 days old)
            instance_age_days: List of instance ages in days
            profit_per_day: Average profit per day
        """
        self.balance = max(0.0, initial_balance)
        self.active_instances = max(1, active_instances)
        self.new_instance_count = max(0, new_instance_count)
        self.instance_age_days = instance_age_days or [30]  # Default to one 30-day old instance
        self.profit_per_day = max(0.0, profit_per_day)
        
        self.withdrawal_analyzer = get_withdrawal_analyzer(
            total_balance=self.balance,
            active_instances=self.active_instances,
            new_instance_count=self.new_instance_count,
            instance_age_days=self.instance_age_days,
            profit_per_day=self.profit_per_day
        )
        
        self.transaction_history: List[Dict[str, Any]] = []
    
    def deposit(self, amount: float) -> Dict[str, Any]:
        """
        Deposit funds.
        
        Args:
            amount: Amount to deposit
            
        Returns:
            Dict[str, Any]: Deposit result
        """
        if amount <= 0:
            logger.warning(f"Invalid deposit amount: {amount}")
            return {
                "success": False,
                "message": "Deposit amount must be positive",
                "balance": self.balance
            }
        
        previous_balance = self.balance
        self.balance += amount
        
        self.withdrawal_analyzer.update_system_metrics(
            total_balance=self.balance,
            active_instances=self.active_instances,
            new_instance_count=self.new_instance_count,
            instance_age_days=self.instance_age_days,
            profit_per_day=self.profit_per_day
        )
        
        transaction = {
            "timestamp": datetime.now().isoformat(),
            "type": "deposit",
            "amount": amount,
            "previous_balance": previous_balance,
            "new_balance": self.balance
        }
        self.transaction_history.append(transaction)
        
        logger.info(f"Deposited ${amount:.2f}, new balance: ${self.balance:.2f}")
        
        return {
            "success": True,
            "message": f"Successfully deposited ${amount:.2f}",
            "balance": self.balance,
            "transaction": transaction
        }
    
    def withdraw(self, amount: float) -> Dict[str, Any]:
        """
        Withdraw funds with intelligent analysis.
        
        Args:
            amount: Amount to withdraw
            
        Returns:
            Dict[str, Any]: Withdrawal result with impact analysis
        """
        if amount <= 0:
            logger.warning(f"Invalid withdrawal amount: {amount}")
            return {
                "success": False,
                "message": "Withdrawal amount must be positive",
                "balance": self.balance
            }
        
        if amount > self.balance:
            logger.warning(f"Insufficient funds for withdrawal: {amount} > {self.balance}")
            return {
                "success": False,
                "message": "Insufficient funds",
                "balance": self.balance
            }
        
        impact = self.withdrawal_analyzer.analyze_withdrawal(amount)
        
        previous_balance = self.balance
        self.balance -= amount
        
        self.withdrawal_analyzer.record_withdrawal(amount, impact)
        
        transaction = {
            "timestamp": datetime.now().isoformat(),
            "type": "withdrawal",
            "amount": amount,
            "previous_balance": previous_balance,
            "new_balance": self.balance,
            "impact": impact.to_dict()
        }
        self.transaction_history.append(transaction)
        
        logger.info(f"Withdrew ${amount:.2f}, new balance: ${self.balance:.2f}, impact level: {impact.get_impact_level()}")
        
        return {
            "success": True,
            "message": f"Successfully withdrew ${amount:.2f}",
            "balance": self.balance,
            "impact": impact.to_dict(),
            "impact_level": impact.get_impact_level(),
            "transaction": transaction
        }
    
    def get_optimal_withdrawal(self) -> Dict[str, Any]:
        """
        Get optimal withdrawal amount.
        
        Returns:
            Dict[str, Any]: Optimal withdrawal amount and its impact
        """
        amount, impact = self.withdrawal_analyzer.suggest_optimal_withdrawal()
        
        return {
            "amount": amount,
            "impact": impact.to_dict(),
            "impact_level": impact.get_impact_level(),
            "color_code": impact.get_color_code()
        }
    
    def get_withdrawal_recommendations(self) -> Dict[str, Any]:
        """
        Get withdrawal recommendations.
        
        Returns:
            Dict[str, Any]: Withdrawal recommendations
        """
        return self.withdrawal_analyzer.get_withdrawal_recommendations()
    
    def get_balance(self) -> float:
        """
        Get current balance.
        
        Returns:
            float: Current balance
        """
        return self.balance
    
    def get_available_balance(self) -> float:
        """
        Get available balance for transactions.
        
        Returns:
            float: Available balance
        """
        return self.balance
    
    def process_expense(self, amount: float, description: str, category: str = "general") -> Dict[str, Any]:
        """
        Process an expense transaction.
        
        Args:
            amount: Amount to deduct
            description: Description of the expense
            category: Category of the expense
            
        Returns:
            Dict[str, Any]: Transaction result
        """
        if amount <= 0:
            logger.warning(f"Invalid expense amount: {amount}")
            return {
                "success": False,
                "message": "Expense amount must be positive",
                "balance": self.balance
            }
        
        if amount > self.balance:
            logger.warning(f"Insufficient funds for expense: {amount} > {self.balance}")
            return {
                "success": False,
                "message": "Insufficient funds",
                "balance": self.balance
            }
        
        previous_balance = self.balance
        self.balance -= amount
        
        transaction = {
            "timestamp": datetime.now().isoformat(),
            "type": "expense",
            "amount": amount,
            "description": description,
            "category": category,
            "previous_balance": previous_balance,
            "new_balance": self.balance
        }
        self.transaction_history.append(transaction)
        
        logger.info(f"Processed expense: {description} - ${amount:.2f}, new balance: ${self.balance:.2f}")
        
        return {
            "success": True,
            "message": f"Successfully processed expense: {description}",
            "balance": self.balance,
            "transaction": transaction
        }
    
    def get_transaction_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get transaction history.
        
        Args:
            limit: Maximum number of transactions to return
            
        Returns:
            List[Dict[str, Any]]: Transaction history
        """
        return self.transaction_history[-limit:]
    
    def update_system_metrics(self, 
                             active_instances: int,
                             new_instance_count: int,
                             instance_age_days: List[int],
                             profit_per_day: float):
        """
        Update system metrics.
        
        Args:
            active_instances: Number of active instances
            new_instance_count: Number of new instances (less than 7 days old)
            instance_age_days: List of instance ages in days
            profit_per_day: Average profit per day
        """
        self.active_instances = max(1, active_instances)
        self.new_instance_count = max(0, new_instance_count)
        self.instance_age_days = instance_age_days or [30]
        self.profit_per_day = max(0.0, profit_per_day)
        
        self.withdrawal_analyzer.update_system_metrics(
            total_balance=self.balance,
            active_instances=self.active_instances,
            new_instance_count=self.new_instance_count,
            instance_age_days=self.instance_age_days,
            profit_per_day=self.profit_per_day
        )
    
    def get_system_metrics(self) -> Dict[str, Any]:
        """
        Get system metrics.
        
        Returns:
            Dict[str, Any]: System metrics
        """
        return {
            "balance": self.balance,
            "active_instances": self.active_instances,
            "new_instance_count": self.new_instance_count,
            "instance_age_days": self.instance_age_days,
            "profit_per_day": self.profit_per_day,
            "balance_per_instance": self.balance / self.active_instances if self.active_instances > 0 else 0
        }
    
    def simulate_withdrawal_impact(self, amounts: List[float]) -> List[Dict[str, Any]]:
        """
        Simulate the impact of different withdrawal amounts.
        
        Args:
            amounts: List of amounts to simulate
            
        Returns:
            List[Dict[str, Any]]: Impact of each amount
        """
        return self.withdrawal_analyzer.simulate_withdrawal_impact(amounts)

_instance = None

def get_fund_manager(
    initial_balance: float = 0.0,
    active_instances: int = 1,
    new_instance_count: int = 0,
    instance_age_days: List[int] = None,
    profit_per_day: float = 0.0
) -> FundManager:
    """
    Get the singleton instance of the Fund Manager.
    
    Args:
        initial_balance: Initial balance
        active_instances: Number of active instances
        new_instance_count: Number of new instances (less than 7 days old)
        instance_age_days: List of instance ages in days
        profit_per_day: Average profit per day
        
    Returns:
        FundManager: Singleton instance of the Fund Manager
    """
    global _instance
    
    if _instance is None:
        _instance = FundManager(
            initial_balance=initial_balance,
            active_instances=active_instances,
            new_instance_count=new_instance_count,
            instance_age_days=instance_age_days,
            profit_per_day=profit_per_day
        )
    
    return _instance

def deposit(amount: float) -> Dict[str, Any]:
    """
    Deposit funds.
    
    Args:
        amount: Amount to deposit
        
    Returns:
        Dict[str, Any]: Deposit result
    """
    fund_manager = get_fund_manager()
    return fund_manager.deposit(amount)

def withdraw(amount: float) -> Dict[str, Any]:
    """
    Withdraw funds.
    
    Args:
        amount: Amount to withdraw
        
    Returns:
        Dict[str, Any]: Withdrawal result
    """
    fund_manager = get_fund_manager()
    return fund_manager.withdraw(amount)

def get_optimal_withdrawal() -> Dict[str, Any]:
    """
    Get optimal withdrawal amount.
    
    Returns:
        Dict[str, Any]: Optimal withdrawal amount and its impact
    """
    fund_manager = get_fund_manager()
    return fund_manager.get_optimal_withdrawal()

def get_balance() -> float:
    """
    Get current balance.
    
    Returns:
        float: Current balance
    """
    fund_manager = get_fund_manager()
    return fund_manager.get_balance()
