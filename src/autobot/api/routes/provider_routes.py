"""
Provider routes for AUTOBOT.

This module contains API routes for data providers.
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any

from autobot.autobot_security.auth.jwt_handler import oauth2_scheme, verify_license_key

from autobot.providers.alphavantage import get_intraday as get_alphavantage
from autobot.providers.ccxt_provider import fetch_ticker as get_ccxt_provider
from autobot.providers.newsapi import get_time_series as get_newsapi
from autobot.providers.shopify import get_shopify
from autobot.providers.fred import get_time_series as get_fred

router = APIRouter(prefix="/provider", tags=["providers"])

@router.get('/alphavantage/{param}')
def prov_alphavantage(
    param: str,
    token: str = Depends(oauth2_scheme),
    _ok: bool = Depends(verify_license_key)
): 
    """
    Get data from AlphaVantage provider.
    
    Args:
        param: Parameter for the provider
        
    Returns:
        Data from the provider
    """
    return get_alphavantage(param)

@router.get('/ccxt_provider/{param}')
def prov_ccxt_provider(
    param: str,
    token: str = Depends(oauth2_scheme),
    _ok: bool = Depends(verify_license_key)
): 
    """
    Get data from CCXT provider.
    
    Args:
        param: Parameter for the provider
        
    Returns:
        Data from the provider
    """
    return get_ccxt_provider(param)

@router.get('/newsapi/{param}')
def prov_newsapi(
    param: str,
    token: str = Depends(oauth2_scheme),
    _ok: bool = Depends(verify_license_key)
): 
    """
    Get data from NewsAPI provider.
    
    Args:
        param: Parameter for the provider
        
    Returns:
        Data from the provider
    """
    return get_newsapi(param)

@router.get('/shopify/{param}')
def prov_shopify(
    param: str,
    token: str = Depends(oauth2_scheme),
    _ok: bool = Depends(verify_license_key)
): 
    """
    Get data from Shopify provider.
    
    Args:
        param: Parameter for the provider
        
    Returns:
        Data from the provider
    """
    return get_shopify(param)

@router.get('/fred/{param}')
def prov_fred(
    param: str,
    token: str = Depends(oauth2_scheme),
    _ok: bool = Depends(verify_license_key)
): 
    """
    Get data from FRED provider.
    
    Args:
        param: Parameter for the provider
        
    Returns:
        Data from the provider
    """
    return get_fred(param)
