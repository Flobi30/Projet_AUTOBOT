import os
import requests

if os.getenv("USE_MOCK") == "1":
    from autobot.data.providers.fred import *
else:
    KEY = os.getenv("FRED_API_KEY", "")
    
    def get_series(series_id: str) -> dict:
        if not KEY:
            return {"error": "FRED API key not configured"}
        r = requests.get("https://api.stlouisfed.org/fred/series/observations", params={
            "series_id": series_id,
            "api_key": KEY,
            "file_type": "json"
        })
        r.raise_for_status()
        return r.json()

get_time_series = get_series
get_fred = get_series
