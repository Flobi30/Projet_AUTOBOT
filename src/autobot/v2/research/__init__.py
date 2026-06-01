"""Research and validation building blocks for AUTOBOT.

This package is intentionally isolated from runtime paper/live execution. It
provides deterministic components for historical research, replay, metrics and
validation before any strategy can be considered for promotion.
"""

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
    "AttributionBucket",
    "LossAttributionResult",
    "MarketBar",
    "MarketDataQualityReport",
    "MarketDataRepository",
    "MetricsEngine",
    "MetricsResult",
    "MatrixCellResult",
    "MatrixRunConfig",
    "MatrixRunResult",
    "RegistryRecommendationCriteria",
    "RegistryRecommendationReport",
    "RoundTripPnL",
    "GridResearchConfig",
    "GridResearchSignalGenerator",
    "MeanReversionResearchConfig",
    "MeanReversionResearchSignalGenerator",
    "ResearchStrategyInstance",
    "RuntimeStrategyBacktestAdapter",
    "StrategyRecommendation",
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
    "analyze_trade_journal",
    "analyze_trade_losses",
    "load_matrix_result",
    "recommend_from_matrix",
    "render_loss_attribution_report",
    "run_validation",
    "run_validation_matrix",
    "write_loss_attribution_report",
    "write_registry_recommendation_report",
]

_LAZY_EXPORTS = {
    "BacktestConfig": ("backtest_engine", "BacktestConfig"),
    "BacktestDecision": ("backtest_engine", "BacktestDecision"),
    "BacktestEngine": ("backtest_engine", "BacktestEngine"),
    "BacktestResult": ("backtest_engine", "BacktestResult"),
    "BacktestSignal": ("backtest_engine", "BacktestSignal"),
    "AttributionBucket": ("loss_attribution", "AttributionBucket"),
    "LossAttributionResult": ("loss_attribution", "LossAttributionResult"),
    "analyze_trade_journal": ("loss_attribution", "analyze_trade_journal"),
    "analyze_trade_losses": ("loss_attribution", "analyze_trade_losses"),
    "render_loss_attribution_report": ("loss_attribution", "render_loss_attribution_report"),
    "write_loss_attribution_report": ("loss_attribution", "write_loss_attribution_report"),
    "ExecutionCostConfig": ("execution_cost_model", "ExecutionCostConfig"),
    "ExecutionCostModel": ("execution_cost_model", "ExecutionCostModel"),
    "FillRequest": ("execution_cost_model", "FillRequest"),
    "FillResult": ("execution_cost_model", "FillResult"),
    "RoundTripPnL": ("execution_cost_model", "RoundTripPnL"),
    "MarketBar": ("market_data_repository", "MarketBar"),
    "MarketDataQualityReport": ("market_data_repository", "MarketDataQualityReport"),
    "MarketDataRepository": ("market_data_repository", "MarketDataRepository"),
    "MetricsEngine": ("metrics_engine", "MetricsEngine"),
    "MetricsResult": ("metrics_engine", "MetricsResult"),
    "MatrixCellResult": ("validation_matrix", "MatrixCellResult"),
    "MatrixRunConfig": ("validation_matrix", "MatrixRunConfig"),
    "MatrixRunResult": ("validation_matrix", "MatrixRunResult"),
    "run_validation_matrix": ("validation_matrix", "run_validation_matrix"),
    "RegistryRecommendationCriteria": ("registry_recommendations", "RegistryRecommendationCriteria"),
    "RegistryRecommendationReport": ("registry_recommendations", "RegistryRecommendationReport"),
    "StrategyRecommendation": ("registry_recommendations", "StrategyRecommendation"),
    "load_matrix_result": ("registry_recommendations", "load_matrix_result"),
    "recommend_from_matrix": ("registry_recommendations", "recommend_from_matrix"),
    "write_registry_recommendation_report": (
        "registry_recommendations",
        "write_registry_recommendation_report",
    ),
    "GridResearchConfig": ("strategy_signal_generators", "GridResearchConfig"),
    "GridResearchSignalGenerator": ("strategy_signal_generators", "GridResearchSignalGenerator"),
    "MeanReversionResearchConfig": ("strategy_signal_generators", "MeanReversionResearchConfig"),
    "MeanReversionResearchSignalGenerator": (
        "strategy_signal_generators",
        "MeanReversionResearchSignalGenerator",
    ),
    "TrendResearchConfig": ("strategy_signal_generators", "TrendResearchConfig"),
    "TrendResearchSignalGenerator": ("strategy_signal_generators", "TrendResearchSignalGenerator"),
    "ResearchStrategyInstance": ("strategy_adapters", "ResearchStrategyInstance"),
    "RuntimeStrategyBacktestAdapter": ("strategy_adapters", "RuntimeStrategyBacktestAdapter"),
    "TradingSignalAdapter": ("strategy_adapters", "TradingSignalAdapter"),
    "TradeJournal": ("trade_journal", "TradeJournal"),
    "TradeRecord": ("trade_journal", "TradeRecord"),
    "ValidationRunnerConfig": ("validation_runner", "ValidationRunnerConfig"),
    "ValidationRunnerResult": ("validation_runner", "ValidationRunnerResult"),
    "run_validation": ("validation_runner", "run_validation"),
    "WalkForwardConfig": ("walk_forward", "WalkForwardConfig"),
    "WalkForwardDecision": ("walk_forward", "WalkForwardDecision"),
    "WalkForwardFoldResult": ("walk_forward", "WalkForwardFoldResult"),
    "WalkForwardResult": ("walk_forward", "WalkForwardResult"),
    "WalkForwardValidator": ("walk_forward", "WalkForwardValidator"),
}


def __getattr__(name):
    """Expose research helpers without importing every submodule eagerly."""

    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = _LAZY_EXPORTS[name]
    from importlib import import_module

    value = getattr(import_module(f"{__name__}.{module_name}"), attr_name)
    globals()[name] = value
    return value
