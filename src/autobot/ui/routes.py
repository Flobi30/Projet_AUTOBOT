"""
Routes pour l'interface utilisateur AUTOBOT
"""

import os
import json
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from autobot.autobot_security.auth.user_manager import User, UserManager
from autobot.autobot_security.auth.jwt_handler import decode_token

logger = logging.getLogger(__name__)

current_dir = os.path.dirname(os.path.abspath(__file__))
templates_dir = os.path.join(current_dir, "templates")

router = APIRouter(tags=["ui"])
templates = Jinja2Templates(directory=templates_dir)

user_manager = UserManager()

def load_api_keys():
    """Load API keys from config file"""
    config_file = "/home/autobot/Projet_AUTOBOT/config/api_keys.json"
    api_keys = {}
    
    if os.path.exists(config_file):
        try:
            with open(config_file, "r") as f:
                api_keys = json.load(f)
        except Exception as e:
            logger.error(f"Error loading API keys: {str(e)}")
    
    return api_keys

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

@router.get("/", response_class=HTMLResponse)
async def get_dashboard(request: Request, user: dict = Depends(get_current_user)):
    """
    Page principale du dashboard.
    """
    api_keys = load_api_keys()
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "active_page": "dashboard",
        "username": user.get("username", "AUTOBOT"),
        "user_role": user.get("role", "admin"),
        "user_role_display": "Administrateur"
    })

@router.get("/parametres", response_class=HTMLResponse)
async def get_parametres(request: Request, user: dict = Depends(get_current_user)):
    """
    Page de paramètres.
    """
    api_keys = load_api_keys()
    
    return templates.TemplateResponse("parametres.html", {
        "request": request,
        "active_page": "parametres",
        "username": user.get("username", "AUTOBOT"),
        "user_role": user.get("role", "admin"),
        "user_role_display": "Administrateur",
        "binance_api_key": api_keys.get("binance", {}).get("api_key", ""),
        "binance_api_secret": api_keys.get("binance", {}).get("secret_key", ""),
        "coinbase_api_key": api_keys.get("coinbase", {}).get("api_key", ""),
        "coinbase_api_secret": api_keys.get("coinbase", {}).get("secret_key", ""),
        "kraken_api_key": api_keys.get("kraken", {}).get("api_key", ""),
        "kraken_api_secret": api_keys.get("kraken", {}).get("secret_key", ""),
        "twelve_data_api_key": api_keys.get("twelve_data", ""),
        "alpha_vantage_api_key": api_keys.get("alpha_vantage", ""),
        "fred_api_key": api_keys.get("fred", ""),
        "newsapi_api_key": api_keys.get("news_api", ""),
        "shopify_api_key": api_keys.get("shopify", {}).get("api_key", ""),
        "shopify_shop_name": api_keys.get("shopify", {}).get("shop_name", ""),
        "stripe_api_key": api_keys.get("stripe", "")
    })

@router.post("/api/save-settings")
async def save_api_settings(request: Request):
    """
    Save API settings to api_keys.json and trigger backtest automation.
    """
    try:
        data = await request.json()
        
        config_dir = '/home/autobot/Projet_AUTOBOT/config'
        config_file = os.path.join(config_dir, 'api_keys.json')
        
        existing_keys = {}
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                existing_keys = json.load(f)
        
        api_data = data.get('api', {})
        
        if api_data.get('binance-api-key'):
            existing_keys['binance'] = {
                'api_key': api_data['binance-api-key'],
                'secret_key': api_data.get('binance-api-secret', '')
            }
        
        if api_data.get('coinbase-api-key'):
            existing_keys['coinbase'] = {
                'api_key': api_data['coinbase-api-key'],
                'secret_key': api_data.get('coinbase-api-secret', '')
            }
        
        if api_data.get('kraken-api-key'):
            existing_keys['kraken'] = {
                'api_key': api_data['kraken-api-key'],
                'secret_key': api_data.get('kraken-api-secret', '')
            }
        
        if api_data.get('twelve-data-api-key'):
            existing_keys['twelve_data'] = api_data['twelve-data-api-key']
        
        if api_data.get('alpha-vantage-api-key'):
            existing_keys['alpha_vantage'] = api_data['alpha-vantage-api-key']
        
        if api_data.get('fred-api-key'):
            existing_keys['fred'] = api_data['fred-api-key']
        
        if api_data.get('newsapi-api-key'):
            existing_keys['news_api'] = api_data['newsapi-api-key']
        
        if api_data.get('shopify-api-key'):
            existing_keys['shopify'] = {
                'api_key': api_data['shopify-api-key'],
                'secret_key': api_data.get('shopify-api-secret', ''),
                'shop_name': api_data.get('shopify-shop-name', '')
            }
        
        if api_data.get('stripe-api-key'):
            existing_keys['stripe'] = api_data['stripe-api-key']
        
        with open(config_file, 'w') as f:
            json.dump(existing_keys, f, indent=2)
        
        return JSONResponse(content={
            "status": "success",
            "message": "Configuration sauvegardée avec succès!"
        })
        
    except Exception as e:
        logger.error(f"Error saving API settings: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Erreur: {str(e)}"}
        )
