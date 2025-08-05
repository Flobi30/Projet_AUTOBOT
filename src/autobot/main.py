from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os
import logging
from fastapi import FastAPI, Request, Form, HTTPException, status
from fastapi.responses import RedirectResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
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
from autobot.autobot_security.auth.user_manager import UserManager

logger = logging.getLogger(__name__)

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

from autobot.utils.instance_access import set_hft_engine
set_hft_engine(hft_engine)

hft_engine.start()

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

@app.middleware("http")
async def route_middleware(request: Request, call_next):
    """Middleware to handle routing based on host"""
    host = request.headers.get("host", "")
    
    if request.url.path.startswith("/assets/") or request.url.path.startswith("/static/"):
        response = await call_next(request)
        return response
    
    if "stripe-autobot.fr" in host and request.url.path in ["/capital", "/trading", "/backtest", "/analytics"]:
        react_static_path = os.path.join(os.path.dirname(__file__), "ui", "static", "react")
        react_index = os.path.join(react_static_path, "index.html")
        
        if os.path.exists(react_index):
            from fastapi.responses import FileResponse
            return FileResponse(react_index)
    
    response = await call_next(request)
    return response

app.include_router(ui_router)

user_manager = UserManager()

current_dir = os.path.dirname(os.path.abspath(__file__))
templates_dir = os.path.join(current_dir, "ui", "templates")
templates = Jinja2Templates(directory=templates_dir)

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
    
    return response

try:
    from .api.live_trading_routes import router as live_trading_router
    from .api.analytics_routes import router as analytics_router
    
    app.include_router(live_trading_router)
    app.include_router(analytics_router)
    
    logger.info("Successfully loaded React frontend API routers")
except ImportError as e:
    logger.warning(f"Could not load React frontend API routers: {e}")

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

react_static_path = os.path.join(os.path.dirname(__file__), "ui", "static", "react")
if os.path.exists(react_static_path):
    app.mount("/static/react", StaticFiles(directory=react_static_path), name="react-static")
    
    react_assets_path = os.path.join(react_static_path, "assets")
    if os.path.exists(react_assets_path):
        app.mount("/assets", StaticFiles(directory=react_assets_path), name="react-assets")
    
    @app.get("/react-app", response_class=HTMLResponse, tags=["frontend"])
    async def serve_react_frontend(request: Request):
        """Serve React frontend for authenticated users only."""
        access_token = request.cookies.get("access_token")
        if not access_token:
            return RedirectResponse(url="/login")
        
        try:
            from autobot.autobot_security.auth.jwt_handler import decode_token
            decode_token(access_token)
        except:
            return RedirectResponse(url="/login")
        
        react_index = os.path.join(react_static_path, "index.html")
        if os.path.exists(react_index):
            return FileResponse(react_index)
        else:
            return RedirectResponse(url="/dashboard")
    
    logger.info("React frontend mounted successfully")
else:
    logger.warning("React frontend directory not found")

@app.get("/", tags=["root"])
async def root(request: Request):
    """Root endpoint that redirects to login or dashboard based on authentication."""
    host = request.headers.get("host", "")
    
    if "stripe-autobot.fr" in host:
        react_static_path = os.path.join(os.path.dirname(__file__), "ui", "static", "react")
        react_index = os.path.join(react_static_path, "index.html")
        
        if os.path.exists(react_index):
            return FileResponse(react_index)
    
    access_token = request.cookies.get("access_token")
    if access_token:
        try:
            from autobot.autobot_security.auth.jwt_handler import decode_token
            decode_token(access_token)
            return RedirectResponse(url="/dashboard")
        except:
            pass
    
    return RedirectResponse(url="/login")

@app.get("/{path:path}", response_class=HTMLResponse, tags=["public"])
async def serve_public_react(request: Request, path: str):
    """Serve React frontend for all paths on public domain without authentication."""
    host = request.headers.get("host", "")
    
    if path.startswith("assets/") or path.startswith("static/"):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Not found")
    
    if "stripe-autobot.fr" in host:
        react_static_path = os.path.join(os.path.dirname(__file__), "ui", "static", "react")
        react_index = os.path.join(react_static_path, "index.html")
        
        if os.path.exists(react_index):
            return FileResponse(react_index)
    
    return RedirectResponse(url="/login")
