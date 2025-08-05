"""
Real Stripe Service for AUTOBOT payment processing
"""

import stripe
import logging
from typing import Dict, Any, Optional
from ..autobot_security.auth.user_manager import UserManager

logger = logging.getLogger(__name__)

class StripeService:
    """Real Stripe service for payment processing"""
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize Stripe service with API key"""
        if api_key:
            stripe.api_key = api_key
        else:
            logger.warning("No Stripe API key provided")
    
    def create_checkout_session(self, amount: int, currency: str = "eur", 
                              success_url: str = None, cancel_url: str = None) -> Dict[str, Any]:
        """Create real Stripe checkout session"""
        try:
            session = stripe.checkout.Session.create(
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
                success_url=success_url or 'https://stripe-autobot.fr/capital?success=true',
                cancel_url=cancel_url or 'https://stripe-autobot.fr/capital?canceled=true',
            )
            
            return {
                "sessionId": session.id,
                "url": session.url
            }
        except Exception as e:
            logger.error(f"Error creating Stripe checkout session: {e}")
            raise
    
    def create_payout(self, amount: int, currency: str = "eur", 
                     destination: str = None) -> Dict[str, Any]:
        """Create Stripe payout for withdrawals"""
        try:
            payout = stripe.Payout.create(
                amount=amount,
                currency=currency,
                destination=destination,
                method='instant'
            )
            
            return {
                "success": True,
                "payout_id": payout.id,
                "status": payout.status
            }
        except Exception as e:
            logger.error(f"Error creating Stripe payout: {e}")
            raise

def get_user_stripe_service(user_id: str) -> Optional[StripeService]:
    """Get StripeService instance for authenticated user"""
    try:
        user_manager = UserManager()
        user = user_manager.get_user(user_id)
        
        if user and 'stripe_api_key' in user:
            return StripeService(api_key=user['stripe_api_key'])
        
        logger.warning(f"No Stripe API key found for user {user_id}")
        return None
    except Exception as e:
        logger.error(f"Error getting user Stripe service: {e}")
        return None
