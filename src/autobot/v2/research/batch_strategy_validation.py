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
from .validation_runner import DataSource


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
class StrategyBatchDecision:
    strategy: str
    status: str
    reasons: tuple[str, ...]
    blockers: tuple[str, ...]
    supporting_windows: tuple[str, ...]
    failing_windows: tuple[str, ...]
    best_symbols: tuple[str, ...]
    rejected_symbols: tuple[str, ...]
    sample_size_warning: str | None
    overfit_risk: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reasons"] = list(self.reasons)
        payload["blockers"] = list(self.blockers)
        payload["supporting_windows"] = list(self.supporting_windows)
        payload["failing_windows"] = list(self.failing_windows)
        payload["best_symbols"] = list(self.best_symbols)
        payload["rejected_symbols"] = list(self.rejected_symbols)
        return payload


@dataclass(frozen=True)
class BatchStrategyValidationConfig:
    run_id: str
    symbols: tuple[str, ...]
    state_db_path: Path | None = None
    data_source: DataSource = "autobot_state_db"
    data_path: Path | None = None
    strategies: tuple[str, ...] = ("trend", "mean_reversion")
    timeframe: str = "5m"
    mode: str = "backtest"
    output_dir: Path = Path("reports/research/batch_strategy_validation")
    initial_capital_eur: float = 1_000.0
    order_notional_eur: float = 100.0
    min_closed_trades: int = 30
    min_profit_factor: float = 1.2
    max_drawdown_pct: float = 15.0
    min_mfe_to_cost: float = 1.5
    min_exit_capture_bps: float = 0.0
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
        if self.min_mfe_to_cost < 0.0:
            raise ValueError("min_mfe_to_cost must not be negative")
        if self.data_source not in {"autobot_state_db", "csv"}:
            raise ValueError("data_source must be autobot_state_db or csv")
        if self.effective_data_path is None:
            raise ValueError("state_db_path or data_path is required")
        self.cost_config.validate()

    @property
    def effective_data_path(self) -> Path | None:
        return self.data_path or self.state_db_path


@dataclass(frozen=True)
class BatchStrategyValidationReport:
    run_id: str
    generated_at: str
    data_source: str
    data_path: str
    state_db_path: str
    symbols: tuple[str, ...]
    strategies: tuple[str, ...]
    timeframe: str
    cost_config: dict[str, Any]
    windows: tuple[BatchValidationWindow, ...]
    window_summaries: tuple[BatchWindowSummary, ...]
    matrix_report_paths: tuple[str, ...]
    strategy_decisions: tuple[StrategyBatchDecision, ...]
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
            "data_source": self.data_source,
            "data_path": self.data_path,
            "state_db_path": self.state_db_path,
            "symbols": list(self.symbols),
            "strategies": list(self.strategies),
            "timeframe": self.timeframe,
            "cost_config": dict(self.cost_config),
            "windows": [item.to_dict() for item in self.windows],
            "window_summaries": [item.to_dict() for item in self.window_summaries],
            "matrix_report_paths": list(self.matrix_report_paths),
            "strategy_decisions": [item.to_dict() for item in self.strategy_decisions],
            "status_by_strategy": dict(self.status_by_strategy),
            "conclusion": self.conclusion,
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
            "safety_notes": list(self.safety_notes),
        }


def run_batch_strategy_validation(config: BatchStrategyValidationConfig) -> BatchStrategyValidationReport:
    effective_path = config.effective_data_path
    if effective_path is None:
        raise ValueError("state_db_path or data_path is required")
    windows = config.windows or infer_default_windows(
        effective_path,
        symbols=config.symbols,
        data_source=config.data_source,
    )
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
                data_source=config.data_source,
                data_path=effective_path,
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
    decisions = decide_strategy_batch(
        matrices,
        config.strategies,
        min_closed_trades=config.min_closed_trades,
        min_profit_factor=config.min_profit_factor,
        max_drawdown_pct=config.max_drawdown_pct,
        min_mfe_to_cost=config.min_mfe_to_cost,
        min_exit_capture_bps=config.min_exit_capture_bps,
        mode=config.mode,
    )
    report = BatchStrategyValidationReport(
        run_id=config.run_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        data_source=config.data_source,
        data_path=str(effective_path),
        state_db_path=str(config.state_db_path or ""),
        symbols=config.symbols,
        strategies=config.strategies,
        timeframe=config.timeframe,
        cost_config=config.cost_config.to_dict(),
        windows=tuple(windows),
        window_summaries=tuple(summaries),
        matrix_report_paths=tuple(matrix_paths),
        strategy_decisions=tuple(decisions),
        status_by_strategy={decision.strategy: decision.status for decision in decisions},
        conclusion=_batch_conclusion(summaries),
    )
    return write_batch_strategy_validation_report(report, output_dir)


