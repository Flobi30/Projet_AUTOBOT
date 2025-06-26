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

    def get_economic_data(series_id: str, limit: int = 100) -> dict:
        """Get economic data from FRED API"""
        if not KEY:
            return {"error": "FRED API key not configured"}
        try:
            r = requests.get("https://api.stlouisfed.org/fred/series/observations", params={
                "series_id": series_id,
                "api_key": KEY,
                "file_type": "json",
                "limit": limit
            })
            r.raise_for_status()
            return r.json()
        except Exception as e:
            return {"error": str(e)}

    def get_interest_rates(country_code: str = "US") -> dict:
        """Get interest rates for forex fundamental analysis"""
        series_mapping = {
            'US': 'FEDFUNDS',  # Federal Funds Rate
            'EU': 'IRSTCI01EZM156N',  # ECB Interest Rate
            'GB': 'IRSTCI01GBM156N',  # Bank of England Rate
            'JP': 'IRSTCI01JPM156N',  # Bank of Japan Rate
        }
        
        series_id = series_mapping.get(country_code, 'FEDFUNDS')
        return get_economic_data(series_id)

    def get_inflation_data(country_code: str = "US") -> dict:
        """Get inflation data for forex analysis"""
        series_mapping = {
            'US': 'CPIAUCSL',  # US CPI
            'EU': 'CP0000EZ19M086NEST',  # EU CPI
            'GB': 'GBRCPIALLMINMEI',  # UK CPI
            'JP': 'JPNCPIALLMINMEI',  # Japan CPI
        }
        
        series_id = series_mapping.get(country_code, 'CPIAUCSL')
        return get_economic_data(series_id)

    def get_gdp_data(country_code: str = "US") -> dict:
        """Get GDP data for fundamental analysis"""
        series_mapping = {
            'US': 'GDP',
            'EU': 'CLVMNACSCAB1GQEA19',
            'GB': 'CLVMNACSCAB1GQUK',
            'JP': 'CLVMNACSCAB1GQJP',
        }
        
        series_id = series_mapping.get(country_code, 'GDP')
        return get_economic_data(series_id)

get_time_series = get_series
get_fred = get_series
