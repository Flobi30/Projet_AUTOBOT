"""Research-only grid improvement experiments for AUTOBOT.

This module deliberately stays outside runtime paper/live execution. It builds
datasets from persisted market samples, replays conservative grid variants
through the research validation stack, compares them with baselines, attributes
losses, and produces reports that can recommend shadow-only candidates or grid
disablement. It never mutates the strategy registry and never grants live
permission.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from .dataset_builder import DatasetBuildConfig, DatasetBuildResult, build_dataset_from_state_db
from .execution_cost_model import ExecutionCostConfig
from .loss_attribution import LossAttributionResult, analyze_trade_journal
from .strategy_scorecard import StrategyEvidence, StrategyScorecardResult, score_strategy
from .validation_runner import ValidationRunnerConfig, run_validation
from .walk_forward import WalkForwardResult


GRID_EXPERIMENT_FAMILIES = (
    "baseline_current",
    "wider_grid_spacing",
    "stronger_support_confirmation",
    "min_volatility_filter",
    "max_volatility_filter",
    "trend_down_block_filter",
    "regime_range_only_filter",
    "cost_aware_min_mfe_filter",
    "wider_take_profit",
    "mfe_trailing_exit",
    "time_stop_if_no_mfe",
    "symbol_specific_filters",
)
STRICT_ENTRY_SYMBOLS = {"ATOMEUR", "BTCZEUR", "ADAEUR", "AVAXEUR"}
EXIT_CAPTURE_SYMBOLS = {"XLMZEUR"}


@dataclass(frozen=True)
class GridExperimentVariant:
    name: str
    family: str
    strategy_config: dict[str, Any] = field(default_factory=dict)
    symbol_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("variant name must not be empty")
        if self.family not in GRID_EXPERIMENT_FAMILIES:
            raise ValueError(f"unsupported grid experiment family: {self.family}")

    def config_for_symbol(self, symbol: str, *, estimated_round_trip_cost_bps: float) -> dict[str, Any]:
        config = dict(self.strategy_config)
        config.setdefault("estimated_round_trip_cost_bps", estimated_round_trip_cost_bps)
        config.setdefault("strategy_id", f"dynamic_grid__{self.name}")
        override = self.symbol_overrides.get(symbol.upper())
        if override:
            config.update(override)
            config.setdefault("strategy_id", f"dynamic_grid__{self.name}__{symbol.upper()}")
        return config

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "family": self.family,
            "strategy_config": dict(self.strategy_config),
            "symbol_overrides": {key: dict(value) for key, value in self.symbol_overrides.items()},
            "notes": self.notes,
        }


@dataclass(frozen=True)
class GridExperimentConfig:
    run_id: str
    state_db_path: Path
    symbols: tuple[str, ...]
    timeframe: str = "5m"
    output_dir: Path = Path("reports/research/grid_experiments")
    dataset_output_dir: Path = Path("data/research/grid_experiments")
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
    max_variants: int | None = None
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
        if self.initial_capital_eur <= 0.0:
            raise ValueError("initial_capital_eur must be positive")
        if self.order_notional_eur <= 0.0:
            raise ValueError("order_notional_eur must be positive")
        if self.min_closed_trades <= 0 or self.candidate_min_closed_trades <= 0:
            raise ValueError("trade thresholds must be positive")
        if self.max_variants is not None and self.max_variants <= 0:
            raise ValueError("max_variants must be positive when provided")
        self.cost_config.validate()

    @property
    def estimated_round_trip_cost_bps(self) -> float:
        return 2.0 * (
            self.cost_config.taker_fee_bps
            + (self.cost_config.fallback_spread_bps / 2.0)
            + self.cost_config.slippage_bps
            + self.cost_config.latency_buffer_bps
        )


@dataclass(frozen=True)
class GridExperimentCell:
    run_id: str
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
class GridExperimentVariantSummary:
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
class GridExperimentReport:
    run_id: str
    timestamp: str
    dataset: dict[str, Any]
    timeframe: str
    symbols: tuple[str, ...]
    cost_config: dict[str, float]
    estimated_round_trip_cost_bps: float
    variants: tuple[dict[str, Any], ...]
    cells: tuple[GridExperimentCell, ...]
    variant_summaries: tuple[GridExperimentVariantSummary, ...]
    best_by_symbol: dict[str, dict[str, Any]]
    rejected_variants: tuple[dict[str, Any], ...]
    grid_disabled_candidates: tuple[str, ...]
    conclusion: str
    json_report_path: str | None = None
    markdown_report_path: str | None = None
    safety_notes: tuple[str, ...] = (
        "Research-only grid experiments.",
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
            "cost_config": dict(self.cost_config),
            "estimated_round_trip_cost_bps": self.estimated_round_trip_cost_bps,
            "variants": [dict(item) for item in self.variants],
            "cells": [cell.to_dict() for cell in self.cells],
            "variant_summaries": [summary.to_dict() for summary in self.variant_summaries],
            "best_by_symbol": self.best_by_symbol,
            "rejected_variants": [dict(item) for item in self.rejected_variants],
            "grid_disabled_candidates": list(self.grid_disabled_candidates),
            "conclusion": self.conclusion,
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
            "safety_notes": list(self.safety_notes),
        }


def build_grid_experiment_variants(*, max_variants: int | None = None) -> tuple[GridExperimentVariant, ...]:
    """Return a conservative, non-exhaustive grid experiment menu.

    The parameter values are drawn from the requested ranges, but this function
    intentionally avoids a full Cartesian optimization sweep.
    """

    variants = [
        GridExperimentVariant("baseline_current", "baseline_current", notes="Current research grid baseline."),
        GridExperimentVariant(
            "wider_grid_spacing_r5_l7_tp70",
            "wider_grid_spacing",
            {"range_percent": 5.0, "num_levels": 7, "entry_touch_bps": 8.0, "take_profit_bps": 70.0},
        ),
        GridExperimentVariant(
            "wider_grid_spacing_r7_l7_tp100",
            "wider_grid_spacing",
            {"range_percent": 7.0, "num_levels": 7, "entry_touch_bps": 8.0, "take_profit_bps": 100.0},
        ),
        GridExperimentVariant(
            "wider_grid_spacing_r10_l5_tp140",
            "wider_grid_spacing",
            {
                "range_percent": 10.0,
                "num_levels": 5,
                "entry_touch_bps": 12.0,
                "take_profit_bps": 140.0,
                "stop_loss_bps": 250.0,
            },
        ),
        GridExperimentVariant(
            "support_confirmation_2bars_touch4",
            "stronger_support_confirmation",
            {"entry_touch_bps": 4.0, "support_confirmation_bars": 2},
        ),
        GridExperimentVariant(
            "support_confirmation_3bars_touch8",
            "stronger_support_confirmation",
            {"entry_touch_bps": 8.0, "support_confirmation_bars": 3},
        ),
        GridExperimentVariant(
            "min_volatility_atr25_tp70",
            "min_volatility_filter",
            {"min_atr_bps": 25.0, "atr_window": 14, "take_profit_bps": 70.0},
        ),
        GridExperimentVariant(
            "min_volatility_atr50_tp100",
            "min_volatility_filter",
            {"min_atr_bps": 50.0, "atr_window": 14, "take_profit_bps": 100.0},
        ),
        GridExperimentVariant(
            "max_volatility_atr150",
            "max_volatility_filter",
            {"max_atr_bps": 150.0, "atr_window": 14},
        ),
        GridExperimentVariant(
            "max_volatility_atr250",
            "max_volatility_filter",
            {"max_atr_bps": 250.0, "atr_window": 14},
        ),
        GridExperimentVariant(
            "block_trend_down_and_breakout",
            "trend_down_block_filter",
            {"blocked_regimes": ["trend_down", "high_volatility_breakout"]},
        ),
        GridExperimentVariant(
            "range_only_filter",
            "regime_range_only_filter",
            {"allowed_regimes": ["range"]},
        ),
        GridExperimentVariant(
            "cost_aware_mfe_cost_1_2_tp70",
            "cost_aware_min_mfe_filter",
            {"min_expected_mfe_to_cost": 1.2, "take_profit_bps": 70.0},
        ),
        GridExperimentVariant(
            "cost_aware_mfe_cost_1_5_tp100",
            "cost_aware_min_mfe_filter",
            {"min_expected_mfe_to_cost": 1.5, "take_profit_bps": 100.0},
        ),
        GridExperimentVariant(
            "cost_aware_mfe_cost_2_0_tp140",
            "cost_aware_min_mfe_filter",
            {"min_expected_mfe_to_cost": 2.0, "take_profit_bps": 140.0},
        ),
        GridExperimentVariant("wider_take_profit_70", "wider_take_profit", {"take_profit_bps": 70.0}),
        GridExperimentVariant("wider_take_profit_100", "wider_take_profit", {"take_profit_bps": 100.0}),
        GridExperimentVariant("wider_take_profit_140", "wider_take_profit", {"take_profit_bps": 140.0}),
        GridExperimentVariant(
            "cost_buffered_tp_70_plus_cost",
            "wider_take_profit",
            {"exit_mode": "cost_buffered_tp", "take_profit_bps": 70.0, "cost_buffer_bps": 20.0},
        ),
        GridExperimentVariant(
            "mfe_trailing_70_35",
            "mfe_trailing_exit",
            {
                "exit_mode": "mfe_trailing",
                "take_profit_bps": 140.0,
                "mfe_trailing_activation_bps": 70.0,
                "mfe_trailing_drawdown_bps": 35.0,
            },
        ),
        GridExperimentVariant(
            "mfe_trailing_100_45",
            "mfe_trailing_exit",
            {
                "exit_mode": "mfe_trailing",
                "take_profit_bps": 140.0,
                "mfe_trailing_activation_bps": 100.0,
                "mfe_trailing_drawdown_bps": 45.0,
            },
        ),
        GridExperimentVariant(
            "time_stop_no_mfe_6",
            "time_stop_if_no_mfe",
            {"exit_mode": "time_stop_no_mfe", "max_hold_bars": 6, "min_mfe_before_time_stop_bps": 50.0},
        ),
        GridExperimentVariant(
            "time_stop_no_mfe_12",
            "time_stop_if_no_mfe",
            {"exit_mode": "time_stop_no_mfe", "max_hold_bars": 12, "min_mfe_before_time_stop_bps": 50.0},
        ),
        GridExperimentVariant(
            "time_stop_no_mfe_24",
            "time_stop_if_no_mfe",
            {"exit_mode": "time_stop_no_mfe", "max_hold_bars": 24, "min_mfe_before_time_stop_bps": 50.0},
        ),
        GridExperimentVariant(
            "decaying_net_edge_exit",
            "mfe_trailing_exit",
            {
                "exit_mode": "decaying_net_edge",
                "take_profit_bps": 140.0,
                "decay_min_profit_bps": 10.0,
                "decay_giveback_bps": 25.0,
            },
        ),
        GridExperimentVariant(
            "symbol_specific_filters",
            "symbol_specific_filters",
            {
                "take_profit_bps": 70.0,
                "min_expected_mfe_to_cost": 1.2,
                "blocked_regimes": ["trend_down", "high_volatility_breakout"],
            },
            symbol_overrides=_symbol_specific_overrides(),
            notes="XLM focuses exit capture; weak-MFE symbols use stricter entry and wider TP.",
        ),
    ]
    if max_variants is None:
        return tuple(variants)
    return tuple(variants[:max_variants])


def run_grid_experiments(config: GridExperimentConfig) -> GridExperimentReport:
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
    variants = build_grid_experiment_variants(max_variants=config.max_variants)
    cells: list[GridExperimentCell] = []
    baseline_by_symbol: dict[str, GridExperimentCell] = {}

    for variant in variants:
        for symbol in config.symbols:
            cell, backtest_result = _run_backtest_cell(config, variant, dataset_csv_path, symbol.upper())
            cells.append(cell)
            if variant.family == "baseline_current":
                baseline_by_symbol[symbol.upper()] = cell

    evaluated_cells: list[GridExperimentCell] = []
    for cell in cells:
        baseline = baseline_by_symbol.get(cell.symbol)
        provisional_status, provisional_reasons = _candidate_precheck(config, cell, baseline)
        if provisional_status == "candidate_precheck_passed":
            walk_forward = _run_walk_forward_cell(
                config,
                _variant_by_name(variants, cell.variant_name),
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

    summaries = _variant_summaries(evaluated_cells)
    best_by_symbol = _best_by_symbol(evaluated_cells)
    rejected_variants = tuple(_rejected_variant_payload(summary) for summary in summaries if summary.pass_count <= 0)
    grid_disabled = _grid_disabled_candidates(evaluated_cells)
    conclusion = _conclusion(evaluated_cells)
    report = GridExperimentReport(
        run_id=config.run_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        dataset=dataset_result.to_dict(),
        timeframe=config.timeframe,
        symbols=tuple(symbol.upper() for symbol in config.symbols),
        cost_config=config.cost_config.to_dict(),
        estimated_round_trip_cost_bps=config.estimated_round_trip_cost_bps,
        variants=tuple(variant.to_dict() for variant in variants),
        cells=tuple(evaluated_cells),
        variant_summaries=summaries,
        best_by_symbol=best_by_symbol,
        rejected_variants=rejected_variants,
        grid_disabled_candidates=grid_disabled,
        conclusion=conclusion,
    )
    return write_grid_experiment_reports(report, config.output_dir)


def write_grid_experiment_reports(report: GridExperimentReport, output_dir: str | Path) -> GridExperimentReport:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / f"{report.run_id}.json"
    md_path = output / f"{report.run_id}.md"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(render_grid_experiment_report(report), encoding="utf-8")
    return GridExperimentReport(
        run_id=report.run_id,
        timestamp=report.timestamp,
        dataset=report.dataset,
        timeframe=report.timeframe,
        symbols=report.symbols,
        cost_config=report.cost_config,
        estimated_round_trip_cost_bps=report.estimated_round_trip_cost_bps,
        variants=report.variants,
        cells=report.cells,
        variant_summaries=report.variant_summaries,
        best_by_symbol=report.best_by_symbol,
        rejected_variants=report.rejected_variants,
        grid_disabled_candidates=report.grid_disabled_candidates,
        conclusion=report.conclusion,
        json_report_path=str(json_path),
        markdown_report_path=str(md_path),
        safety_notes=report.safety_notes,
    )


def render_grid_experiment_report(report: GridExperimentReport) -> str:
    top = sorted(report.variant_summaries, key=_summary_sort_key)[:20]
    lines = [
        f"# Grid Experiment Report - {report.run_id}",
        "",
        "## Scope",
        "",
        "Research-only grid improvement campaign. This report does not authorize paper promotion, live trading,",
        "runtime sizing changes, risk-manager changes, or registry mutation.",
        "",
        "## Dataset And Costs",
        "",
        f"- Timeframe: `{report.timeframe}`",
        f"- Symbols: `{', '.join(report.symbols)}`",
        f"- Cost config: `{json.dumps(report.cost_config, sort_keys=True)}`",
        f"- Estimated round-trip cost: `{report.estimated_round_trip_cost_bps:.3f}` bps",
        f"- Dataset manifest: `{report.dataset.get('manifest_path')}`",
        "",
        "## Top Variants",
        "",
        "| Variant | Family | Trades | Net PnL | PF Proxy | Max DD | MFE/Cost | Exit Capture | Passes | Best Symbol | Overfit Risk |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for item in top:
        lines.append(
            f"| {item.variant_name} | {item.family} | {item.trade_count} | {_fmt(item.net_pnl_eur)} | "
            f"{_fmt(item.profit_factor_proxy)} | {_fmt(item.max_drawdown_pct)} | "
            f"{_fmt(item.average_mfe_to_cost_ratio)} | {_fmt(item.average_exit_capture_bps)} | "
            f"{item.pass_count} | {item.best_symbol or ''} | {item.overfit_risk} |"
        )
    lines.extend(
        [
            "",
            "## Best By Symbol",
            "",
            "| Symbol | Variant | Family | Trades | Net PnL | PF | MFE/Cost | Exit Capture | Candidate | Reasons |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
        ]
    )
    for symbol, item in sorted(report.best_by_symbol.items()):
        lines.append(
            f"| {symbol} | {item['variant_name']} | {item['family']} | {item['trade_count']} | "
            f"{_fmt(item['net_pnl_eur'])} | {_fmt(item.get('profit_factor'))} | "
            f"{_fmt(item.get('average_mfe_to_cost_ratio'))} | {_fmt(item.get('average_exit_capture_bps'))} | "
            f"{item['candidate_status']} | {', '.join(item.get('candidate_reasons') or [])} |"
        )
    lines.extend(
        [
            "",
            "## Rejected Variants",
            "",
            "| Variant | Family | Reason |",
            "| --- | --- | --- |",
        ]
    )
    for item in report.rejected_variants[:50]:
        lines.append(f"| {item['variant_name']} | {item['family']} | {item['reason']} |")
    lines.extend(
        [
            "",
            "## Grid Disabled Candidates",
            "",
            ", ".join(report.grid_disabled_candidates) if report.grid_disabled_candidates else "none",
            "",
            "## Conclusion",
            "",
            report.conclusion,
            "",
            "## Safety",
            "",
        ]
    )
    lines.extend(f"- {note}" for note in report.safety_notes)
    return "\n".join(lines) + "\n"


def _run_backtest_cell(
    config: GridExperimentConfig,
    variant: GridExperimentVariant,
    dataset_csv_path: Path,
    symbol: str,
) -> tuple[GridExperimentCell, Any]:
    run_id = f"{config.run_id}_{variant.name}_{symbol}".replace("/", "_")
    strategy_config = variant.config_for_symbol(symbol, estimated_round_trip_cost_bps=config.estimated_round_trip_cost_bps)
    runner_result = run_validation(
        ValidationRunnerConfig(
            run_id=run_id,
            strategy="grid",
            data_source="csv",
            data_path=dataset_csv_path,
            symbol=symbol,
            dataset_id=f"grid_experiment:{config.timeframe}:{symbol}:{variant.name}",
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
            source=f"grid_experiment:{variant.name}",
            fees_included=True,
            slippage_included=True,
            baseline_included=True,
            out_of_sample_included=False,
        )
    )
    cell = _cell_from_backtest(
        config=config,
        variant=variant,
        symbol=symbol,
        strategy_config=strategy_config,
        bar_count=runner_result.bar_count,
        result=result,
        attribution=attribution,
        scorecard=scorecard,
    )
    return cell, result


def _run_walk_forward_cell(
    config: GridExperimentConfig,
    variant: GridExperimentVariant,
    dataset_csv_path: Path,
    symbol: str,
) -> WalkForwardResult:
    run_id = f"{config.run_id}_{variant.name}_{symbol}_wf".replace("/", "_")
    runner_result = run_validation(
        ValidationRunnerConfig(
            run_id=run_id,
            strategy="grid",
            data_source="csv",
            data_path=dataset_csv_path,
            symbol=symbol,
            dataset_id=f"grid_experiment:{config.timeframe}:{symbol}:{variant.name}:walk_forward",
            mode="walk_forward",
            output_dir=config.output_dir / "walk_forward",
            initial_capital_eur=config.initial_capital_eur,
            order_notional_eur=config.order_notional_eur,
            min_closed_trades=config.min_closed_trades,
            min_profit_factor=config.candidate_min_profit_factor,
            max_drawdown_pct=config.candidate_max_drawdown_pct,
            cost_config=config.cost_config,
            strategy_config=variant.config_for_symbol(
                symbol,
                estimated_round_trip_cost_bps=config.estimated_round_trip_cost_bps,
            ),
            train_window_bars=config.train_window_bars,
            test_window_bars=config.test_window_bars,
            step_window_bars=config.step_window_bars,
            min_folds=config.min_folds,
            min_passing_folds=max(1, math.ceil(config.min_folds * config.candidate_min_walk_forward_positive_fold_ratio)),
            include_regime_context=config.include_regime_context,
        )
    )
    return runner_result.result


def _cell_from_backtest(
    *,
    config: GridExperimentConfig,
    variant: GridExperimentVariant,
    symbol: str,
    strategy_config: dict[str, Any],
    bar_count: int,
    result: Any,
    attribution: LossAttributionResult | None,
    scorecard: StrategyScorecardResult,
) -> GridExperimentCell:
    metrics = result.metrics
    return GridExperimentCell(
        run_id=result.run_id,
        variant_name=variant.name,
        family=variant.family,
        symbol=symbol,
        status="ok",
        decision=result.decision.status,
        reason=result.decision.reason,
        bar_count=bar_count,
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


def _candidate_precheck(
    config: GridExperimentConfig,
    cell: GridExperimentCell,
    baseline: GridExperimentCell | None,
) -> tuple[str, tuple[str, ...]]:
    reasons = _candidate_reasons(config, cell, baseline)
    pre_wf_reasons = tuple(reason for reason in reasons if reason != "walk_forward_not_run")
    if pre_wf_reasons:
        return "fail", pre_wf_reasons
    return "candidate_precheck_passed", ()


def _candidate_final_status(
    config: GridExperimentConfig,
    cell: GridExperimentCell,
    baseline: GridExperimentCell | None,
    walk_forward: WalkForwardResult,
) -> tuple[str, tuple[str, ...]]:
    reasons = list(_candidate_reasons(config, cell, baseline))
    passing_ratio = (walk_forward.passing_fold_count / walk_forward.fold_count) if walk_forward.fold_count else 0.0
    if passing_ratio < config.candidate_min_walk_forward_positive_fold_ratio:
        reasons.append("walk_forward_positive_fold_ratio_below_60pct")
    if walk_forward.aggregate_net_pnl_eur <= 0.0:
        reasons.append("walk_forward_net_pnl_not_positive")
    if walk_forward.decision.live_promotion_allowed:
        reasons.append("unexpected_live_promotion_allowed")
    reasons = [reason for reason in reasons if reason != "walk_forward_not_run"]
    return ("candidate_shadow_only" if not reasons else "fail", tuple(reasons))


def _candidate_reasons(
    config: GridExperimentConfig,
    cell: GridExperimentCell,
    baseline: GridExperimentCell | None,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if cell.net_pnl_eur <= 0.0:
        reasons.append("net_pnl_not_positive")
    if cell.profit_factor is None or cell.profit_factor < config.candidate_min_profit_factor:
        reasons.append("profit_factor_below_1_20")
    if cell.average_mfe_to_cost_ratio is None or cell.average_mfe_to_cost_ratio < config.candidate_min_mfe_to_cost:
        reasons.append("mfe_to_cost_below_1_5")
    if cell.max_drawdown_pct > config.candidate_max_drawdown_pct:
        reasons.append("max_drawdown_above_12pct")
    if cell.trade_count < config.candidate_min_closed_trades:
        reasons.append("insufficient_trade_count")
    if cell.beats_baseline is False:
        reasons.append("does_not_beat_baseline")
    baseline_exit_capture = baseline.average_exit_capture_bps if baseline else None
    exit_capture = cell.average_exit_capture_bps
    strong_improvement = (
        exit_capture is not None
        and baseline_exit_capture is not None
        and (exit_capture - baseline_exit_capture) >= 25.0
    )
    if exit_capture is None or (exit_capture <= 0.0 and not strong_improvement):
        reasons.append("exit_capture_not_positive_or_strongly_improved")
    if cell.live_promotion_allowed:
        reasons.append("unexpected_live_promotion_allowed")
    reasons.append("walk_forward_not_run")
    return tuple(reasons)


def _replace_cell_candidate(
    cell: GridExperimentCell,
    *,
    candidate_status: str,
    candidate_reasons: Sequence[str],
    overfit_risk: str,
    walk_forward: dict[str, Any] | None = None,
) -> GridExperimentCell:
    return GridExperimentCell(
        **{
            **cell.to_dict(),
            "candidate_status": candidate_status,
            "candidate_reasons": tuple(candidate_reasons),
            "overfit_risk": overfit_risk,
            "walk_forward": walk_forward,
            "live_promotion_allowed": False,
        }
    )


def _variant_summaries(cells: Sequence[GridExperimentCell]) -> tuple[GridExperimentVariantSummary, ...]:
    grouped: dict[str, list[GridExperimentCell]] = {}
    for cell in cells:
        grouped.setdefault(cell.variant_name, []).append(cell)
    summaries: list[GridExperimentVariantSummary] = []
    for variant_name, group in grouped.items():
        positive_net = sum(max(0.0, cell.net_pnl_eur) for cell in group)
        negative_net = abs(sum(min(0.0, cell.net_pnl_eur) for cell in group))
        best = max(group, key=lambda cell: (cell.net_pnl_eur, cell.profit_factor or 0.0, cell.trade_count))
        summaries.append(
            GridExperimentVariantSummary(
                variant_name=variant_name,
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


def _best_by_symbol(cells: Sequence[GridExperimentCell]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[GridExperimentCell]] = {}
    for cell in cells:
        grouped.setdefault(cell.symbol, []).append(cell)
    result: dict[str, dict[str, Any]] = {}
    for symbol, group in grouped.items():
        best = max(
            group,
            key=lambda cell: (
                cell.candidate_status == "candidate_shadow_only",
                cell.net_pnl_eur,
                cell.profit_factor or 0.0,
                cell.average_mfe_to_cost_ratio or 0.0,
            ),
        )
        result[symbol] = {
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


def _grid_disabled_candidates(cells: Sequence[GridExperimentCell]) -> tuple[str, ...]:
    disabled: list[str] = []
    for symbol, best in _best_by_symbol(cells).items():
        if best["candidate_status"] == "candidate_shadow_only":
            continue
        if float(best["net_pnl_eur"]) <= 0.0 or "mfe_to_cost_below_1_5" in best.get("candidate_reasons", ()):
            disabled.append(symbol)
    return tuple(sorted(disabled))


def _conclusion(cells: Sequence[GridExperimentCell]) -> str:
    candidates = [cell for cell in cells if cell.candidate_status == "candidate_shadow_only"]
    if not candidates:
        return (
            "Grid is not currently viable on this dataset after costs. "
            "Recommendation: keep grid in shadow/research only or disable it from official paper until a variant passes "
            "net-PnL, MFE/Cost, exit-capture and walk-forward criteria."
        )
    names = sorted({f"{cell.variant_name}/{cell.symbol}" for cell in candidates})
    return (
        "Grid has research-only shadow candidates, but no live permission. "
        f"Candidate cells: {', '.join(names)}. Human review and additional paper evidence are required."
    )


def _dataset_csv_path(result: DatasetBuildResult, timeframe: str) -> Path:
    export = next((item for item in result.exports if item.timeframe.lower() == timeframe.lower()), None)
    if export is None or not export.csv_path:
        raise ValueError(f"dataset export for timeframe {timeframe!r} did not produce a CSV path")
    return Path(export.csv_path)


def _loss_attribution(path: str | None, *, run_id: str) -> LossAttributionResult | None:
    if not path:
        return None
    report = analyze_trade_journal(path, run_id=run_id)
    return report


def _primary_failure_mode(attribution: LossAttributionResult | None) -> str | None:
    if attribution is None or not attribution.by_failure_mode:
        return None
    return max(attribution.by_failure_mode, key=lambda bucket: bucket.trade_count).key


def _variant_by_name(variants: Sequence[GridExperimentVariant], name: str) -> GridExperimentVariant:
    for variant in variants:
        if variant.name == name:
            return variant
    raise KeyError(name)


def _cell_overfit_risk(
    cell: GridExperimentCell,
    baseline: GridExperimentCell | None,
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


def _variant_overfit_risk(group: Sequence[GridExperimentCell]) -> str:
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


def _rejected_variant_payload(summary: GridExperimentVariantSummary) -> dict[str, Any]:
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
        "variant_name": summary.variant_name,
        "family": summary.family,
        "reason": ", ".join(reasons) or "criteria_not_met",
    }


def _symbol_specific_overrides() -> dict[str, dict[str, Any]]:
    overrides: dict[str, dict[str, Any]] = {}
    for symbol in EXIT_CAPTURE_SYMBOLS:
        overrides[symbol] = {
            "exit_mode": "mfe_trailing",
            "take_profit_bps": 140.0,
            "mfe_trailing_activation_bps": 70.0,
            "mfe_trailing_drawdown_bps": 30.0,
        }
    for symbol in STRICT_ENTRY_SYMBOLS:
        overrides[symbol] = {
            "range_percent": 7.0,
            "num_levels": 7,
            "entry_touch_bps": 4.0,
            "take_profit_bps": 100.0,
            "stop_loss_bps": 180.0,
            "min_expected_mfe_to_cost": 1.5,
            "min_atr_bps": 25.0,
            "support_confirmation_bars": 2,
            "blocked_regimes": ["trend_down", "high_volatility_breakout"],
        }
    return overrides


def _weighted_average(
    values: Sequence[GridExperimentCell],
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


def _summary_sort_key(summary: GridExperimentVariantSummary) -> tuple[float, float, float, float, float]:
    return (
        -float(summary.pass_count),
        -float(summary.net_pnl_eur),
        -float(summary.profit_factor_proxy or -1.0),
        float(summary.max_drawdown_pct),
        -float(summary.average_mfe_to_cost_ratio or -1.0),
    )


def _fmt(value: float | int | None) -> str:
    if value is None:
        return ""
    return f"{float(value):.6f}"
