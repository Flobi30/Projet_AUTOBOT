"""
Data Connector Module for AUTOBOT.

Architecture event-driven pour la collecte de données de marché.
Supporte Interactive Brokers (TWS API), données tierces, rate limiting,
cache local et validation des données.
"""

from .base import (
    BaseConnector,
    ConnectorEvent,
    EventType,
    MarketData,
    ConnectionStatus,
)
from .rate_limiter import RateLimiter, RateLimitConfig
from .cache import DataCache, CacheConfig
from .validator import DataValidator, ValidationRule, ValidationResult
from .ib_connector import IBConnector, IBConfig
from .third_party_connector import ThirdPartyConnector, ThirdPartyConfig

__all__ = [
    "BaseConnector",
    "ConnectorEvent",
    "EventType",
    "MarketData",
    "ConnectionStatus",
    "RateLimiter",
    "RateLimitConfig",
    "DataCache",
    "CacheConfig",
    "DataValidator",
    "ValidationRule",
    "ValidationResult",
    "IBConnector",
    "IBConfig",
    "ThirdPartyConnector",
    "ThirdPartyConfig",
]
