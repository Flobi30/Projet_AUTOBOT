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
        self.transactions_file = "transactions.json"
        self.transactions = self._load_transactions()
        
    def _load_transactions(self) -> List[Dict[str, Any]]:
        """Load transactions from file if it exists."""
        import json
        if os.path.exists(self.transactions_file):
            try:
                with open(self.transactions_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading transactions: {str(e)}")
                return []
        return []
        
    def _save_transactions(self) -> None:
        """Save transactions to file."""
        import json
        try:
            with open(self.transactions_file, 'w') as f:
                json.dump(self.transactions, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving transactions: {str(e)}")
    
    def get_system_metrics(self, user_id: str = None) -> Dict[str, Any]:
        """
        Get system metrics for a specific user or default metrics if user_id is None.
        
        Args:
            user_id: Optional user ID to get metrics for
            
        Returns:
            Dict: System metrics
        """
        default_metrics = {
            "total_balance": 0.0,
            "active_instances": 0,
            "instance_age_days": 0,
            "profit_per_day": 0.0
        }
        
        if not user_id:
            return default_metrics
            
        # Calculate user balance from transactions
        user_transactions = [t for t in self.transactions if t.get("user_id") == user_id]
        
        total_balance = 0.0
        for transaction in user_transactions:
            if transaction["type"] == "deposit":
                total_balance += transaction["amount"]
            elif transaction["type"] == "withdrawal":
                total_balance -= transaction["amount"]
        
        profit_transactions = [t for t in user_transactions if t.get("profit", 0) > 0]
        
        import datetime
        thirty_days_ago = (datetime.datetime.now() - datetime.timedelta(days=30)).strftime("%Y-%m-%d")
        
        recent_profits = [
            t.get("profit", 0) for t in profit_transactions 
            if t.get("date", "").split()[0] >= thirty_days_ago
        ]
        
        daily_profit = sum(recent_profits) / 30 if recent_profits else 0
        
        active_instances = len(set([t.get("instance_id") for t in user_transactions if t.get("instance_id")]))
        
        instance_age_days = 30  # Default to 30 days if no instance data
        
        if active_instances > 0:
            instance_dates = [
                datetime.datetime.strptime(t.get("date", ""), "%Y-%m-%d %H:%M:%S")
                for t in user_transactions 
                if t.get("instance_id") and t.get("date")
            ]
            
            if instance_dates:
                oldest_date = min(instance_dates)
                instance_age_days = (datetime.datetime.now() - oldest_date).days
        
        return {
            "total_balance": total_balance,
            "active_instances": active_instances,
            "instance_age_days": instance_age_days,
            "profit_per_day": daily_profit
        }
    
    def update_system_metrics(self, user_id: str, total_balance: float = None, 
                             active_instances: int = None, new_instance_count: int = None, 
                             instance_age_days: int = None, profit_per_day: float = None) -> None:
        """
        Update system metrics is no longer needed as metrics are calculated from transactions.
        This method is kept for backward compatibility.
        """
        # System metrics are now calculated from transactions
        # This method doesn't need to do anything as metrics are derived from transactions
        pass
    
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
    
    def record_withdrawal(self, user_id: str, amount: float, impact: WithdrawalImpact) -> None:
        """
        Record a withdrawal and its impact for a specific user.
        
        Args:
            user_id: User ID
            amount: Withdrawal amount
            impact: Withdrawal impact analysis
        """
        if not user_id:
            logger.error("Cannot record withdrawal: Missing user ID")
            return
            
        if amount <= 0:
            logger.error(f"Cannot record withdrawal: Invalid amount {amount}")
            return
            
        metrics = self.get_system_metrics(user_id)
        if amount > metrics["total_balance"]:
            logger.error(f"Cannot record withdrawal: Insufficient funds (requested: {amount}, available: {metrics['total_balance']})")
            return
            
        self.record_transaction(
            user_id=user_id,
            transaction_type="withdrawal",
            amount=amount
        )
    
    def record_transaction(self, user_id: str, transaction_type: str, amount: float, 
                           instance_id: str = None, profit: float = 0.0) -> None:
        """
        Record a transaction for a specific user.
        
        Args:
            user_id: User ID
            transaction_type: Type of transaction (deposit, withdrawal)
            amount: Transaction amount
            instance_id: Optional instance ID for tracking
            profit: Optional profit amount
        """
        import datetime
        
        if not user_id:
            logger.error("Cannot record transaction: Missing user ID")
            return
            
        if amount <= 0:
            logger.error(f"Cannot record transaction: Invalid amount {amount}")
            return
            
        transaction = {
            "user_id": user_id,
            "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "type": transaction_type,
            "amount": amount,
            "status": "completed",
            "status_class": "success"
        }
        
        if instance_id:
            transaction["instance_id"] = instance_id
            
        if profit > 0:
            transaction["profit"] = profit
            
        self.transactions.append(transaction)
        self._save_transactions()
    
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
    """
    Deposit funds to user account.
    
    Args:
        deposit: Deposit request with amount
        user: Authenticated user
        
    Returns:
        TransactionResponse: Transaction result
    """
    if deposit.amount <= 0:
        raise HTTPException(status_code=400, detail="Deposit amount must be positive")
    
    analyzer = get_withdrawal_analyzer()
    
    try:
        analyzer.record_transaction(
            user_id=user.id,
            transaction_type="deposit",
            amount=deposit.amount
        )
        
        system_metrics = analyzer.get_system_metrics(user_id=user.id)
        
        return TransactionResponse(
            success=True,
            message=f"Successfully deposited ${deposit.amount:.2f}",
            new_balance=system_metrics["total_balance"]
        )
    except Exception as e:
        logger.error(f"Deposit error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing deposit: {str(e)}")


@router.post("/api/withdraw")
async def withdraw_funds(withdrawal: WithdrawalRequest, user: User = Depends(get_current_user)):
    """
    Withdraw funds from user account.
    
    Args:
        withdrawal: Withdrawal request with amount
        user: Authenticated user
        
    Returns:
        TransactionResponse: Transaction result with impact analysis
    """
    # Validate withdrawal amount
    if withdrawal.amount <= 0: 
        raise HTTPException(status_code=400, detail="Withdrawal amount must be positive")
    
    analyzer = get_withdrawal_analyzer()
    
    system_metrics = analyzer.get_system_metrics(user_id=user.id)
    
    if withdrawal.amount > system_metrics["total_balance"]:
        raise HTTPException(status_code=400, detail="Insufficient funds")
    
    try:
        impact = analyzer.analyze_withdrawal(withdrawal.amount)
        
        analyzer.record_withdrawal(user_id=user.id, amount=withdrawal.amount, impact=impact)
        
        updated_metrics = analyzer.get_system_metrics(user_id=user.id)
        
        return TransactionResponse(
            success=True,
            message=f"Successfully withdrew ${withdrawal.amount:.2f}",
            new_balance=updated_metrics["total_balance"],
            impact=impact.to_dict()
        )
    except Exception as e:
        logger.error(f"Withdrawal error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing withdrawal: {str(e)}")


@router.get("/api/analyze-withdrawal")
async def analyze_withdrawal_route(amount: float, user: User = Depends(get_current_user)):
    """
    Analyze withdrawal impact for a specific user.
    
    Args:
        amount: Withdrawal amount to analyze
        user: Authenticated user
        
    Returns:
        Dict: Analysis result with impact metrics
    """
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Withdrawal amount must be positive")
    
    analyzer = get_withdrawal_analyzer()
    
    system_metrics = analyzer.get_system_metrics(user_id=user.id)
    
    if amount > system_metrics["total_balance"]:
        raise HTTPException(status_code=400, detail="Insufficient funds")
    
    try:
        impact = analyzer.analyze_withdrawal(amount)
        
        return {
            "amount": amount,
            "impact": impact.to_dict(),
            "current_balance": system_metrics["total_balance"]
        }
    except Exception as e:
        logger.error(f"Withdrawal analysis error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error analyzing withdrawal: {str(e)}")


@router.get("/api/transaction-history")
async def get_transaction_history(user: User = Depends(get_current_user)):
    """
    Get transaction history for the authenticated user.
    
    Args:
        user: Authenticated user
        
    Returns:
        Dict: User's transaction history
    """
    analyzer = get_withdrawal_analyzer()
    
    try:
        # Get all transactions
        all_transactions = analyzer.get_transaction_history()
        
        user_transactions = [
            t for t in all_transactions 
            if t.get("user_id") == user.id
        ]
        
        return {
            "transactions": user_transactions
        }
    except Exception as e:
        logger.error(f"Error retrieving transaction history: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving transaction history: {str(e)}")

@router.post("/api/stripe/create-checkout-session")
async def create_checkout_session(request: dict):
    """
    Create real Stripe checkout session for deposits - Public access for stripe-autobot.fr
    """
    try:
        import os
        from ..services.stripe_service import StripeService
        
        stripe_api_key = os.getenv("STRIPE_SECRET_KEY")
        if not stripe_api_key:
            raise HTTPException(status_code=500, detail="Stripe API key not configured")
        stripe_service = StripeService(api_key=stripe_api_key)
        
        amount = request.get("amount", 5000)
        currency = request.get("currency", "eur")
        
        session_data = stripe_service.create_checkout_session(amount, currency)
        
        return {
            "sessionId": session_data["sessionId"],
            "url": session_data["url"]
        }
    except Exception as e:
        logger.error(f"Error creating checkout session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/stripe/create-payout")
async def create_payout(request: dict):
    """
    Create real Stripe payout for withdrawals - Public access for stripe-autobot.fr
    """
    try:
        import os
        from ..services.stripe_service import StripeService
        
        stripe_api_key = os.getenv("STRIPE_SECRET_KEY")
        if not stripe_api_key:
            raise HTTPException(status_code=500, detail="Stripe API key not configured")
        stripe_service = StripeService(api_key=stripe_api_key)
        
        amount = request.get("amount", 10000)
        currency = request.get("currency", "eur")
        destination = request.get("destination")
        
        if not destination:
            raise HTTPException(status_code=400, detail="Destination account required for payout")
        
        payout_data = stripe_service.create_payout(amount, currency, destination)
        
        return payout_data
    except Exception as e:
        logger.error(f"Error creating payout: {e}")
        raise HTTPException(status_code=500, detail=str(e))
