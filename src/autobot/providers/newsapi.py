import os
import requests

if os.getenv("USE_MOCK") == "1":
    from autobot.data.providers.newsapi import *  # mode mock
else:
    KEY = os.getenv("NEWSAPI_KEY", "")
    
    def get_news(q: str) -> dict:
        if not KEY:
            return {"error": "NewsAPI key not configured"}
        r = requests.get("https://newsapi.org/v2/everything", params={
            "q": q,
            "apiKey": KEY
        })
        r.raise_for_status()
        return r.json()

get_time_series = get_news
get_newsapi = get_news
