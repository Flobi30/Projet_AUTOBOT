"""
Routes pour l'interface utilisateur AUTOBOT
"""

import os
import json
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from autobot.autobot_security.auth.jwt_handler import get_current_user
from autobot.autobot_security.auth.user_manager import User, UserManager
from autobot.profit_engine import get_user_capital_data

logger = logging.getLogger(__name__)

current_dir = os.path.dirname(os.path.abspath(__file__))
templates_dir = os.path.join(current_dir, "templates")

router = APIRouter(tags=["ui"])
templates = Jinja2Templates(directory=templates_dir)

@router.get("/api/user/profile", response_class=JSONResponse)
async def get_user_profile(current_user: User = Depends(get_current_user)):
    """
    Get current user profile data.
    """
    return {
        "username": current_user.username,
        "role": current_user.role,
        "role_display": "Administrateur" if current_user.role == "admin" else "Utilisateur"
    }

@router.get("/api/trading/data", response_class=JSONResponse)
async def get_trading_data(current_user: User = Depends(get_current_user)):
    """
    Get trading data for React component.
    """
    return {
        "status": "active",
        "positions": [],
        "performance": 0.0
    }

@router.get("/api/ecommerce/data", response_class=JSONResponse)
async def get_ecommerce_data(current_user: User = Depends(get_current_user)):
    """
    Get e-commerce data for React component.
    """
    return {
        "products": [],
        "orders": [],
        "revenue": 0.0
    }

@router.get("/api/arbitrage/data", response_class=JSONResponse)
async def get_arbitrage_data(current_user: User = Depends(get_current_user)):
    """
    Get arbitrage data for React component.
    """
    return {
        "opportunities": [],
        "profit": 0.0
    }

@router.get("/api/backtest/current", response_class=JSONResponse)
async def get_backtest_current():
    """
    Get current backtest data for React component using real MetaLearner data.
    """
    try:
        from autobot.rl.meta_learning import create_meta_learner
        
        meta_learner = create_meta_learner()
        
        all_strategies = meta_learner.get_all_strategies()
        strategies = []
        
        total_performance = 0.0
        total_sharpe = 0.0
        total_trades = 0
        total_wins = 0
        
        if all_strategies:
            for strategy_id, strategy_data in all_strategies.items():
                performance = strategy_data.get('performance', 0.0)
                win_rate = strategy_data.get('win_rate', 0.0)
                sharpe = strategy_data.get('sharpe_ratio', 0.0)
                trades = strategy_data.get('total_trades', 0)
                
                strategies.append({
                    "name": strategy_id.replace('_', ' ').title(),
                    "status": "Active" if performance > 0 else "Inactive",
                    "performance": round(performance, 2)
                })
                
                total_performance += performance
                total_sharpe += sharpe
                total_trades += trades
                total_wins += int(trades * (win_rate / 100))
        
        num_strategies = len(strategies) if strategies else 1
        avg_performance = total_performance / num_strategies
        avg_sharpe = total_sharpe / num_strategies
        overall_win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0
        
        try:
            best_strategy = meta_learner.get_best_strategy()
            if best_strategy:
                strategy_id, strategy_data = best_strategy
                max_drawdown = strategy_data.get('max_drawdown', 0.15)
            else:
                max_drawdown = 0.15
        except:
            max_drawdown = 0.15
        
        return {
            "performance": round(avg_performance, 2),
            "sharpe_ratio": round(avg_sharpe, 2),
            "max_drawdown": round(max_drawdown, 3),
            "total_trades": total_trades,
            "win_rate": round(overall_win_rate, 1),
            "strategies": strategies
        }
        
    except Exception as e:
        logger.error(f"Error getting real backtest data: {e}")
        return {
            "performance": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown": 0.0,
            "total_trades": 0,
            "win_rate": 0.0,
            "strategies": [
                {"name": "Momentum", "status": "Inactive", "performance": 0.0},
                {"name": "Mean Reversion", "status": "Inactive", "performance": 0.0},
                {"name": "Breakout", "status": "Inactive", "performance": 0.0},
                {"name": "Trend Following", "status": "Inactive", "performance": 0.0},
                {"name": "Grid Trading", "status": "Inactive", "performance": 0.0}
            ]
        }

