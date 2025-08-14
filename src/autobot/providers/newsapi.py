import os
import requests
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

class NewsAPIProvider:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('NEWSAPI_KEY', 'demo')
        self.base_url = "https://newsapi.org/v2"
        
    def _fetch(self, endpoint: str, **params) -> Dict[str, Any]:
        """Fetch data from NewsAPI."""
        if self.api_key == "demo":
            return {"articles": []}
        
        url = f"{self.base_url}/{endpoint}"
        headers = {'X-API-Key': self.api_key}
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching from NewsAPI: {e}")
            return {"articles": []}
    
    def get_news(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get news articles for a query."""
        data = self._fetch('everything', q=query, pageSize=limit, sortBy='publishedAt')
        return data.get('articles', [])

def get_time_series(*args, **kwargs):
    """Backward compatibility function."""
    r = requests.get(*args, **kwargs)
    r.raise_for_status()
    return r.json()

get_news = get_time_series
get_newsapi = get_time_series

class NewsDataProvider(NewsAPIProvider):
    """Backward compatibility alias."""
    pass
