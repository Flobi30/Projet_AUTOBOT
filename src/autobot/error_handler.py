"""
Error Handler - Gestion des erreurs avec retry et circuit breaker
"""

import time
import logging
from typing import Callable, Any, Optional, Type, Tuple
from functools import wraps
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """États du circuit breaker"""
    CLOSED = "closed"      # Fonctionnement normal
    OPEN = "open"          # Circuit ouvert (erreurs)
    HALF_OPEN = "half_open"  # Test de récupération


class CircuitBreakerOpenError(Exception):
    """Exception levée quand le circuit breaker est ouvert"""
    pass


class ErrorHandler:
    """
    Gestionnaire d'erreurs avec retry et circuit breaker.
    
    Features:
    - Retry automatique avec backoff exponentiel
    - Circuit breaker pour éviter les cascades d'erreurs
    - Logging détaillé des erreurs
    """
    
    def __init__(
        self,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        backoff_factor: float = 2.0,
        circuit_failure_threshold: int = 5,
        circuit_recovery_timeout: float = 60.0
    ):
        """
        Initialise le gestionnaire d'erreurs.
        
        Args:
            max_retries: Nombre max de tentatives
            retry_delay: Délai initial entre retries (secondes)
            backoff_factor: Multiplicateur pour backoff exponentiel
            circuit_failure_threshold: Nombre d'erreurs avant ouverture circuit
            circuit_recovery_timeout: Temps avant tentative récupération (secondes)
        """
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.backoff_factor = backoff_factor
        self.circuit_failure_threshold = circuit_failure_threshold
        self.circuit_recovery_timeout = circuit_recovery_timeout
        
        # État du circuit breaker
        self._circuit_state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
        
    @property
    def circuit_state(self) -> CircuitState:
        """Retourne l'état actuel du circuit"""
        return self._circuit_state
    
    def _check_circuit(self) -> bool:
        """
        Vérifie si le circuit permet l'exécution.
        
        Returns:
            True si l'exécution est autorisée
        """
        if self._circuit_state == CircuitState.CLOSED:
            return True
        
        if self._circuit_state == CircuitState.OPEN:
            # Vérifie si on peut passer en half-open
            if time.time() - self._last_failure_time > self.circuit_recovery_timeout:
                logger.info("🔧 Circuit breaker: Passage en HALF_OPEN pour test de récupération")
                self._circuit_state = CircuitState.HALF_OPEN
                return True
            return False
        
        # HALF_OPEN: autorise une tentative
        return True
    
    def _record_success(self):
        """Enregistre un succès (ferme le circuit si half-open)"""
        if self._circuit_state == CircuitState.HALF_OPEN:
            logger.info("✅ Circuit breaker: Récupération réussie, circuit FERMÉ")
            self._circuit_state = CircuitState.CLOSED
            self._failure_count = 0
    
    def _record_failure(self):
        """Enregistre un échec (ouvre le circuit si trop d'erreurs)"""
        self._failure_count += 1
        self._last_failure_time = time.time()
        
        if self._circuit_state == CircuitState.HALF_OPEN:
            # Échec en half-open = retour en open
            logger.warning("❌ Circuit breaker: Échec en HALF_OPEN, circuit OUVERT")
            self._circuit_state = CircuitState.OPEN
        elif self._failure_count >= self.circuit_failure_threshold:
            logger.warning(f"❌ Circuit breaker: {self._failure_count} échecs, circuit OUVERT")
            self._circuit_state = CircuitState.OPEN
    
    def execute_with_retry(
        self,
        func: Callable,
        *args,
        expected_exceptions: Tuple[Type[Exception], ...] = (Exception,),
        **kwargs
    ) -> Any:
        """
        Exécute une fonction avec retry et circuit breaker.
        
        Args:
            func: Fonction à exécuter
            *args: Arguments positionnels
            expected_exceptions: Exceptions qui déclenchent un retry
            **kwargs: Arguments nommés
            
        Returns:
            Résultat de la fonction
            
        Raises:
            CircuitBreakerOpenError: Si le circuit est ouvert
            Exception: La dernière exception après épuisement des retries
        """
        # Vérifie le circuit breaker
        if not self._check_circuit():
            raise CircuitBreakerOpenError("Circuit breaker est ouvert - trop d'erreurs récentes")
        
        last_exception = None
        delay = self.retry_delay
        
        for attempt in range(1, self.max_retries + 1):
            try:
                result = func(*args, **kwargs)
                self._record_success()
                return result
                
            except expected_exceptions as e:
                last_exception = e
                self._record_failure()
                
                if attempt < self.max_retries:
                    logger.warning(
                        f"⚠️ Tentative {attempt}/{self.max_retries} échouée: {e}. "
                        f"Retry dans {delay:.1f}s..."
                    )
                    time.sleep(delay)
                    delay *= self.backoff_factor
                else:
                    logger.error(f"❌ Toutes les tentatives échouées: {e}")
        
        raise last_exception
    
    def retry_decorator(
        self,
        expected_exceptions: Tuple[Type[Exception], ...] = (Exception,)
    ):
        """
        Décorateur pour ajouter le retry à une fonction.
        
        Args:
            expected_exceptions: Exceptions qui déclenchent un retry
            
        Returns:
            Décorateur
        """
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs) -> Any:
                return self.execute_with_retry(
                    func, *args,
                    expected_exceptions=expected_exceptions,
                    **kwargs
                )
            return wrapper
        return decorator
