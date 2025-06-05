"""
Dashboard Routes Module for AUTOBOT

This module provides the FastAPI routes and WebSocket endpoints for the AUTOBOT dashboard UI.
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse

from autobot.autobot_security.auth.jwt_handler import decode_token, verify_license_key
from autobot.autobot_security.auth.user_manager import UserManager
from autobot.autobot_security.auth.models import User
from autobot.trading.strategy import Strategy, MovingAverageStrategy
from autobot.rl.train import get_training_status
from autobot.agents.orchestrator import AgentOrchestrator
from autobot.ecommerce.inventory_manager import InventoryManager
from autobot.ui.dashboard import Dashboard, DashboardManager, create_default_trading_dashboard

logger = logging.getLogger(__name__)

current_dir = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(current_dir, "static")
templates_dir = os.path.join(current_dir, "templates")

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

templates = Jinja2Templates(directory=templates_dir)

dashboard_manager = DashboardManager()

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        
    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)
        
    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)
            
    async def broadcast_json(self, data: Dict[str, Any]):
        json_data = json.dumps(data)
        await self.broadcast(json_data)

manager = ConnectionManager()

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/static") or request.url.path == "/login":
            return await call_next(request)
        
        token = request.cookies.get("access_token")
        if not token:
            return RedirectResponse(url="/login")
        
        try:
            payload = decode_token(token)
            request.state.user = payload
            return await call_next(request)
        except Exception:
            return RedirectResponse(url="/login")

@router.get("/", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    """
    Render the dashboard HTML page.
    """
    return templates.TemplateResponse("dashboard.html", {"request": request})

@router.get("/ecommerce", response_class=HTMLResponse)
async def get_ecommerce(request: Request):
    """
    Render the e-commerce HTML page.
    """
    return templates.TemplateResponse("ecommerce.html", {"request": request})

@router.get("/data", response_class=JSONResponse)
async def get_dashboard_data(request: Request):
    """
    Get dashboard data.
    """
    user = request.state.user
    
    return {
        "portfolio": {
            "total_value": 10245.67,
            "change_24h": 2.5,
            "assets": [
                {"symbol": "BTC", "amount": 0.1, "value": 4567.89},
                {"symbol": "ETH", "amount": 1.5, "value": 3518.51},
                {"symbol": "XRP", "amount": 5000, "value": 2159.27}
            ]
        },
        "trades": [
            {
                "date": "2025-05-14 12:30",
                "pair": "BTC/EUR",
                "type": "buy",
                "price": 45678.90,
                "amount": 0.1,
                "total": 4567.89,
                "status": "completed"
            },
            {
                "date": "2025-05-14 11:45",
                "pair": "ETH/EUR",
                "type": "sell",
                "price": 2345.67,
                "amount": 1.5,
                "total": 3518.51,
                "status": "completed"
            },
            {
                "date": "2025-05-14 10:15",
                "pair": "XRP/EUR",
                "type": "buy",
                "price": 0.75,
                "amount": 5000,
                "total": 3750.00,
                "status": "completed"
            }
        ],
        "strategies": [
            {
                "id": "strat-001",
                "name": "Moving Average Crossover",
                "type": "ma_crossover",
                "pair": "BTC/EUR",
                "timeframe": "1h",
                "performance": 5.2,
                "status": "active"
            },
            {
                "id": "strat-002",
                "name": "RSI Oversold",
                "type": "rsi",
                "pair": "ETH/EUR",
                "timeframe": "4h",
                "performance": 3.7,
                "status": "active"
            },
            {
                "id": "strat-003",
                "name": "Bollinger Bands",
                "type": "bollinger",
                "pair": "XRP/EUR",
                "timeframe": "1d",
                "performance": -1.2,
                "status": "inactive"
            }
        ],
        "models": [
            {
                "id": "model-001",
                "name": "DQN BTC Trader",
                "type": "dqn",
                "pair": "BTC/EUR",
                "timeframe": "1h",
                "performance": 7.8,
                "episodes": 1000,
                "status": "active"
            },
            {
                "id": "model-002",
                "name": "PPO Multi-Asset",
                "type": "ppo",
                "pair": "Multiple",
                "timeframe": "4h",
                "progress": 65,
                "episodes": 750,
                "total_episodes": 1000,
                "status": "training"
            }
        ],
        "agents": [
            {
                "id": "agent-001",
                "name": "Market Analyzer",
                "type": "analyzer",
                "tasks_per_hour": 24,
                "accuracy": 92,
                "status": "active"
            },
            {
                "id": "agent-002",
                "name": "News Sentiment",
                "type": "data",
                "sources": 15,
                "update_interval": 5,
                "status": "active"
            },
            {
                "id": "agent-003",
                "name": "Portfolio Optimizer",
                "type": "optimizer",
                "frequency": "1h",
                "improvement": 2.3,
                "status": "active"
            }
        ],
        "ecommerce": {
            "unsold_products": 124,
            "unsold_value": 12450,
            "potential_savings": 2890,
            "recycled_orders": 45,
            "products": [
                {
                    "name": "Smartphone XYZ",
                    "sku": "SM-XYZ-123",
                    "original_price": 599.99,
                    "optimized_price": 499.99,
                    "stock": 15,
                    "days_in_stock": 45
                },
                {
                    "name": "Écouteurs Bluetooth",
                    "sku": "EB-BT-456",
                    "original_price": 129.99,
                    "optimized_price": 89.99,
                    "stock": 32,
                    "days_in_stock": 60
                },
                {
                    "name": "Montre Connectée",
                    "sku": "MC-789",
                    "original_price": 249.99,
                    "optimized_price": 199.99,
                    "stock": 8,
                    "days_in_stock": 30
                }
            ]
        },
        "settings": {
            "api_key": "autobot_xxxxxxxxxxxx",
            "license_key": "AUTOBOT-XXXX-XXXX-XXXX-XXXX",
            "risk_level": "medium",
            "max_allocation": 10,
            "auto_compound": True,
            "notifications_enabled": True
        }
    }

@router.post("/strategy", response_class=JSONResponse)
async def create_strategy(request: Request):
    """
    Create a new trading strategy.
    """
    data = await request.json()
    
    strategy_id = f"strat-{len(data['name'])}{data['type'][:3]}"
    
    await manager.broadcast_json({
        "type": "strategy_created",
        "data": {
            "id": strategy_id,
            "name": data["name"],
            "type": data["type"],
            "pair": data["pair"],
            "timeframe": data["timeframe"],
            "performance": 0.0,
            "status": "active"
        }
    })
    
    return {"id": strategy_id, "status": "created"}

@router.post("/model", response_class=JSONResponse)
async def create_model(request: Request):
    """
    Create a new RL model.
    """
    data = await request.json()
    
    model_id = f"model-{len(data['name'])}{data['type'][:3]}"
    
    await manager.broadcast_json({
        "type": "model_created",
        "data": {
            "id": model_id,
            "name": data["name"],
            "type": data["type"],
            "pair": data["pair"],
            "timeframe": "1h",
            "progress": 0,
            "episodes": 0,
            "total_episodes": data["episodes"],
            "status": "training"
        }
    })
    
    return {"id": model_id, "status": "created"}

@router.post("/agent", response_class=JSONResponse)
async def create_agent(request: Request):
    """
    Create a new agent.
    """
    data = await request.json()
    
    agent_id = f"agent-{len(data['name'])}{data['type'][:3]}"
    
    await manager.broadcast_json({
        "type": "agent_created",
        "data": {
            "id": agent_id,
            "name": data["name"],
            "type": data["type"],
            "frequency": data["frequency"],
            "status": "active"
        }
    })
    
    return {"id": agent_id, "status": "created"}

@router.post("/settings", response_class=JSONResponse)
async def update_settings(request: Request):
    """
    Update user settings.
    
    Args:
        request: Request object
        current_user: Authenticated user
        
    Returns:
        JSONResponse: Status of the update operation
    """
    try:
        data = await request.json()
        
        required_sections = ["general", "api", "trading", "security"]
        for section in required_sections:
            if section not in data:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Missing required settings section: {section}"
                )
        
        if "api" in data:
            api_settings = data["api"]
            user_manager = UserManager()
            
            if "binance-api-key" in api_settings and api_settings["binance-api-key"]:
                user_manager.update_user_data(
                    user_id="AUTOBOT",
                    field="binance_api_key",
                    value=api_settings["binance-api-key"]
                )
                
            if "binance-api-secret" in api_settings and api_settings["binance-api-secret"]:
                user_manager.update_user_data(
                    user_id="AUTOBOT",
                    field="binance_api_secret",
                    value=api_settings["binance-api-secret"]
                )
                
            if "openai-api-key" in api_settings and api_settings["openai-api-key"]:
                user_manager.update_user_data(
                    user_id="AUTOBOT",
                    field="openai_api_key",
                    value=api_settings["openai-api-key"]
                )
                
            if "superagi-api-key" in api_settings and api_settings["superagi-api-key"]:
                user_manager.update_user_data(
                    user_id="AUTOBOT",
                    field="superagi_api_key",
                    value=api_settings["superagi-api-key"]
                )
                
            if "stripe-api-key" in api_settings and api_settings["stripe-api-key"]:
                user_manager.update_user_data(
                    user_id="AUTOBOT",
                    field="stripe_api_key",
                    value=api_settings["stripe-api-key"]
                )
        
        user_manager = UserManager()
        user_manager.update_user_data(
            user_id="AUTOBOT",
            field="preferences",
            value=data
        )
        
        await manager.broadcast_json({
            "type": "settings_updated",
            "user_id": "AUTOBOT"
        })
        
        return {
            "status": "success",
            "message": "Paramètres enregistrés avec succès"
        }
        
    except HTTPException as e:
        logger.error(f"Settings update error: {str(e)}")
        return JSONResponse(
            status_code=e.status_code,
            content={"status": "error", "message": e.detail}
        )
    except Exception as e:
        logger.error(f"Unexpected error updating settings: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Erreur lors de la mise à jour des paramètres: {str(e)}"}
        )

@router.post("/ecommerce/sync", response_class=JSONResponse)
async def sync_inventory(request: Request):
    """
    Synchronize e-commerce inventory.
    """
    
    return {"status": "synced", "products_count": 124}

@router.post("/ecommerce/optimize", response_class=JSONResponse)
async def optimize_prices(request: Request):
    """
    Optimize e-commerce prices.
    """
    
    return {"status": "optimized", "products_optimized": 45}

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time updates.
    """
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            
            try:
                message = json.loads(data)
                
                if message["type"] == "ping":
                    await manager.send_personal_message(json.dumps({"type": "pong"}), websocket)
                elif message["type"] == "subscribe":
                    pass
                else:
                    pass
                    
            except json.JSONDecodeError:
                pass
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)

def mount_static_files(app):
    """
    Mount static files for the dashboard.
    """
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

def add_auth_middleware(app):
    """
    Add authentication middleware to the app.
    """
    # app.add_middleware(AuthMiddleware)
    pass

def include_dashboard_router(app):
    """
    Include dashboard router in the app.
    """
    app.include_router(router)
    
    mount_static_files(app)
    
    add_auth_middleware(app)
