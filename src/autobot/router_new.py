"""
Consolidated router module for AUTOBOT.

This module provides a consolidated router that includes all API routes.
"""

from fastapi import APIRouter

router = APIRouter()

from autobot.api.routes import api_router
from autobot.routes.health_routes import router as health_router
from autobot.routes.prediction_routes import router as prediction_router
from autobot.routes.auth_routes import router as auth_router
from autobot.ui.mobile_routes import router as mobile_router
from autobot.ui.simplified_dashboard_routes import router as simplified_dashboard_router
from autobot.ui.arbitrage_routes import router as arbitrage_router
from autobot.ui.backtest_routes import router as backtest_router
from autobot.ui.deposit_withdrawal_routes import router as deposit_withdrawal_router
from autobot.ui.chat_routes_custom import router as chat_router
from autobot.ui.routes import router as ui_router

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
