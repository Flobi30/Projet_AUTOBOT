# File: src/autobot/schemas.py
from pydantic import BaseModel
from typing import Dict, Any

class BacktestRequest(BaseModel):
    strategy: str
    parameters: Dict[str, Any] = {}

class BacktestResult(BaseModel):
    strategy: str
    metrics: Dict[str, float]
