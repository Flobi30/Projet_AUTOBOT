# File: src/autobot/schemas.py
from pydantic import BaseModel
from typing import Dict, Any

class BacktestRequest(BaseModel):
    strategy: str = "moving_average"
    parameters: Dict[str, Any] = {}

class BacktestResult(BaseModel):
    strategy: str = "moving_average"
    metrics: Dict[str, float]

class APIKeyConfig(BaseModel):
    api_key: str
    api_secret: str

class APIKeysRequest(BaseModel):
    binance: APIKeyConfig = None
    coinbase: APIKeyConfig = None
    kraken: APIKeyConfig = None
    other: Dict[str, APIKeyConfig] = {}

class APIKeysResponse(BaseModel):
    status: str
    message: str

class CapitalStatus(BaseModel):
    initial_capital: float
    current_capital: float
    total_deposits: float
    total_withdrawals: float
    trading_profit: float
    total_profit: float
    roi: float
    available_for_withdrawal: float
    last_updated: str
