from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from ..autobot_security.auth.user_manager import UserManager
from ..autobot_security.auth.jwt_handler import decode_token
import os

router = APIRouter()

current_dir = os.path.dirname(os.path.abspath(__file__))
templates_dir = os.path.join(current_dir, "templates")
templates = Jinja2Templates(directory=templates_dir)

user_manager = UserManager()

async def get_current_user(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        payload = decode_token(token)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        user = user_manager.get_user(user_id)
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        
        return user
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user: dict = Depends(get_current_user)):
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "active_page": "dashboard",
        "username": user.get("username", "AUTOBOT"),
        "user_role": user.get("role", "admin"),
        "user_role_display": "Administrateur"
    })

@router.get("/trading", response_class=HTMLResponse)
async def trading(request: Request, user: dict = Depends(get_current_user)):
    return templates.TemplateResponse("trading.html", {
        "request": request,
        "active_page": "trading",
        "username": user.get("username", "AUTOBOT"),
        "user_role": user.get("role", "admin"),
        "user_role_display": "Administrateur"
    })

@router.get("/ecommerce", response_class=HTMLResponse)
async def ecommerce(request: Request, user: dict = Depends(get_current_user)):
    return templates.TemplateResponse("ecommerce.html", {
        "request": request,
        "active_page": "ecommerce",
        "username": user.get("username", "AUTOBOT"),
        "user_role": user.get("role", "admin"),
        "user_role_display": "Administrateur"
    })

@router.get("/arbitrage", response_class=HTMLResponse)
async def arbitrage(request: Request, user: dict = Depends(get_current_user)):
    return templates.TemplateResponse("arbitrage.html", {
        "request": request,
        "active_page": "arbitrage",
        "username": user.get("username", "AUTOBOT"),
        "user_role": user.get("role", "admin"),
        "user_role_display": "Administrateur"
    })

@router.get("/backtest", response_class=HTMLResponse)
async def backtest(request: Request, user: dict = Depends(get_current_user)):
    return templates.TemplateResponse("backtest.html", {
        "request": request,
        "active_page": "backtest",
        "username": user.get("username", "AUTOBOT"),
        "user_role": user.get("role", "admin"),
        "user_role_display": "Administrateur"
    })

@router.get("/capital", response_class=HTMLResponse)
async def capital(request: Request, user: dict = Depends(get_current_user)):
    return templates.TemplateResponse("capital.html", {
        "request": request,
        "active_page": "capital",
        "username": user.get("username", "AUTOBOT"),
        "user_role": user.get("role", "admin"),
        "user_role_display": "Administrateur"
    })

@router.get("/duplication", response_class=HTMLResponse)
async def duplication(request: Request, user: dict = Depends(get_current_user)):
    return templates.TemplateResponse("duplication.html", {
        "request": request,
        "active_page": "duplication",
        "username": user.get("username", "AUTOBOT"),
        "user_role": user.get("role", "admin"),
        "user_role_display": "Administrateur"
    })

@router.get("/retrait-depot", response_class=HTMLResponse)
async def retrait_depot(request: Request, user: dict = Depends(get_current_user)):
    return templates.TemplateResponse("retrait_depot.html", {
        "request": request,
        "active_page": "retrait-depot",
        "username": user.get("username", "AUTOBOT"),
        "user_role": user.get("role", "admin"),
        "user_role_display": "Administrateur"
    })

@router.get("/parametres", response_class=HTMLResponse)
async def parametres(request: Request, user: dict = Depends(get_current_user)):
    env_file_path = "/home/ubuntu/Projet_AUTOBOT/.env"
    env_vars = {}
    
    if os.path.exists(env_file_path):
        with open(env_file_path, 'r') as f:
            for line in f:
                if '=' in line and not line.strip().startswith('#'):
                    key, value = line.strip().split('=', 1)
                    env_vars[key] = value
    
    return templates.TemplateResponse("parametres.html", {
        "request": request,
        "active_page": "parametres",
        "username": user.get("username", "AUTOBOT"),
        "user_role": user.get("role", "admin"),
        "user_role_display": "Administrateur",
        "binance_api_key": env_vars.get("BINANCE_API_KEY", ""),
        "binance_api_secret": env_vars.get("BINANCE_API_SECRET", ""),
        "openai_api_key": env_vars.get("OPENAI_API_KEY", ""),
        "superagi_api_key": env_vars.get("SUPERAGI_API_KEY", ""),
        "stripe_api_key": env_vars.get("STRIPE_API_KEY", ""),
        "alpha_vantage_api_key": env_vars.get("ALPHA_VANTAGE_API_KEY", ""),
        "twelve_data_api_key": env_vars.get("TWELVE_DATA_API_KEY", ""),
        "fred_api_key": env_vars.get("FRED_API_KEY", ""),
        "newsapi_api_key": env_vars.get("NEWSAPI_KEY", ""),
        "shopify_api_key": env_vars.get("SHOPIFY_API_KEY", ""),
        "shopify_api_secret": env_vars.get("SHOPIFY_API_SECRET", ""),
        "shopify_shop_name": env_vars.get("SHOPIFY_SHOP_NAME", ""),
        "coinbase_api_key": env_vars.get("COINBASE_API_KEY", ""),
        "coinbase_api_secret": env_vars.get("COINBASE_API_SECRET", ""),
        "kraken_api_key": env_vars.get("KRAKEN_API_KEY", ""),
        "kraken_api_secret": env_vars.get("KRAKEN_API_SECRET", "")
    })
