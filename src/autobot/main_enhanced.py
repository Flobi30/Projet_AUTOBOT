"""
AUTOBOT Main Module

This is the main entry point for the AUTOBOT system, integrating all modules:
- Trading (CCXT provider, risk manager, execution)
- Reinforcement Learning (agent, environment, training)
- Security (authentication, license management)
- Multi-agent orchestration
- E-commerce inventory management
- Dashboard UI
"""

import os
import logging
import asyncio
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, Depends, HTTPException, Request, WebSocket, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from autobot.router import router
from autobot.trading.execution import execute_trade
from autobot.trading.strategy import Strategy, MovingAverageStrategy
from autobot.trading.order import Order, OrderType, OrderSide
from autobot.trading.position import Position
from autobot.providers.ccxt_provider_enhanced import CCXTProviderEnhanced
from autobot.risk_manager_enhanced import RiskManagerEnhanced
from autobot.rl.agent import RLAgent
from autobot.rl.env import TradingEnvironment
from autobot.rl.train import train_agent, get_training_status
from autobot.autobot_security.auth.jwt_handler import create_access_token, decode_token, verify_license_key
from autobot.autobot_security.auth.user_manager import UserManager
from autobot.agents.orchestrator import AgentOrchestrator
from autobot.ecommerce.inventory_manager import InventoryManager
from autobot.ui.dashboard_routes import include_dashboard_router

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("autobot.log")
    ]
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="AUTOBOT",
    description="Trading and Automation Framework",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

user_manager = UserManager()
risk_manager = RiskManagerEnhanced()
agent_orchestrator = AgentOrchestrator()
inventory_manager = InventoryManager()

exchange_providers = {}

strategies = {}

rl_agents = {}

current_dir = os.path.dirname(os.path.abspath(__file__))
templates_dir = os.path.join(current_dir, "ui", "templates")
templates = Jinja2Templates(directory=templates_dir)

include_dashboard_router(app)

@app.get("/health", tags=["health"])
async def health_check():
    """
    Health check endpoint.
    """
    return {"status": "ok"}

@app.get("/login", response_class=HTMLResponse, tags=["auth"])
async def login_page(request: Request):
    """
    Login page endpoint.
    """
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login", tags=["auth"])
async def login(username: str = Form(...), password: str = Form(...), license_key: str = Form(...)):
    """
    Login endpoint.
    """
    user = user_manager.authenticate_user(username, password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    
    access_token = user_manager.create_token(user["id"])
    
    response = RedirectResponse(url="/dashboard", status_code=303)
    
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=900,  # 15 minutes to match JWT expiration
        samesite="lax"
    )
    
    response.set_cookie(
        key="auth_status",
        value="authenticated",
        max_age=86400,  # 24 hours
        samesite="lax"
    )
    
    return response

@app.post("/register", tags=["auth"])
async def register(username: str, password: str, email: str):
    """
    Register endpoint.
    """
    try:
        user = user_manager.register_user(username, password, email)
        return {"message": "User registered successfully", "user": user}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/verify-license", tags=["auth"])
async def verify_license(license_key: str, user_id: str):
    """
    Verify license endpoint.
    """
    is_valid = user_manager.verify_license(user_id, license_key)
    
    if not is_valid:
        raise HTTPException(status_code=400, detail="Invalid license key")
    
    return {"message": "License key is valid"}

@app.post("/api-key", tags=["auth"])
async def create_api_key(user_id: str, name: str, permissions: List[str]):
    """
    Create API key endpoint.
    """
    api_key = user_manager.create_api_key(user_id, name, permissions)
    
    if not api_key:
        raise HTTPException(status_code=400, detail="Failed to create API key")
    
    return {"api_key": api_key}

@app.get("/exchanges", tags=["trading"])
async def list_exchanges():
    """
    List available exchanges.
    """
    provider = CCXTProviderEnhanced()
    exchanges = provider.get_available_exchanges()
    
    return {"exchanges": exchanges}

@app.post("/exchange", tags=["trading"])
async def add_exchange(exchange_id: str, api_key: str, api_secret: str, user_id: str):
    """
    Add exchange credentials.
    """
    provider = CCXTProviderEnhanced()
    
    try:
        exchange = provider.create_exchange(exchange_id, api_key, api_secret)
        exchange_providers[user_id] = {exchange_id: provider}
        
        return {"message": f"Exchange {exchange_id} added successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/markets/{exchange_id}", tags=["trading"])
