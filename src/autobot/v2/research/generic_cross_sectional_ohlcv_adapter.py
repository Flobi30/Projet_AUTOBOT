"""Generic cross-sectional OHLCV research adapter.

This adapter is deliberately research-only. It runs bounded long-only smoke
tests on multi-symbol OHLCV data and never imports or calls runtime order
paths. Signals use only data available before entry; future bars are used only
to evaluate the already-created hypothetical trade.
"""

from __future__ import annotations

import csv
import itertools
import math
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .alpha_hypothesis_lab import RESEARCH_ONLY_CAPITAL_FLAGS
from .execution_cost_model import ExecutionCostConfig, execution_cost_config_for_profile
from .market_data_repository import MarketBar


ADAPTER_ID = "generic_cross_sectional_ohlcv_adapter"
SUPPORTED_MODES = {"leader_laggard_momentum", "relative_strength_rotation"}


@dataclass(frozen=True)
class GenericCrossSectionalConfig:
    run_id: str
    mode: str
    data_paths: tuple[Path, ...]
    template: Mapping[str, Any]
    symbols: tuple[str, ...]
    cost_profile: str = "research_stress"
    max_variants: int = 3
    max_symbols: int = 6
    max_runtime_seconds: float = 120.0
    max_data_rows: int = 250_000
    order_notional_eur: float = 100.0
    timeframe_preference: tuple[str, ...] = ("1h", "15m", "5m")

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id is required")
        if self.mode not in SUPPORTED_MODES:
            raise ValueError(f"unsupported generic cross-sectional mode: {self.mode}")
        if not self.data_paths:
            raise ValueError("data_paths is required")
        if self.max_variants <= 0 or self.max_variants > 5:
            raise ValueError("max_variants must be between 1 and 5")
        if self.max_symbols <= 1 or self.max_symbols > 14:
            raise ValueError("max_symbols must be between 2 and 14")
        if self.max_runtime_seconds <= 0.0:
            raise ValueError("max_runtime_seconds must be positive")
        if self.order_notional_eur <= 0.0:
            raise ValueError("order_notional_eur must be positive")
        execution_cost_config_for_profile(self.cost_profile).validate()


@dataclass(frozen=True)
class CrossSectionalAvailability:
    adapter_id: str
    mode: str
    status: str
    available: bool
    symbols: tuple[str, ...]
    timeframes: tuple[str, ...]
    start_at: str | None
    end_at: str | None
    row_count: int
    duplicate_count: int
    selected_timeframe: str | None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CrossSectionalTrade:
    symbol: str
    opened_at: datetime
    closed_at: datetime
    signal_at: datetime
    mode: str
    variant_label: str
    timeframe: str
    gross_bps: float
    cost_bps: float
    net_bps: float
    gross_pnl_eur: float
    net_pnl_eur: float
    expected_move_bps: float
    estimated_total_cost_bps: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["opened_at"] = self.opened_at.isoformat()
        payload["closed_at"] = self.closed_at.isoformat()
        payload["signal_at"] = self.signal_at.isoformat()
        return payload


@dataclass(frozen=True)
class CrossSectionalMetrics:
    trade_count: int
    profit_factor_net: float | None
    net_pnl_eur: float
    expectancy_net: float | None
    max_drawdown_eur: float
    winrate_pct: float | None
    total_cost_bps: float
    no_trade_baseline_eur: float
    by_symbol: dict[str, dict[str, Any]]
    by_period: dict[str, dict[str, Any]]
    concentration: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CrossSectionalSmokeResult:
    adapter_id: str
    mode: str
    template_id: str
    variant_count: int
    primary_variant: str | None
    decision: str
    reasons: tuple[str, ...]
    metrics: CrossSectionalMetrics
    variants: tuple[dict[str, Any], ...]
    availability: CrossSectionalAvailability
    elapsed_seconds: float
    safety: dict[str, bool] = field(default_factory=lambda: dict(RESEARCH_ONLY_CAPITAL_FLAGS))
    paper_capital_allowed: bool = False
    live_allowed: bool = False
    promotable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "mode": self.mode,
            "template_id": self.template_id,
            "variant_count": self.variant_count,
            "primary_variant": self.primary_variant,
            "decision": self.decision,
            "reasons": list(self.reasons),
            "metrics": self.metrics.to_dict(),
            "variants": [dict(item) for item in self.variants],
            "availability": self.availability.to_dict(),
            "elapsed_seconds": self.elapsed_seconds,
            "safety": dict(self.safety),
            "paper_capital_allowed": self.paper_capital_allowed,
            "live_allowed": self.live_allowed,
            "promotable": self.promotable,
        }


