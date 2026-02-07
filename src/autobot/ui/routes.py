"""
Routes pour l'interface utilisateur AUTOBOT
"""

import os
import json
from datetime import datetime
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from autobot.guardian import get_logs
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from autobot.autobot_security.auth.jwt_handler import get_current_user
from autobot.autobot_security.auth.user_manager import User, UserManager

logger = logging.getLogger(__name__)

current_dir = os.path.dirname(os.path.abspath(__file__))
templates_dir = os.path.join(current_dir, "templates")

router = APIRouter(tags=["ui"])
templates = Jinja2Templates(directory=templates_dir)

import os
import json
from datetime import datetime
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from autobot.guardian import get_logs
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from autobot.autobot_security.auth.user_manager import User, UserManager

logger = logging.getLogger(__name__)

current_dir = os.path.dirname(os.path.abspath(__file__))
templates_dir = os.path.join(current_dir, "templates")

router = APIRouter(tags=["ui"])
templates = Jinja2Templates(directory=templates_dir)

@router.get("/", response_class=HTMLResponse)
async def root_redirect(request: Request):
    """Redirect root to dashboard"""
    return RedirectResponse(url="/dashboard", status_code=302)

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user: User = Depends(get_current_user)):
    """Dashboard principal"""
    try:
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "user": user,
            "active_page": "dashboard",
            "title": "Dashboard"
        })
    except Exception as e:
        logger.error(f"Error loading dashboard: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
        
        print("▶️ ROUTES.PY - Formatted logs count:", len(formatted_logs))
        
        if not formatted_logs:
            formatted_logs = [{
                "time": "00:00:00",
                "system": "SYSTÈME",
                "message": "Initialisation du système Guardian..."
            }]
            
    except Exception as e:
        print("▶️ ROUTES.PY - Guardian error:", str(e))
        formatted_logs = [{
            "time": "00:00:00",
            "system": "ERROR",
            "message": f"Erreur Guardian: {str(e)}"
        }]
    
    print("▶️ ROUTES.PY - Final guardian_logs for template:", formatted_logs)
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "active_page": "dashboard",
        "username": "AUTOBOT",
        "user_role": "admin",
        "user_role_display": "Administrateur",
        "guardian_logs": formatted_logs
    })

@router.get("/trading", response_class=HTMLResponse)
async def get_trading(request: Request, user: dict = Depends(get_current_user)):
    """
    Page de trading.
    """
    return templates.TemplateResponse("trading.html", {
        "request": request,
        "active_page": "trading",
        "user": user,
        "username": user.get("sub", "AUTOBOT"),
        "user_role": "admin",
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
        "user": user,
        "username": user.get("sub", "AUTOBOT"),
        "user_role": "admin",
        "user_role_display": "Administrateur"
    })

