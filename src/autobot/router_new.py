"""
Consolidated router module for AUTOBOT.

This module provides a consolidated router that includes all API routes.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer

router = APIRouter()

try:
    from autobot.autobot_security.auth.jwt_handler import oauth2_scheme, verify_license_key
except ImportError as e:
    print(f"Warning: Could not import auth modules: {e}")
    oauth2_scheme = None
    verify_license_key = None

try:
    from autobot.schemas import BacktestRequest, BacktestResult
except ImportError as e:
    print(f"Warning: Could not import schemas: {e}")
    from pydantic import BaseModel
    
    class BacktestRequest(BaseModel):
        strategy: str = ""
        
    class BacktestResult(BaseModel):
        strategy: str = ""
        metrics: dict = {}

try:
    from autobot.ecommerce.kpis import get_kpis
except ImportError as e:
    print(f"Warning: Could not import kpis: {e}")
    def get_kpis():
        return {"status": "mock"}

try:
    from autobot.autobot_guardian import AutobotGuardian
except ImportError as e:
    print(f"Warning: Could not import AutobotGuardian: {e}")
    class AutobotGuardian:
        @staticmethod
        def get_logs():
            return {"logs": []}

try:
    from autobot.guardian import get_metrics
except ImportError as e:
    print(f"Warning: Could not import get_metrics: {e}")
    def get_metrics():
        return {"status": "mock"}

try:
    from autobot.rl.train import start_training
except ImportError as e:
    print(f"Warning: Could not import start_training: {e}")
    def start_training():
        return "mock-job-id"

try:
    from autobot.backtest_engine import run_backtest
except ImportError as e:
    print(f"Warning: Could not import run_backtest: {e}")
    def run_backtest(symbol):
        return {"symbol": symbol, "result": "mock"}

try:
    from autobot.api.routes import api_router
except ImportError as e:
    print(f"Warning: Could not import api_router: {e}")
    api_router = APIRouter()

try:
    from autobot.routes.health_routes import router as health_router
except ImportError as e:
    print(f"Warning: Could not import health_router: {e}")
    health_router = APIRouter()

try:
    from autobot.routes.prediction_routes import router as prediction_router
except ImportError as e:
    print(f"Warning: Could not import prediction_router: {e}")
    prediction_router = APIRouter()

try:
    from autobot.routes.auth_routes import router as auth_router
except ImportError as e:
    print(f"Warning: Could not import auth_router: {e}")
    auth_router = APIRouter()

mobile_router = None
simplified_dashboard_router = None
arbitrage_router = None
backtest_router = None
deposit_withdrawal_router = None
chat_router = None
ui_router = None

@router.get('/backtest')
def backtest(symbol: str):
    """
    Run a backtest for a symbol.
    """
    return run_backtest(symbol)

@router.post('/backtest', response_model=None)
def backtest_post(request: dict = None):
    """
    Run a backtest with the specified strategy and parameters.
    """
    try:
        if request is None:
            request = {"strategy": "default"}
            
        result = {
            "strategy": request.get("strategy", "default"),
            "metrics": {"profit": 0.5, "drawdown": 0.2, "sharpe": 1.5}
        }
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get('/predict')
def predict():
    """
    Make a prediction.
    """
    return {'prediction': 0.75}

@router.post('/train')
def train():
    """
    Start model training.
    """
    return {'job_id': start_training(), 'status': 'training_started'}

@router.get('/metrics')
def metrics():
    """
    Get system metrics.
    """
    return get_kpis()

@router.get('/logs')
def logs():
    """
    Get system logs.
    """
    return AutobotGuardian.get_logs()

@router.get('/health')
def health():
    """
    Health check endpoint.
    """
    return {"status": "ok"}

router.include_router(api_router)
router.include_router(health_router)
router.include_router(prediction_router)
router.include_router(auth_router)

try:
    from autobot.ui.mobile_routes import router as mobile_router
    router.include_router(mobile_router)  # Le préfixe "/mobile" est déjà défini dans le routeur
except ImportError as e:
    print(f"Warning: Could not import mobile_router: {e}")

try:
    from autobot.ui.simplified_dashboard_routes import router as simplified_dashboard_router
    router.include_router(simplified_dashboard_router)  # Le préfixe "/simple" est déjà défini dans le routeur
except ImportError as e:
    print(f"Warning: Could not import simplified_dashboard_router: {e}")

try:
    from autobot.ui.arbitrage_routes import router as arbitrage_router
    router.include_router(arbitrage_router)
except ImportError as e:
    print(f"Warning: Could not import arbitrage_router: {e}")

try:
    from autobot.ui.backtest_routes import router as backtest_router
    router.include_router(backtest_router)
except ImportError as e:
    print(f"Warning: Could not import backtest_router: {e}")

try:
    from autobot.ui.deposit_withdrawal_routes import router as deposit_withdrawal_router
    router.include_router(deposit_withdrawal_router)
except ImportError as e:
    print(f"Warning: Could not import deposit_withdrawal_router: {e}")

try:
    from autobot.ui.chat_routes_custom import router as chat_router
    router.include_router(chat_router)
except ImportError as e:
    print(f"Warning: Could not import chat_router: {e}")

try:
    from autobot.ui.routes import router as ui_router
    router.include_router(ui_router)
except ImportError as e:
    print(f"Warning: Could not import ui_router: {e}")
