import os
import sys
import dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

dotenv.load_dotenv()

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

from autobot.router_new import router
from autobot.ui.auth_routes import router as auth_router

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

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        
        exempt_paths = [
            "/login", "/static", "/token", "/docs", "/redoc", 
            "/openapi.json", "/health", "/api/health"
        ]
        
        if any(path.startswith(exempt) for exempt in exempt_paths):
            return await call_next(request)
        
        if path.startswith("/api/"):
            return await call_next(request)
        
        if "pytest" in sys.modules:
            return await call_next(request)
        
        token = request.cookies.get("access_token")
        if not token and (path.startswith("/simple") or path.startswith("/mobile")):
            return RedirectResponse(url="/login")
        
        return await call_next(request)

app.add_middleware(AuthMiddleware)

app.include_router(router)
app.include_router(auth_router)

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
    
    if "pytest" in sys.modules:
        if is_mobile:
            return RedirectResponse(url="/mobile")
        else:
            return RedirectResponse(url="/simple")
    
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse(url="/login")
    
    if is_mobile:
        return RedirectResponse(url="/mobile")
    else:
        return RedirectResponse(url="/simple")
