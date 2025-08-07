import requests

def get_time_series(*args, **kwargs):
    """Real FRED API implementation."""
    r = requests.get(*args, **kwargs)
    r.raise_for_status()
    return r.json()

get_series = get_time_series
get_fred = get_time_series
