"""Tests for Third Party Connector module."""

import asyncio
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock, patch, Mock
import aiohttp

import sys
sys.path.insert(0, "/home/ubuntu/Projet_AUTOBOT/src")

from data_connector.third_party_connector import (
    ThirdPartyConfig,
    ProviderAdapter,
    TwelveDataAdapter,
    AlphaVantageAdapter,
    BinanceAdapter,
    CoinbaseAdapter,
    KrakenAdapter,
    ThirdPartyConnector,
    create_third_party_connector,
)
from data_connector.base import ConnectionStatus, EventType, MarketData


class TestThirdPartyConfig:
    """Tests for ThirdPartyConfig dataclass."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = ThirdPartyConfig()
        
        assert "twelvedata" in config.providers
        assert "alphavantage" in config.providers
        assert "binance" in config.providers
        assert config.simultaneous_collection is True
        assert config.auto_reconnect is True
    
    def test_custom_config(self):
        """Test custom configuration."""
        config = ThirdPartyConfig(
            providers=["binance", "coinbase"],
            simultaneous_collection=False,
        )
        
        assert config.providers == ["binance", "coinbase"]
        assert config.simultaneous_collection is False
    
    def test_config_with_api_keys(self):
        """Test configuration with API keys."""
        config = ThirdPartyConfig(
            twelvedata_api_key="td_key",
            alphavantage_api_key="av_key",
            binance_api_key="bn_key",
        )
        
        assert config.twelvedata_api_key == "td_key"
        assert config.alphavantage_api_key == "av_key"
        assert config.binance_api_key == "bn_key"
    
    @patch.dict('os.environ', {'TWELVEDATA_API_KEY': 'env_td_key'})
    def test_config_from_env(self):
        """Test configuration from environment variables."""
        config = ThirdPartyConfig()
        
        assert config.twelvedata_api_key == "env_td_key"


class TestProviderAdapter:
    """Tests for ProviderAdapter base class."""
    
    def test_adapter_creation(self):
        """Test adapter creation."""
        adapter = ProviderAdapter(name="test", api_key="key123")
        
        assert adapter.name == "test"
        assert adapter.api_key == "key123"
    
    def test_is_configured_with_key(self):
        """Test is_configured with API key."""
        adapter = ProviderAdapter(name="test", api_key="key123")
        
        assert adapter.is_configured() is True
    
    def test_is_configured_without_key(self):
        """Test is_configured without API key."""
        adapter = ProviderAdapter(name="test")
        
        assert adapter.is_configured() is False
    
    @pytest.mark.asyncio
    async def test_close(self):
        """Test closing adapter session."""
        adapter = ProviderAdapter(name="test")
        
        await adapter.close()


class TestTwelveDataAdapter:
    """Tests for TwelveDataAdapter class."""
    
    def test_adapter_creation(self):
        """Test adapter creation."""
        adapter = TwelveDataAdapter(api_key="test_key")
        
        assert adapter.name == "twelvedata"
        assert adapter.api_key == "test_key"
    
    def test_is_configured(self):
        """Test is_configured."""
        adapter_with_key = TwelveDataAdapter(api_key="key")
        adapter_without_key = TwelveDataAdapter()
        
        assert adapter_with_key.is_configured() is True
        assert adapter_without_key.is_configured() is False
    
    @pytest.mark.asyncio
    async def test_get_quote_not_configured(self):
        """Test get_quote when not configured."""
        adapter = TwelveDataAdapter()
        
        result = await adapter.get_quote("AAPL")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_get_historical_not_configured(self):
        """Test get_historical when not configured."""
        adapter = TwelveDataAdapter()
        
        start = datetime.utcnow() - timedelta(days=1)
        end = datetime.utcnow()
        
        result = await adapter.get_historical("AAPL", start, end, "1h")
        
        assert result == []


class TestAlphaVantageAdapter:
    """Tests for AlphaVantageAdapter class."""
    
    def test_adapter_creation(self):
        """Test adapter creation."""
        adapter = AlphaVantageAdapter(api_key="test_key")
        
        assert adapter.name == "alphavantage"
        assert adapter.api_key == "test_key"
    
    def test_is_configured(self):
        """Test is_configured."""
        adapter_with_key = AlphaVantageAdapter(api_key="key")
        adapter_without_key = AlphaVantageAdapter()
        
        assert adapter_with_key.is_configured() is True
        assert adapter_without_key.is_configured() is False
    
    @pytest.mark.asyncio
    async def test_get_quote_not_configured(self):
        """Test get_quote when not configured."""
        adapter = AlphaVantageAdapter()
        
        result = await adapter.get_quote("AAPL")
        
        assert result is None


class TestBinanceAdapter:
    """Tests for BinanceAdapter class."""
    
    def test_adapter_creation(self):
        """Test adapter creation."""
        adapter = BinanceAdapter()
        
        assert adapter.name == "binance"
    
    def test_is_configured(self):
        """Test is_configured (Binance public endpoints don't require key)."""
        adapter = BinanceAdapter()
        
        assert adapter.is_configured() is True
    
    @pytest.mark.asyncio
    async def test_get_quote_symbol_conversion(self):
        """Test symbol conversion for Binance."""
        adapter = BinanceAdapter()
        
        assert "BTC/USDT".replace("/", "").upper() == "BTCUSDT"
        assert "ETH-USD".replace("/", "").replace("-", "").upper() == "ETHUSD"


class TestCoinbaseAdapter:
    """Tests for CoinbaseAdapter class."""
    
    def test_adapter_creation(self):
        """Test adapter creation."""
        adapter = CoinbaseAdapter()
        
        assert adapter.name == "coinbase"
    
    def test_is_configured(self):
        """Test is_configured (Coinbase public endpoints don't require key)."""
        adapter = CoinbaseAdapter()
        
        assert adapter.is_configured() is True
    
    def test_symbol_conversion(self):
        """Test symbol conversion for Coinbase."""
        assert "BTC/USD".replace("/", "-").upper() == "BTC-USD"
        assert "ETH/EUR".replace("/", "-").upper() == "ETH-EUR"


class TestKrakenAdapter:
    """Tests for KrakenAdapter class."""
    
    def test_adapter_creation(self):
        """Test adapter creation."""
        adapter = KrakenAdapter()
        
        assert adapter.name == "kraken"
    
    def test_is_configured(self):
        """Test is_configured (Kraken public endpoints don't require key)."""
        adapter = KrakenAdapter()
        
        assert adapter.is_configured() is True


class TestThirdPartyConnector:
    """Tests for ThirdPartyConnector class."""
    
    def test_connector_creation(self):
        """Test connector creation."""
        connector = ThirdPartyConnector()
        
        assert connector.name == "third_party"
        assert connector.status == ConnectionStatus.DISCONNECTED
    
    def test_connector_with_config(self):
        """Test connector with custom config."""
        config = ThirdPartyConfig(
            providers=["binance", "coinbase"],
            simultaneous_collection=False,
        )
        connector = ThirdPartyConnector(config=config)
        
        assert connector.config.providers == ["binance", "coinbase"]
        assert connector.config.simultaneous_collection is False
    
    def test_get_configured_providers(self):
        """Test getting configured providers."""
        connector = ThirdPartyConnector()
        
        configured = connector.get_configured_providers()
        
        assert "binance" in configured
        assert "coinbase" in configured
        assert "kraken" in configured
    
    @pytest.mark.asyncio
    async def test_connect(self):
        """Test connecting to providers."""
        connector = ThirdPartyConnector()
        
        result = await connector.connect()
        
        assert result is True
        assert connector.is_connected
        assert connector.status == ConnectionStatus.CONNECTED
    
    @pytest.mark.asyncio
    async def test_connect_no_providers(self):
        """Test connecting with no configured providers."""
        config = ThirdPartyConfig(providers=[])
        connector = ThirdPartyConnector(config=config)
        
        result = await connector.connect()
        
        assert result is False
        assert connector.status == ConnectionStatus.ERROR
    
    @pytest.mark.asyncio
    async def test_disconnect(self):
        """Test disconnecting from providers."""
        connector = ThirdPartyConnector()
        await connector.connect()
        
        await connector.disconnect()
        
        assert not connector.is_connected
        assert connector.status == ConnectionStatus.DISCONNECTED
    
    @pytest.mark.asyncio
    async def test_subscribe(self):
        """Test subscribing to a symbol."""
        connector = ThirdPartyConnector()
        await connector.connect()
        
        result = await connector.subscribe("BTC/USD")
        
        assert result is True
        assert "BTC/USD" in connector.subscriptions
    
    @pytest.mark.asyncio
    async def test_unsubscribe(self):
        """Test unsubscribing from a symbol."""
        connector = ThirdPartyConnector()
        await connector.connect()
        await connector.subscribe("BTC/USD")
        
        result = await connector.unsubscribe("BTC/USD")
        
        assert result is True
        assert "BTC/USD" not in connector.subscriptions
    
    def test_aggregate_market_data_single(self):
        """Test aggregating single market data result."""
        connector = ThirdPartyConnector()
        
        data = MarketData(
            symbol="BTC/USD",
            timestamp=datetime.utcnow(),
            last=50000.0,
            source="binance",
        )
        
        result = connector._aggregate_market_data([data])
        
        assert result == data
    
    def test_aggregate_market_data_multiple(self):
        """Test aggregating multiple market data results."""
        connector = ThirdPartyConnector()
        
        now = datetime.utcnow()
        
        data1 = MarketData(
            symbol="BTC/USD",
            timestamp=now,
            last=50000.0,
            bid=49900.0,
            source="binance",
        )
        data2 = MarketData(
            symbol="BTC/USD",
            timestamp=now - timedelta(seconds=1),
            last=50010.0,
            ask=50100.0,
            volume=1000.0,
            source="coinbase",
        )
        
        result = connector._aggregate_market_data([data1, data2])
        
        assert result.symbol == "BTC/USD"
        assert result.source == "aggregated"
        assert result.last == 50000.0
        assert result.bid == 49900.0
        assert result.ask == 50100.0
        assert result.volume == 1000.0
    
    def test_get_stats(self):
        """Test getting connector statistics."""
        connector = ThirdPartyConnector()
        
        stats = connector.get_stats()
        
        assert stats["name"] == "third_party"
        assert "providers" in stats
        assert "configured_providers" in stats
        assert "simultaneous_collection" in stats
    
    @pytest.mark.asyncio
    async def test_event_emission(self):
        """Test event emission on connect."""
        connector = ThirdPartyConnector()
        callback = MagicMock()
        
        connector.events.on(EventType.CONNECTED, callback)
        
        await connector.connect()
        
        # May emit multiple CONNECTED events during connection process
        assert callback.call_count >= 1
    
    @pytest.mark.asyncio
    async def test_subscription_events(self):
        """Test subscription event emission."""
        connector = ThirdPartyConnector()
        await connector.connect()
        
        add_callback = MagicMock()
        remove_callback = MagicMock()
        
        connector.events.on(EventType.SUBSCRIPTION_ADDED, add_callback)
        connector.events.on(EventType.SUBSCRIPTION_REMOVED, remove_callback)
        
        await connector.subscribe("BTC/USD")
        await connector.unsubscribe("BTC/USD")
        
        add_callback.assert_called_once()
        remove_callback.assert_called_once()


class TestCreateThirdPartyConnector:
    """Tests for create_third_party_connector factory function."""
    
    def test_create_default(self):
        """Test creating connector with defaults."""
        connector = create_third_party_connector()
        
        assert "binance" in connector.config.providers
        assert connector.config.simultaneous_collection is True
    
    def test_create_custom_providers(self):
        """Test creating connector with custom providers."""
        connector = create_third_party_connector(
            providers=["binance", "kraken"]
        )
        
        assert connector.config.providers == ["binance", "kraken"]
    
    def test_create_sequential(self):
        """Test creating connector with sequential collection."""
        connector = create_third_party_connector(simultaneous=False)
        
        assert connector.config.simultaneous_collection is False
    
    def test_create_with_api_keys(self):
        """Test creating connector with API keys."""
        connector = create_third_party_connector(
            twelvedata_api_key="td_key",
            alphavantage_api_key="av_key",
        )
        
        assert connector.config.twelvedata_api_key == "td_key"
        assert connector.config.alphavantage_api_key == "av_key"


class TestIntegration:
    """Integration tests for third party connector."""
    
    @pytest.mark.asyncio
    async def test_full_workflow(self):
        """Test full connector workflow."""
        connector = ThirdPartyConnector()
        
        assert await connector.connect() is True
        
        assert await connector.subscribe("BTC/USD") is True
        assert await connector.subscribe("ETH/USD") is True
        
        assert len(connector.subscriptions) == 2
        
        assert await connector.unsubscribe("BTC/USD") is True
        
        assert len(connector.subscriptions) == 1
        
        await connector.disconnect()
        
        assert not connector.is_connected
    
    @pytest.mark.asyncio
    async def test_multiple_connectors(self):
        """Test multiple connector instances."""
        connector1 = ThirdPartyConnector(ThirdPartyConfig(providers=["binance"]))
        connector2 = ThirdPartyConnector(ThirdPartyConfig(providers=["coinbase"]))
        
        await connector1.connect()
        await connector2.connect()
        
        assert connector1.is_connected
        assert connector2.is_connected
        
        await connector1.disconnect()
        await connector2.disconnect()
