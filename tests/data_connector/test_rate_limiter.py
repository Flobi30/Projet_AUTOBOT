"""
Tests for data_connector rate_limiter module.
"""

import asyncio
import time
import pytest
from src.data_connector.rate_limiter import (
    RateLimiter,
    RateLimiterConfig,
    SlidingWindowRateLimiter,
)
from src.data_connector.exceptions import RateLimitExceeded


class TestRateLimiterConfig:
    """Tests for RateLimiterConfig."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = RateLimiterConfig()
        assert config.rate == 50.0
        assert config.burst == 50
    
    def test_custom_config(self):
        """Test custom configuration."""
        config = RateLimiterConfig(rate=100.0, burst=200)
        assert config.rate == 100.0
        assert config.burst == 200
    
    def test_invalid_rate(self):
        """Test that invalid rate raises error."""
        with pytest.raises(ValueError, match="Rate must be positive"):
            RateLimiterConfig(rate=0)
        
        with pytest.raises(ValueError, match="Rate must be positive"):
            RateLimiterConfig(rate=-10)
    
    def test_invalid_burst(self):
        """Test that invalid burst raises error."""
        with pytest.raises(ValueError, match="Burst must be positive"):
            RateLimiterConfig(burst=0)


class TestRateLimiter:
    """Tests for RateLimiter."""
    
    def test_initialization(self):
        """Test rate limiter initialization."""
        limiter = RateLimiter(rate=50.0, burst=50)
        assert limiter.rate == 50.0
        assert limiter.burst == 50
    
    def test_initialization_with_config(self):
        """Test initialization with config object."""
        config = RateLimiterConfig(rate=100.0, burst=100)
        limiter = RateLimiter(config=config)
        assert limiter.rate == 100.0
        assert limiter.burst == 100
    
    def test_default_burst(self):
        """Test that burst defaults to rate."""
        limiter = RateLimiter(rate=30.0)
        assert limiter.burst == 30
    
    def test_try_acquire_success(self):
        """Test successful token acquisition."""
        limiter = RateLimiter(rate=50.0, burst=50)
        assert limiter.try_acquire() is True
        assert limiter.available_tokens < 50
    
    def test_try_acquire_multiple(self):
        """Test acquiring multiple tokens."""
        limiter = RateLimiter(rate=50.0, burst=50)
        assert limiter.try_acquire(tokens=10) is True
        assert limiter.available_tokens < 41
    
    def test_try_acquire_exhausted(self):
        """Test acquisition when tokens exhausted."""
        limiter = RateLimiter(rate=50.0, burst=5)
        
        for _ in range(5):
            assert limiter.try_acquire() is True
        
        assert limiter.try_acquire() is False
    
    def test_token_refill(self):
        """Test that tokens refill over time."""
        limiter = RateLimiter(rate=1000.0, burst=10)
        
        for _ in range(10):
            limiter.try_acquire()
        
        assert limiter.available_tokens < 1
        
        time.sleep(0.02)
        
        assert limiter.available_tokens >= 1
    
    @pytest.mark.asyncio
    async def test_acquire_success(self):
        """Test async acquire success."""
        limiter = RateLimiter(rate=50.0, burst=50)
        result = await limiter.acquire()
        assert result is True
    
    @pytest.mark.asyncio
    async def test_acquire_waits(self):
        """Test that acquire waits for tokens."""
        limiter = RateLimiter(rate=100.0, burst=1)
        
        await limiter.acquire()
        
        start = time.monotonic()
        await limiter.acquire()
        elapsed = time.monotonic() - start
        
        assert elapsed >= 0.005
    
    @pytest.mark.asyncio
    async def test_acquire_timeout(self):
        """Test acquire with timeout."""
        limiter = RateLimiter(rate=1.0, burst=1)
        
        await limiter.acquire()
        
        with pytest.raises(RateLimitExceeded) as exc_info:
            await limiter.acquire(timeout=0.01)
        
        assert exc_info.value.retry_after is not None
    
    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test async context manager."""
        limiter = RateLimiter(rate=50.0, burst=50)
        
        async with limiter:
            pass
        
        assert limiter.available_tokens < 50
    
    def test_get_metrics(self):
        """Test metrics retrieval."""
        limiter = RateLimiter(rate=50.0, burst=50)
        
        limiter.try_acquire()
        limiter.try_acquire()
        
        metrics = limiter.get_metrics()
        
        assert metrics["rate"] == 50.0
        assert metrics["burst"] == 50
        assert metrics["total_acquired"] == 2
        assert "available_tokens" in metrics
    
    def test_reset(self):
        """Test reset functionality."""
        limiter = RateLimiter(rate=50.0, burst=50)
        
        for _ in range(50):
            limiter.try_acquire()
        
        assert limiter.available_tokens < 1
        
        limiter.reset()
        
        assert limiter.available_tokens == 50.0
    
    def test_rejected_tracking(self):
        """Test that rejected requests are tracked."""
        limiter = RateLimiter(rate=50.0, burst=2)
        
        limiter.try_acquire()
        limiter.try_acquire()
        limiter.try_acquire()
        
        metrics = limiter.get_metrics()
        assert metrics["total_rejected"] == 1


class TestSlidingWindowRateLimiter:
    """Tests for SlidingWindowRateLimiter."""
    
    def test_initialization(self):
        """Test sliding window initialization."""
        limiter = SlidingWindowRateLimiter(rate=50.0, window_size=1.0)
        assert limiter._rate == 50.0
        assert limiter._window_size == 1.0
    
    def test_try_acquire_success(self):
        """Test successful acquisition."""
        limiter = SlidingWindowRateLimiter(rate=50.0)
        assert limiter.try_acquire() is True
    
    def test_try_acquire_exhausted(self):
        """Test acquisition when limit reached."""
        limiter = SlidingWindowRateLimiter(rate=3.0)
        
        assert limiter.try_acquire() is True
        assert limiter.try_acquire() is True
        assert limiter.try_acquire() is True
        assert limiter.try_acquire() is False
    
    @pytest.mark.asyncio
    async def test_acquire_waits(self):
        """Test that acquire waits when limit reached."""
        limiter = SlidingWindowRateLimiter(rate=10.0, window_size=0.1)
        
        for _ in range(10):
            await limiter.acquire()
        
        start = time.monotonic()
        await limiter.acquire()
        elapsed = time.monotonic() - start
        
        assert elapsed >= 0.05
    
    @pytest.mark.asyncio
    async def test_acquire_timeout(self):
        """Test acquire with timeout."""
        limiter = SlidingWindowRateLimiter(rate=1.0, window_size=1.0)
        
        await limiter.acquire()
        
        with pytest.raises(RateLimitExceeded):
            await limiter.acquire(timeout=0.01)


class TestRateLimiterConcurrency:
    """Tests for rate limiter under concurrent access."""
    
    @pytest.mark.asyncio
    async def test_concurrent_acquire(self):
        """Test concurrent token acquisition."""
        limiter = RateLimiter(rate=100.0, burst=100)
        
        async def acquire_token():
            await limiter.acquire()
            return True
        
        tasks = [acquire_token() for _ in range(50)]
        results = await asyncio.gather(*tasks)
        
        assert all(results)
        assert limiter.available_tokens < 51
    
    @pytest.mark.asyncio
    async def test_rate_enforcement(self):
        """Test that rate is actually enforced."""
        limiter = RateLimiter(rate=100.0, burst=10)
        
        start = time.monotonic()
        
        for _ in range(20):
            await limiter.acquire()
        
        elapsed = time.monotonic() - start
        
        assert elapsed >= 0.09
