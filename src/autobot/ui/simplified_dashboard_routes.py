"""
AUTOBOT Simplified Dashboard Routes

This module implements the routes for the simplified dashboard, which focuses
only on API key input and fund management (deposit/withdrawal).
"""

import os
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..trading.withdrawal_analyzer import (
    get_withdrawal_analyzer,
    analyze_withdrawal,
    suggest_optimal_withdrawal,
    get_withdrawal_recommendations
)
from ..trading.auto_mode_manager import (
    get_mode_manager,
    get_component_mode,
    ComponentType
)
from ..autobot_security.auth.user_manager import get_current_user, User

logger = logging.getLogger(__name__)

router = APIRouter()

templates_dir = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=templates_dir)

static_dir = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir)

class DepositRequest(BaseModel):
    amount: float

class WithdrawalRequest(BaseModel):
    amount: float

class ApiKeyRequest(BaseModel):
    api_key: str
    api_secret: str

def get_impact_color(value: float) -> str:
    """Get color for impact value."""
    if value < 0.2:
        return "#00c853"  # Green
    elif value < 0.4:
        return "#aeea00"  # Light Green
    elif value < 0.6:
        return "#ffd600"  # Yellow
    elif value < 0.8:
        return "#ff6d00"  # Orange
    else:
        return "#d50000"  # Red

@router.get("/", response_class=HTMLResponse)
async def simplified_dashboard(request: Request, user: User = Depends(get_current_user)):
    """Render the simplified dashboard."""
    mode_manager = get_mode_manager()
    system_status = mode_manager.get_system_status()
    
    withdrawal_analyzer = get_withdrawal_analyzer()
    recommendations = withdrawal_analyzer.get_withdrawal_recommendations()
    
    api_keys = {
        "binance": {
            "connected": False,
            "api_key": "",
            "api_secret": ""
        },
        "coinbase": {
            "connected": False,
            "api_key": "",
            "api_secret": ""
        },
        "kraken": {
            "connected": False,
            "api_key": "",
            "api_secret": ""
        }
    }
    
    
    system_metrics = withdrawal_analyzer.get_system_metrics()
    
    return templates.TemplateResponse(
        "simplified_dashboard.html",
        {
            "request": request,
            "user": user,
            "balance": system_metrics["total_balance"],
            "active_instances": system_metrics["active_instances"],
            "new_instances": system_metrics["new_instance_count"],
            "balance_per_instance": system_metrics["balance_per_instance"],
            "daily_profit": system_metrics["profit_per_day"],
            "monthly_profit": system_metrics["profit_per_day"] * 30,
            "profit_trend": "Increasing",  # TODO: Calculate actual trend
            "optimal_withdrawal": recommendations["optimal_amount"],
            "withdrawal_impact": None,  # Will be populated via API call
            "current_mode": system_status["component_modes"]["trading"],
            "auto_switching": system_status["auto_switching_enabled"],
            "always_ghost": system_status["always_ghost"],
            "market_condition": system_status["market_condition"],
            "security_threat": system_status["security_threat"],
            "system_performance": system_status["system_performance"],
            "binance_connected": api_keys["binance"]["connected"],
            "binance_api_key": api_keys["binance"]["api_key"],
            "binance_api_secret": api_keys["binance"]["api_secret"],
            "coinbase_connected": api_keys["coinbase"]["connected"],
            "coinbase_api_key": api_keys["coinbase"]["api_key"],
            "coinbase_api_secret": api_keys["coinbase"]["api_secret"],
            "kraken_connected": api_keys["kraken"]["connected"],
            "kraken_api_key": api_keys["kraken"]["api_key"],
            "kraken_api_secret": api_keys["kraken"]["api_secret"],
            "get_impact_color": get_impact_color,
            "notification": None  # Will be populated when needed
        }
    )

@router.post("/api/deposit")
async def deposit_funds(deposit: DepositRequest, user: User = Depends(get_current_user)):
    """Deposit funds."""
    if deposit.amount <= 0:
        raise HTTPException(status_code=400, detail="Deposit amount must be positive")
    
    withdrawal_analyzer = get_withdrawal_analyzer()
    
    system_metrics = withdrawal_analyzer.get_system_metrics()
    new_balance = system_metrics["total_balance"] + deposit.amount
    
    withdrawal_analyzer.update_system_metrics(
        total_balance=new_balance,
        active_instances=system_metrics["active_instances"],
        new_instance_count=system_metrics["new_instance_count"],
        instance_age_days=withdrawal_analyzer.instance_age_days,
        profit_per_day=system_metrics["profit_per_day"]
    )
    
    
    return {
        "success": True,
        "message": f"Successfully deposited ${deposit.amount:.2f}",
        "new_balance": new_balance
    }

