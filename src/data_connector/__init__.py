"""
Data Connector Module for AUTOBOT Trading System.

This module provides robust data connectivity for Interactive Brokers
with automatic reconnection, heartbeat monitoring, rate limiting,
and circuit breaker patterns.

Architecture:
- BaseConnector: Abstract base class for all connectors
- IBConnector: Interactive Brokers implementation using ib_insync
- RateLimiter: Token bucket rate limiting (50 req/sec)
- CircuitBreaker: Fault tolerance pattern
- HeartbeatMonitor: Connection health monitoring
"""

from .base import BaseConnector, ConnectorState, ConnectorConfig
from .ib_connector import IBConnector
from .rate_limiter import RateLimiter, RateLimitExceeded
from .circuit_breaker import CircuitBreaker, CircuitBreakerOpen
from .heartbeat import HeartbeatMonitor
from .exceptions import (
    DataConnectorError,
    ConnectionError,
    ReconnectionError,
    IBError,
)

__all__ = [
    # Core classes
    "BaseConnector",
    "ConnectorState",
    "ConnectorConfig",
    "IBConnector",
    # Resilience patterns
    "RateLimiter",
    "RateLimitExceeded",
    "CircuitBreaker",
    "CircuitBreakerOpen",
    "HeartbeatMonitor",
    # Exceptions
    "DataConnectorError",
    "ConnectionError",
    "ReconnectionError",
    "IBError",
]

__version__ = "1.0.0"
