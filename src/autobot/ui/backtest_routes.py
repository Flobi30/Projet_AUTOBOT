"""
AUTOBOT Backtest Routes

This module implements the routes for the backtest page.
"""

import os
import logging
import time
import uuid
import random
import numpy as np
from datetime import datetime, timedelta
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

class BacktestRequest(BaseModel):
    strategy: str
    symbol: str
    timeframe: str
    start_date: str
    end_date: str
    initial_capital: float
    params: Optional[Dict[str, Any]] = None

class BacktestResult(BaseModel):
    id: str
    strategy: str
    symbol: str
    timeframe: str
    start_date: str
    end_date: str
    initial_capital: float
    params: Optional[Dict[str, Any]] = None
    metrics: Dict[str, Any]
    equity_curve: Dict[str, List[Any]]
    trades: List[Dict[str, Any]]

strategies = [
    {
        "id": "moving_average_crossover",
        "name": "Moving Average Crossover",
        "params": [
            {
                "name": "fast_period",
                "label": "Fast MA Period",
                "type": "number",
                "default": 10,
                "min": 2,
                "max": 200,
                "step": 1,
                "description": "Period for the fast moving average"
            },
            {
                "name": "slow_period",
                "label": "Slow MA Period",
                "type": "number",
                "default": 50,
                "min": 5,
                "max": 200,
                "step": 1,
                "description": "Period for the slow moving average"
            }
        ]
    },
    {
        "id": "rsi_strategy",
        "name": "RSI Strategy",
        "params": [
            {
                "name": "rsi_period",
                "label": "RSI Period",
                "type": "number",
                "default": 14,
                "min": 2,
                "max": 50,
                "step": 1,
                "description": "Period for the RSI indicator"
            },
            {
                "name": "overbought",
                "label": "Overbought Level",
                "type": "number",
                "default": 70,
                "min": 50,
                "max": 90,
                "step": 1,
                "description": "Level for overbought condition"
            },
            {
                "name": "oversold",
                "label": "Oversold Level",
                "type": "number",
                "default": 30,
                "min": 10,
                "max": 50,
                "step": 1,
                "description": "Level for oversold condition"
            }
        ]
    },
    {
        "id": "bollinger_bands",
        "name": "Bollinger Bands",
        "params": [
            {
                "name": "bb_period",
                "label": "BB Period",
                "type": "number",
                "default": 20,
                "min": 5,
                "max": 100,
                "step": 1,
                "description": "Period for Bollinger Bands"
            },
            {
                "name": "bb_std",
                "label": "Standard Deviation",
                "type": "number",
                "default": 2,
                "min": 1,
                "max": 4,
                "step": 0.1,
                "description": "Number of standard deviations"
            }
        ]
    }
]

symbols = ["BTC/USD", "ETH/USD", "SOL/USD", "ADA/USD", "DOT/USD", "XRP/USD", "DOGE/USD"]

saved_backtests = []

@router.get("/backtest", response_class=HTMLResponse)
async def backtest_page(request: Request, user: User = Depends(get_current_user)):
    """Render the backtest page."""
    return templates.TemplateResponse(
        "backtest.html",
        {
            "request": request,
            "user": user,
            "strategies": strategies,
            "symbols": symbols,
            "saved_backtests": saved_backtests
        }
    )

