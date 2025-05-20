"""
Consolidated router module for AUTOBOT.

This module provides a consolidated router that includes all API routes.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from fastapi import APIRouter

router = APIRouter()

try:
    import src.autobot.security.auth
    
    from src.autobot.api.routes import api_router
    from src.autobot.routes.health_routes import router as health_router
    from src.autobot.routes.prediction_routes import router as prediction_router
    from src.autobot.routes.auth_routes import router as auth_router
    from src.autobot.ui.mobile_routes import router as mobile_router
    from src.autobot.ui.simplified_dashboard_routes import router as simplified_dashboard_router
    from src.autobot.ui.arbitrage_routes import router as arbitrage_router
    from src.autobot.ui.backtest_routes import router as backtest_router
    from src.autobot.ui.deposit_withdrawal_routes import router as deposit_withdrawal_router
    from src.autobot.ui.chat_routes_custom import router as chat_router
    from src.autobot.ui.routes import router as ui_router
except ImportError as e:
    print(f"Warning: Could not import all routers: {e}")
    api_router = APIRouter()
    health_router = APIRouter()
    prediction_router = APIRouter()
    auth_router = APIRouter()
    mobile_router = APIRouter()
    simplified_dashboard_router = APIRouter()
    arbitrage_router = APIRouter()
    backtest_router = APIRouter()
    deposit_withdrawal_router = APIRouter()
    chat_router = APIRouter()
    ui_router = APIRouter()

router.include_router(api_router)
router.include_router(health_router)
router.include_router(prediction_router)
router.include_router(auth_router)
router.include_router(mobile_router, prefix="/mobile")
router.include_router(simplified_dashboard_router, prefix="/simple")
router.include_router(arbitrage_router)
router.include_router(backtest_router)
router.include_router(deposit_withdrawal_router)
router.include_router(chat_router)
router.include_router(ui_router)
