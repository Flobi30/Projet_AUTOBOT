import requests

def get_intraday(*args, **kwargs):
    """Real CoinGecko API implementation."""
    r = requests.get(*args, **kwargs)
    r.raise_for_status()
    return r.json()

get_prices = get_intraday
get_coingecko = get_intraday
