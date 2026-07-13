"""Deterministic, research-only walk-forward for the funding/basis adapter.

The adapter has no optimisation phase: bounded template variants are fixed
before every fold.  Train windows are descriptive audit evidence only; each
test simulation is re-run with strict entry/exit bounds and point-in-time
feature availability.  This module never imports an order, paper, or runtime
trading path.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

from .alpha_hypothesis_lab import RESEARCH_ONLY_CAPITAL_FLAGS
from .funding_basis_research_adapter import (
    ADAPTER_ID,
    FundingBasisMetrics,
    FundingBasisResearchConfig,
    FundingBasisSmokeResult,
    FundingBasisTrade,
    compute_funding_basis_metrics,
    run_funding_basis_research_smoke,
)


@dataclass(frozen=True)
class FundingBasisWalkForwardConfig:
    run_id: str
    spot_data_paths: tuple[Path, ...]
    derivatives_feature_snapshot_manifest: Path
    template: Mapping[str, Any]
    symbols: tuple[str, ...]
    cost_profile: str = "research_stress"
    max_variants: int = 2
    max_symbols: int = 4
    max_runtime_seconds: float = 120.0
    max_data_rows: int = 250_000
    folds: int = 3
    train_fraction: float = 0.45

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id is required")
        if self.folds < 3 or self.folds > 8:
            raise ValueError("folds must be between 3 and 8")
        if not 0.3 <= self.train_fraction <= 0.7:
            raise ValueError("train_fraction must stay bounded between 0.3 and 0.7")


@dataclass(frozen=True)
class FundingBasisWalkForwardFold:
    fold_id: str
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    train_metrics: FundingBasisMetrics
    test_metrics: FundingBasisMetrics
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
class FundingBasisWalkForwardReport:
    run_id: str
    adapter_id: str
    decision: str
    reasons: tuple[str, ...]
    availability: Mapping[str, Any]
    overall_oos: FundingBasisMetrics
    folds: tuple[FundingBasisWalkForwardFold, ...]
    oos_trades: tuple[FundingBasisTrade, ...]
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


def build_funding_basis_walk_forward_report(
    config: FundingBasisWalkForwardConfig,
) -> FundingBasisWalkForwardReport:
    """Evaluate a fixed template on sequential, non-overlapping OOS windows."""

    started = time.perf_counter()
    baseline = _run(config)
    empty = FundingBasisMetrics(0, 0.0, 0.0, None, None, None, 0.0, 0.0, 0.0, {}, {}, {})
    if not baseline.availability.available:
        return _report(
            config,
            decision="INSUFFICIENT_DATA",
            reasons=baseline.availability.blockers or ("funding_basis_inputs_unavailable",),
            availability=baseline,
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
            reasons=("no_executable_funding_basis_trades_for_walk_forward",),
            availability=baseline,
            overall=empty,
            folds=(),
            trades=(),
            diagnostics={"fixed_template_only": True, "simulation_not_run": True},
            started=started,
        )
    windows = _windows(*bounds, folds=config.folds, train_fraction=config.train_fraction)
    folds: list[FundingBasisWalkForwardFold] = []
    oos_trades: list[FundingBasisTrade] = []
    for fold_id, train_start, train_end, test_start, test_end in windows:
        if time.perf_counter() - started > config.max_runtime_seconds:
            break
        train = _run(config, evaluation_start_at=train_start, evaluation_end_at=train_end)
        test = _run(config, evaluation_start_at=test_start, evaluation_end_at=test_end)
        folds.append(
            FundingBasisWalkForwardFold(
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
    overall = _aggregate_metrics(oos_trades)
    decision, reasons = _decision(overall, folds, config.template, complete=len(folds) == len(windows))
    return _report(
        config,
        decision=decision,
        reasons=reasons,
        availability=baseline,
        overall=overall,
        folds=tuple(folds),
        trades=tuple(oos_trades),
        diagnostics={
            "fixed_template_only": True,
            "parameter_selection": "none; bounded template order is immutable across folds",
            "anti_lookahead": "each test fold only records entries/exits inside its OOS interval; derivatives availability remains checked before every signal",
            "fold_count_requested": config.folds,
            "fold_count_completed": len(folds),
            "test_windows_non_overlapping": True,
        },
        started=started,
    )


def _run(
    config: FundingBasisWalkForwardConfig,
    *,
    evaluation_start_at: datetime | None = None,
    evaluation_end_at: datetime | None = None,
) -> FundingBasisSmokeResult:
    return run_funding_basis_research_smoke(
        FundingBasisResearchConfig(
            run_id=config.run_id,
            spot_data_paths=config.spot_data_paths,
            derivatives_feature_snapshot_manifest=config.derivatives_feature_snapshot_manifest,
            template=config.template,
            symbols=config.symbols,
            cost_profile=config.cost_profile,
            max_variants=config.max_variants,
            max_symbols=config.max_symbols,
            max_runtime_seconds=config.max_runtime_seconds,
            max_data_rows=config.max_data_rows,
            evaluation_start_at=evaluation_start_at,
            evaluation_end_at=evaluation_end_at,
        )
    )


def _trade_bounds(trades: tuple[FundingBasisTrade, ...]) -> tuple[datetime, datetime] | None:
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


def _aggregate_metrics(trades: list[FundingBasisTrade]) -> FundingBasisMetrics:
    # OOS trades are the only records allowed to contribute to this aggregation.
    return compute_funding_basis_metrics(trades)


def _decision(
    metrics: FundingBasisMetrics,
    folds: list[FundingBasisWalkForwardFold],
    template: Mapping[str, Any],
    *,
    complete: bool,
) -> tuple[str, tuple[str, ...]]:
    reasons: list[str] = []
    minimum = int(template.get("minimum_sample_size") or 30)
    if not complete:
        reasons.append("walk_forward_runtime_incomplete")
    if not folds:
        reasons.append("walk_forward_folds_unavailable")
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
    if folds and profitable_folds < max(2, (len(folds) + 1) // 2):
        reasons.append("oos_profitable_folds_insufficient")
    if reasons:
        return ("REJECTED" if metrics.trade_count else "INSUFFICIENT_DATA", tuple(reasons))
    return ("KEEP_RESEARCH", ("oos_net_cost_walk_forward_passed; stress_gate_still_required",))


def _report(
    config: FundingBasisWalkForwardConfig,
    *,
    decision: str,
    reasons: tuple[str, ...],
    availability: FundingBasisSmokeResult,
    overall: FundingBasisMetrics,
    folds: tuple[FundingBasisWalkForwardFold, ...],
    trades: tuple[FundingBasisTrade, ...],
    diagnostics: Mapping[str, Any],
    started: float,
) -> FundingBasisWalkForwardReport:
    return FundingBasisWalkForwardReport(
        run_id=config.run_id,
        adapter_id=ADAPTER_ID,
        decision=decision,
        reasons=reasons,
        availability=availability.availability.to_dict(),
        overall_oos=overall,
        folds=folds,
        oos_trades=trades,
        diagnostics=diagnostics,
        elapsed_seconds=round(time.perf_counter() - started, 6),
    )
