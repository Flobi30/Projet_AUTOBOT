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
    from autobot.schemas import BacktestRequest, BacktestResult
    from autobot.ecommerce.kpis import get_kpis
    from autobot.autobot_guardian import AutobotGuardian
    from autobot.guardian import get_metrics
    from autobot.rl.train import start_training
    from autobot.backtest_engine import run_backtest
    
    from autobot.api.routes import api_router
    from autobot.api.orchestration_routes import router as orchestration_router
    from autobot.routes.health_routes import router as health_router
    from autobot.routes.prediction_routes import router as prediction_router
    from autobot.routes.auth_routes import router as auth_router
    from autobot.ui.mobile_routes import router as mobile_router
    from autobot.ui.arbitrage_routes import router as arbitrage_router
    from autobot.ui.backtest_routes import router as backtest_router
    from autobot.ui.deposit_withdrawal_routes import router as deposit_withdrawal_router
    from autobot.ui.chat_routes_custom import router as chat_router
    from autobot.ui.routes import router as ui_router
except ImportError as e:
    print(f"Warning: Could not import all routers: {e}")
    api_router = APIRouter()
    orchestration_router = APIRouter()
    health_router = APIRouter()
    prediction_router = APIRouter()
    auth_router = APIRouter()
    mobile_router = APIRouter()
    arbitrage_router = APIRouter()
    backtest_router = APIRouter()
    deposit_withdrawal_router = APIRouter()
    chat_router = APIRouter()
    ui_router = APIRouter()

@router.get('/backtest')
def backtest(symbol: str):
    """
    Run a backtest for a symbol.
    """
    return run_backtest(symbol)

@router.post('/backtest')
def backtest_post(request: BacktestRequest):
    """
    Run a backtest with the specified strategy and parameters.
    """
    try:
        result = BacktestResult(
            strategy=request.strategy,
            metrics={"profit": 0.5, "drawdown": 0.2, "sharpe": 1.5}
        )
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
router.include_router(orchestration_router)
router.include_router(health_router)
router.include_router(prediction_router)
router.include_router(auth_router)
router.include_router(mobile_router)  # Le préfixe "/mobile" est déjà défini dans le routeur
router.include_router(arbitrage_router)
router.include_router(backtest_router)
router.include_router(deposit_withdrawal_router)
router.include_router(chat_router)
router.include_router(ui_router)
