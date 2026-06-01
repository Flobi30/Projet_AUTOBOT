"""Loss attribution helpers for AUTOBOT research trade journals."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Iterable

from .trade_journal import TradeJournal, TradeRecord


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
    losing_trade_count: int
    winning_trade_count: int
    largest_loss_eur: float | None
    largest_win_eur: float | None
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
            "losing_trade_count": self.losing_trade_count,
            "winning_trade_count": self.winning_trade_count,
            "largest_loss_eur": self.largest_loss_eur,
            "largest_win_eur": self.largest_win_eur,
            "by_entry_reason": [bucket.to_dict() for bucket in self.by_entry_reason],
            "by_exit_reason": [bucket.to_dict() for bucket in self.by_exit_reason],
            "by_symbol": [bucket.to_dict() for bucket in self.by_symbol],
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
        }


def analyze_trade_losses(records: Iterable[TradeRecord], *, run_id: str | None = None) -> LossAttributionResult:
    trades = tuple(records)
    inferred_run_id = run_id or _single_value((trade.run_id for trade in trades), default="mixed_runs")
    strategy_id = _single_value((trade.strategy_id for trade in trades), default="mixed_strategies")
    symbol = _single_value((trade.symbol for trade in trades), default="multi_symbol")
    net_values = [trade.net_pnl_eur for trade in trades]
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
        losing_trade_count=sum(1 for trade in trades if trade.net_pnl_eur < 0.0),
        winning_trade_count=sum(1 for trade in trades if trade.net_pnl_eur > 0.0),
        largest_loss_eur=min(net_values) if net_values else None,
        largest_win_eur=max(net_values) if net_values else None,
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
        f"| Winning Trades | {result.winning_trade_count} |",
        f"| Losing Trades | {result.losing_trade_count} |",
        "",
        "## By Exit Reason",
        "",
    ]
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


def _single_value(values: Iterable[str], *, default: str) -> str:
    unique = {str(value) for value in values if str(value)}
    if len(unique) == 1:
        return next(iter(unique))
    return default
