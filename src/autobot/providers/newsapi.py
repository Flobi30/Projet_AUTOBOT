import os
import requests

if os.getenv("USE_MOCK") == "1":
    from autobot.data.providers.newsapi import *  # mode mock
else:
    def get_news(q: str) -> dict:
        KEY = os.getenv("NEWSAPI_KEY", "")
        if not KEY:
            return {"error": "NewsAPI key not configured"}
        try:
            r = requests.get("https://newsapi.org/v2/everything", params={
                "q": q,
                "apiKey": KEY
            })
            r.raise_for_status()
            data = r.json()
            if data.get("status") == "error":
                return {"error": f"NewsAPI error: {data.get('message', 'Unknown error')}"}
            return data
        except Exception as e:
            return {"error": f"NewsAPI connection error: {str(e)}"}

get_time_series = get_news
get_newsapi = get_news
