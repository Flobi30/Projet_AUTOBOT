"""Walk-forward validation for AUTOBOT research backtests."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Sequence

from .backtest_alpha_adapter import BacktestSignalProvenance, fingerprint_backtest_bars
from .backtest_engine import BacktestConfig, BacktestEngine, BacktestResult, SignalGenerator
from .market_data_repository import MarketBar, MarketDataRepository


@dataclass(frozen=True)
class WalkForwardConfig:
    run_id: str
    base_backtest_config: BacktestConfig
    train_window_bars: int
    test_window_bars: int
    step_window_bars: int | None = None
    min_folds: int = 3
    min_passing_folds: int = 2
    output_dir: Path = Path("reports/walk_forward")
    alpha_provenance: BacktestSignalProvenance | None = None

    def __post_init__(self) -> None:
        if self.train_window_bars <= 0:
            raise ValueError("train_window_bars must be positive")
        if self.test_window_bars <= 0:
            raise ValueError("test_window_bars must be positive")
        if self.step_window_bars is not None and self.step_window_bars <= 0:
            raise ValueError("step_window_bars must be positive when provided")
        if self.min_folds <= 0:
            raise ValueError("min_folds must be positive")
        if self.min_passing_folds <= 0:
            raise ValueError("min_passing_folds must be positive")
        if self.alpha_provenance is not None:
            if self.alpha_provenance.strategy_id != self.base_backtest_config.strategy_id.strip().lower():
                raise ValueError("alpha provenance strategy_id must match base_backtest_config.strategy_id")
            if self.alpha_provenance.data_snapshot_id != self.base_backtest_config.dataset_id.strip():
                raise ValueError("alpha provenance data_snapshot_id must match base_backtest_config.dataset_id")


@dataclass(frozen=True)
class WalkForwardFoldResult:
    fold_index: int
    train_event_count: int
    test_event_count: int
    train_start_at: str
    train_end_at: str
    test_start_at: str
    test_end_at: str
    backtest_result: BacktestResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "fold_index": self.fold_index,
            "train_event_count": self.train_event_count,
            "test_event_count": self.test_event_count,
            "train_start_at": self.train_start_at,
            "train_end_at": self.train_end_at,
            "test_start_at": self.test_start_at,
            "test_end_at": self.test_end_at,
            "backtest_result": self.backtest_result.to_dict(),
        }


@dataclass(frozen=True)
class WalkForwardDecision:
    status: str
    reason: str
    proposed_registry_status: str
    live_promotion_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WalkForwardResult:
    run_id: str
    strategy_id: str
    dataset_id: str
    fold_count: int
    passing_fold_count: int
    aggregate_net_pnl_eur: float
    average_fold_return_pct: float | None
    worst_fold_drawdown_pct: float | None
    total_closed_trades: int
    folds: tuple[WalkForwardFoldResult, ...]
    decision: WalkForwardDecision
    json_report_path: str | None = None
    markdown_report_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "strategy_id": self.strategy_id,
            "dataset_id": self.dataset_id,
            "fold_count": self.fold_count,
            "passing_fold_count": self.passing_fold_count,
            "aggregate_net_pnl_eur": self.aggregate_net_pnl_eur,
            "average_fold_return_pct": self.average_fold_return_pct,
            "worst_fold_drawdown_pct": self.worst_fold_drawdown_pct,
            "total_closed_trades": self.total_closed_trades,
            "folds": [fold.to_dict() for fold in self.folds],
            "decision": self.decision.to_dict(),
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
        }


class WalkForwardValidator:
    """Run rolling OOS replays of a fixed signal policy without future bars.

    ``train_window_bars`` defines the historical context that is deliberately
    held before each test slice.  This validator does not fit or tune the
    strategy inside that window; callers must record any calibration as a
    separate experiment before claiming parameter re-estimation.
    """

    PASSING_BACKTEST_STATUSES = {"promote_candidate"}

    def __init__(self, config: WalkForwardConfig, *, repository: MarketDataRepository | None = None) -> None:
        self.config = config
        self.repository = repository or MarketDataRepository()

    def run(
        self,
        bars: Sequence[MarketBar],
        signal_generator_factory: Callable[[], SignalGenerator],
        *,
        write_reports: bool = True,
    ) -> WalkForwardResult:
        ordered_bars = self.repository.normalize(bars)
        folds = self._fold_windows(ordered_bars)
        fold_results: list[WalkForwardFoldResult] = []
        for fold_index, (train_bars, test_bars) in enumerate(folds, start=1):
            fold_config = self._fold_backtest_config(fold_index)
            fold_provenance = self._fold_alpha_provenance(test_bars)
            fold_engine = BacktestEngine(
                fold_config,
                market_data_repository=self.repository,
                alpha_provenance=fold_provenance,
            )
            backtest_result = fold_engine.run(
                test_bars,
                signal_generator_factory(),
                write_reports=False,
            )
            fold_results.append(
                WalkForwardFoldResult(
                    fold_index=fold_index,
                    train_event_count=len(train_bars),
                    test_event_count=len(test_bars),
                    train_start_at=train_bars[0].timestamp.isoformat(),
                    train_end_at=train_bars[-1].timestamp.isoformat(),
                    test_start_at=test_bars[0].timestamp.isoformat(),
                    test_end_at=test_bars[-1].timestamp.isoformat(),
                    backtest_result=backtest_result,
                )
            )
        decision = self._decide(fold_results)
        result = WalkForwardResult(
            run_id=self.config.run_id,
            strategy_id=self.config.base_backtest_config.strategy_id,
            dataset_id=self.config.base_backtest_config.dataset_id,
            fold_count=len(fold_results),
            passing_fold_count=sum(
                1 for fold in fold_results if fold.backtest_result.decision.status in self.PASSING_BACKTEST_STATUSES
            ),
            aggregate_net_pnl_eur=sum(fold.backtest_result.metrics.total_net_pnl_eur for fold in fold_results),
            average_fold_return_pct=self._average_return(fold_results),
            worst_fold_drawdown_pct=self._worst_drawdown(fold_results),
            total_closed_trades=sum(fold.backtest_result.trade_count for fold in fold_results),
            folds=tuple(fold_results),
            decision=decision,
        )
        if write_reports:
            result = self._write_reports(result)
        return result

    def _fold_windows(self, bars: Sequence[MarketBar]) -> list[tuple[list[MarketBar], list[MarketBar]]]:
        if len(bars) < self.config.train_window_bars + self.config.test_window_bars:
            return []
        step = self.config.step_window_bars or self.config.test_window_bars
        windows: list[tuple[list[MarketBar], list[MarketBar]]] = []
        start = 0
        while start + self.config.train_window_bars + self.config.test_window_bars <= len(bars):
            train_end = start + self.config.train_window_bars
            test_end = train_end + self.config.test_window_bars
            windows.append((list(bars[start:train_end]), list(bars[train_end:test_end])))
            start += step
        return windows

    def _fold_alpha_provenance(self, test_bars: Sequence[MarketBar]) -> BacktestSignalProvenance | None:
        """Bind each OOS replay to its exact test-window input.

        The parent provenance remains the verified full validation snapshot;
        only ``input_snapshot_fingerprint`` changes for the isolated fold. This
        prevents a full-run fingerprint from being incorrectly asserted for a
        smaller out-of-sample slice.
        """

        if self.config.alpha_provenance is None:
            return None
        return replace(
            self.config.alpha_provenance,
            input_snapshot_fingerprint=fingerprint_backtest_bars(test_bars),
        )

    def _fold_backtest_config(self, fold_index: int) -> BacktestConfig:
        base = self.config.base_backtest_config
        return BacktestConfig(
            run_id=f"{self.config.run_id}_fold_{fold_index:03d}",
            strategy_id=base.strategy_id,
            dataset_id=base.dataset_id,
            hypothesis=base.hypothesis,
            initial_capital_eur=base.initial_capital_eur,
            default_order_notional_eur=base.default_order_notional_eur,
            output_dir=self.config.output_dir / "folds",
            cost_config=base.cost_config,
            min_closed_trades=base.min_closed_trades,
            min_profit_factor=base.min_profit_factor,
            max_drawdown_pct=base.max_drawdown_pct,
            close_open_positions_at_end=base.close_open_positions_at_end,
            min_signal_net_edge_bps=base.min_signal_net_edge_bps,
            execution_timing=base.execution_timing,
        )

    def _decide(self, folds: Sequence[WalkForwardFoldResult]) -> WalkForwardDecision:
        if len(folds) < self.config.min_folds:
            return WalkForwardDecision(
                status="keep_testing",
                reason="insufficient_walk_forward_folds",
                proposed_registry_status="candidate",
            )
        passing = sum(1 for fold in folds if fold.backtest_result.decision.status in self.PASSING_BACKTEST_STATUSES)
        if passing < self.config.min_passing_folds:
            return WalkForwardDecision(
                status="modify",
                reason="insufficient_passing_folds",
                proposed_registry_status="candidate",
            )
        aggregate_net = sum(fold.backtest_result.metrics.total_net_pnl_eur for fold in folds)
        if aggregate_net <= 0.0:
            return WalkForwardDecision(
                status="modify",
                reason="non_positive_walk_forward_net_pnl",
                proposed_registry_status="candidate",
            )
        return WalkForwardDecision(
            status="walk_forward_passed",
            reason="walk_forward_criteria_passed_for_human_review",
            proposed_registry_status="walk_forward_passed",
        )

    @staticmethod
    def _average_return(folds: Sequence[WalkForwardFoldResult]) -> float | None:
        if not folds:
            return None
        return sum(fold.backtest_result.metrics.total_return_pct for fold in folds) / len(folds)

    @staticmethod
    def _worst_drawdown(folds: Sequence[WalkForwardFoldResult]) -> float | None:
        if not folds:
            return None
        return max(fold.backtest_result.metrics.max_drawdown_pct for fold in folds)

    def _write_reports(self, result: WalkForwardResult) -> WalkForwardResult:
        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path = output_dir / f"{self.config.run_id}.json"
        md_path = output_dir / f"{self.config.run_id}.md"
        json_path.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        md_path.write_text(render_walk_forward_report(result), encoding="utf-8")
        return WalkForwardResult(
            run_id=result.run_id,
            strategy_id=result.strategy_id,
            dataset_id=result.dataset_id,
            fold_count=result.fold_count,
            passing_fold_count=result.passing_fold_count,
            aggregate_net_pnl_eur=result.aggregate_net_pnl_eur,
            average_fold_return_pct=result.average_fold_return_pct,
            worst_fold_drawdown_pct=result.worst_fold_drawdown_pct,
            total_closed_trades=result.total_closed_trades,
            folds=result.folds,
            decision=result.decision,
            json_report_path=str(json_path),
            markdown_report_path=str(md_path),
        )


def render_walk_forward_report(result: WalkForwardResult) -> str:
    lines = [
        f"# Walk-Forward Run - {result.run_id}",
        "",
        f"Strategy: `{result.strategy_id}`",
        f"Dataset: `{result.dataset_id}`",
        "",
        "## Summary",
        "",
        f"- Folds: {result.fold_count}",
        f"- Passing folds: {result.passing_fold_count}",
        f"- Total closed trades: {result.total_closed_trades}",
        f"- Aggregate net PnL: {result.aggregate_net_pnl_eur:.6f}",
        f"- Average fold return: {_fmt(result.average_fold_return_pct)}%",
        f"- Worst fold drawdown: {_fmt(result.worst_fold_drawdown_pct)}%",
        "",
        "## Folds",
        "",
        "| Fold | Train events | Test events | Net PnL | Return | Trades | Decision |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for fold in result.folds:
        metrics = fold.backtest_result.metrics
        lines.append(
            f"| {fold.fold_index} | {fold.train_event_count} | {fold.test_event_count} | "
            f"{metrics.total_net_pnl_eur:.6f} | {metrics.total_return_pct:.4f}% | "
            f"{fold.backtest_result.trade_count} | {fold.backtest_result.decision.status} |"
        )
    lines.extend(
        [
            "",
            "## Decision",
            "",
            f"Decision: `{result.decision.status}`",
            f"Registry proposal: `{result.decision.proposed_registry_status}`",
            f"Reason: `{result.decision.reason}`",
            f"Live promotion allowed: `{result.decision.live_promotion_allowed}`",
            "",
        ]
    )
    return "\n".join(lines)


def _fmt(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.6f}"
