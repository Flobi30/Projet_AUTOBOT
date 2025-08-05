"""
API routes for Analytics functionality
"""

import os
import json
import logging
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timedelta
import random

from ..auth_simple import get_current_user, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

@router.get("/summary")
async def get_analytics_summary(current_user: User = Depends(get_current_user)) -> Dict[str, Any]:
    """
    Get comprehensive analytics data for the Analytics page
    """
    try:
        performance_data = []
        base_portfolio = 5000
        base_benchmark = 5000
        
        for i in range(30):
            date = (datetime.now() - timedelta(days=29-i)).strftime("%m/%d")
            portfolio_value = base_portfolio + (i * 50) + random.randint(-100, 200)
            benchmark_value = base_benchmark + (i * 30) + random.randint(-50, 100)
            
            performance_data.append({
                "date": date,
                "portfolio": portfolio_value,
                "benchmark": benchmark_value
            })
        
        market_pairs = [
            {"pair": "BTC/USD", "trend": "Haussier", "signal": "BUY"},
            {"pair": "ETH/USD", "trend": "Neutre", "signal": "HOLD"},
            {"pair": "ADA/USD", "trend": "Haussier", "signal": "BUY"},
            {"pair": "DOT/USD", "trend": "Baissier", "signal": "SELL"},
            {"pair": "LINK/USD", "trend": "Haussier", "signal": "BUY"}
        ]
        
        return {
            "kpis": {
                "annualizedReturn": 24.8,
                "sharpeRatio": 1.84,
                "winRate": 68
            },
            "performanceVsBenchmark": performance_data,
            "riskMetrics": {
                "volatility": 12.5,
                "alpha": 2.3,
                "maxDrawdown": -4.2
            },
            "marketAnalysis": market_pairs
        }
    except Exception as e:
        logger.error(f"Error getting analytics summary: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving analytics data")
