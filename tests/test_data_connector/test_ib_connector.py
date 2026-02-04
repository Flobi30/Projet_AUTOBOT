"""Tests for Interactive Brokers Connector module."""

import asyncio
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock, patch

import sys
sys.path.insert(0, "/home/ubuntu/Projet_AUTOBOT/src")

from data_connector.ib_connector import (
    IBConfig,
    IBContract,
    IBConnector,
    IBTickType,
    create_ib_connector,
)
from data_connector.base import ConnectionStatus, EventType, MarketData


class TestIBConfig:
    """Tests for IBConfig dataclass."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = IBConfig()
        
        assert config.host == "127.0.0.1"
        assert config.port == 7497
        assert config.client_id == 1
        assert config.auto_reconnect is True
        assert config.read_only is True
    
    def test_custom_config(self):
        """Test custom configuration."""
        config = IBConfig(
            host="192.168.1.100",
            port=4002,
            client_id=5,
            read_only=False,
        )
        
        assert config.host == "192.168.1.100"
        assert config.port == 4002
        assert config.client_id == 5
        assert config.read_only is False
    
    def test_config_with_cache_settings(self):
        """Test configuration with cache settings."""
        config = IBConfig(
            use_cache=True,
            cache_ttl=5.0,
        )
        
        assert config.use_cache is True
        assert config.cache_ttl == 5.0
    
    def test_config_with_rate_limiter_settings(self):
        """Test configuration with rate limiter settings."""
        config = IBConfig(
            use_rate_limiter=True,
            requests_per_second=25.0,
        )
        
        assert config.use_rate_limiter is True
        assert config.requests_per_second == 25.0


class TestIBContract:
    """Tests for IBContract dataclass."""
    
    def test_default_contract(self):
        """Test default contract values."""
        contract = IBContract(symbol="AAPL")
        
        assert contract.symbol == "AAPL"
        assert contract.sec_type == "STK"
        assert contract.exchange == "SMART"
        assert contract.currency == "USD"
    
    def test_forex_contract(self):
        """Test forex contract."""
        contract = IBContract(
            symbol="EUR.USD",
            sec_type="CASH",
            exchange="IDEALPRO",
            currency="USD",
        )
        
        assert contract.symbol == "EUR.USD"
        assert contract.sec_type == "CASH"
        assert contract.exchange == "IDEALPRO"
    
    def test_futures_contract(self):
        """Test futures contract."""
        contract = IBContract(
            symbol="ES",
            sec_type="FUT",
            exchange="GLOBEX",
            expiry="202312",
        )
        
        assert contract.symbol == "ES"
        assert contract.sec_type == "FUT"
        assert contract.exchange == "GLOBEX"
        assert contract.expiry == "202312"
    
    def test_contract_to_dict(self):
        """Test contract to_dict conversion."""
        contract = IBContract(
            symbol="AAPL",
            sec_type="STK",
            exchange="NASDAQ",
        )
        
        result = contract.to_dict()
        
        assert result["symbol"] == "AAPL"
        assert result["secType"] == "STK"
        assert result["exchange"] == "NASDAQ"


class TestIBConnector:
    """Tests for IBConnector class."""
    
    def test_connector_creation(self):
        """Test connector creation."""
        connector = IBConnector()
        
        assert connector.name == "interactive_brokers"
        assert connector.status == ConnectionStatus.DISCONNECTED
    
    def test_connector_with_config(self):
        """Test connector with custom config."""
        config = IBConfig(
            host="192.168.1.100",
            port=4002,
        )
        connector = IBConnector(config=config)
        
        assert connector.config.host == "192.168.1.100"
        assert connector.config.port == 4002
    
    @pytest.mark.asyncio
    async def test_connect(self):
        """Test connecting to TWS."""
        connector = IBConnector()
        
        result = await connector.connect()
        
        assert result is True
        assert connector.is_connected
        assert connector.status == ConnectionStatus.CONNECTED
    
    @pytest.mark.asyncio
    async def test_disconnect(self):
        """Test disconnecting from TWS."""
        connector = IBConnector()
        await connector.connect()
        
        await connector.disconnect()
        
        assert not connector.is_connected
        assert connector.status == ConnectionStatus.DISCONNECTED
    
    @pytest.mark.asyncio
    async def test_subscribe(self):
        """Test subscribing to market data."""
        connector = IBConnector()
        await connector.connect()
        
        result = await connector.subscribe("AAPL")
        
        assert result is True
        assert "AAPL" in connector.subscriptions
    
    @pytest.mark.asyncio
    async def test_subscribe_not_connected(self):
        """Test subscribing when not connected."""
        connector = IBConnector()
        
        result = await connector.subscribe("AAPL")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_unsubscribe(self):
        """Test unsubscribing from market data."""
        connector = IBConnector()
        await connector.connect()
        await connector.subscribe("AAPL")
        
        result = await connector.unsubscribe("AAPL")
        
        assert result is True
        assert "AAPL" not in connector.subscriptions
    
    @pytest.mark.asyncio
    async def test_get_market_data(self):
        """Test getting market data."""
        connector = IBConnector()
        await connector.connect()
        await connector.subscribe("AAPL")
        
        data = await connector.get_market_data("AAPL")
        
        assert data is not None
        assert data.symbol == "AAPL"
        assert data.source == "interactive_brokers"
    
    @pytest.mark.asyncio
    async def test_get_market_data_auto_subscribe(self):
        """Test getting market data with auto-subscribe."""
        connector = IBConnector()
        await connector.connect()
        
        data = await connector.get_market_data("GOOGL")
        
        assert data is not None
        assert data.symbol == "GOOGL"
    
    @pytest.mark.asyncio
    async def test_get_historical_data(self):
        """Test getting historical data."""
        connector = IBConnector()
        await connector.connect()
        
        start = datetime.utcnow() - timedelta(hours=1)
        end = datetime.utcnow()
        
        data = await connector.get_historical_data("AAPL", start, end, "1m")
        
        assert len(data) > 0
        assert all(d.symbol == "AAPL" for d in data)
        assert all(d.source == "interactive_brokers" for d in data)
    
    @pytest.mark.asyncio
    async def test_get_historical_data_not_connected(self):
        """Test getting historical data when not connected."""
        connector = IBConnector()
        
        start = datetime.utcnow() - timedelta(hours=1)
        end = datetime.utcnow()
        
        data = await connector.get_historical_data("AAPL", start, end)
        
        assert len(data) == 0
    
    @pytest.mark.asyncio
    async def test_get_historical_data_intervals(self):
        """Test getting historical data with different intervals."""
        connector = IBConnector()
        await connector.connect()
        
        start = datetime.utcnow() - timedelta(days=1)
        end = datetime.utcnow()
        
        for interval in ["1m", "5m", "15m", "1h", "1d"]:
            data = await connector.get_historical_data("AAPL", start, end, interval)
            assert isinstance(data, list)
    
    def test_parse_symbol_stock(self):
        """Test parsing stock symbol."""
        connector = IBConnector()
        
        contract = connector._parse_symbol("AAPL")
        
        assert contract.symbol == "AAPL"
        assert contract.sec_type == "STK"
        assert contract.exchange == "SMART"
    
    def test_parse_symbol_with_exchange(self):
        """Test parsing symbol with exchange."""
        connector = IBConnector()
        
        contract = connector._parse_symbol("AAPL:NASDAQ")
        
        assert contract.symbol == "AAPL"
        assert contract.exchange == "NASDAQ"
    
    def test_parse_symbol_forex(self):
        """Test parsing forex symbol."""
        connector = IBConnector()
        
        contract = connector._parse_symbol("EUR.USD")
        
        assert contract.symbol == "EUR.USD"
        assert contract.sec_type == "CASH"
        assert contract.exchange == "IDEALPRO"
    
    def test_parse_symbol_futures(self):
        """Test parsing futures symbol."""
        connector = IBConnector()
        
        contract = connector._parse_symbol("ES:GLOBEX:FUT:202312")
        
        assert contract.symbol == "ES"
        assert contract.exchange == "GLOBEX"
        assert contract.sec_type == "FUT"
        assert contract.expiry == "202312"
    
    def test_get_next_req_id(self):
        """Test request ID generation."""
        connector = IBConnector()
        
        id1 = connector._get_next_req_id()
        id2 = connector._get_next_req_id()
        id3 = connector._get_next_req_id()
        
        assert id1 == 1
        assert id2 == 2
        assert id3 == 3
    
    def test_handle_tick_price(self):
        """Test handling tick price updates."""
        connector = IBConnector()
        connector._market_data["AAPL"] = MarketData(
            symbol="AAPL",
            timestamp=datetime.utcnow(),
            source="interactive_brokers",
        )
        connector._req_id_to_symbol[1] = "AAPL"
        
        connector._handle_tick_price(1, IBTickType.LAST, 150.0)
        
        assert connector._market_data["AAPL"].last == 150.0
    
    def test_handle_tick_size(self):
        """Test handling tick size updates."""
        connector = IBConnector()
        connector._market_data["AAPL"] = MarketData(
            symbol="AAPL",
            timestamp=datetime.utcnow(),
            source="interactive_brokers",
        )
        connector._req_id_to_symbol[1] = "AAPL"
        
        connector._handle_tick_size(1, IBTickType.VOLUME, 1000000)
        
        assert connector._market_data["AAPL"].volume == 1000000.0
    
    @pytest.mark.asyncio
    async def test_request_contract_details(self):
        """Test requesting contract details."""
        connector = IBConnector()
        await connector.connect()
        
        details = await connector.request_contract_details("AAPL")
        
        assert details is not None
        assert details["symbol"] == "AAPL"
    
    @pytest.mark.asyncio
    async def test_request_contract_details_not_connected(self):
        """Test requesting contract details when not connected."""
        connector = IBConnector()
        
        details = await connector.request_contract_details("AAPL")
        
        assert details is None
    
    def test_get_stats(self):
        """Test getting connector statistics."""
        connector = IBConnector()
        
        stats = connector.get_stats()
        
        assert stats["name"] == "interactive_brokers"
        assert stats["host"] == "127.0.0.1"
        assert stats["port"] == 7497
        assert "rate_limiter" in stats
        assert "cache" in stats
    
    @pytest.mark.asyncio
    async def test_multiple_subscriptions(self):
        """Test multiple subscriptions."""
        connector = IBConnector()
        await connector.connect()
        
        symbols = ["AAPL", "GOOGL", "MSFT", "AMZN"]
        
        for symbol in symbols:
            result = await connector.subscribe(symbol)
            assert result is True
        
        assert len(connector.subscriptions) == 4
        for symbol in symbols:
            assert symbol in connector.subscriptions
    
    @pytest.mark.asyncio
    async def test_event_emission(self):
        """Test event emission on connect."""
        connector = IBConnector()
        callback = MagicMock()
        
        connector.events.on(EventType.CONNECTED, callback)
        
        await connector.connect()
        
        # May emit multiple CONNECTED events during connection process
        assert callback.call_count >= 1
    
    @pytest.mark.asyncio
    async def test_subscription_events(self):
        """Test subscription event emission."""
        connector = IBConnector()
        await connector.connect()
        
        add_callback = MagicMock()
        remove_callback = MagicMock()
        
        connector.events.on(EventType.SUBSCRIPTION_ADDED, add_callback)
        connector.events.on(EventType.SUBSCRIPTION_REMOVED, remove_callback)
        
        await connector.subscribe("AAPL")
        await connector.unsubscribe("AAPL")
        
        add_callback.assert_called_once()
        remove_callback.assert_called_once()


class TestCreateIBConnector:
    """Tests for create_ib_connector factory function."""
    
    def test_create_default(self):
        """Test creating connector with defaults."""
        connector = create_ib_connector()
        
        assert connector.config.host == "127.0.0.1"
        assert connector.config.port == 7497
        assert connector.config.client_id == 1
    
    def test_create_custom(self):
        """Test creating connector with custom settings."""
        connector = create_ib_connector(
            host="192.168.1.100",
            port=4002,
            client_id=10,
            read_only=False,
        )
        
        assert connector.config.host == "192.168.1.100"
        assert connector.config.port == 4002
        assert connector.config.client_id == 10
        assert connector.config.read_only is False
    
    def test_create_paper_trading(self):
        """Test creating connector for paper trading."""
        connector = create_ib_connector(port=7497)
        
        assert connector.config.port == 7497
    
    def test_create_live_trading(self):
        """Test creating connector for live trading."""
        connector = create_ib_connector(port=7496)
        
        assert connector.config.port == 7496
    
    def test_create_gateway(self):
        """Test creating connector for IB Gateway."""
        connector = create_ib_connector(port=4002)
        
        assert connector.config.port == 4002


class TestIBTickType:
    """Tests for IBTickType constants."""
    
    def test_tick_types_exist(self):
        """Test that all expected tick types exist."""
        expected_types = [
            "BID", "ASK", "LAST", "HIGH", "LOW", "VOLUME",
            "CLOSE", "OPEN", "BID_SIZE", "ASK_SIZE", "LAST_SIZE",
        ]
        
        for tick_type in expected_types:
            assert hasattr(IBTickType, tick_type)
    
    def test_tick_type_values(self):
        """Test tick type values."""
        assert IBTickType.BID == 1
        assert IBTickType.ASK == 2
        assert IBTickType.LAST == 4
        assert IBTickType.VOLUME == 8
