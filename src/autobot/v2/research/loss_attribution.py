"""Loss attribution helpers for AUTOBOT research trade journals."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Iterable

from .trade_journal import TradeJournal, TradeRecord
from .validation_matrix import MatrixRunResult


@dataclass(frozen=True)
class AttributionBucket:
    key: str
    trade_count: int
    win_count: int
    gross_pnl_eur: float
    net_pnl_eur: float
    fees_eur: float
    slippage_eur: float
    spread_cost_eur: float
    average_duration_seconds: float

    @property
    def win_rate_pct(self) -> float:
        if self.trade_count <= 0:
            return 0.0
        return (self.win_count / self.trade_count) * 100.0

    @property
    def total_cost_eur(self) -> float:
        return self.fees_eur + self.slippage_eur + self.spread_cost_eur

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["win_rate_pct"] = self.win_rate_pct
        payload["total_cost_eur"] = self.total_cost_eur
        return payload


@dataclass(frozen=True)
class LossAttributionResult:
    run_id: str
    strategy_id: str
    symbol: str
    trade_count: int
    gross_pnl_eur: float
    net_pnl_eur: float
    fees_eur: float
    slippage_eur: float
    spread_cost_eur: float
    cost_flipped_trade_count: int
    mfe_above_cost_trade_count: int
    mfe_above_cost_lost_trade_count: int
    average_mfe_bps: float | None
    average_mae_bps: float | None
    average_exit_capture_bps: float | None
    average_mfe_giveback_bps: float | None
    average_mfe_capture_ratio: float | None
    average_positive_mfe_capture_ratio: float | None
    average_mfe_to_cost_ratio: float | None
    losing_trade_count: int
    winning_trade_count: int
    largest_loss_eur: float | None
    largest_win_eur: float | None
    by_failure_mode: tuple[AttributionBucket, ...]
    by_entry_reason: tuple[AttributionBucket, ...]
    by_exit_reason: tuple[AttributionBucket, ...]
    by_symbol: tuple[AttributionBucket, ...]
    json_report_path: str | None = None
    markdown_report_path: str | None = None

    @property
    def total_cost_eur(self) -> float:
        return self.fees_eur + self.slippage_eur + self.spread_cost_eur

    @property
    def cost_drag_vs_gross_abs_pct(self) -> float:
        denominator = abs(self.gross_pnl_eur)
        if denominator <= 0.0:
            return 0.0
        return (self.total_cost_eur / denominator) * 100.0

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "trade_count": self.trade_count,
            "gross_pnl_eur": self.gross_pnl_eur,
            "net_pnl_eur": self.net_pnl_eur,
            "fees_eur": self.fees_eur,
            "slippage_eur": self.slippage_eur,
            "spread_cost_eur": self.spread_cost_eur,
            "total_cost_eur": self.total_cost_eur,
            "cost_drag_vs_gross_abs_pct": self.cost_drag_vs_gross_abs_pct,
            "cost_flipped_trade_count": self.cost_flipped_trade_count,
            "mfe_above_cost_trade_count": self.mfe_above_cost_trade_count,
            "mfe_above_cost_lost_trade_count": self.mfe_above_cost_lost_trade_count,
            "average_mfe_bps": self.average_mfe_bps,
            "average_mae_bps": self.average_mae_bps,
            "average_exit_capture_bps": self.average_exit_capture_bps,
            "average_mfe_giveback_bps": self.average_mfe_giveback_bps,
            "average_mfe_capture_ratio": self.average_mfe_capture_ratio,
            "average_positive_mfe_capture_ratio": self.average_positive_mfe_capture_ratio,
            "average_mfe_to_cost_ratio": self.average_mfe_to_cost_ratio,
            "losing_trade_count": self.losing_trade_count,
            "winning_trade_count": self.winning_trade_count,
            "largest_loss_eur": self.largest_loss_eur,
            "largest_win_eur": self.largest_win_eur,
            "by_failure_mode": [bucket.to_dict() for bucket in self.by_failure_mode],
            "by_entry_reason": [bucket.to_dict() for bucket in self.by_entry_reason],
            "by_exit_reason": [bucket.to_dict() for bucket in self.by_exit_reason],
            "by_symbol": [bucket.to_dict() for bucket in self.by_symbol],
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
        }


@dataclass(frozen=True)
class MatrixCellLossAttribution:
    run_id: str
    strategy: str
    symbol: str
    decision: str | None
    reason: str | None
    journal_path: str
    attribution_report_path: str | None
    trade_count: int
    gross_pnl_eur: float
    net_pnl_eur: float
    total_cost_eur: float
    cost_flipped_trade_count: int
    mfe_above_cost_trade_count: int
    mfe_above_cost_lost_trade_count: int
    average_mfe_bps: float | None
    average_mae_bps: float | None
    average_exit_capture_bps: float | None
    average_mfe_giveback_bps: float | None
    average_mfe_capture_ratio: float | None
    average_positive_mfe_capture_ratio: float | None
    average_mfe_to_cost_ratio: float | None
    worst_exit_reason: str | None
    worst_entry_reason: str | None
    primary_failure_mode: str | None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class MatrixLossAttributionReport:
    matrix_run_id: str
    mode: str
    analyzed_cell_count: int
    missing_journal_count: int
    total_trades: int
    aggregate_gross_pnl_eur: float
    aggregate_net_pnl_eur: float
    aggregate_cost_eur: float
    aggregate_cost_flipped_trade_count: int
    aggregate_mfe_above_cost_trade_count: int
    aggregate_mfe_above_cost_lost_trade_count: int
    aggregate_average_mfe_bps: float | None
    aggregate_average_mae_bps: float | None
    aggregate_average_exit_capture_bps: float | None
    aggregate_average_mfe_giveback_bps: float | None
    aggregate_average_mfe_capture_ratio: float | None
    aggregate_average_positive_mfe_capture_ratio: float | None
    aggregate_average_mfe_to_cost_ratio: float | None
    by_failure_mode: tuple[AttributionBucket, ...]
    cells: tuple[MatrixCellLossAttribution, ...]
    json_report_path: str | None = None
    markdown_report_path: str | None = None

    def to_dict(self) -> dict:
        return {
            "matrix_run_id": self.matrix_run_id,
            "mode": self.mode,
            "analyzed_cell_count": self.analyzed_cell_count,
            "missing_journal_count": self.missing_journal_count,
            "total_trades": self.total_trades,
            "aggregate_gross_pnl_eur": self.aggregate_gross_pnl_eur,
            "aggregate_net_pnl_eur": self.aggregate_net_pnl_eur,
            "aggregate_cost_eur": self.aggregate_cost_eur,
            "aggregate_cost_flipped_trade_count": self.aggregate_cost_flipped_trade_count,
            "aggregate_mfe_above_cost_trade_count": self.aggregate_mfe_above_cost_trade_count,
            "aggregate_mfe_above_cost_lost_trade_count": self.aggregate_mfe_above_cost_lost_trade_count,
            "aggregate_average_mfe_bps": self.aggregate_average_mfe_bps,
            "aggregate_average_mae_bps": self.aggregate_average_mae_bps,
            "aggregate_average_exit_capture_bps": self.aggregate_average_exit_capture_bps,
            "aggregate_average_mfe_giveback_bps": self.aggregate_average_mfe_giveback_bps,
            "aggregate_average_mfe_capture_ratio": self.aggregate_average_mfe_capture_ratio,
            "aggregate_average_positive_mfe_capture_ratio": self.aggregate_average_positive_mfe_capture_ratio,
            "aggregate_average_mfe_to_cost_ratio": self.aggregate_average_mfe_to_cost_ratio,
            "by_failure_mode": [bucket.to_dict() for bucket in self.by_failure_mode],
            "cells": [cell.to_dict() for cell in self.cells],
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
        }


def analyze_trade_losses(records: Iterable[TradeRecord], *, run_id: str | None = None) -> LossAttributionResult:
    trades = tuple(records)
    inferred_run_id = run_id or _single_value((trade.run_id for trade in trades), default="mixed_runs")
    strategy_id = _single_value((trade.strategy_id for trade in trades), default="mixed_strategies")
    symbol = _single_value((trade.symbol for trade in trades), default="multi_symbol")
    net_values = [trade.net_pnl_eur for trade in trades]
    mfe_values = [_path_float(trade, "max_favorable_excursion_bps") for trade in trades]
    mae_values = [_path_float(trade, "max_adverse_excursion_bps") for trade in trades]
    exit_capture_values = [_path_float(trade, "entry_to_exit_bps") for trade in trades]
    mfe_giveback_values = [_path_float(trade, "mfe_giveback_bps") for trade in trades]
    mfe_capture_ratios = [_path_float(trade, "mfe_capture_ratio") for trade in trades]
    positive_mfe_capture_ratios = [_path_float(trade, "positive_mfe_capture_ratio") for trade in trades]
    mfe_cost_ratios = [_path_float(trade, "mfe_to_cost_ratio") for trade in trades]
    return LossAttributionResult(
        run_id=inferred_run_id,
        strategy_id=strategy_id,
        symbol=symbol,
        trade_count=len(trades),
        gross_pnl_eur=sum(trade.gross_pnl_eur for trade in trades),
        net_pnl_eur=sum(trade.net_pnl_eur for trade in trades),
        fees_eur=sum(trade.fees_eur for trade in trades),
        slippage_eur=sum(trade.slippage_eur for trade in trades),
        spread_cost_eur=sum(trade.spread_cost_eur for trade in trades),
        cost_flipped_trade_count=sum(1 for trade in trades if trade.gross_pnl_eur > 0.0 >= trade.net_pnl_eur),
        mfe_above_cost_trade_count=sum(1 for trade in trades if _mfe_exceeds_cost(trade)),
        mfe_above_cost_lost_trade_count=sum(
            1 for trade in trades if _mfe_exceeds_cost(trade) and trade.net_pnl_eur <= 0.0
        ),
        average_mfe_bps=_average_optional(mfe_values),
        average_mae_bps=_average_optional(mae_values),
        average_exit_capture_bps=_average_optional(exit_capture_values),
        average_mfe_giveback_bps=_average_optional(mfe_giveback_values),
        average_mfe_capture_ratio=_average_optional(mfe_capture_ratios),
        average_positive_mfe_capture_ratio=_average_optional(positive_mfe_capture_ratios),
        average_mfe_to_cost_ratio=_average_optional(mfe_cost_ratios),
        losing_trade_count=sum(1 for trade in trades if trade.net_pnl_eur < 0.0),
        winning_trade_count=sum(1 for trade in trades if trade.net_pnl_eur > 0.0),
        largest_loss_eur=min(net_values) if net_values else None,
        largest_win_eur=max(net_values) if net_values else None,
        by_failure_mode=_build_buckets(trades, key_func=_failure_mode_key),
        by_entry_reason=_build_buckets(trades, key_func=lambda trade: trade.entry_reason or "unknown_entry"),
        by_exit_reason=_build_buckets(trades, key_func=lambda trade: trade.exit_reason or "unknown_exit"),
        by_symbol=_build_buckets(trades, key_func=lambda trade: trade.symbol),
    )


def analyze_trade_journal(path: str | Path, *, run_id: str | None = None) -> LossAttributionResult:
    return analyze_trade_losses(TradeJournal.from_json(path).records, run_id=run_id)


def write_loss_attribution_report(
    result: LossAttributionResult,
    output_dir: str | Path,
) -> LossAttributionResult:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / f"{result.run_id}_loss_attribution.json"
    md_path = output_path / f"{result.run_id}_loss_attribution.md"
    json_path.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(render_loss_attribution_report(result), encoding="utf-8")
    return replace(result, json_report_path=str(json_path), markdown_report_path=str(md_path))


def write_matrix_loss_attribution_report(
    matrix: MatrixRunResult,
    output_dir: str | Path,
    *,
    write_cell_reports: bool = True,
) -> MatrixLossAttributionReport:
    """Write attribution reports for all matrix cells that have trade journals."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    cell_output_dir = output_path / "cells"
    analyzed: list[MatrixCellLossAttribution] = []
    all_trades: list[TradeRecord] = []
    missing = 0

    for cell in matrix.results:
        journal_path = _journal_path_from_cell(cell.report_path)
        if not journal_path or not journal_path.exists():
            if cell.closed_trades > 0:
                missing += 1
            continue
        journal = TradeJournal.from_json(journal_path)
        all_trades.extend(journal.records)
        attribution = analyze_trade_losses(journal.records, run_id=cell.run_id)
        if write_cell_reports:
            attribution = write_loss_attribution_report(attribution, cell_output_dir)
        analyzed.append(
            MatrixCellLossAttribution(
                run_id=cell.run_id,
                strategy=cell.strategy,
                symbol=cell.symbol,
                decision=cell.decision,
                reason=cell.reason,
                journal_path=str(journal_path),
                attribution_report_path=attribution.markdown_report_path,
                trade_count=attribution.trade_count,
                gross_pnl_eur=attribution.gross_pnl_eur,
                net_pnl_eur=attribution.net_pnl_eur,
                total_cost_eur=attribution.total_cost_eur,
                cost_flipped_trade_count=attribution.cost_flipped_trade_count,
                mfe_above_cost_trade_count=attribution.mfe_above_cost_trade_count,
                mfe_above_cost_lost_trade_count=attribution.mfe_above_cost_lost_trade_count,
                average_mfe_bps=attribution.average_mfe_bps,
                average_mae_bps=attribution.average_mae_bps,
                average_exit_capture_bps=attribution.average_exit_capture_bps,
                average_mfe_giveback_bps=attribution.average_mfe_giveback_bps,
                average_mfe_capture_ratio=attribution.average_mfe_capture_ratio,
                average_positive_mfe_capture_ratio=attribution.average_positive_mfe_capture_ratio,
                average_mfe_to_cost_ratio=attribution.average_mfe_to_cost_ratio,
                worst_exit_reason=attribution.by_exit_reason[0].key if attribution.by_exit_reason else None,
                worst_entry_reason=attribution.by_entry_reason[0].key if attribution.by_entry_reason else None,
                primary_failure_mode=_primary_failure_mode(attribution.by_failure_mode),
            )
        )

    sorted_cells = tuple(sorted(analyzed, key=lambda item: (item.net_pnl_eur, -item.trade_count)))
    report = MatrixLossAttributionReport(
        matrix_run_id=matrix.run_id,
        mode=matrix.mode,
        analyzed_cell_count=len(sorted_cells),
        missing_journal_count=missing,
        total_trades=sum(cell.trade_count for cell in sorted_cells),
        aggregate_gross_pnl_eur=sum(cell.gross_pnl_eur for cell in sorted_cells),
        aggregate_net_pnl_eur=sum(cell.net_pnl_eur for cell in sorted_cells),
        aggregate_cost_eur=sum(cell.total_cost_eur for cell in sorted_cells),
        aggregate_cost_flipped_trade_count=sum(cell.cost_flipped_trade_count for cell in sorted_cells),
        aggregate_mfe_above_cost_trade_count=sum(cell.mfe_above_cost_trade_count for cell in sorted_cells),
        aggregate_mfe_above_cost_lost_trade_count=sum(
            cell.mfe_above_cost_lost_trade_count for cell in sorted_cells
        ),
        aggregate_average_mfe_bps=_weighted_cell_average(
            sorted_cells,
            value_func=lambda cell: cell.average_mfe_bps,
        ),
        aggregate_average_mae_bps=_weighted_cell_average(
            sorted_cells,
            value_func=lambda cell: cell.average_mae_bps,
        ),
        aggregate_average_exit_capture_bps=_weighted_cell_average(
            sorted_cells,
            value_func=lambda cell: cell.average_exit_capture_bps,
        ),
        aggregate_average_mfe_giveback_bps=_weighted_cell_average(
            sorted_cells,
            value_func=lambda cell: cell.average_mfe_giveback_bps,
        ),
        aggregate_average_mfe_capture_ratio=_weighted_cell_average(
            sorted_cells,
            value_func=lambda cell: cell.average_mfe_capture_ratio,
        ),
        aggregate_average_positive_mfe_capture_ratio=_weighted_cell_average(
            sorted_cells,
            value_func=lambda cell: cell.average_positive_mfe_capture_ratio,
        ),
        aggregate_average_mfe_to_cost_ratio=_weighted_cell_average(
            sorted_cells,
            value_func=lambda cell: cell.average_mfe_to_cost_ratio,
        ),
        by_failure_mode=_build_buckets(tuple(all_trades), key_func=_failure_mode_key),
        cells=sorted_cells,
    )
    json_path = output_path / f"{matrix.run_id}_matrix_loss_attribution.json"
    md_path = output_path / f"{matrix.run_id}_matrix_loss_attribution.md"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(render_matrix_loss_attribution_report(report), encoding="utf-8")
    return replace(report, json_report_path=str(json_path), markdown_report_path=str(md_path))


