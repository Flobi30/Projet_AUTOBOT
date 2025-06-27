import os
import requests
import urllib.parse
import hashlib
import hmac
import base64
import time

if os.getenv("USE_MOCK") == "1":
    from autobot.data.providers.kraken import *
else:
    API_KEY = os.getenv("KRAKEN_API_KEY", "")
    API_SECRET = os.getenv("KRAKEN_API_SECRET", "")
    BASE_URL = "https://api.kraken.com"
    
    def _get_kraken_signature(urlpath, data):
        postdata = urllib.parse.urlencode(data)
        encoded = (str(data['nonce']) + postdata).encode()
        message = urlpath.encode() + hashlib.sha256(encoded).digest()
        
        mac = hmac.new(base64.b64decode(API_SECRET), message, hashlib.sha512)
        sigdigest = base64.b64encode(mac.digest())
        return sigdigest.decode()
    
    def get_ticker(pair: str = "XBTUSD") -> dict:
        try:
            r = requests.get(f"{BASE_URL}/0/public/Ticker", params={"pair": pair})
            r.raise_for_status()
            data = r.json()
            if "error" in data and data["error"]:
                return {"error": f"Kraken error: {', '.join(data['error'])}"}
            return data
        except Exception as e:
            return {"error": f"Kraken connection error: {str(e)}"}
    
    def get_ohlc(pair: str = "XBTUSD", interval: int = 60) -> dict:
        r = requests.get(f"{BASE_URL}/0/public/OHLC", params={
            "pair": pair,
            "interval": interval
        })
        r.raise_for_status()
        return r.json()
    
    def get_balance() -> dict:
        if not API_KEY or not API_SECRET:
            return {"error": "Kraken API credentials not configured"}
        
        urlpath = "/0/private/Balance"
        data = {"nonce": str(int(1000*time.time()))}
        
        headers = {
            "API-Key": API_KEY,
            "API-Sign": _get_kraken_signature(urlpath, data)
        }
        
        r = requests.post(f"{BASE_URL}{urlpath}", headers=headers, data=data)
        r.raise_for_status()
        return r.json()

get_kraken = get_ticker
