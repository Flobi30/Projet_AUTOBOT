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
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


class BacktestRequest(BaseModel):
    strategy: str
    symbol: str
    timeframe: str
    start_date: str
    end_date: str
    initial_capital: float
    params: Optional[Dict[str, Any]] = None
    parameters: Optional[Dict[str, Any]] = None

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

saved_backtests = [
    {
        "id": "demo-1",
        "date": "2025-08-06 00:45:00",
        "strategy": "MultiTimeframe_RSI",
        "symbol": "BTC/USD",
        "timeframe": "Multi-TF (5m, 15m, 1h)",
        "return": 8.42,
        "sharpe": 1.84,
        "multi_timeframe": True,
        "auto_generated": True
    },
    {
        "id": "demo-2", 
        "date": "2025-08-06 00:30:00",
        "strategy": "MultiTimeframe_Bollinger",
        "symbol": "ETH/USD",
        "timeframe": "Multi-TF (15m, 1h, 4h)",
        "return": 12.15,
        "sharpe": 2.31,
        "multi_timeframe": True,
        "auto_generated": True
    },
    {
        "id": "demo-3",
        "date": "2025-08-06 00:15:00", 
        "strategy": "MultiTimeframe_RSI",
        "symbol": "BTC/USD",
        "timeframe": "Multi-TF (1h, 4h, 1d)",
        "return": -2.18,
        "sharpe": 0.95,
        "multi_timeframe": True,
        "auto_generated": True
    },
    {
        "id": "demo-4",
        "date": "2025-08-06 00:00:00",
        "strategy": "MultiTimeframe_Bollinger", 
        "symbol": "SOL/USD",
        "timeframe": "Multi-TF (5m, 15m, 1h)",
        "return": 15.67,
        "sharpe": 2.89,
        "multi_timeframe": True,
        "auto_generated": True
    }
]


@router.post("/api/backtest/run")
async def run_backtest_strategy(request: BacktestRequest):
    """Run a backtest with real strategy calculations."""
    try:
        if request.strategy in ["MultiTimeframe_RSI", "MultiTimeframe_Bollinger"]:
            from ..services.enhanced_backtest_service import run_multi_timeframe_backtest
            
            timeframes = request.parameters.get('timeframes', ['5m', '15m', '1h', '4h']) if request.parameters else ['5m', '15m', '1h', '4h']
            
            result = run_multi_timeframe_backtest(
                strategy_name=request.strategy,
                symbol=request.symbol,
                start_date=request.start_date,
                end_date=request.end_date,
                timeframes=timeframes
            )
            
            result_id = str(uuid.uuid4())
            
            backtest_result = BacktestResult(
                id=result_id,
                strategy=request.strategy,
                symbol=request.symbol,
                timeframe="Multi-TF",
                start_date=request.start_date,
                end_date=request.end_date,
                initial_capital=request.initial_capital,
                params=request.parameters,
                metrics=result.get("metrics", {}),
                equity_curve=result.get("equity_curve", {"dates": [], "values": []}),
                trades=result.get("trades", [])
            )
            
            saved_backtests.append({
                "id": result_id,
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "strategy": request.strategy,
                "symbol": request.symbol,
                "timeframe": "Multi-TF",
                "return": round(result.get("total_return", 0), 2),
                "sharpe": round(result.get("sharpe_ratio", 0), 2),
                "multi_timeframe": True
            })
            
            return backtest_result
        else:
            from ..services.backtest_service import get_backtest_service
            
            backtest_service = get_backtest_service()
            
            result = backtest_service.run_backtest(
                strategy_id=request.strategy,
                symbol=request.symbol,
                start_date=request.start_date,
                end_date=request.end_date,
                initial_capital=request.initial_capital,
                params=request.params
            )
            
            result_id = str(uuid.uuid4())
            
            backtest_result = BacktestResult(
                id=result_id,
                strategy=request.strategy,
                symbol=request.symbol,
                timeframe=request.timeframe,
                start_date=request.start_date,
                end_date=request.end_date,
                initial_capital=request.initial_capital,
                params=request.params,
                metrics=result["metrics"],
                equity_curve=result["equity_curve"],
                trades=result["trades"]
            )
            
            saved_backtests.append({
                "id": result_id,
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "strategy": next((s["name"] for s in strategies if s["id"] == request.strategy), request.strategy),
                "symbol": request.symbol,
                "timeframe": request.timeframe,
                "return": round(result["metrics"]["total_return"], 2),
                "sharpe": round(result["metrics"]["sharpe"], 2)
            })
            
            return backtest_result
        
    except Exception as e:
        logger.error(f"Error running backtest: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/backtest/runs")
