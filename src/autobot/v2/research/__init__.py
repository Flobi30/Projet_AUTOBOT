"""Research and validation building blocks for AUTOBOT.

This package is intentionally isolated from runtime paper/live execution. It
provides deterministic components for historical research, replay, metrics and
validation before any strategy can be considered for promotion.
"""

from .backtest_engine import BacktestConfig, BacktestDecision, BacktestEngine, BacktestResult, BacktestSignal
from .execution_cost_model import ExecutionCostConfig, ExecutionCostModel, FillRequest, FillResult, RoundTripPnL
from .market_data_repository import MarketBar, MarketDataQualityReport, MarketDataRepository
from .metrics_engine import MetricsEngine, MetricsResult
from .strategy_adapters import ResearchStrategyInstance, RuntimeStrategyBacktestAdapter, TradingSignalAdapter
from .strategy_signal_generators import (
    GridResearchConfig,
    GridResearchSignalGenerator,
    MeanReversionResearchConfig,
    MeanReversionResearchSignalGenerator,
    TrendResearchConfig,
    TrendResearchSignalGenerator,
)
from .trade_journal import TradeJournal, TradeRecord
from .validation_runner import ValidationRunnerConfig, ValidationRunnerResult, run_validation
from .validation_matrix import MatrixCellResult, MatrixRunConfig, MatrixRunResult, run_validation_matrix
from .walk_forward import (
    WalkForwardConfig,
    WalkForwardDecision,
    WalkForwardFoldResult,
    WalkForwardResult,
    WalkForwardValidator,
)

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
    "MatrixCellResult",
    "MatrixRunConfig",
    "MatrixRunResult",
    "RoundTripPnL",
    "GridResearchConfig",
    "GridResearchSignalGenerator",
    "MeanReversionResearchConfig",
    "MeanReversionResearchSignalGenerator",
    "ResearchStrategyInstance",
    "RuntimeStrategyBacktestAdapter",
    "TradeJournal",
    "TradeRecord",
    "TradingSignalAdapter",
    "ValidationRunnerConfig",
    "ValidationRunnerResult",
    "TrendResearchConfig",
    "TrendResearchSignalGenerator",
    "WalkForwardConfig",
    "WalkForwardDecision",
    "WalkForwardFoldResult",
    "WalkForwardResult",
    "WalkForwardValidator",
    "run_validation",
    "run_validation_matrix",
]
