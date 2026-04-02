"""
Rate Limit Optimizer — Optimiseur de rate limiting pour l'API Kraken.

Kraken impose des limites strictes sur les appels API :
  - REST API : ~15 appels/seconde (dépend du tier)
  - Matching Engine : 60 ordres/minute par pair
  - Penalty pour excès : ban temporaire (15 min - 1h)

Ce module :
  1. Suit les appels en temps réel avec un sliding window
  2. Planifie les requêtes pour rester sous les limites
  3. Priorise les ordres critiques (stop-loss > DCA > info)
  4. Batch les requêtes quand possible (batch cancel, etc.)
  5. Détecte et gère le rate-limit (429) avec backoff exponentiel

Thread-safe (RLock), O(1) amorti par appel.

Usage:
    from autobot.v2.modules.rate_limit_optimizer import RateLimitOptimizer

    limiter = RateLimitOptimizer(max_calls_per_second=15)

    # Avant chaque appel API
    if limiter.can_call("order"):
        limiter.record_call("order")
        # ... faire l'appel
    else:
        delay = limiter.wait_time("order")
        # ... attendre delay secondes

    # En cas de 429
    limiter.record_rate_limit()

    status = limiter.get_status()
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from enum import IntEnum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class CallPriority(IntEnum):
    """Priorité des appels API (plus petit = plus prioritaire)."""
    EMERGENCY = 0     # Stop-loss, emergency stop
    ORDER = 1         # Placement/annulation d'ordres
    POSITION = 2      # Info positions, balance
    MARKET_DATA = 3   # OHLC, ticker, orderbook
    INFO = 4          # Status, système
    BACKGROUND = 5    # Logs, historique, non-urgent


# Kraken rate limit configuration par défaut
KRAKEN_LIMITS = {
    "rest_calls_per_second": 15,
    "rest_burst": 20,           # burst max avant throttle
    "orders_per_minute": 60,    # matching engine limit
    "cancel_per_minute": 60,
    "backoff_base_seconds": 1.0,
    "backoff_max_seconds": 60.0,
    "backoff_multiplier": 2.0,
}


class RateLimitOptimizer:
    """
    Optimiseur de rate limiting pour l'API Kraken.

    Utilise un token bucket + sliding window pour gérer les limites
    d'appels. Priorise les appels critiques et applique un backoff
    exponentiel en cas de rate limit.

    Args:
        max_calls_per_second: Limite d'appels REST par seconde. Défaut 15.
        burst_limit: Nombre max d'appels en burst. Défaut 20.
        orders_per_minute: Limite d'ordres par minute. Défaut 60.
        safety_margin: Marge de sécurité (0-1). Défaut 0.8 (80% de la limite).
    """

    def __init__(
        self,
        max_calls_per_second: int = 15,
        burst_limit: int = 20,
        orders_per_minute: int = 60,
        safety_margin: float = 0.8,
    ) -> None:
        if max_calls_per_second < 1:
            raise ValueError(f"max_calls_per_second doit être >= 1, reçu {max_calls_per_second}")
        if safety_margin <= 0 or safety_margin > 1:
            raise ValueError(f"safety_margin doit être dans (0, 1], reçu {safety_margin}")

        self._lock = threading.RLock()

        # Configuration (avec marge de sécurité)
        self._max_cps = int(max_calls_per_second * safety_margin)
        self._burst_limit = int(burst_limit * safety_margin)
        self._orders_per_min = int(orders_per_minute * safety_margin)
        self._safety_margin = safety_margin

        # Sliding windows
        self._call_times: deque = deque()        # timestamps de tous les appels
        self._order_times: deque = deque()       # timestamps des ordres spécifiquement

        # Token bucket pour le burst
        self._tokens: float = float(self._burst_limit)
        self._last_refill: float = time.time()
        self._refill_rate: float = float(self._max_cps)  # tokens/sec

        # Backoff exponentiel
        self._backoff_until: float = 0.0
        self._backoff_count: int = 0
        self._backoff_base = KRAKEN_LIMITS["backoff_base_seconds"]
        self._backoff_max = KRAKEN_LIMITS["backoff_max_seconds"]
        self._backoff_mult = KRAKEN_LIMITS["backoff_multiplier"]

        # Statistiques
        self._total_calls: int = 0
        self._total_orders: int = 0
        self._blocked_calls: int = 0
        self._rate_limits_hit: int = 0
        self._total_wait_time: float = 0.0

        # Queue de priorité simple
        self._priority_queue: List[Tuple[float, CallPriority, str]] = []

        logger.info(
            f"RateLimitOptimizer initialisé: {self._max_cps} calls/s "
            f"(burst {self._burst_limit}), {self._orders_per_min} orders/min, "
            f"safety={safety_margin*100:.0f}%"
        )

    # ------------------------------------------------------------------
    # Token bucket
    # ------------------------------------------------------------------

    def _refill_tokens(self) -> None:
        """Remplit les tokens selon le temps écoulé."""
        now = time.time()
        elapsed = now - self._last_refill
        self._tokens = min(
            float(self._burst_limit),
            self._tokens + elapsed * self._refill_rate
        )
        self._last_refill = now

    # ------------------------------------------------------------------
    # Sliding window management
    # ------------------------------------------------------------------

    def _purge_old_calls(self) -> None:
        """Supprime les appels de plus d'1 seconde (pour CPS)."""
        cutoff = time.time() - 1.0
        while self._call_times and self._call_times[0] < cutoff:
            self._call_times.popleft()

    def _purge_old_orders(self) -> None:
        """Supprime les ordres de plus d'1 minute."""
        cutoff = time.time() - 60.0
        while self._order_times and self._order_times[0] < cutoff:
            self._order_times.popleft()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def can_call(self, call_type: str = "info", priority: CallPriority = CallPriority.INFO) -> bool:
        """
        Vérifie si un appel API peut être fait maintenant.

        Args:
            call_type: Type d'appel ("order", "cancel", "info", "market_data").
            priority: Priorité de l'appel.

        Returns:
            True si l'appel est autorisé.
        """
        with self._lock:
            now = time.time()

            # Backoff actif ?
            if now < self._backoff_until:
                # Exception : les appels EMERGENCY passent toujours
                if priority > CallPriority.EMERGENCY:
                    return False

            self._refill_tokens()
            self._purge_old_calls()

            # Token bucket check
            if self._tokens < 1.0:
                return False

            # Sliding window CPS check
            if len(self._call_times) >= self._max_cps:
                return False

            # Order-specific limit
            if call_type in ("order", "cancel"):
                self._purge_old_orders()
                if len(self._order_times) >= self._orders_per_min:
                    return False

            return True

    def record_call(self, call_type: str = "info") -> None:
        """
        Enregistre un appel API effectué.

        Args:
            call_type: Type d'appel.
        """
        with self._lock:
            now = time.time()
            self._call_times.append(now)
            self._tokens = max(0.0, self._tokens - 1.0)
            self._total_calls += 1

            if call_type in ("order", "cancel"):
                self._order_times.append(now)
                self._total_orders += 1

    def wait_time(self, call_type: str = "info") -> float:
        """
        Calcule le temps d'attente avant le prochain appel autorisé.

        Returns:
            Temps en secondes (0 si appel immédiat possible).
        """
        with self._lock:
            now = time.time()

            # Backoff ?
            if now < self._backoff_until:
                return self._backoff_until - now

            self._refill_tokens()
            self._purge_old_calls()

            waits = []

            # Token bucket
            if self._tokens < 1.0:
                tokens_needed = 1.0 - self._tokens
                waits.append(tokens_needed / self._refill_rate)

            # CPS
            if len(self._call_times) >= self._max_cps and self._call_times:
                oldest = self._call_times[0]
                waits.append(max(0, (oldest + 1.0) - now))

            # Orders
            if call_type in ("order", "cancel"):
                self._purge_old_orders()
                if len(self._order_times) >= self._orders_per_min and self._order_times:
                    oldest_order = self._order_times[0]
                    waits.append(max(0, (oldest_order + 60.0) - now))

            return max(waits) if waits else 0.0

    def record_rate_limit(self) -> None:
        """
        Enregistre un rate limit (HTTP 429) et active le backoff.
        """
        with self._lock:
            self._rate_limits_hit += 1
            self._backoff_count += 1

            # Backoff exponentiel
            delay = min(
                self._backoff_base * (self._backoff_mult ** (self._backoff_count - 1)),
                self._backoff_max,
            )
            self._backoff_until = time.time() + delay

            logger.warning(
                f"⚠️ Rate limit hit #{self._rate_limits_hit}! "
                f"Backoff {delay:.1f}s (count={self._backoff_count})"
            )

    def record_success(self) -> None:
        """Enregistre un appel réussi (réduit le backoff count progressivement)."""
        with self._lock:
            if self._backoff_count > 0:
                self._backoff_count = max(0, self._backoff_count - 1)

    def clear_backoff(self) -> None:
        """Force la fin du backoff."""
        with self._lock:
            self._backoff_until = 0.0
            self._backoff_count = 0
            logger.info("Backoff cleared")

    # ------------------------------------------------------------------
    # Batch helpers
    # ------------------------------------------------------------------

    def can_batch(self, count: int, call_type: str = "order") -> bool:
        """
        Vérifie si un batch de `count` appels peut passer.

        Utile pour batch cancel ou batch order.
        """
        with self._lock:
            self._refill_tokens()
            self._purge_old_calls()

            if self._tokens < count:
                return False

            if len(self._call_times) + count > self._max_cps:
                return False

            if call_type in ("order", "cancel"):
                self._purge_old_orders()
                if len(self._order_times) + count > self._orders_per_min:
                    return False

            return True

    def optimal_batch_size(self, call_type: str = "order") -> int:
        """
        Retourne le nombre maximum d'appels faisables maintenant.
        """
        with self._lock:
            self._refill_tokens()
            self._purge_old_calls()

            available_tokens = int(self._tokens)
            available_cps = max(0, self._max_cps - len(self._call_times))
            available = min(available_tokens, available_cps)

            if call_type in ("order", "cancel"):
                self._purge_old_orders()
                available_orders = max(0, self._orders_per_min - len(self._order_times))
                available = min(available, available_orders)

            return available

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        """Retourne l'état complet du module."""
        with self._lock:
            self._refill_tokens()
            self._purge_old_calls()
            self._purge_old_orders()
            now = time.time()

            return {
                "module": "rate_limit_optimizer",
                "current": {
                    "tokens_available": round(self._tokens, 1),
                    "calls_last_second": len(self._call_times),
                    "orders_last_minute": len(self._order_times),
                    "backoff_active": now < self._backoff_until,
                    "backoff_remaining": round(max(0, self._backoff_until - now), 1),
                },
                "limits": {
                    "max_calls_per_second": self._max_cps,
                    "burst_limit": self._burst_limit,
                    "orders_per_minute": self._orders_per_min,
                    "safety_margin": self._safety_margin,
                },
                "stats": {
                    "total_calls": self._total_calls,
                    "total_orders": self._total_orders,
                    "blocked_calls": self._blocked_calls,
                    "rate_limits_hit": self._rate_limits_hit,
                    "backoff_count": self._backoff_count,
                    "total_wait_time": round(self._total_wait_time, 2),
                },
            }

    def reset(self) -> None:
        """Réinitialise toutes les statistiques et les windows."""
        with self._lock:
            self._call_times.clear()
            self._order_times.clear()
            self._tokens = float(self._burst_limit)
            self._last_refill = time.time()
            self._backoff_until = 0.0
            self._backoff_count = 0
            self._total_calls = 0
            self._total_orders = 0
            self._blocked_calls = 0
            self._rate_limits_hit = 0
            self._total_wait_time = 0.0
            logger.info("RateLimitOptimizer réinitialisé")