def infer_default_windows(
    data_path: str | Path,
    *,
    symbols: Sequence[str],
    data_source: DataSource = "autobot_state_db",
) -> tuple[BatchValidationWindow, ...]:
    repository = MarketDataRepository()
    if data_source == "autobot_state_db":
        bars = repository.load_autobot_state_db(data_path, symbols=symbols, canonicalize_symbols=True)
    elif data_source == "csv":
        bars = repository.load_csv(data_path)
        wanted = {symbol.upper() for symbol in symbols}
        bars = [bar for bar in bars if bar.symbol.upper() in wanted]
    else:
        raise ValueError("data_source must be autobot_state_db or csv")
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
        data_source=report.data_source,
        data_path=report.data_path,
        state_db_path=report.state_db_path,
        symbols=report.symbols,
        strategies=report.strategies,
        timeframe=report.timeframe,
        cost_config=report.cost_config,
        windows=report.windows,
        window_summaries=report.window_summaries,
        matrix_report_paths=report.matrix_report_paths,
        strategy_decisions=report.strategy_decisions,
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
        f"Data source: `{report.data_source}`",
        f"Data path: `{report.data_path}`",
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
    lines.extend(["", "## Strategy Decisions", ""])
    lines.append("| Strategy | Status | Blockers | Supporting Windows | Failing Windows | Best Symbols | Rejected Symbols | Overfit Risk |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for decision in sorted(report.strategy_decisions, key=lambda item: item.strategy):
        lines.append(
            f"| {decision.strategy} | {decision.status} | {', '.join(decision.blockers) or 'none'} | "
            f"{', '.join(decision.supporting_windows) or '-'} | {', '.join(decision.failing_windows) or '-'} | "
            f"{', '.join(decision.best_symbols) or '-'} | {', '.join(decision.rejected_symbols) or '-'} | "
            f"{decision.overfit_risk} |"
        )
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


def decide_strategy_batch(
    matrices: Sequence[MatrixRunResult],
    strategies: Sequence[str],
    *,
    min_closed_trades: int,
    min_profit_factor: float,
    max_drawdown_pct: float,
    min_mfe_to_cost: float = 1.5,
    min_exit_capture_bps: float = 0.0,
    mode: str = "backtest",
) -> tuple[StrategyBatchDecision, ...]:
    decisions: list[StrategyBatchDecision] = []
    for strategy in strategies:
        cells = [
            cell
            for matrix in matrices
            for cell in matrix.results
            if cell.strategy == strategy and cell.status == "ok"
        ]
        if not cells:
            decisions.append(
                StrategyBatchDecision(
                    strategy=strategy,
                    status="research_only",
                    reasons=("no successful validation cells were produced",),
                    blockers=("no_successful_cells",),
                    supporting_windows=(),
                    failing_windows=tuple(matrix.run_id for matrix in matrices),
                    best_symbols=(),
                    rejected_symbols=(),
                    sample_size_warning="no closed trades available",
                    overfit_risk="unknown",
                )
            )
            continue
        total_trades = sum(int(cell.closed_trades or 0) for cell in cells)
        total_net = sum(float(cell.net_pnl_eur or 0.0) for cell in cells)
        blockers: list[str] = []
        reasons: list[str] = []
        positive_cells = [cell for cell in cells if (cell.net_pnl_eur or 0.0) > 0.0]
        eligible_cells = [
            cell
            for cell in positive_cells
            if int(cell.closed_trades or 0) >= min_closed_trades
            and (cell.profit_factor or 0.0) >= min_profit_factor
            and (cell.max_drawdown_pct is None or cell.max_drawdown_pct <= max_drawdown_pct)
        ]
        supporting_windows, failing_windows = _window_support_for_strategy(matrices, strategy, min_closed_trades)
        positive_by_symbol = _net_pnl_by_symbol(positive_cells)
        all_by_symbol = _net_pnl_by_symbol(cells)
        best_symbols = tuple(f"{symbol}:{value:.6f}" for symbol, value in sorted(positive_by_symbol.items(), key=lambda item: item[1], reverse=True)[:5])
        rejected_symbols = tuple(
            f"{symbol}:{value:.6f}"
            for symbol, value in sorted(all_by_symbol.items(), key=lambda item: item[1])[:5]
            if value <= 0.0
        )
        if total_net <= 0.0:
            blockers.append("non_positive_total_net_pnl")
        if total_trades < min_closed_trades:
            blockers.append("insufficient_total_closed_trades")
        if not positive_cells:
            blockers.append("no_positive_net_pnl_cells")
        if not any((cell.profit_factor or 0.0) >= min_profit_factor for cell in positive_cells):
            blockers.append("profit_factor_below_threshold")
        if any((cell.max_drawdown_pct or 0.0) > max_drawdown_pct for cell in cells):
            blockers.append("drawdown_above_threshold")
        required_supporting = max(1, int(len(matrices) * 0.6 + 0.999))
        if len(supporting_windows) < required_supporting:
            blockers.append("insufficient_window_stability")
        if mode == "walk_forward" and len(supporting_windows) < required_supporting:
            blockers.append("walk_forward_not_passed")
        if _is_dominated_by_single_symbol(positive_by_symbol):
            blockers.append("dominated_by_single_symbol")
        if not eligible_cells:
            blockers.append("no_cell_passes_candidate_thresholds")
        evidence_cells = eligible_cells or positive_cells or [
            cell for cell in cells if int(cell.closed_trades or 0) > 0
        ]
        _append_evidence_blockers(
            blockers,
            evidence_cells,
            min_mfe_to_cost=min_mfe_to_cost,
            min_exit_capture_bps=min_exit_capture_bps,
        )
        if positive_cells:
            reasons.append(f"{len(positive_cells)} positive cells exist but full validation evidence is incomplete")
        if total_net <= 0.0:
            reasons.append("aggregate net PnL is not positive after costs")
        if blockers:
            status = "research_only"
        else:
            status = "shadow_candidate"
        sample_warning = None
        if total_trades < max(min_closed_trades, min_closed_trades * max(1, len(matrices) // 2)):
            sample_warning = f"sample too small: {total_trades} closed trades"
        decisions.append(
            StrategyBatchDecision(
                strategy=strategy,
                status=status,
                reasons=tuple(dict.fromkeys(reasons or ("candidate thresholds not met",))),
                blockers=tuple(dict.fromkeys(blockers)),
                supporting_windows=tuple(supporting_windows),
                failing_windows=tuple(failing_windows),
                best_symbols=best_symbols,
                rejected_symbols=rejected_symbols,
                sample_size_warning=sample_warning,
                overfit_risk=_overfit_risk(blockers, positive_by_symbol, positive_cells, cells),
            )
        )
    return tuple(decisions)


def _append_evidence_blockers(
    blockers: list[str],
    cells: Sequence[Any],
    *,
    min_mfe_to_cost: float,
    min_exit_capture_bps: float,
) -> None:
    evidence = (
        ("no_trade", "beats_no_trade", "baseline_no_trade_unavailable", "does_not_beat_no_trade"),
        ("buy_and_hold", "beats_buy_and_hold", "baseline_buy_and_hold_unavailable", "does_not_beat_buy_and_hold"),
        (
            "random_signal_same_frequency",
            "beats_random_signal_same_frequency",
            "baseline_random_signal_unavailable",
            "does_not_beat_random_signal",
        ),
    )
    if not cells:
        blockers.extend(item[2] for item in evidence)
        blockers.extend(("mfe_to_cost_unavailable", "exit_capture_unavailable"))
        return
    for _name, field_name, unavailable, failed in evidence:
        values = [getattr(cell, field_name, None) for cell in cells]
        if any(value is None for value in values):
            blockers.append(unavailable)
        elif not all(bool(value) for value in values):
            blockers.append(failed)
    mfe_values = [getattr(cell, "average_mfe_to_cost_ratio", None) for cell in cells]
    if any(value is None for value in mfe_values):
        blockers.append("mfe_to_cost_unavailable")
    elif not all(float(value) >= min_mfe_to_cost for value in mfe_values):
        blockers.append("mfe_to_cost_below_threshold")
    exit_values = [getattr(cell, "average_exit_capture_bps", None) for cell in cells]
    if any(value is None for value in exit_values):
        blockers.append("exit_capture_unavailable")
    elif not all(float(value) > min_exit_capture_bps for value in exit_values):
        blockers.append("exit_capture_below_threshold")


def _window_support_for_strategy(
    matrices: Sequence[MatrixRunResult],
    strategy: str,
    min_closed_trades: int,
) -> tuple[list[str], list[str]]:
    supporting: list[str] = []
    failing: list[str] = []
    for matrix in matrices:
        cells = [cell for cell in matrix.results if cell.strategy == strategy and cell.status == "ok"]
        trades = sum(int(cell.closed_trades or 0) for cell in cells)
        net_pnl = sum(float(cell.net_pnl_eur or 0.0) for cell in cells)
        if cells and trades >= min_closed_trades and net_pnl > 0.0:
            supporting.append(matrix.run_id)
        else:
            failing.append(matrix.run_id)
    return supporting, failing


def _net_pnl_by_symbol(cells: Sequence[Any]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for cell in cells:
        totals[cell.symbol] = totals.get(cell.symbol, 0.0) + float(cell.net_pnl_eur or 0.0)
    return totals


def _is_dominated_by_single_symbol(positive_by_symbol: dict[str, float]) -> bool:
    positive_values = [value for value in positive_by_symbol.values() if value > 0.0]
    if len(positive_values) <= 1:
        return bool(positive_values)
    total = sum(positive_values)
    return total > 0.0 and max(positive_values) / total >= 0.70


def _overfit_risk(
    blockers: Sequence[str],
    positive_by_symbol: dict[str, float],
    positive_cells: Sequence[Any],
    all_cells: Sequence[Any],
) -> str:
    if any(blocker.startswith("baseline_") for blocker in blockers):
        return "high"
    if _is_dominated_by_single_symbol(positive_by_symbol):
        return "high"
    if len(positive_cells) < max(2, len(all_cells) // 4):
        return "medium"
    return "low"


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
