"""
Tests for data_connector ib_connector module.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.data_connector.ib_connector import (
    IBConnector,
    IBConnectorConfig,
    MockIBClient,
)
from src.data_connector.base import ConnectorState
from src.data_connector.exceptions import (
    ConnectionError,
    ReconnectionError,
    IBError,
    DataConnectorError,
)


class TestIBConnectorConfig:
    """Tests for IBConnectorConfig."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = IBConnectorConfig()
        
        assert config.host == "127.0.0.1"
        assert config.port == 7497
        assert config.client_id == 1
        assert config.readonly is False
        assert config.account is None
    
    def test_custom_config(self):
        """Test custom configuration."""
        config = IBConnectorConfig(
            host="192.168.1.1",
            port=7496,
            client_id=5,
            readonly=True,
            account="DU12345"
        )
        
        assert config.host == "192.168.1.1"
        assert config.port == 7496
        assert config.client_id == 5
        assert config.readonly is True
        assert config.account == "DU12345"
    
    def test_from_env(self):
        """Test configuration from environment variables."""
        with patch.dict('os.environ', {
            'IB_HOST': '10.0.0.1',
            'IB_PORT': '7496',
            'IB_CLIENT_ID': '10',
            'IB_READONLY': 'true',
            'IB_ACCOUNT': 'DU99999',
        }):
            config = IBConnectorConfig.from_env()
            
            assert config.host == '10.0.0.1'
            assert config.port == 7496
            assert config.client_id == 10
            assert config.readonly is True
            assert config.account == 'DU99999'


class TestMockIBClient:
    """Tests for MockIBClient."""
    
    @pytest.mark.asyncio
    async def test_connect(self):
        """Test mock connection."""
        client = MockIBClient()
        
        assert client.isConnected() is False
        
        await client.connect()
        
        assert client.isConnected() is True
    
    def test_disconnect(self):
        """Test mock disconnection."""
        client = MockIBClient()
        client._connected = True
        
        client.disconnect()
        
        assert client.isConnected() is False
    
    @pytest.mark.asyncio
    async def test_get_ticker(self):
        """Test mock ticker data."""
        client = MockIBClient()
        
        ticker = await client.get_ticker("AAPL")
        
        assert ticker["symbol"] == "AAPL"
        assert "bid" in ticker
        assert "ask" in ticker
        assert "last" in ticker
        assert "volume" in ticker
    
    @pytest.mark.asyncio
    async def test_get_historical_data(self):
        """Test mock historical data."""
        client = MockIBClient()
        
        bars = await client.get_historical_data("AAPL", "1 D", "1 min")
        
        assert len(bars) == 100
        assert "open" in bars[0]
        assert "high" in bars[0]
        assert "low" in bars[0]
        assert "close" in bars[0]
        assert "volume" in bars[0]
    
    @pytest.mark.asyncio
    async def test_get_account_summary(self):
        """Test mock account summary."""
        client = MockIBClient()
        
        summary = await client.get_account_summary()
        
        assert "NetLiquidation" in summary
        assert "TotalCashValue" in summary
        assert "BuyingPower" in summary
    
    @pytest.mark.asyncio
    async def test_get_positions(self):
        """Test mock positions."""
        client = MockIBClient()
        
        positions = await client.get_positions()
        
        assert len(positions) == 1
        assert positions[0]["symbol"] == "AAPL"
        assert "position" in positions[0]
        assert "avg_cost" in positions[0]
    
    @pytest.mark.asyncio
    async def test_place_order(self):
        """Test mock order placement."""
        client = MockIBClient()
        
        order = await client.place_order(
            symbol="AAPL",
            action="BUY",
            quantity=100,
            order_type="MKT",
            limit_price=None,
            stop_price=None
        )
        
        assert order["symbol"] == "AAPL"
        assert order["action"] == "BUY"
        assert order["quantity"] == 100
        assert order["status"] == "Submitted"
        assert "order_id" in order
    
    @pytest.mark.asyncio
    async def test_cancel_order(self):
        """Test mock order cancellation."""
        client = MockIBClient()
        
        order = await client.place_order("AAPL", "BUY", 100, "MKT", None, None)
        order_id = order["order_id"]
        
        result = await client.cancel_order(order_id)
        
        assert result is True
        assert client._orders[order_id]["status"] == "Cancelled"
    
    @pytest.mark.asyncio
    async def test_cancel_nonexistent_order(self):
        """Test cancelling non-existent order."""
        client = MockIBClient()
        
        result = await client.cancel_order(99999)
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_get_open_orders(self):
        """Test mock open orders."""
        client = MockIBClient()
        
        await client.place_order("AAPL", "BUY", 100, "MKT", None, None)
        await client.place_order("MSFT", "SELL", 50, "LMT", 300.0, None)
        
        orders = await client.get_open_orders()
        
        assert len(orders) == 2


