"""
Rate Limiter - Limite les appels API pour éviter le rate limiting
"""

import time
import logging
from threading import Lock
from typing import Optional

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Rate limiter simple utilisant l'algorithme token bucket.
    
    Pour Kraken:
    - Endpoints privés: 20 appels max (système de counter complexe)
    - Prudent: 1 appel par seconde max
    """
    
    def __init__(self, max_calls_per_second: float = 1.0):
        """
        Initialise le rate limiter.
        
        Args:
            max_calls_per_second: Nombre max d'appels par seconde
        """
        self.min_interval = 1.0 / max_calls_per_second
        self._last_call_time: Optional[float] = None
        self._lock = Lock()
        
        logger.info(f"⏱️ RateLimiter initialisé: {max_calls_per_second} appels/sec max")
    
    def throttle(self):
        """
        Attend si nécessaire pour respecter le rate limit.
        Bloque jusqu'à ce qu'on puisse faire l'appel.
        """
        with self._lock:
            if self._last_call_time is not None:
                elapsed = time.time() - self._last_call_time
                if elapsed < self.min_interval:
                    sleep_time = self.min_interval - elapsed
                    time.sleep(sleep_time)
            
            self._last_call_time = time.time()
    
    def __enter__(self):
        """Context manager: throttle() au début"""
        self.throttle()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager: rien à faire à la sortie"""
        pass
