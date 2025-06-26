import os
import requests

if os.getenv("USE_MOCK") == "1":
    from autobot.data.providers.alphavantage import *  # mode mock
else:
    BASE = "https://www.alphavantage.co/query"
    KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "")
    
    def get_intraday(symbol: str, interval: str = "1min") -> dict:
        if not KEY:
            return {"error": "Alpha Vantage API key not configured"}
        r = requests.get(BASE, params={
            "function": "TIME_SERIES_INTRADAY",
            "symbol": symbol,
            "interval": interval,
            "apikey": KEY
        })
        r.raise_for_status()
        return r.json()
    
    def get_time_series(symbol: str, series_type: str = "DAILY") -> dict:
        if not KEY:
            return {"error": "Alpha Vantage API key not configured"}
        r = requests.get(BASE, params={
            "function": f"TIME_SERIES_{series_type}",
            "symbol": symbol,
            "apikey": KEY
        })
        r.raise_for_status()
        return r.json()
    
    def get_technical_indicators(symbol: str, indicator: str, interval: str = "daily") -> dict:
        if not KEY:
            return {"error": "Alpha Vantage API key not configured"}
        r = requests.get(BASE, params={
            "function": indicator,
            "symbol": symbol,
            "interval": interval,
            "apikey": KEY
        })
        r.raise_for_status()
        return r.json()

get_alphavantage = get_intraday
get_alphavantage_ts = get_time_series
get_alphavantage_ti = get_technical_indicators
