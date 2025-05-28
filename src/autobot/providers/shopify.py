import os
if os.getenv("USE_MOCK") == "1":
    from autobot.data.providers.shopify import *  # mode mock
else:
    import requests
    
    def get_shopify_orders(*args, **kwargs):
        """Stub auto-généré pour tests."""
        r = requests.get(*args, **kwargs)
        r.raise_for_status()
        return r.json()
    
    get_orders = get_shopify_orders
    get_shopify = get_shopify_orders

get_shopify_orders = get_orders