class TestIBConnector:
    """Tests for IBConnector."""
    
    @pytest.fixture
    def mock_client(self):
        """Create a mock IB client."""
        return MockIBClient()
    
    @pytest.fixture
    def connector(self, mock_client):
        """Create a connector with mock client."""
        config = IBConnectorConfig(timeout=1.0)
        return IBConnector(config=config, ib_client=mock_client)
    
    def test_initialization(self):
        """Test connector initialization."""
        connector = IBConnector()
        
        assert connector.state == ConnectorState.DISCONNECTED
        assert connector.is_connected is False
    
    def test_initialization_with_config(self):
        """Test initialization with custom config."""
        config = IBConnectorConfig(port=7496, client_id=5)
        connector = IBConnector(config=config)
        
        assert connector._ib_config.port == 7496
        assert connector._ib_config.client_id == 5
    
    @pytest.mark.asyncio
    async def test_connect_with_mock(self, connector, mock_client):
        """Test connection with mock client."""
        await mock_client.connect()
        
        result = await connector.connect()
        
        assert result is True
        assert connector.is_connected is True
        assert connector.state == ConnectorState.CONNECTED
        
        await connector.disconnect()
    
    @pytest.mark.asyncio
    async def test_disconnect(self, connector, mock_client):
        """Test disconnection."""
        await mock_client.connect()
        await connector.connect()
        
        await connector.disconnect()
        
        assert connector.is_connected is False
        assert connector.state == ConnectorState.DISCONNECTED
    
    @pytest.mark.asyncio
    async def test_health_check(self, connector, mock_client):
        """Test health check."""
        assert await connector.health_check() is False
        
        await mock_client.connect()
        await connector.connect()
        
        assert await connector.health_check() is True
        
        await connector.disconnect()
    
    @pytest.mark.asyncio
    async def test_get_ticker(self, connector, mock_client):
        """Test getting ticker data."""
        await mock_client.connect()
        await connector.connect()
        
        ticker = await connector.get_ticker("AAPL")
        
        assert ticker["symbol"] == "AAPL"
        assert "bid" in ticker
        assert "ask" in ticker
        
        await connector.disconnect()
    
    @pytest.mark.asyncio
    async def test_get_historical_data(self, connector, mock_client):
        """Test getting historical data."""
        await mock_client.connect()
        await connector.connect()
        
        bars = await connector.get_historical_data("AAPL")
        
        assert len(bars) > 0
        assert "open" in bars[0]
        assert "close" in bars[0]
        
        await connector.disconnect()
    
    @pytest.mark.asyncio
    async def test_get_account_summary(self, connector, mock_client):
        """Test getting account summary."""
        await mock_client.connect()
        await connector.connect()
        
        summary = await connector.get_account_summary()
        
        assert "NetLiquidation" in summary
        
        await connector.disconnect()
    
    @pytest.mark.asyncio
    async def test_get_positions(self, connector, mock_client):
        """Test getting positions."""
        await mock_client.connect()
        await connector.connect()
        
        positions = await connector.get_positions()
        
        assert isinstance(positions, list)
        
        await connector.disconnect()
    
    @pytest.mark.asyncio
    async def test_place_order(self, connector, mock_client):
        """Test placing an order."""
        await mock_client.connect()
        await connector.connect()
        
        order = await connector.place_order(
            symbol="AAPL",
            action="BUY",
            quantity=100,
            order_type="MKT"
        )
        
        assert order["symbol"] == "AAPL"
        assert order["action"] == "BUY"
        assert order["quantity"] == 100
        
        await connector.disconnect()
    
    @pytest.mark.asyncio
    async def test_place_order_readonly(self, mock_client):
        """Test that orders are blocked in readonly mode."""
        config = IBConnectorConfig(readonly=True, timeout=1.0)
        connector = IBConnector(config=config, ib_client=mock_client)
        
        await mock_client.connect()
        await connector.connect()
        
        with pytest.raises(DataConnectorError, match="readonly"):
            await connector.place_order("AAPL", "BUY", 100)
        
        await connector.disconnect()
    
    @pytest.mark.asyncio
    async def test_cancel_order(self, connector, mock_client):
        """Test cancelling an order."""
        await mock_client.connect()
        await connector.connect()
        
        order = await connector.place_order("AAPL", "BUY", 100)
        order_id = order["order_id"]
        
        result = await connector.cancel_order(order_id)
        
        assert result is True
        
        await connector.disconnect()
    
    @pytest.mark.asyncio
    async def test_get_open_orders(self, connector, mock_client):
        """Test getting open orders."""
        await mock_client.connect()
        await connector.connect()
        
        await connector.place_order("AAPL", "BUY", 100)
        
        orders = await connector.get_open_orders()
        
        assert len(orders) >= 1
        
        await connector.disconnect()
    
    @pytest.mark.asyncio
    async def test_get_status(self, connector, mock_client):
        """Test getting connector status."""
        await mock_client.connect()
        await connector.connect()
        
        status = connector.get_status()
        
        assert status["state"] == "connected"
        assert status["is_connected"] is True
        assert "config" in status
        assert "metrics" in status
        assert "rate_limiter" in status
        assert "circuit_breaker" in status
        
        await connector.disconnect()
    
    @pytest.mark.asyncio
    async def test_context_manager(self, mock_client):
        """Test async context manager."""
        config = IBConnectorConfig(timeout=1.0)
        connector = IBConnector(config=config, ib_client=mock_client)
        await mock_client.connect()
        
        async with connector:
            assert connector.is_connected is True
        
        assert connector.is_connected is False
    
    @pytest.mark.asyncio
    async def test_not_connected_error(self, connector):
        """Test that operations fail when not connected."""
        with pytest.raises(ConnectionError, match="Not connected"):
            await connector.get_ticker("AAPL")


