"""
Core routes for AUTOBOT.

This module contains API routes for core functionality.
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any

from autobot.autobot_security.auth.jwt_handler import oauth2_scheme, verify_license_key
from autobot.ecommerce.kpis import get_kpis
from autobot.guardian import get_logs
from autobot.autobot_guardian import get_health

router = APIRouter(tags=["core"])

@router.get('/metrics')
def metrics(
    token: str = Depends(oauth2_scheme),
    _ok: bool = Depends(verify_license_key)
):
    """
    Get system metrics.
    
    Returns:
        System metrics
    """
    return get_kpis()

@router.get('/logs')
def logs(
    token: str = Depends(oauth2_scheme),
    _ok: bool = Depends(verify_license_key)
):
    """
    Get system logs.
    
    Returns:
        System logs
    """
    return get_logs()

@router.get('/monitoring')
def monitoring(
    token: str = Depends(oauth2_scheme),
    _ok: bool = Depends(verify_license_key)
):
    """
    Get system health.
    
    Returns:
        System health
    """
    return get_health()

@router.get('/health')
def health():
    """
    Get system health status.
    
    Returns:
        System health status
    """
    return {"status": "ok"}
