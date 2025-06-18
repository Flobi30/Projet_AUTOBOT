from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
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
from .api.ghosting_routes import router as ghosting_router
from .autobot_security.auth.user_manager import UserManager
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

app.include_router(router)
app.include_router(health_router)
app.include_router(prediction_router)
app.include_router(mobile_router)
app.include_router(backtest_router)
app.include_router(deposit_withdrawal_router)
app.include_router(chat_router)
app.include_router(funds_router)
app.include_router(funds_router)
app.include_router(ui_router)
app.include_router(ghosting_router)
app.include_router(setup_router)
app.include_router(capital_router)
app.include_router(funds_router)

user_manager = UserManager()

@app.get("/", response_class=HTMLResponse)
async def root():
    return RedirectResponse(url="/")

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    templates = Jinja2Templates(directory=templates_dir)
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    user = user_manager.authenticate_user(username, password)
    if user:
        return RedirectResponse(url="/dashboard", status_code=302)
    else:
        templates = Jinja2Templates(directory=templates_dir)
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Invalid username or password"
        })

if __name__ == "__main__":
    from pprint import pprint
    
    # Affiche dans la console toutes les routes connues
    for route in app.router.routes:
        pprint({
            "path":    route.path,
            "methods": route.methods,
            "name":    route.name,
        })
    
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