class TestIBConnectorReconnection:
    """Tests for IBConnector reconnection logic."""
    
    @pytest.mark.asyncio
    async def test_reconnect_success(self):
        """Test successful reconnection."""
        mock_client = MockIBClient()
        config = IBConnectorConfig(
            timeout=1.0,
            max_reconnect_attempts=3,
            reconnect_delay=0.01
        )
        connector = IBConnector(config=config, ib_client=mock_client)
        
        await mock_client.connect()
        await connector.connect()
        
        mock_client.disconnect()
        connector.state = ConnectorState.DISCONNECTED
        
        result = await connector.reconnect()
        
        assert result is True
        assert connector.is_connected is True
        
        await connector.disconnect()
    
    @pytest.mark.asyncio
    async def test_reconnect_increments_metrics(self):
        """Test that reconnection increments metrics counter."""
        mock_client = MockIBClient()
        config = IBConnectorConfig(
            timeout=1.0,
            max_reconnect_attempts=3,
            reconnect_delay=0.01
        )
        connector = IBConnector(config=config, ib_client=mock_client)
        
        await mock_client.connect()
        
        initial_count = connector._metrics.reconnect_count
        
        await connector.reconnect()
        
        assert connector._metrics.reconnect_count > initial_count
        
        await connector.disconnect()


