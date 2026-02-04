"""Tests for base Data Connector classes."""

import asyncio
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock, patch

import sys
sys.path.insert(0, "/home/ubuntu/Projet_AUTOBOT/src")

from data_connector.base import (
    EventType,
    ConnectionStatus,
    MarketData,
    ConnectorEvent,
    EventEmitter,
    BaseConnector,
)


class TestMarketData:
    """Tests for MarketData dataclass."""
    
    def test_market_data_creation(self):
        """Test basic MarketData creation."""
        data = MarketData(
            symbol="AAPL",
            timestamp=datetime.utcnow(),
            bid=150.0,
            ask=150.5,
            last=150.25,
            volume=1000000.0,
        )
        
        assert data.symbol == "AAPL"
        assert data.bid == 150.0
        assert data.ask == 150.5
        assert data.last == 150.25
        assert data.volume == 1000000.0
    
    def test_market_data_to_dict(self):
        """Test MarketData to_dict conversion."""
        timestamp = datetime.utcnow()
        data = MarketData(
            symbol="BTC/USD",
            timestamp=timestamp,
            bid=50000.0,
            ask=50100.0,
            last=50050.0,
            source="binance",
        )
        
        result = data.to_dict()
        
        assert result["symbol"] == "BTC/USD"
        assert result["bid"] == 50000.0
        assert result["ask"] == 50100.0
        assert result["last"] == 50050.0
        assert result["source"] == "binance"
        assert result["timestamp"] == timestamp.isoformat()
    
    def test_market_data_from_dict(self):
        """Test MarketData from_dict creation."""
        timestamp = datetime.utcnow()
        data_dict = {
            "symbol": "EUR/USD",
            "timestamp": timestamp.isoformat(),
            "bid": 1.1000,
            "ask": 1.1005,
            "last": 1.1002,
            "volume": 500000.0,
            "source": "forex",
        }
        
        data = MarketData.from_dict(data_dict)
        
        assert data.symbol == "EUR/USD"
        assert data.bid == 1.1000
        assert data.ask == 1.1005
        assert data.last == 1.1002
        assert data.volume == 500000.0
        assert data.source == "forex"
    
    def test_market_data_optional_fields(self):
        """Test MarketData with optional fields."""
        data = MarketData(
            symbol="TEST",
            timestamp=datetime.utcnow(),
        )
        
        assert data.bid is None
        assert data.ask is None
        assert data.last is None
        assert data.volume is None
        assert data.open is None
        assert data.high is None
        assert data.low is None
        assert data.close is None
        assert data.vwap is None


class TestConnectorEvent:
    """Tests for ConnectorEvent dataclass."""
    
    def test_event_creation(self):
        """Test basic event creation."""
        event = ConnectorEvent(
            event_type=EventType.CONNECTED,
            timestamp=datetime.utcnow(),
            connector_name="test_connector",
        )
        
        assert event.event_type == EventType.CONNECTED
        assert event.connector_name == "test_connector"
        assert event.data is None
        assert event.error is None
    
    def test_event_with_data(self):
        """Test event with data payload."""
        data = MarketData(symbol="AAPL", timestamp=datetime.utcnow())
        event = ConnectorEvent(
            event_type=EventType.DATA_RECEIVED,
            timestamp=datetime.utcnow(),
            connector_name="test",
            data=data,
        )
        
        assert event.data == data
    
    def test_event_with_error(self):
        """Test event with error."""
        event = ConnectorEvent(
            event_type=EventType.ERROR,
            timestamp=datetime.utcnow(),
            connector_name="test",
            error="Connection failed",
        )
        
        assert event.error == "Connection failed"
    
    def test_event_with_metadata(self):
        """Test event with metadata."""
        event = ConnectorEvent(
            event_type=EventType.SUBSCRIPTION_ADDED,
            timestamp=datetime.utcnow(),
            connector_name="test",
            metadata={"symbol": "AAPL", "req_id": 123},
        )
        
        assert event.metadata["symbol"] == "AAPL"
        assert event.metadata["req_id"] == 123


