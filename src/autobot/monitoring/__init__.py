"""
AUTOBOT Monitoring Module

Comprehensive monitoring including:
- Prometheus-compatible metrics
- Structured logging with rotation
- Alerting for critical events
- Log retention management
"""

from autobot.monitoring.metrics import (
    MetricsManager,
    MetricType,
    InternalMetric,
    get_metrics_manager,
    PROMETHEUS_AVAILABLE,
)
from autobot.monitoring.logging_config import (
    LoggingManager,
    GzipRotatingFileHandler,
    JsonFormatter,
    AlertHandler,
    LogRetentionManager,
    get_logging_manager,
    setup_logging,
)

__all__ = [
    # Metrics
    "MetricsManager",
    "MetricType",
    "InternalMetric",
    "get_metrics_manager",
    "PROMETHEUS_AVAILABLE",
    # Logging
    "LoggingManager",
    "GzipRotatingFileHandler",
    "JsonFormatter",
    "AlertHandler",
    "LogRetentionManager",
    "get_logging_manager",
    "setup_logging",
]
