"""
Rate Limiter implementation using Token Bucket algorithm.

Provides rate limiting at 50 requests/second as specified for IB connections.
Thread-safe and async-compatible implementation.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Optional

from .exceptions import RateLimitExceeded


@dataclass
class RateLimiterConfig:
    """Configuration for rate limiter."""
    rate: float = 50.0  # requests per second
    burst: int = 50  # maximum burst size
    
    def __post_init__(self):
        if self.rate <= 0:
            raise ValueError("Rate must be positive")
        if self.burst <= 0:
            raise ValueError("Burst must be positive")


class RateLimiter:
    """
    Token Bucket rate limiter for controlling request rates.
    
    Implements a token bucket algorithm that allows bursting up to
    the bucket capacity while maintaining an average rate limit.
    
    Features:
    - Async-compatible with proper locking
    - Configurable rate and burst size
    - Non-blocking check and blocking wait modes
    - Metrics for monitoring
    
    Example:
        limiter = RateLimiter(rate=50.0, burst=50)
        
        # Blocking wait
        await limiter.acquire()
        
        # Non-blocking check
        if limiter.try_acquire():
            # proceed with request
            pass
    """
    
    def __init__(
        self,
        rate: float = 50.0,
        burst: Optional[int] = None,
        config: Optional[RateLimiterConfig] = None
    ):
        """
        Initialize rate limiter.
        
        Args:
            rate: Maximum requests per second
            burst: Maximum burst size (defaults to rate)
            config: Optional configuration object
        """
        if config:
            self._rate = config.rate
            self._burst = config.burst
        else:
            self._rate = rate
            self._burst = burst if burst is not None else int(rate)
        
        self._tokens = float(self._burst)
        self._last_update = time.monotonic()
        self._lock = asyncio.Lock()
        
        # Metrics
        self._total_acquired = 0
        self._total_rejected = 0
        self._total_waited = 0.0
    
    @property
    def rate(self) -> float:
        """Get current rate limit."""
        return self._rate
    
    @property
    def burst(self) -> int:
        """Get burst capacity."""
        return self._burst
    
    @property
    def available_tokens(self) -> float:
        """Get current available tokens (approximate)."""
        self._refill()
        return self._tokens
    
    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_update
        self._tokens = min(
            self._burst,
            self._tokens + elapsed * self._rate
        )
        self._last_update = now
    
    def try_acquire(self, tokens: int = 1) -> bool:
        """
        Try to acquire tokens without blocking.
        
        Args:
            tokens: Number of tokens to acquire
            
        Returns:
            True if tokens acquired, False otherwise
        """
        self._refill()
        
        if self._tokens >= tokens:
            self._tokens -= tokens
            self._total_acquired += tokens
            return True
        
        self._total_rejected += tokens
        return False
    
    async def acquire(self, tokens: int = 1, timeout: Optional[float] = None) -> bool:
        """
        Acquire tokens, waiting if necessary.
        
        Args:
            tokens: Number of tokens to acquire
            timeout: Maximum time to wait (None for no timeout)
            
        Returns:
            True if tokens acquired
            
        Raises:
            RateLimitExceeded: If timeout exceeded
        """
        async with self._lock:
            start_time = time.monotonic()
            
            while True:
                self._refill()
                
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    self._total_acquired += tokens
                    wait_time = time.monotonic() - start_time
                    self._total_waited += wait_time
                    return True
                
                # Calculate wait time for tokens to be available
                tokens_needed = tokens - self._tokens
                wait_time = tokens_needed / self._rate
                
                # Check timeout
                if timeout is not None:
                    elapsed = time.monotonic() - start_time
                    if elapsed + wait_time > timeout:
                        self._total_rejected += tokens
                        raise RateLimitExceeded(
                            message=f"Rate limit exceeded, would need to wait {wait_time:.2f}s",
                            retry_after=wait_time
                        )
                
                # Wait for tokens
                await asyncio.sleep(min(wait_time, 0.1))
    
    async def __aenter__(self) -> "RateLimiter":
        """Context manager entry - acquire one token."""
        await self.acquire()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        pass
    
    def get_metrics(self) -> dict:
        """Get rate limiter metrics."""
        return {
            "rate": self._rate,
            "burst": self._burst,
            "available_tokens": self.available_tokens,
            "total_acquired": self._total_acquired,
            "total_rejected": self._total_rejected,
            "total_wait_time": self._total_waited,
        }
    
    def reset(self) -> None:
        """Reset the rate limiter to full capacity."""
        self._tokens = float(self._burst)
        self._last_update = time.monotonic()


class SlidingWindowRateLimiter:
    """
    Sliding window rate limiter for more precise rate limiting.
    
    Uses a sliding window approach that provides smoother rate limiting
    compared to token bucket, at the cost of slightly more memory usage.
    """
    
    def __init__(self, rate: float = 50.0, window_size: float = 1.0):
        """
        Initialize sliding window rate limiter.
        
        Args:
            rate: Maximum requests per window
            window_size: Window size in seconds
        """
        self._rate = rate
        self._window_size = window_size
        self._requests: list[float] = []
        self._lock = asyncio.Lock()
    
    def _cleanup(self) -> None:
        """Remove expired requests from the window."""
        now = time.monotonic()
        cutoff = now - self._window_size
        self._requests = [t for t in self._requests if t > cutoff]
    
    def try_acquire(self) -> bool:
        """Try to acquire a slot without blocking."""
        self._cleanup()
        
        if len(self._requests) < self._rate:
            self._requests.append(time.monotonic())
            return True
        return False
    
    async def acquire(self, timeout: Optional[float] = None) -> bool:
        """Acquire a slot, waiting if necessary."""
        async with self._lock:
            start_time = time.monotonic()
            
            while True:
                self._cleanup()
                
                if len(self._requests) < self._rate:
                    self._requests.append(time.monotonic())
                    return True
                
                # Calculate wait time
                oldest = self._requests[0]
                wait_time = oldest + self._window_size - time.monotonic()
                
                if timeout is not None:
                    elapsed = time.monotonic() - start_time
                    if elapsed + wait_time > timeout:
                        raise RateLimitExceeded(
                            message="Rate limit exceeded",
                            retry_after=wait_time
                        )
                
                await asyncio.sleep(min(max(wait_time, 0.01), 0.1))
