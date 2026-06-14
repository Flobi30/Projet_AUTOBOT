"""Walk-forward diagnostics for strategy/regime research buckets.

This module evaluates whether strategy/regime buckets that look interesting in
aggregate also beat simple baselines across chronological test windows. It is
research-only and never changes paper/live execution or strategy promotion.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Iterable, Sequence

from autobot.v2.cost_profiles import COST_PROFILE_NAMES, DEFAULT_RESEARCH_COST_PROFILE

from .execution_cost_model import ExecutionCostConfig, execution_cost_config_for_profile
from .market_data_repository import MarketBar
from .regime_context import enrich_bars_with_regime_context
from .strategy_regime_baselines import (
    StrategyRegimeBaselineBucket,
    _load_bars,
    evaluate_strategy_regime_baselines,
)
from .strategy_regime_report import _journal_path_from_cell, analyze_strategy_regimes
from .trade_journal import TradeJournal, TradeRecord


@dataclass(frozen=True)
class StrategyRegimeWalkForwardFoldBucket:
    fold_index: int
    strategy_id: str
    regime: str
    strategy_trade_count: int
    strategy_net_pnl_eur: float
    best_baseline_name: str | None
    best_baseline_net_pnl_eur: float | None
    delta_vs_best_baseline_eur: float | None
    beats_no_trade: bool
    beats_best_baseline: bool | None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class StrategyRegimeWalkForwardFold:
    fold_index: int
    train_event_count: int
    test_event_count: int
    train_start_at: str
    train_end_at: str
    test_start_at: str
    test_end_at: str
    bucket_count: int
    buckets: tuple[StrategyRegimeWalkForwardFoldBucket, ...]

    def to_dict(self) -> dict:
        return {
            "fold_index": self.fold_index,
            "train_event_count": self.train_event_count,
            "test_event_count": self.test_event_count,
            "train_start_at": self.train_start_at,
            "train_end_at": self.train_end_at,
            "test_start_at": self.test_start_at,
            "test_end_at": self.test_end_at,
            "bucket_count": self.bucket_count,
            "buckets": [bucket.to_dict() for bucket in self.buckets],
        }


@dataclass(frozen=True)
class StrategyRegimeWalkForwardSummary:
    strategy_id: str
    regime: str
    evaluated_fold_count: int
    passing_fold_count: int
    positive_fold_count: int
    total_trade_count: int
    aggregate_strategy_net_pnl_eur: float
    aggregate_delta_vs_best_baseline_eur: float
    worst_delta_vs_best_baseline_eur: float | None
    status: str
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class StrategyRegimeWalkForwardReport:
    run_id: str
    fold_count: int
    evaluated_bucket_count: int
    summaries: tuple[StrategyRegimeWalkForwardSummary, ...]
    folds: tuple[StrategyRegimeWalkForwardFold, ...]
    json_report_path: str | None = None
    markdown_report_path: str | None = None

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "fold_count": self.fold_count,
            "evaluated_bucket_count": self.evaluated_bucket_count,
            "summaries": [summary.to_dict() for summary in self.summaries],
            "folds": [fold.to_dict() for fold in self.folds],
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
        }


def evaluate_strategy_regime_walk_forward(
    records: Iterable[TradeRecord],
    bars: Sequence[MarketBar],
    *,
    run_id: str = "strategy_regime_walk_forward",
    train_window_bars: int = 200,
    test_window_bars: int = 100,
    step_window_bars: int | None = None,
    min_folds: int = 3,
    min_passing_folds: int = 2,
    min_total_trades: int = 30,
    initial_capital_eur: float = 1_000.0,
    order_notional_eur: float = 100.0,
    cost_config: ExecutionCostConfig | None = None,
) -> StrategyRegimeWalkForwardReport:
    if train_window_bars <= 0:
        raise ValueError("train_window_bars must be positive")
    if test_window_bars <= 0:
        raise ValueError("test_window_bars must be positive")
    if step_window_bars is not None and step_window_bars <= 0:
        raise ValueError("step_window_bars must be positive when provided")
    if min_folds <= 0:
        raise ValueError("min_folds must be positive")
    if min_passing_folds <= 0:
        raise ValueError("min_passing_folds must be positive")
    if min_total_trades <= 0:
        raise ValueError("min_total_trades must be positive")

    trades = tuple(records)
    ordered_bars = _chronological_bars(bars)
    fold_windows = _fold_windows(
        ordered_bars,
        train_window_bars=train_window_bars,
        test_window_bars=test_window_bars,
        step_window_bars=step_window_bars,
    )
    folds = tuple(
        _evaluate_fold(
            fold_index,
            train_bars,
            test_bars,
            trades,
            run_id=run_id,
            initial_capital_eur=initial_capital_eur,
            order_notional_eur=order_notional_eur,
            cost_config=cost_config,
        )
        for fold_index, (train_bars, test_bars) in enumerate(fold_windows, start=1)
    )
    summaries = _summaries(
        folds,
        min_folds=min_folds,
        min_passing_folds=min_passing_folds,
        min_total_trades=min_total_trades,
    )
    return StrategyRegimeWalkForwardReport(
        run_id=run_id,
        fold_count=len(folds),
        evaluated_bucket_count=sum(fold.bucket_count for fold in folds),
        summaries=summaries,
        folds=folds,
    )


def evaluate_strategy_regime_walk_forward_journals(
    journal_paths: Iterable[str | Path],
    bars: Sequence[MarketBar],
    *,
    run_id: str = "strategy_regime_walk_forward",
    train_window_bars: int = 200,
    test_window_bars: int = 100,
    step_window_bars: int | None = None,
    min_folds: int = 3,
    min_passing_folds: int = 2,
    min_total_trades: int = 30,
    initial_capital_eur: float = 1_000.0,
    order_notional_eur: float = 100.0,
    cost_config: ExecutionCostConfig | None = None,
) -> StrategyRegimeWalkForwardReport:
    records: list[TradeRecord] = []
    for path in journal_paths:
        records.extend(TradeJournal.from_json(path).records)
    return evaluate_strategy_regime_walk_forward(
        records,
        bars,
        run_id=run_id,
        train_window_bars=train_window_bars,
        test_window_bars=test_window_bars,
        step_window_bars=step_window_bars,
        min_folds=min_folds,
        min_passing_folds=min_passing_folds,
        min_total_trades=min_total_trades,
        initial_capital_eur=initial_capital_eur,
        order_notional_eur=order_notional_eur,
        cost_config=cost_config,
    )


def write_strategy_regime_walk_forward_report(
    result: StrategyRegimeWalkForwardReport,
    output_dir: str | Path,
) -> StrategyRegimeWalkForwardReport:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / f"{result.run_id}.json"
    md_path = output_path / f"{result.run_id}.md"
    json_path.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(render_strategy_regime_walk_forward_report(result), encoding="utf-8")
    return replace(result, json_report_path=str(json_path), markdown_report_path=str(md_path))


def write_matrix_strategy_regime_walk_forward_report(matrix_config, matrix_result, output_dir: str | Path):
    journal_paths = [
        path
        for path in (_journal_path_from_cell(getattr(cell, "report_path", None)) for cell in matrix_result.results)
        if path is not None and path.exists()
    ]
    bars = _load_bars(
        data_source=matrix_config.data_source,
        data_path=matrix_config.data_path,
        symbols=matrix_config.symbols,
        start_at=matrix_config.start_at,
        end_at=matrix_config.end_at,
        limit=matrix_config.limit,
    )
    if matrix_config.include_regime_context:
        bars = enrich_bars_with_regime_context(bars)
    return write_strategy_regime_walk_forward_report(
        evaluate_strategy_regime_walk_forward_journals(
            journal_paths,
            bars,
            run_id=f"{matrix_result.run_id}_strategy_regime_walk_forward",
            train_window_bars=matrix_config.train_window_bars,
            test_window_bars=matrix_config.test_window_bars,
            step_window_bars=matrix_config.step_window_bars,
            min_folds=matrix_config.min_folds,
            min_passing_folds=matrix_config.min_passing_folds,
            min_total_trades=matrix_config.min_closed_trades,
            initial_capital_eur=matrix_config.initial_capital_eur,
            order_notional_eur=matrix_config.order_notional_eur,
            cost_config=matrix_config.cost_config,
        ),
        output_dir,
    )


def render_strategy_regime_walk_forward_report(result: StrategyRegimeWalkForwardReport) -> str:
    lines = [
        f"# Strategy Regime Walk-Forward Report - {result.run_id}",
        "",
        "## Summary",
        "",
        f"- Folds: {result.fold_count}",
        f"- Evaluated buckets: {result.evaluated_bucket_count}",
        "",
        "## Strategy x Regime",
        "",
        "| Strategy | Regime | Folds | Passing | Positive | Trades | Net PnL | Delta vs Best Baseline | Worst Delta | Status | Reason |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    if not result.summaries:
        lines.append("| none | none | 0 | 0 | 0 | 0 | 0.000000 | 0.000000 | N/A | no_buckets |")
    for summary in result.summaries:
        lines.append(
            f"| {summary.strategy_id} | {summary.regime} | {summary.evaluated_fold_count} | "
            f"{summary.passing_fold_count} | {summary.positive_fold_count} | {summary.total_trade_count} | "
            f"{summary.aggregate_strategy_net_pnl_eur:.6f} | {summary.aggregate_delta_vs_best_baseline_eur:.6f} | "
            f"{_fmt(summary.worst_delta_vs_best_baseline_eur)} | {summary.status} | {summary.reason} |"
        )
    lines.extend(
        [
            "",
            "## Fold Buckets",
            "",
            "| Fold | Strategy | Regime | Trades | Strategy Net | Best Baseline | Baseline Net | Delta | Beats Best |",
            "| ---: | --- | --- | ---: | ---: | --- | ---: | ---: | --- |",
        ]
    )
    for fold in result.folds:
        for bucket in fold.buckets:
            lines.append(
                f"| {fold.fold_index} | {bucket.strategy_id} | {bucket.regime} | {bucket.strategy_trade_count} | "
                f"{bucket.strategy_net_pnl_eur:.6f} | {bucket.best_baseline_name or 'none'} | "
                f"{_fmt(bucket.best_baseline_net_pnl_eur)} | {_fmt(bucket.delta_vs_best_baseline_eur)} | "
                f"{str(bucket.beats_best_baseline).lower()} |"
            )
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "This report is research-only. It does not authorize paper or live execution.",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write AUTOBOT strategy/regime walk-forward report")
    parser.add_argument("--journal", action="append", required=True)
    parser.add_argument("--data-source", choices=["csv", "autobot_state_db"], required=True)
    parser.add_argument("--data-path", required=True)
    parser.add_argument("--symbols", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--run-id", default="strategy_regime_walk_forward")
    parser.add_argument("--include-regime-context", action="store_true")
    parser.add_argument("--train-window-bars", type=int, default=200)
    parser.add_argument("--test-window-bars", type=int, default=100)
    parser.add_argument("--step-window-bars", type=int, default=None)
    parser.add_argument("--min-folds", type=int, default=3)
    parser.add_argument("--min-passing-folds", type=int, default=2)
    parser.add_argument("--min-total-trades", type=int, default=30)
    parser.add_argument("--initial-capital-eur", type=float, default=1_000.0)
    parser.add_argument("--order-notional-eur", type=float, default=100.0)
    parser.add_argument("--cost-profile", choices=COST_PROFILE_NAMES, default=DEFAULT_RESEARCH_COST_PROFILE)
    parser.add_argument("--fee-bps", type=float, default=None)
    parser.add_argument("--spread-bps", type=float, default=None)
    parser.add_argument("--slippage-bps", type=float, default=None)
    parser.add_argument("--start-at", default=None)
    parser.add_argument("--end-at", default=None)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)

    symbols = tuple(item.strip().upper() for item in args.symbols.split(",") if item.strip())
    bars = _load_bars(
        data_source=args.data_source,
        data_path=Path(args.data_path),
        symbols=symbols,
        start_at=args.start_at,
        end_at=args.end_at,
        limit=args.limit,
    )
    if args.include_regime_context:
        bars = enrich_bars_with_regime_context(bars)
    result = write_strategy_regime_walk_forward_report(
        evaluate_strategy_regime_walk_forward_journals(
            args.journal,
            bars,
            run_id=args.run_id,
            train_window_bars=args.train_window_bars,
            test_window_bars=args.test_window_bars,
            step_window_bars=args.step_window_bars,
            min_folds=args.min_folds,
            min_passing_folds=args.min_passing_folds,
            min_total_trades=args.min_total_trades,
            initial_capital_eur=args.initial_capital_eur,
            order_notional_eur=args.order_notional_eur,
            cost_config=execution_cost_config_for_profile(
                args.cost_profile,
                fee_bps=args.fee_bps,
                spread_bps=args.spread_bps,
                slippage_bps=args.slippage_bps,
            ),
        ),
        args.output_dir,
    )
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0


def _evaluate_fold(
    fold_index: int,
    train_bars: Sequence[MarketBar],
    test_bars: Sequence[MarketBar],
    trades: Sequence[TradeRecord],
    *,
    run_id: str,
    initial_capital_eur: float,
    order_notional_eur: float,
    cost_config: ExecutionCostConfig | None,
) -> StrategyRegimeWalkForwardFold:
    test_start = test_bars[0].timestamp
    test_end = test_bars[-1].timestamp
    fold_trades = tuple(trade for trade in trades if test_start <= trade.closed_at <= test_end)
    strategy_report = analyze_strategy_regimes(fold_trades, run_id=f"{run_id}_fold_{fold_index:03d}")
    baseline_report = evaluate_strategy_regime_baselines(
        strategy_report,
        test_bars,
        initial_capital_eur=initial_capital_eur,
        order_notional_eur=order_notional_eur,
        cost_config=cost_config,
        seed_salt=f"{run_id}:fold:{fold_index}",
    )
    buckets = tuple(_fold_bucket(fold_index, bucket) for bucket in baseline_report.buckets)
    return StrategyRegimeWalkForwardFold(
        fold_index=fold_index,
        train_event_count=len(train_bars),
        test_event_count=len(test_bars),
        train_start_at=train_bars[0].timestamp.isoformat(),
        train_end_at=train_bars[-1].timestamp.isoformat(),
        test_start_at=test_start.isoformat(),
        test_end_at=test_end.isoformat(),
        bucket_count=len(buckets),
        buckets=buckets,
    )


def _fold_bucket(
    fold_index: int,
    bucket: StrategyRegimeBaselineBucket,
) -> StrategyRegimeWalkForwardFoldBucket:
    return StrategyRegimeWalkForwardFoldBucket(
        fold_index=fold_index,
        strategy_id=bucket.strategy_id,
        regime=bucket.regime,
        strategy_trade_count=bucket.strategy_trade_count,
        strategy_net_pnl_eur=bucket.strategy_net_pnl_eur,
        best_baseline_name=bucket.best_baseline_name,
        best_baseline_net_pnl_eur=bucket.best_baseline_net_pnl_eur,
        delta_vs_best_baseline_eur=bucket.delta_vs_best_baseline_eur,
        beats_no_trade=bucket.beats_no_trade,
        beats_best_baseline=bucket.beats_best_baseline,
    )


def _summaries(
    folds: Sequence[StrategyRegimeWalkForwardFold],
    *,
    min_folds: int,
    min_passing_folds: int,
    min_total_trades: int,
) -> tuple[StrategyRegimeWalkForwardSummary, ...]:
    grouped: dict[tuple[str, str], list[StrategyRegimeWalkForwardFoldBucket]] = {}
    for fold in folds:
        for bucket in fold.buckets:
            grouped.setdefault((bucket.strategy_id, bucket.regime), []).append(bucket)
    summaries = []
    for (strategy_id, regime), buckets in grouped.items():
        passing = sum(1 for bucket in buckets if bucket.beats_best_baseline is True and bucket.beats_no_trade)
        positive = sum(1 for bucket in buckets if bucket.beats_no_trade)
        total_trade_count = sum(bucket.strategy_trade_count for bucket in buckets)
        aggregate_net = sum(bucket.strategy_net_pnl_eur for bucket in buckets)
        deltas = [bucket.delta_vs_best_baseline_eur for bucket in buckets if bucket.delta_vs_best_baseline_eur is not None]
        aggregate_delta = sum(deltas)
        worst_delta = min(deltas) if deltas else None
        status, reason = _summary_status(
            evaluated_fold_count=len(buckets),
            passing_fold_count=passing,
            total_trade_count=total_trade_count,
            aggregate_net=aggregate_net,
            aggregate_delta=aggregate_delta,
            min_folds=min_folds,
            min_passing_folds=min_passing_folds,
            min_total_trades=min_total_trades,
        )
        summaries.append(
            StrategyRegimeWalkForwardSummary(
                strategy_id=strategy_id,
                regime=regime,
                evaluated_fold_count=len(buckets),
                passing_fold_count=passing,
                positive_fold_count=positive,
                total_trade_count=total_trade_count,
                aggregate_strategy_net_pnl_eur=aggregate_net,
                aggregate_delta_vs_best_baseline_eur=aggregate_delta,
                worst_delta_vs_best_baseline_eur=worst_delta,
                status=status,
                reason=reason,
            )
        )
    return tuple(
        sorted(
            summaries,
            key=lambda item: (
                item.status != "walk_forward_baseline_passed",
                item.aggregate_delta_vs_best_baseline_eur,
                item.strategy_id,
                item.regime,
            ),
        )
    )


def _summary_status(
    *,
    evaluated_fold_count: int,
    passing_fold_count: int,
    total_trade_count: int,
    aggregate_net: float,
    aggregate_delta: float,
    min_folds: int,
    min_passing_folds: int,
    min_total_trades: int,
) -> tuple[str, str]:
    if evaluated_fold_count < min_folds:
        return "keep_testing", "insufficient_evaluated_folds"
    if total_trade_count < min_total_trades:
        return "keep_testing", "insufficient_total_trades"
    if passing_fold_count < min_passing_folds:
        return "modify", "insufficient_baseline_passing_folds"
    if aggregate_net <= 0.0:
        return "modify", "non_positive_aggregate_net_pnl"
    if aggregate_delta <= 0.0:
        return "modify", "does_not_beat_baselines_in_aggregate"
    return "walk_forward_baseline_passed", "baseline_walk_forward_criteria_passed_for_human_review"


def _fold_windows(
    bars: Sequence[MarketBar],
    *,
    train_window_bars: int,
    test_window_bars: int,
    step_window_bars: int | None,
) -> list[tuple[list[MarketBar], list[MarketBar]]]:
    if len(bars) < train_window_bars + test_window_bars:
        return []
    step = step_window_bars or test_window_bars
    windows = []
    start = 0
    while start + train_window_bars + test_window_bars <= len(bars):
        train_end = start + train_window_bars
        test_end = train_end + test_window_bars
        windows.append((list(bars[start:train_end]), list(bars[train_end:test_end])))
        start += step
    return windows


def _chronological_bars(bars: Sequence[MarketBar]) -> list[MarketBar]:
    return sorted(bars, key=lambda bar: (bar.timestamp, bar.symbol, bar.timeframe))


def _fmt(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.6f}"


if __name__ == "__main__":
    raise SystemExit(main())
