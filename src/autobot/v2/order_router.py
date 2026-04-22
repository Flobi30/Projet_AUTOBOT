"""
Order Router Central — Point unique d'accès API Kraken pour toutes les instances.
MIGRATION P1: Routeur d'ordres prioritaire avec rate limiting

Architecture:
    - Une file d'attente prioritaire (asyncio.PriorityQueue)
    - Priorités: EMERGENCY (SL) = 0, ORDER (buy/sell) = 1, INFO (balance) = 2
    - Protection ban API: toutes les instances passent par le router
    - Intégration RateLimitOptimizer pour contrôle des limites Kraken

Usage:
    from autobot.v2.order_router import OrderRouter, OrderPriority

    router = OrderRouter(api_key, api_secret)
    await router.start()

    # Soumettre un ordre avec priorité
    result = await router.submit({
        'type': 'market',
        'symbol': 'XXBTZEUR',
        'side': 'buy',
        'volume': 0.01
    }, priority=OrderPriority.ORDER)

    await router.stop()
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple, Union

from .order_executor_async import OrderExecutorAsync, OrderResult, OrderSide
from .modules.rate_limit_optimizer import CallPriority
from .speculative_order_cache import SpeculativeOrderCache

logger = logging.getLogger(__name__)

__all__ = [
    "OrderRouter",
    "OrderPriority",
    "OrderRequest",
    "RouterStats",
    "get_order_router",
    "reset_order_router",
    "SpeculativeOrderCache",
]


class OrderPriority(IntEnum):
    """Priorité des ordres (plus petit = plus prioritaire)."""
    EMERGENCY = 0     # Stop-loss, fermeture d'urgence
    ORDER = 1         # Ordres d'achat/vente
    INFO = 2          # Requêtes d'information (balance, status)


@dataclass(order=True)
class OrderRequest:
    """
    Requête d'ordre avec priorité pour la file d'attente.
    
    Note: priority est le premier champ pour le tri automatique
    par asyncio.PriorityQueue (qui utilise heapq, donc ordre croissant).
    """
    priority: int
    timestamp: float = field(compare=False)
    order_type: str = field(compare=False)  # 'market', 'stop_loss', 'cancel', 'balance', etc.
    params: Dict[str, Any] = field(compare=False)
    future: asyncio.Future = field(compare=False)
    instance_id: Optional[str] = field(default=None, compare=False)
    
    @classmethod
    def create(
        cls,
        order_type: str,
        params: Dict[str, Any],
        priority: OrderPriority,
        instance_id: Optional[str] = None,
    ) -> OrderRequest:
        """Crée une nouvelle requête d'ordre."""
        return cls(
            priority=priority.value,
            timestamp=time.monotonic(),
            order_type=order_type,
            params=params,
            future=asyncio.get_running_loop().create_future(),
            instance_id=instance_id,
        )


@dataclass
class RouterStats:
    """Statistiques du routeur."""
    total_submitted: int = 0
    total_executed: int = 0
    total_failed: int = 0
    total_cancelled: int = 0
    emergency_executed: int = 0
    queue_high_watermark: int = 0
    avg_wait_time_ms: float = 0.0
    avg_execution_time_ms: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_submitted": self.total_submitted,
            "total_executed": self.total_executed,
            "total_failed": self.total_failed,
            "total_cancelled": self.total_cancelled,
            "emergency_executed": self.emergency_executed,
            "queue_high_watermark": self.queue_high_watermark,
            "avg_wait_time_ms": round(self.avg_wait_time_ms, 2),
            "avg_execution_time_ms": round(self.avg_execution_time_ms, 2),
        }


