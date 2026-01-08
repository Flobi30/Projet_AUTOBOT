"""
AUTOBOT Prometheus Metrics Module

Exposes metrics for monitoring:
- Trading metrics (trades, P&L, positions)
- Risk metrics (drawdown, leverage, daily loss)
- System metrics (latency, errors, uptime)
- Provider metrics (API calls, failures, cache hits)
- Ledger metrics (discrepancies, reconciliation)
- Webhook metrics (processed, failed, retried)
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
import threading
import json
import os

logger = logging.getLogger(__name__)

# Try to import prometheus_client, fallback to internal metrics if not available
try:
    from prometheus_client import (
        Counter,
        Gauge,
        Histogram,
        Summary,
        Info,
        generate_latest,
        CONTENT_TYPE_LATEST,
        CollectorRegistry,
        REGISTRY,
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    logger.warning("prometheus_client not installed, using internal metrics only")


class MetricType(Enum):
    """Types of metrics"""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


@dataclass
class InternalMetric:
    """Internal metric when Prometheus is not available"""
    name: str
    metric_type: MetricType
    description: str
    value: float = 0.0
    labels: Dict[str, str] = field(default_factory=dict)
    history: List[tuple] = field(default_factory=list)  # (timestamp, value)
    
    def inc(self, amount: float = 1.0):
        """Increment counter or gauge"""
        self.value += amount
        self._record_history()
    
    def dec(self, amount: float = 1.0):
        """Decrement gauge"""
        self.value -= amount
        self._record_history()
    
    def set(self, value: float):
        """Set gauge value"""
        self.value = value
        self._record_history()
    
    def observe(self, value: float):
        """Observe value for histogram/summary"""
        self.value = value
        self._record_history()
    
    def _record_history(self):
        """Record value in history"""
        self.history.append((datetime.utcnow().isoformat(), self.value))
        # Keep only last 1000 entries
        if len(self.history) > 1000:
            self.history = self.history[-1000:]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.metric_type.value,
            "description": self.description,
            "value": self.value,
            "labels": self.labels,
        }


class MetricsManager:
    """
    Metrics Manager for AUTOBOT.
    
    Provides Prometheus-compatible metrics for monitoring.
    Falls back to internal metrics if prometheus_client is not installed.
    """
    
    def __init__(self, data_dir: str = "/app/data"):
        self.data_dir = data_dir
        self.prometheus_available = PROMETHEUS_AVAILABLE
        
        # Internal metrics storage (used when Prometheus not available)
        self.internal_metrics: Dict[str, InternalMetric] = {}
        
        # Initialize metrics
        self._init_trading_metrics()
        self._init_risk_metrics()
        self._init_system_metrics()
        self._init_provider_metrics()
        self._init_ledger_metrics()
        self._init_webhook_metrics()
        
        # Ensure data directory exists
        os.makedirs(data_dir, exist_ok=True)
        
        logger.info(f"Metrics Manager initialized (Prometheus: {self.prometheus_available})")
    
    # =========================================================================
    # Trading Metrics
    # =========================================================================
    
    def _init_trading_metrics(self):
        """Initialize trading-related metrics"""
        if self.prometheus_available:
            self.trades_total = Counter(
                'autobot_trades_total',
                'Total number of trades executed',
                ['strategy', 'symbol', 'side', 'status']
            )
            self.trades_pnl = Gauge(
                'autobot_trades_pnl_total',
                'Total P&L from trades',
                ['strategy']
            )
            self.positions_open = Gauge(
                'autobot_positions_open',
                'Number of open positions',
                ['strategy']
            )
            self.position_value = Gauge(
                'autobot_position_value_total',
                'Total value of open positions'
            )
            self.trade_latency = Histogram(
                'autobot_trade_latency_seconds',
                'Trade execution latency',
                buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0]
            )
            self.win_rate = Gauge(
                'autobot_win_rate',
                'Current win rate',
                ['strategy']
            )
        else:
            self._create_internal_metric('autobot_trades_total', MetricType.COUNTER, 'Total trades')
            self._create_internal_metric('autobot_trades_pnl_total', MetricType.GAUGE, 'Total P&L')
            self._create_internal_metric('autobot_positions_open', MetricType.GAUGE, 'Open positions')
            self._create_internal_metric('autobot_position_value_total', MetricType.GAUGE, 'Position value')
            self._create_internal_metric('autobot_trade_latency_seconds', MetricType.HISTOGRAM, 'Trade latency')
            self._create_internal_metric('autobot_win_rate', MetricType.GAUGE, 'Win rate')
    
    def record_trade(
        self,
        strategy: str,
        symbol: str,
        side: str,
        status: str,
        pnl: float = 0.0,
        latency_seconds: float = 0.0,
    ):
        """Record a trade execution"""
        if self.prometheus_available:
            self.trades_total.labels(
                strategy=strategy,
                symbol=symbol,
                side=side,
                status=status
            ).inc()
            if pnl != 0:
                self.trades_pnl.labels(strategy=strategy).inc(pnl)
            if latency_seconds > 0:
                self.trade_latency.observe(latency_seconds)
        else:
            self.internal_metrics['autobot_trades_total'].inc()
            if pnl != 0:
                self.internal_metrics['autobot_trades_pnl_total'].inc(pnl)
            if latency_seconds > 0:
                self.internal_metrics['autobot_trade_latency_seconds'].observe(latency_seconds)
    
    def set_positions(self, strategy: str, count: int, total_value: float = 0.0):
        """Set current position count and value"""
        if self.prometheus_available:
            self.positions_open.labels(strategy=strategy).set(count)
            self.position_value.set(total_value)
        else:
            self.internal_metrics['autobot_positions_open'].set(count)
            self.internal_metrics['autobot_position_value_total'].set(total_value)
    
    def set_win_rate(self, strategy: str, rate: float):
        """Set win rate for a strategy"""
        if self.prometheus_available:
            self.win_rate.labels(strategy=strategy).set(rate)
        else:
            self.internal_metrics['autobot_win_rate'].set(rate)
    
    # =========================================================================
    # Risk Metrics
    # =========================================================================
    
    def _init_risk_metrics(self):
        """Initialize risk-related metrics"""
        if self.prometheus_available:
            self.current_drawdown = Gauge(
                'autobot_drawdown_pct',
                'Current drawdown percentage'
            )
            self.max_drawdown = Gauge(
                'autobot_max_drawdown_pct',
                'Maximum drawdown reached'
            )
            self.current_leverage = Gauge(
                'autobot_leverage_current',
                'Current leverage'
            )
            self.daily_loss = Gauge(
                'autobot_daily_loss_pct',
                'Daily loss percentage'
            )
            self.risk_level = Gauge(
                'autobot_risk_level',
                'Current risk level (0=low, 1=medium, 2=high, 3=critical, 4=emergency)'
            )
            self.circuit_breaker_active = Gauge(
                'autobot_circuit_breaker_active',
                'Circuit breaker status (1=active, 0=inactive)'
            )
            self.trading_mode = Gauge(
                'autobot_trading_mode',
                'Trading mode (0=normal, 1=reduced, 2=safe, 3=halted)'
            )
        else:
            self._create_internal_metric('autobot_drawdown_pct', MetricType.GAUGE, 'Drawdown %')
            self._create_internal_metric('autobot_max_drawdown_pct', MetricType.GAUGE, 'Max drawdown %')
            self._create_internal_metric('autobot_leverage_current', MetricType.GAUGE, 'Current leverage')
            self._create_internal_metric('autobot_daily_loss_pct', MetricType.GAUGE, 'Daily loss %')
            self._create_internal_metric('autobot_risk_level', MetricType.GAUGE, 'Risk level')
            self._create_internal_metric('autobot_circuit_breaker_active', MetricType.GAUGE, 'Circuit breaker')
            self._create_internal_metric('autobot_trading_mode', MetricType.GAUGE, 'Trading mode')
    
    def set_risk_metrics(
        self,
        drawdown_pct: float,
        max_drawdown_pct: float,
        leverage: float,
        daily_loss_pct: float,
        risk_level: int,
        circuit_breaker: bool,
        trading_mode: int,
    ):
        """Set all risk metrics at once"""
        if self.prometheus_available:
            self.current_drawdown.set(drawdown_pct)
            self.max_drawdown.set(max_drawdown_pct)
            self.current_leverage.set(leverage)
            self.daily_loss.set(daily_loss_pct)
            self.risk_level.set(risk_level)
            self.circuit_breaker_active.set(1 if circuit_breaker else 0)
            self.trading_mode.set(trading_mode)
        else:
            self.internal_metrics['autobot_drawdown_pct'].set(drawdown_pct)
            self.internal_metrics['autobot_max_drawdown_pct'].set(max_drawdown_pct)
            self.internal_metrics['autobot_leverage_current'].set(leverage)
            self.internal_metrics['autobot_daily_loss_pct'].set(daily_loss_pct)
            self.internal_metrics['autobot_risk_level'].set(risk_level)
            self.internal_metrics['autobot_circuit_breaker_active'].set(1 if circuit_breaker else 0)
            self.internal_metrics['autobot_trading_mode'].set(trading_mode)
    
    # =========================================================================
    # System Metrics
    # =========================================================================
    
    def _init_system_metrics(self):
        """Initialize system-related metrics"""
        if self.prometheus_available:
            self.uptime_seconds = Gauge(
                'autobot_uptime_seconds',
                'System uptime in seconds'
            )
            self.errors_total = Counter(
                'autobot_errors_total',
                'Total number of errors',
                ['module', 'error_type']
            )
            self.request_latency = Histogram(
                'autobot_request_latency_seconds',
                'API request latency',
                ['endpoint'],
                buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
            )
            self.active_tasks = Gauge(
                'autobot_active_tasks',
                'Number of active background tasks'
            )
            self.memory_usage_bytes = Gauge(
                'autobot_memory_usage_bytes',
                'Memory usage in bytes'
            )
            self.cpu_usage_pct = Gauge(
                'autobot_cpu_usage_pct',
                'CPU usage percentage'
            )
        else:
            self._create_internal_metric('autobot_uptime_seconds', MetricType.GAUGE, 'Uptime')
            self._create_internal_metric('autobot_errors_total', MetricType.COUNTER, 'Total errors')
            self._create_internal_metric('autobot_request_latency_seconds', MetricType.HISTOGRAM, 'Request latency')
            self._create_internal_metric('autobot_active_tasks', MetricType.GAUGE, 'Active tasks')
            self._create_internal_metric('autobot_memory_usage_bytes', MetricType.GAUGE, 'Memory usage')
            self._create_internal_metric('autobot_cpu_usage_pct', MetricType.GAUGE, 'CPU usage')
    
    def record_error(self, module: str, error_type: str):
        """Record an error"""
        if self.prometheus_available:
            self.errors_total.labels(module=module, error_type=error_type).inc()
        else:
            self.internal_metrics['autobot_errors_total'].inc()
    
    def record_request_latency(self, endpoint: str, latency_seconds: float):
        """Record API request latency"""
        if self.prometheus_available:
            self.request_latency.labels(endpoint=endpoint).observe(latency_seconds)
        else:
            self.internal_metrics['autobot_request_latency_seconds'].observe(latency_seconds)
    
    def set_system_metrics(
        self,
        uptime: float,
        active_tasks: int,
        memory_bytes: int,
        cpu_pct: float,
    ):
        """Set system metrics"""
        if self.prometheus_available:
            self.uptime_seconds.set(uptime)
            self.active_tasks.set(active_tasks)
            self.memory_usage_bytes.set(memory_bytes)
            self.cpu_usage_pct.set(cpu_pct)
        else:
            self.internal_metrics['autobot_uptime_seconds'].set(uptime)
            self.internal_metrics['autobot_active_tasks'].set(active_tasks)
            self.internal_metrics['autobot_memory_usage_bytes'].set(memory_bytes)
            self.internal_metrics['autobot_cpu_usage_pct'].set(cpu_pct)
    
    # =========================================================================
    # Provider Metrics
    # =========================================================================
    
    def _init_provider_metrics(self):
        """Initialize provider-related metrics"""
        if self.prometheus_available:
            self.provider_requests = Counter(
                'autobot_provider_requests_total',
                'Total provider API requests',
                ['provider', 'endpoint', 'status']
            )
            self.provider_latency = Histogram(
                'autobot_provider_latency_seconds',
                'Provider API latency',
                ['provider'],
                buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
            )
            self.provider_errors = Counter(
                'autobot_provider_errors_total',
                'Total provider errors',
                ['provider', 'error_type']
            )
            self.provider_cache_hits = Counter(
                'autobot_provider_cache_hits_total',
                'Provider cache hits',
                ['provider']
            )
            self.provider_cache_misses = Counter(
                'autobot_provider_cache_misses_total',
                'Provider cache misses',
                ['provider']
            )
            self.provider_quota_remaining = Gauge(
                'autobot_provider_quota_remaining_pct',
                'Provider quota remaining percentage',
                ['provider']
            )
        else:
            self._create_internal_metric('autobot_provider_requests_total', MetricType.COUNTER, 'Provider requests')
            self._create_internal_metric('autobot_provider_latency_seconds', MetricType.HISTOGRAM, 'Provider latency')
            self._create_internal_metric('autobot_provider_errors_total', MetricType.COUNTER, 'Provider errors')
            self._create_internal_metric('autobot_provider_cache_hits_total', MetricType.COUNTER, 'Cache hits')
            self._create_internal_metric('autobot_provider_cache_misses_total', MetricType.COUNTER, 'Cache misses')
            self._create_internal_metric('autobot_provider_quota_remaining_pct', MetricType.GAUGE, 'Quota remaining')
    
    def record_provider_request(
        self,
        provider: str,
        endpoint: str,
        status: str,
        latency_seconds: float,
    ):
        """Record a provider API request"""
        if self.prometheus_available:
            self.provider_requests.labels(
                provider=provider,
                endpoint=endpoint,
                status=status
            ).inc()
            self.provider_latency.labels(provider=provider).observe(latency_seconds)
        else:
            self.internal_metrics['autobot_provider_requests_total'].inc()
            self.internal_metrics['autobot_provider_latency_seconds'].observe(latency_seconds)
    
    def record_provider_error(self, provider: str, error_type: str):
        """Record a provider error"""
        if self.prometheus_available:
            self.provider_errors.labels(provider=provider, error_type=error_type).inc()
        else:
            self.internal_metrics['autobot_provider_errors_total'].inc()
    
    def record_cache_hit(self, provider: str):
        """Record a cache hit"""
        if self.prometheus_available:
            self.provider_cache_hits.labels(provider=provider).inc()
        else:
            self.internal_metrics['autobot_provider_cache_hits_total'].inc()
    
    def record_cache_miss(self, provider: str):
        """Record a cache miss"""
        if self.prometheus_available:
            self.provider_cache_misses.labels(provider=provider).inc()
        else:
            self.internal_metrics['autobot_provider_cache_misses_total'].inc()
    
    def set_provider_quota(self, provider: str, remaining_pct: float):
        """Set provider quota remaining"""
        if self.prometheus_available:
            self.provider_quota_remaining.labels(provider=provider).set(remaining_pct)
        else:
            self.internal_metrics['autobot_provider_quota_remaining_pct'].set(remaining_pct)
    
    # =========================================================================
    # Ledger Metrics
    # =========================================================================
    
    def _init_ledger_metrics(self):
        """Initialize ledger-related metrics"""
        if self.prometheus_available:
            self.ledger_transactions = Counter(
                'autobot_ledger_transactions_total',
                'Total ledger transactions',
                ['type']
            )
            self.ledger_balance = Gauge(
                'autobot_ledger_balance',
                'Current ledger balance',
                ['account']
            )
            self.ledger_discrepancy_pct = Gauge(
                'autobot_ledger_discrepancy_pct',
                'Ledger discrepancy percentage'
            )
            self.reconciliation_status = Gauge(
                'autobot_reconciliation_status',
                'Last reconciliation status (0=failed, 1=success, 2=partial)'
            )
            self.unreconciled_transactions = Gauge(
                'autobot_unreconciled_transactions',
                'Number of unreconciled transactions'
            )
        else:
            self._create_internal_metric('autobot_ledger_transactions_total', MetricType.COUNTER, 'Ledger transactions')
            self._create_internal_metric('autobot_ledger_balance', MetricType.GAUGE, 'Ledger balance')
            self._create_internal_metric('autobot_ledger_discrepancy_pct', MetricType.GAUGE, 'Discrepancy %')
            self._create_internal_metric('autobot_reconciliation_status', MetricType.GAUGE, 'Reconciliation status')
            self._create_internal_metric('autobot_unreconciled_transactions', MetricType.GAUGE, 'Unreconciled txns')
    
    def record_ledger_transaction(self, tx_type: str):
        """Record a ledger transaction"""
        if self.prometheus_available:
            self.ledger_transactions.labels(type=tx_type).inc()
        else:
            self.internal_metrics['autobot_ledger_transactions_total'].inc()
    
    def set_ledger_balance(self, account: str, balance: float):
        """Set ledger balance for an account"""
        if self.prometheus_available:
            self.ledger_balance.labels(account=account).set(balance)
        else:
            self.internal_metrics['autobot_ledger_balance'].set(balance)
    
    def set_reconciliation_metrics(
        self,
        discrepancy_pct: float,
        status: int,
        unreconciled_count: int,
    ):
        """Set reconciliation metrics"""
        if self.prometheus_available:
            self.ledger_discrepancy_pct.set(discrepancy_pct)
            self.reconciliation_status.set(status)
            self.unreconciled_transactions.set(unreconciled_count)
        else:
            self.internal_metrics['autobot_ledger_discrepancy_pct'].set(discrepancy_pct)
            self.internal_metrics['autobot_reconciliation_status'].set(status)
            self.internal_metrics['autobot_unreconciled_transactions'].set(unreconciled_count)
    
    # =========================================================================
    # Webhook Metrics
    # =========================================================================
    
    def _init_webhook_metrics(self):
        """Initialize webhook-related metrics"""
        if self.prometheus_available:
            self.webhooks_received = Counter(
                'autobot_webhooks_received_total',
                'Total webhooks received',
                ['event_type']
            )
            self.webhooks_processed = Counter(
                'autobot_webhooks_processed_total',
                'Total webhooks processed successfully',
                ['event_type']
            )
            self.webhooks_failed = Counter(
                'autobot_webhooks_failed_total',
                'Total webhooks failed',
                ['event_type', 'error_type']
            )
            self.webhooks_retried = Counter(
                'autobot_webhooks_retried_total',
                'Total webhook retries',
                ['event_type']
            )
            self.webhook_processing_time = Histogram(
                'autobot_webhook_processing_seconds',
                'Webhook processing time',
                ['event_type'],
                buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
            )
            self.webhook_dlq_size = Gauge(
                'autobot_webhook_dlq_size',
                'Webhook dead letter queue size'
            )
        else:
            self._create_internal_metric('autobot_webhooks_received_total', MetricType.COUNTER, 'Webhooks received')
            self._create_internal_metric('autobot_webhooks_processed_total', MetricType.COUNTER, 'Webhooks processed')
            self._create_internal_metric('autobot_webhooks_failed_total', MetricType.COUNTER, 'Webhooks failed')
            self._create_internal_metric('autobot_webhooks_retried_total', MetricType.COUNTER, 'Webhooks retried')
            self._create_internal_metric('autobot_webhook_processing_seconds', MetricType.HISTOGRAM, 'Webhook processing time')
            self._create_internal_metric('autobot_webhook_dlq_size', MetricType.GAUGE, 'DLQ size')
    
    def record_webhook_received(self, event_type: str):
        """Record a webhook received"""
        if self.prometheus_available:
            self.webhooks_received.labels(event_type=event_type).inc()
        else:
            self.internal_metrics['autobot_webhooks_received_total'].inc()
    
    def record_webhook_processed(self, event_type: str, processing_time: float):
        """Record a webhook processed successfully"""
        if self.prometheus_available:
            self.webhooks_processed.labels(event_type=event_type).inc()
            self.webhook_processing_time.labels(event_type=event_type).observe(processing_time)
        else:
            self.internal_metrics['autobot_webhooks_processed_total'].inc()
            self.internal_metrics['autobot_webhook_processing_seconds'].observe(processing_time)
    
    def record_webhook_failed(self, event_type: str, error_type: str):
        """Record a webhook failure"""
        if self.prometheus_available:
            self.webhooks_failed.labels(event_type=event_type, error_type=error_type).inc()
        else:
            self.internal_metrics['autobot_webhooks_failed_total'].inc()
    
    def record_webhook_retry(self, event_type: str):
        """Record a webhook retry"""
        if self.prometheus_available:
            self.webhooks_retried.labels(event_type=event_type).inc()
        else:
            self.internal_metrics['autobot_webhooks_retried_total'].inc()
    
    def set_webhook_dlq_size(self, size: int):
        """Set webhook DLQ size"""
        if self.prometheus_available:
            self.webhook_dlq_size.set(size)
        else:
            self.internal_metrics['autobot_webhook_dlq_size'].set(size)
    
    # =========================================================================
    # Internal Metrics Helpers
    # =========================================================================
    
    def _create_internal_metric(
        self,
        name: str,
        metric_type: MetricType,
        description: str,
    ):
        """Create an internal metric"""
        self.internal_metrics[name] = InternalMetric(
            name=name,
            metric_type=metric_type,
            description=description,
        )
    
    # =========================================================================
    # Export Methods
    # =========================================================================
    
    def get_prometheus_metrics(self) -> bytes:
        """Get metrics in Prometheus format"""
        if self.prometheus_available:
            return generate_latest(REGISTRY)
        else:
            # Generate Prometheus-compatible text format from internal metrics
            lines = []
            for name, metric in self.internal_metrics.items():
                lines.append(f"# HELP {name} {metric.description}")
                lines.append(f"# TYPE {name} {metric.metric_type.value}")
                lines.append(f"{name} {metric.value}")
            return "\n".join(lines).encode('utf-8')
    
    def get_metrics_json(self) -> Dict[str, Any]:
        """Get all metrics as JSON"""
        return {
            name: metric.to_dict()
            for name, metric in self.internal_metrics.items()
        }
    
    def get_content_type(self) -> str:
        """Get content type for Prometheus metrics"""
        if self.prometheus_available:
            return CONTENT_TYPE_LATEST
        return "text/plain; charset=utf-8"
    
    # =========================================================================
    # Persistence
    # =========================================================================
    
    def save_metrics(self):
        """Save internal metrics to file"""
        metrics_file = os.path.join(self.data_dir, "metrics_snapshot.json")
        
        data = {
            "metrics": {name: m.to_dict() for name, m in self.internal_metrics.items()},
            "saved_at": datetime.utcnow().isoformat(),
        }
        
        with open(metrics_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.debug(f"Metrics saved to {metrics_file}")


# Singleton instance
_metrics_manager_instance: Optional[MetricsManager] = None


def get_metrics_manager(data_dir: str = "/app/data") -> MetricsManager:
    """Get or create the singleton MetricsManager instance"""
    global _metrics_manager_instance
    
    if _metrics_manager_instance is None:
        _metrics_manager_instance = MetricsManager(data_dir=data_dir)
    
    return _metrics_manager_instance