def run_generic_cross_sectional_ohlcv_smoke(config: GenericCrossSectionalConfig) -> CrossSectionalSmokeResult:
    started = time.perf_counter()
    bars, duplicate_count = load_cross_sectional_bars(config.data_paths, max_rows=config.max_data_rows)
    selected_symbols = tuple(symbol.upper() for symbol in config.symbols[: config.max_symbols])
    groups = _group_bars(bars, selected_symbols)
    availability = build_cross_sectional_availability(config, groups, duplicate_count)
    if not availability.available:
        metrics = _metrics(())
        return CrossSectionalSmokeResult(
            adapter_id=ADAPTER_ID,
            mode=config.mode,
            template_id=str(config.template.get("template_id") or config.mode),
            variant_count=0,
            primary_variant=None,
            decision=availability.status if availability.status in {"DATA_MISSING", "ADAPTER_ERROR"} else "DATA_MISSING",
            reasons=tuple(reason for reason in (availability.reason,) if reason),
            metrics=metrics,
            variants=(),
            availability=availability,
            elapsed_seconds=round(time.perf_counter() - started, 6),
        )

    cost_config = execution_cost_config_for_profile(config.cost_profile)
    variants = tuple(_bounded_variants(config))
    selected_timeframe = availability.selected_timeframe or "1h"
    variant_rows: list[dict[str, Any]] = []
    all_primary_trades: list[CrossSectionalTrade] = []
    for index, variant in enumerate(variants):
        if time.perf_counter() - started > config.max_runtime_seconds:
            break
        trades = (
            _leader_laggard_trades(config, groups, selected_timeframe, cost_config, variant)
            if config.mode == "leader_laggard_momentum"
            else _relative_strength_rotation_trades(config, groups, selected_timeframe, cost_config, variant)
        )
        metrics = _metrics(trades)
        variant_rows.append(
            {
                "variant_index": index,
                "variant": dict(variant),
                "selection_policy": "bounded_template_order_not_best_pnl",
                "metrics": metrics.to_dict(),
                "status": "research_only",
                **RESEARCH_ONLY_CAPITAL_FLAGS,
            }
        )
        if index == 0:
            all_primary_trades = trades
    primary_metrics = _metrics(all_primary_trades)
    decision, reasons = _decision(primary_metrics, variant_rows)
    return CrossSectionalSmokeResult(
        adapter_id=ADAPTER_ID,
        mode=config.mode,
        template_id=str(config.template.get("template_id") or config.mode),
        variant_count=len(variant_rows),
        primary_variant=_variant_label(variants[0]) if variants else None,
        decision=decision,
        reasons=tuple(reasons),
        metrics=primary_metrics,
        variants=tuple(variant_rows),
        availability=availability,
        elapsed_seconds=round(time.perf_counter() - started, 6),
    )


def load_cross_sectional_bars(paths: Sequence[Path], *, max_rows: int) -> tuple[list[MarketBar], int]:
    bars: list[MarketBar] = []
    duplicate_count = 0
    seen: set[tuple[str, str, datetime]] = set()
    for path in _iter_csv_paths(paths):
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                if len(bars) >= max_rows:
                    return bars, duplicate_count
                try:
                    bar = MarketBar.from_mapping(
                        row,
                        default_symbol=_symbol_from_filename(path),
                        default_timeframe=_timeframe_from_filename(path),
                    )
                except ValueError:
                    continue
                key = (bar.symbol.upper(), bar.timeframe.lower(), bar.timestamp)
                if key in seen:
                    duplicate_count += 1
                    continue
                seen.add(key)
                bars.append(bar)
    return sorted(bars, key=lambda item: (item.timeframe, item.symbol, item.timestamp)), duplicate_count