def render_loss_attribution_report(result: LossAttributionResult) -> str:
    lines = [
        f"# Loss Attribution - {result.run_id}",
        "",
        f"Strategy: `{result.strategy_id}`",
        f"Symbol: `{result.symbol}`",
        f"Trades: `{result.trade_count}`",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Gross PnL | {result.gross_pnl_eur:.6f} |",
        f"| Net PnL | {result.net_pnl_eur:.6f} |",
        f"| Fees | {result.fees_eur:.6f} |",
        f"| Slippage | {result.slippage_eur:.6f} |",
        f"| Spread Cost | {result.spread_cost_eur:.6f} |",
        f"| Total Cost | {result.total_cost_eur:.6f} |",
        f"| Cost Drag vs Gross Abs | {result.cost_drag_vs_gross_abs_pct:.4f}% |",
        f"| Cost-Flipped Trades | {result.cost_flipped_trade_count} |",
        f"| MFE Above Cost Trades | {result.mfe_above_cost_trade_count} |",
        f"| MFE Above Cost Lost Trades | {result.mfe_above_cost_lost_trade_count} |",
        f"| Average MFE | {_fmt_optional(result.average_mfe_bps)} bps |",
        f"| Average MAE | {_fmt_optional(result.average_mae_bps)} bps |",
        f"| Average Exit Capture | {_fmt_optional(result.average_exit_capture_bps)} bps |",
        f"| Average MFE Giveback | {_fmt_optional(result.average_mfe_giveback_bps)} bps |",
        f"| Average MFE Capture Ratio | {_fmt_optional(result.average_mfe_capture_ratio)} |",
        f"| Average Positive MFE Capture Ratio | {_fmt_optional(result.average_positive_mfe_capture_ratio)} |",
        f"| Average MFE/Cost Ratio | {_fmt_optional(result.average_mfe_to_cost_ratio)} |",
        f"| Winning Trades | {result.winning_trade_count} |",
        f"| Losing Trades | {result.losing_trade_count} |",
        "",
        "## By Failure Mode",
        "",
    ]
    lines.extend(_bucket_table(result.by_failure_mode))
    lines.extend(["", "## Research Recommendations", ""])
    lines.extend(_failure_mode_recommendations(result.by_failure_mode))
    lines.extend(
        [
            "",
            "## By Exit Reason",
            "",
        ]
    )
    lines.extend(_bucket_table(result.by_exit_reason))
    lines.extend(["", "## By Entry Reason", ""])
    lines.extend(_bucket_table(result.by_entry_reason))
    lines.extend(["", "## By Symbol", ""])
    lines.extend(_bucket_table(result.by_symbol))
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


