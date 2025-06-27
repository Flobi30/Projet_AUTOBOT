from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os
import logging
import asyncio
from contextlib import asynccontextmanager
# from autobot.router import router
# from autobot.routes.health_routes import router as health_router
# from autobot.routes.prediction_routes import router as prediction_router
# from autobot.ui.mobile_routes import router as mobile_router

from autobot.ui.backtest_routes import router as backtest_router
# from autobot.ui.deposit_withdrawal_routes import router as deposit_withdrawal_router
# from autobot.ui.chat_routes_custom import router as chat_router
# from autobot.routers.setup import router as setup_router
# from autobot.routers.funds import router as funds_router
# from autobot.routers.capital import router as capital_router
from autobot.config import load_api_keys
from autobot.ui.routes import router as ui_router
load_api_keys()
# from .api.ghosting_routes import router as ghosting_router
from .autobot_security.auth.user_manager import UserManager
from .adaptive import adaptive_capital_manager
from autobot.performance_optimizer import PerformanceOptimizer
from autobot.trading.hft_optimized_enhanced import HFTOptimizedEngine

logger = logging.getLogger(__name__)

strategy_optimizer = None
decision_engine = None
backtest_task = None
decision_task = None

async def continuous_backtest_loop():
    """Run continuous backtests every 30 seconds"""
    global strategy_optimizer
    
    while True:
        try:
            if strategy_optimizer is None:
                try:
                    from autobot.optimization.strategy_optimizer import StrategyOptimizer
                    strategy_optimizer = StrategyOptimizer()
                except ImportError as e:
                    logger.warning(f"Strategy optimizer not available: {e}")
                    await asyncio.sleep(300)  # Wait 5 minutes before retry
                    continue
            
            logger.info("Running continuous strategy optimization...")
            results = strategy_optimizer.optimize_all_strategies()
            
            if results:
                best = results[0]
                logger.info(f"Best strategy: {best.name} - Return: {best.total_return:.4f}, Sharpe: {best.sharpe_ratio:.2f}")
            
            await asyncio.sleep(30)
            
        except Exception as e:
            logger.error(f"Error in continuous backtest: {e}")
            await asyncio.sleep(60)

async def intelligent_decision_loop():
    """Run enhanced intelligent decision engine with WebSocket support"""
    global decision_engine
    
    while True:
        try:
            try:
                from autobot.trading.intelligent_decision_engine import IntelligentDecisionEngine
            except ImportError as e:
                logger.warning(f"Intelligent decision engine not available: {e}")
                await asyncio.sleep(300)  # Wait 5 minutes before retry
                continue
            
            if decision_engine is None:
                decision_engine = IntelligentDecisionEngine()
                await decision_engine.initialize()
            
            logger.info("🚀 Starting Enhanced Intelligent Decision Engine with WebSocket streams...")
            await decision_engine.continuous_analysis_loop()
            
        except Exception as e:
            logger.error(f"❌ Error in enhanced intelligent decision engine: {e}")
            logger.info("🔄 Restarting decision engine in 60 seconds...")
            await asyncio.sleep(60)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global backtest_task, decision_task
    logger.info("Starting AUTOBOT application...")
    
    from autobot.config import load_api_keys
    keys_loaded = load_api_keys()
    logger.info(f"Loaded {keys_loaded} API keys into environment variables")
    
    try:
        logger.info("Initializing Adaptive Capital Management System...")
        adaptive_capital_manager.meta_learner.start_adaptation()
        logger.info("✅ Adaptive Capital Management System initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize Adaptive Capital Management: {e}")
    
    logger.info("Background tasks disabled for debugging - server should start successfully")
    backtest_task = None
    decision_task = None
    
    yield
    
    logger.info("Shutting down AUTOBOT application...")
    try:
        adaptive_capital_manager.meta_learner.stop_adaptation()
    except:
        pass
    
    if backtest_task:
        backtest_task.cancel()
        logger.info("Stopped continuous backtest scheduler")
    
    if decision_task:
        decision_task.cancel()
        logger.info("🤖 Stopped Intelligent Decision Engine")

app = FastAPI(
    title="Autobot API",
    description="API for Autobot trading system",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

app.add_middleware(TrustedHostMiddleware, allowed_hosts=["stripe-autobot.fr", "144.76.16.177", "localhost"])
# Performance optimizations activated for 10% daily return target
performance_optimizer = PerformanceOptimizer(
    memory_threshold=0.80,
    cpu_threshold=0.90,
    auto_optimize=True,
    visible_interface=True
)

hft_engine = HFTOptimizedEngine(
    batch_size=50000,
    max_workers=16,
    prefetch_depth=5,
    artificial_latency=0.00005,
    memory_pool_size=1000000,
    adaptive_throttling=True
)

logger.info("Performance optimizations activated for 10% daily return target")
logger.info(f"HFT Engine configured: {hft_engine.batch_size} batch size, {hft_engine.max_workers} workers")
logger.info(f"Performance Optimizer configured: {performance_optimizer.memory_threshold*100}% memory threshold")

current_dir = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(current_dir, "ui", "static")
templates_dir = os.path.join(current_dir, "ui", "templates")

app.mount("/static", StaticFiles(directory=static_dir), name="static")

# app.include_router(router)
# app.include_router(health_router)
# app.include_router(prediction_router)
# app.include_router(mobile_router)
app.include_router(backtest_router)
# app.include_router(deposit_withdrawal_router)
# app.include_router(chat_router)
app.include_router(ui_router)
# app.include_router(ghosting_router)
# app.include_router(setup_router)
# app.include_router(capital_router)
# app.include_router(funds_router)

user_manager = UserManager()

@app.get("/", response_class=HTMLResponse)
async def root():
    return RedirectResponse(url="/")

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    templates = Jinja2Templates(directory=templates_dir)
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...), license_key: str = Form(...)):
    from autobot.autobot_security.auth.jwt_handler import create_access_token
    from datetime import timedelta
    
    user = user_manager.authenticate_user(username, password)
    if user:
        access_token_expires = timedelta(hours=24)
        access_token = create_access_token(
            data={"sub": user["username"], "user_id": user["id"]},
            expires_delta=access_token_expires
        )
        
        response = RedirectResponse(url="/trading", status_code=302)
        response.set_cookie(
            key="access_token",
            value=f"Bearer {access_token}",
            httponly=True,
            max_age=86400,
            secure=False,
            samesite="lax"
        )
        return response
    else:
        templates = Jinja2Templates(directory=templates_dir)
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Invalid username or password"
        })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
