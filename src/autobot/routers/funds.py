from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
import stripe
import os
import json
import hmac
import hashlib
from typing import Dict, Any
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize Stripe
stripe.api_key = os.getenv('STRIPE_API_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')

# Balance file path
BALANCE_FILE = '/app/data/user_balance.json'

def load_balance() -> Dict[str, float]:
    """Load user balance from JSON file"""
    try:
        if os.path.exists(BALANCE_FILE):
            with open(BALANCE_FILE, 'r') as f:
                return json.load(f)
        return {'balance': 0.0, 'reserved': 0.0}
    except Exception as e:
        logger.error(f"Error loading balance: {e}")
        return {'balance': 0.0, 'reserved': 0.0}

def save_balance(balance_data: Dict[str, float]) -> None:
    """Save user balance to JSON file"""
    try:
        os.makedirs(os.path.dirname(BALANCE_FILE), exist_ok=True)
        with open(BALANCE_FILE, 'w') as f:
            json.dump(balance_data, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving balance: {e}")

@router.post("/funds/deposit")
async def create_deposit(request: Request):
    """Create a Stripe PaymentIntent for deposit"""
    try:
        body = await request.json()
        amount = body.get('amount')
        
        if not amount or amount <= 0:
            raise HTTPException(status_code=400, detail="Invalid amount")
        
        # Convert to cents for Stripe
        amount_cents = int(amount * 100)
        
        # Create PaymentIntent
        intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency='eur',
            metadata={
                'type': 'deposit',
                'user': 'autobot'
            }
        )
        
        logger.info(f"Created PaymentIntent {intent.id} for amount {amount}")
        
        return JSONResponse({
            'client_secret': intent.client_secret,
            'amount': amount
        })
        
    except Exception as e:
        logger.error(f"Error creating deposit: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events"""
    try:
        payload = await request.body()
        sig_header = request.headers.get('stripe-signature')
        
        if not STRIPE_WEBHOOK_SECRET:
            logger.warning("Webhook secret not configured")
            return JSONResponse({'status': 'webhook secret not configured'})
        
        # Verify webhook signature
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, STRIPE_WEBHOOK_SECRET
            )
        except ValueError as e:
            logger.error(f"Invalid payload: {e}")
            raise HTTPException(status_code=400, detail="Invalid payload")
        except stripe.error.SignatureVerificationError as e:
            logger.error(f"Invalid signature: {e}")
            raise HTTPException(status_code=400, detail="Invalid signature")
        
        # Handle the event
        if event['type'] == 'payment_intent.succeeded':
            payment_intent = event['data']['object']
            amount = payment_intent['amount'] / 100  # Convert from cents
            
            # Update user balance
            balance_data = load_balance()
            balance_data['balance'] += amount
            save_balance(balance_data)
            
            logger.info(f"Deposit successful: +{amount} EUR, new balance: {balance_data['balance']}")
            
        elif event['type'] == 'payment_intent.payment_failed':
            payment_intent = event['data']['object']
            logger.warning(f"Payment failed: {payment_intent['id']}")
            
        elif event['type'] == 'charge.dispute.created':
            logger.warning(f"Dispute created for charge")
            
        else:
            logger.info(f"Unhandled event type: {event['type']}")
        
        return JSONResponse({'status': 'success'})
        
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/funds/withdraw")
async def create_withdrawal(request: Request):
    """Create a withdrawal (Stripe Payout)"""
    try:
        body = await request.json()
        amount = body.get('amount')
        
        if not amount or amount <= 0:
            raise HTTPException(status_code=400, detail="Invalid amount")
        
        # Check available balance
        balance_data = load_balance()
        available = balance_data['balance'] - balance_data['reserved']
        
        if amount > available:
            raise HTTPException(
                status_code=400, 
                detail=f"Insufficient funds. Available: {available} EUR"
            )
        
        # Convert to cents for Stripe
        amount_cents = int(amount * 100)
        
        # Create Payout (requires Stripe Connect setup)
        # For now, we'll simulate the withdrawal
        logger.info(f"Withdrawal request: {amount} EUR")
        
        # Update balance
        balance_data['balance'] -= amount
        save_balance(balance_data)
        
        logger.info(f"Withdrawal processed: -{amount} EUR, new balance: {balance_data['balance']}")
        
        return JSONResponse({
            'status': 'success',
            'amount': amount,
            'new_balance': balance_data['balance']
        })
        
    except Exception as e:
        logger.error(f"Error processing withdrawal: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/funds/status")
async def get_funds_status():
    """Get current balance from real Stripe account"""
    try:
        # Get actual Stripe balance
        balance = stripe.Balance.retrieve()
        available_balance = balance.available[0].amount / 100 if balance.available else 0.0
        pending_balance = balance.pending[0].amount / 100 if balance.pending else 0.0
        
        # Get transaction history for totals
        charges = stripe.Charge.list(limit=100)
        total_deposits = sum(charge.amount / 100 for charge in charges.data if charge.paid and charge.amount > 0)
        
        # Get refunds for withdrawals
        refunds = stripe.Refund.list(limit=100)
        total_withdrawals = sum(refund.amount / 100 for refund in refunds.data)
        
        return JSONResponse({
            'balance': available_balance,
            'reserved': pending_balance,
            'available': available_balance,
            'total_deposits': total_deposits,
            'total_withdrawals': total_withdrawals
        })
        
    except Exception as e:
        logger.error(f"Error getting real Stripe funds status: {e}")
        # Return zero values if Stripe API fails instead of fake data
        return JSONResponse({
            'balance': 0.0,
            'reserved': 0.0,
            'available': 0.0,
            'total_deposits': 0.0,
            'total_withdrawals': 0.0
        })
