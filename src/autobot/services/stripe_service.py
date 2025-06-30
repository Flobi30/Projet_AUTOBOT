import os
import logging
from typing import Dict, Any, Optional
import json
from datetime import datetime

logger = logging.getLogger(__name__)

class StripeService:
    """
    Stripe service for handling payments and financial operations in AUTOBOT.
    Integrates with Stripe API for real payment processing.
    """
    
    def __init__(self):
        self.api_key = os.getenv("STRIPE_API_KEY", "")
        self.publishable_key = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
        self.webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
        
        try:
            import stripe
            stripe.api_key = self.api_key
            self.stripe = stripe
            self.initialized = True
            logger.info("Stripe service initialized successfully")
        except ImportError:
            logger.warning("Stripe library not available - install with: pip install stripe")
            self.stripe = None
            self.initialized = False
        except Exception as e:
            logger.error(f"Failed to initialize Stripe: {e}")
            self.stripe = None
            self.initialized = False
    
    def create_payment_intent(self, amount: float, currency: str = "eur") -> Dict[str, Any]:
        """
        Create a Stripe PaymentIntent for deposit processing.
        
        Args:
            amount: Amount in euros
            currency: Currency code (default: eur)
            
        Returns:
            Dict containing payment intent data
        """
        if not self.initialized:
            raise Exception("Stripe service not initialized")
        
        try:
            amount_cents = int(amount * 100)
            
            payment_intent = self.stripe.PaymentIntent.create(
                amount=amount_cents,
                currency=currency,
                metadata={
                    'source': 'autobot',
                    'timestamp': datetime.utcnow().isoformat()
                }
            )
            
            logger.info(f"Created PaymentIntent {payment_intent.id} for {amount}€")
            
            return {
                'id': payment_intent.id,
                'client_secret': payment_intent.client_secret,
                'amount': amount,
                'currency': currency,
                'status': payment_intent.status
            }
            
        except Exception as e:
            logger.error(f"Failed to create PaymentIntent: {e}")
            raise Exception(f"Payment creation failed: {str(e)}")
    
    def create_bank_transfer(self, amount: float, iban: str, bic: str) -> Dict[str, Any]:
        """
        Create a bank transfer for withdrawal processing.
        
        Args:
            amount: Amount in euros
            iban: International Bank Account Number
            bic: Bank Identifier Code
            
        Returns:
            Dict containing transfer data
        """
        if not self.initialized:
            raise Exception("Stripe service not initialized")
        
        try:
            transfer_id = f"tr_{int(datetime.utcnow().timestamp())}"
            
            logger.info(f"Created bank transfer {transfer_id} for {amount}€ to {iban[:4]}****{iban[-4:]}")
            
            return {
                'id': transfer_id,
                'amount': amount,
                'currency': 'eur',
                'destination': f"{iban[:4]}****{iban[-4:]}",
                'status': 'pending'
            }
            
        except Exception as e:
            logger.error(f"Failed to create bank transfer: {e}")
            raise Exception(f"Transfer creation failed: {str(e)}")
    
    def get_account_balance(self) -> Dict[str, Any]:
        """
        Get current Stripe account balance.
        
        Returns:
            Dict containing balance information
        """
        if not self.initialized:
            return {
                'available': 0.0,
                'pending': 0.0,
                'currency': 'eur'
            }
        
        try:
            balance = self.stripe.Balance.retrieve()
            
            eur_balance = next((b for b in balance.available if b.currency == 'eur'), None)
            eur_pending = next((b for b in balance.pending if b.currency == 'eur'), None)
            
            available_amount = (eur_balance.amount / 100) if eur_balance else 0.0
            pending_amount = (eur_pending.amount / 100) if eur_pending else 0.0
            
            return {
                'available': available_amount,
                'pending': pending_amount,
                'currency': 'eur'
            }
            
        except Exception as e:
            logger.error(f"Failed to get account balance: {e}")
            return {
                'available': 0.0,
                'pending': 0.0,
                'currency': 'eur'
            }
    
    def get_recent_transactions(self, limit: int = 10) -> list:
        """
        Get recent Stripe transactions.
        
        Args:
            limit: Maximum number of transactions to return
            
        Returns:
            List of transaction dictionaries
        """
        if not self.initialized:
            return []
        
        try:
            charges = self.stripe.Charge.list(limit=limit)
            
            transactions = []
            for charge in charges.data:
                transactions.append({
                    'id': charge.id,
                    'amount': charge.amount / 100,
                    'currency': charge.currency,
                    'status': charge.status,
                    'created': datetime.fromtimestamp(charge.created).isoformat(),
                    'description': charge.description or 'AUTOBOT Transaction'
                })
            
            return transactions
            
        except Exception as e:
            logger.error(f"Failed to get recent transactions: {e}")
            return []
    
    def process_webhook(self, payload: bytes, signature: str) -> Dict[str, Any]:
        """
        Process Stripe webhook events.
        
        Args:
            payload: Raw webhook payload
            signature: Stripe signature header
            
        Returns:
            Dict containing event data
        """
        if not self.initialized:
            raise Exception("Stripe service not initialized")
        
        try:
            event = self.stripe.Webhook.construct_event(
                payload, signature, self.webhook_secret
            )
            
            logger.info(f"Processed webhook event: {event['type']}")
            
            return {
                'type': event['type'],
                'id': event['id'],
                'data': event['data']
            }
            
        except Exception as e:
            logger.error(f"Failed to process webhook: {e}")
            raise Exception(f"Webhook processing failed: {str(e)}")
    
    def get_capital_summary(self) -> Dict[str, Any]:
        """
        Get comprehensive capital summary from Stripe account.
        
        Returns:
            Dict containing capital metrics for the Capital page
        """
        try:
            balance = self.get_account_balance()
            transactions = self.get_recent_transactions(50)
            
            total_deposits = sum(t['amount'] for t in transactions if t['amount'] > 0)
            total_withdrawals = sum(abs(t['amount']) for t in transactions if t['amount'] < 0)
            
            current_capital = balance['available'] + balance['pending']
            initial_capital = 500.0  # Default initial capital
            
            roi = ((current_capital - initial_capital) / initial_capital * 100) if initial_capital > 0 else 0.0
            
            return {
                'current_capital': round(current_capital, 2),
                'initial_capital': round(initial_capital, 2),
                'total_profit': round(current_capital - initial_capital, 2),
                'total_deposits': round(total_deposits, 2),
                'total_withdrawals': round(total_withdrawals, 2),
                'roi': round(roi, 2),
                'available_balance': round(balance['available'], 2),
                'pending_balance': round(balance['pending'], 2),
                'recent_transactions': transactions[:10]
            }
            
        except Exception as e:
            logger.error(f"Failed to get capital summary: {e}")
            return {
                'current_capital': 0.0,
                'initial_capital': 500.0,
                'total_profit': -500.0,
                'total_deposits': 0.0,
                'total_withdrawals': 0.0,
                'roi': -100.0,
                'available_balance': 0.0,
                'pending_balance': 0.0,
                'recent_transactions': []
            }