async def get_backtest_runs():
    """Get list of saved backtest runs for activity display"""
    try:
        sorted_backtests = sorted(saved_backtests, key=lambda x: x.get("date", ""), reverse=True)
        recent_backtests = sorted_backtests[:50]
        
        return {
            "runs": recent_backtests,
            "total_count": len(saved_backtests),
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    except Exception as e:
        logger.error(f"Error getting backtest runs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/backtest/run-multi-timeframe")
async def run_multi_timeframe_backtest(request: BacktestRequest):
    """Run backtest with multi-timeframe strategy"""
    try:
        from ..services.enhanced_backtest_service import run_multi_timeframe_backtest
        
        result = run_multi_timeframe_backtest(
            strategy_name=request.strategy,
            symbol=request.symbol,
            start_date=request.start_date,
            end_date=request.end_date,
            timeframes=request.parameters.get('timeframes', ['5m', '15m', '1h', '4h']) if request.parameters else ['5m', '15m', '1h', '4h']
        )
        
        backtest_id = str(uuid.uuid4())
        saved_backtests.append({
            "id": backtest_id,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "strategy": request.strategy,
            "symbol": request.symbol,
            "timeframe": "Multi-TF",
            "return": round(result.get("total_return", 0), 2),
            "sharpe": round(result.get("sharpe_ratio", 0), 2),
            "multi_timeframe": True
        })
        
        return result
        
    except Exception as e:
        logger.error(f"Multi-timeframe backtest error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/backtest/{backtest_id}")
async def get_backtest(backtest_id: str):
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
    
    initial_capital = 500
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
        "initial_capital": 500,
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
async def delete_backtest(backtest_id: str):
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

@router.get("/api/backtest/strategies")
async def get_available_strategies():
    """Get list of available strategies including multi-timeframe ones"""
    all_strategies = strategies + [
        {
            "id": "MultiTimeframe_RSI",
            "name": "Multi-Timeframe RSI",
            "params": [
                {
                    "name": "period",
                    "label": "RSI Period",
                    "type": "number",
                    "default": 21,
                    "min": 5,
                    "max": 50,
                    "step": 1,
                    "description": "Period for RSI calculation"
                },
                {
                    "name": "overbought",
                    "label": "Overbought Level",
                    "type": "number",
                    "default": 75,
                    "min": 60,
                    "max": 90,
                    "step": 1,
                    "description": "RSI overbought threshold"
                },
                {
                    "name": "oversold",
                    "label": "Oversold Level",
                    "type": "number",
                    "default": 25,
                    "min": 10,
                    "max": 40,
                    "step": 1,
                    "description": "RSI oversold threshold"
                }
            ]
        },
        {
            "id": "MultiTimeframe_Bollinger",
            "name": "Multi-Timeframe Bollinger Bands",
            "params": [
                {
                    "name": "window",
                    "label": "BB Window",
                    "type": "number",
                    "default": 25,
                    "min": 10,
                    "max": 50,
                    "step": 1,
                    "description": "Bollinger Bands window period"
                },
                {
                    "name": "num_std",
                    "label": "Standard Deviations",
                    "type": "number",
                    "default": 2.5,
                    "min": 1.0,
                    "max": 4.0,
                    "step": 0.1,
                    "description": "Number of standard deviations"
                }
            ]
        }
    ]
    
    return {"strategies": all_strategies}