class TestEventEmitter:
    """Tests for EventEmitter class."""
    
    def test_emitter_creation(self):
        """Test EventEmitter creation."""
        emitter = EventEmitter()
        assert emitter is not None
    
    def test_on_listener(self):
        """Test registering a listener for specific event type."""
        emitter = EventEmitter()
        callback = MagicMock()
        
        emitter.on(EventType.CONNECTED, callback)
        
        event = ConnectorEvent(
            event_type=EventType.CONNECTED,
            timestamp=datetime.utcnow(),
            connector_name="test",
        )
        emitter.emit(event)
        
        callback.assert_called_once_with(event)
    
    def test_on_all_listener(self):
        """Test registering a listener for all events."""
        emitter = EventEmitter()
        callback = MagicMock()
        
        emitter.on_all(callback)
        
        event1 = ConnectorEvent(
            event_type=EventType.CONNECTED,
            timestamp=datetime.utcnow(),
            connector_name="test",
        )
        event2 = ConnectorEvent(
            event_type=EventType.DATA_RECEIVED,
            timestamp=datetime.utcnow(),
            connector_name="test",
        )
        
        emitter.emit(event1)
        emitter.emit(event2)
        
        assert callback.call_count == 2
    
    def test_off_listener(self):
        """Test removing a listener."""
        emitter = EventEmitter()
        callback = MagicMock()
        
        emitter.on(EventType.CONNECTED, callback)
        emitter.off(EventType.CONNECTED, callback)
        
        event = ConnectorEvent(
            event_type=EventType.CONNECTED,
            timestamp=datetime.utcnow(),
            connector_name="test",
        )
        emitter.emit(event)
        
        callback.assert_not_called()
    
    def test_event_history(self):
        """Test event history tracking."""
        emitter = EventEmitter(max_history=10)
        
        for i in range(5):
            event = ConnectorEvent(
                event_type=EventType.HEARTBEAT,
                timestamp=datetime.utcnow(),
                connector_name="test",
                metadata={"index": i},
            )
            emitter.emit(event)
        
        history = emitter.get_history()
        assert len(history) == 5
    
    def test_event_history_limit(self):
        """Test event history respects max_history."""
        emitter = EventEmitter(max_history=5)
        
        for i in range(10):
            event = ConnectorEvent(
                event_type=EventType.HEARTBEAT,
                timestamp=datetime.utcnow(),
                connector_name="test",
            )
            emitter.emit(event)
        
        history = emitter.get_history()
        assert len(history) == 5
    
    def test_event_history_filter_by_type(self):
        """Test filtering event history by type."""
        emitter = EventEmitter()
        
        emitter.emit(ConnectorEvent(
            event_type=EventType.CONNECTED,
            timestamp=datetime.utcnow(),
            connector_name="test",
        ))
        emitter.emit(ConnectorEvent(
            event_type=EventType.DATA_RECEIVED,
            timestamp=datetime.utcnow(),
            connector_name="test",
        ))
        emitter.emit(ConnectorEvent(
            event_type=EventType.DATA_RECEIVED,
            timestamp=datetime.utcnow(),
            connector_name="test",
        ))
        
        history = emitter.get_history(event_type=EventType.DATA_RECEIVED)
        assert len(history) == 2
    
    def test_listener_exception_handling(self):
        """Test that listener exceptions don't break emission."""
        emitter = EventEmitter()
        
        def bad_callback(event):
            raise ValueError("Test error")
        
        good_callback = MagicMock()
        
        emitter.on(EventType.CONNECTED, bad_callback)
        emitter.on(EventType.CONNECTED, good_callback)
        
        event = ConnectorEvent(
            event_type=EventType.CONNECTED,
            timestamp=datetime.utcnow(),
            connector_name="test",
        )
        emitter.emit(event)
        
        good_callback.assert_called_once()


class ConcreteConnector(BaseConnector):
    """Concrete implementation of BaseConnector for testing."""
    
    def __init__(self, **kwargs):
        super().__init__(name="test_connector", **kwargs)
        self._connected = False
        self._data = {}
    
    async def connect(self) -> bool:
        self._connected = True
        self.status = ConnectionStatus.CONNECTED
        return True
    
    async def disconnect(self) -> None:
        self._connected = False
        self.status = ConnectionStatus.DISCONNECTED
    
    async def subscribe(self, symbol: str) -> bool:
        with self._lock:
            self._subscriptions.add(symbol)
        self._emit_event(EventType.SUBSCRIPTION_ADDED, data={"symbol": symbol})
        return True
    
    async def unsubscribe(self, symbol: str) -> bool:
        with self._lock:
            self._subscriptions.discard(symbol)
        self._emit_event(EventType.SUBSCRIPTION_REMOVED, data={"symbol": symbol})
        return True
    
    async def get_market_data(self, symbol: str) -> MarketData:
        return MarketData(
            symbol=symbol,
            timestamp=datetime.utcnow(),
            last=100.0,
            source="test",
        )
    
    async def get_historical_data(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1m",
    ) -> list:
        return [
            MarketData(
                symbol=symbol,
                timestamp=start,
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                source="test",
            )
        ]


