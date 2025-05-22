# File: src/autobot/schemas.py
from pydantic import BaseModel
from typing import Dict, Any, List, Optional

class BacktestRequest(BaseModel):
    strategy: str
    parameters: Dict[str, Any] = {}

class BacktestResult(BaseModel):
    strategy: str
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

class SetupRequest(BaseModel):
    alpha_api_key: str
    twelve_api_key: str
    fred_api_key: str
    news_api_key: str
    shopify_api_key: str
    ollama_api_key: str
    licence_key: str
    jwt_secret_key: str
    jwt_algorithm: str
    admin_user: str
    admin_password: str

class SetupResponse(BaseModel):
    success: bool
    message: str

class BacktestThresholds(BaseModel):
    min_sharpe: float = 1.5
    max_drawdown: float = 15.0
    min_pnl: float = 10.0
    auto_live: bool = False

class BacktestStatus(BaseModel):
    id: str
    strategy: str
    symbol: str
    progress: float
    status: str
    metrics: Dict[str, float] = {}
    equity_curve: Optional[Dict[str, list]] = None

class BacktestStatusResponse(BaseModel):
    backtests: List[BacktestStatus]

class TradingStatusResponse(BaseModel):
    status: str
    daily_pnl: float
    open_positions: int
    pending_orders: int
    recent_orders: List[Dict[str, Any]]
    equity_curve: Dict[str, list]

class ContinuousBacktestStatusResponse(BaseModel):
    enabled: bool
    completed: int
    running: int
    improvement: float
    recent_improvements: List[Dict[str, Any]]

class GhostingConfig(BaseModel):
    max_instances: int
    evasion_mode: str
    instance_type: str

class GhostingStatusResponse(BaseModel):
    active_instances: int
    max_instances: int
    cpu_usage: float
    memory_usage: float
    license_valid: bool
    instances: List[Dict[str, Any]]
    activity_history: Dict[str, list]

class LicenseStatusResponse(BaseModel):
    success: bool
    message: str
    license: Optional[Dict[str, Any]] = None

class LicenseHistoryResponse(BaseModel):
    history: List[Dict[str, Any]]

class LogsResponse(BaseModel):
    logs: List[Dict[str, Any]]
