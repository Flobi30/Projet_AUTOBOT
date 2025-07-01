import stripe
import os
import logging
from typing import Dict, Any, Optional
from fastapi import HTTPException
from sqlalchemy.orm import Session
from ..db.models import UserBalance
from ..db.database import get_db

logger = logging.getLogger(__name__)

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

class StripePaymentManager:
    def __init__(self):
        self.webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    
    async def get_account_balance(self, user_id: str) -> float:
        """Get current account balance from Stripe or database"""
        try:
            db = next(get_db())
            user_balance = db.query(UserBalance).filter(UserBalance.user_id == user_id).first()
            
            if user_balance:
                return float(user_balance.balance)
            else:
                return 0.0
                
        except Exception as e:
            logger.error(f"Error retrieving balance for user {user_id}: {e}")
            return 0.0
    
    async def update_user_balance(self, user_id: str, amount: float, transaction_type: str = "deposit") -> bool:
        """Update user balance in database"""
        try:
            db = next(get_db())
            user_balance = db.query(UserBalance).filter(UserBalance.user_id == user_id).first()
            
            if user_balance:
                if transaction_type == "deposit":
                    user_balance.balance += amount
                elif transaction_type == "withdrawal":
                    if user_balance.balance >= amount:
                        user_balance.balance -= amount
                    else:
                        return False
                else:
                    user_balance.balance = amount
            else:
                user_balance = UserBalance(user_id=user_id, balance=amount)
                db.add(user_balance)
            
            db.commit()
            return True
            
        except Exception as e:
            logger.error(f"Error updating balance for user {user_id}: {e}")
            return False
    
    async def create_payment_intent(self, amount: float, user_id: str) -> Dict[str, Any]:
        """Create Stripe PaymentIntent for deposit"""
        try:
            intent = stripe.PaymentIntent.create(
                amount=int(amount * 100),  # Convert to cents
                currency='eur',
                metadata={'user_id': user_id, 'type': 'deposit'}
            )
            return {
                'client_secret': intent.client_secret,
                'payment_intent_id': intent.id
            }
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error creating payment intent: {str(e)}")
            raise HTTPException(status_code=400, detail=str(e))
    
    async def create_payout(self, amount: float, user_id: str) -> Dict[str, Any]:
        """Create Stripe Payout for withdrawal"""
        try:
            payout = stripe.Payout.create(
                amount=int(amount * 100),
                currency='eur',
                metadata={'user_id': user_id, 'type': 'withdrawal'}
            )
            return {
                'payout_id': payout.id,
                'status': payout.status
            }
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error creating payout: {str(e)}")
            raise HTTPException(status_code=400, detail=str(e))
    
    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify Stripe webhook signature"""
        try:
            stripe.Webhook.construct_event(payload, signature, self.webhook_secret)
            return True
        except ValueError:
            return False
        except stripe.error.SignatureVerificationError:
            return False
    
    async def update_balance_from_webhook(self, event: Dict[str, Any], db: Session):
        """Update user balance based on webhook event"""
        if event['type'] == 'payment_intent.succeeded':
            payment_intent = event['data']['object']
            user_id = payment_intent['metadata']['user_id']
            amount = payment_intent['amount'] / 100  # Convert from cents
            
            balance = db.query(UserBalance).filter(UserBalance.user_id == user_id).first()
            if not balance:
                balance = UserBalance(user_id=user_id, balance=amount)
                db.add(balance)
            else:
                balance.balance += amount
            db.commit()