@router.get("/api/capital/data", response_class=JSONResponse)
async def get_capital_data_api(current_user: User = Depends(get_current_user)):
    """
    Get capital data for React component.
    """
    capital_data = get_user_capital_data(current_user.username)
    
    return {
        "initial_capital": capital_data["initial_capital"],
        "current_capital": capital_data["current_capital"],
        "profit": capital_data["profit"],
        "roi": capital_data["roi"],
        "trading_allocation": capital_data["trading_allocation"],
        "ecommerce_allocation": capital_data["ecommerce_allocation"],
        "capital_history": capital_data["capital_history"],
        "transactions": capital_data["transactions"]
    }

@router.get("/api/duplication/data", response_class=JSONResponse)
async def get_duplication_data(current_user: User = Depends(get_current_user)):
    """
    Get duplication data for React component.
    """
    return {
        "instances": [],
        "status": "ready"
    }

@router.get("/api/retrait-depot/data", response_class=JSONResponse)
async def get_retrait_depot_data(current_user: User = Depends(get_current_user)):
    """
    Get withdrawal/deposit data for React component.
    """
    capital_data = get_user_capital_data(current_user.username)
    
    return {
        "total_capital": capital_data["total_capital"],
        "available_for_withdrawal": capital_data["available_for_withdrawal"],
        "in_use": capital_data["in_use"],
        "transactions": capital_data["transactions"],
        "payment_methods": [],
        "daily_withdrawal_limit": 0,
        "monthly_withdrawal_limit": 0,
        "withdrawal_fee": 0,
        "deposit_fee": 0,
        "min_withdrawal": 0,
        "min_deposit": 0
    }

@router.get("/api/parametres/data", response_class=JSONResponse)
async def get_parametres_data(current_user: User = Depends(get_current_user)):
    """
    Get parameters data for React component.
    """
    return {
        "api_keys": {},
        "settings": {}
    }

@router.post("/api/login", response_class=JSONResponse)
async def login_api(request: Request):
    """
    API endpoint for React login.
    """
    try:
        data = await request.json()
        username = data.get("username")
        password = data.get("password")
        license_key = data.get("license_key")
        
        if not all([username, password, license_key]):
            raise HTTPException(status_code=400, detail="Missing credentials")
        
        user_manager = UserManager()
        user = user_manager.authenticate_user(username, password, license_key)
        
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        from autobot.autobot_security.auth.jwt_handler import create_access_token
        from datetime import timedelta
        
        access_token = create_access_token(
            data={"sub": user.username, "role": user.role},
            expires_delta=timedelta(hours=24)
        )
        
        return {"access_token": access_token, "token_type": "bearer"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/api/save-settings", response_class=JSONResponse)
async def save_settings(request: Request, current_user: User = Depends(get_current_user)):
    """
    Endpoint pour sauvegarder les paramètres utilisateur.
    
    Args:
        request: Request object
        current_user: Authenticated user
        
    Returns:
        JSONResponse: Status of the save operation
    """
    try:
        data = await request.json()
        
        required_sections = ["general", "api", "trading", "security"]
        for section in required_sections:
            if section not in data:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Section de paramètres requise manquante: {section}"
                )
        
        if "api" in data:
            api_settings = data["api"]
            user_manager = UserManager()
            
            for key_name in ["binance-api-key", "binance-api-secret", "openai-api-key", 
                            "superagi-api-key", "stripe-api-key"]:
                if key_name in api_settings and api_settings[key_name]:
                    field_name = key_name.replace("-", "_")
                    user_manager.update_user_data(
                        user_id=current_user.id,
                        field=field_name,
                        value=api_settings[key_name]
                    )
        
        user_manager = UserManager()
        user_manager.update_user_data(
            user_id=current_user.id,
            field="preferences",
            value=data
        )
        
        logger.info(f"Settings saved successfully for user {current_user.username}")
        
        return {
            "status": "success",
            "message": "Paramètres enregistrés avec succès"
        }
        
    except HTTPException as e:
        logger.error(f"Settings save error: {str(e)}")
        return JSONResponse(
            status_code=e.status_code,
            content={"status": "error", "message": e.detail}
        )
    except Exception as e:
        logger.error(f"Unexpected error saving settings: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Erreur lors de la sauvegarde des paramètres: {str(e)}"}
        )
