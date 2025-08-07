from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
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

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Autobot API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://144.76.16.177", "https://144.76.16.177"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

@app.middleware("http")
async def domain_access_control(request: Request, call_next):
    host = request.headers.get("host", "")
    path = request.url.path
    
    if "stripe-autobot.fr" in host:
        allowed_public_paths = ["/capital", "/deposit", "/withdrawal", "/api/stripe", "/static", "/favicon.ico"]
        blocked_paths = ["/", "/simple", "/mobile", "/backtest", "/arbitrage", "/trading", "/ecommerce", "/dashboard", "/parametres", "/duplication"]
        
        if path in blocked_paths or not any(path.startswith(allowed_path) for allowed_path in allowed_public_paths):
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=403, content={"detail": "Access denied"})
    
    response = await call_next(request)
    return response

performance_optimizer = PerformanceOptimizer(
    memory_threshold=0.75,
    cpu_threshold=0.85,
    auto_optimize=True,
    visible_interface=True
)

hft_engine = HFTOptimizedEngine(
    batch_size=15000,
    max_workers=8,
    prefetch_depth=3,
    artificial_latency=2.0,
    memory_pool_size=500000,
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

app.include_router(deposit_withdrawal_router)
app.include_router(chat_router)
app.include_router(ui_router)

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