def build_cross_sectional_availability(
    config: GenericCrossSectionalConfig,
    groups: Mapping[tuple[str, str], Sequence[MarketBar]],
    duplicate_count: int,
) -> CrossSectionalAvailability:
    rows = [bar for group in groups.values() for bar in group]
    symbols = tuple(sorted({bar.symbol for bar in rows}))
    timeframes = tuple(sorted({bar.timeframe.lower() for bar in rows}))
    selected_timeframe = _select_timeframe(groups, config.timeframe_preference)
    start = min((bar.timestamp for bar in rows), default=None)
    end = max((bar.timestamp for bar in rows), default=None)
    if not rows:
        status, available, reason = "DATA_MISSING", False, "spot_ohlcv_multi_symbol_missing"
    elif len(symbols) < 2:
        status, available, reason = "DATA_MISSING", False, "requires_at_least_two_symbols"
    elif not selected_timeframe:
        status, available, reason = "DATA_MISSING", False, "supported_timeframe_missing"
    else:
        status, available, reason = "READY", True, None
    return CrossSectionalAvailability(
        adapter_id=ADAPTER_ID,
        mode=config.mode,
        status=status,
        available=available,
        symbols=symbols,
        timeframes=timeframes,
        start_at=start.isoformat() if start else None,
        end_at=end.isoformat() if end else None,
        row_count=len(rows),
        duplicate_count=duplicate_count,
        selected_timeframe=selected_timeframe,
        reason=reason,
    )