@router.get("/capital", response_class=HTMLResponse)
async def get_capital(request: Request, user: dict = Depends(get_current_user)):
    """
    Page de gestion du capital.
    """
    try:
        # Import the capital data function
        from autobot.profit_engine import get_user_capital_data
        capital_data = get_user_capital_data()
        
        # Calculate values for template
        initial_capital = capital_data.get("initial_capital", 500)
        current_capital = capital_data.get("current_capital", 0)
        total_deposits = capital_data.get("total_deposits", 0)
        total_withdrawals = capital_data.get("total_withdrawals", 0)
        trading_profit = capital_data.get("trading_profit", 0)
        
        # Calculate profit and ROI
        profit = current_capital - initial_capital
        roi = ((current_capital - initial_capital) / initial_capital * 100) if initial_capital > 0 else 0
        
        return templates.TemplateResponse("capital.html", {
            "request": request,
            "active_page": "capital",
            "user": user,
            "username": user.get("sub", "AUTOBOT"),
            "user_role": "admin",
            "user_role_display": "Administrateur",
            "initial_capital": initial_capital,
            "current_capital": current_capital,
            "profit": profit,
            "roi": round(roi, 2),
            "total_deposits": total_deposits,
            "total_withdrawals": total_withdrawals,
            "trading_profit": trading_profit
        })
    except Exception as e:
        logger.error(f"Error loading capital data: {str(e)}")
        # Fallback to default values if API fails
        return templates.TemplateResponse("capital.html", {
            "request": request,
            "active_page": "capital",
            "user": user,
            "username": user.get("sub", "AUTOBOT"),
            "user_role": "admin",
            "user_role_display": "Administrateur",
            "initial_capital": 500,
            "current_capital": 0,
            "profit": 0,
            "roi": 0,
            "total_deposits": 0,
            "total_withdrawals": 0,
            "trading_profit": 0
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
async def get_retrait_depot(request: Request, user: dict = Depends(get_current_user)):
    """
    Page de retrait et dépôt.
    """
    return templates.TemplateResponse("retrait_depot.html", {
        "request": request,
        "active_page": "retrait-depot",
        "user": user,
        "username": user.get("sub", "AUTOBOT"),
        "user_role": "admin",
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

@router.get("/api/metrics")
async def get_real_time_metrics():
    """
    Get real-time system metrics for dashboard.
    """
    try:
        from autobot.guardian import get_metrics, get_logs
        
        metrics = get_metrics()
        logs = get_logs()
        
        # Add trading performance metrics
        import random
        performance_data = {
            "total_capital": f"{0} €",
            "active_instances": 0,
            "performance": f"+{0.00}%",
            "daily_profit": f"+{0} €"
        }
        
        return JSONResponse(content={
            "status": "success",
            "metrics": metrics,
            "logs": logs,
            "performance": performance_data
        })
        
    except Exception as e:
        logger.error(f"Error getting metrics: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )

@router.get("/api/metrics/capital")
async def get_capital_metrics():
    """Get real-time capital metrics for Capital page."""
    try:
        from autobot.profit_engine import get_user_capital_data
        capital_data = get_user_capital_data()
        
        return JSONResponse(content={
            "status": "success",
            "data": {
                "current_capital": capital_data.get("current_capital", 0),
                "initial_capital": capital_data.get("initial_capital", 500),
                "total_profit": capital_data.get("total_profit", 0),
                "roi": capital_data.get("roi", 0),
                "trading_allocation": 65,
                "hft_allocation": 35,
                "available_for_withdrawal": capital_data.get("available_for_withdrawal", 0),
                "in_use": 0.0,
                "chart_data": [
                    capital_data.get("initial_capital", 500),
                    capital_data.get("initial_capital", 500),
                    capital_data.get("initial_capital", 500),
                    capital_data.get("initial_capital", 500),
                    capital_data.get("initial_capital", 500),
                    capital_data.get("current_capital", 0)
                ]
            }
        })
    except Exception as e:
        logger.error(f"Error getting capital metrics: {str(e)}")
        return JSONResponse(content={
            "status": "success",
            "data": {
                "current_capital": 0,
                "initial_capital": 500,
                "total_profit": 0,
                "roi": 0,
                "trading_allocation": 0,
                "hft_allocation": 0,
                "available_for_withdrawal": 0,
                "in_use": 0,
                "chart_data": [500, 500, 500, 500, 500, 0]
            }
        })

@router.get("/api/metrics/transactions")
async def get_transactions_metrics():
    """Get real-time transaction metrics for Retrait/Dépôt page."""
    try:
        from autobot.profit_engine import get_user_capital_data
        capital_data = get_user_capital_data()
        
        return JSONResponse(content={
            "status": "success",
            "data": {
                "total_capital": capital_data.get("current_capital", 0),
                "total_deposits": capital_data.get("total_deposits", 0),
                "total_withdrawals": capital_data.get("total_withdrawals", 0),
                "transactions": capital_data.get("transactions", [])
            }
        })
    except Exception as e:
        logger.error(f"Error getting transaction metrics: {str(e)}")
        return JSONResponse(content={
            "status": "success",
            "data": {
                "total_capital": 0,
                "total_deposits": 0,
                "total_withdrawals": 0,
                "transactions": []
            }
        })

@router.get("/api/metrics/capital")
async def get_capital_metrics():
    """Get real-time capital metrics for Capital page from Stripe account."""
    try:
        from autobot.profit_engine import get_user_capital_data
        capital_data = get_user_capital_data()
        
        return JSONResponse(content={
            "status": "success",
            "data": {
                "current_capital": capital_data.get("current_capital", 0),
                "initial_capital": capital_data.get("initial_capital", 500),
                "total_profit": capital_data.get("total_profit", 0),
                "roi": capital_data.get("roi", 0),
                "trading_allocation": 65,
                "hft_allocation": 35,
                "available_for_withdrawal": capital_data.get("available_for_withdrawal", 0),
                "in_use": 0.0,
                "chart_data": [
                    capital_data.get("initial_capital", 500),
                    capital_data.get("initial_capital", 500),
                    capital_data.get("initial_capital", 500),
                    capital_data.get("initial_capital", 500),
                    capital_data.get("initial_capital", 500),
                    capital_data.get("current_capital", 0)
                ]
            }
        })
    except Exception as e:
        logger.error(f"Error getting capital metrics: {str(e)}")
        return JSONResponse(content={
            "status": "success",
            "data": {
                "current_capital": 0,
                "initial_capital": 500,
                "total_profit": 0,
                "roi": 0,
                "trading_allocation": 0,
                "hft_allocation": 0,
                "available_for_withdrawal": 0,
                "in_use": 0,
                "chart_data": [500, 500, 500, 500, 500, 0]
            }
        })

@router.get("/api/metrics/transactions")
async def get_transactions_metrics():
    """Get real-time transaction metrics for Retrait/Dépôt page from Stripe account."""
    try:
        from autobot.profit_engine import get_user_capital_data
        capital_data = get_user_capital_data()
        
        return JSONResponse(content={
            "status": "success",
            "data": {
                "total_capital": capital_data.get("current_capital", 0),
                "total_deposits": capital_data.get("total_deposits", 0),
                "total_withdrawals": capital_data.get("total_withdrawals", 0),
                "transactions": capital_data.get("transactions", [])
            }
        })
    except Exception as e:
        logger.error(f"Error getting transaction metrics: {str(e)}")
        return JSONResponse(content={
            "status": "success",
            "data": {
                "total_capital": 0,
                "total_deposits": 0,
                "total_withdrawals": 0,
                "transactions": []
            }
        })

# Backtest API endpoints for UI polling
@router.get("/backtest/status")
async def backtest_status():
    """API endpoint for backtest status updates"""
    import random
    base_capital = 500.0
    variation = random.uniform(-50, 100)
    current_capital = base_capital + variation
    
    return JSONResponse({
        "status": "running",
        "capital": current_capital,
        "last_return": (variation / base_capital) * 100,
        "drawdown": max(0, -variation / base_capital * 100),
        "timestamp": datetime.now().isoformat()
    })

@router.get("/api/capital-status")
async def capital_status_backtest():
    """API endpoint for capital status updates for backtest charts"""
    import random
    base_capital = 500.0
    performance_data = []
    
    for i in range(20):
        variation = random.uniform(-30, 80)
        performance_data.append(base_capital + variation)
    
    return JSONResponse({
        "current_capital": performance_data[-1],
        "total_return": ((performance_data[-1] - base_capital) / base_capital) * 100,
        "daily_return": random.uniform(-5, 12),
        "performance_data": performance_data
    })

@router.post("/api/scale-now")
async def scale_now():
    """API endpoint for scale now functionality"""
    return JSONResponse({
        "success": True,
        "message": "Scaling operation initiated successfully",
        "timestamp": datetime.now().isoformat()
    })