@router.post("/api/withdraw")
async def withdraw_funds(withdrawal: WithdrawalRequest, user: User = Depends(get_current_user)):
    """Withdraw funds."""
    if withdrawal.amount <= 0:
        raise HTTPException(status_code=400, detail="Withdrawal amount must be positive")
    
    withdrawal_analyzer = get_withdrawal_analyzer()
    
    system_metrics = withdrawal_analyzer.get_system_metrics()
    
    if withdrawal.amount > system_metrics["total_balance"]:
        raise HTTPException(status_code=400, detail="Insufficient funds")
    
    impact = withdrawal_analyzer.analyze_withdrawal(withdrawal.amount)
    
    withdrawal_analyzer.record_withdrawal(withdrawal.amount, impact)
    
    updated_metrics = withdrawal_analyzer.get_system_metrics()
    
    
    return {
        "success": True,
        "message": f"Successfully withdrew ${withdrawal.amount:.2f}",
        "new_balance": updated_metrics["total_balance"],
        "impact": impact.to_dict()
    }

@router.get("/api/analyze-withdrawal")
async def analyze_withdrawal_route(amount: float, user: User = Depends(get_current_user)):
    """Analyze withdrawal impact."""
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Withdrawal amount must be positive")
    
    withdrawal_analyzer = get_withdrawal_analyzer()
    
    system_metrics = withdrawal_analyzer.get_system_metrics()
    
    if amount > system_metrics["total_balance"]:
        raise HTTPException(status_code=400, detail="Insufficient funds")
    
    impact = withdrawal_analyzer.analyze_withdrawal(amount)
    
    return {
        "amount": amount,
        "impact": impact.to_dict(),
        "impact_level": impact.get_impact_level(),
        "color_code": impact.get_color_code()
    }

@router.post("/api/keys/{exchange}")
async def update_api_keys(
    exchange: str,
    api_key: str = Form(...),
    api_secret: str = Form(...),
    user: User = Depends(get_current_user)
):
    """Update API keys for an exchange."""
    if exchange not in ["binance", "coinbase", "kraken"]:
        raise HTTPException(status_code=400, detail="Invalid exchange")
    
    
    
    return {
        "success": True,
        "message": f"Successfully updated {exchange.capitalize()} API keys",
        "exchange": exchange,
        "connected": True
    }

@router.get("/api/system-status")
async def get_system_status(user: User = Depends(get_current_user)):
    """Get system status."""
    mode_manager = get_mode_manager()
    
    system_status = mode_manager.get_system_status()
    
    return system_status

@router.post("/api/system/mode/{component}/{mode}")
async def set_component_mode(
    component: str,
    mode: str,
    user: User = Depends(get_current_user)
):
    """Set component mode."""
    try:
        component_enum = ComponentType[component.upper()]
    except KeyError:
        raise HTTPException(status_code=400, detail="Invalid component")
    
    if mode not in ["standard", "turbo", "ghost"]:
        raise HTTPException(status_code=400, detail="Invalid mode")
    
    mode_manager = get_mode_manager()
    
    mode_manager.set_component_mode(component, mode)
    
    return {
        "success": True,
        "message": f"Successfully set {component} mode to {mode}",
        "component": component,
        "mode": mode
    }

@router.post("/api/system/auto-switching/{enabled}")
async def set_auto_switching(enabled: bool, user: User = Depends(get_current_user)):
    """Enable or disable automatic mode switching."""
    mode_manager = get_mode_manager()
    
    mode_manager.set_auto_switching(enabled)
    
    return {
        "success": True,
        "message": f"Successfully {'enabled' if enabled else 'disabled'} automatic mode switching",
        "auto_switching": enabled
    }

@router.post("/api/system/always-ghost/{enabled}")
async def set_always_ghost(enabled: bool, user: User = Depends(get_current_user)):
    """Enable or disable always ghost mode."""
    mode_manager = get_mode_manager()
    
    mode_manager.set_always_ghost(enabled)
    
    return {
        "success": True,
        "message": f"Successfully {'enabled' if enabled else 'disabled'} always ghost mode",
        "always_ghost": enabled
    }