def _leader_laggard_trades(
    config: GenericCrossSectionalConfig,
    groups: Mapping[tuple[str, str], Sequence[MarketBar]],
    timeframe: str,
    cost_config: ExecutionCostConfig,
    variant: Mapping[str, Any],
) -> list[CrossSectionalTrade]:
    rows_by_symbol = _aligned_rows(groups, timeframe, config.symbols[: config.max_symbols])
    symbols = tuple(rows_by_symbol)
    if len(symbols) < 2:
        return []
    lookback = int(variant["lookback_bars"])
    min_relative = float(variant["min_relative_strength_bps"])
    min_corr = float(variant["min_correlation"])
    hold_bars = max(6, min(24, lookback))
    cost_bps = cost_config.round_trip_cost_estimate_bps()
    trades: list[CrossSectionalTrade] = []
    cooldown: dict[str, int] = defaultdict(lambda: -1)
    min_len = min(len(rows_by_symbol[symbol]) for symbol in symbols)
    for index in range(lookback, min_len - hold_bars - 1):
        returns = {
            symbol: _return_bps(rows_by_symbol[symbol][index - lookback].close, rows_by_symbol[symbol][index].close)
            for symbol in symbols
        }
        leader = max(returns, key=returns.get)
        leader_return = returns[leader]
        for symbol in symbols:
            if symbol == leader or index <= cooldown[symbol]:
                continue
            relative_gap = leader_return - returns[symbol]
            if relative_gap < min_relative:
                continue
            corr = _rolling_corr(
                _bar_returns(rows_by_symbol[leader][index - lookback : index + 1]),
                _bar_returns(rows_by_symbol[symbol][index - lookback : index + 1]),
            )
            volatility = _realized_vol_bps(rows_by_symbol[symbol][index - lookback : index + 1])
            if corr < min_corr or volatility < max(cost_bps * 0.1, 10.0):
                continue
            entry_index = index + 1
            exit_index = min(entry_index + hold_bars, min_len - 1)
            trade = _make_trade(
                symbol=symbol,
                mode=config.mode,
                timeframe=timeframe,
                variant_label=_variant_label(variant),
                signal_bar=rows_by_symbol[symbol][index],
                entry_bar=rows_by_symbol[symbol][entry_index],
                exit_bar=rows_by_symbol[symbol][exit_index],
                expected_move_bps=relative_gap,
                cost_bps=cost_bps,
                notional_eur=config.order_notional_eur,
                metadata={
                    "leader_symbol": leader,
                    "leader_return_bps": round(leader_return, 6),
                    "laggard_return_bps": round(returns[symbol], 6),
                    "relative_gap_bps": round(relative_gap, 6),
                    "rolling_correlation": round(corr, 6),
                    "volatility_bps": round(volatility, 6),
                    "anti_lookahead": "leader_and_correlation_windows_end_before_entry",
                },
            )
            trades.append(trade)
            cooldown[symbol] = entry_index + max(3, hold_bars // 2)
    return trades


def _relative_strength_rotation_trades(
    config: GenericCrossSectionalConfig,
    groups: Mapping[tuple[str, str], Sequence[MarketBar]],
    timeframe: str,
    cost_config: ExecutionCostConfig,
    variant: Mapping[str, Any],
) -> list[CrossSectionalTrade]:
    rows_by_symbol = _aligned_rows(groups, timeframe, config.symbols[: config.max_symbols])
    symbols = tuple(rows_by_symbol)
    if len(symbols) < 2:
        return []
    lookback = int(variant["rank_lookback_bars"])
    top_n = int(variant["top_n"])
    hold_bars = _hold_hours_to_bars(float(variant["max_hold_hours"]), timeframe)
    rebalance_bars = max(6, hold_bars)
    cost_bps = cost_config.round_trip_cost_estimate_bps()
    trades: list[CrossSectionalTrade] = []
    min_len = min(len(rows_by_symbol[symbol]) for symbol in symbols)
    for index in range(lookback, min_len - hold_bars - 1, rebalance_bars):
        returns = {
            symbol: _return_bps(rows_by_symbol[symbol][index - lookback].close, rows_by_symbol[symbol][index].close)
            for symbol in symbols
        }
        ranked = sorted(returns.items(), key=lambda item: item[1], reverse=True)
        selected = ranked[: max(1, min(top_n, len(ranked)))]
        median_return = sorted(returns.values())[len(returns) // 2]
        for rank, (symbol, score_bps) in enumerate(selected, start=1):
            relative_strength = score_bps - median_return
            volatility = _realized_vol_bps(rows_by_symbol[symbol][index - lookback : index + 1])
            if relative_strength <= cost_bps or volatility < max(cost_bps * 0.1, 10.0):
                continue
            entry_index = index + 1
            exit_index = min(entry_index + hold_bars, min_len - 1)
            trades.append(
                _make_trade(
                    symbol=symbol,
                    mode=config.mode,
                    timeframe=timeframe,
                    variant_label=_variant_label(variant),
                    signal_bar=rows_by_symbol[symbol][index],
                    entry_bar=rows_by_symbol[symbol][entry_index],
                    exit_bar=rows_by_symbol[symbol][exit_index],
                    expected_move_bps=relative_strength,
                    cost_bps=cost_bps,
                    notional_eur=config.order_notional_eur,
                    metadata={
                        "rank": rank,
                        "rank_score_bps": round(score_bps, 6),
                        "median_rank_score_bps": round(median_return, 6),
                        "relative_strength_bps": round(relative_strength, 6),
                        "volatility_bps": round(volatility, 6),
                        "anti_lookahead": "rank_window_ends_before_entry",
                    },
                )
            )
    return trades


def _make_trade(
    *,
    symbol: str,
    mode: str,
    timeframe: str,
    variant_label: str,
    signal_bar: MarketBar,
    entry_bar: MarketBar,
    exit_bar: MarketBar,
    expected_move_bps: float,
    cost_bps: float,
    notional_eur: float,
    metadata: Mapping[str, Any],
) -> CrossSectionalTrade:
    gross_bps = _return_bps(entry_bar.open, exit_bar.close)
    net_bps = gross_bps - cost_bps
    gross_pnl = notional_eur * gross_bps / 10_000.0
    net_pnl = notional_eur * net_bps / 10_000.0
    return CrossSectionalTrade(
        symbol=symbol,
        opened_at=entry_bar.timestamp,
        closed_at=exit_bar.timestamp,
        signal_at=signal_bar.timestamp,
        mode=mode,
        variant_label=variant_label,
        timeframe=timeframe,
        gross_bps=round(gross_bps, 6),
        cost_bps=round(cost_bps, 6),
        net_bps=round(net_bps, 6),
        gross_pnl_eur=round(gross_pnl, 6),
        net_pnl_eur=round(net_pnl, 6),
        expected_move_bps=round(expected_move_bps, 6),
        estimated_total_cost_bps=round(cost_bps, 6),
        metadata=dict(metadata),
    )


def _metrics(trades: Sequence[CrossSectionalTrade]) -> CrossSectionalMetrics:
    pnl = [trade.net_pnl_eur for trade in trades]
    wins = [value for value in pnl if value > 0]
    losses = [value for value in pnl if value < 0]
    by_symbol_counts: Counter[str] = Counter()
    by_symbol_pnl: defaultdict[str, float] = defaultdict(float)
    by_period_counts: Counter[str] = Counter()
    by_period_pnl: defaultdict[str, float] = defaultdict(float)
    for trade in trades:
        by_symbol_counts[trade.symbol] += 1
        by_symbol_pnl[trade.symbol] += trade.net_pnl_eur
        period = trade.closed_at.date().isoformat()
        by_period_counts[period] += 1
        by_period_pnl[period] += trade.net_pnl_eur
    by_symbol = {
        symbol: {"trade_count": by_symbol_counts[symbol], "net_pnl_eur": round(by_symbol_pnl[symbol], 6)}
        for symbol in sorted(by_symbol_counts)
    }
    by_period = {
        period: {"trade_count": by_period_counts[period], "net_pnl_eur": round(by_period_pnl[period], 6)}
        for period in sorted(by_period_counts)
    }
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    top_symbol = None
    top_share = 0.0
    positive_total = sum(value for value in by_symbol_pnl.values() if value > 0)
    if positive_total > 0:
        top_symbol, top_value = max(
            ((symbol, value) for symbol, value in by_symbol_pnl.items() if value > 0),
            key=lambda item: item[1],
        )
        top_share = top_value / positive_total
    return CrossSectionalMetrics(
        trade_count=len(trades),
        profit_factor_net=(gross_profit / gross_loss if gross_loss else (None if gross_profit else 0.0)),
        net_pnl_eur=round(sum(pnl), 6),
        expectancy_net=(round(sum(pnl) / len(pnl), 6) if pnl else None),
        max_drawdown_eur=round(_max_drawdown(pnl), 6),
        winrate_pct=(round(len(wins) / len(pnl) * 100.0, 6) if pnl else None),
        total_cost_bps=round(sum(trade.cost_bps for trade in trades), 6),
        no_trade_baseline_eur=0.0,
        by_symbol=by_symbol,
        by_period=by_period,
        concentration={"top_positive_symbol": top_symbol, "top_positive_pnl_share": round(top_share, 6)},
    )


def _decision(metrics: CrossSectionalMetrics, variants: Sequence[Mapping[str, Any]]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if metrics.trade_count == 0:
        return "REJECT_FAST", ["no_executable_smoke_trades"]
    if metrics.net_pnl_eur <= 0:
        reasons.append("edge_net_not_positive")
    if metrics.profit_factor_net is None or metrics.profit_factor_net <= 1.0:
        reasons.append("profit_factor_net_not_above_1")
    if metrics.expectancy_net is None or metrics.expectancy_net <= 0:
        reasons.append("expectancy_net_not_positive")
    if metrics.trade_count < 20:
        reasons.append("sample_size_tiny_smoke_only")
    if metrics.concentration.get("top_positive_pnl_share", 0.0) and metrics.concentration["top_positive_pnl_share"] > 0.65:
        reasons.append("symbol_concentration_high")
    if all(int(dict(row.get("metrics") or {}).get("trade_count") or 0) == 0 for row in variants):
        reasons.append("all_variants_empty")
    if reasons:
        return "REJECT_FAST", reasons
    if metrics.trade_count < 50:
        return "KEEP_RESEARCH", ["positive_smoke_but_sample_below_50", "walk_forward_required_before_shadow"]
    return "WALK_FORWARD_AVAILABLE", ["positive_smoke_requires_walk_forward", "no_shadow_or_paper_allowed"]


def _bounded_variants(config: GenericCrossSectionalConfig) -> Iterable[dict[str, Any]]:
    ranges = dict(config.template.get("allowed_parameter_ranges") or {})
    keys = (
        ("lookback_bars", "min_relative_strength_bps", "min_correlation")
        if config.mode == "leader_laggard_momentum"
        else ("rank_lookback_bars", "top_n", "max_hold_hours")
    )
    values = []
    for key in keys:
        raw = ranges.get(key)
        if not isinstance(raw, list) or not raw:
            raw = _default_range_for(key)
        values.append(raw)
    for combo in itertools.islice(itertools.product(*values), config.max_variants):
        yield {key: combo[index] for index, key in enumerate(keys)}


def _default_range_for(key: str) -> list[Any]:
    defaults = {
        "lookback_bars": [24],
        "min_relative_strength_bps": [150],
        "min_correlation": [0.45],
        "rank_lookback_bars": [24],
        "top_n": [2],
        "max_hold_hours": [24],
    }
    return defaults[key]


def _group_bars(
    bars: Sequence[MarketBar],
    symbols: Sequence[str],
) -> dict[tuple[str, str], list[MarketBar]]:
    allowed = {symbol.upper() for symbol in symbols}
    groups: dict[tuple[str, str], list[MarketBar]] = defaultdict(list)
    for bar in bars:
        symbol = bar.symbol.upper()
        if allowed and symbol not in allowed:
            continue
        groups[(symbol, bar.timeframe.lower())].append(bar)
    for key, rows in list(groups.items()):
        groups[key] = sorted(rows, key=lambda row: row.timestamp)
    return groups


def _aligned_rows(
    groups: Mapping[tuple[str, str], Sequence[MarketBar]],
    timeframe: str,
    symbols: Sequence[str],
) -> dict[str, list[MarketBar]]:
    rows = {
        symbol.upper(): list(groups.get((symbol.upper(), timeframe), ()))
        for symbol in symbols
        if len(groups.get((symbol.upper(), timeframe), ())) >= 30
    }
    if len(rows) < 2:
        return {}
    common_timestamps = set.intersection(*(set(row.timestamp for row in series) for series in rows.values()))
    if not common_timestamps:
        return {}
    return {
        symbol: [row for row in series if row.timestamp in common_timestamps]
        for symbol, series in rows.items()
    }


def _select_timeframe(
    groups: Mapping[tuple[str, str], Sequence[MarketBar]],
    preference: Sequence[str],
) -> str | None:
    for timeframe in preference:
        symbols = {symbol for (symbol, tf), rows in groups.items() if tf == timeframe and len(rows) >= 30}
        if len(symbols) >= 2:
            return timeframe
    return None


def _iter_csv_paths(paths: Sequence[Path]) -> Iterable[Path]:
    for path in paths:
        if path.is_dir():
            yield from sorted(path.rglob("*.csv"))
        elif path.suffix.lower() == ".csv" and path.exists():
            yield path


def _symbol_from_filename(path: Path) -> str:
    return path.stem.split("_")[0].upper()


def _timeframe_from_filename(path: Path) -> str:
    parts = path.stem.split("_")
    for part in reversed(parts):
        if part.lower() in {"1m", "5m", "15m", "1h", "4h"}:
            return part.lower()
    return "unknown"


def _return_bps(start: float, end: float) -> float:
    if start <= 0:
        return 0.0
    return ((float(end) / float(start)) - 1.0) * 10_000.0


def _bar_returns(rows: Sequence[MarketBar]) -> list[float]:
    return [_return_bps(prev.close, cur.close) for prev, cur in zip(rows, rows[1:])]


def _rolling_corr(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or len(left) < 3:
        return 0.0
    mean_left = sum(left) / len(left)
    mean_right = sum(right) / len(right)
    cov = sum((a - mean_left) * (b - mean_right) for a, b in zip(left, right))
    var_left = sum((a - mean_left) ** 2 for a in left)
    var_right = sum((b - mean_right) ** 2 for b in right)
    denom = math.sqrt(var_left * var_right)
    return cov / denom if denom > 0 else 0.0


def _realized_vol_bps(rows: Sequence[MarketBar]) -> float:
    returns = _bar_returns(rows)
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / (len(returns) - 1)
    return math.sqrt(max(0.0, variance))


def _hold_hours_to_bars(hours: float, timeframe: str) -> int:
    minutes = {"5m": 5, "15m": 15, "1h": 60, "4h": 240}.get(timeframe, 60)
    return max(1, int(round((float(hours) * 60.0) / minutes)))


def _max_drawdown(values: Sequence[float]) -> float:
    cumulative = 0.0
    peak = 0.0
    worst = 0.0
    for value in values:
        cumulative += value
        peak = max(peak, cumulative)
        worst = max(worst, peak - cumulative)
    return worst


def _variant_label(variant: Mapping[str, Any]) -> str:
    return "__".join(f"{key}{variant[key]}" for key in sorted(variant))
