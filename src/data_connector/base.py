"""
Base classes for Data Connector architecture.

Event-driven architecture for scalability, security, and robustness.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set
from collections import deque
import threading

logger = logging.getLogger(__name__)


class EventType(Enum):
    """Types of events emitted by connectors."""
    CONNECTED = auto()
    DISCONNECTED = auto()
    RECONNECTING = auto()
    DATA_RECEIVED = auto()
    ERROR = auto()
    RATE_LIMITED = auto()
    CACHE_HIT = auto()
    CACHE_MISS = auto()
    VALIDATION_PASSED = auto()
    VALIDATION_FAILED = auto()
    HEARTBEAT = auto()
    SUBSCRIPTION_ADDED = auto()
    SUBSCRIPTION_REMOVED = auto()


class ConnectionStatus(Enum):
    """Connection status for connectors."""
    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    RECONNECTING = auto()
    ERROR = auto()


@dataclass
class MarketData:
    """Standardized market data structure."""
    symbol: str
    timestamp: datetime
    bid: Optional[float] = None
    ask: Optional[float] = None
    last: Optional[float] = None
    volume: Optional[float] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    vwap: Optional[float] = None
    source: str = ""
    raw_data: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "bid": self.bid,
            "ask": self.ask,
            "last": self.last,
            "volume": self.volume,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "vwap": self.vwap,
            "source": self.source,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MarketData":
        """Create from dictionary."""
        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)
        elif timestamp is None:
            timestamp = datetime.utcnow()
        
        return cls(
            symbol=data.get("symbol", ""),
            timestamp=timestamp,
            bid=data.get("bid"),
            ask=data.get("ask"),
            last=data.get("last"),
            volume=data.get("volume"),
            open=data.get("open"),
            high=data.get("high"),
            low=data.get("low"),
            close=data.get("close"),
            vwap=data.get("vwap"),
            source=data.get("source", ""),
            raw_data=data.get("raw_data", {}),
        )


@dataclass
class ConnectorEvent:
    """Event emitted by connectors."""
    event_type: EventType
    timestamp: datetime
    connector_name: str
    data: Optional[Any] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


class EventEmitter:
    """Thread-safe event emitter for connector events."""
    
    def __init__(self, max_history: int = 1000):
        self._listeners: Dict[EventType, List[Callable[[ConnectorEvent], None]]] = {}
        self._all_listeners: List[Callable[[ConnectorEvent], None]] = []
        self._event_history: deque = deque(maxlen=max_history)
        self._lock = threading.RLock()
    
    def on(self, event_type: EventType, callback: Callable[[ConnectorEvent], None]) -> None:
        """Register a listener for a specific event type."""
        with self._lock:
            if event_type not in self._listeners:
                self._listeners[event_type] = []
            self._listeners[event_type].append(callback)
    
    def on_all(self, callback: Callable[[ConnectorEvent], None]) -> None:
        """Register a listener for all events."""
        with self._lock:
            self._all_listeners.append(callback)
    
    def off(self, event_type: EventType, callback: Callable[[ConnectorEvent], None]) -> None:
        """Remove a listener for a specific event type."""
        with self._lock:
            if event_type in self._listeners:
                try:
                    self._listeners[event_type].remove(callback)
                except ValueError:
                    pass
    
    def off_all(self, callback: Callable[[ConnectorEvent], None]) -> None:
        """Remove a listener from all events."""
        with self._lock:
            try:
                self._all_listeners.remove(callback)
            except ValueError:
                pass
    
    def emit(self, event: ConnectorEvent) -> None:
        """Emit an event to all registered listeners."""
        with self._lock:
            self._event_history.append(event)
            
            listeners = list(self._all_listeners)
            if event.event_type in self._listeners:
                listeners.extend(self._listeners[event.event_type])
        
        for listener in listeners:
            try:
                listener(event)
            except Exception as e:
                logger.error(f"Error in event listener: {e}")
    
    def get_history(self, event_type: Optional[EventType] = None, limit: int = 100) -> List[ConnectorEvent]:
        """Get event history, optionally filtered by type."""
        with self._lock:
            history = list(self._event_history)
        
        if event_type is not None:
            history = [e for e in history if e.event_type == event_type]
        
        return history[-limit:]


class BaseConnector(ABC):
    """
    Abstract base class for all data connectors.
    
    Implements event-driven architecture with:
    - Async connection management
    - Event emission for all state changes
    - Subscription management
    - Automatic reconnection
    - Health monitoring
    """
    
    def __init__(
        self,
        name: str,
        auto_reconnect: bool = True,
        reconnect_delay: float = 5.0,
        max_reconnect_attempts: int = 10,
        heartbeat_interval: float = 30.0,
    ):
        self.name = name
        self.auto_reconnect = auto_reconnect
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_attempts = max_reconnect_attempts
        self.heartbeat_interval = heartbeat_interval
        
        self._status = ConnectionStatus.DISCONNECTED
        self._subscriptions: Set[str] = set()
        self._reconnect_count = 0
        self._last_heartbeat: Optional[datetime] = None
        self._running = False
        self._lock = threading.RLock()
        
        self.events = EventEmitter()
        
        logger.info(f"Initialized connector: {name}")
    
    @property
    def status(self) -> ConnectionStatus:
        """Get current connection status."""
        return self._status
    
    @status.setter
    def status(self, value: ConnectionStatus) -> None:
        """Set connection status and emit event."""
        old_status = self._status
        self._status = value
        
        if old_status != value:
            event_type = {
                ConnectionStatus.CONNECTED: EventType.CONNECTED,
                ConnectionStatus.DISCONNECTED: EventType.DISCONNECTED,
                ConnectionStatus.RECONNECTING: EventType.RECONNECTING,
                ConnectionStatus.ERROR: EventType.ERROR,
            }.get(value)
            
            if event_type:
                self._emit_event(event_type, metadata={"old_status": old_status.name})
    
    @property
    def is_connected(self) -> bool:
        """Check if connector is connected."""
        return self._status == ConnectionStatus.CONNECTED
    
    @property
    def subscriptions(self) -> Set[str]:
        """Get current subscriptions."""
        with self._lock:
            return self._subscriptions.copy()
    
    def _emit_event(
        self,
        event_type: EventType,
        data: Optional[Any] = None,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emit a connector event."""
        event = ConnectorEvent(
            event_type=event_type,
            timestamp=datetime.utcnow(),
            connector_name=self.name,
            data=data,
            error=error,
            metadata=metadata or {},
        )
        self.events.emit(event)
    
    @abstractmethod
    async def connect(self) -> bool:
        """
        Establish connection to data source.
        
        Returns:
            bool: True if connection successful
        """
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from data source."""
        pass
    
    @abstractmethod
    async def subscribe(self, symbol: str) -> bool:
        """
        Subscribe to market data for a symbol.
        
        Args:
            symbol: Symbol to subscribe to
            
        Returns:
            bool: True if subscription successful
        """
        pass
    
    @abstractmethod
    async def unsubscribe(self, symbol: str) -> bool:
        """
        Unsubscribe from market data for a symbol.
        
        Args:
            symbol: Symbol to unsubscribe from
            
        Returns:
            bool: True if unsubscription successful
        """
        pass
    
    @abstractmethod
    async def get_market_data(self, symbol: str) -> Optional[MarketData]:
        """
        Get current market data for a symbol.
        
        Args:
            symbol: Symbol to get data for
            
        Returns:
            MarketData or None if not available
        """
        pass
    
    @abstractmethod
    async def get_historical_data(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1m",
    ) -> List[MarketData]:
        """
        Get historical market data.
        
        Args:
            symbol: Symbol to get data for
            start: Start datetime
            end: End datetime
            interval: Data interval (e.g., "1m", "5m", "1h", "1d")
            
        Returns:
            List of MarketData objects
        """
        pass
    
    async def _reconnect_loop(self) -> None:
        """Handle automatic reconnection."""
        while self._running and self.auto_reconnect:
            if self._status == ConnectionStatus.DISCONNECTED:
                if self._reconnect_count >= self.max_reconnect_attempts:
                    logger.error(f"{self.name}: Max reconnection attempts reached")
                    self.status = ConnectionStatus.ERROR
                    break
                
                self._reconnect_count += 1
                self.status = ConnectionStatus.RECONNECTING
                
                logger.info(
                    f"{self.name}: Reconnection attempt {self._reconnect_count}/{self.max_reconnect_attempts}"
                )
                
                try:
                    if await self.connect():
                        self._reconnect_count = 0
                        for symbol in self._subscriptions:
                            await self.subscribe(symbol)
                except Exception as e:
                    logger.error(f"{self.name}: Reconnection failed: {e}")
            
            await asyncio.sleep(self.reconnect_delay)
    
    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeats."""
        while self._running:
            if self.is_connected:
                self._last_heartbeat = datetime.utcnow()
                self._emit_event(EventType.HEARTBEAT)
            
            await asyncio.sleep(self.heartbeat_interval)
    
    async def start(self) -> bool:
        """
        Start the connector.
        
        Returns:
            bool: True if started successfully
        """
        if self._running:
            return True
        
        self._running = True
        
        if await self.connect():
            asyncio.create_task(self._reconnect_loop())
            asyncio.create_task(self._heartbeat_loop())
            return True
        
        return False
    
    async def stop(self) -> None:
        """Stop the connector."""
        self._running = False
        await self.disconnect()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get connector statistics."""
        return {
            "name": self.name,
            "status": self._status.name,
            "subscriptions": list(self._subscriptions),
            "subscription_count": len(self._subscriptions),
            "reconnect_count": self._reconnect_count,
            "last_heartbeat": self._last_heartbeat.isoformat() if self._last_heartbeat else None,
            "auto_reconnect": self.auto_reconnect,
        }
