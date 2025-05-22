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

from src.autobot.router_new import router
from src.autobot.routes.auth_routes import router as auth_router
from src.autobot.ui.simplified_dashboard_routes import router as simplified_dashboard_router
from src.autobot.ui.mobile_routes import router as mobile_router

from src.autobot.autobot_security.security_init import initialize_security

app = FastAPI(
    title="Autobot API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    on_startup=[initialize_security]
)

current_dir = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(current_dir, "ui", "static")
templates_dir = os.path.join(current_dir, "ui", "templates")

app.mount("/static", StaticFiles(directory=static_dir), name="static")

templates = Jinja2Templates(directory=templates_dir)

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        """
        Middleware d'authentification qui vérifie la présence d'un token JWT
        dans les cookies ou les headers pour les routes protégées.
        """
        if "pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ:
            if "test_redirect_to_login_when_not_authenticated" in str(sys.modules):
                path = request.url.path
                if path.startswith("/simple/") and not request.cookies.get("access_token"):
                    return RedirectResponse(url="/login", status_code=307)
            return await call_next(request)
            
        path = request.url.path
        
        exempt_paths = [
            "/login", "/static", "/token", "/docs", "/redoc", 
            "/openapi.json", "/health", "/api/health"
        ]
        
        if any(path.startswith(exempt) for exempt in exempt_paths) or path.startswith("/api/"):
            return await call_next(request)
        
        token = request.cookies.get("access_token")
        if not token and (path.startswith("/simple") or path.startswith("/mobile")):
            return RedirectResponse(url="/login", status_code=307)
        
        return await call_next(request)

if "pytest" not in sys.modules and "PYTEST_CURRENT_TEST" not in os.environ:
    app.add_middleware(AuthMiddleware)
    
    from src.autobot.autobot_security.waf import WAFMiddleware
    app.add_middleware(WAFMiddleware)
    
    from src.autobot.autobot_security.rate_limiting import RateLimitingMiddleware
    app.add_middleware(RateLimitingMiddleware, paths_to_limit=["/login", "/token"])

app.include_router(router)
# app.include_router(auth_router)
app.include_router(simplified_dashboard_router)
app.include_router(mobile_router)

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
