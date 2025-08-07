"""
Mobile-specific routes for AUTOBOT.
Provides API endpoints and page routes for mobile interface.
"""
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from typing import Dict, Any, Optional
import os
import logging

from ..autobot_security.auth.jwt_handler import get_current_user

logger = logging.getLogger(__name__)

current_dir = os.path.dirname(os.path.abspath(__file__))
templates_dir = os.path.join(current_dir, "templates")

templates = Jinja2Templates(directory=templates_dir)

router = APIRouter(tags=["Mobile"])


@router.get("/api/mobile/detect", summary="Detect if client is mobile")
async def detect_mobile(user_agent: Optional[str] = None):
    """
    Detect if the client is a mobile device.
    
    Args:
        user_agent: User agent string
        
    Returns:
        Dict: Mobile detection result
    """
    if not user_agent:
        return {"is_mobile": False}
    
    mobile_keywords = [
        "android", "iphone", "ipod", "ipad", "windows phone", "blackberry", 
        "opera mini", "mobile", "tablet"
    ]
    
    user_agent_lower = user_agent.lower()
    is_mobile = any(keyword in user_agent_lower for keyword in mobile_keywords)
    
    return {
        "is_mobile": is_mobile,
        "redirect_url": "/mobile" if is_mobile else "/dashboard"
    }

@router.get("/api/mobile/portfolio", summary="Get portfolio data for mobile")
async def get_mobile_portfolio(current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Get portfolio data optimized for mobile display.
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        Dict: Portfolio data
    """
    try:
        return {
            "total_value": 12450.78,
            "change_percentage": 2.4,
            "change_value": 290.45,
            "assets": [
                {"symbol": "BTC", "value": 5230.45, "percentage": 42},
                {"symbol": "ETH", "value": 3120.33, "percentage": 25},
                {"symbol": "EUR", "value": 4100.00, "percentage": 33}
            ],
            "history": [
                {"date": "2025-05-08", "value": 11800},
                {"date": "2025-05-09", "value": 11950},
                {"date": "2025-05-10", "value": 12100},
                {"date": "2025-05-11", "value": 11900},
                {"date": "2025-05-12", "value": 12200},
                {"date": "2025-05-13", "value": 12350},
                {"date": "2025-05-14", "value": 12450}
            ]
        }
    except Exception as e:
        logger.error(f"Error getting mobile portfolio data: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting mobile portfolio data: {str(e)}")

@router.get("/api/mobile/recent-trades", summary="Get recent trades for mobile")
async def get_mobile_recent_trades(current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Get recent trades optimized for mobile display.
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        Dict: Recent trades data
    """
    try:
        return {
            "trades": [
                {
                    "pair": "BTC/EUR",
                    "type": "BUY",
                    "amount": 0.05,
                    "price": 28450.00,
                    "profit": 142.25,
                    "time": "15:30"
                },
                {
                    "pair": "ETH/EUR",
                    "type": "SELL",
                    "amount": 1.2,
                    "price": 1820.00,
                    "profit": -36.40,
                    "time": "14:45"
                },
                {
                    "pair": "XRP/EUR",
                    "type": "BUY",
                    "amount": 500,
                    "price": 0.48,
                    "profit": 24.00,
                    "time": "13:15"
                }
            ]
        }
    except Exception as e:
        logger.error(f"Error getting mobile recent trades: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting mobile recent trades: {str(e)}")

@router.get("/api/mobile/ai-insights", summary="Get AI insights for mobile")
async def get_mobile_ai_insights(current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Get AI insights optimized for mobile display.
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        Dict: AI insights data
    """
    try:
        return {
            "insights": [
                {
                    "type": "market_trend",
                    "title": "Market Trend",
                    "content": "BTC showing bullish pattern with strong support at €27,800. Consider increasing position if price holds above this level."
                },
                {
                    "type": "portfolio",
                    "title": "Portfolio Suggestion",
                    "content": "Current asset allocation is too concentrated in BTC (42%). Consider diversifying by adding SOL and ADA to reduce volatility."
                },
                {
                    "type": "ecommerce",
                    "title": "E-commerce Opportunity",
                    "content": "Detected 15 new unsold electronics items with high profit potential. Estimated profit margin: 35-40%."
                }
            ]
        }
    except Exception as e:
        logger.error(f"Error getting mobile AI insights: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting mobile AI insights: {str(e)}")

@router.post("/api/mobile/update-exchange", summary="Update exchange API settings")
async def update_exchange_settings(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Update exchange API settings.
    
    Args:
        request: Request object
        current_user: Current authenticated user
        
    Returns:
        Dict: Status of the update operation
    """
    try:
        data = await request.json()
        
        required_fields = ["exchange", "api_key", "api_secret"]
        for field in required_fields:
            if field not in data or not data[field]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Missing required field: {field}"
                )
        
        exchange = data["exchange"]
        api_key = data["api_key"]
        api_secret = data["api_secret"]
        use_testnet = data.get("use_testnet", False)
        
        logger.info(f"Updating {exchange} API settings for user {current_user['username']}")
        
        # )
        
        return {
            "status": "success",
            "message": f"{exchange.capitalize()} API settings updated successfully"
        }
        
    except HTTPException as e:
        logger.error(f"Error updating exchange settings: {str(e)}")
        raise e
    except Exception as e:
        logger.error(f"Unexpected error updating exchange settings: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error updating exchange settings: {str(e)}"
        )

@router.post("/api/mobile/disconnect-exchange", summary="Disconnect exchange API")
async def disconnect_exchange(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Disconnect exchange API.
    
    Args:
        request: Request object
        current_user: Current authenticated user
        
    Returns:
        Dict: Status of the disconnect operation
    """
    try:
        data = await request.json()
        
        if "exchange" not in data or not data["exchange"]:
            raise HTTPException(
                status_code=400,
                detail="Missing required field: exchange"
            )
        
        exchange = data["exchange"]
        
        logger.info(f"Disconnecting {exchange} API for user {current_user['username']}")
        
        # )
        
        return {
            "status": "success",
            "message": f"{exchange.capitalize()} disconnected successfully"
        }
        
    except HTTPException as e:
        logger.error(f"Error disconnecting exchange: {str(e)}")
        raise e
    except Exception as e:
        logger.error(f"Unexpected error disconnecting exchange: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error disconnecting exchange: {str(e)}"
        )
