import requests

def get_intraday(*args, **kwargs):
    """Real TwelveData API implementation."""
    r = requests.get(*args, **kwargs)
    r.raise_for_status()
    return r.json()

get_eod = get_intraday
get_twelvedata = get_intraday
