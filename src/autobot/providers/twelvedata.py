import os
import requests

if os.getenv("USE_MOCK") == "1":
    from autobot.data.providers.twelvedata import *  # mode mock
else:
    BASE = "https://api.twelvedata.com"
    KEY = os.getenv("TWELVE_DATA_API_KEY", "")
    
    def get_intraday(symbol: str, interval: str = "1min") -> dict:
        if not KEY:
            return {"error": "Twelve Data API key not configured"}
        r = requests.get(f"{BASE}/time_series", params={
            "symbol": symbol,
            "interval": interval,
            "apikey": KEY
        })
        r.raise_for_status()
        return r.json()
    
    def get_eod(symbol: str) -> dict:
        if not KEY:
            return {"error": "Twelve Data API key not configured"}
        r = requests.get(f"{BASE}/eod", params={
            "symbol": symbol,
            "apikey": KEY
        })
        r.raise_for_status()
        return r.json()

get_twelvedata = get_intraday
get_time_series = get_intraday
