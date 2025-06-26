import os
import requests

if os.getenv("USE_MOCK") == "1":
    from autobot.data.providers.shopify import *  # mode mock
else:
    KEY = os.getenv("SHOPIFY_API_KEY", "")
    SHOP = os.getenv("SHOPIFY_SHOP_NAME", "")
    
    def get_orders() -> dict:
        if not KEY or not SHOP:
            return {"error": "Shopify API key or shop name not configured"}
        r = requests.get(f"https://{SHOP}.myshopify.com/admin/api/2025-01/orders.json", headers={
            "X-Shopify-Access-Token": KEY
        })
        r.raise_for_status()
        return r.json()
    
    def get_customers() -> dict:
        if not KEY or not SHOP:
            return {"error": "Shopify API key or shop name not configured"}
        r = requests.get(f"https://{SHOP}.myshopify.com/admin/api/2025-01/customers.json", headers={
            "X-Shopify-Access-Token": KEY
        })
        r.raise_for_status()
        return r.json()

get_shopify_orders = get_orders
get_shopify_customers = get_customers
get_shopify = get_orders
get_time_series = get_orders
