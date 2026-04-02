"""
Kraken WebSocket Client - Connexion temps réel aux données de marché
OPTIMISATION: orjson pour parsing JSON 3-10× plus rapide
"""

import asyncio
import orjson  # CORRECTION: orjson 3-10× plus rapide que json
import logging
import time  # CORRECTION Phase 4: Pour heartbeat monitoring
import websocket
import threading
from typing import Dict, Callable, Optional, List
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass(slots=True)  # CORRECTION: __slots__ pour -40% mémoire, +20% vitesse
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
        self.thread: Optional[threading.Thread] = None
        
        # CORRECTION: Event pour thread safety (remplace bool)
        self._running_event = threading.Event()
        
        # CORRECTION: Lock pour thread safety
        self._lock = threading.Lock()
        
        # Callbacks
        self._tickers: Dict[str, List[Callable]] = {}
        self._trades: Dict[str, List[Callable]] = {}
        self._orderbooks: Dict[str, List[Callable]] = {}
        
        # Cache données
        self._last_prices: Dict[str, TickerData] = {}
        self._subscribed_pairs: set = set()

        # CORRECTION Phase 4: Heartbeat et monitoring
        self._last_message_time: Optional[datetime] = None
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._heartbeat_interval = 10  # seconds
        self._stale_threshold = 30  # seconds - prix considéré stalé après
        self._reconnect_backoff = 1  # seconds - backoff exponentiel
        self._max_reconnect_backoff = 60  # seconds

        logger.info("📡 KrakenWebSocket initialisé")
    
    @property
    def running(self) -> bool:
        """Vérifie si le WebSocket tourne"""
        return self._running_event.is_set()
    
    @running.setter
    def running(self, value: bool):
        """Définit l'état du WebSocket (thread-safe)"""
        if value:
            self._running_event.set()
        else:
            self._running_event.clear()
    
    def on_message(self, ws, message):
        """Gestion messages reçus"""
        try:
            # CORRECTION Phase 4: Met à jour timestamp dernier message
            self._last_message_time = datetime.now()

            data = orjson.loads(message)

            # Heartbeat Kraken (different de notre heartbeat monitoring)
            if isinstance(data, dict) and data.get('event') == 'heartbeat':
                return

            # System status
            if isinstance(data, dict) and data.get('event') == 'systemStatus':
                logger.info(f"💚 Kraken WS Status: {data.get('status')}")
                return

            # Subscription confirmation
            if isinstance(data, dict) and data.get('event') == 'subscriptionStatus':
                pair = data.get('pair')
                status = data.get('status')
                logger.info(f"📡 Subscription {pair}: {status}")
                if status == 'subscribed':
                    with self._lock:
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
            with self._lock:
                # CORRECTION: Copier la liste pour éviter race condition
                callbacks = list(self._trades.get(pair, []))
            
            # Notifie les listeners hors lock
            for callback in callbacks:
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
        with self._lock:
            pairs_to_resubscribe = list(self._subscribed_pairs)
        for pair in pairs_to_resubscribe:
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

        # CORRECTION Phase 4: Démarre heartbeat monitoring
        self._start_heartbeat_monitoring()

        logger.info("🚀 WebSocket démarré")

    def _start_heartbeat_monitoring(self):
        """
        CORRECTION Phase 4: Démarre le monitoring heartbeat.
        Détecte connexion silencieuse et gère reconnexion automatique.
        """
        self._last_message_time = datetime.now()
        self._reconnect_backoff = 1

        def heartbeat_loop():
            logger.info("💓 Heartbeat monitoring démarré")

            while self.running:
                try:
                    time.sleep(self._heartbeat_interval)

                    if not self.running:
                        break

                    # Vérifie si prix stalé
                    if self._last_message_time:
                        elapsed = (datetime.now() - self._last_message_time).total_seconds()

                        if elapsed > self._stale_threshold:
                            logger.warning(f"🚨 Prix stalé depuis {elapsed:.0f}s - Reconnexion nécessaire")
                            self._reconnect()
                            continue

                    # Vérifie si toujours connecté
                    if not self.is_connected():
                        logger.warning("🔌 WebSocket déconnecté - Tentative reconnexion...")
                        self._reconnect()

                except Exception as e:
                    logger.exception(f"❌ Erreur heartbeat monitoring: {e}")
                    time.sleep(5)

            logger.info("💓 Heartbeat monitoring arrêté")

        self._heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

    def _reconnect(self):
        """
        CORRECTION Phase 4: Reconnexion automatique avec backoff exponentiel.
        CORRECTION: Arrête heartbeat avant reconnexion pour éviter double thread.
        """
        logger.info(f"🔄 Reconnexion WebSocket (backoff: {self._reconnect_backoff}s)...")

        # CORRECTION: Arrête heartbeat monitoring avant reconnexion
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self.running = False
            self._heartbeat_thread.join(timeout=2)

        # Ferme connexion existante
        try:
            if self.ws:
                self.ws.close()
        except:
            pass

        # Attente backoff
        time.sleep(self._reconnect_backoff)

        # Augmente backoff pour prochaine tentative
        self._reconnect_backoff = min(
            self._reconnect_backoff * 2,
            self._max_reconnect_backoff
        )

        # Redémarre
        try:
            self.connect()
            logger.info("✅ Reconnexion réussie")
            self._reconnect_backoff = 1  # Reset backoff
        except Exception as e:
            logger.error(f"❌ Échec reconnexion: {e}")

    def disconnect(self):
        """Ferme connexion"""
        self.running = False

        # CORRECTION Phase 4: Arrête heartbeat monitoring
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=2)

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
            self.ws.send(orjson.dumps(subscribe_msg).decode('utf-8'))
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
            self.ws.send(orjson.dumps(unsubscribe_msg).decode('utf-8'))
            with self._lock:
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

    def is_data_fresh(self, max_age_seconds: int = 30) -> bool:
        """
        CORRECTION Phase 4: Vérifie si les données sont récentes.

        Args:
            max_age_seconds: Âge maximum acceptable en secondes

        Returns:
            True si données fraîches, False si stalées
        """
        if not self._last_message_time:
            return False

        elapsed = (datetime.now() - self._last_message_time).total_seconds()
        return elapsed < max_age_seconds

    def is_connected(self) -> bool:
        """Vérifie si connecté"""
        return self.running and self.ws and self.ws.sock and self.ws.sock.connected


