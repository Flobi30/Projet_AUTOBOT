import stripe
import os
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class StripeService:
    def __init__(self):
        self.api_key = os.getenv("STRIPE_API_KEY")
        if self.api_key:
            stripe.api_key = self.api_key

    def create_payment_intent(self, amount: float, currency: str = "eur", 
                            payment_method_types: list = None) -> Dict[str, Any]:
        """Create a Stripe PaymentIntent for deposit processing."""
        if not self.api_key:
            raise ValueError("Stripe API key not configured")
        
        if payment_method_types is None:
            payment_method_types = ["card"]
        
        try:
            payment_intent = stripe.PaymentIntent.create(
                amount=int(amount * 100),  # Stripe uses cents
                currency=currency,
                payment_method_types=payment_method_types,
                metadata={
                    "user_id": "AUTOBOT",
                    "type": "deposit"
                }
            )
            
            logger.info(f"Created PaymentIntent {payment_intent.id} for {amount}€")
            return {
                "client_secret": payment_intent.client_secret,
                "payment_intent_id": payment_intent.id,
                "amount": amount,
                "currency": currency
            }
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error creating PaymentIntent: {str(e)}")
            raise

    def create_bank_transfer(self, amount: float, iban: str, bic: str) -> Dict[str, Any]:
        """Create a bank transfer for withdrawal processing."""
        if not self.api_key:
            raise ValueError("Stripe API key not configured")
        
        try:
            transfer = stripe.Transfer.create(
                amount=int(amount * 100),
                currency="eur",
                destination=f"ba_{iban}",
                metadata={
                    "user_id": "AUTOBOT",
                    "type": "withdrawal",
                    "iban": iban,
                    "bic": bic
                }
            )
            
            logger.info(f"Created bank transfer {transfer.id} for {amount}€ to {iban[:4]}****{iban[-4:]}")
            return {
                "transfer_id": transfer.id,
                "amount": amount,
                "iban": iban,
                "status": transfer.status
            }
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error creating bank transfer: {str(e)}")
            raise

    def confirm_payment_intent(self, payment_intent_id: str) -> Dict[str, Any]:
        """Confirm a PaymentIntent and return status."""
        try:
            payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
            return {
                "id": payment_intent.id,
                "status": payment_intent.status,
                "amount": payment_intent.amount / 100,
                "currency": payment_intent.currency
            }
        except stripe.error.StripeError as e:
            logger.error(f"Error retrieving PaymentIntent {payment_intent_id}: {str(e)}")
            raise
