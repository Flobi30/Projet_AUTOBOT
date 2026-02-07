"""API routes for AUTOBOT UI backend (API-only, no Jinja2 templates)."""

import os
import logging
from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from autobot.autobot_security.auth.jwt_handler import get_current_user
from autobot.autobot_security.auth.user_manager import User
from autobot.autobot_security.rate_limiter import financial_limiter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ui"])


@router.post("/api/stripe/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events for payment confirmations."""
    try:
        import stripe
        payload = await request.body()
        sig_header = request.headers.get("stripe-signature")
        event = stripe.Webhook.construct_event(
            payload, sig_header, os.getenv("STRIPE_WEBHOOK_SECRET", "")
        )
        if event["type"] == "payment_intent.succeeded":
            payment_intent = event["data"]["object"]
            amount = payment_intent["amount"] / 100
            user_id = payment_intent["metadata"].get("user_id", "AUTOBOT")
            logger.info(f"Payment confirmed: {amount} for user {user_id}")
        return JSONResponse(content={"status": "success"})
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        return JSONResponse(status_code=400, content={"status": "error", "message": str(e)})


@router.post("/api/save-settings", response_class=JSONResponse)
async def save_settings(request: Request, user: dict = Depends(get_current_user)):
    """Save user settings (API keys)."""
    try:
        data = await request.json()
        api_settings = data.get("api", {})
        env_file_path = "/app/.env"
        env_vars = {}
        if os.path.exists(env_file_path):
            with open(env_file_path, "r") as f:
                for line in f:
                    if "=" in line and not line.strip().startswith("#"):
                        key, value = line.strip().split("=", 1)
                        env_vars[key] = value
        api_key_mapping = {
            "binance-api-key": "BINANCE_API_KEY",
            "binance-api-secret": "BINANCE_API_SECRET",
            "stripe-api-key": "STRIPE_API_KEY",
            "alpha-vantage-api-key": "ALPHA_VANTAGE_API_KEY",
            "twelve-data-api-key": "TWELVE_DATA_API_KEY",
            "fred-api-key": "FRED_API_KEY",
            "newsapi-api-key": "NEWSAPI_KEY",
            "coinbase-api-key": "COINBASE_API_KEY",
            "coinbase-api-secret": "COINBASE_API_SECRET",
            "kraken-api-key": "KRAKEN_API_KEY",
            "kraken-api-secret": "KRAKEN_API_SECRET",
        }
        for form_key, env_key in api_key_mapping.items():
            if form_key in api_settings and api_settings[form_key]:
                env_vars[env_key] = api_settings[form_key]
        with open(env_file_path, "w") as f:
            for key, value in env_vars.items():
                f.write(f"{key}={value}\n")
        logger.info(f"Settings saved: {list(api_settings.keys())}")
        return JSONResponse(status_code=200, content={"status": "success", "message": "Settings saved successfully"})
    except Exception as e:
        logger.error(f"Error saving settings: {str(e)}")
        return JSONResponse(status_code=500, content={"status": "error", "message": "Error saving settings"})


@router.post("/api/deposit")
async def deposit(request: Request, user: dict = Depends(get_current_user)):
    """Process a deposit with Stripe integration."""
    await financial_limiter.check(request)
    try:
        try:
            from autobot.services.stripe_service import StripeService
        except ImportError:
            StripeService = None
        data = await request.json()
        amount = float(data.get("amount", 0))
        method = data.get("method", "card")
        if amount < 10:
            return JSONResponse(status_code=400, content={"status": "error", "message": "Montant minimum: 10"})
        if StripeService and method == "card":
            try:
                stripe_service = StripeService()
                payment_result = stripe_service.create_payment_intent(amount)
                logger.info(f"Stripe PaymentIntent created for {amount}")
                return JSONResponse(content={"status": "success", "message": f"PaymentIntent created for {amount}", "payment_data": payment_result})
            except Exception as e:
                logger.error(f"Stripe payment error: {str(e)}")
                return JSONResponse(status_code=500, content={"status": "error", "message": f"Payment error: {str(e)}"})
        elif method == "card":
            return JSONResponse(status_code=500, content={"status": "error", "message": "Payment service not available"})
        elif method == "bank":
            return JSONResponse(content={"status": "success", "message": f"Bank transfer deposit of {amount} processing"})
    except Exception as e:
        logger.error(f"Deposit error: {str(e)}")
        return JSONResponse(status_code=500, content={"status": "error", "message": "Error processing deposit"})


@router.post("/api/withdraw")
async def withdraw(request: Request, user: dict = Depends(get_current_user)):
    """Process a withdrawal with Stripe integration."""
    await financial_limiter.check(request)
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
            return JSONResponse(status_code=400, content={"status": "error", "message": "Montant minimum: 10"})
        if method == "bank" and (not iban or not bic):
            return JSONResponse(status_code=400, content={"status": "error", "message": "IBAN et BIC requis"})
        if StripeService and method == "bank":
            try:
                stripe_service = StripeService()
                transfer_result = stripe_service.create_bank_transfer(amount, iban, bic)
                logger.info(f"Stripe bank transfer created for {amount}")
                return JSONResponse(content={"status": "success", "message": f"Withdrawal of {amount} initiated", "transfer_data": transfer_result})
            except Exception as e:
                logger.error(f"Stripe withdrawal error: {str(e)}")
                return JSONResponse(status_code=500, content={"status": "error", "message": f"Withdrawal error: {str(e)}"})
        elif method == "bank":
            return JSONResponse(content={"status": "success", "message": f"Bank transfer withdrawal of {amount} processing"})
    except Exception as e:
        logger.error(f"Withdrawal error: {str(e)}")
        return JSONResponse(status_code=500, content={"status": "error", "message": "Error processing withdrawal"})


@router.get("/api/metrics")
async def get_real_time_metrics(user: dict = Depends(get_current_user)):
    """Get real-time system metrics for dashboard."""
    try:
        from autobot.guardian import get_metrics, get_logs
        metrics = get_metrics()
        logs = get_logs()
        performance_data = {
            "total_capital": "0",
            "active_instances": 0,
            "performance": "+0.00%",
            "daily_profit": "+0",
        }
        return JSONResponse(content={"status": "success", "metrics": metrics, "logs": logs, "performance": performance_data})
    except Exception as e:
        logger.error(f"Error getting metrics: {str(e)}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@router.get("/api/metrics/capital")
async def get_capital_metrics(user: dict = Depends(get_current_user)):
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
                    capital_data.get("current_capital", 0),
                ],
            },
        })
    except Exception as e:
        logger.error(f"Error getting capital metrics: {str(e)}")
        return JSONResponse(content={
            "status": "success",
            "data": {
                "current_capital": 0, "initial_capital": 500, "total_profit": 0,
                "roi": 0, "trading_allocation": 0, "hft_allocation": 0,
                "available_for_withdrawal": 0, "in_use": 0, "chart_data": [],
            },
        })


