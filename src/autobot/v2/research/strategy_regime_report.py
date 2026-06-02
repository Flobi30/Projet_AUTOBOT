"""Strategy-by-regime diagnostics for AUTOBOT research validation.

This module summarizes replay journals by strategy family and market regime. It
is research-only and never authorizes official paper or live execution.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Iterable

from .trade_journal import TradeJournal, TradeRecord


@dataclass(frozen=True)
class StrategyRegimeBucket:
    strategy_id: str
    regime: str
    trade_count: int
    win_count: int
    gross_pnl_eur: float
    net_pnl_eur: float
    fees_eur: float
    slippage_eur: float
    spread_cost_eur: float
    cost_dominated_trade_count: int
    mfe_above_cost_lost_trade_count: int
    average_mfe_bps: float | None
    average_exit_capture_bps: float | None
    average_mfe_to_cost_ratio: float | None
    symbols: tuple[str, ...]

    @property
    def win_rate_pct(self) -> float:
        if self.trade_count <= 0:
            return 0.0
        return (self.win_count / self.trade_count) * 100.0

    @property
    def average_net_pnl_eur(self) -> float:
        if self.trade_count <= 0:
            return 0.0
        return self.net_pnl_eur / self.trade_count

    @property
    def total_cost_eur(self) -> float:
        return self.fees_eur + self.slippage_eur + self.spread_cost_eur

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["win_rate_pct"] = self.win_rate_pct
        payload["average_net_pnl_eur"] = self.average_net_pnl_eur
        payload["total_cost_eur"] = self.total_cost_eur
        return payload


@dataclass(frozen=True)
class StrategyRegimeReport:
    run_id: str
    trade_count: int
    gross_pnl_eur: float
    net_pnl_eur: float
    buckets: tuple[StrategyRegimeBucket, ...]
    json_report_path: str | None = None
    markdown_report_path: str | None = None

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "trade_count": self.trade_count,
            "gross_pnl_eur": self.gross_pnl_eur,
            "net_pnl_eur": self.net_pnl_eur,
            "buckets": [bucket.to_dict() for bucket in self.buckets],
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
        }


def analyze_strategy_regimes(
    records: Iterable[TradeRecord],
    *,
    run_id: str | None = None,
) -> StrategyRegimeReport:
    trades = tuple(records)
    grouped: dict[tuple[str, str], list[TradeRecord]] = {}
    for trade in trades:
        grouped.setdefault((_strategy_id(trade), _regime(trade)), []).append(trade)
    buckets = tuple(
        sorted(
            (_bucket(strategy_id, regime, tuple(items)) for (strategy_id, regime), items in grouped.items()),
            key=lambda item: (item.strategy_id, item.net_pnl_eur, -item.trade_count, item.regime),
        )
    )
    return StrategyRegimeReport(
        run_id=run_id or _single_value((trade.run_id for trade in trades), default="mixed_runs"),
        trade_count=len(trades),
        gross_pnl_eur=sum(trade.gross_pnl_eur for trade in trades),
        net_pnl_eur=sum(trade.net_pnl_eur for trade in trades),
        buckets=buckets,
    )


def analyze_strategy_regime_journals(
    paths: Iterable[str | Path],
    *,
    run_id: str | None = None,
) -> StrategyRegimeReport:
    records: list[TradeRecord] = []
    for path in paths:
        records.extend(TradeJournal.from_json(path).records)
    return analyze_strategy_regimes(records, run_id=run_id)


def write_matrix_strategy_regime_report(matrix_result, output_dir: str | Path) -> StrategyRegimeReport:
    journal_paths = [
        path
        for path in (_journal_path_from_cell(getattr(cell, "report_path", None)) for cell in matrix_result.results)
        if path is not None and path.exists()
    ]
    return write_strategy_regime_report(
        analyze_strategy_regime_journals(
            journal_paths,
            run_id=f"{matrix_result.run_id}_strategy_regime",
        ),
        output_dir,
    )


def write_strategy_regime_report(result: StrategyRegimeReport, output_dir: str | Path) -> StrategyRegimeReport:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / f"{result.run_id}.json"
    md_path = output_path / f"{result.run_id}.md"
    json_path.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(render_strategy_regime_report(result), encoding="utf-8")
    return replace(result, json_report_path=str(json_path), markdown_report_path=str(md_path))


def render_strategy_regime_report(result: StrategyRegimeReport) -> str:
    lines = [
        f"# Strategy Regime Report - {result.run_id}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Trades | {result.trade_count} |",
        f"| Gross PnL EUR | {result.gross_pnl_eur:.6f} |",
        f"| Net PnL EUR | {result.net_pnl_eur:.6f} |",
        "",
        "## Strategy x Regime",
        "",
        "| Strategy | Regime | Trades | Win Rate | Gross PnL | Net PnL | Avg Net | Cost | Avg MFE | Avg Exit | MFE/Cost | Cost-Dominated | MFE>Cost Lost | Symbols |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    if not result.buckets:
        lines.append("| none | none | 0 | 0.0000% | 0.000000 | 0.000000 | 0.000000 | 0.000000 | N/A | N/A | N/A | 0 | 0 | none |")
    for bucket in result.buckets:
        lines.append(
            f"| {bucket.strategy_id} | {bucket.regime} | {bucket.trade_count} | "
            f"{bucket.win_rate_pct:.4f}% | {bucket.gross_pnl_eur:.6f} | {bucket.net_pnl_eur:.6f} | "
            f"{bucket.average_net_pnl_eur:.6f} | {bucket.total_cost_eur:.6f} | "
            f"{_fmt_optional(bucket.average_mfe_bps)} | {_fmt_optional(bucket.average_exit_capture_bps)} | "
            f"{_fmt_optional(bucket.average_mfe_to_cost_ratio)} | {bucket.cost_dominated_trade_count} | "
            f"{bucket.mfe_above_cost_lost_trade_count} | {', '.join(bucket.symbols) or 'none'} |"
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


def _bucket(strategy_id: str, regime: str, trades: tuple[TradeRecord, ...]) -> StrategyRegimeBucket:
    return StrategyRegimeBucket(
        strategy_id=strategy_id,
        regime=regime,
        trade_count=len(trades),
        win_count=sum(1 for trade in trades if trade.net_pnl_eur > 0.0),
        gross_pnl_eur=sum(trade.gross_pnl_eur for trade in trades),
        net_pnl_eur=sum(trade.net_pnl_eur for trade in trades),
        fees_eur=sum(trade.fees_eur for trade in trades),
        slippage_eur=sum(trade.slippage_eur for trade in trades),
        spread_cost_eur=sum(trade.spread_cost_eur for trade in trades),
        cost_dominated_trade_count=sum(1 for trade in trades if _is_cost_dominated(trade)),
        mfe_above_cost_lost_trade_count=sum(
            1 for trade in trades if _mfe_exceeds_cost(trade) and trade.net_pnl_eur <= 0.0
        ),
        average_mfe_bps=_average_optional(_path_float(trade, "max_favorable_excursion_bps") for trade in trades),
        average_exit_capture_bps=_average_optional(_path_float(trade, "entry_to_exit_bps") for trade in trades),
        average_mfe_to_cost_ratio=_average_optional(_path_float(trade, "mfe_to_cost_ratio") for trade in trades),
        symbols=tuple(sorted({trade.symbol for trade in trades})),
    )


def _strategy_id(trade: TradeRecord) -> str:
    metadata = trade.metadata if isinstance(trade.metadata, dict) else {}
    entry = metadata.get("entry")
    if isinstance(entry, dict):
        value = entry.get("strategy_id")
        if value:
            return str(value)
    return str(trade.strategy_id or "unknown_strategy")


def _regime(trade: TradeRecord) -> str:
    metadata = trade.metadata if isinstance(trade.metadata, dict) else {}
    entry = metadata.get("entry")
    if isinstance(entry, dict):
        value = entry.get("regime")
        if value:
            return str(value)
    return str(trade.regime or "unknown")


def _journal_path_from_cell(report_path: str | None) -> Path | None:
    if not report_path:
        return None
    path = Path(report_path)
    if path.suffix != ".md":
        return None
    return path.with_name(f"{path.stem}_journal.json")


def _path_float(trade: TradeRecord, key: str) -> float | None:
    metadata = trade.metadata if isinstance(trade.metadata, dict) else {}
    path = metadata.get("path")
    if not isinstance(path, dict):
        return None
    value = path.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_cost_dominated(trade: TradeRecord) -> bool:
    ratio = _path_float(trade, "mfe_to_cost_ratio")
    return ratio is not None and ratio < 1.0


def _mfe_exceeds_cost(trade: TradeRecord) -> bool:
    mfe = _path_float(trade, "max_favorable_excursion_bps")
    cost = _path_float(trade, "total_cost_bps")
    return mfe is not None and cost is not None and mfe >= cost > 0.0


def _average_optional(values: Iterable[float | None]) -> float | None:
    cleaned = [value for value in values if value is not None]
    if not cleaned:
        return None
    return sum(cleaned) / len(cleaned)


def _single_value(values: Iterable[str], *, default: str) -> str:
    unique = {str(value) for value in values if str(value)}
    if len(unique) == 1:
        return next(iter(unique))
    return default


def _fmt_optional(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.6f}"