class TestBaseConnector:
    """Tests for BaseConnector abstract class."""
    
    def test_connector_creation(self):
        """Test connector creation."""
        connector = ConcreteConnector()
        
        assert connector.name == "test_connector"
        assert connector.status == ConnectionStatus.DISCONNECTED
        assert not connector.is_connected
    
    @pytest.mark.asyncio
    async def test_connect(self):
        """Test connector connection."""
        connector = ConcreteConnector()
        
        result = await connector.connect()
        
        assert result is True
        assert connector.is_connected
        assert connector.status == ConnectionStatus.CONNECTED
    
    @pytest.mark.asyncio
    async def test_disconnect(self):
        """Test connector disconnection."""
        connector = ConcreteConnector()
        await connector.connect()
        
        await connector.disconnect()
        
        assert not connector.is_connected
        assert connector.status == ConnectionStatus.DISCONNECTED
    
    @pytest.mark.asyncio
    async def test_subscribe(self):
        """Test subscribing to a symbol."""
        connector = ConcreteConnector()
        await connector.connect()
        
        result = await connector.subscribe("AAPL")
        
        assert result is True
        assert "AAPL" in connector.subscriptions
    
    @pytest.mark.asyncio
    async def test_unsubscribe(self):
        """Test unsubscribing from a symbol."""
        connector = ConcreteConnector()
        await connector.connect()
        await connector.subscribe("AAPL")
        
        result = await connector.unsubscribe("AAPL")
        
        assert result is True
        assert "AAPL" not in connector.subscriptions
    
    @pytest.mark.asyncio
    async def test_get_market_data(self):
        """Test getting market data."""
        connector = ConcreteConnector()
        await connector.connect()
        
        data = await connector.get_market_data("AAPL")
        
        assert data is not None
        assert data.symbol == "AAPL"
        assert data.last == 100.0
    
    @pytest.mark.asyncio
    async def test_get_historical_data(self):
        """Test getting historical data."""
        connector = ConcreteConnector()
        await connector.connect()
        
        start = datetime.utcnow() - timedelta(days=1)
        end = datetime.utcnow()
        
        data = await connector.get_historical_data("AAPL", start, end)
        
        assert len(data) == 1
        assert data[0].symbol == "AAPL"
    
    def test_get_stats(self):
        """Test getting connector statistics."""
        connector = ConcreteConnector()
        
        stats = connector.get_stats()
        
        assert stats["name"] == "test_connector"
        assert stats["status"] == "DISCONNECTED"
        assert stats["subscription_count"] == 0
    
    @pytest.mark.asyncio
    async def test_status_change_emits_event(self):
        """Test that status changes emit events."""
        connector = ConcreteConnector()
        callback = MagicMock()
        
        connector.events.on(EventType.CONNECTED, callback)
        
        await connector.connect()
        
        callback.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_multiple_subscriptions(self):
        """Test multiple subscriptions."""
        connector = ConcreteConnector()
        await connector.connect()
        
        await connector.subscribe("AAPL")
        await connector.subscribe("GOOGL")
        await connector.subscribe("MSFT")
        
        assert len(connector.subscriptions) == 3
        assert "AAPL" in connector.subscriptions
        assert "GOOGL" in connector.subscriptions
        assert "MSFT" in connector.subscriptions
    
    def test_subscriptions_copy(self):
        """Test that subscriptions property returns a copy."""
        connector = ConcreteConnector()
        
        subs = connector.subscriptions
        subs.add("TEST")
        
        assert "TEST" not in connector.subscriptions


class TestEventTypes:
    """Tests for EventType enum."""
    
    def test_all_event_types_exist(self):
        """Test that all expected event types exist."""
        expected_types = [
            "CONNECTED",
            "DISCONNECTED",
            "RECONNECTING",
            "DATA_RECEIVED",
            "ERROR",
            "RATE_LIMITED",
            "CACHE_HIT",
            "CACHE_MISS",
            "VALIDATION_PASSED",
            "VALIDATION_FAILED",
            "HEARTBEAT",
            "SUBSCRIPTION_ADDED",
            "SUBSCRIPTION_REMOVED",
        ]
        
        for type_name in expected_types:
            assert hasattr(EventType, type_name)


class TestConnectionStatus:
    """Tests for ConnectionStatus enum."""
    
    def test_all_statuses_exist(self):
        """Test that all expected statuses exist."""
        expected_statuses = [
            "DISCONNECTED",
            "CONNECTING",
            "CONNECTED",
            "RECONNECTING",
            "ERROR",
        ]
        
        for status_name in expected_statuses:
            assert hasattr(ConnectionStatus, status_name)
