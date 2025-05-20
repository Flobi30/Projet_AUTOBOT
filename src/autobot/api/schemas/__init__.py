"""
API schemas module for AUTOBOT.

This module contains Pydantic models for API request and response validation.
"""

from pydantic import BaseModel
from typing import Dict, Any, List, Optional

class BacktestRequest(BaseModel):
    """
    Request model for backtest endpoint.
    """
    strategy: str
    parameters: Dict[str, Any] = {}

class BacktestResult(BaseModel):
    """
    Response model for backtest endpoint.
    """
    strategy: str
    metrics: Dict[str, float]
