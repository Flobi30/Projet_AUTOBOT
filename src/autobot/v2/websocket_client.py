"""
Kraken WebSocket Client - Connexion temps réel aux données de marché
"""

import asyncio
import json
import logging
import websocket
import threading
from typing import Dict, Callable, Optional, List
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class TickerData:
    """Données ticker temps réel"""
    symbol: str
    price: float
    bid: float
    ask: float
    volume_24h: float
    timestamp: datetime


class KrakenWebSocket:
    """
    Client WebSocket Kraken pour données temps réel.
    
    Avantages vs REST:
    - Données instantanées (pas de rate limit)
    - Moins de latence
    - Économie sur les appels API
    """
    
    # URLs Kraken
    WS_PUBLIC = "wss://ws.kraken.com"
    WS_PRIVATE = "wss://ws-auth.kraken.com"
    
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.ws: Optional[websocket.WebSocketApp] = None
        self.running = False
        self.thread: Optional[threading.Thread] = None
        
        # CORRECTION: Lock pour thread safety
        self._lock = threading.Lock()
        
        # Callbacks
        self._tickers: Dict[str, List[Callable]] = {}
        self._trades: Dict[str, List[Callable]] = {}
        self._orderbooks: Dict[str, List[Callable]] = {}
        
        # Cache données
        self._last_prices: Dict[str, TickerData] = {}
        self._subscribed_pairs: set = set()
        
        logger.info("📡 KrakenWebSocket initialisé")
    
    def on_message(self, ws, message):
        """Gestion messages reçus"""
        try:
            data = json.loads(message)
            
            # Heartbeat
            if data.get('event') == 'heartbeat':
                return
            
            # System status
            if data.get('event') == 'systemStatus':
                logger.info(f"💚 Kraken WS Status: {data.get('status')}")
                return
            
            # Subscription confirmation
            if data.get('event') == 'subscriptionStatus':
                pair = data.get('pair')
                status = data.get('status')
                logger.info(f"📡 Subscription {pair}: {status}")
                if status == 'subscribed':
                    self._subscribed_pairs.add(pair)
                return
            
            # Channel data (ticker, trade, etc.)
            if isinstance(data, list) and len(data) >= 4:
                channel_id = data[0]
                channel_data = data[1]
                channel_name = data[2]
                pair = data[3]
                
                if 'ticker' in channel_name:
                    self._process_ticker(pair, channel_data)
                elif 'trade' in channel_name:
                    self._process_trade(pair, channel_data)
                    
        except Exception as e:
            logger.error(f"❌ Erreur traitement message WS: {e}")
    
    def _process_ticker(self, pair: str, data: dict):
        """Traite données ticker"""
        try:
            # Format Kraken: { "c": ["price", "lot"], "b": ["bid", "lot"], "a": ["ask", "lot"], "v": ["today", "24h"] }
            price = float(data.get('c', [0])[0])
            bid = float(data.get('b', [0])[0])
            ask = float(data.get('a', [0])[0])
            volume = float(data.get('v', [0, 0])[1])
            
            ticker = TickerData(
                symbol=pair,
                price=price,
                bid=bid,
                ask=ask,
                volume_24h=volume,
                timestamp=datetime.now()
            )
            
            with self._lock:
                self._last_prices[pair] = ticker
                # CORRECTION: Copier la liste pour éviter race condition
                callbacks = list(self._tickers.get(pair, []))
            
            # Notifie les listeners hors lock
            for callback in callbacks:
                try:
                    callback(ticker)
                except Exception as e:
                    logger.error(f"❌ Erreur callback ticker: {e}")
                        
        except Exception as e:
            logger.error(f"❌ Erreur parsing ticker: {e}")
    
    def _process_trade(self, pair: str, data: list):
        """Traite données trades"""
        try:
            if pair in self._trades:
                for callback in self._trades[pair]:
                    try:
                        callback(pair, data)
                    except Exception as e:
                        logger.error(f"❌ Erreur callback trade: {e}")
        except Exception as e:
            logger.error(f"❌ Erreur parsing trade: {e}")
    
    def on_error(self, ws, error):
        """Gestion erreurs"""
        logger.error(f"❌ WebSocket erreur: {error}")
    
    def on_close(self, ws, close_status_code, close_msg):
        """Connexion fermée"""
        logger.warning(f"🔌 WebSocket fermé: {close_status_code} - {close_msg}")
        self.running = False
    
    def on_open(self, ws):
        """Connexion ouverte"""
        logger.info("✅ WebSocket Kraken connecté")
        # Resubscribe aux paires précédentes
        for pair in list(self._subscribed_pairs):
            self.subscribe_ticker(pair)
    
    def connect(self):
        """Démarre connexion WebSocket"""
        if self.running:
            logger.warning("⚠️ WebSocket déjà connecté")
            return
        
        self.running = True
        
        def run():
            self.ws = websocket.WebSocketApp(
                self.WS_PUBLIC,
                on_open=self.on_open,
                on_message=self.on_message,
                on_error=self.on_error,
                on_close=self.on_close
            )
            self.ws.run_forever(ping_interval=30, ping_timeout=10)
        
        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        logger.info("🚀 WebSocket démarré")
    
    def disconnect(self):
        """Ferme connexion"""
        self.running = False
        if self.ws:
            self.ws.close()
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("🔌 WebSocket déconnecté")
    
    def subscribe_ticker(self, pair: str):
        """Souscription aux tickers d'une paire"""
        if not self.running or not self.ws:
            logger.warning("⚠️ WebSocket non connecté")
            return
        
        subscribe_msg = {
            "event": "subscribe",
            "pair": [pair],
            "subscription": {"name": "ticker"}
        }
        
        try:
            self.ws.send(json.dumps(subscribe_msg))
            logger.info(f"📡 Subscription ticker: {pair}")
        except Exception as e:
            logger.error(f"❌ Erreur subscription: {e}")
    
    def unsubscribe_ticker(self, pair: str):
        """Désouscription"""
        if not self.running or not self.ws:
            return
        
        unsubscribe_msg = {
            "event": "unsubscribe",
            "pair": [pair],
            "subscription": {"name": "ticker"}
        }
        
        try:
            self.ws.send(json.dumps(unsubscribe_msg))
            self._subscribed_pairs.discard(pair)
            logger.info(f"📡 Unsubscribed: {pair}")
        except Exception as e:
            logger.error(f"❌ Erreur unsubscribe: {e}")
    
    def add_ticker_listener(self, pair: str, callback: Callable):
        """Ajoute un listener pour les tickers"""
        with self._lock:
            if pair not in self._tickers:
                self._tickers[pair] = []
            self._tickers[pair].append(callback)
        
        self.subscribe_ticker(pair)
        logger.debug(f"👂 Listener ajouté pour {pair}")
    
    def remove_ticker_listener(self, pair: str, callback: Callable):
        """Retire un listener"""
        with self._lock:
            if pair in self._tickers and callback in self._tickers[pair]:
                self._tickers[pair].remove(callback)
                should_unsubscribe = not self._tickers[pair]
                if should_unsubscribe:
                    del self._tickers[pair]
            else:
                should_unsubscribe = False
        
        if should_unsubscribe:
            self.unsubscribe_ticker(pair)
    
    def get_last_price(self, pair: str) -> Optional[TickerData]:
        """Retourne dernier prix connu"""
        return self._last_prices.get(pair)
    
    def is_connected(self) -> bool:
        """Vérifie si connecté"""
        return self.running and self.ws and self.ws.sock and self.ws.sock.connected


# Test rapide
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    ws = KrakenWebSocket()
    
    def on_ticker(data: TickerData):
        print(f"{data.symbol}: €{data.price:,.2f} (Bid: €{data.bid:,.2f}, Ask: €{data.ask:,.2f})")
    
    ws.connect()
    ws.add_ticker_listener("XXBTZEUR", on_ticker)
    
    try:
        input("Appuyez sur Entrée pour arrêter...")
    except:
        pass
    
    ws.disconnect()
