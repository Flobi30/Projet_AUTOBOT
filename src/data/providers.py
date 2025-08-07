"""
Module de fournisseurs de données pour AUTOBOT.
Implémente différents fournisseurs pour récupérer des données de marché.
"""
import os
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class AlphaVantageProvider:
    """
    Fournisseur de données AlphaVantage.
    """
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("ALPHAVANTAGE_API_KEY", "demo")
        logger.debug(f"AlphaVantageProvider initialized")
    
    def _fetch(self, symbol: str) -> Dict[str, Any]:
        """Fetch real data from AlphaVantage API."""
        if self.api_key == "demo":
            return {}
        
        import requests
        url = f"https://www.alphavantage.co/query"
        params = {
            "function": "TIME_SERIES_INTRADAY",
            "symbol": symbol,
            "interval": "5min",
            "apikey": self.api_key
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching from AlphaVantage: {e}")
            return {}
    
    def get_time_series(self, symbol: str) -> Dict[str, Any]:
        """
        Récupère les séries temporelles pour un symbole.
        
        Args:
            symbol: Le symbole du titre
            
        Returns:
            Dictionnaire contenant les données
        """
        try:
            return self._fetch(symbol)
        except Exception as e:
            logger.error(f"Error fetching data from AlphaVantage: {e}")
            return {}


class TwelveDataProvider:
    """
    Fournisseur de données TwelveData.
    """
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("TWELVEDATA_API_KEY", "demo")
        logger.debug(f"TwelveDataProvider initialized")
    
    def _fetch(self, symbol: str) -> Dict[str, Any]:
        """Fetch real data from TwelveData API."""
        if self.api_key == "demo":
            return {}
        
        import requests
        url = f"https://api.twelvedata.com/time_series"
        params = {
            "symbol": symbol,
            "interval": "5min",
            "apikey": self.api_key,
            "outputsize": 100
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching from TwelveData: {e}")
            return {}
    
    def get_time_series(self, symbol: str) -> Dict[str, Any]:
        """
        Récupère les séries temporelles pour un symbole.
        
        Args:
            symbol: Le symbole du titre
            
        Returns:
            Dictionnaire contenant les données
        """
        try:
            return self._fetch(symbol)
        except Exception as e:
            logger.error(f"Error fetching data from TwelveData: {e}")
            return {}


class CCXTProvider:
    """
    Fournisseur de données CCXT pour les cryptomonnaies.
    """
    def __init__(self, exchange: str = "binance"):
        self.exchange = exchange
        logger.debug(f"CCXTProvider initialized for {exchange}")
    
    def get_time_series(self, symbol: str) -> Dict[str, Any]:
        """
        Récupère les séries temporelles pour un symbole.
        
        Args:
            symbol: Le symbole de la cryptomonnaie (ex: BTC/USDT)
            
        Returns:
            Dictionnaire contenant les données
        """
        try:
            from autobot.providers.ccxt_provider_enhanced import get_ccxt_provider
            provider = get_ccxt_provider(self.exchange)
            ticker = provider.fetch_ticker(symbol)
            return {
                "last": ticker.get("last", 0.0),
                "bid": ticker.get("bid", 0.0),
                "ask": ticker.get("ask", 0.0),
                "volume": ticker.get("baseVolume", 0.0)
            }
        except Exception as e:
            logger.error(f"Error fetching from CCXT: {e}")
            return {}
