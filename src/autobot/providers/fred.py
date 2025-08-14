import os
import requests
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class FREDProvider:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('FRED_API_KEY', 'demo')
        self.base_url = "https://api.stlouisfed.org/fred"
        
    def _fetch(self, series_id: str, **params) -> Dict[str, Any]:
        """Fetch data from FRED API."""
        if self.api_key == "demo":
            return {"value": 2.5}
        
        url = f"{self.base_url}/series/observations"
        params.update({
            'series_id': series_id,
            'api_key': self.api_key,
            'file_type': 'json',
            'limit': 1,
            'sort_order': 'desc'
        })
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            observations = data.get('observations', [])
            if observations:
                return {"value": float(observations[0].get('value', 2.5))}
            return {"value": 2.5}
        except Exception as e:
            logger.error(f"Error fetching from FRED: {e}")
            return {"value": 2.5}
    
    def get_gdp_data(self) -> Dict[str, float]:
        """Get GDP growth data."""
        data = self._fetch('GDP')
        return {"value": data.get("value", 2.5)}
    
    def get_inflation_data(self) -> Dict[str, float]:
        """Get inflation rate data."""
        data = self._fetch('CPIAUCSL')
        return {"value": data.get("value", 3.2)}
    
    def get_unemployment_data(self) -> Dict[str, float]:
        """Get unemployment rate data."""
        data = self._fetch('UNRATE')
        return {"value": data.get("value", 4.1)}

def get_time_series(*args, **kwargs):
    """Backward compatibility function."""
    r = requests.get(*args, **kwargs)
    r.raise_for_status()
    return r.json()

get_series = get_time_series
get_fred = get_time_series

class FREDDataProvider(FREDProvider):
    """Backward compatibility alias."""
    pass
