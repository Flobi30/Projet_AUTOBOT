"""
API routes module for AUTOBOT.

This module contains API route definitions for the AUTOBOT system.
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, Optional

from autobot.autobot_security.auth.jwt_handler import oauth2_scheme, verify_license_key
from autobot.ecommerce.kpis import get_kpis
from autobot.autobot_guardian import get_logs, get_health
from autobot.rl.train import start_training

from autobot.api.routes.backtest_routes import router as backtest_router
from autobot.api.routes.core_routes import router as core_router
from autobot.api.routes.plugin_routes import router as plugin_router
from autobot.api.routes.provider_routes import router as provider_router

api_router = APIRouter()

api_router.include_router(backtest_router)
api_router.include_router(core_router)
api_router.include_router(plugin_router)
api_router.include_router(provider_router)

@api_router.get('/predict')
def predict(
    token: str = Depends(oauth2_scheme),
    _ok: bool = Depends(verify_license_key)
):
    return {'prediction': None}

@api_router.post('/train')
def train(
    token: str = Depends(oauth2_scheme),
    _ok: bool = Depends(verify_license_key)
):
    return {'job_id': start_training()}