@router.post("/api/backtest/run")
async def run_backtest_strategy(request: BacktestRequest, user: User = Depends(get_current_user)):
    """Run a backtest with the specified strategy and parameters."""
    try:
        strategy = next((s for s in strategies if s["id"] == request.strategy), None)
        
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")
        
        
        start_date = datetime.strptime(request.start_date, "%Y-%m-%d")
        end_date = datetime.strptime(request.end_date, "%Y-%m-%d")
        
        date_range = []
        current_date = start_date
        while current_date <= end_date:
            if current_date.weekday() < 5:  # Only weekdays
                date_range.append(current_date.strftime("%Y-%m-%d"))
            current_date += timedelta(days=1)
        
        initial_capital = request.initial_capital
        equity = [initial_capital]
        
        volatility = 0.01
        if request.strategy == "rsi_strategy":
            volatility = 0.015
        elif request.strategy == "bollinger_bands":
            volatility = 0.02
        
        if request.params:
            if "fast_period" in request.params and "slow_period" in request.params:
                ratio = float(request.params["fast_period"]) / float(request.params["slow_period"])
                volatility *= (1 + ratio)
            elif "rsi_period" in request.params:
                volatility *= (20 / float(request.params["rsi_period"]))
            elif "bb_std" in request.params:
                volatility *= float(request.params["bb_std"])
        
        for i in range(1, len(date_range)):
            change = np.random.normal(0.0005, volatility)  # Slight upward bias
            equity.append(equity[-1] * (1 + change))
        
        trades = []
        current_position = None
        
        for i in range(1, len(date_range) - 1):
            if current_position is None and random.random() < 0.1:
                price = equity[i] / 10  # Mock price
                size = initial_capital / price * 0.1  # Use 10% of capital
                
                current_position = {
                    "type": "BUY",
                    "date": date_range[i],
                    "price": price,
                    "size": size
                }
                
                trades.append(current_position)
            
            elif current_position is not None and random.random() < 0.2:
                price = equity[i] / 10  # Mock price
                pl = (price - current_position["price"]) * current_position["size"]
                
                trades.append({
                    "type": "SELL",
                    "date": date_range[i],
                    "price": price,
                    "size": current_position["size"],
                    "pl": pl,
                    "cumulative": pl  # Will be updated below
                })
                
                current_position = None
        
        cumulative = 0
        for trade in trades:
            if "pl" in trade:
                cumulative += trade["pl"]
                trade["cumulative"] = cumulative
            else:
                trade["pl"] = 0
                trade["cumulative"] = cumulative
        
        total_return = ((equity[-1] - initial_capital) / initial_capital) * 100
        
        max_equity = equity[0]
        drawdowns = []
        
        for e in equity:
            max_equity = max(max_equity, e)
            drawdown = (max_equity - e) / max_equity * 100
            drawdowns.append(drawdown)
        
        max_drawdown = max(drawdowns)
        
        returns = [(equity[i] - equity[i-1]) / equity[i-1] for i in range(1, len(equity))]
        sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(252) if np.std(returns) > 0 else 0
        
        winning_trades = [t for t in trades if "pl" in t and t["pl"] > 0]
        win_rate = (len(winning_trades) / len(trades)) * 100 if trades else 0
        
        profit_factor = sum(t["pl"] for t in trades if "pl" in t and t["pl"] > 0) / abs(sum(t["pl"] for t in trades if "pl" in t and t["pl"] < 0)) if sum(t["pl"] for t in trades if "pl" in t and t["pl"] < 0) != 0 else 0
        
        avg_trade = sum(t["pl"] for t in trades if "pl" in t) / len(trades) if trades else 0
        avg_win = sum(t["pl"] for t in winning_trades) / len(winning_trades) if winning_trades else 0
        avg_loss = sum(t["pl"] for t in trades if "pl" in t and t["pl"] < 0) / len([t for t in trades if "pl" in t and t["pl"] < 0]) if len([t for t in trades if "pl" in t and t["pl"] < 0]) > 0 else 0
        
        best_trade = max([t["pl"] for t in trades if "pl" in t], default=0)
        worst_trade = min([t["pl"] for t in trades if "pl" in t], default=0)
        
        days = (end_date - start_date).days
        annual_return = ((equity[-1] / equity[0]) ** (365 / days) - 1) * 100 if days > 0 else 0
        
        result_id = str(uuid.uuid4())
        
        result = BacktestResult(
            id=result_id,
            strategy=request.strategy,
            symbol=request.symbol,
            timeframe=request.timeframe,
            start_date=request.start_date,
            end_date=request.end_date,
            initial_capital=request.initial_capital,
            params=request.params,
            metrics={
                "total_return": total_return,
                "max_drawdown": max_drawdown,
                "sharpe": sharpe,
                "win_rate": win_rate,
                "total_trades": len(trades),
                "profit_factor": profit_factor,
                "avg_trade": avg_trade,
                "avg_win": avg_win,
                "avg_loss": avg_loss,
                "best_trade": best_trade,
                "worst_trade": worst_trade,
                "annual_return": annual_return
            },
            equity_curve={
                "dates": date_range,
                "values": equity
            },
            trades=trades
        )
        
        saved_backtests.append({
            "id": result_id,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "strategy": strategy["name"],
            "symbol": request.symbol,
            "timeframe": request.timeframe,
            "return": round(total_return, 2),
            "sharpe": round(sharpe, 2)
        })
        
        return result
        
    except Exception as e:
        logger.error(f"Error running backtest: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/backtest/{backtest_id}")
