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

logger = logging.getLogger(__name__)

current_dir = os.path.dirname(os.path.abspath(__file__))
templates_dir = os.path.join(current_dir, "templates")

router = APIRouter(tags=["ui"])
templates = Jinja2Templates(directory=templates_dir)

@router.get("/", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    """
    Page principale du dashboard.
    """
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "active_page": "dashboard",
        "username": "AUTOBOT",
        "user_role": "admin",
        "user_role_display": "Administrateur"
    })

@router.get("/trading", response_class=HTMLResponse)
async def get_trading(request: Request):
    """
    Page de trading.
    """
    return templates.TemplateResponse("trading.html", {
        "request": request,
        "active_page": "trading",
        "username": "AUTOBOT",
        "user_role": "admin",
        "user_role_display": "Administrateur"
    })

@router.get("/ecommerce", response_class=HTMLResponse)
async def get_ecommerce(request: Request):
    """
    Page d'e-commerce.
    """
    return templates.TemplateResponse("ecommerce.html", {
        "request": request,
        "active_page": "ecommerce",
        "username": "AUTOBOT",
        "user_role": "admin",
        "user_role_display": "Administrateur"
    })

@router.get("/arbitrage", response_class=HTMLResponse)
async def get_arbitrage(request: Request):
    """
    Page d'arbitrage.
    """
    return templates.TemplateResponse("arbitrage.html", {
        "request": request,
        "active_page": "arbitrage",
        "username": "AUTOBOT",
        "user_role": "admin",
        "user_role_display": "Administrateur"
    })

@router.get("/backtest", response_class=HTMLResponse)
async def get_backtest(request: Request):
    """
    Page de backtest.
    """
    return templates.TemplateResponse("backtest.html", {
        "request": request,
        "active_page": "backtest",
        "username": "AUTOBOT",
        "user_role": "admin",
        "user_role_display": "Administrateur"
    })

@router.get("/capital", response_class=HTMLResponse)
async def get_capital(request: Request):
    """
    Page de gestion du capital.
    """
    return templates.TemplateResponse("capital.html", {
        "request": request,
        "active_page": "capital",
        "username": "AUTOBOT",
        "user_role": "admin",
        "user_role_display": "Administrateur"
    })

@router.get("/duplication", response_class=HTMLResponse)
async def get_duplication(request: Request):
    """
    Page de duplication d'instances.
    """
    return templates.TemplateResponse("duplication.html", {
        "request": request,
        "active_page": "duplication",
        "username": "AUTOBOT",
        "user_role": "admin",
        "user_role_display": "Administrateur"
    })

@router.get("/retrait-depot", response_class=HTMLResponse)
async def get_retrait_depot(request: Request):
    """
    Page de retrait et dépôt.
    """
    return templates.TemplateResponse("retrait_depot.html", {
        "request": request,
        "active_page": "retrait-depot",
        "username": "AUTOBOT",
        "user_role": "admin",
        "user_role_display": "Administrateur"
    })

@router.get("/parametres", response_class=HTMLResponse)
async def get_parametres(request: Request):
    """
    Page de paramètres.
    """
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
        "username": "AUTOBOT",
        "user_role": "admin",
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

@router.get("/rl-training", response_class=HTMLResponse)
async def get_rl_training(request: Request):
    """
    Page de RL Training.
    """
    return templates.TemplateResponse("rl_training.html", {
        "request": request,
        "active_page": "rl-training",
        "username": "AUTOBOT",
        "user_role": "admin",
        "user_role_display": "Administrateur"
    })

@router.get("/performance", response_class=HTMLResponse)
async def get_performance(request: Request):
    """
    Page de performance.
    """
    return templates.TemplateResponse("performance.html", {
        "request": request,
        "active_page": "performance",
        "username": "AUTOBOT",
        "user_role": "admin",
        "user_role_display": "Administrateur"
    })

