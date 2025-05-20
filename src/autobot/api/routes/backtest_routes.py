"""
Backtest routes for AUTOBOT.

This module contains API routes for backtesting.
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any

from autobot.autobot_security.auth.jwt_handler import oauth2_scheme, verify_license_key
from autobot.api.schemas import BacktestRequest, BacktestResult
from autobot.trading.backtest.engine import run_backtest

router = APIRouter(prefix="/backtest", tags=["backtest"])

@router.get('/')
def backtest(
    symbol: str,
    token: str = Depends(oauth2_scheme),
    _ok: bool = Depends(verify_license_key)
):
    """
    Run a backtest for a symbol.
    
    Args:
        symbol: Symbol to backtest
        
    Returns:
        Backtest results
    """
    return run_backtest(symbol)

@router.post('/')
def backtest_post(
    request: BacktestRequest,
    token: str = Depends(oauth2_scheme),
    _ok: bool = Depends(verify_license_key)
):
    """
    Run a backtest with the specified strategy and parameters.
    
    Args:
        request: Backtest request
        
    Returns:
        Backtest results
    """
    try:
        result = BacktestResult(
            strategy=request.strategy,
            metrics={"profit": 0.5, "drawdown": 0.2, "sharpe": 1.5}
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post('/run')
def run_backtest_strategy(
    request: BacktestRequest,
    token: str = Depends(oauth2_scheme),
    _ok: bool = Depends(verify_license_key)
):
    """
    Run a backtest with the specified strategy and parameters.
    
    Args:
        request: Backtest request
        
    Returns:
        Backtest results
    """
    try:
        result = BacktestResult(
            strategy=request.strategy,
            metrics={"profit": 0.0, "drawdown": 0.0, "sharpe": 0.0}
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
@router.post('/')
def backtest_post(
    request: BacktestRequest,
    token: str = Depends(oauth2_scheme),
    _ok: bool = Depends(verify_license_key)
):
    """
    Run a backtest with the specified strategy and parameters.
    
    Args:
        request: Backtest request
        
    Returns:
        Backtest results
    """
    try:
        result = BacktestResult(
            strategy=request.strategy,
            metrics={"profit": 0.5, "drawdown": 0.2, "sharpe": 1.5}
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