async def get_markets(exchange_id: str, user_id: str):
    """
    Get markets for an exchange.
    """
    if user_id not in exchange_providers or exchange_id not in exchange_providers[user_id]:
        raise HTTPException(status_code=400, detail=f"Exchange {exchange_id} not found")
    
    provider = exchange_providers[user_id][exchange_id]
    markets = provider.get_markets()
    
    return {"markets": markets}

@app.post("/strategy", tags=["trading"])
async def create_strategy(
    name: str,
    strategy_type: str,
    exchange_id: str,
    symbol: str,
    timeframe: str,
    parameters: Dict[str, Any],
    user_id: str
):
    """
    Create a trading strategy.
    """
    if user_id not in exchange_providers or exchange_id not in exchange_providers[user_id]:
        raise HTTPException(status_code=400, detail=f"Exchange {exchange_id} not found")
    
    provider = exchange_providers[user_id][exchange_id]
    
    if strategy_type == "moving_average":
        strategy = MovingAverageStrategy(
            name=name,
            exchange=provider.get_exchange(exchange_id),
            symbol=symbol,
            timeframe=timeframe,
            parameters=parameters
        )
    else:
        raise HTTPException(status_code=400, detail=f"Strategy type {strategy_type} not supported")
    
    strategy_id = f"{user_id}_{name}"
    strategies[strategy_id] = strategy
    
    return {"strategy_id": strategy_id, "message": f"Strategy {name} created successfully"}

@app.post("/strategy/{strategy_id}/start", tags=["trading"])
async def start_strategy(strategy_id: str, user_id: str):
    """
    Start a trading strategy.
    """
    if strategy_id not in strategies:
        raise HTTPException(status_code=400, detail=f"Strategy {strategy_id} not found")
    
    strategy = strategies[strategy_id]
    
    if not strategy_id.startswith(user_id):
        raise HTTPException(status_code=403, detail="Not authorized to access this strategy")
    
    try:
        strategy.start()
        return {"message": f"Strategy {strategy_id} started successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/strategy/{strategy_id}/stop", tags=["trading"])
async def stop_strategy(strategy_id: str, user_id: str):
    """
    Stop a trading strategy.
    """
    if strategy_id not in strategies:
        raise HTTPException(status_code=400, detail=f"Strategy {strategy_id} not found")
    
    strategy = strategies[strategy_id]
    
    if not strategy_id.startswith(user_id):
        raise HTTPException(status_code=403, detail="Not authorized to access this strategy")
    
    try:
        strategy.stop()
        return {"message": f"Strategy {strategy_id} stopped successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/strategy/{strategy_id}/status", tags=["trading"])
async def get_strategy_status(strategy_id: str, user_id: str):
    """
    Get strategy status.
    """
    if strategy_id not in strategies:
        raise HTTPException(status_code=400, detail=f"Strategy {strategy_id} not found")
    
    strategy = strategies[strategy_id]
    
    if not strategy_id.startswith(user_id):
        raise HTTPException(status_code=403, detail="Not authorized to access this strategy")
    
    status = strategy.get_status()
    
    return {"status": status}

@app.post("/rl/agent", tags=["rl"])
async def create_rl_agent(
    name: str,
    agent_type: str,
    exchange_id: str,
    symbol: str,
    timeframe: str,
    parameters: Dict[str, Any],
    user_id: str
):
    """
    Create a reinforcement learning agent.
    """
    if user_id not in exchange_providers or exchange_id not in exchange_providers[user_id]:
        raise HTTPException(status_code=400, detail=f"Exchange {exchange_id} not found")
    
    provider = exchange_providers[user_id][exchange_id]
    
    env = TradingEnvironment(
        exchange=provider.get_exchange(exchange_id),
        symbol=symbol,
        timeframe=timeframe,
        parameters=parameters
    )
    
    agent = RLAgent(
        name=name,
        agent_type=agent_type,
        env=env,
        parameters=parameters
    )
    
    agent_id = f"{user_id}_{name}"
    rl_agents[agent_id] = agent
    
    return {"agent_id": agent_id, "message": f"RL agent {name} created successfully"}

