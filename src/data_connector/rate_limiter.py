"""
Rate Limiter for Data Connector.

Implements token bucket algorithm with per-endpoint and global limits.
Supports burst handling and adaptive rate limiting.
"""

import asyncio
import logging
import time
import threading
from dataclasses import dataclass, field
from typing import Dict, Optional, Callable, Any
from collections import defaultdict
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""
    requests_per_second: float = 10.0
    requests_per_minute: float = 600.0
    requests_per_hour: float = 36000.0
    requests_per_day: float = 100000.0
    burst_size: int = 20
    adaptive: bool = True
    backoff_factor: float = 2.0
    max_backoff: float = 60.0
    min_interval: float = 0.01
    
    def __post_init__(self):
        if self.requests_per_second <= 0:
            raise ValueError("requests_per_second must be positive")
        if self.burst_size < 1:
            raise ValueError("burst_size must be at least 1")


@dataclass
class RateLimitState:
    """State for a rate limit bucket."""
    tokens: float = 0.0
    last_update: float = field(default_factory=time.time)
    request_count: int = 0
    minute_count: int = 0
    hour_count: int = 0
    day_count: int = 0
    minute_reset: float = field(default_factory=time.time)
    hour_reset: float = field(default_factory=time.time)
    day_reset: float = field(default_factory=time.time)
    consecutive_429s: int = 0
    current_backoff: float = 0.0