class TestIBConnectorErrorHandling:
    """Tests for IBConnector error handling."""
    
    def test_ib_error_handler_info(self):
        """Test handling of informational IB errors."""
        mock_client = MockIBClient()
        config = IBConnectorConfig(timeout=1.0)
        connector = IBConnector(config=config, ib_client=mock_client)
        
        connector._on_ib_error(
            req_id=-1,
            error_code=2104,
            error_string="Market data farm connection is OK"
        )
    
    @pytest.mark.asyncio
    async def test_ib_error_handler_recoverable(self):
        """Test handling of recoverable IB errors."""
        mock_client = MockIBClient()
        config = IBConnectorConfig(timeout=1.0)
        connector = IBConnector(config=config, ib_client=mock_client)
        
        errors_received = []
        connector.on_error(lambda e: errors_received.append(e))
        
        connector._on_ib_error(
            req_id=-1,
            error_code=1100,
            error_string="Connectivity lost"
        )
        
        assert len(errors_received) == 1
        assert isinstance(errors_received[0], IBError)
    
    def test_ib_error_handler_fatal(self):
        """Test handling of fatal IB errors."""
        mock_client = MockIBClient()
        config = IBConnectorConfig(timeout=1.0)
        connector = IBConnector(config=config, ib_client=mock_client)
        
        connector._on_ib_error(
            req_id=-1,
            error_code=502,
            error_string="Couldn't connect to TWS"
        )
        
        assert connector._circuit_breaker.failure_count > 0


class TestIBConnectorRateLimiting:
    """Tests for IBConnector rate limiting."""
    
    @pytest.mark.asyncio
    async def test_rate_limiter_integration(self):
        """Test that rate limiter is used."""
        mock_client = MockIBClient()
        config = IBConnectorConfig(timeout=1.0, rate_limit=100)
        connector = IBConnector(config=config, ib_client=mock_client)
        
        await mock_client.connect()
        await connector.connect()
        
        for _ in range(5):
            await connector.get_ticker("AAPL")
        
        metrics = connector._rate_limiter.get_metrics()
        assert metrics["total_acquired"] >= 5
        
        await connector.disconnect()


class TestIBConnectorCircuitBreaker:
    """Tests for IBConnector circuit breaker."""
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_integration(self):
        """Test that circuit breaker is used."""
        mock_client = MockIBClient()
        config = IBConnectorConfig(
            timeout=1.0,
            circuit_breaker_threshold=5
        )
        connector = IBConnector(config=config, ib_client=mock_client)
        
        await mock_client.connect()
        await connector.connect()
        
        await connector.get_ticker("AAPL")
        
        metrics = connector._circuit_breaker.get_metrics()
        assert metrics["total_successes"] >= 1
        
        await connector.disconnect()


class TestIBConnectorLatencyTracking:
    """Tests for IBConnector latency tracking."""
    
    @pytest.mark.asyncio
    async def test_latency_recorded(self):
        """Test that latency is recorded."""
        mock_client = MockIBClient()
        config = IBConnectorConfig(timeout=1.0)
        connector = IBConnector(config=config, ib_client=mock_client)
        
        await mock_client.connect()
        await connector.connect()
        
        await connector.get_ticker("AAPL")
        
        assert len(connector._metrics.latencies) > 0
        
        await connector.disconnect()
    
    @pytest.mark.asyncio
    async def test_p95_latency_target(self):
        """Test p95 latency tracking."""
        mock_client = MockIBClient()
        config = IBConnectorConfig(timeout=1.0)
        connector = IBConnector(config=config, ib_client=mock_client)
        
        await mock_client.connect()
        await connector.connect()
        
        for _ in range(10):
            await connector.get_ticker("AAPL")
        
        p95 = connector._metrics.p95_latency_ms
        assert p95 < 100
        
        await connector.disconnect()