class WebSocketMultiplexer:
    """
    Multiplexeur WebSocket — 1 connexion pour N paires.
    
    Au lieu de créer 1 KrakenWebSocket par paire (50 connexions),
    on utilise UNE seule connexion et on dispatch les messages
    vers les bonnes instances via des Queues thread-safe.
    
    Usage:
        mux = WebSocketMultiplexer()
        mux.connect()
        mux.subscribe("XXBTZEUR", callback_btc)
        mux.subscribe("XETHZEUR", callback_eth)
        # => 1 seule connexion WS, 2 subscriptions
    """
    
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        # UNE seule connexion WebSocket
        self._ws = KrakenWebSocket(api_key, api_secret)
        self._lock = threading.Lock()
        
        # Dispatch: pair -> [Queue, ...] pour chaque instance
        from queue import Queue
        self._queues: Dict[str, List[Queue]] = {}
        self._callbacks: Dict[str, List[Callable]] = {}
        
        # Thread de dispatch
        self._dispatch_thread: Optional[threading.Thread] = None
        self._running = False
        
        logger.info("🔀 WebSocketMultiplexer initialisé (1 connexion pour N paires)")
    
    def connect(self):
        """Démarre la connexion unique"""
        self._ws.connect()
        self._running = True
        logger.info("🔀 Multiplexer connecté")
    
    def disconnect(self):
        """Ferme la connexion unique"""
        self._running = False
        self._ws.disconnect()
        logger.info("🔀 Multiplexer déconnecté")
    
    def subscribe(self, pair: str, callback: Callable):
        """
        Subscribe une instance à une paire via le multiplexeur.
        Réutilise la connexion existante.
        
        Args:
            pair: Paire Kraken (ex: "XXBTZEUR")
            callback: Fonction appelée avec TickerData
        """
        with self._lock:
            if pair not in self._callbacks:
                self._callbacks[pair] = []
            self._callbacks[pair].append(callback)
        
        # Delegate au KrakenWebSocket sous-jacent
        # add_ticker_listener gère la subscription WS
        self._ws.add_ticker_listener(pair, lambda data: self._dispatch_message(pair, data))
        
        logger.debug(f"🔀 Paire {pair} souscrite via multiplexer ({len(self._callbacks.get(pair, []))} listeners)")
    
    def unsubscribe(self, pair: str, callback: Callable):
        """
        Retire un listener d'une paire.
        Ne ferme la subscription WS que si plus aucun listener.
        """
        with self._lock:
            if pair in self._callbacks and callback in self._callbacks[pair]:
                self._callbacks[pair].remove(callback)
                remaining = len(self._callbacks[pair])
                if remaining == 0:
                    del self._callbacks[pair]
            else:
                remaining = -1
        
        # Si plus aucun listener, unsubscribe de la connexion WS
        if remaining == 0:
            self._ws.unsubscribe_ticker(pair)
            logger.debug(f"🔀 Paire {pair} désabonnée (plus de listeners)")
    
    def _dispatch_message(self, pair: str, data: TickerData):
        """
        Dispatch un message ticker vers tous les callbacks de cette paire.
        Thread-safe: copie la liste des callbacks avant itération.
        
        Args:
            pair: Paire source
            data: Données ticker
        """
        with self._lock:
            callbacks = list(self._callbacks.get(pair, []))
        
        for callback in callbacks:
            try:
                callback(data)
            except Exception as e:
                logger.error(f"❌ Erreur dispatch {pair}: {e}")
    
    def get_last_price(self, pair: str) -> Optional[TickerData]:
        """Proxy vers KrakenWebSocket"""
        return self._ws.get_last_price(pair)
    
    def is_connected(self) -> bool:
        """Proxy vers KrakenWebSocket"""
        return self._ws.is_connected()
    
    def is_data_fresh(self, max_age_seconds: int = 30) -> bool:
        """Proxy vers KrakenWebSocket"""
        return self._ws.is_data_fresh(max_age_seconds)
    
    @property
    def stats(self) -> Dict[str, int]:
        """Statistiques du multiplexer"""
        with self._lock:
            total_listeners = sum(len(cbs) for cbs in self._callbacks.values())
            return {
                'pairs_subscribed': len(self._callbacks),
                'total_listeners': total_listeners,
                'ws_connected': self._ws.is_connected(),
                'connections': 1  # Toujours 1 !
            }


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
