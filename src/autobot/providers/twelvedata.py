import os
import requests

if os.getenv("USE_MOCK") == "1":
    from autobot.data.providers.twelvedata import *  # mode mock
else:
    BASE = "https://api.twelvedata.com"
    def get_intraday(symbol: str, interval: str = "1min") -> dict:
        KEY = os.getenv("TWELVE_DATA_API_KEY", "")
        if not KEY:
            return {"error": "Twelve Data API key not configured"}
        try:
            r = requests.get(f"{BASE}/time_series", params={
                "symbol": symbol,
                "interval": interval,
                "apikey": KEY
            })
            r.raise_for_status()
            data = r.json()
            if "message" in data and "API call frequency" in data["message"]:
                return {"error": f"TwelveData rate limit exceeded: {data['message']}"}
            elif "status" in data and data["status"] == "error":
                return {"error": f"TwelveData error: {data.get('message', 'Unknown error')}"}
            return data
        except Exception as e:
            return {"error": f"TwelveData connection error: {str(e)}"}
    
    def get_eod(symbol: str) -> dict:
        KEY = os.getenv("TWELVE_DATA_API_KEY", "")
        if not KEY:
            return {"error": "Twelve Data API key not configured"}
        r = requests.get(f"{BASE}/eod", params={
            "symbol": symbol,
            "apikey": KEY
        })
        r.raise_for_status()
        return r.json()

    def get_forex_data(symbol: str, interval: str = "5min") -> dict:
        """Get forex data from Twelve Data (e.g., EUR/USD, GBP/USD)"""
        KEY = os.getenv("TWELVE_DATA_API_KEY", "")
        if not KEY:
            return {"error": "Twelve Data API key not configured"}
        
        try:
            r = requests.get(f"{BASE}/time_series", params={
                "symbol": symbol,
                "interval": interval,
                "apikey": KEY
            })
            r.raise_for_status()
            return r.json()
        except Exception as e:
            return {"error": str(e)}

    def get_commodity_data(symbol: str, interval: str = "1day") -> dict:
        """Get commodity data from Twelve Data (e.g., XAU/USD, XAG/USD, WTI/USD)"""
        KEY = os.getenv("TWELVE_DATA_API_KEY", "")
        if not KEY:
            return {"error": "Twelve Data API key not configured"}
        
        try:
            r = requests.get(f"{BASE}/time_series", params={
                "symbol": symbol,
                "interval": interval,
                "apikey": KEY
            })
            r.raise_for_status()
            return r.json()
        except Exception as e:
            return {"error": str(e)}

def get_stock_data(symbol: str = "AAPL") -> dict:
    """Get stock data for connectivity testing"""
    return get_intraday(symbol, "1min")

get_twelvedata = get_intraday
get_time_series = get_intraday
