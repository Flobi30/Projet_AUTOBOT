import requests
import logging

logger = logging.getLogger(__name__)

def get_intraday(symbol, interval="5min", api_key=None):
    """Get real intraday data from AlphaVantage API."""
    if not api_key:
        logger.warning("No AlphaVantage API key provided")
        return {}
    
    url = "https://www.alphavantage.co/query"
    params = {
        "function": "TIME_SERIES_INTRADAY",
        "symbol": symbol,
        "interval": interval,
        "apikey": api_key
    }
    
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.error(f"Error fetching AlphaVantage data: {e}")
        return {}

get_time_series = get_intraday
get_technical_indicators = get_intraday
get_alphavantage = get_intraday
get_alphavantage_ts = get_intraday
get_alphavantage_ti = get_intraday

get_technical_indicators = get_technical_indicators
get_alphavantage = get_intraday
get_alphavantage_ts = get_time_series
get_alphavantage_ti = get_technical_indicators
