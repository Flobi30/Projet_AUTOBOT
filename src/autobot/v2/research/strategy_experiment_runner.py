"""Research-only experiments for trend and mean-reversion families.

This runner applies the same cost-aware validation discipline used by the grid
experiment campaign to non-grid strategy families. It does not touch official
paper/live runtime components, does not mutate the registry, and never grants
live permission.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Sequence

from .dataset_builder import DatasetBuildConfig, DatasetBuildResult, build_dataset_from_state_db
from .execution_cost_model import ExecutionCostConfig
from .loss_attribution import LossAttributionResult, analyze_trade_journal
from .strategy_scorecard import StrategyEvidence, StrategyScorecardResult, score_strategy
from .validation_runner import ValidationRunnerConfig, run_validation
from .walk_forward import WalkForwardResult


SUPPORTED_EXPERIMENT_STRATEGIES = ("trend", "mean_reversion")
StrategyExperimentName = Literal["trend", "mean_reversion"]


@dataclass(frozen=True)
class StrategyExperimentVariant:
    strategy: StrategyExperimentName
    name: str
    family: str
    strategy_config: dict[str, Any] = field(default_factory=dict)
    notes: str = ""

    def __post_init__(self) -> None:
        if self.strategy not in SUPPORTED_EXPERIMENT_STRATEGIES:
            raise ValueError(f"unsupported experiment strategy: {self.strategy}")
        if not self.name.strip():
            raise ValueError("variant name must not be empty")
        if not self.family.strip():
            raise ValueError("family must not be empty")

    def config_for_symbol(self, symbol: str) -> dict[str, Any]:
        config = dict(self.strategy_config)
        config.setdefault("strategy_id", f"{_strategy_id(self.strategy)}__{self.name}")
        return config

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "name": self.name,
            "family": self.family,
            "strategy_config": dict(self.strategy_config),
            "notes": self.notes,
        }


@dataclass(frozen=True)
class StrategyExperimentConfig:
    run_id: str
    state_db_path: Path
    symbols: tuple[str, ...]
    strategies: tuple[StrategyExperimentName, ...] = SUPPORTED_EXPERIMENT_STRATEGIES
    timeframe: str = "5m"
    output_dir: Path = Path("reports/research/strategy_experiments")
    dataset_output_dir: Path = Path("data/research/strategy_experiments")
    initial_capital_eur: float = 1_000.0
    order_notional_eur: float = 100.0
    cost_config: ExecutionCostConfig = field(
        default_factory=lambda: ExecutionCostConfig(
            taker_fee_bps=16.0,
            fallback_spread_bps=8.0,
            slippage_bps=4.0,
        )
    )
    min_closed_trades: int = 30
    candidate_min_closed_trades: int = 100
    candidate_min_profit_factor: float = 1.20
    candidate_min_mfe_to_cost: float = 1.50
    candidate_max_drawdown_pct: float = 12.0
    candidate_min_walk_forward_positive_fold_ratio: float = 0.60
    max_variants_per_strategy: int | None = None
    start_at: str | None = None
    end_at: str | None = None
    limit: int | None = None
    include_regime_context: bool = True
    train_window_bars: int = 200
    test_window_bars: int = 100
    step_window_bars: int | None = None
    min_folds: int = 3

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id must not be empty")
        if not self.symbols:
            raise ValueError("symbols must not be empty")
        if not self.strategies:
            raise ValueError("strategies must not be empty")
        for strategy in self.strategies:
            if strategy not in SUPPORTED_EXPERIMENT_STRATEGIES:
                raise ValueError(f"unsupported experiment strategy: {strategy}")
        if self.initial_capital_eur <= 0.0:
            raise ValueError("initial_capital_eur must be positive")
        if self.order_notional_eur <= 0.0:
            raise ValueError("order_notional_eur must be positive")
        if self.min_closed_trades <= 0 or self.candidate_min_closed_trades <= 0:
            raise ValueError("trade thresholds must be positive")
        if self.max_variants_per_strategy is not None and self.max_variants_per_strategy <= 0:
            raise ValueError("max_variants_per_strategy must be positive when provided")
        self.cost_config.validate()


@dataclass(frozen=True)
class StrategyExperimentCell:
    run_id: str
    strategy: str
    variant_name: str
    family: str
    symbol: str
    status: str
    decision: str
    reason: str
    bar_count: int
    signal_count: int
    fill_count: int
    trade_count: int
    gross_pnl_eur: float
    net_pnl_eur: float
    fees_eur: float
    spread_cost_eur: float
    slippage_eur: float
    profit_factor: float | None
    winrate_pct: float | None
    expectancy_eur: float | None
    max_drawdown_pct: float
    baseline_name: str | None
    baseline_return_pct: float | None
    baseline_delta_pct: float | None
    beats_baseline: bool | None
    average_mfe_to_cost_ratio: float | None
    average_exit_capture_bps: float | None
    average_mfe_giveback_bps: float | None
    cost_flipped_trade_count: int
    primary_failure_mode: str | None
    scorecard: dict[str, Any]
    backtest_report_path: str | None
    journal_path: str | None
    config: dict[str, Any]
    candidate_status: str = "fail"
    candidate_reasons: tuple[str, ...] = ()
    overfit_risk: str = "not_evaluated"
    walk_forward: dict[str, Any] | None = None
    live_promotion_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["candidate_reasons"] = list(self.candidate_reasons)
        return data


@dataclass(frozen=True)
class StrategyExperimentSummary:
    strategy: str
    variant_name: str
    family: str
    cell_count: int
    trade_count: int
    net_pnl_eur: float
    gross_pnl_eur: float
    profit_factor_proxy: float | None
    max_drawdown_pct: float
    average_mfe_to_cost_ratio: float | None
    average_exit_capture_bps: float | None
    pass_count: int
    best_symbol: str | None
    overfit_risk: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StrategyExperimentReport:
    run_id: str
    timestamp: str
    dataset: dict[str, Any]
    timeframe: str
    symbols: tuple[str, ...]
    strategies: tuple[str, ...]
    cost_config: dict[str, float]
    variants: tuple[dict[str, Any], ...]
    cells: tuple[StrategyExperimentCell, ...]
    summaries: tuple[StrategyExperimentSummary, ...]
    best_by_strategy_symbol: dict[str, dict[str, Any]]
    rejected_variants: tuple[dict[str, Any], ...]
    conclusion: str
    json_report_path: str | None = None
    markdown_report_path: str | None = None
    safety_notes: tuple[str, ...] = (
        "Research-only trend/mean-reversion experiments.",
        "No runtime paper/live service is modified or restarted.",
        "No strategy registry mutation is performed.",
        "No Kraken order can be created by this command.",
        "No live trading permission is granted.",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "dataset": dict(self.dataset),
            "timeframe": self.timeframe,
            "symbols": list(self.symbols),
            "strategies": list(self.strategies),
            "cost_config": dict(self.cost_config),
            "variants": [dict(item) for item in self.variants],
            "cells": [cell.to_dict() for cell in self.cells],
            "summaries": [summary.to_dict() for summary in self.summaries],
            "best_by_strategy_symbol": self.best_by_strategy_symbol,
            "rejected_variants": [dict(item) for item in self.rejected_variants],
            "conclusion": self.conclusion,
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
            "safety_notes": list(self.safety_notes),
        }


def build_strategy_experiment_variants(
    strategies: Sequence[StrategyExperimentName] = SUPPORTED_EXPERIMENT_STRATEGIES,
    *,
    max_variants_per_strategy: int | None = None,
) -> tuple[StrategyExperimentVariant, ...]:
    variants: list[StrategyExperimentVariant] = []
    if "trend" in strategies:
        variants.extend(_trend_variants(max_variants=max_variants_per_strategy))
    if "mean_reversion" in strategies:
        variants.extend(_mean_reversion_variants(max_variants=max_variants_per_strategy))
    return tuple(variants)


def run_strategy_experiments(config: StrategyExperimentConfig) -> StrategyExperimentReport:
    dataset_result = build_dataset_from_state_db(
        DatasetBuildConfig(
            run_id=config.run_id,
            state_db_path=config.state_db_path,
            output_dir=config.dataset_output_dir,
            symbols=config.symbols,
            timeframes=(config.timeframe,),
            start_at=config.start_at,
            end_at=config.end_at,
            limit=config.limit,
            export_csv=True,
            export_parquet=False,
            canonicalize_symbols=True,
        )
    )
    dataset_csv_path = _dataset_csv_path(dataset_result, config.timeframe)
    variants = build_strategy_experiment_variants(
        config.strategies,
        max_variants_per_strategy=config.max_variants_per_strategy,
    )
    cells: list[StrategyExperimentCell] = []
    baseline_by_strategy_symbol: dict[tuple[str, str], StrategyExperimentCell] = {}

    for variant in variants:
        for symbol in config.symbols:
            cell = _run_backtest_cell(config, variant, dataset_csv_path, symbol.upper())
            cells.append(cell)
            if variant.family == "baseline_current":
                baseline_by_strategy_symbol[(variant.strategy, symbol.upper())] = cell

    evaluated_cells: list[StrategyExperimentCell] = []
    for cell in cells:
        baseline = baseline_by_strategy_symbol.get((cell.strategy, cell.symbol))
        provisional_status, provisional_reasons = _candidate_precheck(config, cell, baseline)
        if provisional_status == "candidate_precheck_passed":
            walk_forward = _run_walk_forward_cell(
                config,
                _variant_by_key(variants, cell.strategy, cell.variant_name),
                dataset_csv_path,
                cell.symbol,
            )
            final_status, final_reasons = _candidate_final_status(config, cell, baseline, walk_forward)
            evaluated_cells.append(
                _replace_cell_candidate(
                    cell,
                    candidate_status=final_status,
                    candidate_reasons=final_reasons,
                    walk_forward=walk_forward.to_dict(),
                    overfit_risk=_cell_overfit_risk(cell, baseline, walk_forward),
                )
            )
        else:
            evaluated_cells.append(
                _replace_cell_candidate(
                    cell,
                    candidate_status="fail",
                    candidate_reasons=provisional_reasons,
                    overfit_risk=_cell_overfit_risk(cell, baseline, None),
                )
            )

    summaries = _summaries(evaluated_cells)
    report = StrategyExperimentReport(
        run_id=config.run_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        dataset=dataset_result.to_dict(),
        timeframe=config.timeframe,
        symbols=tuple(symbol.upper() for symbol in config.symbols),
        strategies=tuple(config.strategies),
        cost_config=config.cost_config.to_dict(),
        variants=tuple(variant.to_dict() for variant in variants),
        cells=tuple(evaluated_cells),
        summaries=summaries,
        best_by_strategy_symbol=_best_by_strategy_symbol(evaluated_cells),
        rejected_variants=tuple(_rejected_variant_payload(summary) for summary in summaries if summary.pass_count <= 0),
        conclusion=_conclusion(evaluated_cells),
    )
    return write_strategy_experiment_reports(report, config.output_dir)


def write_strategy_experiment_reports(
    report: StrategyExperimentReport,
    output_dir: str | Path,
) -> StrategyExperimentReport:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / f"{report.run_id}.json"
    md_path = output / f"{report.run_id}.md"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(render_strategy_experiment_report(report), encoding="utf-8")
    return StrategyExperimentReport(
        run_id=report.run_id,
        timestamp=report.timestamp,
        dataset=report.dataset,
        timeframe=report.timeframe,
        symbols=report.symbols,
        strategies=report.strategies,
        cost_config=report.cost_config,
        variants=report.variants,
        cells=report.cells,
        summaries=report.summaries,
        best_by_strategy_symbol=report.best_by_strategy_symbol,
        rejected_variants=report.rejected_variants,
        conclusion=report.conclusion,
        json_report_path=str(json_path),
        markdown_report_path=str(md_path),
        safety_notes=report.safety_notes,
    )


def render_strategy_experiment_report(report: StrategyExperimentReport) -> str:
    top = sorted(report.summaries, key=_summary_sort_key)[:30]
    lines = [
        f"# Strategy Experiment Report - {report.run_id}",
        "",
        "## Scope",
        "",
        "Research-only trend/mean-reversion campaign. This report does not authorize paper promotion, live trading,",
        "runtime sizing changes, risk-manager changes, or registry mutation.",
        "",
        "## Dataset And Costs",
        "",
        f"- Timeframe: `{report.timeframe}`",
        f"- Symbols: `{', '.join(report.symbols)}`",
        f"- Strategies: `{', '.join(report.strategies)}`",
        f"- Cost config: `{json.dumps(report.cost_config, sort_keys=True)}`",
        f"- Dataset manifest: `{report.dataset.get('manifest_path')}`",
        "",
        "## Top Variants",
        "",
        "| Strategy | Variant | Family | Trades | Net PnL | PF Proxy | Max DD | MFE/Cost | Exit Capture | Passes | Best Symbol | Risk |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for item in top:
        lines.append(
            f"| {item.strategy} | {item.variant_name} | {item.family} | {item.trade_count} | {_fmt(item.net_pnl_eur)} | "
            f"{_fmt(item.profit_factor_proxy)} | {_fmt(item.max_drawdown_pct)} | {_fmt(item.average_mfe_to_cost_ratio)} | "
            f"{_fmt(item.average_exit_capture_bps)} | {item.pass_count} | {item.best_symbol or ''} | {item.overfit_risk} |"
        )
    lines.extend(
        [
            "",
            "## Best By Strategy/Symbol",
            "",
            "| Strategy/Symbol | Variant | Family | Trades | Net PnL | PF | MFE/Cost | Exit Capture | Candidate | Reasons |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
        ]
    )
    for key, item in sorted(report.best_by_strategy_symbol.items()):
        lines.append(
            f"| {key} | {item['variant_name']} | {item['family']} | {item['trade_count']} | "
            f"{_fmt(item['net_pnl_eur'])} | {_fmt(item.get('profit_factor'))} | "
            f"{_fmt(item.get('average_mfe_to_cost_ratio'))} | {_fmt(item.get('average_exit_capture_bps'))} | "
            f"{item['candidate_status']} | {', '.join(item.get('candidate_reasons') or [])} |"
        )
    lines.extend(["", "## Conclusion", "", report.conclusion, "", "## Safety", ""])
    lines.extend(f"- {note}" for note in report.safety_notes)
    return "\n".join(lines) + "\n"


def _trend_variants(*, max_variants: int | None) -> list[StrategyExperimentVariant]:
    variants = [
        StrategyExperimentVariant("trend", "baseline_current", "baseline_current"),
        StrategyExperimentVariant("trend", "confirm_30", "stronger_breakout_confirmation", {"confirm_bps": 30.0}),
        StrategyExperimentVariant("trend", "confirm_50", "stronger_breakout_confirmation", {"confirm_bps": 50.0}),
        StrategyExperimentVariant("trend", "momentum_40", "stronger_momentum_filter", {"min_momentum_bps": 40.0}),
        StrategyExperimentVariant("trend", "momentum_60", "stronger_momentum_filter", {"min_momentum_bps": 60.0}),
        StrategyExperimentVariant("trend", "min_atr_15", "min_volatility_filter", {"min_atr_bps": 15.0}),
        StrategyExperimentVariant("trend", "min_atr_30", "min_volatility_filter", {"min_atr_bps": 30.0}),
        StrategyExperimentVariant(
            "trend",
            "longer_breakout_36",
            "longer_timeframe_proxy",
            {"breakout_window": 36, "exit_window": 18, "momentum_window": 12},
        ),
        StrategyExperimentVariant(
            "trend",
            "longer_breakout_48",
            "longer_timeframe_proxy",
            {"breakout_window": 48, "exit_window": 24, "momentum_window": 16},
        ),
        StrategyExperimentVariant(
            "trend",
            "cost_buffer_tp_80",
            "exit_capture",
            {"exit_mode": "cost_buffer_tp", "take_profit_bps": 80.0, "trailing_atr_mult": 100.0, "stop_atr_mult": 3.0},
        ),
        StrategyExperimentVariant(
            "trend",
            "mfe_trailing_70_35",
            "exit_capture",
            {"exit_mode": "mfe_trailing", "mfe_trailing_activation_bps": 70.0, "mfe_trailing_drawdown_bps": 35.0},
        ),
        StrategyExperimentVariant(
            "trend",
            "time_stop_24",
            "exit_capture",
            {"exit_mode": "time_stop", "max_hold_bars": 24, "min_profit_before_time_exit_bps": 0.0},
        ),
    ]
    return variants[:max_variants] if max_variants is not None else variants


def _mean_reversion_variants(*, max_variants: int | None) -> list[StrategyExperimentVariant]:
    variants = [
        StrategyExperimentVariant("mean_reversion", "baseline_current", "baseline_current"),
        StrategyExperimentVariant("mean_reversion", "window_30", "longer_window", {"window": 30}),
        StrategyExperimentVariant("mean_reversion", "window_40", "longer_window", {"window": 40}),
        StrategyExperimentVariant("mean_reversion", "entry_z_2_5", "stricter_deviation", {"entry_z": 2.5}),
        StrategyExperimentVariant("mean_reversion", "entry_z_3_0", "stricter_deviation", {"entry_z": 3.0}),
        StrategyExperimentVariant("mean_reversion", "min_atr_8", "min_volatility_filter", {"min_atr_bps": 8.0}),
        StrategyExperimentVariant("mean_reversion", "min_atr_15", "min_volatility_filter", {"min_atr_bps": 15.0}),
        StrategyExperimentVariant(
            "mean_reversion",
            "trend_cap_80",
            "trend_block_filter",
            {"max_abs_trend_bps": 80.0},
        ),
        StrategyExperimentVariant(
            "mean_reversion",
            "trend_cap_120",
            "trend_block_filter",
            {"max_abs_trend_bps": 120.0},
        ),
        StrategyExperimentVariant(
            "mean_reversion",
            "expected_edge_50",
            "cost_aware_edge_filter",
            {"min_expected_edge_bps": 50.0},
        ),
        StrategyExperimentVariant(
            "mean_reversion",
            "expected_edge_80",
            "cost_aware_edge_filter",
            {"min_expected_edge_bps": 80.0},
        ),
        StrategyExperimentVariant(
            "mean_reversion",
            "strict_combo",
            "combined_quality_filter",
            {"window": 30, "entry_z": 2.5, "min_atr_bps": 8.0, "max_abs_trend_bps": 120.0, "min_expected_edge_bps": 50.0},
        ),
    ]
    return variants[:max_variants] if max_variants is not None else variants


def _run_backtest_cell(
    config: StrategyExperimentConfig,
    variant: StrategyExperimentVariant,
    dataset_csv_path: Path,
    symbol: str,
) -> StrategyExperimentCell:
    run_id = f"{config.run_id}_{variant.strategy}_{variant.name}_{symbol}".replace("/", "_")
    strategy_config = variant.config_for_symbol(symbol)
    runner_result = run_validation(
        ValidationRunnerConfig(
            run_id=run_id,
            strategy=variant.strategy,
            data_source="csv",
            data_path=dataset_csv_path,
            symbol=symbol,
            dataset_id=f"strategy_experiment:{config.timeframe}:{symbol}:{variant.strategy}:{variant.name}",
            mode="backtest",
            output_dir=config.output_dir / "cells",
            initial_capital_eur=config.initial_capital_eur,
            order_notional_eur=config.order_notional_eur,
            min_closed_trades=config.min_closed_trades,
            min_profit_factor=config.candidate_min_profit_factor,
            max_drawdown_pct=config.candidate_max_drawdown_pct,
            cost_config=config.cost_config,
            strategy_config=strategy_config,
            include_regime_context=config.include_regime_context,
        )
    )
    result = runner_result.result
    attribution = _loss_attribution(result.journal_path, run_id=run_id)
    scorecard = score_strategy(
        StrategyEvidence.from_metrics(
            result.strategy_id,
            result.metrics,
            source=f"strategy_experiment:{variant.strategy}:{variant.name}",
            fees_included=True,
            slippage_included=True,
            baseline_included=True,
            out_of_sample_included=False,
        )
    )
    metrics = result.metrics
    return StrategyExperimentCell(
        run_id=result.run_id,
        strategy=variant.strategy,
        variant_name=variant.name,
        family=variant.family,
        symbol=symbol,
        status="ok",
        decision=result.decision.status,
        reason=result.decision.reason,
        bar_count=runner_result.bar_count,
        signal_count=result.signal_count,
        fill_count=result.fill_count,
        trade_count=result.trade_count,
        gross_pnl_eur=metrics.total_gross_pnl_eur,
        net_pnl_eur=metrics.total_net_pnl_eur,
        fees_eur=metrics.total_fees_eur,
        spread_cost_eur=metrics.total_spread_cost_eur,
        slippage_eur=metrics.total_slippage_eur,
        profit_factor=metrics.profit_factor,
        winrate_pct=metrics.winrate_pct,
        expectancy_eur=metrics.expectancy_eur,
        max_drawdown_pct=metrics.max_drawdown_pct,
        baseline_name=metrics.baseline_name,
        baseline_return_pct=metrics.baseline_return_pct,
        baseline_delta_pct=metrics.baseline_delta_pct,
        beats_baseline=metrics.beats_baseline,
        average_mfe_to_cost_ratio=attribution.average_mfe_to_cost_ratio if attribution else None,
        average_exit_capture_bps=attribution.average_exit_capture_bps if attribution else None,
        average_mfe_giveback_bps=attribution.average_mfe_giveback_bps if attribution else None,
        cost_flipped_trade_count=attribution.cost_flipped_trade_count if attribution else 0,
        primary_failure_mode=_primary_failure_mode(attribution),
        scorecard=scorecard.to_dict(),
        backtest_report_path=result.markdown_report_path,
        journal_path=result.journal_path,
        config=strategy_config,
        live_promotion_allowed=False,
    )


def _run_walk_forward_cell(
    config: StrategyExperimentConfig,
    variant: StrategyExperimentVariant,
    dataset_csv_path: Path,
    symbol: str,
) -> WalkForwardResult:
    run_id = f"{config.run_id}_{variant.strategy}_{variant.name}_{symbol}_wf".replace("/", "_")
    runner_result = run_validation(
        ValidationRunnerConfig(
            run_id=run_id,
            strategy=variant.strategy,
            data_source="csv",
            data_path=dataset_csv_path,
            symbol=symbol,
            dataset_id=f"strategy_experiment:{config.timeframe}:{symbol}:{variant.strategy}:{variant.name}:walk_forward",
            mode="walk_forward",
            output_dir=config.output_dir / "walk_forward",
            initial_capital_eur=config.initial_capital_eur,
            order_notional_eur=config.order_notional_eur,
            min_closed_trades=config.min_closed_trades,
            min_profit_factor=config.candidate_min_profit_factor,
            max_drawdown_pct=config.candidate_max_drawdown_pct,
            cost_config=config.cost_config,
            strategy_config=variant.config_for_symbol(symbol),
            train_window_bars=config.train_window_bars,
            test_window_bars=config.test_window_bars,
            step_window_bars=config.step_window_bars,
            min_folds=config.min_folds,
            min_passing_folds=max(1, math.ceil(config.min_folds * config.candidate_min_walk_forward_positive_fold_ratio)),
            include_regime_context=config.include_regime_context,
        )
    )
    return runner_result.result


def _candidate_precheck(
    config: StrategyExperimentConfig,
    cell: StrategyExperimentCell,
    baseline: StrategyExperimentCell | None,
) -> tuple[str, tuple[str, ...]]:
    reasons = tuple(reason for reason in _candidate_reasons(config, cell, baseline) if reason != "walk_forward_not_run")
    if reasons:
        return "fail", reasons
    return "candidate_precheck_passed", ()


def _candidate_final_status(
    config: StrategyExperimentConfig,
    cell: StrategyExperimentCell,
    baseline: StrategyExperimentCell | None,
    walk_forward: WalkForwardResult,
) -> tuple[str, tuple[str, ...]]:
    reasons = [reason for reason in _candidate_reasons(config, cell, baseline) if reason != "walk_forward_not_run"]
    passing_ratio = (walk_forward.passing_fold_count / walk_forward.fold_count) if walk_forward.fold_count else 0.0
    if passing_ratio < config.candidate_min_walk_forward_positive_fold_ratio:
        reasons.append("walk_forward_positive_fold_ratio_below_60pct")
    if walk_forward.aggregate_net_pnl_eur <= 0.0:
        reasons.append("walk_forward_net_pnl_not_positive")
    if walk_forward.decision.live_promotion_allowed:
        reasons.append("unexpected_live_promotion_allowed")
    return ("candidate_shadow_only" if not reasons else "fail", tuple(reasons))


def _candidate_reasons(
    config: StrategyExperimentConfig,
    cell: StrategyExperimentCell,
    baseline: StrategyExperimentCell | None,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if cell.net_pnl_eur <= 0.0:
        reasons.append("net_pnl_not_positive")
    if cell.profit_factor is None or cell.profit_factor < config.candidate_min_profit_factor:
        reasons.append("profit_factor_below_1_20")
    if cell.average_mfe_to_cost_ratio is None or cell.average_mfe_to_cost_ratio < config.candidate_min_mfe_to_cost:
        reasons.append("mfe_to_cost_below_1_5")
    if cell.average_exit_capture_bps is None or cell.average_exit_capture_bps <= 0.0:
        reasons.append("exit_capture_not_positive")
    if cell.max_drawdown_pct > config.candidate_max_drawdown_pct:
        reasons.append("max_drawdown_above_12pct")
    if cell.trade_count < config.candidate_min_closed_trades:
        reasons.append("insufficient_trade_count")
    if cell.beats_baseline is False:
        reasons.append("does_not_beat_baseline")
    if baseline and cell.net_pnl_eur <= baseline.net_pnl_eur:
        reasons.append("does_not_improve_family_baseline")
    if cell.live_promotion_allowed:
        reasons.append("unexpected_live_promotion_allowed")
    reasons.append("walk_forward_not_run")
    return tuple(reasons)


def _replace_cell_candidate(
    cell: StrategyExperimentCell,
    *,
    candidate_status: str,
    candidate_reasons: Sequence[str],
    overfit_risk: str,
    walk_forward: dict[str, Any] | None = None,
) -> StrategyExperimentCell:
    return StrategyExperimentCell(
        **{
            **cell.to_dict(),
            "candidate_status": candidate_status,
            "candidate_reasons": tuple(candidate_reasons),
            "overfit_risk": overfit_risk,
            "walk_forward": walk_forward,
            "live_promotion_allowed": False,
        }
    )


def _summaries(cells: Sequence[StrategyExperimentCell]) -> tuple[StrategyExperimentSummary, ...]:
    grouped: dict[tuple[str, str], list[StrategyExperimentCell]] = {}
    for cell in cells:
        grouped.setdefault((cell.strategy, cell.variant_name), []).append(cell)
    summaries: list[StrategyExperimentSummary] = []
    for (_strategy, _variant_name), group in grouped.items():
        positive_net = sum(max(0.0, cell.net_pnl_eur) for cell in group)
        negative_net = abs(sum(min(0.0, cell.net_pnl_eur) for cell in group))
        best = max(group, key=lambda cell: (cell.net_pnl_eur, cell.profit_factor or 0.0, cell.trade_count))
        summaries.append(
            StrategyExperimentSummary(
                strategy=group[0].strategy,
                variant_name=group[0].variant_name,
                family=group[0].family,
                cell_count=len(group),
                trade_count=sum(cell.trade_count for cell in group),
                net_pnl_eur=sum(cell.net_pnl_eur for cell in group),
                gross_pnl_eur=sum(cell.gross_pnl_eur for cell in group),
                profit_factor_proxy=(positive_net / negative_net) if negative_net > 0.0 else None,
                max_drawdown_pct=max(cell.max_drawdown_pct for cell in group),
                average_mfe_to_cost_ratio=_weighted_average(
                    group,
                    value_func=lambda cell: cell.average_mfe_to_cost_ratio,
                    weight_func=lambda cell: cell.trade_count,
                ),
                average_exit_capture_bps=_weighted_average(
                    group,
                    value_func=lambda cell: cell.average_exit_capture_bps,
                    weight_func=lambda cell: cell.trade_count,
                ),
                pass_count=sum(1 for cell in group if cell.candidate_status == "candidate_shadow_only"),
                best_symbol=best.symbol if group else None,
                overfit_risk=_variant_overfit_risk(group),
            )
        )
    return tuple(sorted(summaries, key=_summary_sort_key))


def _best_by_strategy_symbol(cells: Sequence[StrategyExperimentCell]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[StrategyExperimentCell]] = {}
    for cell in cells:
        grouped.setdefault(f"{cell.strategy}:{cell.symbol}", []).append(cell)
    result: dict[str, dict[str, Any]] = {}
    for key, group in grouped.items():
        best = max(
            group,
            key=lambda cell: (
                cell.candidate_status == "candidate_shadow_only",
                cell.net_pnl_eur,
                cell.profit_factor or 0.0,
                cell.average_mfe_to_cost_ratio or 0.0,
            ),
        )
        result[key] = {
            "variant_name": best.variant_name,
            "family": best.family,
            "trade_count": best.trade_count,
            "net_pnl_eur": best.net_pnl_eur,
            "gross_pnl_eur": best.gross_pnl_eur,
            "profit_factor": best.profit_factor,
            "max_drawdown_pct": best.max_drawdown_pct,
            "average_mfe_to_cost_ratio": best.average_mfe_to_cost_ratio,
            "average_exit_capture_bps": best.average_exit_capture_bps,
            "candidate_status": best.candidate_status,
            "candidate_reasons": list(best.candidate_reasons),
            "overfit_risk": best.overfit_risk,
        }
    return result


def _conclusion(cells: Sequence[StrategyExperimentCell]) -> str:
    candidates = [cell for cell in cells if cell.candidate_status == "candidate_shadow_only"]
    if not candidates:
        return (
            "No trend or mean-reversion variant passed the full shadow-candidate criteria on this dataset after costs. "
            "Keep them in research/shadow until a variant passes net-PnL, PF, MFE/Cost, exit-capture, baseline, "
            "sample-size and walk-forward checks."
        )
    names = sorted({f"{cell.strategy}/{cell.variant_name}/{cell.symbol}" for cell in candidates})
    return (
        "Research-only shadow candidates were found, with no live permission. "
        f"Candidate cells: {', '.join(names)}. Human review and longer paper evidence are required."
    )


def _dataset_csv_path(result: DatasetBuildResult, timeframe: str) -> Path:
    export = next((item for item in result.exports if item.timeframe.lower() == timeframe.lower()), None)
    if export is None or not export.csv_path:
        raise ValueError(f"dataset export for timeframe {timeframe!r} did not produce a CSV path")
    return Path(export.csv_path)


def _loss_attribution(path: str | None, *, run_id: str) -> LossAttributionResult | None:
    if not path:
        return None
    return analyze_trade_journal(path, run_id=run_id)


def _primary_failure_mode(attribution: LossAttributionResult | None) -> str | None:
    if attribution is None or not attribution.by_failure_mode:
        return None
    return max(attribution.by_failure_mode, key=lambda bucket: bucket.trade_count).key


def _variant_by_key(
    variants: Sequence[StrategyExperimentVariant],
    strategy: str,
    name: str,
) -> StrategyExperimentVariant:
    for variant in variants:
        if variant.strategy == strategy and variant.name == name:
            return variant
    raise KeyError(f"{strategy}:{name}")


def _cell_overfit_risk(
    cell: StrategyExperimentCell,
    baseline: StrategyExperimentCell | None,
    walk_forward: WalkForwardResult | None,
) -> str:
    if cell.trade_count < 30:
        return "tiny_sample"
    if walk_forward is None:
        return "walk_forward_missing"
    if walk_forward.fold_count < 3:
        return "insufficient_walk_forward_folds"
    if baseline and cell.net_pnl_eur > 0.0 and baseline.net_pnl_eur <= 0.0 and cell.trade_count < 100:
        return "parameter_sample_fragile"
    return "controlled"


def _variant_overfit_risk(group: Sequence[StrategyExperimentCell]) -> str:
    positive = [cell for cell in group if cell.net_pnl_eur > 0.0]
    total_positive = sum(cell.net_pnl_eur for cell in positive)
    if total_positive <= 0.0:
        return "no_positive_evidence"
    largest_share = max(cell.net_pnl_eur for cell in positive) / total_positive
    if largest_share >= 0.70:
        return "single_symbol_dominated"
    if sum(cell.trade_count for cell in group) < 100:
        return "small_sample"
    return "controlled"


def _rejected_variant_payload(summary: StrategyExperimentSummary) -> dict[str, Any]:
    reasons = []
    if summary.net_pnl_eur <= 0.0:
        reasons.append("aggregate_net_pnl_not_positive")
    if summary.average_mfe_to_cost_ratio is None or summary.average_mfe_to_cost_ratio < 1.5:
        reasons.append("aggregate_mfe_to_cost_below_1_5")
    if summary.average_exit_capture_bps is None or summary.average_exit_capture_bps <= 0.0:
        reasons.append("aggregate_exit_capture_not_positive")
    if summary.pass_count <= 0:
        reasons.append("no_candidate_shadow_cells")
    if summary.overfit_risk != "controlled":
        reasons.append(summary.overfit_risk)
    return {
        "strategy": summary.strategy,
        "variant_name": summary.variant_name,
        "family": summary.family,
        "reason": ", ".join(reasons) or "criteria_not_met",
    }


def _weighted_average(
    values: Sequence[StrategyExperimentCell],
    *,
    value_func,
    weight_func,
) -> float | None:
    numerator = 0.0
    denominator = 0.0
    for item in values:
        value = value_func(item)
        if value is None:
            continue
        weight = max(0.0, float(weight_func(item)))
        if weight <= 0.0:
            continue
        numerator += float(value) * weight
        denominator += weight
    return numerator / denominator if denominator > 0.0 else None


def _summary_sort_key(summary: StrategyExperimentSummary) -> tuple[float, float, float, float, float]:
    return (
        -float(summary.pass_count),
        -float(summary.net_pnl_eur),
        -float(summary.profit_factor_proxy or -1.0),
        float(summary.max_drawdown_pct),
        -float(summary.average_mfe_to_cost_ratio or -1.0),
    )


def _strategy_id(strategy: str) -> str:
    return {
        "trend": "trend_momentum",
        "mean_reversion": "mean_reversion",
    }[strategy]


def _fmt(value: float | int | None) -> str:
    if value is None:
        return ""
    return f"{float(value):.6f}"
