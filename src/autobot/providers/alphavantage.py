import os
import requests

if os.getenv("USE_MOCK") == "1":
    from autobot.data.providers.alphavantage import *  # mode mock
else:
    BASE = "https://www.alphavantage.co/query"
    def get_intraday(symbol: str, interval: str = "1min") -> dict:
        KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "")
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
        KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "")
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
        KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "")
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

    def get_fx_intraday(from_symbol: str, to_symbol: str, interval: str = "5min") -> dict:
        """Get forex intraday data from Alpha Vantage"""
        KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "")
        if not KEY:
            return {"error": "Alpha Vantage API key not configured"}
        
        try:
            r = requests.get(BASE, params={
                "function": "FX_INTRADAY",
                "from_symbol": from_symbol,
                "to_symbol": to_symbol,
                "interval": interval,
                "apikey": KEY
            })
            r.raise_for_status()
            return r.json()
        except Exception as e:
            return {"error": str(e)}

    def get_fx_daily(from_symbol: str, to_symbol: str) -> dict:
        """Get forex daily data from Alpha Vantage"""
        KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "")
        if not KEY:
            return {"error": "Alpha Vantage API key not configured"}
        
        try:
            r = requests.get(BASE, params={
                "function": "FX_DAILY",
                "from_symbol": from_symbol,
                "to_symbol": to_symbol,
                "apikey": KEY
            })
            r.raise_for_status()
            return r.json()
        except Exception as e:
            return {"error": str(e)}

    def get_commodity_data(symbol: str, interval: str = "daily") -> dict:
        """Get commodity data from Alpha Vantage"""
        KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "")
        if not KEY:
            return {"error": "Alpha Vantage API key not configured"}
        
        try:
            r = requests.get(BASE, params={
                "function": "TIME_SERIES_DAILY",
                "symbol": symbol,
                "interval": interval,
                "apikey": KEY
            })
            r.raise_for_status()
            return r.json()
        except Exception as e:
            return {"error": str(e)}

get_alphavantage = get_intraday
get_alphavantage_ts = get_time_series
get_alphavantage_ti = get_technical_indicators
