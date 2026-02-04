"""
Tests for data_connector circuit_breaker module.
"""

import asyncio
import pytest
from src.data_connector.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    CircuitBreakerConfig,
)
from src.data_connector.exceptions import CircuitBreakerOpen


class TestCircuitBreakerConfig:
    """Tests for CircuitBreakerConfig."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = CircuitBreakerConfig()
        assert config.failure_threshold == 5
        assert config.success_threshold == 2
        assert config.timeout == 60.0
        assert config.half_open_max_calls == 3
    
    def test_custom_config(self):
        """Test custom configuration."""
        config = CircuitBreakerConfig(
            failure_threshold=10,
            success_threshold=3,
            timeout=30.0,
            half_open_max_calls=5
        )
        assert config.failure_threshold == 10
        assert config.success_threshold == 3
        assert config.timeout == 30.0
        assert config.half_open_max_calls == 5


class TestCircuitBreaker:
    """Tests for CircuitBreaker."""
    
    def test_initialization(self):
        """Test circuit breaker initialization."""
        breaker = CircuitBreaker(failure_threshold=5, timeout=60.0)
        assert breaker.state == CircuitState.CLOSED
        assert breaker.is_closed is True
        assert breaker.failure_count == 0
    
    def test_initialization_with_config(self):
        """Test initialization with config object."""
        config = CircuitBreakerConfig(failure_threshold=10)
        breaker = CircuitBreaker(config=config)
        assert breaker._failure_threshold == 10
    
    def test_allow_request_closed(self):
        """Test that requests are allowed when closed."""
        breaker = CircuitBreaker()
        assert breaker.allow_request() is True
    
    def test_record_success(self):
        """Test recording successful calls."""
        breaker = CircuitBreaker()
        breaker.record_success()
        
        metrics = breaker.get_metrics()
        assert metrics["total_successes"] == 1
        assert metrics["total_calls"] == 1
    
    def test_record_failure(self):
        """Test recording failed calls."""
        breaker = CircuitBreaker(failure_threshold=5)
        breaker.record_failure()
        
        assert breaker.failure_count == 1
        assert breaker.state == CircuitState.CLOSED
    
    def test_opens_on_threshold(self):
        """Test that circuit opens when threshold reached."""
        breaker = CircuitBreaker(failure_threshold=3)
        
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == CircuitState.CLOSED
        
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN
        assert breaker.is_open is True
    
    def test_blocks_requests_when_open(self):
        """Test that requests are blocked when open."""
        breaker = CircuitBreaker(failure_threshold=1)
        breaker.record_failure()
        
        assert breaker.state == CircuitState.OPEN
        assert breaker.allow_request() is False
    
    def test_half_open_after_timeout(self):
        """Test transition to half-open after timeout."""
        breaker = CircuitBreaker(failure_threshold=1, timeout=0.01)
        breaker.record_failure()
        
        assert breaker.state == CircuitState.OPEN
        
        import time
        time.sleep(0.02)
        
        assert breaker.state == CircuitState.HALF_OPEN
    
    def test_half_open_allows_limited_requests(self):
        """Test that half-open allows limited requests."""
        breaker = CircuitBreaker(
            failure_threshold=1,
            timeout=0.01,
            half_open_max_calls=2
        )
        breaker.record_failure()
        
        import time
        time.sleep(0.02)
        
        assert breaker.allow_request() is True
        assert breaker.allow_request() is True
        assert breaker.allow_request() is False
    
    def test_closes_on_success_in_half_open(self):
        """Test that circuit closes on success in half-open."""
        breaker = CircuitBreaker(
            failure_threshold=1,
            success_threshold=2,
            timeout=0.01
        )
        breaker.record_failure()
        
        import time
        time.sleep(0.02)
        
        breaker.allow_request()
        breaker.record_success()
        assert breaker.state == CircuitState.HALF_OPEN
        
        breaker.allow_request()
        breaker.record_success()
        assert breaker.state == CircuitState.CLOSED
    
    def test_reopens_on_failure_in_half_open(self):
        """Test that circuit reopens on failure in half-open."""
        breaker = CircuitBreaker(failure_threshold=1, timeout=0.01)
        breaker.record_failure()
        
        import time
        time.sleep(0.02)
        
        assert breaker.state == CircuitState.HALF_OPEN
        
        breaker.allow_request()
        breaker.record_failure()
        
        assert breaker.state == CircuitState.OPEN
    
    def test_reset(self):
        """Test reset functionality."""
        breaker = CircuitBreaker(failure_threshold=1)
        breaker.record_failure()
        
        assert breaker.state == CircuitState.OPEN
        
        breaker.reset()
        
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0
    
    def test_get_metrics(self):
        """Test metrics retrieval."""
        breaker = CircuitBreaker(name="test_breaker")
        
        breaker.record_success()
        breaker.record_failure()
        
        metrics = breaker.get_metrics()
        
        assert metrics["name"] == "test_breaker"
        assert metrics["state"] == "closed"
        assert metrics["total_calls"] == 2
        assert metrics["total_successes"] == 1
        assert metrics["total_failures"] == 1
    
    def test_repr(self):
        """Test string representation."""
        breaker = CircuitBreaker(name="test", failure_threshold=5)
        repr_str = repr(breaker)
        
        assert "test" in repr_str
        assert "closed" in repr_str


class TestCircuitBreakerExecute:
    """Tests for circuit breaker execute method."""
    
    @pytest.mark.asyncio
    async def test_execute_success(self):
        """Test successful execution."""
        breaker = CircuitBreaker()
        
        async def success_func():
            return "success"
        
        result = await breaker.execute(success_func)
        
        assert result == "success"
        assert breaker.get_metrics()["total_successes"] == 1
    
    @pytest.mark.asyncio
    async def test_execute_failure(self):
        """Test execution with failure."""
        breaker = CircuitBreaker()
        
        async def fail_func():
            raise ValueError("Test error")
        
        with pytest.raises(ValueError):
            await breaker.execute(fail_func)
        
        assert breaker.failure_count == 1
    
    @pytest.mark.asyncio
    async def test_execute_blocked_when_open(self):
        """Test that execute raises when circuit is open."""
        breaker = CircuitBreaker(failure_threshold=1)
        breaker.record_failure()
        
        async def some_func():
            return "result"
        
        with pytest.raises(CircuitBreakerOpen) as exc_info:
            await breaker.execute(some_func)
        
        assert exc_info.value.failure_count == 1
    
    @pytest.mark.asyncio
    async def test_execute_with_args(self):
        """Test execution with arguments."""
        breaker = CircuitBreaker()
        
        async def add_func(a, b):
            return a + b
        
        result = await breaker.execute(add_func, 2, 3)
        assert result == 5
    
    @pytest.mark.asyncio
    async def test_execute_with_kwargs(self):
        """Test execution with keyword arguments."""
        breaker = CircuitBreaker()
        
        async def greet_func(name, greeting="Hello"):
            return f"{greeting}, {name}!"
        
        result = await breaker.execute(greet_func, "World", greeting="Hi")
        assert result == "Hi, World!"
    
    @pytest.mark.asyncio
    async def test_execute_sync_function(self):
        """Test execution of sync function."""
        breaker = CircuitBreaker()
        
        def sync_func():
            return "sync result"
        
        result = await breaker.execute(sync_func)
        assert result == "sync result"


class TestCircuitBreakerDecorator:
    """Tests for circuit breaker decorator."""
    
    @pytest.mark.asyncio
    async def test_protect_decorator_async(self):
        """Test protect decorator with async function."""
        breaker = CircuitBreaker()
        
        @breaker.protect
        async def protected_func():
            return "protected"
        
        result = await protected_func()
        assert result == "protected"
    
    @pytest.mark.asyncio
    async def test_protect_decorator_records_success(self):
        """Test that decorator records success."""
        breaker = CircuitBreaker()
        
        @breaker.protect
        async def success_func():
            return "ok"
        
        await success_func()
        
        assert breaker.get_metrics()["total_successes"] == 1
    
    @pytest.mark.asyncio
    async def test_protect_decorator_records_failure(self):
        """Test that decorator records failure."""
        breaker = CircuitBreaker()
        
        @breaker.protect
        async def fail_func():
            raise RuntimeError("Error")
        
        with pytest.raises(RuntimeError):
            await fail_func()
        
        assert breaker.failure_count == 1


class TestCircuitBreakerConcurrency:
    """Tests for circuit breaker under concurrent access."""
    
    @pytest.mark.asyncio
    async def test_concurrent_executions(self):
        """Test concurrent executions."""
        breaker = CircuitBreaker()
        
        async def slow_func():
            await asyncio.sleep(0.01)
            return "done"
        
        tasks = [breaker.execute(slow_func) for _ in range(10)]
        results = await asyncio.gather(*tasks)
        
        assert all(r == "done" for r in results)
        assert breaker.get_metrics()["total_successes"] == 10
    
    @pytest.mark.asyncio
    async def test_concurrent_failures(self):
        """Test concurrent failures."""
        breaker = CircuitBreaker(failure_threshold=5)
        
        async def fail_func():
            raise ValueError("Error")
        
        tasks = []
        for _ in range(10):
            tasks.append(breaker.execute(fail_func))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        errors = [r for r in results if isinstance(r, Exception)]
        assert len(errors) == 10