class RateLimiter:
    """
    Token bucket rate limiter with multiple time windows.
    
    Features:
    - Per-endpoint rate limiting
    - Global rate limiting
    - Burst handling
    - Adaptive rate limiting based on 429 responses
    - Async-safe with proper locking
    """
    
    def __init__(
        self,
        config: Optional[RateLimitConfig] = None,
        name: str = "default",
    ):
        self.config = config or RateLimitConfig()
        self.name = name
        
        self._global_state = RateLimitState(tokens=self.config.burst_size)
        self._endpoint_states: Dict[str, RateLimitState] = defaultdict(
            lambda: RateLimitState(tokens=self.config.burst_size)
        )
        self._lock = threading.RLock()
        self._async_lock = asyncio.Lock()
        
        self._on_rate_limit: Optional[Callable[[str, float], None]] = None
        
        logger.info(f"RateLimiter '{name}' initialized: {self.config.requests_per_second} req/s")
    
    def set_rate_limit_callback(self, callback: Callable[[str, float], None]) -> None:
        """Set callback for rate limit events."""
        self._on_rate_limit = callback
    
    def _refill_tokens(self, state: RateLimitState) -> None:
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - state.last_update
        
        tokens_to_add = elapsed * self.config.requests_per_second
        state.tokens = min(self.config.burst_size, state.tokens + tokens_to_add)
        state.last_update = now
        
        if now - state.minute_reset >= 60:
            state.minute_count = 0
            state.minute_reset = now
        
        if now - state.hour_reset >= 3600:
            state.hour_count = 0
            state.hour_reset = now
        
        if now - state.day_reset >= 86400:
            state.day_count = 0
            state.day_reset = now
    
    def _check_limits(self, state: RateLimitState) -> tuple[bool, float]:
        """
        Check if request is allowed.
        
        Returns:
            Tuple of (allowed, wait_time)
        """
        self._refill_tokens(state)
        
        if state.current_backoff > 0:
            return False, state.current_backoff
        
        if state.tokens < 1:
            wait_time = (1 - state.tokens) / self.config.requests_per_second
            return False, max(wait_time, self.config.min_interval)
        
        if state.minute_count >= self.config.requests_per_minute:
            wait_time = 60 - (time.time() - state.minute_reset)
            return False, max(wait_time, 0.1)
        
        if state.hour_count >= self.config.requests_per_hour:
            wait_time = 3600 - (time.time() - state.hour_reset)
            return False, max(wait_time, 0.1)
        
        if state.day_count >= self.config.requests_per_day:
            wait_time = 86400 - (time.time() - state.day_reset)
            return False, max(wait_time, 0.1)
        
        return True, 0.0
    
    def _consume_token(self, state: RateLimitState) -> None:
        """Consume a token from the bucket."""
        state.tokens -= 1
        state.request_count += 1
        state.minute_count += 1
        state.hour_count += 1
        state.day_count += 1
    
    def acquire(self, endpoint: str = "default") -> tuple[bool, float]:
        """
        Try to acquire a rate limit token (synchronous).
        
        Args:
            endpoint: Endpoint identifier for per-endpoint limiting
            
        Returns:
            Tuple of (acquired, wait_time)
        """
        with self._lock:
            global_allowed, global_wait = self._check_limits(self._global_state)
            if not global_allowed:
                if self._on_rate_limit:
                    self._on_rate_limit(endpoint, global_wait)
                return False, global_wait
            
            endpoint_state = self._endpoint_states[endpoint]
            endpoint_allowed, endpoint_wait = self._check_limits(endpoint_state)
            if not endpoint_allowed:
                if self._on_rate_limit:
                    self._on_rate_limit(endpoint, endpoint_wait)
                return False, endpoint_wait
            
            self._consume_token(self._global_state)
            self._consume_token(endpoint_state)
            
            return True, 0.0
    
    async def acquire_async(self, endpoint: str = "default") -> tuple[bool, float]:
        """
        Try to acquire a rate limit token (asynchronous).
        
        Args:
            endpoint: Endpoint identifier for per-endpoint limiting
            
        Returns:
            Tuple of (acquired, wait_time)
        """
        async with self._async_lock:
            return self.acquire(endpoint)
    
    async def wait_and_acquire(self, endpoint: str = "default", max_wait: float = 60.0) -> bool:
        """
        Wait until a token is available and acquire it.
        
        Args:
            endpoint: Endpoint identifier
            max_wait: Maximum time to wait in seconds
            
        Returns:
            bool: True if acquired, False if max_wait exceeded
        """
        total_waited = 0.0
        
        while total_waited < max_wait:
            acquired, wait_time = await self.acquire_async(endpoint)
            
            if acquired:
                return True
            
            if total_waited + wait_time > max_wait:
                return False
            
            await asyncio.sleep(min(wait_time, max_wait - total_waited))
            total_waited += wait_time
        
        return False
    
    def report_429(self, endpoint: str = "default") -> None:
        """
        Report a 429 (rate limited) response.
        
        Triggers adaptive backoff if enabled.
        """
        if not self.config.adaptive:
            return
        
        with self._lock:
            state = self._endpoint_states[endpoint]
            state.consecutive_429s += 1
            
            state.current_backoff = min(
                self.config.backoff_factor ** state.consecutive_429s,
                self.config.max_backoff
            )
            
            logger.warning(
                f"RateLimiter '{self.name}': 429 on {endpoint}, "
                f"backoff={state.current_backoff:.1f}s"
            )
            
            asyncio.get_event_loop().call_later(
                state.current_backoff,
                self._clear_backoff,
                endpoint
            )
    
    def _clear_backoff(self, endpoint: str) -> None:
        """Clear backoff for an endpoint."""
        with self._lock:
            if endpoint in self._endpoint_states:
                self._endpoint_states[endpoint].current_backoff = 0.0
    
    def report_success(self, endpoint: str = "default") -> None:
        """Report a successful request, resetting consecutive 429 count."""
        with self._lock:
            if endpoint in self._endpoint_states:
                self._endpoint_states[endpoint].consecutive_429s = 0
    
    def get_stats(self, endpoint: Optional[str] = None) -> Dict[str, Any]:
        """
        Get rate limiter statistics.
        
        Args:
            endpoint: Specific endpoint or None for global stats
            
        Returns:
            Dictionary of statistics
        """
        with self._lock:
            if endpoint:
                state = self._endpoint_states.get(endpoint, RateLimitState())
            else:
                state = self._global_state
            
            self._refill_tokens(state)
            
            return {
                "name": self.name,
                "endpoint": endpoint or "global",
                "available_tokens": state.tokens,
                "burst_size": self.config.burst_size,
                "requests_per_second": self.config.requests_per_second,
                "total_requests": state.request_count,
                "minute_requests": state.minute_count,
                "hour_requests": state.hour_count,
                "day_requests": state.day_count,
                "consecutive_429s": state.consecutive_429s,
                "current_backoff": state.current_backoff,
                "limits": {
                    "per_minute": self.config.requests_per_minute,
                    "per_hour": self.config.requests_per_hour,
                    "per_day": self.config.requests_per_day,
                },
                "remaining": {
                    "minute": max(0, self.config.requests_per_minute - state.minute_count),
                    "hour": max(0, self.config.requests_per_hour - state.hour_count),
                    "day": max(0, self.config.requests_per_day - state.day_count),
                },
            }
    
    def reset(self, endpoint: Optional[str] = None) -> None:
        """
        Reset rate limiter state.
        
        Args:
            endpoint: Specific endpoint to reset, or None for all
        """
        with self._lock:
            if endpoint:
                if endpoint in self._endpoint_states:
                    self._endpoint_states[endpoint] = RateLimitState(
                        tokens=self.config.burst_size
                    )
            else:
                self._global_state = RateLimitState(tokens=self.config.burst_size)
                self._endpoint_states.clear()
            
            logger.info(f"RateLimiter '{self.name}': Reset {'endpoint ' + endpoint if endpoint else 'all'}")