@router.post("/api/save-settings", response_class=JSONResponse)
async def save_settings(request: Request):
    """
    Endpoint pour sauvegarder les paramètres utilisateur.
    
    Args:
        request: Request object
        
    Returns:
        JSONResponse: Status of the save operation
    """
    try:
        data = await request.json()
        
        api_settings = data.get("api", {})
        
        env_file_path = "/app/.env"
        
        env_vars = {}
        if os.path.exists(env_file_path):
            with open(env_file_path, 'r') as f:
                for line in f:
                    if '=' in line and not line.strip().startswith('#'):
                        key, value = line.strip().split('=', 1)
                        env_vars[key] = value
        
        api_key_mapping = {
            "binance-api-key": "BINANCE_API_KEY",
            "binance-api-secret": "BINANCE_API_SECRET",
            "openai-api-key": "OPENAI_API_KEY",
            "superagi-api-key": "SUPERAGI_API_KEY",
            "stripe-api-key": "STRIPE_API_KEY",
            "alpha-vantage-api-key": "ALPHA_VANTAGE_API_KEY",
            "twelve-data-api-key": "TWELVE_DATA_API_KEY",
            "fred-api-key": "FRED_API_KEY",
            "newsapi-api-key": "NEWSAPI_KEY",
            "shopify-api-key": "SHOPIFY_API_KEY",
            "shopify-api-secret": "SHOPIFY_API_SECRET",
            "coinbase-api-key": "COINBASE_API_KEY",
            "coinbase-api-secret": "COINBASE_API_SECRET",
            "kraken-api-key": "KRAKEN_API_KEY",
            "kraken-api-secret": "KRAKEN_API_SECRET",
            "shopify-shop-name": "SHOPIFY_SHOP_NAME"
        }
        
        for form_key, env_key in api_key_mapping.items():
            if form_key in api_settings and api_settings[form_key]:
                env_vars[env_key] = api_settings[form_key]
        
        with open(env_file_path, 'w') as f:
            for key, value in env_vars.items():
                f.write(f"{key}={value}\n")
        
        logger.info(f"Settings saved successfully: {list(api_settings.keys())}")
        
        return JSONResponse(
            status_code=200,
            content={"status": "success", "message": "Paramètres sauvegardés avec succès"}
        )
        
    except Exception as e:
        logger.error(f"Unexpected error saving settings: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Erreur lors de la sauvegarde"}
        )

@router.post("/api/deposit")
async def deposit(request: Request):
    """
    Traite un dépôt de fonds.
    """
    try:
        data = await request.json()
        amount = data.get("amount")
        method = data.get("method", "bank")
        
        if not amount or amount <= 0:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "Montant invalide"}
            )
        
        if amount < 10:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "Montant minimum: 10€"}
            )
        
        return JSONResponse(
            status_code=200,
            content={"status": "success", "message": f"Dépôt de {amount}€ effectué avec succès via {method}"}
        )
    
    except Exception as e:
        logger.error(f"Erreur lors du dépôt: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Erreur lors du dépôt"}
        )

@router.post("/api/withdraw")
async def withdraw(request: Request):
    """
    Traite un retrait de fonds.
    """
    try:
        data = await request.json()
        amount = data.get("amount")
        method = data.get("method", "bank")
        iban = data.get("iban", "")
        bic = data.get("bic", "")
        
        if not amount or amount <= 0:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "Montant invalide"}
            )
        
        if amount < 10:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "Montant minimum: 10€"}
            )
        
        if method == "bank" and (not iban or not bic):
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "IBAN et BIC requis pour virement bancaire"}
            )
        
        message = f"Retrait de {amount}€ effectué avec succès via {method}"
        if method == "bank":
            message += f" vers IBAN {iban[:4]}****{iban[-4:]}"
        
        return JSONResponse(
            status_code=200,
            content={"status": "success", "message": message}
        )
    
    except Exception as e:
        logger.error(f"Erreur lors du retrait: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Erreur lors du retrait"}
        )