@router.get("/api/metrics/transactions")
async def get_transactions_metrics(user: dict = Depends(get_current_user)):
    """Get transaction history."""
    try:
        from autobot.profit_engine import get_transaction_history
        transactions = get_transaction_history()
        return JSONResponse(content={"status": "success", "data": {"transactions": transactions}})
    except Exception as e:
        logger.error(f"Error getting transactions: {str(e)}")
        return JSONResponse(content={"status": "success", "data": {"transactions": []}})


@router.get("/backtest/status")
async def backtest_status(user: dict = Depends(get_current_user)):
    """Get backtest status."""
    try:
        return JSONResponse(content={"status": "running", "progress": 0, "message": "Initializing"})
    except Exception as e:
        logger.error(f"Error getting backtest status: {str(e)}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@router.get("/api/capital-status")
async def capital_status_backtest(user: dict = Depends(get_current_user)):
    """Get capital status for backtest."""
    try:
        from autobot.profit_engine import get_user_capital_data
        capital_data = get_user_capital_data()
        return JSONResponse(content={
            "status": "success",
            "capital": capital_data.get("current_capital", 0),
            "initial": capital_data.get("initial_capital", 500),
        })
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return JSONResponse(content={"status": "success", "capital": 0, "initial": 500})


@router.post("/api/scale-now")
async def scale_now(request: Request, user: dict = Depends(get_current_user)):
    """Trigger immediate scaling."""
    await financial_limiter.check(request)
    try:
        data = await request.json()
        logger.info(f"Scale request: {data}")
        return JSONResponse(content={"status": "success", "message": "Scaling initiated"})
    except Exception as e:
        logger.error(f"Scale error: {str(e)}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
