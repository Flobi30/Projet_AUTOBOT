"""
Backtest schemas for AUTOBOT.

This module contains Pydantic models for backtest requests and responses.
"""

from pydantic import BaseModel
from typing import Dict, Any, List, Optional

class BacktestRequest(BaseModel):
    """
    Backtest request model.
    """
    strategy: str
    symbol: str
    timeframe: str
    start_date: str
    end_date: str
    parameters: Dict[str, Any] = {}
    
class BacktestResult(BaseModel):
    """
    Backtest result model.
    """
    strategy: str
    metrics: Dict[str, float]
    trades: Optional[List[Dict[str, Any]]] = None
