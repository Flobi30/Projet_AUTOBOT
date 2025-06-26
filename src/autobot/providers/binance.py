import os
import requests
import hmac
import hashlib
import time

if os.getenv("USE_MOCK") == "1":
    from autobot.data.providers.binance import *
else:
    API_KEY = os.getenv("BINANCE_API_KEY", "")
    API_SECRET = os.getenv("BINANCE_API_SECRET", "")
    BASE_URL = "https://api.binance.com"
    
    def _sign_request(params):
        query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
        signature = hmac.new(API_SECRET.encode(), query_string.encode(), hashlib.sha256).hexdigest()
        return signature
    
    def get_ticker(symbol: str = "BTCUSDT") -> dict:
        r = requests.get(f"{BASE_URL}/api/v3/ticker/24hr", params={"symbol": symbol})
        r.raise_for_status()
        return r.json()
    
    def get_klines(symbol: str = "BTCUSDT", interval: str = "1h", limit: int = 100) -> dict:
        r = requests.get(f"{BASE_URL}/api/v3/klines", params={
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        })
        r.raise_for_status()
        return r.json()
    
    def get_account_info() -> dict:
        if not API_KEY or not API_SECRET:
            return {"error": "Binance API credentials not configured"}
        
        timestamp = int(time.time() * 1000)
        params = {"timestamp": timestamp}
        signature = _sign_request(params)
        params["signature"] = signature
        
        headers = {"X-MBX-APIKEY": API_KEY}
        r = requests.get(f"{BASE_URL}/api/v3/account", params=params, headers=headers)
        r.raise_for_status()
        return r.json()

get_binance = get_ticker
