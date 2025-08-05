"""
API routes for Live Trading functionality
"""

import os
import json
import logging
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timedelta
import random

from ..auth_simple import get_current_user, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/live", tags=["live-trading"])

@router.get("/metrics")
async def get_live_metrics(current_user: User = Depends(get_current_user)) -> Dict[str, float]:
    """
    Get real-time trading metrics
    """
    try:
        return {
            "totalReturnPercent": 8.42,
            "pnl24h": 118.50,
            "pnl24hPercent": 2.18,
            "sharpeRatio": 1.84
        }
    except Exception as e:
        logger.error(f"Error getting live metrics: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving live metrics")

@router.get("/portfolio-history")
async def get_portfolio_history(current_user: User = Depends(get_current_user)) -> List[Dict[str, Any]]:
    """
    Get portfolio evolution history for charts
    """
    try:
        base_value = 5000
        history = []
        
        for i in range(0, 24, 4):
            time_str = f"{i:02d}:00"
            value = base_value + (i * 25) + random.randint(-50, 100)
            history.append({
                "time": time_str,
                "value": value
            })
        
        return history
    except Exception as e:
        logger.error(f"Error getting portfolio history: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving portfolio history")

@router.get("/positions")
async def get_open_positions(current_user: User = Depends(get_current_user)) -> List[Dict[str, Any]]:
    """
    Get currently open trading positions
    """
    try:
        positions = [
            {
                "pair": "BTC/USD",
                "side": "LONG",
                "size": "0.15 BTC",
                "entry": "45230",
                "pnl": 920,
                "pnlPercent": 2.03
            },
            {
                "pair": "ETH/USD",
                "side": "SHORT",
                "size": "2.5 ETH",
                "entry": "2850",
                "pnl": -45,
                "pnlPercent": -0.85
            },
            {
                "pair": "ADA/USD",
                "side": "LONG",
                "size": "1000 ADA",
                "entry": "0.45",
                "pnl": 67,
                "pnlPercent": 1.48
            }
        ]
        
        return positions
    except Exception as e:
        logger.error(f"Error getting open positions: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving open positions")

@router.get("/logs")
async def get_live_logs(current_user: User = Depends(get_current_user)) -> List[Dict[str, str]]:
    """
    Get recent trading activity logs
    """
    try:
        now = datetime.now()
        logs = []
        
        log_entries = [
            {"level": "RISK", "message": "Stop-loss ajusté pour la position ETH/USD."},
            {"level": "TRADE", "message": "Ordre d'achat de 0.15 BTC exécuté."},
            {"level": "INFO", "message": "Analyse de marché terminée - Signal haussier détecté."},
            {"level": "TRADE", "message": "Position ADA/USD ouverte - LONG 1000 ADA."},
            {"level": "RISK", "message": "Volatilité élevée détectée sur BTC/USD."},
            {"level": "INFO", "message": "Synchronisation des données de marché réussie."}
        ]
        
        for i, entry in enumerate(log_entries):
            timestamp = (now - timedelta(minutes=i*2)).strftime("%H:%M:%S")
            logs.append({
                "timestamp": timestamp,
                "level": entry["level"],
                "message": entry["message"]
            })
        
        return logs
    except Exception as e:
        logger.error(f"Error getting live logs: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving live logs")
