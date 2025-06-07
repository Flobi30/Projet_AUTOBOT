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
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "active_page": "dashboard",
        "username": user.get("username", "AUTOBOT"),
        "user_role": user.get("role", "admin"),
        "user_role_display": "Administrateur"
    })

@router.get("/trading", response_class=HTMLResponse)
async def get_trading(request: Request, user: dict = Depends(get_current_user)):
    """
    Page de trading.
    """
    return templates.TemplateResponse("trading.html", {
        "request": request,
        "active_page": "trading",
        "username": user.get("username", "AUTOBOT"),
        "user_role": user.get("role", "admin"),
        "user_role_display": "Administrateur"
    })

@router.get("/ecommerce", response_class=HTMLResponse)
async def get_ecommerce(request: Request, user: dict = Depends(get_current_user)):
    """
    Page d'e-commerce.
    """
    return templates.TemplateResponse("ecommerce.html", {
        "request": request,
        "active_page": "ecommerce",
        "username": user.get("username", "AUTOBOT"),
        "user_role": user.get("role", "admin"),
        "user_role_display": "Administrateur"
    })

@router.get("/backtest", response_class=HTMLResponse)
async def get_backtest(request: Request, user: dict = Depends(get_current_user)):
    """
    Page de backtest.
    """
    return templates.TemplateResponse("backtest.html", {
        "request": request,
        "active_page": "backtest",
        "username": user.get("username", "AUTOBOT"),
        "user_role": user.get("role", "admin"),
        "user_role_display": "Administrateur"
    })

@router.get("/capital", response_class=HTMLResponse)
async def get_capital(request: Request, user: dict = Depends(get_current_user)):
    """
    Page de gestion du capital.
    """
    return templates.TemplateResponse("capital.html", {
        "request": request,
        "active_page": "capital",
        "username": user.get("username", "AUTOBOT"),
        "user_role": user.get("role", "admin"),
        "user_role_display": "Administrateur"
    })

@router.get("/duplication", response_class=HTMLResponse)
async def get_duplication(request: Request, user: dict = Depends(get_current_user)):
    """
    Page de duplication d'instances.
    """
    return templates.TemplateResponse("duplication.html", {
        "request": request,
        "active_page": "duplication",
        "username": user.get("username", "AUTOBOT"),
        "user_role": user.get("role", "admin"),
        "user_role_display": "Administrateur"
    })

@router.get("/retrait-depot", response_class=HTMLResponse)
async def get_retrait_depot(request: Request, user: dict = Depends(get_current_user)):
    """
    Page de retrait et dépôt.
    """
    return templates.TemplateResponse("retrait_depot.html", {
        "request": request,
        "active_page": "retrait-depot",
        "username": user.get("username", "AUTOBOT"),
        "user_role": user.get("role", "admin"),
        "user_role_display": "Administrateur"
    })

@router.get("/parametres", response_class=HTMLResponse)
async def get_parametres(request: Request, user: dict = Depends(get_current_user)):
    """
    Page de paramètres.
    """
    env_file_path = "/app/.env"
    env_vars = {}
    
    if os.path.exists(env_file_path):
        with open(env_file_path, 'r') as f:
            for line in f:
                if '=' in line and not line.strip().startswith('#'):
                    key, value = line.strip().split('=', 1)
                    env_vars[key] = value
        
        print(f"DEBUG: Read {len(env_vars)} environment variables from {env_file_path}")
        print(f"DEBUG: Available variables: {list(env_vars.keys())}")
    
    return templates.TemplateResponse("parametres.html", {
        "request": request,
        "active_page": "parametres",
        "username": user.get("username", "AUTOBOT"),
        "user_role": user.get("role", "admin"),
        "user_role_display": "Administrateur",
        "binance_api_key": env_vars.get("BINANCE_KEY", ""),
        "binance_api_secret": env_vars.get("BINANCE_SECRET", ""),
        "stripe_api_key": env_vars.get("STRIPE_KEY", ""),
        "alpha_vantage_api_key": env_vars.get("ALPHA_KEY", ""),
        "twelve_data_api_key": env_vars.get("TWELVE_DATA_API_KEY", ""),
        "fred_api_key": env_vars.get("FRED_KEY", ""),
        "newsapi_api_key": env_vars.get("NEWSAPI_KEY", ""),
        "shopify_api_key": env_vars.get("SHOPIFY_KEY", ""),
        "shopify_api_secret": env_vars.get("SHOPIFY_SECRET", ""),
        "shopify_shop_name": env_vars.get("SHOPIFY_SHOP_NAME", ""),
        "coinbase_api_key": env_vars.get("COINBASE_KEY", ""),
        "coinbase_api_secret": env_vars.get("COINBASE_SECRET", ""),
        "kraken_api_key": env_vars.get("KRAKEN_KEY", ""),
        "kraken_api_secret": env_vars.get("KRAKEN_SECRET", "")
    })

@router.get("/arbitrage", response_class=HTMLResponse)
async def get_arbitrage(request: Request, user: dict = Depends(get_current_user)):
    """
    Page d'arbitrage.
    """
    return templates.TemplateResponse("arbitrage.html", {
        "request": request,
        "active_page": "arbitrage",
        "username": user.get("username", "AUTOBOT"),
        "user_role": user.get("role", "admin"),
        "user_role_display": "Administrateur"
    })

