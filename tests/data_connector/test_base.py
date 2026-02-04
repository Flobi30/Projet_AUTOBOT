"""
Tests for data_connector base module.
"""

import asyncio
import json
import logging
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from src.data_connector.base import (
    BaseConnector,
    ConnectorState,
    ConnectorConfig,
    ConnectionMetrics,
    JSONFormatter,
    setup_json_logger,
)
from src.data_connector.exceptions import DataConnectorError


class TestConnectorState:
    """Tests for ConnectorState enum."""
    
    def test_states_exist(self):
        """Test that all expected states exist."""
        assert ConnectorState.DISCONNECTED.value == "disconnected"
        assert ConnectorState.CONNECTING.value == "connecting"
        assert ConnectorState.CONNECTED.value == "connected"
        assert ConnectorState.RECONNECTING.value == "reconnecting"
        assert ConnectorState.ERROR.value == "error"


class TestConnectorConfig:
    """Tests for ConnectorConfig."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = ConnectorConfig()
        
        assert config.host == "127.0.0.1"
        assert config.port == 7497
        assert config.client_id == 1
        assert config.timeout == 30.0
        assert config.max_reconnect_attempts == 5
        assert config.reconnect_delay == 1.0
        assert config.heartbeat_interval == 10.0
        assert config.rate_limit == 50
    
    def test_custom_config(self):
        """Test custom configuration."""
        config = ConnectorConfig(
            host="192.168.1.1",
            port=7496,
            client_id=5,
            timeout=60.0,
            rate_limit=100
        )
        
        assert config.host == "192.168.1.1"
        assert config.port == 7496
        assert config.client_id == 5
        assert config.timeout == 60.0
        assert config.rate_limit == 100
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        config = ConnectorConfig()
        result = config.to_dict()
        
        assert isinstance(result, dict)
        assert result["host"] == "127.0.0.1"
        assert result["port"] == 7497
        assert result["rate_limit"] == 50


class TestConnectionMetrics:
    """Tests for ConnectionMetrics."""
    
    def test_default_metrics(self):
        """Test default metrics values."""
        metrics = ConnectionMetrics()
        
        assert metrics.connect_time is None
        assert metrics.disconnect_time is None
        assert metrics.reconnect_count == 0
        assert metrics.total_requests == 0
        assert metrics.failed_requests == 0
        assert metrics.latencies == []
    
    def test_uptime_seconds_not_connected(self):
        """Test uptime when not connected."""
        metrics = ConnectionMetrics()
        assert metrics.uptime_seconds == 0.0
    
    def test_uptime_seconds_connected(self):
        """Test uptime when connected."""
        metrics = ConnectionMetrics()
        metrics.connect_time = datetime.utcnow()
        
        import time
        time.sleep(0.1)
        
        assert metrics.uptime_seconds >= 0.1
    
    def test_success_rate_no_requests(self):
        """Test success rate with no requests."""
        metrics = ConnectionMetrics()
        assert metrics.success_rate == 1.0
    
    def test_success_rate_with_requests(self):
        """Test success rate calculation."""
        metrics = ConnectionMetrics()
        metrics.total_requests = 100
        metrics.failed_requests = 10
        
        assert metrics.success_rate == 0.9
    
    def test_p95_latency_empty(self):
        """Test p95 latency with no data."""
        metrics = ConnectionMetrics()
        assert metrics.p95_latency_ms == 0.0
    
    def test_p95_latency_with_data(self):
        """Test p95 latency calculation."""
        metrics = ConnectionMetrics()
        metrics.latencies = list(range(1, 101))
        
        p95 = metrics.p95_latency_ms
        assert p95 >= 95
    
    def test_record_latency(self):
        """Test latency recording."""
        metrics = ConnectionMetrics()
        
        metrics.record_latency(10.0)
        metrics.record_latency(20.0)
        
        assert len(metrics.latencies) == 2
        assert 10.0 in metrics.latencies
        assert 20.0 in metrics.latencies
    
    def test_record_latency_limit(self):
        """Test that latency list is limited to 1000 samples."""
        metrics = ConnectionMetrics()
        
        for i in range(1100):
            metrics.record_latency(float(i))
        
        assert len(metrics.latencies) == 1000
        assert metrics.latencies[0] == 100.0
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        metrics = ConnectionMetrics()
        metrics.total_requests = 50
        metrics.failed_requests = 5
        metrics.reconnect_count = 2
        
        result = metrics.to_dict()
        
        assert result["total_requests"] == 50
        assert result["failed_requests"] == 5
        assert result["reconnect_count"] == 2
        assert result["success_rate"] == 0.9


class TestJSONFormatter:
    """Tests for JSONFormatter."""
    
    def test_basic_format(self):
        """Test basic log formatting."""
        formatter = JSONFormatter()
        
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None
        )
        
        result = formatter.format(record)
        data = json.loads(result)
        
        assert data["level"] == "INFO"
        assert data["logger"] == "test_logger"
        assert data["message"] == "Test message"
        assert "timestamp" in data
    
    def test_format_with_extra_data(self):
        """Test formatting with extra data."""
        formatter = JSONFormatter()
        
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None
        )
        record.connector_state = "connected"
        record.latency_ms = 50.5
        
        result = formatter.format(record)
        data = json.loads(result)
        
        assert data["connector_state"] == "connected"
        assert data["latency_ms"] == 50.5
    
    def test_format_with_exception(self):
        """Test formatting with exception info."""
        formatter = JSONFormatter()
        
        try:
            raise ValueError("Test error")
        except ValueError:
            import sys
            exc_info = sys.exc_info()
        
        record = logging.LogRecord(
            name="test_logger",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="Error occurred",
            args=(),
            exc_info=exc_info
        )
        
        result = formatter.format(record)
        data = json.loads(result)
        
        assert "exception" in data
        assert "ValueError" in data["exception"]


class TestSetupJsonLogger:
    """Tests for setup_json_logger function."""
    
    def test_creates_logger(self):
        """Test that logger is created."""
        logger = setup_json_logger("test_logger_1")
        
        assert logger is not None
        assert logger.name == "test_logger_1"
    
    def test_sets_level(self):
        """Test that log level is set."""
        logger = setup_json_logger("test_logger_2", level=logging.DEBUG)
        
        assert logger.level == logging.DEBUG
    
    def test_adds_handler(self):
        """Test that handler is added."""
        logger = setup_json_logger("test_logger_3")
        
        assert len(logger.handlers) > 0
    
    def test_handler_has_json_formatter(self):
        """Test that handler uses JSON formatter."""
        logger = setup_json_logger("test_logger_4")
        
        handler = logger.handlers[0]
        assert isinstance(handler.formatter, JSONFormatter)


class ConcreteConnector(BaseConnector):
    """Concrete implementation for testing."""
    
    def __init__(self, config=None):
        super().__init__(config)
        self._connected = False
    
    async def connect(self) -> bool:
        self._connected = True
        self.state = ConnectorState.CONNECTED
        return True
    
    async def disconnect(self) -> None:
        self._connected = False
        self.state = ConnectorState.DISCONNECTED
    
    async def reconnect(self) -> bool:
        return await self.connect()
    
    async def health_check(self) -> bool:
        return self._connected


class TestBaseConnector:
    """Tests for BaseConnector."""
    
    def test_initialization(self):
        """Test connector initialization."""
        connector = ConcreteConnector()
        
        assert connector.state == ConnectorState.DISCONNECTED
        assert connector.is_connected is False
        assert connector.config is not None
    
    def test_initialization_with_config(self):
        """Test initialization with custom config."""
        config = ConnectorConfig(port=7496, client_id=5)
        connector = ConcreteConnector(config)
        
        assert connector.config.port == 7496
        assert connector.config.client_id == 5
    
    @pytest.mark.asyncio
    async def test_connect(self):
        """Test connection."""
        connector = ConcreteConnector()
        
        result = await connector.connect()
        
        assert result is True
        assert connector.is_connected is True
        assert connector.state == ConnectorState.CONNECTED
    
    @pytest.mark.asyncio
    async def test_disconnect(self):
        """Test disconnection."""
        connector = ConcreteConnector()
        await connector.connect()
        
        await connector.disconnect()
        
        assert connector.is_connected is False
        assert connector.state == ConnectorState.DISCONNECTED
    
    @pytest.mark.asyncio
    async def test_health_check(self):
        """Test health check."""
        connector = ConcreteConnector()
        
        assert await connector.health_check() is False
        
        await connector.connect()
        
        assert await connector.health_check() is True
    
    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test async context manager."""
        connector = ConcreteConnector()
        
        async with connector:
            assert connector.is_connected is True
        
        assert connector.is_connected is False
    
    def test_state_change_callback(self):
        """Test state change callback."""
        connector = ConcreteConnector()
        states_received = []
        
        def callback(state):
            states_received.append(state)
        
        connector.on_state_change(callback)
        connector.state = ConnectorState.CONNECTING
        connector.state = ConnectorState.CONNECTED
        
        assert ConnectorState.CONNECTING in states_received
        assert ConnectorState.CONNECTED in states_received
    
    def test_error_callback(self):
        """Test error callback."""
        connector = ConcreteConnector()
        errors_received = []
        
        def callback(error):
            errors_received.append(error)
        
        connector.on_error(callback)
        
        error = DataConnectorError("Test error")
        connector._notify_error(error)
        
        assert len(errors_received) == 1
        assert errors_received[0].message == "Test error"
    
    def test_metrics_property(self):
        """Test metrics property."""
        connector = ConcreteConnector()
        
        metrics = connector.metrics
        
        assert isinstance(metrics, ConnectionMetrics)
    
    def test_state_callback_error_handling(self):
        """Test that callback errors don't break state changes."""
        connector = ConcreteConnector()
        
        def bad_callback(state):
            raise ValueError("Callback error")
        
        connector.on_state_change(bad_callback)
        
        connector.state = ConnectorState.CONNECTED
        
        assert connector.state == ConnectorState.CONNECTED
