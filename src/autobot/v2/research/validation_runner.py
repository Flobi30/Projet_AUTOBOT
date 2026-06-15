"""Command-line runner for AUTOBOT research validation.

This module is research-only. It loads historical/runtime data, chooses a
strategy-family signal generator, runs either a deterministic backtest or
walk-forward validation, and writes reports. It never touches runtime paper/live
execution.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from autobot.v2.cost_profiles import COST_PROFILE_NAMES, DEFAULT_RESEARCH_COST_PROFILE

from .backtest_engine import BacktestConfig, BacktestEngine, BacktestResult
from .execution_cost_model import ExecutionCostConfig, execution_cost_config_for_profile
from .market_data_repository import MarketBar, MarketDataRepository
from .regime_context import enrich_bars_with_regime_context
from .strategy_signal_generators import (
    GridResearchConfig,
    GridResearchSignalGenerator,
    MeanReversionResearchConfig,
    MeanReversionResearchSignalGenerator,
    TrendResearchConfig,
    TrendResearchSignalGenerator,
)
from .symbol_normalization import normalize_research_symbol
from .walk_forward import WalkForwardConfig, WalkForwardResult, WalkForwardValidator


StrategyName = Literal["grid", "trend", "mean_reversion"]
DataSource = Literal["csv", "autobot_state_db"]
RunMode = Literal["backtest", "walk_forward"]


@dataclass(frozen=True)
class ValidationRunnerConfig:
    run_id: str
    strategy: StrategyName
    data_source: DataSource
    data_path: Path
    symbol: str
    dataset_id: str
    mode: RunMode = "backtest"
    output_dir: Path = Path("reports/research_validation")
    initial_capital_eur: float = 1_000.0
    order_notional_eur: float = 100.0
    min_closed_trades: int = 30
    min_profit_factor: float = 1.2
    max_drawdown_pct: float = 15.0
    min_signal_net_edge_bps: float | None = None
    cost_config: ExecutionCostConfig = field(default_factory=ExecutionCostConfig)
    strategy_config: dict[str, Any] = field(default_factory=dict)
    start_at: str | None = None
    end_at: str | None = None
    limit: int | None = None
    train_window_bars: int = 200
    test_window_bars: int = 100
    step_window_bars: int | None = None
    min_folds: int = 3
    min_passing_folds: int = 2
    include_regime_context: bool = False


@dataclass(frozen=True)
class ValidationRunnerResult:
    mode: RunMode
    bar_count: int
    result: BacktestResult | WalkForwardResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "bar_count": self.bar_count,
            "result": self.result.to_dict(),
        }


def load_bars_for_validation(config: ValidationRunnerConfig) -> list[MarketBar]:
    repository = MarketDataRepository()
    if config.data_source == "csv":
        bars = repository.load_csv(config.data_path, default_symbol=config.symbol, default_timeframe="csv")
        bars = _filter_bars_for_symbol(bars, config.symbol)
        return _apply_temporal_filters(bars, start_at=config.start_at, end_at=config.end_at, limit=config.limit)
    if config.data_source == "autobot_state_db":
        return repository.load_autobot_state_db(
            config.data_path,
            symbol=config.symbol,
            start_at=config.start_at,
            end_at=config.end_at,
            limit=config.limit,
            canonicalize_symbols=True,
        )
    raise ValueError(f"unsupported data_source: {config.data_source}")


def _apply_temporal_filters(
    bars: list[MarketBar],
    *,
    start_at: str | None = None,
    end_at: str | None = None,
    limit: int | None = None,
) -> list[MarketBar]:
    start = _parse_optional_timestamp(start_at)
    end = _parse_optional_timestamp(end_at)
    filtered = [
        bar
        for bar in bars
        if (start is None or bar.timestamp >= start)
        and (end is None or bar.timestamp <= end)
    ]
    if limit is not None:
        return filtered[: max(1, int(limit))]
    return filtered


def _parse_optional_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _filter_bars_for_symbol(bars: list[MarketBar], symbol: str) -> list[MarketBar]:
    expected_symbol = normalize_research_symbol(symbol)
    filtered: list[MarketBar] = []
    for bar in bars:
        canonical_symbol = normalize_research_symbol(bar.symbol)
        if canonical_symbol != expected_symbol:
            continue
        if bar.symbol == canonical_symbol:
            filtered.append(bar)
            continue
        metadata = dict(bar.metadata)
        metadata.setdefault("raw_symbol", bar.symbol)
        metadata["symbol_normalized"] = True
        filtered.append(replace(bar, symbol=canonical_symbol, metadata=metadata))
    return MarketDataRepository.normalize(filtered)


def make_signal_generator_factory(
    strategy: StrategyName,
    strategy_config: dict[str, Any] | None = None,
    *,
    cost_config: ExecutionCostConfig | None = None,
) -> Callable[[], Any]:
    strategy_config = dict(strategy_config or {})
    if strategy == "grid":
        if cost_config is not None:
            strategy_config.setdefault(
                "estimated_round_trip_cost_bps",
                cost_config.round_trip_cost_estimate_bps(),
            )
        return lambda: GridResearchSignalGenerator(GridResearchConfig(**strategy_config))
    if strategy == "trend":
        return lambda: TrendResearchSignalGenerator(TrendResearchConfig(**strategy_config))
    if strategy == "mean_reversion":
        return lambda: MeanReversionResearchSignalGenerator(MeanReversionResearchConfig(**strategy_config))
    raise ValueError(f"unsupported strategy: {strategy}")


def run_validation(config: ValidationRunnerConfig) -> ValidationRunnerResult:
    bars = load_bars_for_validation(config)
    if config.include_regime_context:
        bars = enrich_bars_with_regime_context(bars)
    factory = make_signal_generator_factory(
        config.strategy,
        config.strategy_config,
        cost_config=config.cost_config,
    )
    backtest_config = BacktestConfig(
        run_id=config.run_id,
        strategy_id=_strategy_id(config.strategy),
        dataset_id=config.dataset_id,
        hypothesis=f"{config.strategy} research validation on {config.symbol}",
        initial_capital_eur=config.initial_capital_eur,
        default_order_notional_eur=config.order_notional_eur,
        output_dir=config.output_dir / "backtests",
        cost_config=config.cost_config,
        min_closed_trades=config.min_closed_trades,
        min_profit_factor=config.min_profit_factor,
        max_drawdown_pct=config.max_drawdown_pct,
        min_signal_net_edge_bps=config.min_signal_net_edge_bps,
    )
    if config.mode == "backtest":
        result = BacktestEngine(backtest_config).run(bars, factory())
        return ValidationRunnerResult(mode=config.mode, bar_count=len(bars), result=result)
    if config.mode == "walk_forward":
        walk_config = WalkForwardConfig(
            run_id=config.run_id,
            base_backtest_config=backtest_config,
            train_window_bars=config.train_window_bars,
            test_window_bars=config.test_window_bars,
            step_window_bars=config.step_window_bars,
            min_folds=config.min_folds,
            min_passing_folds=config.min_passing_folds,
            output_dir=config.output_dir / "walk_forward",
        )
        result = WalkForwardValidator(walk_config).run(bars, factory)
        return ValidationRunnerResult(mode=config.mode, bar_count=len(bars), result=result)
    raise ValueError(f"unsupported mode: {config.mode}")


def _strategy_id(strategy: StrategyName) -> str:
    return {
        "grid": "dynamic_grid",
        "trend": "trend_momentum",
        "mean_reversion": "mean_reversion",
    }[strategy]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run AUTOBOT research validation")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--strategy", choices=["grid", "trend", "mean_reversion"], required=True)
    parser.add_argument("--data-source", choices=["csv", "autobot_state_db"], required=True)
    parser.add_argument("--data-path", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--dataset-id", default=None)
    parser.add_argument("--mode", choices=["backtest", "walk_forward"], default="backtest")
    parser.add_argument("--output-dir", default="reports/research_validation")
    parser.add_argument("--initial-capital-eur", type=float, default=1_000.0)
    parser.add_argument("--order-notional-eur", type=float, default=100.0)
    parser.add_argument("--min-closed-trades", type=int, default=30)
    parser.add_argument("--min-profit-factor", type=float, default=1.2)
    parser.add_argument("--max-drawdown-pct", type=float, default=15.0)
    parser.add_argument("--min-signal-net-edge-bps", type=float, default=None)
    parser.add_argument("--start-at", default=None)
    parser.add_argument("--end-at", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--train-window-bars", type=int, default=200)
    parser.add_argument("--test-window-bars", type=int, default=100)
    parser.add_argument("--step-window-bars", type=int, default=None)
    parser.add_argument("--min-folds", type=int, default=3)
    parser.add_argument("--min-passing-folds", type=int, default=2)
    parser.add_argument("--include-regime-context", action="store_true")
    parser.add_argument("--cost-profile", choices=COST_PROFILE_NAMES, default=DEFAULT_RESEARCH_COST_PROFILE)
    parser.add_argument("--fee-bps", type=float, default=None)
    parser.add_argument("--spread-bps", type=float, default=None)
    parser.add_argument("--slippage-bps", type=float, default=None)
    parser.add_argument("--strategy-config-json", default="{}")
    args = parser.parse_args(argv)

    strategy_config = json.loads(args.strategy_config_json)
    if not isinstance(strategy_config, dict):
        raise ValueError("--strategy-config-json must decode to an object")
    config = ValidationRunnerConfig(
        run_id=args.run_id,
        strategy=args.strategy,
        data_source=args.data_source,
        data_path=Path(args.data_path),
        symbol=args.symbol.upper(),
        dataset_id=args.dataset_id or f"{args.data_source}:{args.symbol.upper()}",
        mode=args.mode,
        output_dir=Path(args.output_dir),
        initial_capital_eur=args.initial_capital_eur,
        order_notional_eur=args.order_notional_eur,
        min_closed_trades=args.min_closed_trades,
        min_profit_factor=args.min_profit_factor,
        max_drawdown_pct=args.max_drawdown_pct,
        min_signal_net_edge_bps=args.min_signal_net_edge_bps,
        cost_config=execution_cost_config_for_profile(
            args.cost_profile,
            fee_bps=args.fee_bps,
            spread_bps=args.spread_bps,
            slippage_bps=args.slippage_bps,
        ),
        strategy_config=strategy_config,
        start_at=args.start_at,
        end_at=args.end_at,
        limit=args.limit,
        train_window_bars=args.train_window_bars,
        test_window_bars=args.test_window_bars,
        step_window_bars=args.step_window_bars,
        min_folds=args.min_folds,
        min_passing_folds=args.min_passing_folds,
        include_regime_context=args.include_regime_context,
    )
    result = run_validation(config)
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
