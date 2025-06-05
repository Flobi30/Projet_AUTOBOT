"""
AUTOBOT Arbitrage Routes

This module implements the routes for the arbitrage page.
"""

import os
import logging
import time
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel



logger = logging.getLogger(__name__)

router = APIRouter()

templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui", "templates")
templates = Jinja2Templates(directory=templates_dir)

class ArbitrageSettings(BaseModel):
    min_profit_threshold: float
    max_execution_time_ms: int
    scan_interval: int
    exchanges: List[str]

class ArbitrageOpportunity(BaseModel):
    id: str
    symbol: str
    buy_exchange: str
    sell_exchange: str
    buy_price: float
    sell_price: float
    price_diff_percent: float
    expected_profit: float
    timestamp: int

class ArbitrageExecution(BaseModel):
    id: str
    opportunity_id: str
    timestamp: str
    symbol: str
    buy_exchange: str
    sell_exchange: str
    amount: float
    profit: float
    status: str
    status_class: str = "success"

arbitrage_settings = {
    "min_profit_threshold": 0.1,
    "max_execution_time_ms": 1000,
    "scan_interval": 5,
    "exchanges": ["binance", "coinbase", "kraken"]
}

opportunities = []
recent_executions = []

chart_data = {
    "labels": [f"{i}:00" for i in range(24)],
    "profit": [0] * 24,
    "opportunities": [0] * 24
}

exchanges = [
    {"id": "binance", "name": "Binance"},
    {"id": "coinbase", "name": "Coinbase"},
    {"id": "kraken", "name": "Kraken"},
    {"id": "kucoin", "name": "KuCoin"},
    {"id": "ftx", "name": "FTX"},
    {"id": "huobi", "name": "Huobi"}
]

@router.get("/arbitrage", response_class=HTMLResponse)
async def arbitrage_page(request: Request):
    """Render the arbitrage page."""
    profit_24h = sum(execution.profit for execution in recent_executions if execution.timestamp > time.time() - 86400)
    
    success_count = sum(1 for execution in recent_executions if execution.status == "completed")
    total_count = len(recent_executions) or 1  # Avoid division by zero
    success_rate = (success_count / total_count) * 100
    
    execution_times = [execution.timestamp for execution in recent_executions if execution.status == "completed"]
    avg_execution_ms = sum(execution_times) / len(execution_times) if execution_times else 0
    
    return templates.TemplateResponse(
        "arbitrage.html",
        {
            "request": request,
            "active_page": "arbitrage",
            "username": "AUTOBOT",
            "user_role": "admin",
            "user_role_display": "Administrateur",
            "opportunities_count": len(opportunities),
            "profit_24h": profit_24h,
            "avg_execution_ms": avg_execution_ms,
            "success_rate": success_rate,
            "settings": arbitrage_settings,
            "exchanges": exchanges,
            "opportunities": opportunities,
            "recent_executions": recent_executions,
            "chart_labels": chart_data["labels"],
            "chart_data": {
                "profit": chart_data["profit"],
                "opportunities": chart_data["opportunities"]
            }
        }
    )

@router.post("/api/arbitrage/settings")
async def update_arbitrage_settings(settings: ArbitrageSettings):
    """Update arbitrage settings."""
    global arbitrage_settings
    
    if settings.min_profit_threshold <= 0:
        raise HTTPException(status_code=400, detail="Minimum profit threshold must be positive")
    
    if settings.max_execution_time_ms <= 0:
        raise HTTPException(status_code=400, detail="Maximum execution time must be positive")
    
    if settings.scan_interval <= 0:
        raise HTTPException(status_code=400, detail="Scan interval must be positive")
    
    if not settings.exchanges:
        raise HTTPException(status_code=400, detail="At least one exchange must be selected")
    
    arbitrage_settings = {
        "min_profit_threshold": settings.min_profit_threshold,
        "max_execution_time_ms": settings.max_execution_time_ms,
        "scan_interval": settings.scan_interval,
        "exchanges": settings.exchanges
    }
    
    return {
        "success": True,
        "message": "Settings updated successfully",
        "settings": arbitrage_settings
    }

@router.post("/api/arbitrage/execute/{opportunity_id}")
async def execute_arbitrage(opportunity_id: str):
    """Execute an arbitrage opportunity."""
    opportunity = next((o for o in opportunities if o.id == opportunity_id), None)
    
    if not opportunity:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    
    execution_id = f"exec_{int(time.time())}_{len(recent_executions)}"
    
    execution = ArbitrageExecution(
        id=execution_id,
        opportunity_id=opportunity_id,
        timestamp=datetime.now().strftime("%H:%M:%S"),
        symbol=opportunity.symbol,
        buy_exchange=opportunity.buy_exchange,
        sell_exchange=opportunity.sell_exchange,
        amount=1.0,  # Mock amount
        profit=opportunity.expected_profit,
        status="completed"  # Mock status
    )
    
    recent_executions.append(execution)
    
    opportunities.remove(opportunity)
    
    hour = int(time.strftime("%H"))
    chart_data["profit"][hour] += opportunity.expected_profit
    
    return {
        "success": True,
        "message": "Arbitrage execution completed",
        "execution": execution
    }

@router.get("/api/arbitrage/opportunities")
async def get_arbitrage_opportunities():
    """Get arbitrage opportunities."""
    return {
        "opportunities": opportunities
    }

@router.get("/api/arbitrage/executions")
async def get_arbitrage_executions():
    """Get arbitrage executions."""
    return {
        "executions": recent_executions
    }

@router.post("/api/arbitrage/scan")
async def scan_arbitrage_opportunities():
    """Scan for arbitrage opportunities."""
    global opportunities
    
    new_opportunities = []
    
    import random
    
    symbols = ["BTC/USD", "ETH/USD", "SOL/USD", "ADA/USD", "DOT/USD"]
    
    for _ in range(random.randint(0, 3)):
        symbol = random.choice(symbols)
        buy_exchange = random.choice(arbitrage_settings["exchanges"])
        
        available_sell_exchanges = [e for e in arbitrage_settings["exchanges"] if e != buy_exchange]
        if not available_sell_exchanges:
            continue
            
        sell_exchange = random.choice(available_sell_exchanges)
        
        base_price = 1000 if symbol == "ETH/USD" else 30000 if symbol == "BTC/USD" else random.uniform(10, 100)
        buy_price = base_price * (1 - random.uniform(0.001, 0.005))
        sell_price = base_price * (1 + random.uniform(0.001, 0.005))
        
        price_diff_percent = ((sell_price - buy_price) / buy_price) * 100
        expected_profit = (sell_price - buy_price) * random.uniform(0.1, 1.0)
        
        if price_diff_percent >= arbitrage_settings["min_profit_threshold"]:
            opportunity_id = f"opp_{int(time.time())}_{len(opportunities)}"
            
            opportunity = ArbitrageOpportunity(
                id=opportunity_id,
                symbol=symbol,
                buy_exchange=buy_exchange,
                sell_exchange=sell_exchange,
                buy_price=buy_price,
                sell_price=sell_price,
                price_diff_percent=price_diff_percent,
                expected_profit=expected_profit,
                timestamp=int(time.time())
            )
            
            new_opportunities.append(opportunity)
    
    opportunities.extend(new_opportunities)
    
    hour = int(time.strftime("%H"))
    chart_data["opportunities"][hour] += len(new_opportunities)
    
    return {
        "success": True,
        "message": f"Found {len(new_opportunities)} new opportunities",
        "opportunities": new_opportunities
    }
