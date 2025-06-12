from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os
import logging
from autobot.router_clean import router
from autobot.routes.health_routes import router as health_router
from autobot.routes.prediction_routes import router as prediction_router
from autobot.ui.mobile_routes import router as mobile_router
from autobot.ui.simplified_dashboard_routes import router as simplified_dashboard_router
from autobot.ui.arbitrage_routes import router as arbitrage_router
from autobot.ui.backtest_routes import router as backtest_router
from autobot.ui.deposit_withdrawal_routes import router as deposit_withdrawal_router
from autobot.ui.chat_routes_custom import router as chat_router
from autobot.ui.routes import router as ui_router
from autobot.performance_optimizer import PerformanceOptimizer
from autobot.trading.hft_optimized_enhanced import HFTOptimizedEngine
from autobot.ecommerce_engine import ecommerce_engine
from autobot.arbitrage_engine import arbitrage_engine
from autobot.backtest_learning_system import learning_system
from autobot.autobot_security.auth.user_manager import UserManager, get_current_user

logger = logging.getLogger(__name__)

user_manager = UserManager(users_file="/home/ubuntu/Projet_AUTOBOT/users.json")

app = FastAPI(
    title="Autobot API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

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

templates = Jinja2Templates(directory=templates_dir)

app.include_router(router)
app.include_router(health_router)
app.include_router(prediction_router)
app.include_router(mobile_router)
app.include_router(simplified_dashboard_router, prefix="/simple")
app.include_router(arbitrage_router)
app.include_router(backtest_router)
app.include_router(deposit_withdrawal_router)
app.include_router(chat_router)
app.include_router(ui_router)

@app.get("/login", response_class=HTMLResponse, tags=["auth"])
async def login_page(request: Request):
    """Login page endpoint."""
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login", tags=["auth"])
async def login(username: str = Form(...), password: str = Form(...), license_key: str = Form(...)):
    """Login endpoint."""
    user = user_manager.authenticate_user(username, password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    
    access_token = user_manager.create_token(user["id"])
    
    response = RedirectResponse(url="/dashboard", status_code=303)
    
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=900,
        samesite="lax"
    )
    
    response.set_cookie(
        key="auth_status",
        value="authenticated",
        max_age=86400,
        samesite="lax"
    )
    
    return response

@app.on_event("startup")
async def startup_event():
    """Initialize AUTOBOT engines and learning system."""
    logger.info("Starting AUTOBOT engines...")
    
    hft_engine.start()
    hft_engine.start_backtest_collection(interval_hours=1)
    
    ecommerce_engine.start()
    ecommerce_engine.start_backtest_collection(interval_hours=2)
    
    arbitrage_engine.start()
    arbitrage_engine.start_backtest_collection(interval_hours=1)
    
    learning_system.start()
    
    logger.info("All AUTOBOT engines and learning system started successfully")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup AUTOBOT engines."""
    logger.info("Stopping AUTOBOT engines...")
    hft_engine.stop()
    ecommerce_engine.stop()
    arbitrage_engine.stop()
    learning_system.stop()
    logger.info("All AUTOBOT engines stopped")

@app.get("/", tags=["root"])
async def root(request: Request):
    """
    Root endpoint that detects device type and redirects accordingly.
    """
    user_agent = request.headers.get("user-agent", "")
    
    mobile_keywords = [
        "android", "iphone", "ipod", "ipad", "windows phone", "blackberry", 
        "opera mini", "mobile", "tablet"
    ]
    
    is_mobile = any(keyword in user_agent.lower() for keyword in mobile_keywords)
    
    if is_mobile:
        return RedirectResponse(url="/mobile")
    else:
        return RedirectResponse(url="/simple")
