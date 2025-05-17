from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os
from autobot.router_clean import router
from autobot.routes.health_routes import router as health_router
from autobot.routes.prediction_routes import router as prediction_router
from autobot.ui.mobile_routes import router as mobile_router
from autobot.ui.simplified_dashboard_routes import router as simplified_dashboard_router
from autobot.ui.arbitrage_routes import router as arbitrage_router
from autobot.ui.backtest_routes import router as backtest_router
from autobot.ui.deposit_withdrawal_routes import router as deposit_withdrawal_router

app = FastAPI(
    title="Autobot API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

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
