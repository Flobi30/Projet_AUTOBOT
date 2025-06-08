import sys
import os
sys.path.append('/home/ubuntu/Projet_AUTOBOT/src')

try:
    from autobot.services.stripe_service import StripeService
    print('✅ StripeService import successful')
    
    service = StripeService()
    print('✅ StripeService instantiation successful')
    
    try:
        result = service.create_payment_intent(100.0)
        print('❌ Should have failed without API key')
    except ValueError as e:
        print(f'✅ Correctly handles missing API key: {e}')
    
    print('✅ Stripe integration test completed successfully')
    
except Exception as e:
    print(f'❌ Error: {e}')
    import traceback
    traceback.print_exc()
