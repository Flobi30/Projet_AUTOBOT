from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os
from autobot.router_clean import router
from autobot.routes.health_routes import router as health_router
from autobot.routes.prediction_routes import router as prediction_router
from autobot.ui.mobile_routes import router as mobile_router

from autobot.ui.arbitrage_routes import router as arbitrage_router
from autobot.ui.backtest_routes import router as backtest_router
from autobot.ui.deposit_withdrawal_routes import router as deposit_withdrawal_router
from autobot.ui.chat_routes_custom import router as chat_router
from autobot.ui.routes import router as ui_router
from .api.ghosting_routes import router as ghosting_router


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
app.include_router(arbitrage_router)
app.include_router(backtest_router)
app.include_router(deposit_withdrawal_router)
app.include_router(chat_router)
app.include_router(ui_router)
app.include_router(ghosting_router)

from .api.backtest_routes import router as api_backtest_router
app.include_router(api_backtest_router)



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
    response = RedirectResponse(url="/dashboard", status_code=303)
    
    response.set_cookie(
        key="auth_status",
        value="authenticated",
        max_age=86400,  # 24 hours
        samesite="lax"
    )
    
    return response

@app.get("/dashboard", tags=["ui"])
async def dashboard_page(request: Request):
    """
    Main dashboard endpoint.
    """
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "active_page": "dashboard",
        "username": "AUTOBOT",
        "user_role": "admin",
        "user_role_display": "Administrateur"
    })

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
        return RedirectResponse(url="/dashboard")
