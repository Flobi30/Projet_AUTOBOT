import requests

def get_ccxt_provider(*args, **kwargs):
    """Real CCXT provider for API calls."""
    r = requests.get(*args, **kwargs)
    r.raise_for_status()
    return r.json()

fetch_ticker = get_ccxt_provider
