"""
AUTOBOT Deposit/Withdrawal Routes

This module implements the routes for the dedicated deposit/withdrawal page.
"""

import os
import logging
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from ..autobot_security.auth.user_manager import User, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()

templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui", "templates")
templates = Jinja2Templates(directory=templates_dir)

class DepositRequest(BaseModel):
    amount: float

class WithdrawalRequest(BaseModel):
    amount: float

class TransactionResponse(BaseModel):
    success: bool
    message: str
    new_balance: float
    impact: Optional[Dict[str, Any]] = None

class WithdrawalImpact:
    def __init__(self, 
                 scalability_impact: float = 0.0, 
                 performance_impact: float = 0.0,
                 instance_risk: float = 0.0,
                 profit_impact: float = 0.0,
                 overall_safety: float = 1.0):
        self.scalability_impact = scalability_impact
        self.performance_impact = performance_impact
        self.instance_risk = instance_risk
        self.profit_impact = profit_impact
        self.overall_safety = overall_safety
    
    def to_dict(self) -> Dict[str, float]:
        return {
            "scalability_impact": self.scalability_impact,
            "performance_impact": self.performance_impact,
            "instance_risk": self.instance_risk,
            "profit_impact": self.profit_impact,
            "overall_safety": self.overall_safety
        }

class WithdrawalAnalyzer:
    def __init__(self):
        self.total_balance = 10000.0  # Example initial balance
        self.active_instances = 5
        self.instance_age_days = 30
        self.profit_per_day = 100.0
        self.transactions = []
    
    def get_system_metrics(self) -> Dict[str, Any]:
        return {
            "total_balance": self.total_balance,
            "active_instances": self.active_instances,
            "instance_age_days": self.instance_age_days,
            "profit_per_day": self.profit_per_day
        }
    
    def update_system_metrics(self, total_balance: float, active_instances: int, 
                             new_instance_count: int, instance_age_days: int,
                             profit_per_day: float) -> None:
        self.total_balance = total_balance
        self.active_instances = active_instances
        self.instance_age_days = instance_age_days
        self.profit_per_day = profit_per_day
    
    def analyze_withdrawal(self, amount: float) -> WithdrawalImpact:
        """Analyze the impact of a withdrawal on the system."""
        percentage = amount / self.total_balance if self.total_balance > 0 else 0
        
        scalability_impact = min(1.0, percentage * 2)  # Higher impact on scalability
        performance_impact = min(1.0, percentage * 1.5)  # Moderate impact on performance
        instance_risk = min(1.0, percentage * 3 if percentage > 0.3 else 0)  # Risk increases sharply above 30%
        profit_impact = min(1.0, percentage * 1.2)  # Proportional impact on profit
        
        avg_impact = (scalability_impact + performance_impact + instance_risk + profit_impact) / 4
        overall_safety = max(0, 1.0 - avg_impact)
        
        return WithdrawalImpact(
            scalability_impact=scalability_impact,
            performance_impact=performance_impact,
            instance_risk=instance_risk,
            profit_impact=profit_impact,
            overall_safety=overall_safety
        )
    
    def get_withdrawal_recommendations(self) -> Dict[str, Any]:
        """Get recommendations for optimal withdrawal."""
        optimal_amount = self.total_balance * 0.2
        
        return {
            "optimal_amount": optimal_amount,
            "message": "Recommended withdrawal amount based on current system metrics."
        }
    
    def record_withdrawal(self, amount: float, impact: WithdrawalImpact) -> None:
        """Record a withdrawal and its impact."""
        self.total_balance -= amount
        
        import datetime
        self.transactions.append({
            "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "type": "withdrawal",
            "amount": amount,
            "status": "completed",
            "status_class": "success"
        })
    
    def record_transaction(self, transaction_type: str, amount: float) -> None:
        """Record a transaction."""
        import datetime
        self.transactions.append({
            "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "type": transaction_type,
            "amount": amount,
            "status": "completed",
            "status_class": "success"
        })
    
    def get_transaction_history(self) -> List[Dict[str, Any]]:
        """Get transaction history."""
        return self.transactions

withdrawal_analyzer = WithdrawalAnalyzer()

def get_withdrawal_analyzer() -> WithdrawalAnalyzer:
    """Get the withdrawal analyzer instance."""
    return withdrawal_analyzer

