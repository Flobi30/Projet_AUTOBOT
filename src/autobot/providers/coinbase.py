import os
import requests
import base64
import hmac
import hashlib
import time

if os.getenv("USE_MOCK") == "1":
    from autobot.data.providers.coinbase import *
else:
    API_KEY = os.getenv("COINBASE_API_KEY", "")
    API_SECRET = os.getenv("COINBASE_API_SECRET", "")
    BASE_URL = "https://api.exchange.coinbase.com"
    
    def _create_signature(timestamp, method, path, body=""):
        message = timestamp + method + path + body
        signature = hmac.new(
            base64.b64decode(API_SECRET),
            message.encode(),
            hashlib.sha256
        ).digest()
        return base64.b64encode(signature).decode()
    
    def get_ticker(product_id: str = "BTC-USD") -> dict:
        r = requests.get(f"{BASE_URL}/products/{product_id}/ticker")
        r.raise_for_status()
        return r.json()
    
    def get_products() -> dict:
        r = requests.get(f"{BASE_URL}/products")
        r.raise_for_status()
        return r.json()
    
    def get_accounts() -> dict:
        if not API_KEY or not API_SECRET:
            return {"error": "Coinbase API credentials not configured"}
        
        timestamp = str(time.time())
        path = "/accounts"
        signature = _create_signature(timestamp, "GET", path)
        
        headers = {
            "CB-ACCESS-KEY": API_KEY,
            "CB-ACCESS-SIGN": signature,
            "CB-ACCESS-TIMESTAMP": timestamp,
            "CB-ACCESS-PASSPHRASE": os.getenv("COINBASE_PASSPHRASE", "")
        }
        
        r = requests.get(f"{BASE_URL}{path}", headers=headers)
        r.raise_for_status()
        return r.json()

get_coinbase = get_ticker
