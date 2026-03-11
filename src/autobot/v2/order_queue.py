"""
Order Queue - File d'attente globale pour ordres Kraken
Sérialise les ordres pour éviter les race conditions et respecter les rate limits
"""

import logging
import threading
import time
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass
from datetime import datetime
from queue import Queue, Empty
from enum import Enum

logger = logging.getLogger(__name__)


class OrderType(Enum):
    BUY = "buy"
    SELL = "sell"
    STOP_LOSS = "stop_loss"
    CANCEL = "cancel"


@dataclass
class OrderRequest:
    """Représente une requête d'ordre"""
    order_type: OrderType
    symbol: str
    volume: float
    price: Optional[float] = None  # Pour limit orders
    stop_price: Optional[float] = None  # Pour stop-loss
    callback: Optional[Callable] = None  # Callback avec résultat
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class TokenBucket:
    """
    Token bucket pour rate limiting
    Permet des bursts contrôlés tout en maintenant une moyenne
    """
    
    def __init__(self, tokens_per_second: float, max_tokens: float):
        self.tokens_per_second = tokens_per_second
        self.max_tokens = max_tokens
        self.tokens = max_tokens
        self.last_update = time.time()
        self._lock = threading.Lock()
        
    def consume(self, tokens: float = 1.0) -> bool:
        """
        Consomme des tokens. Retourne True si assez de tokens, False sinon.
        """
        with self._lock:
            now = time.time()
            elapsed = now - self.last_update
            self.tokens = min(self.max_tokens, self.tokens + elapsed * self.tokens_per_second)
            self.last_update = now
            
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False
    
    def wait_time(self, tokens: float = 1.0) -> float:
        """Calcule le temps d'attente nécessaire pour avoir assez de tokens"""
        with self._lock:
            if self.tokens >= tokens:
                return 0.0
            needed = tokens - self.tokens
            return needed / self.tokens_per_second
    
    def get_tokens_snapshot(self) -> float:
        """
        CORRECTION: Retourne une snapshot thread-safe du nombre de tokens.
        À utiliser pour les stats uniquement, pas pour la logique métier.
        """
        with self._lock:
            return self.tokens


class OrderQueue:
    """
    File d'attente globale pour ordres Kraken
    - Sérialise les ordres (un seul à la fois)
 - Respecte les rate limits via token bucket
    - Gère les priorités (emergency > normal)
    """
    
    def __init__(self, order_executor, max_rate: float = 1.0, max_burst: float = 3.0):
        """
        Args:
            order_executor: Instance d'OrderExecutor
            max_rate: Nombre max d'ordres par seconde (moyenne)
            max_burst: Nombre max d'ordres en burst
        """
        self.order_executor = order_executor
        self.token_bucket = TokenBucket(max_rate, max_burst)
        self.queue = Queue()
        self.emergency_queue = Queue()  # Priorité haute
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._stats = {
            'processed': 0,
            'failed': 0,
            'queued': 0
        }
        
    def start(self):
        """Démarre le processeur de file d'attente"""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(target=self._process_loop, daemon=True)
            self._thread.start()
            logger.info("✅ OrderQueue démarrée")
            
    def stop(self):
        """Arrête la file d'attente"""
        with self._lock:
            self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            logger.info("🛑 OrderQueue arrêtée")
            
    def submit(self, order: OrderRequest, emergency: bool = False) -> bool:
        """
        Soumet un ordre à la file d'attente
        
        Args:
            order: La requête d'ordre
            emergency: Si True, priorité haute (devant la file)
            
        Returns:
            True si soumis avec succès
        """
        if emergency:
            self.emergency_queue.put(order)
        else:
            self.queue.put(order)
        
        with self._lock:
            self._stats['queued'] += 1
            
        logger.debug(f"📥 Ordre {order.order_type.value} en file d'attente (emergency={emergency})")
        return True
        
    def _process_loop(self):
        """Boucle principale de traitement"""
        while self._running:
            try:
                # Priorité aux ordres emergency
                try:
                    order = self.emergency_queue.get(timeout=0.1)
                except Empty:
                    try:
                        order = self.queue.get(timeout=0.1)
                    except Empty:
                        continue
                
                # Attendre d'avoir assez de tokens
                wait_time = self.token_bucket.wait_time(1.0)
                if wait_time > 0:
                    time.sleep(wait_time)
                
                # Exécuter l'ordre
                self._execute_order(order)
                
            except Exception as e:
                logger.exception(f"❌ Erreur traitement ordre: {e}")
                time.sleep(0.1)
                
    def _execute_order(self, order: OrderRequest):
        """Exécute un ordre via OrderExecutor"""
        try:
            from .order_executor import OrderSide
            
            result = None
            
            if order.order_type == OrderType.BUY:
                result = self.order_executor.execute_market_order(
                    symbol=order.symbol,
                    side=OrderSide.BUY,
                    volume=order.volume
                )
            elif order.order_type == OrderType.SELL:
                result = self.order_executor.execute_market_order(
                    symbol=order.symbol,
                    side=OrderSide.SELL,
                    volume=order.volume
                )
            elif order.order_type == OrderType.STOP_LOSS:
                result = self.order_executor.execute_stop_loss_order(
                    symbol=order.symbol,
                    side=OrderSide.SELL,
                    volume=order.volume,
                    stop_price=order.stop_price
                )
            elif order.order_type == OrderType.CANCEL:
                result = self.order_executor.cancel_order(order.symbol)  # symbol = txid ici
            
            # Mettre à jour stats
            with self._lock:
                if result and result.success:
                    self._stats['processed'] += 1
                else:
                    self._stats['failed'] += 1
            
            # Appeler le callback si présent
            if order.callback:
                try:
                    order.callback(result)
                except Exception as e:
                    logger.exception(f"❌ Erreur callback ordre: {e}")
                    
        except Exception as e:
            logger.exception(f"❌ Erreur exécution ordre: {e}")
            with self._lock:
                self._stats['failed'] += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques de la file"""
        with self._lock:
            return {
                'processed': self._stats['processed'],
                'failed': self._stats['failed'],
                'queued': self.queue.qsize() + self.emergency_queue.qsize(),
                'tokens_available': self.token_bucket.get_tokens_snapshot()  # CORRECTION: thread-safe
            }


# Singleton global
_order_queue_instance: Optional[OrderQueue] = None
_order_queue_lock = threading.Lock()


def get_order_queue(order_executor=None, max_rate: float = 1.0) -> OrderQueue:
    """Retourne l'instance singleton de OrderQueue"""
    global _order_queue_instance
    
    with _order_queue_lock:
        if _order_queue_instance is None and order_executor is not None:
            _order_queue_instance = OrderQueue(order_executor, max_rate)
        return _order_queue_instance
