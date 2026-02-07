from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import os
import logging
from autobot.router_clean import router
from autobot.routes.health_routes import router as health_router
from autobot.routes.prediction_routes import router as prediction_router
from autobot.ui.mobile_routes import router as mobile_router

from autobot.ui.backtest_routes import router as backtest_router
from autobot.ui.deposit_withdrawal_routes import router as deposit_withdrawal_router
from autobot.ui.chat_routes_custom import router as chat_router
from autobot.routers.setup import router as setup_router
from autobot.routers.funds import router as funds_router
from autobot.routers.capital import router as capital_router
from autobot.config import load_api_keys
from autobot.ui.routes import router as ui_router
load_api_keys()
try:
    from .api.ghosting_routes import router as ghosting_router
except ImportError:
    ghosting_router = None
from .autobot_security.auth.user_manager import UserManager
from .autobot_security.auth.jwt_handler import create_access_token
from .autobot_security.rate_limiter import login_limiter
from autobot.performance_optimizer import PerformanceOptimizer
from autobot.trading.hft_optimized_enhanced import HFTOptimizedEngine

logger = logging.getLogger(__name__)
app = FastAPI(

    title="Autobot API",
    description="API for Autobot trading system",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(TrustedHostMiddleware, allowed_hosts=["stripe-autobot.fr", "144.76.16.177", "localhost"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://144.76.16.177",
        "https://stripe-autobot.fr",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
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

if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

app.include_router(router)
app.include_router(health_router)
app.include_router(prediction_router)
app.include_router(mobile_router)
app.include_router(backtest_router)
app.include_router(deposit_withdrawal_router)
app.include_router(chat_router)
app.include_router(ui_router)
if ghosting_router is not None:
    app.include_router(ghosting_router)
app.include_router(setup_router)
app.include_router(capital_router)
app.include_router(funds_router)

user_manager = UserManager()

@app.post("/login")
async def login(request: Request):
    from datetime import timedelta

    await login_limiter.check(request)

    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        data = await request.json()
        username = data.get("username", "")
        password = data.get("password", "")
    else:
        form = await request.form()
        username = form.get("username", "")
        password = form.get("password", "")

    user = user_manager.authenticate_user(username, password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    access_token_expires = timedelta(hours=24)
    access_token = create_access_token(
        data={"sub": user["username"], "user_id": user["id"]},
        expires_delta=access_token_expires
    )

    _env = os.getenv('ENV', 'production').lower()
    _cookie_secure = _env not in ('dev', 'development', 'test', 'testing', 'ci')

    response = JSONResponse(content={
        "access_token": access_token,
        "token_type": "bearer",
        "username": user["username"],
        "role": user.get("role", "user"),
    })
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,
        max_age=86400,
        secure=_cookie_secure,
        samesite="lax"
    )
    return response
