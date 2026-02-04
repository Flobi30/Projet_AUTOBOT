"""
Circuit Breaker pattern implementation for fault tolerance.

Provides protection against cascading failures by temporarily
blocking requests when a service is experiencing issues.

States:
- CLOSED: Normal operation, requests pass through
- OPEN: Service is failing, requests are blocked
- HALF_OPEN: Testing if service has recovered
"""

import asyncio
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional, TypeVar, Generic
from functools import wraps

from .exceptions import CircuitBreakerOpen


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""
    failure_threshold: int = 5  # failures before opening
    success_threshold: int = 2  # successes in half-open before closing
    timeout: float = 60.0  # seconds to wait before half-open
    half_open_max_calls: int = 3  # max calls allowed in half-open state


T = TypeVar("T")


class CircuitBreaker:
    """
    Circuit Breaker for protecting against cascading failures.
    
    The circuit breaker monitors for failures and opens the circuit
    when the failure threshold is reached, preventing further calls
    until the timeout expires.
    
    Features:
    - Configurable failure and success thresholds
    - Automatic state transitions
    - Async-compatible
    - Metrics and monitoring
    - Decorator support
    
    Example:
        breaker = CircuitBreaker(failure_threshold=5, timeout=60.0)
        
        # Manual usage
        if breaker.allow_request():
            try:
                result = await some_operation()
                breaker.record_success()
            except Exception as e:
                breaker.record_failure()
                raise
        
        # Decorator usage
        @breaker.protect
        async def protected_operation():
            return await some_operation()
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout: float = 60.0,
        half_open_max_calls: int = 3,
        config: Optional[CircuitBreakerConfig] = None,
        name: str = "default"
    ):
        """
        Initialize circuit breaker.
        
        Args:
            failure_threshold: Number of failures before opening circuit
            success_threshold: Number of successes in half-open before closing
            timeout: Seconds to wait before transitioning to half-open
            half_open_max_calls: Maximum calls allowed in half-open state
            config: Optional configuration object
            name: Name for identification in logs
        """
        if config:
            self._failure_threshold = config.failure_threshold
            self._success_threshold = config.success_threshold
            self._timeout = config.timeout
            self._half_open_max_calls = config.half_open_max_calls
        else:
            self._failure_threshold = failure_threshold
            self._success_threshold = success_threshold
            self._timeout = timeout
            self._half_open_max_calls = half_open_max_calls
        
        self._name = name
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._half_open_calls = 0
        self._lock = asyncio.Lock()
        
        # Metrics
        self._total_calls = 0
        self._total_failures = 0
        self._total_successes = 0
        self._total_rejected = 0
        self._state_changes: list[tuple[float, CircuitState]] = []
    
    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        self._check_state_transition()
        return self._state
    
    @property
    def is_closed(self) -> bool:
        """Check if circuit is closed (normal operation)."""
        return self.state == CircuitState.CLOSED
    
    @property
    def is_open(self) -> bool:
        """Check if circuit is open (blocking requests)."""
        return self.state == CircuitState.OPEN
    
    @property
    def failure_count(self) -> int:
        """Get current failure count."""
        return self._failure_count
    
    def _check_state_transition(self) -> None:
        """Check and perform automatic state transitions."""
        if self._state == CircuitState.OPEN:
            if self._last_failure_time is not None:
                elapsed = time.monotonic() - self._last_failure_time
                if elapsed >= self._timeout:
                    self._transition_to(CircuitState.HALF_OPEN)
    
    def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to a new state."""
        old_state = self._state
        self._state = new_state
        self._state_changes.append((time.monotonic(), new_state))
        
        if new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0
            self._success_count = 0
        elif new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
    
    def allow_request(self) -> bool:
        """
        Check if a request should be allowed.
        
        Returns:
            True if request is allowed, False otherwise
        """
        self._check_state_transition()
        
        if self._state == CircuitState.CLOSED:
            return True
        
        if self._state == CircuitState.OPEN:
            return False
        
        # HALF_OPEN state
        if self._half_open_calls < self._half_open_max_calls:
            self._half_open_calls += 1
            return True
        
        return False
    
    def record_success(self) -> None:
        """Record a successful call."""
        self._total_calls += 1
        self._total_successes += 1
        
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self._success_threshold:
                self._transition_to(CircuitState.CLOSED)
        elif self._state == CircuitState.CLOSED:
            # Reset failure count on success in closed state
            self._failure_count = max(0, self._failure_count - 1)
    
    def record_failure(self) -> None:
        """Record a failed call."""
        self._total_calls += 1
        self._total_failures += 1
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        
        if self._state == CircuitState.HALF_OPEN:
            # Any failure in half-open reopens the circuit
            self._transition_to(CircuitState.OPEN)
        elif self._state == CircuitState.CLOSED:
            if self._failure_count >= self._failure_threshold:
                self._transition_to(CircuitState.OPEN)
    
    async def execute(self, func: Callable[..., Any], *args, **kwargs) -> Any:
        """
        Execute a function with circuit breaker protection.
        
        Args:
            func: Function to execute
            *args: Positional arguments for function
            **kwargs: Keyword arguments for function
            
        Returns:
            Result of the function
            
        Raises:
            CircuitBreakerOpen: If circuit is open
        """
        async with self._lock:
            if not self.allow_request():
                self._total_rejected += 1
                time_until_reset = 0.0
                if self._last_failure_time:
                    time_until_reset = max(
                        0,
                        self._timeout - (time.monotonic() - self._last_failure_time)
                    )
                raise CircuitBreakerOpen(
                    message=f"Circuit breaker '{self._name}' is open",
                    reset_time=time_until_reset,
                    failure_count=self._failure_count
                )
        
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            self.record_success()
            return result
        except CircuitBreakerOpen:
            raise
        except Exception as e:
            self.record_failure()
            raise
    
    def protect(self, func: Callable) -> Callable:
        """
        Decorator to protect a function with circuit breaker.
        
        Example:
            @breaker.protect
            async def my_function():
                return await some_operation()
        """
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                return await self.execute(func, *args, **kwargs)
            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                return asyncio.get_event_loop().run_until_complete(
                    self.execute(func, *args, **kwargs)
                )
            return sync_wrapper
    
    def reset(self) -> None:
        """Reset circuit breaker to closed state."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        self._last_failure_time = None
    
    def get_metrics(self) -> dict:
        """Get circuit breaker metrics."""
        return {
            "name": self._name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "total_calls": self._total_calls,
            "total_failures": self._total_failures,
            "total_successes": self._total_successes,
            "total_rejected": self._total_rejected,
            "failure_threshold": self._failure_threshold,
            "timeout": self._timeout,
        }
    
    def __repr__(self) -> str:
        return (
            f"CircuitBreaker(name={self._name!r}, state={self._state.value}, "
            f"failures={self._failure_count}/{self._failure_threshold})"
        )
