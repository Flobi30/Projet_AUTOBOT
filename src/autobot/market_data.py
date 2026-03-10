"""
Market Data - Récupération des prix de marché
"""

import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class MarketData:
    """
    Récupère les données de marché depuis Kraken.
    
    Features:
    - Prix actuel (ticker)
    - Order book (depth)
    - Historique des trades
    """
    
    def __init__(self, client):
        """
        Initialise le service de données de marché.
        
        Args:
            client: Client Krakenex API (peut être None si krakenex non installé)
        """
        self._client = client
        if client is None:
            logger.warning("⚠️ MarketData sans client - fonctionnalité limitée")
        else:
            logger.info("📈 MarketData initialisé")
    
    def get_current_price(self, symbol: str = "XXBTZEUR") -> Optional[float]:
        """
        Récupère le prix actuel d'une paire.
        
        CORRECTION: Essentiel pour le stop-loss automatique et
        la recalibration de la grille.
        
        Args:
            symbol: Paire de trading (ex: XXBTZEUR)
            
        Returns:
            Prix actuel ou None en cas d'erreur
        """
        if self._client is None:
            logger.warning("⚠️ Pas de client Kraken - prix simulé à 75000")
            # Prix simulé pour tests sans API
            return 75000.0
        
        try:
            result = self._client.query_public('Ticker', {'pair': symbol})
            
            if result.get('error'):
                logger.error(f"❌ Erreur Kraken Ticker: {result['error']}")
                return None
            
            # Le dernier prix de cloture est dans 'c' [0]
            ticker_data = result.get('result', {}).get(symbol, {})
            if not ticker_data:
                # Essayer avec la clé alternative (Kraken parfois utilise des noms différents)
                for key in result.get('result', {}).keys():
                    if symbol in key or key in symbol:
                        ticker_data = result['result'][key]
                        break
            
            last_price = ticker_data.get('c', [None])[0]
            if last_price:
                return float(last_price)
            
            # Fallback: prix moyen bid/ask
            bid = float(ticker_data.get('b', [0])[0])
            ask = float(ticker_data.get('a', [0])[0])
            if bid > 0 and ask > 0:
                return (bid + ask) / 2
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Erreur récupération prix: {e}")
            return None
    
    def get_order_book(self, symbol: str = "XXBTZEUR", count: int = 10) -> Optional[Dict[str, Any]]:
        """
        Récupère le carnet d'ordres (order book).
        
        Args:
            symbol: Paire de trading
            count: Nombre de niveaux à récupérer
            
        Returns:
            Dict avec 'bids' et 'asks' ou None
        """
        try:
            result = self._client.query_public('Depth', {'pair': symbol, 'count': count})
            
            if result.get('error'):
                logger.error(f"❌ Erreur Kraken Depth: {result['error']}")
                return None
            
            return result.get('result', {}).get(symbol)
            
        except Exception as e:
            logger.error(f"❌ Erreur récupération order book: {e}")
            return None