class MultiProviderRateLimiter:
    """
    Rate limiter for multiple API providers.
    
    Manages separate rate limits for each provider while
    coordinating global request flow.
    """
    
    PROVIDER_DEFAULTS = {
        "twelvedata_free": RateLimitConfig(
            requests_per_second=0.13,
            requests_per_minute=8,
            requests_per_hour=480,
            requests_per_day=800,
            burst_size=5,
        ),
        "twelvedata_pro": RateLimitConfig(
            requests_per_second=4.0,
            requests_per_minute=240,
            requests_per_hour=14400,
            requests_per_day=25000,
            burst_size=20,
        ),
        "alphavantage_free": RateLimitConfig(
            requests_per_second=0.083,
            requests_per_minute=5,
            requests_per_hour=300,
            requests_per_day=500,
            burst_size=5,
        ),
        "alphavantage_premium": RateLimitConfig(
            requests_per_second=1.25,
            requests_per_minute=75,
            requests_per_hour=4500,
            requests_per_day=100000,
            burst_size=15,
        ),
        "binance": RateLimitConfig(
            requests_per_second=10.0,
            requests_per_minute=1200,
            requests_per_hour=72000,
            requests_per_day=1000000,
            burst_size=50,
        ),
        "coinbase": RateLimitConfig(
            requests_per_second=10.0,
            requests_per_minute=600,
            requests_per_hour=36000,
            requests_per_day=500000,
            burst_size=30,
        ),
        "kraken": RateLimitConfig(
            requests_per_second=1.0,
            requests_per_minute=60,
            requests_per_hour=3600,
            requests_per_day=86400,
            burst_size=15,
        ),
        "interactive_brokers": RateLimitConfig(
            requests_per_second=50.0,
            requests_per_minute=3000,
            requests_per_hour=180000,
            requests_per_day=4000000,
            burst_size=100,
        ),
        "fred": RateLimitConfig(
            requests_per_second=2.0,
            requests_per_minute=120,
            requests_per_hour=7200,
            requests_per_day=100000,
            burst_size=10,
        ),
        "newsapi": RateLimitConfig(
            requests_per_second=0.5,
            requests_per_minute=30,
            requests_per_hour=1800,
            requests_per_day=1000,
            burst_size=5,
        ),
    }
    
    def __init__(self):
        self._limiters: Dict[str, RateLimiter] = {}
        self._lock = threading.RLock()
    
    def get_limiter(self, provider: str, config: Optional[RateLimitConfig] = None) -> RateLimiter:
        """
        Get or create a rate limiter for a provider.
        
        Args:
            provider: Provider name
            config: Optional custom configuration
            
        Returns:
            RateLimiter for the provider
        """
        with self._lock:
            if provider not in self._limiters:
                if config is None:
                    config = self.PROVIDER_DEFAULTS.get(provider, RateLimitConfig())
                
                self._limiters[provider] = RateLimiter(config=config, name=provider)
            
            return self._limiters[provider]
    
    async def acquire(self, provider: str, endpoint: str = "default") -> tuple[bool, float]:
        """Acquire a token for a provider."""
        limiter = self.get_limiter(provider)
        return await limiter.acquire_async(endpoint)
    
    async def wait_and_acquire(
        self,
        provider: str,
        endpoint: str = "default",
        max_wait: float = 60.0
    ) -> bool:
        """Wait and acquire a token for a provider."""
        limiter = self.get_limiter(provider)
        return await limiter.wait_and_acquire(endpoint, max_wait)
    
    def report_429(self, provider: str, endpoint: str = "default") -> None:
        """Report a 429 response for a provider."""
        limiter = self.get_limiter(provider)
        limiter.report_429(endpoint)
    
    def report_success(self, provider: str, endpoint: str = "default") -> None:
        """Report a successful request for a provider."""
        limiter = self.get_limiter(provider)
        limiter.report_success(endpoint)
    
    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all providers."""
        with self._lock:
            return {
                provider: limiter.get_stats()
                for provider, limiter in self._limiters.items()
            }