def get_impact_color(impact_value: float) -> str:
    """Get color for impact meter based on impact value."""
    if impact_value < 0.3:
        return "#00ff9d"  # Green
    elif impact_value < 0.7:
        return "#ffcc00"  # Yellow
    else:
        return "#ff3333"  # Red

@router.get("/deposit-withdrawal", response_class=HTMLResponse)
async def deposit_withdrawal_page(request: Request, user: User = Depends(get_current_user)):
    """Render the deposit/withdrawal page."""
    analyzer = get_withdrawal_analyzer()
    recommendations = analyzer.get_withdrawal_recommendations()
    system_metrics = analyzer.get_system_metrics()
    
    transactions = analyzer.get_transaction_history()
    
    return templates.TemplateResponse(
        "deposit_withdrawal.html",
        {
            "request": request,
            "user": user,
            "total_balance": system_metrics["total_balance"],
            "daily_profit": system_metrics["profit_per_day"],
            "monthly_profit": system_metrics["profit_per_day"] * 30,
            "profit_percentage": (system_metrics["profit_per_day"] / system_metrics["total_balance"]) * 100 if system_metrics["total_balance"] > 0 else 0,
            "active_instances": system_metrics["active_instances"],
            "optimal_withdrawal": recommendations,
            "withdrawal_impact": None,  # Will be populated via API call
            "transactions": transactions,
            "get_impact_color": get_impact_color
        }
    )

@router.post("/api/deposit")
async def deposit_funds(deposit: DepositRequest, user: User = Depends(get_current_user)):
    """Deposit funds."""
    if deposit.amount <= 0:
        raise HTTPException(status_code=400, detail="Deposit amount must be positive")
    
    analyzer = get_withdrawal_analyzer()
    
    system_metrics = analyzer.get_system_metrics()
    new_balance = system_metrics["total_balance"] + deposit.amount
    
    analyzer.update_system_metrics(
        total_balance=new_balance,
        active_instances=system_metrics["active_instances"],
        new_instance_count=0,
        instance_age_days=analyzer.instance_age_days,
        profit_per_day=system_metrics["profit_per_day"]
    )
    
    analyzer.record_transaction("deposit", deposit.amount)
    
    return TransactionResponse(
        success=True,
        message=f"Successfully deposited ${deposit.amount:.2f}",
        new_balance=new_balance
    )

@router.post("/api/withdraw")
async def withdraw_funds(withdrawal: WithdrawalRequest, user: User = Depends(get_current_user)):
    """Withdraw funds."""
    if withdrawal.amount <= 0: 
        raise HTTPException(status_code=400, detail="Withdrawal amount must be positive")
    
    analyzer = get_withdrawal_analyzer()
    
    system_metrics = analyzer.get_system_metrics()
    
    if withdrawal.amount > system_metrics["total_balance"]:
        raise HTTPException(status_code=400, detail="Insufficient funds")
    
    impact = analyzer.analyze_withdrawal(withdrawal.amount)
    
    analyzer.record_withdrawal(withdrawal.amount, impact)
    
    updated_metrics = analyzer.get_system_metrics()
    
    return TransactionResponse(
        success=True,
        message=f"Successfully withdrew ${withdrawal.amount:.2f}",
        new_balance=updated_metrics["total_balance"],
        impact=impact.to_dict()
    )

@router.get("/api/analyze-withdrawal")
async def analyze_withdrawal_route(amount: float, user: User = Depends(get_current_user)):
    """Analyze withdrawal impact."""
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Withdrawal amount must be positive")
    
    analyzer = get_withdrawal_analyzer()
    
    system_metrics = analyzer.get_system_metrics()
    
    if amount > system_metrics["total_balance"]:
        raise HTTPException(status_code=400, detail="Insufficient funds")
    
    impact = analyzer.analyze_withdrawal(amount)
    
    return {
        "amount": amount,
        "impact": impact.to_dict()
    }

@router.get("/api/transaction-history")
async def get_transaction_history(user: User = Depends(get_current_user)):
    """Get transaction history."""
    analyzer = get_withdrawal_analyzer()
    transactions = analyzer.get_transaction_history()
    
    return {
        "transactions": transactions
    }