async def get_backtest(backtest_id: str, user: User = Depends(get_current_user)):
    """Get a saved backtest."""
    backtest = next((b for b in saved_backtests if b["id"] == backtest_id), None)
    
    if not backtest:
        raise HTTPException(status_code=404, detail="Backtest not found")
    
    
    
    start_date = datetime.strptime("2023-01-01", "%Y-%m-%d")
    end_date = datetime.strptime("2023-12-31", "%Y-%m-%d")
    
    date_range = []
    current_date = start_date
    while current_date <= end_date:
        if current_date.weekday() < 5:  # Only weekdays
            date_range.append(current_date.strftime("%Y-%m-%d"))
        current_date += timedelta(days=1)
    
    initial_capital = 10000
    equity = [initial_capital]
    
    volatility = 0.01
    
    for i in range(1, len(date_range)):
        change = np.random.normal(0.0005, volatility)  # Slight upward bias
        equity.append(equity[-1] * (1 + change))
    
    trades = []
    current_position = None
    
    for i in range(1, len(date_range) - 1):
        if current_position is None and random.random() < 0.1:
            price = equity[i] / 10  # Mock price
            size = initial_capital / price * 0.1  # Use 10% of capital
            
            current_position = {
                "type": "BUY",
                "date": date_range[i],
                "price": price,
                "size": size
            }
            
            trades.append(current_position)
        
        elif current_position is not None and random.random() < 0.2:
            price = equity[i] / 10  # Mock price
            pl = (price - current_position["price"]) * current_position["size"]
            
            trades.append({
                "type": "SELL",
                "date": date_range[i],
                "price": price,
                "size": current_position["size"],
                "pl": pl,
                "cumulative": pl  # Will be updated below
            })
            
            current_position = None
    
    cumulative = 0
    for trade in trades:
        if "pl" in trade:
            cumulative += trade["pl"]
            trade["cumulative"] = cumulative
        else:
            trade["pl"] = 0
            trade["cumulative"] = cumulative
    
    total_return = ((equity[-1] - initial_capital) / initial_capital) * 100
    
    max_equity = equity[0]
    drawdowns = []
    
    for e in equity:
        max_equity = max(max_equity, e)
        drawdown = (max_equity - e) / max_equity * 100
        drawdowns.append(drawdown)
    
    max_drawdown = max(drawdowns)
    
    returns = [(equity[i] - equity[i-1]) / equity[i-1] for i in range(1, len(equity))]
    sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(252) if np.std(returns) > 0 else 0
    
    winning_trades = [t for t in trades if "pl" in t and t["pl"] > 0]
    win_rate = (len(winning_trades) / len(trades)) * 100 if trades else 0
    
    profit_factor = sum(t["pl"] for t in trades if "pl" in t and t["pl"] > 0) / abs(sum(t["pl"] for t in trades if "pl" in t and t["pl"] < 0)) if sum(t["pl"] for t in trades if "pl" in t and t["pl"] < 0) != 0 else 0
    
    avg_trade = sum(t["pl"] for t in trades if "pl" in t) / len(trades) if trades else 0
    avg_win = sum(t["pl"] for t in winning_trades) / len(winning_trades) if winning_trades else 0
    avg_loss = sum(t["pl"] for t in trades if "pl" in t and t["pl"] < 0) / len([t for t in trades if "pl" in t and t["pl"] < 0]) if len([t for t in trades if "pl" in t and t["pl"] < 0]) > 0 else 0
    
    best_trade = max([t["pl"] for t in trades if "pl" in t], default=0)
    worst_trade = min([t["pl"] for t in trades if "pl" in t], default=0)
    
    days = (end_date - start_date).days
    annual_return = ((equity[-1] / equity[0]) ** (365 / days) - 1) * 100 if days > 0 else 0
    
    return {
        "id": backtest_id,
        "strategy_id": "moving_average_crossover",
        "symbol": "BTC/USD",
        "timeframe": "1d",
        "start_date": "2023-01-01",
        "end_date": "2023-12-31",
        "initial_capital": 10000,
        "params": {
            "fast_period": 10,
            "slow_period": 50
        },
        "metrics": {
            "total_return": total_return,
            "max_drawdown": max_drawdown,
            "sharpe": sharpe,
            "win_rate": win_rate,
            "total_trades": len(trades),
            "profit_factor": profit_factor,
            "avg_trade": avg_trade,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "best_trade": best_trade,
            "worst_trade": worst_trade,
            "annual_return": annual_return
        },
        "equity_curve": {
            "dates": date_range,
            "values": equity
        },
        "trades": trades
    }

@router.delete("/api/backtest/{backtest_id}")
async def delete_backtest(backtest_id: str, user: User = Depends(get_current_user)):
    """Delete a saved backtest."""
    global saved_backtests
    
    backtest = next((b for b in saved_backtests if b["id"] == backtest_id), None)
    
    if not backtest:
        raise HTTPException(status_code=404, detail="Backtest not found")
    
    saved_backtests = [b for b in saved_backtests if b["id"] != backtest_id]
    
    return {
        "success": True,
        "message": "Backtest deleted successfully"
    }
