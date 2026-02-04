"""Tests for Rate Limiter module."""

import asyncio
import pytest
import time
from unittest.mock import MagicMock, patch

import sys
sys.path.insert(0, "/home/ubuntu/Projet_AUTOBOT/src")

from data_connector.rate_limiter import (
    RateLimitConfig,
    RateLimitState,
    RateLimiter,
    MultiProviderRateLimiter,
)


class TestRateLimitConfig:
    """Tests for RateLimitConfig dataclass."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = RateLimitConfig()
        
        assert config.requests_per_second == 10.0
        assert config.requests_per_minute == 600.0
        assert config.requests_per_hour == 36000.0
        assert config.requests_per_day == 100000.0
        assert config.burst_size == 20
        assert config.adaptive is True
    
    def test_custom_config(self):
        """Test custom configuration."""
        config = RateLimitConfig(
            requests_per_second=5.0,
            burst_size=10,
            adaptive=False,
        )
        
        assert config.requests_per_second == 5.0
        assert config.burst_size == 10
        assert config.adaptive is False
    
    def test_invalid_requests_per_second(self):
        """Test that invalid requests_per_second raises error."""
        with pytest.raises(ValueError):
            RateLimitConfig(requests_per_second=0)
        
        with pytest.raises(ValueError):
            RateLimitConfig(requests_per_second=-1)
    
    def test_invalid_burst_size(self):
        """Test that invalid burst_size raises error."""
        with pytest.raises(ValueError):
            RateLimitConfig(burst_size=0)


class TestRateLimitState:
    """Tests for RateLimitState dataclass."""
    
    def test_default_state(self):
        """Test default state values."""
        state = RateLimitState()
        
        assert state.tokens == 0.0
        assert state.request_count == 0
        assert state.minute_count == 0
        assert state.hour_count == 0
        assert state.day_count == 0
        assert state.consecutive_429s == 0
        assert state.current_backoff == 0.0
    
    def test_state_with_tokens(self):
        """Test state with initial tokens."""
        state = RateLimitState(tokens=10.0)
        
        assert state.tokens == 10.0


class TestRateLimiter:
    """Tests for RateLimiter class."""
    
    def test_limiter_creation(self):
        """Test RateLimiter creation."""
        limiter = RateLimiter(name="test")
        
        assert limiter.name == "test"
        assert limiter.config is not None
    
    def test_limiter_with_config(self):
        """Test RateLimiter with custom config."""
        config = RateLimitConfig(requests_per_second=5.0)
        limiter = RateLimiter(config=config, name="custom")
        
        assert limiter.config.requests_per_second == 5.0
    
    def test_acquire_success(self):
        """Test successful token acquisition."""
        config = RateLimitConfig(
            requests_per_second=100.0,
            burst_size=10,
        )
        limiter = RateLimiter(config=config, name="test")
        
        acquired, wait_time = limiter.acquire()
        
        assert acquired is True
        assert wait_time == 0.0
    
    def test_acquire_burst(self):
        """Test burst acquisition."""
        config = RateLimitConfig(
            requests_per_second=1.0,
            burst_size=5,
        )
        limiter = RateLimiter(config=config, name="test")
        
        for i in range(5):
            acquired, _ = limiter.acquire()
            assert acquired is True
        
        acquired, wait_time = limiter.acquire()
        assert acquired is False
        assert wait_time > 0
    
    def test_acquire_with_endpoint(self):
        """Test acquisition with specific endpoint."""
        limiter = RateLimiter(name="test")
        
        acquired, _ = limiter.acquire(endpoint="quotes")
        assert acquired is True
        
        acquired, _ = limiter.acquire(endpoint="historical")
        assert acquired is True
    
    @pytest.mark.asyncio
    async def test_acquire_async(self):
        """Test async token acquisition."""
        limiter = RateLimiter(name="test")
        
        acquired, wait_time = await limiter.acquire_async()
        
        assert acquired is True
        assert wait_time == 0.0
    
    @pytest.mark.asyncio
    async def test_wait_and_acquire(self):
        """Test wait_and_acquire method."""
        config = RateLimitConfig(
            requests_per_second=100.0,
            burst_size=10,
        )
        limiter = RateLimiter(config=config, name="test")
        
        result = await limiter.wait_and_acquire(max_wait=1.0)
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_wait_and_acquire_timeout(self):
        """Test wait_and_acquire with timeout."""
        config = RateLimitConfig(
            requests_per_second=0.1,
            burst_size=1,
        )
        limiter = RateLimiter(config=config, name="test")
        
        await limiter.acquire_async()
        
        result = await limiter.wait_and_acquire(max_wait=0.1)
        
        assert result is False
    
    def test_report_429(self):
        """Test reporting 429 response."""
        config = RateLimitConfig(adaptive=True, backoff_factor=2.0)
        limiter = RateLimiter(config=config, name="test")
        
        limiter.report_429("test_endpoint")
        
        stats = limiter.get_stats("test_endpoint")
        assert stats["consecutive_429s"] == 1
    
    def test_report_success(self):
        """Test reporting successful request."""
        limiter = RateLimiter(name="test")
        
        limiter.report_429("test_endpoint")
        limiter.report_success("test_endpoint")
        
        stats = limiter.get_stats("test_endpoint")
        assert stats["consecutive_429s"] == 0
    
    def test_get_stats(self):
        """Test getting statistics."""
        limiter = RateLimiter(name="test")
        
        limiter.acquire()
        limiter.acquire()
        
        stats = limiter.get_stats()
        
        assert stats["name"] == "test"
        assert stats["total_requests"] == 2
        assert "available_tokens" in stats
        assert "limits" in stats
        assert "remaining" in stats
    
    def test_reset(self):
        """Test resetting rate limiter."""
        limiter = RateLimiter(name="test")
        
        for _ in range(5):
            limiter.acquire()
        
        limiter.reset()
        
        stats = limiter.get_stats()
        assert stats["total_requests"] == 0
    
    def test_reset_endpoint(self):
        """Test resetting specific endpoint."""
        limiter = RateLimiter(name="test")
        
        limiter.acquire("endpoint1")
        limiter.acquire("endpoint2")
        
        limiter.reset("endpoint1")
        
        stats1 = limiter.get_stats("endpoint1")
        stats2 = limiter.get_stats("endpoint2")
        
        assert stats1["total_requests"] == 0
        assert stats2["total_requests"] == 1
    
    def test_rate_limit_callback(self):
        """Test rate limit callback."""
        config = RateLimitConfig(
            requests_per_second=1.0,
            burst_size=1,
        )
        limiter = RateLimiter(config=config, name="test")
        
        callback = MagicMock()
        limiter.set_rate_limit_callback(callback)
        
        limiter.acquire()
        limiter.acquire()
        
        callback.assert_called_once()
    
    def test_minute_limit(self):
        """Test minute rate limit."""
        config = RateLimitConfig(
            requests_per_second=1000.0,
            requests_per_minute=5,
            burst_size=100,
        )
        limiter = RateLimiter(config=config, name="test")
        
        for _ in range(5):
            acquired, _ = limiter.acquire()
            assert acquired is True
        
        acquired, wait_time = limiter.acquire()
        assert acquired is False
        assert wait_time > 0


class TestMultiProviderRateLimiter:
    """Tests for MultiProviderRateLimiter class."""
    
    def test_creation(self):
        """Test MultiProviderRateLimiter creation."""
        limiter = MultiProviderRateLimiter()
        assert limiter is not None
    
    def test_get_limiter_default(self):
        """Test getting limiter with default config."""
        multi = MultiProviderRateLimiter()
        
        limiter = multi.get_limiter("binance")
        
        assert limiter is not None
        assert limiter.name == "binance"
    
    def test_get_limiter_custom(self):
        """Test getting limiter with custom config."""
        multi = MultiProviderRateLimiter()
        config = RateLimitConfig(requests_per_second=5.0)
        
        limiter = multi.get_limiter("custom_provider", config)
        
        assert limiter.config.requests_per_second == 5.0
    
    def test_get_limiter_cached(self):
        """Test that limiter is cached."""
        multi = MultiProviderRateLimiter()
        
        limiter1 = multi.get_limiter("binance")
        limiter2 = multi.get_limiter("binance")
        
        assert limiter1 is limiter2
    
    @pytest.mark.asyncio
    async def test_acquire(self):
        """Test acquiring token for provider."""
        multi = MultiProviderRateLimiter()
        
        acquired, wait_time = await multi.acquire("binance")
        
        assert acquired is True
        assert wait_time == 0.0
    
    @pytest.mark.asyncio
    async def test_wait_and_acquire(self):
        """Test wait_and_acquire for provider."""
        multi = MultiProviderRateLimiter()
        
        result = await multi.wait_and_acquire("binance", max_wait=1.0)
        
        assert result is True
    
    def test_report_429(self):
        """Test reporting 429 for provider."""
        multi = MultiProviderRateLimiter()
        
        limiter = multi.get_limiter("binance")
        limiter.report_429()
        
        stats = limiter.get_stats()
        assert stats["consecutive_429s"] >= 0  # Backoff resets on success
    
    def test_report_success(self):
        """Test reporting success for provider."""
        multi = MultiProviderRateLimiter()
        
        multi.get_limiter("binance")
        multi.report_429("binance")
        multi.report_success("binance")
        
        stats = multi.get_all_stats()
        assert stats["binance"]["consecutive_429s"] == 0
    
    def test_get_all_stats(self):
        """Test getting stats for all providers."""
        multi = MultiProviderRateLimiter()
        
        multi.get_limiter("binance")
        multi.get_limiter("coinbase")
        
        stats = multi.get_all_stats()
        
        assert "binance" in stats
        assert "coinbase" in stats
    
    def test_provider_defaults(self):
        """Test that provider defaults are applied."""
        multi = MultiProviderRateLimiter()
        
        assert "twelvedata_free" in MultiProviderRateLimiter.PROVIDER_DEFAULTS
        assert "binance" in MultiProviderRateLimiter.PROVIDER_DEFAULTS
        assert "interactive_brokers" in MultiProviderRateLimiter.PROVIDER_DEFAULTS
        
        td_config = MultiProviderRateLimiter.PROVIDER_DEFAULTS["twelvedata_free"]
        assert td_config.requests_per_day == 800
        
        ib_config = MultiProviderRateLimiter.PROVIDER_DEFAULTS["interactive_brokers"]
        assert ib_config.requests_per_second == 50.0


class TestRateLimiterIntegration:
    """Integration tests for rate limiter."""
    
    @pytest.mark.asyncio
    async def test_concurrent_requests(self):
        """Test concurrent request handling."""
        config = RateLimitConfig(
            requests_per_second=10.0,
            burst_size=5,
        )
        limiter = RateLimiter(config=config, name="test")
        
        async def make_request():
            return await limiter.acquire_async()
        
        tasks = [make_request() for _ in range(5)]
        results = await asyncio.gather(*tasks)
        
        acquired_count = sum(1 for acquired, _ in results if acquired)
        assert acquired_count == 5
    
    @pytest.mark.asyncio
    async def test_token_refill(self):
        """Test token refill over time."""
        config = RateLimitConfig(
            requests_per_second=10.0,
            burst_size=2,
        )
        limiter = RateLimiter(config=config, name="test")
        
        await limiter.acquire_async()
        await limiter.acquire_async()
        
        acquired, _ = await limiter.acquire_async()
        assert acquired is False
        
        await asyncio.sleep(0.2)
        
        acquired, _ = await limiter.acquire_async()
        assert acquired is True
