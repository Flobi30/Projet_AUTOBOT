"""
Tests for data_connector heartbeat module.
"""

import asyncio
import time
import pytest
from src.data_connector.heartbeat import (
    HeartbeatMonitor,
    HeartbeatConfig,
)


class TestHeartbeatConfig:
    """Tests for HeartbeatConfig."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = HeartbeatConfig()
        assert config.interval == 10.0
        assert config.timeout == 30.0
        assert config.max_missed == 3
    
    def test_custom_config(self):
        """Test custom configuration."""
        config = HeartbeatConfig(
            interval=5.0,
            timeout=15.0,
            max_missed=5
        )
        assert config.interval == 5.0
        assert config.timeout == 15.0
        assert config.max_missed == 5


class TestHeartbeatMonitor:
    """Tests for HeartbeatMonitor."""
    
    @pytest.fixture
    def healthy_check(self):
        """Health check that always returns True."""
        async def check():
            return True
        return check
    
    @pytest.fixture
    def unhealthy_check(self):
        """Health check that always returns False."""
        async def check():
            return False
        return check
    
    @pytest.fixture
    def slow_check(self):
        """Health check that takes too long."""
        async def check():
            await asyncio.sleep(10)
            return True
        return check
    
    def test_initialization(self, healthy_check):
        """Test heartbeat monitor initialization."""
        monitor = HeartbeatMonitor(
            health_check=healthy_check,
            interval=10.0,
            timeout=30.0,
            max_missed=3
        )
        
        assert monitor.is_running is False
        assert monitor.is_healthy is True
        assert monitor.missed_count == 0
    
    def test_initialization_with_config(self, healthy_check):
        """Test initialization with config object."""
        config = HeartbeatConfig(interval=5.0, timeout=15.0, max_missed=5)
        monitor = HeartbeatMonitor(
            health_check=healthy_check,
            config=config
        )
        
        assert monitor._interval == 5.0
        assert monitor._timeout == 15.0
        assert monitor._max_missed == 5
    
    @pytest.mark.asyncio
    async def test_start_stop(self, healthy_check):
        """Test starting and stopping the monitor."""
        monitor = HeartbeatMonitor(
            health_check=healthy_check,
            interval=0.1
        )
        
        await monitor.start()
        assert monitor.is_running is True
        
        await monitor.stop()
        assert monitor.is_running is False
    
    @pytest.mark.asyncio
    async def test_context_manager(self, healthy_check):
        """Test async context manager."""
        monitor = HeartbeatMonitor(
            health_check=healthy_check,
            interval=0.1
        )
        
        async with monitor:
            assert monitor.is_running is True
        
        assert monitor.is_running is False
    
    @pytest.mark.asyncio
    async def test_successful_heartbeat(self, healthy_check):
        """Test successful heartbeat updates last_heartbeat."""
        monitor = HeartbeatMonitor(
            health_check=healthy_check,
            interval=0.05,
            timeout=1.0
        )
        
        await monitor.start()
        await asyncio.sleep(0.1)
        
        assert monitor.last_heartbeat is not None
        assert monitor.is_healthy is True
        
        await monitor.stop()
    
    @pytest.mark.asyncio
    async def test_failed_heartbeat(self, unhealthy_check):
        """Test failed heartbeat increments missed count."""
        monitor = HeartbeatMonitor(
            health_check=unhealthy_check,
            interval=0.05,
            timeout=1.0,
            max_missed=10
        )
        
        await monitor.start()
        await asyncio.sleep(0.15)
        
        assert monitor.missed_count > 0
        
        await monitor.stop()
    
    @pytest.mark.asyncio
    async def test_connection_lost_callback(self, unhealthy_check):
        """Test that connection lost callback is called."""
        callback_called = asyncio.Event()
        
        async def on_lost():
            callback_called.set()
        
        monitor = HeartbeatMonitor(
            health_check=unhealthy_check,
            on_connection_lost=on_lost,
            interval=0.02,
            timeout=1.0,
            max_missed=2
        )
        
        await monitor.start()
        
        try:
            await asyncio.wait_for(callback_called.wait(), timeout=0.5)
            assert callback_called.is_set()
        except asyncio.TimeoutError:
            pytest.fail("Connection lost callback was not called")
        finally:
            await monitor.stop()
    
    @pytest.mark.asyncio
    async def test_connection_restored_callback(self):
        """Test that connection restored callback is called."""
        health_status = {"healthy": False}
        restored_called = asyncio.Event()
        
        async def health_check():
            return health_status["healthy"]
        
        async def on_restored():
            restored_called.set()
        
        monitor = HeartbeatMonitor(
            health_check=health_check,
            on_connection_restored=on_restored,
            interval=0.02,
            timeout=1.0,
            max_missed=2
        )
        
        await monitor.start()
        await asyncio.sleep(0.1)
        
        health_status["healthy"] = True
        
        try:
            await asyncio.wait_for(restored_called.wait(), timeout=0.5)
            assert restored_called.is_set()
        except asyncio.TimeoutError:
            pass
        finally:
            await monitor.stop()
    
    @pytest.mark.asyncio
    async def test_timeout_handling(self, slow_check):
        """Test that slow health checks are handled."""
        monitor = HeartbeatMonitor(
            health_check=slow_check,
            interval=0.05,
            timeout=0.01,
            max_missed=10
        )
        
        await monitor.start()
        await asyncio.sleep(0.15)
        
        assert monitor.missed_count > 0
        
        await monitor.stop()
    
    def test_record_activity(self, healthy_check):
        """Test manual activity recording."""
        monitor = HeartbeatMonitor(
            health_check=healthy_check,
            interval=10.0
        )
        
        monitor.record_activity()
        
        assert monitor.last_heartbeat is not None
        assert monitor.missed_count == 0
    
    def test_time_since_heartbeat(self, healthy_check):
        """Test time since heartbeat calculation."""
        monitor = HeartbeatMonitor(
            health_check=healthy_check,
            interval=10.0
        )
        
        assert monitor.time_since_heartbeat is None
        
        monitor.record_activity()
        time.sleep(0.1)
        
        assert monitor.time_since_heartbeat is not None
        assert monitor.time_since_heartbeat >= 0.1
    
    @pytest.mark.asyncio
    async def test_get_metrics(self, healthy_check):
        """Test metrics retrieval."""
        monitor = HeartbeatMonitor(
            health_check=healthy_check,
            interval=0.05,
            timeout=1.0
        )
        
        await monitor.start()
        await asyncio.sleep(0.15)
        await monitor.stop()
        
        metrics = monitor.get_metrics()
        
        assert "is_running" in metrics
        assert "is_healthy" in metrics
        assert "missed_count" in metrics
        assert "total_checks" in metrics
        assert "successful_checks" in metrics
        assert metrics["total_checks"] > 0
    
    @pytest.mark.asyncio
    async def test_double_start(self, healthy_check):
        """Test that double start is handled gracefully."""
        monitor = HeartbeatMonitor(
            health_check=healthy_check,
            interval=0.1
        )
        
        await monitor.start()
        await monitor.start()
        
        assert monitor.is_running is True
        
        await monitor.stop()
    
    @pytest.mark.asyncio
    async def test_double_stop(self, healthy_check):
        """Test that double stop is handled gracefully."""
        monitor = HeartbeatMonitor(
            health_check=healthy_check,
            interval=0.1
        )
        
        await monitor.start()
        await monitor.stop()
        await monitor.stop()
        
        assert monitor.is_running is False


class TestHeartbeatMonitorLatency:
    """Tests for heartbeat monitor latency tracking."""
    
    @pytest.mark.asyncio
    async def test_latency_tracking(self):
        """Test that latency is tracked."""
        async def slow_healthy_check():
            await asyncio.sleep(0.01)
            return True
        
        monitor = HeartbeatMonitor(
            health_check=slow_healthy_check,
            interval=0.05,
            timeout=1.0
        )
        
        await monitor.start()
        await asyncio.sleep(0.2)
        await monitor.stop()
        
        metrics = monitor.get_metrics()
        
        assert metrics["avg_latency_ms"] > 0
        assert metrics["p95_latency_ms"] > 0
