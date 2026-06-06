"""Multi-window strategy validation for AUTOBOT research.

This runner reuses the existing validation matrix across deterministic time
windows. It is read-only and research-only.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

from .execution_cost_model import ExecutionCostConfig
from .market_data_repository import MarketDataRepository
from .validation_matrix import MatrixRunConfig, MatrixRunResult, run_validation_matrix


@dataclass(frozen=True)
class BatchValidationWindow:
    name: str
    start_at: str | None
    end_at: str | None
    regime_hint: str = "unknown"
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BatchWindowSummary:
    window_name: str
    cell_count: int
    success_count: int
    error_count: int
    total_trades: int
    total_net_pnl_eur: float
    profitable_cell_count: int
    best_cell: dict[str, Any] | None
    worst_cell: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BatchStrategyValidationConfig:
    run_id: str
    state_db_path: Path
    symbols: tuple[str, ...]
    strategies: tuple[str, ...] = ("grid", "trend", "mean_reversion")
    timeframe: str = "5m"
    mode: str = "backtest"
    output_dir: Path = Path("reports/research/batch_strategy_validation")
    initial_capital_eur: float = 1_000.0
    order_notional_eur: float = 100.0
    min_closed_trades: int = 30
    min_profit_factor: float = 1.2
    max_drawdown_pct: float = 15.0
    include_regime_context: bool = True
    cost_config: ExecutionCostConfig = field(default_factory=ExecutionCostConfig)
    windows: tuple[BatchValidationWindow, ...] = ()

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id must not be empty")
        if not self.symbols:
            raise ValueError("symbols must not be empty")
        if not self.strategies:
            raise ValueError("strategies must not be empty")
        if self.mode not in {"backtest", "walk_forward"}:
            raise ValueError("mode must be backtest or walk_forward")
        self.cost_config.validate()


@dataclass(frozen=True)
class BatchStrategyValidationReport:
    run_id: str
    generated_at: str
    state_db_path: str
    symbols: tuple[str, ...]
    strategies: tuple[str, ...]
    timeframe: str
    cost_config: dict[str, float]
    windows: tuple[BatchValidationWindow, ...]
    window_summaries: tuple[BatchWindowSummary, ...]
    matrix_report_paths: tuple[str, ...]
    status_by_strategy: dict[str, str]
    conclusion: str
    json_report_path: str | None = None
    markdown_report_path: str | None = None
    safety_notes: tuple[str, ...] = (
        "Batch strategy validation is research-only.",
        "No runtime paper/live service is started.",
        "No paper or live order is created.",
        "No strategy registry mutation is performed.",
        "No live trading permission is granted.",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "state_db_path": self.state_db_path,
            "symbols": list(self.symbols),
            "strategies": list(self.strategies),
            "timeframe": self.timeframe,
            "cost_config": dict(self.cost_config),
            "windows": [item.to_dict() for item in self.windows],
            "window_summaries": [item.to_dict() for item in self.window_summaries],
            "matrix_report_paths": list(self.matrix_report_paths),
            "status_by_strategy": dict(self.status_by_strategy),
            "conclusion": self.conclusion,
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
            "safety_notes": list(self.safety_notes),
        }


def run_batch_strategy_validation(config: BatchStrategyValidationConfig) -> BatchStrategyValidationReport:
    windows = config.windows or infer_default_windows(config.state_db_path, symbols=config.symbols)
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    matrix_paths: list[str] = []
    summaries: list[BatchWindowSummary] = []
    matrices: list[MatrixRunResult] = []
    for window in windows:
        safe_window = window.name.replace(" ", "_").lower()
        matrix = run_validation_matrix(
            MatrixRunConfig(
                run_id=f"{config.run_id}_{safe_window}",
                data_source="autobot_state_db",
                data_path=config.state_db_path,
                symbols=config.symbols,
                strategies=config.strategies,  # type: ignore[arg-type]
                mode=config.mode,  # type: ignore[arg-type]
                output_dir=output_dir / "matrices" / safe_window,
                initial_capital_eur=config.initial_capital_eur,
                order_notional_eur=config.order_notional_eur,
                min_closed_trades=config.min_closed_trades,
                min_profit_factor=config.min_profit_factor,
                max_drawdown_pct=config.max_drawdown_pct,
                cost_config=config.cost_config,
                start_at=window.start_at,
                end_at=window.end_at,
                include_regime_context=config.include_regime_context,
            )
        )
        matrices.append(matrix)
        if matrix.json_report_path:
            matrix_paths.append(matrix.json_report_path)
        summaries.append(_summarize_matrix(window, matrix))
    report = BatchStrategyValidationReport(
        run_id=config.run_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        state_db_path=str(config.state_db_path),
        symbols=config.symbols,
        strategies=config.strategies,
        timeframe=config.timeframe,
        cost_config=config.cost_config.to_dict(),
        windows=tuple(windows),
        window_summaries=tuple(summaries),
        matrix_report_paths=tuple(matrix_paths),
        status_by_strategy=_status_by_strategy(matrices, config.strategies),
        conclusion=_batch_conclusion(summaries),
    )
    return write_batch_strategy_validation_report(report, output_dir)


def infer_default_windows(
    state_db_path: str | Path,
    *,
    symbols: Sequence[str],
) -> tuple[BatchValidationWindow, ...]:
    repository = MarketDataRepository()
    bars = repository.load_autobot_state_db(state_db_path, symbols=symbols, canonicalize_symbols=True)
    if len(bars) < 8:
        return (
            BatchValidationWindow("full", None, None, "all", "Full available sample."),
        )
    timestamps = sorted({bar.timestamp for bar in bars})
    start = timestamps[0]
    end = timestamps[-1]
    span = end - start
    one_third = span / 3
    first_end = start + one_third
    second_end = start + one_third * 2
    weekend_start = _first_weekend_start(timestamps)
    windows = [
        BatchValidationWindow("full", start.isoformat(), end.isoformat(), "all", "Full available sample."),
        BatchValidationWindow("early", start.isoformat(), first_end.isoformat(), "sample_segment", "First third."),
        BatchValidationWindow("middle", first_end.isoformat(), second_end.isoformat(), "sample_segment", "Middle third."),
        BatchValidationWindow("late", second_end.isoformat(), end.isoformat(), "sample_segment", "Final third."),
    ]
    if weekend_start:
        weekend_end = weekend_start + timedelta(days=2)
        windows.append(
            BatchValidationWindow(
                "weekend",
                weekend_start.isoformat(),
                min(weekend_end, end).isoformat(),
                "weekend",
                "First weekend segment found in the dataset.",
            )
        )
    return tuple(windows)


def write_batch_strategy_validation_report(
    report: BatchStrategyValidationReport,
    output_dir: str | Path,
) -> BatchStrategyValidationReport:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / f"{report.run_id}.json"
    markdown_path = output_path / f"{report.run_id}.md"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(render_batch_strategy_validation_report(report), encoding="utf-8")
    return BatchStrategyValidationReport(
        run_id=report.run_id,
        generated_at=report.generated_at,
        state_db_path=report.state_db_path,
        symbols=report.symbols,
        strategies=report.strategies,
        timeframe=report.timeframe,
        cost_config=report.cost_config,
        windows=report.windows,
        window_summaries=report.window_summaries,
        matrix_report_paths=report.matrix_report_paths,
        status_by_strategy=report.status_by_strategy,
        conclusion=report.conclusion,
        json_report_path=str(json_path),
        markdown_report_path=str(markdown_path),
        safety_notes=report.safety_notes,
    )


def render_batch_strategy_validation_report(report: BatchStrategyValidationReport) -> str:
    lines = [
        f"# Batch Strategy Validation - {report.run_id}",
        "",
        f"Generated at: `{report.generated_at}`",
        f"Strategies: `{', '.join(report.strategies)}`",
        f"Symbols: `{', '.join(report.symbols)}`",
        f"Cost config: `{json.dumps(report.cost_config, sort_keys=True)}`",
        "",
        "## Window Summary",
        "",
        "| Window | Cells | Success | Errors | Trades | Net PnL | Profitable Cells | Best | Worst |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for item in report.window_summaries:
        best = item.best_cell or {}
        worst = item.worst_cell or {}
        lines.append(
            f"| {item.window_name} | {item.cell_count} | {item.success_count} | {item.error_count} | "
            f"{item.total_trades} | {item.total_net_pnl_eur:.6f} | {item.profitable_cell_count} | "
            f"{best.get('symbol', '-')}/{best.get('strategy', '-')} {best.get('net_pnl_eur', '')} | "
            f"{worst.get('symbol', '-')}/{worst.get('strategy', '-')} {worst.get('net_pnl_eur', '')} |"
        )
    lines.extend(["", "## Status By Strategy", ""])
    lines.extend(f"- `{strategy}`: `{status}`" for strategy, status in sorted(report.status_by_strategy.items()))
    lines.extend(["", "## Conclusion", "", report.conclusion, "", "## Safety", ""])
    lines.extend(f"- {note}" for note in report.safety_notes)
    lines.append("")
    return "\n".join(lines)


def _summarize_matrix(window: BatchValidationWindow, matrix: MatrixRunResult) -> BatchWindowSummary:
    ok_cells = [cell for cell in matrix.results if cell.status == "ok"]
    sorted_cells = sorted(ok_cells, key=lambda cell: cell.net_pnl_eur if cell.net_pnl_eur is not None else -10**12)
    total_net = sum(float(cell.net_pnl_eur or 0.0) for cell in ok_cells)
    return BatchWindowSummary(
        window_name=window.name,
        cell_count=matrix.cell_count,
        success_count=matrix.success_count,
        error_count=matrix.error_count,
        total_trades=sum(int(cell.closed_trades or 0) for cell in ok_cells),
        total_net_pnl_eur=total_net,
        profitable_cell_count=sum(1 for cell in ok_cells if (cell.net_pnl_eur or 0.0) > 0.0),
        best_cell=sorted_cells[-1].to_dict() if sorted_cells else None,
        worst_cell=sorted_cells[0].to_dict() if sorted_cells else None,
    )


def _status_by_strategy(matrices: Sequence[MatrixRunResult], strategies: Sequence[str]) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for strategy in strategies:
        cells = [
            cell
            for matrix in matrices
            for cell in matrix.results
            if cell.strategy == strategy and cell.status == "ok"
        ]
        if not cells:
            statuses[strategy] = "research_only:no_successful_cells"
            continue
        positive = [cell for cell in cells if (cell.net_pnl_eur or 0.0) > 0.0]
        enough_samples = [cell for cell in positive if int(cell.closed_trades or 0) >= 100]
        stable_positive = len(enough_samples) >= max(1, len(cells) // 4)
        statuses[strategy] = "shadow_candidate" if stable_positive else "research_only"
    return statuses


def _batch_conclusion(summaries: Sequence[BatchWindowSummary]) -> str:
    if not summaries:
        return "No validation windows were run."
    positive_windows = sum(1 for item in summaries if item.total_net_pnl_eur > 0.0)
    if positive_windows == len(summaries):
        return "All windows were net positive, but human review and strategy-level thresholds remain required."
    if positive_windows:
        return "Some windows were net positive, but evidence is unstable; keep strategies research-only."
    return "No validation window was net positive after costs; keep strategies research-only."


def _first_weekend_start(timestamps: Sequence[datetime]) -> datetime | None:
    for timestamp in timestamps:
        if timestamp.weekday() == 5:
            return timestamp
    return None