def render_matrix_loss_attribution_report(report: MatrixLossAttributionReport) -> str:
    lines = [
        f"# Matrix Loss Attribution - {report.matrix_run_id}",
        "",
        f"Mode: `{report.mode}`",
        f"Analyzed cells: `{report.analyzed_cell_count}`",
        f"Missing journals: `{report.missing_journal_count}`",
        "",
        "## Aggregate",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Trades | {report.total_trades} |",
        f"| Gross PnL | {report.aggregate_gross_pnl_eur:.6f} |",
        f"| Net PnL | {report.aggregate_net_pnl_eur:.6f} |",
        f"| Total Cost | {report.aggregate_cost_eur:.6f} |",
        f"| Cost-Flipped Trades | {report.aggregate_cost_flipped_trade_count} |",
        f"| MFE Above Cost Trades | {report.aggregate_mfe_above_cost_trade_count} |",
        f"| MFE Above Cost Lost Trades | {report.aggregate_mfe_above_cost_lost_trade_count} |",
        f"| Average MFE | {_fmt_optional(report.aggregate_average_mfe_bps)} bps |",
        f"| Average MAE | {_fmt_optional(report.aggregate_average_mae_bps)} bps |",
        f"| Average Exit Capture | {_fmt_optional(report.aggregate_average_exit_capture_bps)} bps |",
        f"| Average MFE Giveback | {_fmt_optional(report.aggregate_average_mfe_giveback_bps)} bps |",
        f"| Average MFE Capture Ratio | {_fmt_optional(report.aggregate_average_mfe_capture_ratio)} |",
        f"| Average Positive MFE Capture Ratio | {_fmt_optional(report.aggregate_average_positive_mfe_capture_ratio)} |",
        f"| Average MFE/Cost Ratio | {_fmt_optional(report.aggregate_average_mfe_to_cost_ratio)} |",
        "",
        "## By Failure Mode",
        "",
    ]
    lines.extend(_bucket_table(report.by_failure_mode))
    lines.extend(["", "## Research Recommendations", ""])
    lines.extend(_failure_mode_recommendations(report.by_failure_mode))
    lines.extend(
        [
            "",
            "## Worst Cells",
            "",
            "| Symbol | Strategy | Decision | Reason | Trades | Gross PnL | Net PnL | Cost | Cost-Flipped | MFE>Cost | MFE>Cost Lost | Avg MFE | Avg MAE | Avg Exit | Avg Giveback | Avg Capture | Avg MFE/Cost | Failure Mode | Worst Exit | Worst Entry |",
            "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |",
        ]
    )
    for cell in report.cells:
        lines.append(
            f"| {cell.symbol} | {cell.strategy} | {cell.decision or ''} | {cell.reason or ''} | "
            f"{cell.trade_count} | {cell.gross_pnl_eur:.6f} | {cell.net_pnl_eur:.6f} | "
            f"{cell.total_cost_eur:.6f} | {cell.cost_flipped_trade_count} | "
            f"{cell.mfe_above_cost_trade_count} | {cell.mfe_above_cost_lost_trade_count} | "
            f"{_fmt_optional(cell.average_mfe_bps)} | {_fmt_optional(cell.average_mae_bps)} | "
            f"{_fmt_optional(cell.average_exit_capture_bps)} | "
            f"{_fmt_optional(cell.average_mfe_giveback_bps)} | "
            f"{_fmt_optional(cell.average_mfe_capture_ratio)} | "
            f"{_fmt_optional(cell.average_mfe_to_cost_ratio)} | "
            f"{cell.primary_failure_mode or ''} | {cell.worst_exit_reason or ''} | {cell.worst_entry_reason or ''} |"
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


def _build_buckets(trades: tuple[TradeRecord, ...], *, key_func) -> tuple[AttributionBucket, ...]:
    grouped: dict[str, list[TradeRecord]] = {}
    for trade in trades:
        grouped.setdefault(str(key_func(trade)), []).append(trade)
    buckets = [_bucket_from_trades(key, tuple(items)) for key, items in grouped.items()]
    return tuple(sorted(buckets, key=lambda item: (item.net_pnl_eur, -item.trade_count)))


def _bucket_from_trades(key: str, trades: tuple[TradeRecord, ...]) -> AttributionBucket:
    duration = sum(trade.duration_seconds for trade in trades)
    return AttributionBucket(
        key=key,
        trade_count=len(trades),
        win_count=sum(1 for trade in trades if trade.net_pnl_eur > 0.0),
        gross_pnl_eur=sum(trade.gross_pnl_eur for trade in trades),
        net_pnl_eur=sum(trade.net_pnl_eur for trade in trades),
        fees_eur=sum(trade.fees_eur for trade in trades),
        slippage_eur=sum(trade.slippage_eur for trade in trades),
        spread_cost_eur=sum(trade.spread_cost_eur for trade in trades),
        average_duration_seconds=duration / len(trades) if trades else 0.0,
    )


def _bucket_table(buckets: tuple[AttributionBucket, ...]) -> list[str]:
    lines = [
        "| Key | Trades | Win Rate | Gross PnL | Net PnL | Fees | Slippage | Spread | Avg Duration |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    if not buckets:
        lines.append("| none | 0 | 0.0000% | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 |")
        return lines
    for bucket in buckets:
        lines.append(
            f"| {bucket.key} | {bucket.trade_count} | {bucket.win_rate_pct:.4f}% | "
            f"{bucket.gross_pnl_eur:.6f} | {bucket.net_pnl_eur:.6f} | {bucket.fees_eur:.6f} | "
            f"{bucket.slippage_eur:.6f} | {bucket.spread_cost_eur:.6f} | "
            f"{bucket.average_duration_seconds:.6f} |"
        )
    return lines


def _primary_failure_mode(buckets: tuple[AttributionBucket, ...]) -> str | None:
    for bucket in buckets:
        if bucket.key != "profitable":
            return bucket.key
    return buckets[0].key if buckets else None


def _failure_mode_key(trade: TradeRecord) -> str:
    if trade.net_pnl_eur > 0.0:
        return "profitable"
    if trade.gross_pnl_eur > 0.0 >= trade.net_pnl_eur:
        return "cost_flipped_positive_gross"
    if _mfe_exceeds_cost(trade):
        return "mfe_giveback_loss"
    mfe_to_cost = _path_float(trade, "mfe_to_cost_ratio")
    if mfe_to_cost is not None and mfe_to_cost < 1.0:
        return "weak_mfe_below_cost"
    if "stop" in (trade.exit_reason or "").lower() and trade.gross_pnl_eur <= 0.0:
        return "stop_loss_adverse_move"
    if trade.gross_pnl_eur <= 0.0:
        return "adverse_price_move"
    return "loss_unclassified"


def _failure_mode_recommendations(buckets: tuple[AttributionBucket, ...]) -> list[str]:
    dominant = _primary_failure_mode(buckets)
    if dominant is None:
        return ["- No failure mode available yet. Collect more closed trades before changing parameters."]
    recommendations = {
        "weak_mfe_below_cost": (
            "Do not lower global thresholds first. Prioritize entry-quality filters: test wider grid spacing, "
            "stronger support confirmation, and regime/volatility filters so expected MFE clears costs."
        ),
        "cost_flipped_positive_gross": (
            "The setup can move in the right direction but not far enough net of costs. Test higher net "
            "take-profit buffers, lower trade frequency, or maker/limit assumptions before increasing size."
        ),
        "mfe_giveback_loss": (
            "The setup reaches tradable MFE but gives it back before exit. Test exit-capture rules such as "
            "MFE trailing or earlier take-profit, strictly in research/paper."
        ),
        "stop_loss_adverse_move": (
            "Stop-loss losses dominate. Test trend/regime filters that block grid entries during directional "
            "adverse moves."
        ),
        "adverse_price_move": (
            "The entry is directionally wrong in this sample. Improve signal quality before tuning execution "
            "or sizing."
        ),
        "loss_unclassified": (
            "The loss source is not fully explained by recorded path metrics. Improve decision/ledger "
            "traceability before tuning."
        ),
        "profitable": (
            "No dominant losing mode in this sample. Keep collecting evidence and compare against baselines "
            "before promotion."
        ),
    }
    text = recommendations.get(dominant, "Investigate this failure mode before changing runtime trading behavior.")
    return [
        f"- Dominant failure mode: `{dominant}`.",
        f"- {text}",
        "- This is research-only guidance. It does not authorize paper/live promotion or risk increases.",
    ]


def _single_value(values: Iterable[str], *, default: str) -> str:
    unique = {str(value) for value in values if str(value)}
    if len(unique) == 1:
        return next(iter(unique))
    return default


def _journal_path_from_cell(report_path: str | None) -> Path | None:
    if not report_path:
        return None
    path = Path(report_path)
    if path.suffix != ".md":
        return None
    return path.with_name(f"{path.stem}_journal.json")


def _path_float(trade: TradeRecord, key: str) -> float | None:
    path = trade.metadata.get("path") if isinstance(trade.metadata, dict) else None
    if not isinstance(path, dict):
        return None
    value = path.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _mfe_exceeds_cost(trade: TradeRecord) -> bool:
    mfe = _path_float(trade, "max_favorable_excursion_bps")
    cost = _path_float(trade, "total_cost_bps")
    return mfe is not None and cost is not None and mfe >= cost > 0.0


def _average_optional(values: Iterable[float | None]) -> float | None:
    cleaned = [value for value in values if value is not None]
    if not cleaned:
        return None
    return sum(cleaned) / len(cleaned)


def _weighted_cell_average(
    cells: Iterable[MatrixCellLossAttribution],
    *,
    value_func,
) -> float | None:
    weighted_total = 0.0
    weight = 0
    for cell in cells:
        value = value_func(cell)
        if value is None or cell.trade_count <= 0:
            continue
        weighted_total += float(value) * cell.trade_count
        weight += cell.trade_count
    if weight <= 0:
        return None
    return weighted_total / weight


def _fmt_optional(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.6f}"
