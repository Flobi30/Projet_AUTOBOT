"""Research and validation building blocks for AUTOBOT.

This package is intentionally isolated from runtime paper/live execution. It
provides deterministic components for historical research, replay, metrics and
validation before any strategy can be considered for promotion.
"""

from .backtest_engine import BacktestConfig, BacktestDecision, BacktestEngine, BacktestResult, BacktestSignal
from .execution_cost_model import ExecutionCostConfig, ExecutionCostModel, FillRequest, FillResult, RoundTripPnL
from .market_data_repository import MarketBar, MarketDataQualityReport, MarketDataRepository
from .metrics_engine import MetricsEngine, MetricsResult
from .trade_journal import TradeJournal, TradeRecord

__all__ = [
    "ExecutionCostConfig",
    "ExecutionCostModel",
    "FillRequest",
    "FillResult",
    "BacktestConfig",
    "BacktestDecision",
    "BacktestEngine",
    "BacktestResult",
    "BacktestSignal",
    "MarketBar",
    "MarketDataQualityReport",
    "MarketDataRepository",
    "MetricsEngine",
    "MetricsResult",
    "RoundTripPnL",
    "TradeJournal",
    "TradeRecord",
]
