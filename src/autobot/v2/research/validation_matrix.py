"""Batch validation matrix for AUTOBOT research strategy families."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Sequence

from .execution_cost_model import ExecutionCostConfig
from .validation_runner import DataSource, RunMode, StrategyName, ValidationRunnerConfig, run_validation


@dataclass(frozen=True)
class MatrixRunConfig:
    run_id: str
    data_source: DataSource
    data_path: Path
    symbols: tuple[str, ...]
    strategies: tuple[StrategyName, ...] = ("grid", "trend", "mean_reversion")
    mode: RunMode = "backtest"
    output_dir: Path = Path("reports/research_matrix")
    initial_capital_eur: float = 1_000.0
    order_notional_eur: float = 100.0
    min_closed_trades: int = 30
    min_profit_factor: float = 1.2
    max_drawdown_pct: float = 15.0
    cost_config: ExecutionCostConfig = field(default_factory=ExecutionCostConfig)
    strategy_configs: dict[str, dict[str, Any]] = field(default_factory=dict)
    start_at: str | None = None
    end_at: str | None = None
    limit: int | None = None
    train_window_bars: int = 200
    test_window_bars: int = 100
    step_window_bars: int | None = None
    min_folds: int = 3
    min_passing_folds: int = 2

    def __post_init__(self) -> None:
        if not self.symbols:
            raise ValueError("symbols must not be empty")
        if not self.strategies:
            raise ValueError("strategies must not be empty")


@dataclass(frozen=True)
class MatrixCellResult:
    run_id: str
    symbol: str
    strategy: str
    mode: str
    status: str
    decision: str | None = None
    reason: str | None = None
    bar_count: int = 0
    closed_trades: int = 0
    net_pnl_eur: float | None = None
    total_return_pct: float | None = None
    profit_factor: float | None = None
    max_drawdown_pct: float | None = None
    report_path: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MatrixRunResult:
    run_id: str
    mode: str
    cell_count: int
    success_count: int
    error_count: int
    results: tuple[MatrixCellResult, ...]
    json_report_path: str | None = None
    markdown_report_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "mode": self.mode,
            "cell_count": self.cell_count,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "results": [result.to_dict() for result in self.results],
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
        }


def run_validation_matrix(config: MatrixRunConfig, *, write_reports: bool = True) -> MatrixRunResult:
    cells: list[MatrixCellResult] = []
    for symbol in config.symbols:
        for strategy in config.strategies:
            cell_run_id = f"{config.run_id}_{symbol}_{strategy}".replace("/", "_")
            runner_config = ValidationRunnerConfig(
                run_id=cell_run_id,
                strategy=strategy,
                data_source=config.data_source,
                data_path=config.data_path,
                symbol=symbol.upper(),
                dataset_id=f"{config.data_source}:{symbol.upper()}",
                mode=config.mode,
                output_dir=config.output_dir / "cells",
                initial_capital_eur=config.initial_capital_eur,
                order_notional_eur=config.order_notional_eur,
                min_closed_trades=config.min_closed_trades,
                min_profit_factor=config.min_profit_factor,
                max_drawdown_pct=config.max_drawdown_pct,
                cost_config=config.cost_config,
                strategy_config=dict(config.strategy_configs.get(strategy, {})),
                start_at=config.start_at,
                end_at=config.end_at,
                limit=config.limit,
                train_window_bars=config.train_window_bars,
                test_window_bars=config.test_window_bars,
                step_window_bars=config.step_window_bars,
                min_folds=config.min_folds,
                min_passing_folds=config.min_passing_folds,
            )
            try:
                runner_result = run_validation(runner_config)
                cells.append(_cell_from_runner_result(cell_run_id, symbol, strategy, runner_result))
            except Exception as exc:
                cells.append(
                    MatrixCellResult(
                        run_id=cell_run_id,
                        symbol=symbol.upper(),
                        strategy=strategy,
                        mode=config.mode,
                        status="error",
                        error=str(exc),
                    )
                )
    result = MatrixRunResult(
        run_id=config.run_id,
        mode=config.mode,
        cell_count=len(cells),
        success_count=sum(1 for cell in cells if cell.status == "ok"),
        error_count=sum(1 for cell in cells if cell.status == "error"),
        results=tuple(cells),
    )
    if write_reports:
        result = _write_matrix_reports(config, result)
    return result


def _cell_from_runner_result(cell_run_id: str, symbol: str, strategy: str, runner_result: Any) -> MatrixCellResult:
    result = runner_result.result
    if runner_result.mode == "backtest":
        metrics = result.metrics
        return MatrixCellResult(
            run_id=cell_run_id,
            symbol=symbol.upper(),
            strategy=strategy,
            mode=runner_result.mode,
            status="ok",
            decision=result.decision.status,
            reason=result.decision.reason,
            bar_count=runner_result.bar_count,
            closed_trades=result.trade_count,
            net_pnl_eur=metrics.total_net_pnl_eur,
            total_return_pct=metrics.total_return_pct,
            profit_factor=metrics.profit_factor,
            max_drawdown_pct=metrics.max_drawdown_pct,
            report_path=result.markdown_report_path,
        )
    return MatrixCellResult(
        run_id=cell_run_id,
        symbol=symbol.upper(),
        strategy=strategy,
        mode=runner_result.mode,
        status="ok",
        decision=result.decision.status,
        reason=result.decision.reason,
        bar_count=runner_result.bar_count,
        closed_trades=result.total_closed_trades,
        net_pnl_eur=result.aggregate_net_pnl_eur,
        total_return_pct=result.average_fold_return_pct,
        profit_factor=None,
        max_drawdown_pct=result.worst_fold_drawdown_pct,
        report_path=result.markdown_report_path,
    )


def _write_matrix_reports(config: MatrixRunConfig, result: MatrixRunResult) -> MatrixRunResult:
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{config.run_id}.json"
    md_path = output_dir / f"{config.run_id}.md"
    json_path.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(render_matrix_report(result), encoding="utf-8")
    return MatrixRunResult(
        run_id=result.run_id,
        mode=result.mode,
        cell_count=result.cell_count,
        success_count=result.success_count,
        error_count=result.error_count,
        results=result.results,
        json_report_path=str(json_path),
        markdown_report_path=str(md_path),
    )


def render_matrix_report(result: MatrixRunResult) -> str:
    sorted_cells = sorted(
        result.results,
        key=lambda cell: (
            cell.status != "ok",
            -(cell.net_pnl_eur or -10**12),
            cell.symbol,
            cell.strategy,
        ),
    )
    lines = [
        f"# Research Validation Matrix - {result.run_id}",
        "",
        f"Mode: `{result.mode}`",
        f"Cells: `{result.cell_count}`",
        f"Success: `{result.success_count}`",
        f"Errors: `{result.error_count}`",
        "",
        "## Results",
        "",
        "| Symbol | Strategy | Status | Decision | Reason | Bars | Trades | Net PnL | Return | PF | Max DD |",
        "| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for cell in sorted_cells:
        lines.append(
            f"| {cell.symbol} | {cell.strategy} | {cell.status} | {cell.decision or ''} | "
            f"{cell.reason or cell.error or ''} | {cell.bar_count} | {cell.closed_trades} | "
            f"{_fmt(cell.net_pnl_eur)} | {_fmt(cell.total_return_pct)} | {_fmt(cell.profit_factor)} | "
            f"{_fmt(cell.max_drawdown_pct)} |"
        )
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "This matrix is research-only. It does not authorize live trading and does not update the strategy registry automatically.",
            "",
        ]
    )
    return "\n".join(lines)


def _fmt(value: float | None) -> str:
    return "" if value is None else f"{value:.6f}"