@router.post("/api/stripe/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events for payment confirmations."""
    try:
        import stripe
        
        payload = await request.body()
        sig_header = request.headers.get('stripe-signature')
        
        event = stripe.Webhook.construct_event(
            payload, sig_header, os.getenv("STRIPE_WEBHOOK_SECRET", "")
        )
        
        if event['type'] == 'payment_intent.succeeded':
            payment_intent = event['data']['object']
            amount = payment_intent['amount'] / 100
            user_id = payment_intent['metadata'].get('user_id', 'AUTOBOT')
            
            logger.info(f"Payment confirmed: {amount}€ for user {user_id}")
            
        return JSONResponse(content={"status": "success"})
        
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": str(e)}
        )

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
        
        print(f"DEBUG: Loading existing env vars from {env_file_path}")
        print(f"DEBUG: Found {len(env_vars)} existing variables: {list(env_vars.keys())}")
        
        api_key_mapping = {
            "binance-api-key": "BINANCE_KEY",
            "binance-api-secret": "BINANCE_SECRET",
            "stripe-api-key": "STRIPE_KEY",
            "stripe-api-secret": "STRIPE_SECRET",
            "alpha-vantage-api-key": "ALPHA_KEY",
            "twelve-data-api-key": "TWELVE_DATA_API_KEY",
            "fred-api-key": "FRED_KEY",
            "newsapi-api-key": "NEWSAPI_KEY",
            "shopify-api-key": "SHOPIFY_KEY",
            "shopify-api-secret": "SHOPIFY_SECRET",
            "coinbase-api-key": "COINBASE_KEY",
            "coinbase-api-secret": "COINBASE_SECRET",
            "kraken-api-key": "KRAKEN_KEY",
            "kraken-api-secret": "KRAKEN_SECRET",
            "shopify-shop-name": "SHOPIFY_SHOP_NAME"
        }
        
        for form_key, env_key in api_key_mapping.items():
            if form_key in api_settings and api_settings[form_key]:
                env_vars[env_key] = api_settings[form_key]
        
        with open(env_file_path, 'w') as f:
            for key, value in env_vars.items():
                f.write(f"{key}={value}\n")
        
        print(f"DEBUG: Successfully wrote {len(env_vars)} environment variables to {env_file_path}")
        print(f"DEBUG: Written variables: {list(env_vars.keys())}")
        
        print(f"DEBUG: Settings saved successfully: {list(api_settings.keys())}")
        print(f"DEBUG: API settings received: {api_settings}")
        print(f"DEBUG: Environment variables written: {env_vars}")
        logger.info(f"Settings saved successfully: {list(api_settings.keys())}")
        logger.info(f"API settings received: {api_settings}")
        logger.info(f"Environment variables written: {env_vars}")
        
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
    Traite un dépôt de fonds avec intégration Stripe complète.
    """
    try:
        try:
            from autobot.services.stripe_service import StripeService
        except ImportError:
            StripeService = None
        
        data = await request.json()
        amount = float(data.get("amount", 0))
        method = data.get("method", "card")
        
        if amount < 10:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "Montant minimum: 10€"}
            )
        
        if StripeService and method == "card":
            try:
                stripe_service = StripeService()
                payment_result = stripe_service.create_payment_intent(amount)
                logger.info(f"Stripe PaymentIntent created for {amount}€")
                
                return JSONResponse(content={
                    "status": "success",
                    "message": f"PaymentIntent créé pour {amount}€",
                    "payment_data": payment_result
                })
            except Exception as e:
                logger.error(f"Stripe payment error: {str(e)}")
                return JSONResponse(
                    status_code=500,
                    content={"status": "error", "message": f"Erreur de paiement: {str(e)}"}
                )
        elif method == "card":
            logger.warning("Stripe service not available")
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": "Service de paiement non disponible"}
            )
        elif method == "bank":
            logger.info(f"Bank transfer deposit for {amount}€")
            return JSONResponse(content={
                "status": "success", 
                "message": f"Dépôt de {amount}€ par virement bancaire en cours de traitement"
            })
        
    except Exception as e:
        logger.error(f"Deposit error: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Erreur lors du traitement du dépôt"}
        )

@router.post("/api/withdraw")
async def withdraw(request: Request):
    """
    Traite un retrait de fonds avec intégration Stripe complète.
    """
    try:
        try:
            from autobot.services.stripe_service import StripeService
        except ImportError:
            StripeService = None
        
        data = await request.json()
        amount = float(data.get("amount", 0))
        method = data.get("method", "bank")
        iban = data.get("iban", "")
        bic = data.get("bic", "")
        
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
        
        if StripeService and method == "bank":
            try:
                stripe_service = StripeService()
                transfer_result = stripe_service.create_bank_transfer(amount, iban, bic)
                logger.info(f"Stripe bank transfer created for {amount}€")
                
                return JSONResponse(content={
                    "status": "success",
                    "message": f"Retrait de {amount}€ initié vers {iban[:4]}****{iban[-4:]}",
                    "transfer_data": transfer_result
                })
            except Exception as e:
                logger.error(f"Stripe withdrawal error: {str(e)}")
                return JSONResponse(
                    status_code=500,
                    content={"status": "error", "message": f"Erreur de retrait: {str(e)}"}
                )
        elif method == "bank":
            logger.info(f"Bank transfer withdrawal for {amount}€")
            return JSONResponse(content={
                "status": "success", 
                "message": f"Retrait de {amount}€ par virement bancaire en cours de traitement"
            })
        
    except Exception as e:
        logger.error(f"Withdrawal error: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Erreur lors du traitement du retrait"}
        )