class AsyncRateLimiter:
    """
    Version async du RateLimitOptimizer.
    
    Gère les limites d'appels API Kraken avec:
    - Token bucket pour le burst
    - Sliding window pour les appels par seconde
    - Limite d'ordres par minute
    - Backoff exponentiel en cas de rate limit
    """
    
    # Configuration par défaut
    DEFAULT_MAX_CPS = 12          # 15 × 0.8 (marge de sécurité)
    DEFAULT_BURST = 16            # 20 × 0.8
    DEFAULT_ORDERS_PER_MIN = 48   # 60 × 0.8
    
    def __init__(
        self,
        max_calls_per_second: int = DEFAULT_MAX_CPS,
        burst_limit: int = DEFAULT_BURST,
        orders_per_minute: int = DEFAULT_ORDERS_PER_MIN,
    ) -> None:
        self._max_cps = max_calls_per_second
        self._burst_limit = burst_limit
        self._orders_per_min = orders_per_minute
        
        # Locks pour thread-safety
        self._lock = asyncio.Lock()
        
        # Sliding windows (stockage des timestamps)
        self._call_times: List[float] = []
        self._order_times: List[float] = []
        
        # Token bucket
        self._tokens: float = float(burst_limit)
        self._last_refill: float = time.monotonic()
        self._refill_rate: float = float(max_calls_per_second)
        
        # Backoff
        self._backoff_until: float = 0.0
        self._backoff_count: int = 0
        self._backoff_base: float = 1.0
        self._backoff_max: float = 60.0
        self._backoff_mult: float = 2.0
        
        # Stats
        self._total_calls: int = 0
        self._total_orders: int = 0
        self._rate_limits_hit: int = 0
        
        logger.info(
            f"🚦 AsyncRateLimiter initialisé: {max_calls_per_second} calls/s "
            f"(burst {burst_limit}), {orders_per_minute} orders/min"
        )
    
    async def _refill_tokens(self) -> None:
        """Remplit les tokens selon le temps écoulé."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(
            float(self._burst_limit),
            self._tokens + elapsed * self._refill_rate
        )
        self._last_refill = now
    
    async def _purge_old_calls(self) -> None:
        """Supprime les appels de plus d'1 seconde."""
        cutoff = time.monotonic() - 1.0
        self._call_times = [t for t in self._call_times if t >= cutoff]
    
    async def _purge_old_orders(self) -> None:
        """Supprime les ordres de plus d'1 minute."""
        cutoff = time.monotonic() - 60.0
        self._order_times = [t for t in self._order_times if t >= cutoff]
    
    async def can_execute(
        self,
        order_type: str,
        priority: OrderPriority = OrderPriority.INFO,
    ) -> bool:
        """Vérifie si un ordre peut être exécuté maintenant."""
        async with self._lock:
            now = time.monotonic()
            
            # Backoff actif ? Les EMERGENCY passent toujours
            if now < self._backoff_until and priority != OrderPriority.EMERGENCY:
                return False
            
            await self._refill_tokens()
            await self._purge_old_calls()
            
            # EMERGENCY passe même avec 0 tokens (mais respecte CPS)
            if priority != OrderPriority.EMERGENCY:
                # Token bucket check (sauf pour EMERGENCY)
                if self._tokens < 1.0:
                    return False
            
            # Sliding window CPS (tout le monde respecte ça)
            if len(self._call_times) >= self._max_cps:
                return False
            
            # Order-specific limit (EMERGENCY passe aussi)
            if priority != OrderPriority.EMERGENCY and order_type in ("market", "stop_loss", "limit"):
                await self._purge_old_orders()
                if len(self._order_times) >= self._orders_per_min:
                    return False
            
            return True
    
    async def wait_time(self, order_type: str, priority: OrderPriority = OrderPriority.INFO) -> float:
        """Calcule le temps d'attente avant exécution possible."""
        async with self._lock:
            now = time.monotonic()
            
            # Backoff (EMERGENCY ignore)
            if now < self._backoff_until and priority != OrderPriority.EMERGENCY:
                return self._backoff_until - now
            
            await self._refill_tokens()
            await self._purge_old_calls()
            
            waits: List[float] = []
            
            # Token bucket (EMERGENCY ignore)
            if priority != OrderPriority.EMERGENCY and self._tokens < 1.0:
                tokens_needed = 1.0 - self._tokens
                waits.append(tokens_needed / self._refill_rate)
            
            # CPS (tout le monde respecte)
            if len(self._call_times) >= self._max_cps and self._call_times:
                oldest = self._call_times[0]
                waits.append(max(0, (oldest + 1.0) - now))
            
            # Orders
            if order_type in ("market", "stop_loss", "limit"):
                await self._purge_old_orders()
                if len(self._order_times) >= self._orders_per_min and self._order_times:
                    oldest_order = self._order_times[0]
                    waits.append(max(0, (oldest_order + 60.0) - now))
            
            return max(waits) if waits else 0.0
    
    async def record_call(self, order_type: str) -> None:
        """Enregistre un appel API effectué."""
        async with self._lock:
            now = time.monotonic()
            self._call_times.append(now)
            self._tokens = max(0.0, self._tokens - 1.0)
            self._total_calls += 1
            
            if order_type in ("market", "stop_loss", "limit"):
                self._order_times.append(now)
                self._total_orders += 1
    
    async def record_rate_limit(self) -> None:
        """Enregistre un rate limit et active le backoff."""
        async with self._lock:
            self._rate_limits_hit += 1
            self._backoff_count += 1
            
            delay = min(
                self._backoff_base * (self._backoff_mult ** (self._backoff_count - 1)),
                self._backoff_max,
            )
            self._backoff_until = time.monotonic() + delay
            
            logger.warning(
                f"⚠️ Rate limit détecté! Backoff {delay:.1f}s "
                f"(count={self._backoff_count})"
            )
    
    async def record_success(self) -> None:
        """Réduit progressivement le backoff count."""
        async with self._lock:
            if self._backoff_count > 0:
                self._backoff_count = max(0, self._backoff_count - 1)
    
    async def get_status(self) -> Dict[str, Any]:
        """Retourne l'état du rate limiter."""
        async with self._lock:
            await self._refill_tokens()
            await self._purge_old_calls()
            await self._purge_old_orders()
            now = time.monotonic()
            
            return {
                "tokens_available": round(self._tokens, 1),
                "calls_last_second": len(self._call_times),
                "orders_last_minute": len(self._order_times),
                "backoff_active": now < self._backoff_until,
                "backoff_remaining": round(max(0, self._backoff_until - now), 1),
                "backoff_count": self._backoff_count,
                "total_calls": self._total_calls,
                "total_orders": self._total_orders,
                "rate_limits_hit": self._rate_limits_hit,
            }


