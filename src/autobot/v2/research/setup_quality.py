"""Setup-quality diagnostics for AUTOBOT research trade journals.

This module explains whether entries had enough setup quality before worrying
about exit tuning. It is research-only and does not authorize paper/live
execution.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Iterable

from .trade_journal import TradeJournal, TradeRecord


@dataclass(frozen=True)
class SetupQualityBucket:
    key: str
    trade_count: int
    win_count: int
    gross_pnl_eur: float
    net_pnl_eur: float
    average_mfe_bps: float | None
    average_mae_bps: float | None
    average_exit_capture_bps: float | None
    average_mfe_to_cost_ratio: float | None
    cost_dominated_trade_count: int
    mfe_above_cost_lost_trade_count: int

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

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["win_rate_pct"] = self.win_rate_pct
        payload["average_net_pnl_eur"] = self.average_net_pnl_eur
        return payload


@dataclass(frozen=True)
class SetupQualityReport:
    run_id: str
    strategy_id: str
    symbol: str
    trade_count: int
    gross_pnl_eur: float
    net_pnl_eur: float
    cost_dominated_trade_count: int
    mfe_above_cost_lost_trade_count: int
    by_regime: tuple[SetupQualityBucket, ...]
    by_breakout_strength: tuple[SetupQualityBucket, ...]
    by_momentum_strength: tuple[SetupQualityBucket, ...]
    by_atr_regime: tuple[SetupQualityBucket, ...]
    json_report_path: str | None = None
    markdown_report_path: str | None = None

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "trade_count": self.trade_count,
            "gross_pnl_eur": self.gross_pnl_eur,
            "net_pnl_eur": self.net_pnl_eur,
            "cost_dominated_trade_count": self.cost_dominated_trade_count,
            "mfe_above_cost_lost_trade_count": self.mfe_above_cost_lost_trade_count,
            "by_regime": [bucket.to_dict() for bucket in self.by_regime],
            "by_breakout_strength": [bucket.to_dict() for bucket in self.by_breakout_strength],
            "by_momentum_strength": [bucket.to_dict() for bucket in self.by_momentum_strength],
            "by_atr_regime": [bucket.to_dict() for bucket in self.by_atr_regime],
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
        }


def analyze_setup_quality(records: Iterable[TradeRecord], *, run_id: str | None = None) -> SetupQualityReport:
    trades = tuple(records)
    return SetupQualityReport(
        run_id=run_id or _single_value((trade.run_id for trade in trades), default="mixed_runs"),
        strategy_id=_single_value((trade.strategy_id for trade in trades), default="mixed_strategies"),
        symbol=_single_value((trade.symbol for trade in trades), default="multi_symbol"),
        trade_count=len(trades),
        gross_pnl_eur=sum(trade.gross_pnl_eur for trade in trades),
        net_pnl_eur=sum(trade.net_pnl_eur for trade in trades),
        cost_dominated_trade_count=sum(1 for trade in trades if _is_cost_dominated(trade)),
        mfe_above_cost_lost_trade_count=sum(1 for trade in trades if _mfe_exceeds_cost(trade) and trade.net_pnl_eur <= 0.0),
        by_regime=_build_buckets(trades, key_func=_regime_key),
        by_breakout_strength=_build_buckets(
            trades,
            key_func=lambda trade: _strength_bucket(_entry_float(trade, "breakout_bps"), low=40.0, high=80.0),
        ),
        by_momentum_strength=_build_buckets(
            trades,
            key_func=lambda trade: _strength_bucket(_entry_float(trade, "momentum_bps"), low=40.0, high=100.0),
        ),
        by_atr_regime=_build_buckets(
            trades,
            key_func=lambda trade: _strength_bucket(_entry_float(trade, "atr_bps"), low=15.0, high=50.0),
        ),
    )


def analyze_setup_quality_journal(path: str | Path, *, run_id: str | None = None) -> SetupQualityReport:
    return analyze_setup_quality(TradeJournal.from_json(path).records, run_id=run_id)


def write_setup_quality_report(result: SetupQualityReport, output_dir: str | Path) -> SetupQualityReport:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / f"{result.run_id}_setup_quality.json"
    md_path = output_path / f"{result.run_id}_setup_quality.md"
    json_path.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(render_setup_quality_report(result), encoding="utf-8")
    return replace(result, json_report_path=str(json_path), markdown_report_path=str(md_path))


def render_setup_quality_report(result: SetupQualityReport) -> str:
    lines = [
        f"# Setup Quality - {result.run_id}",
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
        f"| Cost-Dominated Trades | {result.cost_dominated_trade_count} |",
        f"| MFE Above Cost Lost Trades | {result.mfe_above_cost_lost_trade_count} |",
        "",
        "## By Regime",
        "",
    ]
    lines.extend(_bucket_table(result.by_regime))
    lines.extend(["", "## By Breakout Strength", ""])
    lines.extend(_bucket_table(result.by_breakout_strength))
    lines.extend(["", "## By Momentum Strength", ""])
    lines.extend(_bucket_table(result.by_momentum_strength))
    lines.extend(["", "## By ATR Regime", ""])
    lines.extend(_bucket_table(result.by_atr_regime))
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


def _build_buckets(trades: tuple[TradeRecord, ...], *, key_func) -> tuple[SetupQualityBucket, ...]:
    grouped: dict[str, list[TradeRecord]] = {}
    for trade in trades:
        grouped.setdefault(str(key_func(trade)), []).append(trade)
    buckets = [_bucket_from_trades(key, tuple(items)) for key, items in grouped.items()]
    return tuple(sorted(buckets, key=lambda item: (item.net_pnl_eur, -item.trade_count, item.key)))


def _bucket_from_trades(key: str, trades: tuple[TradeRecord, ...]) -> SetupQualityBucket:
    return SetupQualityBucket(
        key=key,
        trade_count=len(trades),
        win_count=sum(1 for trade in trades if trade.net_pnl_eur > 0.0),
        gross_pnl_eur=sum(trade.gross_pnl_eur for trade in trades),
        net_pnl_eur=sum(trade.net_pnl_eur for trade in trades),
        average_mfe_bps=_average_optional(_path_float(trade, "max_favorable_excursion_bps") for trade in trades),
        average_mae_bps=_average_optional(_path_float(trade, "max_adverse_excursion_bps") for trade in trades),
        average_exit_capture_bps=_average_optional(_path_float(trade, "entry_to_exit_bps") for trade in trades),
        average_mfe_to_cost_ratio=_average_optional(_path_float(trade, "mfe_to_cost_ratio") for trade in trades),
        cost_dominated_trade_count=sum(1 for trade in trades if _is_cost_dominated(trade)),
        mfe_above_cost_lost_trade_count=sum(1 for trade in trades if _mfe_exceeds_cost(trade) and trade.net_pnl_eur <= 0.0),
    )


def _bucket_table(buckets: tuple[SetupQualityBucket, ...]) -> list[str]:
    lines = [
        "| Key | Trades | Win Rate | Gross PnL | Net PnL | Avg Net | Avg MFE | Avg MAE | Avg Exit | Avg MFE/Cost | Cost-Dominated | MFE>Cost Lost |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    if not buckets:
        lines.append("| none | 0 | 0.0000% | 0.000000 | 0.000000 | 0.000000 | N/A | N/A | N/A | N/A | 0 | 0 |")
        return lines
    for bucket in buckets:
        lines.append(
            f"| {bucket.key} | {bucket.trade_count} | {bucket.win_rate_pct:.4f}% | "
            f"{bucket.gross_pnl_eur:.6f} | {bucket.net_pnl_eur:.6f} | "
            f"{bucket.average_net_pnl_eur:.6f} | {_fmt_optional(bucket.average_mfe_bps)} | "
            f"{_fmt_optional(bucket.average_mae_bps)} | {_fmt_optional(bucket.average_exit_capture_bps)} | "
            f"{_fmt_optional(bucket.average_mfe_to_cost_ratio)} | "
            f"{bucket.cost_dominated_trade_count} | {bucket.mfe_above_cost_lost_trade_count} |"
        )
    return lines


def _regime_key(trade: TradeRecord) -> str:
    entry = _entry_metadata(trade)
    return str(entry.get("regime") or trade.regime or "unknown")


def _strength_bucket(value: float | None, *, low: float, high: float) -> str:
    if value is None:
        return "unknown"
    if value < low:
        return f"weak_lt_{low:g}"
    if value < high:
        return f"medium_{low:g}_{high:g}"
    return f"strong_gte_{high:g}"


def _entry_metadata(trade: TradeRecord) -> dict:
    metadata = trade.metadata if isinstance(trade.metadata, dict) else {}
    entry = metadata.get("entry")
    return entry if isinstance(entry, dict) else {}


def _entry_float(trade: TradeRecord, key: str) -> float | None:
    value = _entry_metadata(trade).get(key)
    return _safe_float(value)


def _path_float(trade: TradeRecord, key: str) -> float | None:
    metadata = trade.metadata if isinstance(trade.metadata, dict) else {}
    path = metadata.get("path")
    if not isinstance(path, dict):
        return None
    return _safe_float(path.get(key))


def _safe_float(value) -> float | None:
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
