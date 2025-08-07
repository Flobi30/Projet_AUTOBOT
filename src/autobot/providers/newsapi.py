import requests

def get_time_series(*args, **kwargs):
    """Real NewsAPI implementation."""
    r = requests.get(*args, **kwargs)
    r.raise_for_status()
    return r.json()

get_news = get_time_series
get_newsapi = get_time_series
