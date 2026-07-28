"""Deterministic walk-forward for the bounded volatility-reversal adapter.

The template variants are declared before any data is inspected.  Training
windows are descriptive evidence only: each test fold reruns the same primary
variant with closed-bar, next-bar entry rules and explicit stress costs.  This
module is research-only and deliberately imports no runtime, order, paper, or
promotion path.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

from .alpha_hypothesis_lab import RESEARCH_ONLY_CAPITAL_FLAGS
from .generic_cross_sectional_ohlcv_adapter import CrossSectionalMetrics, CrossSectionalTrade
from .volatility_reversal_research_adapter import (
    ADAPTER_ID,
    VolatilityReversalResearchConfig,
    VolatilityReversalSmokeResult,
    compute_volatility_reversal_metrics,
    run_volatility_reversal_research_smoke,
)


@dataclass(frozen=True)
class VolatilityReversalWalkForwardConfig:
    run_id: str
    data_paths: tuple[Path, ...]
    template: Mapping[str, Any]
    symbols: tuple[str, ...]
    cost_profile: str = "research_stress"
    max_variants: int = 3
    max_symbols: int = 6
    max_runtime_seconds: float = 120.0
    max_data_rows: int = 250_000
    folds: int = 3
    train_fraction: float = 0.45

    def __post_init__(self) -> None:
        if not self.run_id.strip() or not self.data_paths or not self.symbols:
            raise ValueError("run_id, data_paths, and symbols are required")
        if self.max_variants <= 0 or self.max_variants > 3:
            raise ValueError("max_variants must be between 1 and 3")
        if self.max_symbols <= 0 or self.max_symbols > 6:
            raise ValueError("max_symbols must be between 1 and 6")
        if self.max_runtime_seconds <= 0.0 or self.max_data_rows <= 0:
            raise ValueError("runtime and data-row limits must be positive")
        if self.folds < 3 or self.folds > 8:
            raise ValueError("folds must be between 3 and 8")
        if not 0.3 <= self.train_fraction <= 0.7:
            raise ValueError("train_fraction must stay bounded between 0.3 and 0.7")


@dataclass(frozen=True)
class VolatilityReversalWalkForwardFold:
    fold_id: str
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    train_metrics: CrossSectionalMetrics
    test_metrics: CrossSectionalMetrics
    test_trade_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "fold_id": self.fold_id,
            "train_start": self.train_start.isoformat(),
            "train_end": self.train_end.isoformat(),
            "test_start": self.test_start.isoformat(),
            "test_end": self.test_end.isoformat(),
            "train_metrics": self.train_metrics.to_dict(),
            "test_metrics": self.test_metrics.to_dict(),
            "test_trade_count": self.test_trade_count,
        }


@dataclass(frozen=True)
class VolatilityReversalWalkForwardReport:
    run_id: str
    adapter_id: str
    decision: str
    reasons: tuple[str, ...]
    availability: Mapping[str, Any]
    overall_oos: CrossSectionalMetrics
    folds: tuple[VolatilityReversalWalkForwardFold, ...]
    oos_trades: tuple[CrossSectionalTrade, ...]
    diagnostics: Mapping[str, Any]
    elapsed_seconds: float
    safety: Mapping[str, bool] = field(default_factory=lambda: dict(RESEARCH_ONLY_CAPITAL_FLAGS))
    paper_capital_allowed: bool = False
    live_allowed: bool = False
    promotable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "adapter_id": self.adapter_id,
            "decision": self.decision,
            "reasons": list(self.reasons),
            "availability": dict(self.availability),
            "overall_oos": self.overall_oos.to_dict(),
            "folds": [fold.to_dict() for fold in self.folds],
            "oos_trades": [trade.to_dict() for trade in self.oos_trades],
            "diagnostics": dict(self.diagnostics),
            "elapsed_seconds": self.elapsed_seconds,
            "safety": dict(self.safety),
            "paper_capital_allowed": False,
            "live_allowed": False,
            "promotable": False,
        }


def build_volatility_reversal_walk_forward_report(
    config: VolatilityReversalWalkForwardConfig,
) -> VolatilityReversalWalkForwardReport:
    """Evaluate only the immutable primary template across sequential OOS folds."""

    started = time.perf_counter()
    baseline = _run(config)
    empty = _empty_metrics()
    if not baseline.availability.available:
        return _report(
            config,
            decision="INSUFFICIENT_DATA",
            reasons=tuple(item for item in (baseline.availability.reason,) if item)
            or ("volatility_reversal_inputs_unavailable",),
            baseline=baseline,
            overall=empty,
            folds=(),
            trades=(),
            diagnostics={"fixed_template_only": True, "simulation_not_run": True},
            started=started,
        )
    bounds = _trade_bounds(baseline.primary_trades)
    if bounds is None:
        return _report(
            config,
            decision="INSUFFICIENT_DATA",
            reasons=("no_executable_volatility_reversal_trades_for_walk_forward",),
            baseline=baseline,
            overall=empty,
            folds=(),
            trades=(),
            diagnostics={"fixed_template_only": True, "simulation_not_run": True},
            started=started,
        )
    windows = _windows(*bounds, folds=config.folds, train_fraction=config.train_fraction)
    folds: list[VolatilityReversalWalkForwardFold] = []
    oos_trades: list[CrossSectionalTrade] = []
    for fold_id, train_start, train_end, test_start, test_end in windows:
        remaining = config.max_runtime_seconds - (time.perf_counter() - started)
        if remaining <= 0.0:
            break
        train = _run(config, evaluation_start_at=train_start, evaluation_end_at=train_end, remaining_seconds=remaining)
        remaining = config.max_runtime_seconds - (time.perf_counter() - started)
        if remaining <= 0.0:
            break
        test = _run(config, evaluation_start_at=test_start, evaluation_end_at=test_end, remaining_seconds=remaining)
        folds.append(
            VolatilityReversalWalkForwardFold(
                fold_id=fold_id,
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
                train_metrics=train.metrics,
                test_metrics=test.metrics,
                test_trade_count=len(test.primary_trades),
            )
        )
        oos_trades.extend(test.primary_trades)
    overall = _metrics(oos_trades)
    decision, reasons = _decision(
        overall,
        folds,
        config.template,
        complete=len(folds) == len(windows),
    )
    return _report(
        config,
        decision=decision,
        reasons=reasons,
        baseline=baseline,
        overall=overall,
        folds=tuple(folds),
        trades=tuple(oos_trades),
        diagnostics={
            "fixed_template_only": True,
            "parameter_selection": "none; primary template order is immutable across folds",
            "anti_lookahead": (
                "each OOS record requires a closed signal bar, a next-bar entry, and a close "
                "inside its test window; prior bars only provide contextual history"
            ),
            "fold_count_requested": config.folds,
            "fold_count_completed": len(folds),
            "test_windows_non_overlapping": True,
        },
        started=started,
    )


def _run(
    config: VolatilityReversalWalkForwardConfig,
    *,
    evaluation_start_at: datetime | None = None,
    evaluation_end_at: datetime | None = None,
    remaining_seconds: float | None = None,
) -> VolatilityReversalSmokeResult:
    runtime_limit = (
        config.max_runtime_seconds
        if remaining_seconds is None
        else min(config.max_runtime_seconds, remaining_seconds)
    )
    return run_volatility_reversal_research_smoke(
        VolatilityReversalResearchConfig(
            run_id=config.run_id,
            data_paths=config.data_paths,
            template=config.template,
            symbols=config.symbols,
            cost_profile=config.cost_profile,
            max_variants=config.max_variants,
            max_symbols=config.max_symbols,
            max_runtime_seconds=max(0.001, runtime_limit),
            max_data_rows=config.max_data_rows,
            evaluation_start_at=evaluation_start_at,
            evaluation_end_at=evaluation_end_at,
        )
    )


def _trade_bounds(trades: tuple[CrossSectionalTrade, ...]) -> tuple[datetime, datetime] | None:
    if not trades:
        return None
    return min(item.signal_at for item in trades), max(item.closed_at for item in trades)


def _windows(
    start: datetime,
    end: datetime,
    *,
    folds: int,
    train_fraction: float,
) -> tuple[tuple[str, datetime, datetime, datetime, datetime], ...]:
    span_seconds = (end - start).total_seconds()
    train_seconds = span_seconds * train_fraction
    test_seconds = (span_seconds - train_seconds) / folds
    if test_seconds <= 0.0:
        return ()
    initial_train_end = start + timedelta(seconds=train_seconds)
    windows = []
    for index in range(folds):
        test_start = initial_train_end + timedelta(seconds=index * test_seconds)
        test_end = end if index == folds - 1 else initial_train_end + timedelta(seconds=(index + 1) * test_seconds)
        windows.append((f"fold_{index + 1}", start, test_start, test_start, test_end))
    return tuple(windows)


def _empty_metrics() -> CrossSectionalMetrics:
    return CrossSectionalMetrics(0, None, 0.0, None, 0.0, None, 0.0, 0.0, {}, {}, {})


def _metrics(trades: list[CrossSectionalTrade]) -> CrossSectionalMetrics:
    return compute_volatility_reversal_metrics(trades)


def _decision(
    metrics: CrossSectionalMetrics,
    folds: list[VolatilityReversalWalkForwardFold],
    template: Mapping[str, Any],
    *,
    complete: bool,
) -> tuple[str, tuple[str, ...]]:
    if not complete:
        return "REJECTED", ("walk_forward_runtime_incomplete",)
    if not folds or metrics.trade_count == 0:
        return "INSUFFICIENT_DATA", ("walk_forward_folds_unavailable",)
    minimum = int(template.get("minimum_sample_size") or 50)
    reasons: list[str] = []
    if metrics.trade_count < minimum:
        reasons.append("oos_sample_size_below_template_minimum")
    if metrics.net_pnl_eur <= 0.0:
        reasons.append("oos_net_pnl_not_positive")
    if metrics.profit_factor_net is None or metrics.profit_factor_net <= 1.0:
        reasons.append("oos_profit_factor_net_not_above_1")
    if metrics.expectancy_net is None or metrics.expectancy_net <= 0.0:
        reasons.append("oos_expectancy_net_not_positive")
    if metrics.concentration.get("top_positive_pnl_share", 0.0) > 0.65:
        reasons.append("oos_symbol_concentration_high")
    profitable_folds = sum(1 for fold in folds if fold.test_metrics.net_pnl_eur > 0.0)
    if profitable_folds < max(2, (len(folds) + 1) // 2):
        reasons.append("oos_profitable_folds_insufficient")
    if reasons:
        decision = "INSUFFICIENT_DATA" if metrics.trade_count < minimum else "REJECTED"
        return decision, tuple(reasons)
    return "KEEP_RESEARCH", ("oos_net_cost_walk_forward_passed; statistical_gate_still_required",)


def _report(
    config: VolatilityReversalWalkForwardConfig,
    *,
    decision: str,
    reasons: tuple[str, ...],
    baseline: VolatilityReversalSmokeResult,
    overall: CrossSectionalMetrics,
    folds: tuple[VolatilityReversalWalkForwardFold, ...],
    trades: tuple[CrossSectionalTrade, ...],
    diagnostics: Mapping[str, Any],
    started: float,
) -> VolatilityReversalWalkForwardReport:
    return VolatilityReversalWalkForwardReport(
        run_id=config.run_id,
        adapter_id=ADAPTER_ID,
        decision=decision,
        reasons=reasons,
        availability=baseline.availability.to_dict(),
        overall_oos=overall,
        folds=folds,
        oos_trades=trades,
        diagnostics=diagnostics,
        elapsed_seconds=round(time.perf_counter() - started, 6),
    )