class OrderRouter:
    """
    Routeur d'ordres central — point unique d'accès API Kraken.
    
    Gère une file d'attente prioritaire avec:
    - EMERGENCY (0): Stop-loss, fermetures d'urgence
    - ORDER (1): Ordres d'achat/vente normaux
    - INFO (2): Requêtes d'information
    
    Protection contre les bans API via AsyncRateLimiter.
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        max_queue_size: int = 10000,
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self._max_queue_size = max_queue_size
        
        # Executor pour les appels API
        self._executor = OrderExecutorAsync(api_key, api_secret)
        
        # Rate limiter
        self._rate_limiter = AsyncRateLimiter()
        
        # File d'attente prioritaire
        self._queue: asyncio.PriorityQueue[OrderRequest] = asyncio.PriorityQueue(
            maxsize=max_queue_size
        )
        
        # Task de processing
        self._processor_task: Optional[asyncio.Task] = None
        self._running = False
        self._inflight_by_client_id: Dict[str, asyncio.Future] = {}
        self._inflight_lock = asyncio.Lock()
        
        # Stats
        self._stats = RouterStats()
        self._stats_lock = asyncio.Lock()
        
        # Callbacks
        self._on_order_executed: Optional[Callable[[OrderRequest, OrderResult], None]] = None
        self._on_rate_limit: Optional[Callable[[], None]] = None

        # P6 — Speculative execution cache (optional)
        self._spec_cache: Optional[SpeculativeOrderCache] = None

        logger.info("🚦 OrderRouter initialisé")
    
    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    
    async def start(self) -> None:
        """Démarre le routeur et le worker de traitement."""
        if self._running:
            return
        
        self._running = True
        self._processor_task = asyncio.create_task(self._process_loop())
        logger.info("🚦 OrderRouter démarré")
    
    async def stop(self) -> None:
        """Arrête le routeur et annule les ordres en attente."""
        if not self._running:
            return
        
        logger.info("🛑 Arrêt OrderRouter...")
        self._running = False
        
        # Annuler le worker
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass
        
        # Annuler les ordres en attente
        cancelled = 0
        while not self._queue.empty():
            try:
                request = self._queue.get_nowait()
                if not request.future.done():
                    request.future.set_exception(asyncio.CancelledError("Router stopped"))
                    cancelled += 1
            except asyncio.QueueEmpty:
                break
        
        await self._executor.close()
        
        async with self._stats_lock:
            self._stats.total_cancelled += cancelled
        
        logger.info(f"🛑 OrderRouter arrêté ({cancelled} ordres annulés)")
    
    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    
    async def submit(
        self,
        order: Dict[str, Any],
        priority: OrderPriority = OrderPriority.ORDER,
        instance_id: Optional[str] = None,
    ) -> OrderResult:
        """
        Soumet un ordre au routeur.
        
        Args:
            order: Dictionnaire décrivant l'ordre
                - 'type': 'market', 'stop_loss', 'cancel', 'balance', etc.
                - autres params selon le type
            priority: Priorité de l'ordre (EMERGENCY, ORDER, INFO)
            instance_id: ID de l'instance qui soumet l'ordre
        
        Returns:
            OrderResult avec le résultat de l'exécution
        """
        if not self._running:
            raise RuntimeError("OrderRouter n'est pas démarré")
        
        order_type = order.get("type", "unknown")
        client_order_id = order.get("client_order_id")

        # Créer la requête
        request = OrderRequest.create(
            order_type=order_type,
            params=order,
            priority=priority,
            instance_id=instance_id,
        )

        if client_order_id:
            async with self._inflight_lock:
                existing = self._inflight_by_client_id.get(client_order_id)
                if existing is not None:
                    try:
                        return await existing
                    except asyncio.CancelledError:
                        return OrderResult(success=False, error="Ordre annulé")
                self._inflight_by_client_id[client_order_id] = request.future
        
        # Mettre à jour les stats
        async with self._stats_lock:
            self._stats.total_submitted += 1
            current_queue_size = self._queue.qsize()
            if current_queue_size > self._stats.queue_high_watermark:
                self._stats.queue_high_watermark = current_queue_size
        
        # Ajouter à la file
        try:
            await asyncio.wait_for(
                self._queue.put(request),
                timeout=5.0
            )
        except asyncio.TimeoutError:
            logger.error("⏱️ Timeout ajout à la file d'attente")
            return OrderResult(
                success=False,
                error="Queue full - timeout ajout"
            )
        
        # Attendre le résultat
        try:
            result = await request.future
            return result
        except asyncio.CancelledError:
            logger.warning(f"🚫 Ordre annulé: {order_type}")
            return OrderResult(success=False, error="Ordre annulé")
        finally:
            if client_order_id:
                self._inflight_by_client_id.pop(client_order_id, None)
    
    async def submit_speculative(
        self,
        symbol: str,
        side: str,
        level_index: int,
        live_price: float,
        priority: OrderPriority = OrderPriority.ORDER,
        instance_id: Optional[str] = None,
        fallback_capital: float = 0.0,
    ) -> OrderResult:
        """
        P6 fast path — submit a market order using a pre-computed template.

        Skips dict construction on cache hit: the order params are built from
        the template in O(1) with a single float division for the volume.

        Falls back to ``submit()`` using ``fallback_capital / live_price`` on
        cache miss.  Returns ``OrderResult(success=False)`` if fallback_capital
        is not provided (safer than sending a wrong volume).

        Parameters
        ----------
        symbol:
            Kraken pair (e.g. ``"XXBTZEUR"``).
        side:
            ``"buy"`` or ``"sell"``.
        level_index:
            Grid level index from the strategy signal.
        live_price:
            Current market price (for BUY volume computation).
        fallback_capital:
            EUR capital to use for volume computation on cache miss.
            Must be > 0 to trigger the fallback; otherwise the call fails safely.
        """
        if self._spec_cache is not None:
            template = self._spec_cache.get(symbol, side, level_index)
            if template is not None:
                # --- cache HIT: build params with one division ---
                if template.has_fixed_volume:
                    volume = template.fixed_volume
                else:
                    volume = template.capital_per_level / live_price

                order = {
                    "type": "market",
                    "symbol": template.symbol,
                    "side": template.side,
                    "volume": volume,
                }
                return await self.submit(order, priority, instance_id)

        # --- cache MISS: compute volume from fallback_capital or fail safely ---
        # W9 fix: never use live_price as volume (price ≠ volume).
        if fallback_capital <= 0 or live_price <= 0:
            logger.warning(
                "🗃️ SpecCache miss sans capital: %s %s lvl=%d — ordre annulé",
                symbol, side, level_index,
            )
            return OrderResult(success=False, error="SpecCache miss: fallback_capital requis")
        volume = fallback_capital / live_price
        order = {
            "type": "market",
            "symbol": symbol,
            "side": side,
            "volume": volume,
        }
        logger.debug(
            "🗃️ SpecCache miss fallback: %s %s lvl=%d vol=%.8f",
            symbol, side, level_index, volume,
        )
        return await self.submit(order, priority, instance_id)

    async def submit_emergency(
        self,
        order: Dict[str, Any],
        instance_id: Optional[str] = None,
    ) -> OrderResult:
        """Soumet un ordre d'urgence (stop-loss)."""
        return await self.submit(order, OrderPriority.EMERGENCY, instance_id)
    
    async def submit_info_request(
        self,
        request_type: str,
        params: Optional[Dict[str, Any]] = None,
        instance_id: Optional[str] = None,
    ) -> Any:
        """Soumet une requête d'information (balance, status, etc.)."""
        order = {
            "type": request_type,
            **(params or {}),
        }
        return await self.submit(order, OrderPriority.INFO, instance_id)
    
    # ------------------------------------------------------------------
    # Processing loop
    # ------------------------------------------------------------------
    
    async def _process_loop(self) -> None:
        """Boucle principale de traitement des ordres."""
        logger.info("🔄 OrderRouter processing loop démarré")
        
        while self._running:
            try:
                # Attendre un ordre
                request = await self._queue.get()
                
                # Calculer le temps d'attente
                wait_time_ms = (time.monotonic() - request.timestamp) * 1000
                
                # Vérifier si la requête n'est pas expirée (timeout 30s)
                if wait_time_ms > 30000:
                    logger.warning(f"⏱️ Ordre expiré après {wait_time_ms:.0f}ms")
                    request.future.set_exception(asyncio.TimeoutError("Request expired"))
                    async with self._stats_lock:
                        self._stats.total_failed += 1
                    self._queue.task_done()
                    continue
                
                # Attendre le rate limiter si nécessaire
                wait_needed = await self._rate_limiter.wait_time(
                    request.order_type, 
                    OrderPriority(request.priority)
                )
                if wait_needed > 0:
                    # Les ordres EMERGENCY passent même avec rate limit
                    if request.priority == OrderPriority.EMERGENCY:
                        logger.warning(f"🚨 Ordre EMERGENCY passe malgré rate limit!")
                    else:
                        logger.debug(f"⏳ Attente rate limit: {wait_needed:.2f}s")
                        await asyncio.sleep(wait_needed)
                
                # Exécuter l'ordre
                start_time = time.monotonic()
                result = await self._execute_request(request)
                execution_time_ms = (time.monotonic() - start_time) * 1000
                
                # Mettre à jour les stats
                async with self._stats_lock:
                    self._stats.total_executed += 1
                    if request.priority == OrderPriority.EMERGENCY:
                        self._stats.emergency_executed += 1
                    
                    # Moyennes mobiles
                    alpha = 0.1  # smoothing factor
                    self._stats.avg_wait_time_ms = (
                        (1 - alpha) * self._stats.avg_wait_time_ms + alpha * wait_time_ms
                    )
                    self._stats.avg_execution_time_ms = (
                        (1 - alpha) * self._stats.avg_execution_time_ms + alpha * execution_time_ms
                    )
                
                # Notifier le résultat
                if not request.future.done():
                    request.future.set_result(result)
                
                # Callback optionnel
                if self._on_order_executed:
                    try:
                        self._on_order_executed(request, result)
                    except Exception as exc:
                        logger.exception(f"❌ Erreur callback: {exc}")
                
                # Marquer la tâche comme faite
                self._queue.task_done()
                
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception(f"❌ Erreur processing loop: {exc}")
                await asyncio.sleep(0.1)
    
    async def _execute_request(self, request: OrderRequest) -> OrderResult:
        """Exécute une requête selon son type."""
        order_type = request.order_type
        params = request.params
        
        # Enregistrer l'appel dans le rate limiter
        await self._rate_limiter.record_call(order_type)
        
        try:
            if order_type == "market":
                return await self._executor.execute_market_order(
                    symbol=params["symbol"],
                    side=OrderSide(params["side"]),
                    volume=params["volume"],
                    userref=params.get("userref"),
                )
            elif order_type == "limit":
                return await self._executor.execute_limit_order(
                    symbol=params["symbol"],
                    side=OrderSide(params["side"]),
                    volume=params["volume"],
                    limit_price=params["price"],
                    post_only=bool(params.get("post_only", False)),
                    userref=params.get("userref"),
                )
            
            elif order_type == "stop_loss":
                return await self._executor.execute_stop_loss_order(
                    symbol=params["symbol"],
                    side=OrderSide(params["side"]),
                    volume=params["volume"],
                    stop_price=params["stop_price"],
                    userref=params.get("userref"),
                )
            
            elif order_type == "cancel":
                success = await self._executor.cancel_order(params["txid"])
                return OrderResult(success=success, txid=params.get("txid"))
            
            elif order_type == "cancel_all":
                success = await self._executor.cancel_all_orders(params.get("userref"))
                return OrderResult(success=success)
            
            elif order_type == "balance":
                balance = await self._executor.get_balance()
                return OrderResult(success=True, raw_response=balance)
            
            elif order_type == "trade_balance":
                trade_balance = await self._executor.get_trade_balance(
                    params.get("asset", "EUR")
                )
                return OrderResult(success=True, raw_response=trade_balance)
            
            elif order_type == "order_status":
                status = await self._executor.get_order_status(params["txid"])
                return OrderResult(
                    success=status is not None,
                    raw_response=status.__dict__ if status else None,
                )
            
            else:
                logger.error(f"❌ Type d'ordre inconnu: {order_type}")
                return OrderResult(success=False, error=f"Unknown order type: {order_type}")
        
        except Exception as exc:
            logger.exception(f"❌ Erreur exécution ordre {order_type}: {exc}")
            
            # Vérifier si c'est un rate limit
            if "rate limit" in str(exc).lower() or "429" in str(exc):
                await self._rate_limiter.record_rate_limit()
                if self._on_rate_limit:
                    self._on_rate_limit()
            
            async with self._stats_lock:
                self._stats.total_failed += 1
            
            return OrderResult(success=False, error=str(exc))
    
    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------
    
    def set_callbacks(
        self,
        on_order_executed: Optional[Callable[[OrderRequest, OrderResult], None]] = None,
        on_rate_limit: Optional[Callable[[], None]] = None,
    ) -> None:
        """Configure les callbacks."""
        self._on_order_executed = on_order_executed
        self._on_rate_limit = on_rate_limit

    def set_speculative_cache(self, cache: SpeculativeOrderCache) -> None:
        """
        Attach a pre-computed order cache for P6 speculative execution.

        Once set, ``submit()`` for ``type='market'`` will attempt an O(1)
        template lookup before falling back to normal construction.  The
        cache is optional — routing behaviour is unchanged when ``None``.
        """
        self._spec_cache = cache
        logger.info("🗃️ OrderRouter: SpeculativeOrderCache attaché (%d templates)", cache.size)
    
    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------
    
    async def get_status(self) -> Dict[str, Any]:
        """Retourne l'état complet du routeur."""
        async with self._stats_lock:
            stats_dict = self._stats.to_dict()
        
        rate_limiter_status = await self._rate_limiter.get_status()
        
        return {
            "running": self._running,
            "queue_size": self._queue.qsize(),
            "max_queue_size": self._max_queue_size,
            "stats": stats_dict,
            "rate_limiter": rate_limiter_status,
        }
    
    def get_queue_size(self) -> int:
        """Retourne la taille actuelle de la file."""
        return self._queue.qsize()
    
    def is_running(self) -> bool:
        """Vérifie si le routeur est actif."""
        return self._running


# ------------------------------------------------------------------------------
# Singleton
# ------------------------------------------------------------------------------

_router_instance: Optional[OrderRouter] = None
_router_lock = asyncio.Lock()


async def get_order_router(
    api_key: Optional[str] = None,
    api_secret: Optional[str] = None,
) -> OrderRouter:
    """Retourne le singleton OrderRouter (crée si nécessaire)."""
    global _router_instance
    async with _router_lock:
        if _router_instance is None:
            _router_instance = OrderRouter(api_key, api_secret)
    return _router_instance


def reset_order_router() -> None:
    """Reset le singleton (pour les tests)."""
    global _router_instance
    _router_instance = None
