"""
Base classes and interfaces for Data Connectors.

Provides abstract base class and common functionality for all
broker/data connectors in the AUTOBOT system.
"""

import asyncio
import logging
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TypeVar, Generic

from .exceptions import DataConnectorError, ConnectionError


class ConnectorState(Enum):
    """Connection state enumeration."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


@dataclass
class ConnectorConfig:
    """
    Configuration for data connectors.
    
    Attributes:
        host: Broker host address
        port: Broker port (7497 for IB paper trading)
        client_id: Unique client identifier
        timeout: Connection timeout in seconds
        max_reconnect_attempts: Maximum reconnection attempts
        reconnect_delay: Base delay between reconnection attempts
        heartbeat_interval: Interval for heartbeat checks
        rate_limit: Maximum requests per second
    """
    host: str = "127.0.0.1"
    port: int = 7497  # IB paper trading port
    client_id: int = 1
    timeout: float = 30.0
    max_reconnect_attempts: int = 5
    reconnect_delay: float = 1.0
    reconnect_delay_max: float = 60.0
    heartbeat_interval: float = 10.0
    rate_limit: int = 50  # 50 req/sec as specified
    circuit_breaker_threshold: int = 5
    circuit_breaker_timeout: float = 60.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary for logging."""
        return {
            "host": self.host,
            "port": self.port,
            "client_id": self.client_id,
            "timeout": self.timeout,
            "max_reconnect_attempts": self.max_reconnect_attempts,
            "reconnect_delay": self.reconnect_delay,
            "heartbeat_interval": self.heartbeat_interval,
            "rate_limit": self.rate_limit,
        }


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        if hasattr(record, "connector_state"):
            log_data["connector_state"] = record.connector_state
        if hasattr(record, "latency_ms"):
            log_data["latency_ms"] = record.latency_ms
        if hasattr(record, "error_code"):
            log_data["error_code"] = record.error_code
        if hasattr(record, "extra_data"):
            log_data.update(record.extra_data)
        
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_data)


def setup_json_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Create a logger with JSON formatting."""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
    
    return logger


T = TypeVar("T")


@dataclass
class ConnectionMetrics:
    """Metrics for connection monitoring."""
    connect_time: Optional[datetime] = None
    disconnect_time: Optional[datetime] = None
    reconnect_count: int = 0
    total_requests: int = 0
    failed_requests: int = 0
    last_request_time: Optional[datetime] = None
    last_error: Optional[str] = None
    latencies: List[float] = field(default_factory=list)
    
    @property
    def uptime_seconds(self) -> float:
        """Calculate uptime in seconds."""
        if not self.connect_time:
            return 0.0
        end_time = self.disconnect_time or datetime.utcnow()
        return (end_time - self.connect_time).total_seconds()
    
    @property
    def success_rate(self) -> float:
        """Calculate request success rate."""
        if self.total_requests == 0:
            return 1.0
        return (self.total_requests - self.failed_requests) / self.total_requests
    
    @property
    def p95_latency_ms(self) -> float:
        """Calculate p95 latency in milliseconds."""
        if not self.latencies:
            return 0.0
        sorted_latencies = sorted(self.latencies)
        idx = int(len(sorted_latencies) * 0.95)
        return sorted_latencies[min(idx, len(sorted_latencies) - 1)]
    
    def record_latency(self, latency_ms: float) -> None:
        """Record a latency measurement, keeping last 1000 samples."""
        self.latencies.append(latency_ms)
        if len(self.latencies) > 1000:
            self.latencies = self.latencies[-1000:]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "uptime_seconds": self.uptime_seconds,
            "reconnect_count": self.reconnect_count,
            "total_requests": self.total_requests,
            "failed_requests": self.failed_requests,
            "success_rate": self.success_rate,
            "p95_latency_ms": self.p95_latency_ms,
            "last_error": self.last_error,
        }


class BaseConnector(ABC):
    """
    Abstract base class for all data connectors.
    
    Provides common functionality for connection management,
    state tracking, and metrics collection.
    """
    
    def __init__(self, config: Optional[ConnectorConfig] = None):
        self.config = config or ConnectorConfig()
        self._state = ConnectorState.DISCONNECTED
        self._metrics = ConnectionMetrics()
        self._state_callbacks: List[Callable[[ConnectorState], None]] = []
        self._error_callbacks: List[Callable[[DataConnectorError], None]] = []
        self._logger = setup_json_logger(self.__class__.__name__)
        self._lock = asyncio.Lock()
    
    @property
    def state(self) -> ConnectorState:
        """Get current connection state."""
        return self._state
    
    @state.setter
    def state(self, new_state: ConnectorState) -> None:
        """Set connection state and notify callbacks."""
        old_state = self._state
        self._state = new_state
        
        self._logger.info(
            f"State changed: {old_state.value} -> {new_state.value}",
            extra={"extra_data": {"old_state": old_state.value, "new_state": new_state.value}}
        )
        
        for callback in self._state_callbacks:
            try:
                callback(new_state)
            except Exception as e:
                self._logger.error(f"State callback error: {e}")
    
    @property
    def is_connected(self) -> bool:
        """Check if connector is connected."""
        return self._state == ConnectorState.CONNECTED
    
    @property
    def metrics(self) -> ConnectionMetrics:
        """Get connection metrics."""
        return self._metrics
    
    def on_state_change(self, callback: Callable[[ConnectorState], None]) -> None:
        """Register a state change callback."""
        self._state_callbacks.append(callback)
    
    def on_error(self, callback: Callable[[DataConnectorError], None]) -> None:
        """Register an error callback."""
        self._error_callbacks.append(callback)
    
    def _notify_error(self, error: DataConnectorError) -> None:
        """Notify error callbacks."""
        self._metrics.last_error = str(error)
        for callback in self._error_callbacks:
            try:
                callback(error)
            except Exception as e:
                self._logger.error(f"Error callback error: {e}")
    
    @abstractmethod
    async def connect(self) -> bool:
        """
        Establish connection to the broker.
        
        Returns:
            True if connection successful, False otherwise.
        """
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the broker."""
        pass
    
    @abstractmethod
    async def reconnect(self) -> bool:
        """
        Attempt to reconnect to the broker.
        
        Returns:
            True if reconnection successful, False otherwise.
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check connection health.
        
        Returns:
            True if connection is healthy, False otherwise.
        """
        pass
    
    async def __aenter__(self) -> "BaseConnector":
        """Async context manager entry."""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.disconnect()
