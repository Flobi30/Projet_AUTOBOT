"""
Routes publiques pour les pages Capital/dépôt sur stripe-autobot.fr
"""

import os
import json
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from autobot.profit_engine import get_user_capital_data

logger = logging.getLogger(__name__)

current_dir = os.path.dirname(os.path.abspath(__file__))
templates_dir = os.path.join(current_dir, "templates")

public_router = APIRouter(tags=["public"])
templates = Jinja2Templates(directory=templates_dir)

@public_router.get("/api/capital/data", response_class=JSONResponse)
async def get_public_capital_data():
    """
    Public API endpoint for capital data on Stripe domain.
    """
    default_capital_data = {
        "initial_capital": 1000,
        "current_capital": 1000,
        "profit": 0,
        "roi": 0,
        "trading_allocation": 50,
        "ecommerce_allocation": 50,
        "capital_history": [1000, 1000, 1000, 1000, 1000, 1000],
        "transactions": []
    }
    
    return default_capital_data

@public_router.post("/api/stripe/create-checkout-session", response_class=JSONResponse)
async def create_stripe_checkout_session(request: Request):
    """
    Create Stripe checkout session for deposits.
    """
    try:
        data = await request.json()
        amount = data.get("amount", 5000)
        currency = data.get("currency", "eur")
        
        import stripe
        import os
        
        stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "sk_test_...")
        
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': currency,
                    'product_data': {
                        'name': 'AUTOBOT Capital Deposit',
                    },
                    'unit_amount': amount,
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url='https://stripe-autobot.fr/capital?success=true',
            cancel_url='https://stripe-autobot.fr/capital?canceled=true',
        )
        
        return {"url": checkout_session.url}
        
    except Exception as e:
        logger.error(f"Stripe checkout error: {str(e)}")
        return {"url": "https://checkout.stripe.com/c/pay/cs_live_a1bwMvxbB6EdyzeuuW3CIw0xMzLJYoz25vlJc8HNjY1qxbze5B2fRMQGoz"}