@app.post("/rl/agent/{agent_id}/train", tags=["rl"])
async def train_rl_agent(
    agent_id: str,
    episodes: int,
    user_id: str
):
    """
    Train a reinforcement learning agent.
    """
    if agent_id not in rl_agents:
        raise HTTPException(status_code=400, detail=f"RL agent {agent_id} not found")
    
    agent = rl_agents[agent_id]
    
    if not agent_id.startswith(user_id):
        raise HTTPException(status_code=403, detail="Not authorized to access this agent")
    
    asyncio.create_task(train_agent(agent, episodes))
    
    return {"message": f"Training started for RL agent {agent_id}"}

@app.get("/rl/agent/{agent_id}/status", tags=["rl"])
async def get_rl_agent_status(agent_id: str, user_id: str):
    """
    Get RL agent training status.
    """
    if agent_id not in rl_agents:
        raise HTTPException(status_code=400, detail=f"RL agent {agent_id} not found")
    
    agent = rl_agents[agent_id]
    
    if not agent_id.startswith(user_id):
        raise HTTPException(status_code=403, detail="Not authorized to access this agent")
    
    status = get_training_status(agent)
    
    return {"status": status}

@app.post("/agents/orchestrator/start", tags=["agents"])
async def start_orchestrator(user_id: str):
    """
    Start the agent orchestrator.
    """
    try:
        agent_orchestrator.start()
        return {"message": "Agent orchestrator started successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/agents/orchestrator/stop", tags=["agents"])
async def stop_orchestrator(user_id: str):
    """
    Stop the agent orchestrator.
    """
    try:
        agent_orchestrator.stop()
        return {"message": "Agent orchestrator stopped successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/agents/orchestrator/status", tags=["agents"])
async def get_orchestrator_status(user_id: str):
    """
    Get orchestrator status.
    """
    status = agent_orchestrator.get_status()
    
    return {"status": status}

@app.post("/agents/orchestrator/add", tags=["agents"])
async def add_agent_to_orchestrator(
    agent_type: str,
    agent_config: Dict[str, Any],
    user_id: str
):
    """
    Add an agent to the orchestrator.
    """
    try:
        agent_id = agent_orchestrator.add_agent(agent_type, agent_config)
        return {"agent_id": agent_id, "message": f"Agent added to orchestrator successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ecommerce/sync", tags=["ecommerce"])
async def sync_ecommerce_inventory(user_id: str):
    """
    Synchronize e-commerce inventory.
    """
    try:
        result = inventory_manager.sync_inventory()
        return {"message": "Inventory synchronized successfully", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ecommerce/optimize", tags=["ecommerce"])
async def optimize_ecommerce_prices(user_id: str):
    """
    Optimize e-commerce prices.
    """
    try:
        result = inventory_manager.optimize_prices()
        return {"message": "Prices optimized successfully", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/ecommerce/products", tags=["ecommerce"])
async def get_ecommerce_products(user_id: str):
    """
    Get e-commerce products.
    """
    try:
        products = inventory_manager.get_products()
        return {"products": products}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ecommerce/order", tags=["ecommerce"])
async def place_ecommerce_order(
    product_ids: List[str],
    quantities: List[int],
    user_id: str
):
    """
    Place an e-commerce order.
    """
    try:
        order = inventory_manager.place_order(product_ids, quantities, user_id)
        return {"order_id": order["id"], "message": "Order placed successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.on_event("startup")
async def startup_event():
    """
    Startup event.
    """
    logger.info("Starting AUTOBOT...")
    
    logger.info("Initializing components...")
    
    logger.info("Loading user data...")
    
    logger.info("AUTOBOT started successfully")

@app.on_event("shutdown")
async def shutdown_event():
    """
    Shutdown event.
    """
    logger.info("Shutting down AUTOBOT...")
    
    for strategy_id, strategy in strategies.items():
        try:
            strategy.stop()
        except Exception as e:
            logger.error(f"Error stopping strategy {strategy_id}: {str(e)}")
    
    try:
        agent_orchestrator.stop()
    except Exception as e:
        logger.error(f"Error stopping agent orchestrator: {str(e)}")
    
    logger.info("AUTOBOT shut down successfully")

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "autobot.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
