"""Bounded closed-bar volatility-reversal research adapter.

This is a new, research-only mean-reversion hypothesis.  It is intentionally
separate from the legacy runtime ``mean_reversion`` strategy: it reads closed
OHLCV, emits hypothetical research trades only, and imports no runtime,
paper, or order-routing component.
"""

from __future__ import annotations

import itertools
import math
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .alpha_hypothesis_lab import RESEARCH_ONLY_CAPITAL_FLAGS
from .execution_cost_model import ExecutionCostConfig, execution_cost_config_for_profile
from .generic_cross_sectional_ohlcv_adapter import (
    CrossSectionalAvailability,
    CrossSectionalMetrics,
    CrossSectionalTrade,
    load_cross_sectional_bars,
)
from .market_data_repository import MarketBar


ADAPTER_ID = "volatility_reversal_research_adapter"
SUPPORTED_MODE = "volatility_reversal_after_extension"
ROLLING_MEAN_BARS = 24
RANGE_SIGMA_MULTIPLIER = 2.0
COST_MARGIN_MULTIPLIER = 1.25
TIMEFRAME_SECONDS = {"5m": 300, "15m": 900, "1h": 3600}


@dataclass(frozen=True)
class VolatilityReversalResearchConfig:
    run_id: str
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
    evaluation_start_at: datetime | None = None
    evaluation_end_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.run_id.strip() or not self.data_paths:
            raise ValueError("run_id and data_paths are required")
        if self.max_variants <= 0 or self.max_variants > 3:
            raise ValueError("max_variants must be between 1 and 3")
        if self.max_symbols <= 0 or self.max_symbols > 6:
            raise ValueError("max_symbols must be between 1 and 6")
        if self.max_runtime_seconds <= 0.0 or self.max_data_rows <= 0 or self.order_notional_eur <= 0.0:
            raise ValueError("runtime, data-row, and notional limits must be positive")
        if not self.timeframe_preference or any(value not in TIMEFRAME_SECONDS for value in self.timeframe_preference):
            raise ValueError("timeframe_preference must contain supported closed-bar timeframes")
        for value in (self.evaluation_start_at, self.evaluation_end_at):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError("evaluation bounds must be timezone-aware")
        if (
            self.evaluation_start_at is not None
            and self.evaluation_end_at is not None
            and self.evaluation_end_at <= self.evaluation_start_at
        ):
            raise ValueError("evaluation_end_at must be after evaluation_start_at")
        execution_cost_config_for_profile(self.cost_profile).validate()


@dataclass(frozen=True)
class VolatilityReversalSmokeResult:
    adapter_id: str
    mode: str
    template_id: str
    variant_count: int
    primary_variant: str | None
    decision: str
    reasons: tuple[str, ...]
    metrics: CrossSectionalMetrics
    variants: tuple[Mapping[str, Any], ...]
    availability: CrossSectionalAvailability
    elapsed_seconds: float
    primary_trades: tuple[CrossSectionalTrade, ...] = ()
    safety: Mapping[str, bool] = field(default_factory=lambda: dict(RESEARCH_ONLY_CAPITAL_FLAGS))
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
            "primary_trades": [item.to_dict() for item in self.primary_trades],
            "safety": dict(self.safety),
            "paper_capital_allowed": False,
            "live_allowed": False,
            "promotable": False,
        }


def run_volatility_reversal_research_smoke(
    config: VolatilityReversalResearchConfig,
) -> VolatilityReversalSmokeResult:
    """Run only predeclared, net-of-cost, closed-bar research variants."""

    started = time.perf_counter()
    bars, duplicate_count = load_cross_sectional_bars(config.data_paths, max_rows=config.max_data_rows)
    groups = _groups(bars, config.symbols[: config.max_symbols])
    availability = build_volatility_reversal_availability(config, groups, duplicate_count)
    if not availability.available:
        return VolatilityReversalSmokeResult(
            adapter_id=ADAPTER_ID,
            mode=SUPPORTED_MODE,
            template_id=str(config.template.get("template_id") or SUPPORTED_MODE),
            variant_count=0,
            primary_variant=None,
            decision="DATA_MISSING",
            reasons=tuple(item for item in (availability.reason,) if item),
            metrics=_metrics(()),
            variants=(),
            availability=availability,
            elapsed_seconds=round(time.perf_counter() - started, 6),
        )

    variants = tuple(_bounded_variants(config))
    cost_config = execution_cost_config_for_profile(config.cost_profile)
    primary_trades: list[CrossSectionalTrade] = []
    rows: list[dict[str, Any]] = []
    for index, variant in enumerate(variants):
        if time.perf_counter() - started > config.max_runtime_seconds:
            break
        trades = _simulate(
            config,
            groups,
            str(availability.selected_timeframe),
            cost_config,
            variant,
        )
        metrics = _metrics(trades)
        rows.append(
            {
                "variant_index": index,
                "variant": dict(variant),
                "selection_policy": "predeclared_balanced_template_order_not_best_pnl",
                "fixed_parameters": {
                    "rolling_mean_bars": ROLLING_MEAN_BARS,
                    "range_regime_rule": "abs(prior_window_return) <= 2 * prior_return_std * sqrt(window)",
                    "cost_margin_multiplier": COST_MARGIN_MULTIPLIER,
                    "loss_control": "one_pre_entry_mean_distance_below_entry",
                },
                "metrics": metrics.to_dict(),
                **_trade_summary(trades),
                "status": "research_only",
                **RESEARCH_ONLY_CAPITAL_FLAGS,
            }
        )
        if index == 0:
            primary_trades = trades
    metrics = _metrics(primary_trades)
    decision, reasons = _decision(metrics, rows, config.template)
    return VolatilityReversalSmokeResult(
        adapter_id=ADAPTER_ID,
        mode=SUPPORTED_MODE,
        template_id=str(config.template.get("template_id") or SUPPORTED_MODE),
        variant_count=len(rows),
        primary_variant=_label(variants[0]) if rows else None,
        decision=decision,
        reasons=tuple(reasons),
        metrics=metrics,
        variants=tuple(rows),
        availability=availability,
        elapsed_seconds=round(time.perf_counter() - started, 6),
        primary_trades=tuple(primary_trades),
    )


def build_volatility_reversal_availability(
    config: VolatilityReversalResearchConfig,
    groups: Mapping[tuple[str, str], Sequence[MarketBar]] | None = None,
    duplicate_count: int | None = None,
) -> CrossSectionalAvailability:
    if groups is None or duplicate_count is None:
        bars, loaded_duplicates = load_cross_sectional_bars(config.data_paths, max_rows=config.max_data_rows)
        groups = _groups(bars, config.symbols[: config.max_symbols])
        duplicate_count = loaded_duplicates
    rows = [bar for values in groups.values() for bar in values]
    symbols = tuple(sorted({bar.symbol.upper() for bar in rows}))
    timeframes = tuple(sorted({bar.timeframe.lower() for bar in rows}))
    selected = _select_timeframe(groups, config.timeframe_preference)
    start = min((bar.timestamp for bar in rows), default=None)
    end = max((bar.timestamp for bar in rows), default=None)
    status = "READY" if selected else "DATA_MISSING"
    return CrossSectionalAvailability(
        adapter_id=ADAPTER_ID,
        mode=SUPPORTED_MODE,
        status=status,
        available=bool(selected),
        symbols=symbols,
        timeframes=timeframes,
        start_at=start.isoformat() if start else None,
        end_at=end.isoformat() if end else None,
        row_count=len(rows),
        duplicate_count=int(duplicate_count or 0),
        selected_timeframe=selected,
        reason=None if selected else "closed_ohlcv_history_insufficient_for_reversal_window",
    )


def _simulate(
    config: VolatilityReversalResearchConfig,
    groups: Mapping[tuple[str, str], Sequence[MarketBar]],
    timeframe: str,
    costs: ExecutionCostConfig,
    variant: Mapping[str, Any],
) -> list[CrossSectionalTrade]:
    result: list[CrossSectionalTrade] = []
    cost_parts = _cost_parts(costs)
    cost_bps = sum(cost_parts.values())
    hold_bars = max(1, math.ceil(float(variant["max_hold_hours"]) * 3600.0 / TIMEFRAME_SECONDS[timeframe]))
    for symbol in config.symbols[: config.max_symbols]:
        bars = list(groups.get((symbol.upper(), timeframe), ()))
        index = ROLLING_MEAN_BARS
        while index < len(bars) - 1:
            prior = bars[index - ROLLING_MEAN_BARS : index]
            signal_bar, entry_bar = bars[index], bars[index + 1]
            mean, std = _mean_std([bar.close for bar in prior])
            zscore = (signal_bar.close - mean) / std if std else 0.0
            window_return, noise_band = _range_measure(prior)
            signal_at = _available_at(signal_bar)
            if any(
                (
                    std <= 0.0,
                    zscore > float(variant["zscore_entry"]),
                    abs(window_return) > noise_band,
                    entry_bar.timestamp < signal_at,
                    mean <= entry_bar.open,
                )
            ):
                index += 1
                continue
            target = entry_bar.open + (mean - entry_bar.open) * float(variant["mean_target_fraction"])
            expected_move = _return_bps(entry_bar.open, target)
            if expected_move <= cost_bps * COST_MARGIN_MULTIPLIER:
                index += 1
                continue
            stop = entry_bar.open - abs(mean - entry_bar.open)
            if stop <= 0.0:
                index += 1
                continue
            exit_index, exit_price, exit_reason = _exit(bars, index + 1, hold_bars, target, stop)
            closed_at = _available_at(bars[exit_index])
            if not _inside_evaluation_window(config, signal_at, entry_bar.timestamp, closed_at):
                index += 1
                continue
            gross_bps = _return_bps(entry_bar.open, exit_price)
            metadata = {
                "anti_lookahead": "prior_window_excludes_signal_bar; signal_uses_closed_bar; entry_is_next_bar_open",
                "signal_bar_timestamp": signal_bar.timestamp.isoformat(),
                "signal_bar_available_time": signal_at.isoformat(),
                "pre_entry_window_end": prior[-1].timestamp.isoformat(),
                "regime": "range_like",
                "zscore": round(zscore, 8),
                "range_window_return_bps": round(window_return, 8),
                "range_noise_band_bps": round(noise_band, 8),
                "target_price": round(target, 10),
                "stop_price": round(stop, 10),
                "exit_reason": exit_reason,
                "cost_components_bps": {key: round(value, 8) for key, value in cost_parts.items()},
                "cost_profile": costs.cost_profile,
                **RESEARCH_ONLY_CAPITAL_FLAGS,
            }
            result.append(
                CrossSectionalTrade(
                    symbol=symbol.upper(),
                    opened_at=entry_bar.timestamp,
                    closed_at=closed_at,
                    signal_at=signal_at,
                    mode=SUPPORTED_MODE,
                    variant_label=_label(variant),
                    timeframe=timeframe,
                    gross_bps=round(gross_bps, 8),
                    cost_bps=round(cost_bps, 8),
                    net_bps=round(gross_bps - cost_bps, 8),
                    gross_pnl_eur=round(config.order_notional_eur * gross_bps / 10_000.0, 8),
                    net_pnl_eur=round(config.order_notional_eur * (gross_bps - cost_bps) / 10_000.0, 8),
                    expected_move_bps=round(expected_move, 8),
                    estimated_total_cost_bps=round(cost_bps, 8),
                    metadata=metadata,
                )
            )
            index = exit_index + 1  # one hypothetical position per symbol
    return result


def _exit(
    bars: Sequence[MarketBar], entry_index: int, hold_bars: int, target: float, stop: float
) -> tuple[int, float, str]:
    last = min(len(bars) - 1, entry_index + hold_bars - 1)
    for index in range(entry_index, last + 1):
        bar = bars[index]
        # OHLC cannot order intrabar highs/lows. Prefer the adverse outcome.
        if bar.low <= stop:
            return index, stop, "fixed_loss_control"
        if bar.high >= target:
            return index, target, "mean_target"
    return last, bars[last].close, "time_stop"


def _metrics(trades: Sequence[CrossSectionalTrade]) -> CrossSectionalMetrics:
    pnl = [trade.net_pnl_eur for trade in trades]
    wins, losses = [value for value in pnl if value > 0.0], [value for value in pnl if value < 0.0]
    by_symbol_count: Counter[str] = Counter(trade.symbol for trade in trades)
    by_symbol_pnl: defaultdict[str, float] = defaultdict(float)
    by_period_count: Counter[str] = Counter()
    by_period_pnl: defaultdict[str, float] = defaultdict(float)
    for trade in trades:
        by_symbol_pnl[trade.symbol] += trade.net_pnl_eur
        period = trade.closed_at.date().isoformat()
        by_period_count[period] += 1
        by_period_pnl[period] += trade.net_pnl_eur
    positives = [(symbol, value) for symbol, value in by_symbol_pnl.items() if value > 0.0]
    total_positive = sum(value for _, value in positives)
    top_symbol, top_value = max(positives, key=lambda item: item[1]) if positives else (None, 0.0)
    return CrossSectionalMetrics(
        trade_count=len(trades),
        profit_factor_net=sum(wins) / abs(sum(losses)) if losses else (None if not wins else float("inf")),
        net_pnl_eur=round(sum(pnl), 6),
        expectancy_net=round(sum(pnl) / len(pnl), 6) if pnl else None,
        max_drawdown_eur=round(_max_drawdown(pnl), 6),
        winrate_pct=round(100.0 * len(wins) / len(pnl), 6) if pnl else None,
        total_cost_bps=round(sum(trade.cost_bps for trade in trades), 6),
        no_trade_baseline_eur=0.0,
        by_symbol={
            symbol: {"trade_count": by_symbol_count[symbol], "net_pnl_eur": round(by_symbol_pnl[symbol], 6)}
            for symbol in sorted(by_symbol_count)
        },
        by_period={
            period: {"trade_count": by_period_count[period], "net_pnl_eur": round(by_period_pnl[period], 6)}
            for period in sorted(by_period_count)
        },
        concentration={
            "top_positive_symbol": top_symbol,
            "top_positive_pnl_share": round(top_value / total_positive, 6) if total_positive else 0.0,
        },
    )


def compute_volatility_reversal_metrics(
    trades: Sequence[CrossSectionalTrade],
) -> CrossSectionalMetrics:
    """Return the canonical net-of-cost metrics for this research adapter."""

    return _metrics(trades)


def _decision(
    metrics: CrossSectionalMetrics, variants: Sequence[Mapping[str, Any]], template: Mapping[str, Any]
) -> tuple[str, list[str]]:
    minimum = int(template.get("minimum_sample_size") or 50)
    if metrics.trade_count == 0:
        return "INSUFFICIENT_DATA", ["no_executable_range_reversal_trades"]
    if metrics.trade_count < minimum:
        if metrics.trade_count >= 30 and (metrics.profit_factor_net is None or metrics.profit_factor_net < 0.9):
            return "REJECT_FAST", ["sample_size_below_template_minimum", "profit_factor_net_below_0_9_after_30_trades"]
        return "INSUFFICIENT_DATA", ["sample_size_below_template_minimum"]
    reasons: list[str] = []
    primary = dict(variants[0]) if variants else {}
    gross_pnl = float(primary.get("gross_pnl_eur") or 0.0)
    explicit_cost_eur = float(primary.get("explicit_cost_eur") or 0.0)
    if gross_pnl > 0.0 and metrics.net_pnl_eur <= 0.0:
        reasons.append("gross_positive_net_negative")
    if gross_pnl > 0.0 and explicit_cost_eur >= gross_pnl:
        reasons.append("costs_exceed_reversal")
    if metrics.net_pnl_eur <= 0.0:
        reasons.append("edge_net_not_positive")
    if metrics.profit_factor_net is None or metrics.profit_factor_net <= 1.0:
        reasons.append("profit_factor_net_not_above_1")
    if metrics.expectancy_net is None or metrics.expectancy_net <= 0.0:
        reasons.append("expectancy_net_not_positive")
    if metrics.concentration.get("top_positive_pnl_share", 0.0) > 0.65:
        reasons.append("symbol_concentration_high")
    if all(int(dict(row.get("metrics") or {}).get("trade_count") or 0) == 0 for row in variants):
        reasons.append("all_variants_empty")
    return ("REJECT_FAST", reasons) if reasons else ("WALK_FORWARD_AVAILABLE", ["net_cost_smoke_requires_walk_forward_before_shadow_or_paper"])


def _trade_summary(trades: Sequence[CrossSectionalTrade]) -> dict[str, float]:
    gross = sum(trade.gross_pnl_eur for trade in trades)
    net = sum(trade.net_pnl_eur for trade in trades)
    return {
        "gross_pnl_eur": round(gross, 6),
        "net_pnl_eur": round(net, 6),
        "explicit_cost_eur": round(gross - net, 6),
    }


def _bounded_variants(config: VolatilityReversalResearchConfig) -> Iterable[dict[str, Any]]:
    ranges = dict(config.template.get("allowed_parameter_ranges") or {})
    zscores = _values(ranges, "zscore_entry", [-2.0])
    targets = _values(ranges, "mean_target_fraction", [0.5])
    holds = _values(ranges, "max_hold_hours", [24])
    candidates = (
        {"zscore_entry": zscores[0], "mean_target_fraction": targets[0], "max_hold_hours": holds[0]},
        {"zscore_entry": zscores[-1], "mean_target_fraction": targets[0], "max_hold_hours": holds[0]},
        {"zscore_entry": zscores[-1], "mean_target_fraction": targets[-1], "max_hold_hours": holds[-1]},
    )
    seen: set[tuple[tuple[str, Any], ...]] = set()
    for item in itertools.islice(candidates, config.max_variants):
        key = tuple(sorted(item.items()))
        if key not in seen:
            seen.add(key)
            yield item


def _values(ranges: Mapping[str, Any], name: str, default: list[Any]) -> list[Any]:
    value = ranges.get(name)
    return list(value) if isinstance(value, list) and value else default


def _groups(bars: Sequence[MarketBar], symbols: Sequence[str]) -> dict[tuple[str, str], list[MarketBar]]:
    allowed = {item.upper() for item in symbols}
    result: defaultdict[tuple[str, str], list[MarketBar]] = defaultdict(list)
    for bar in bars:
        if bar.symbol.upper() in allowed and bar.timeframe.lower() in TIMEFRAME_SECONDS:
            result[(bar.symbol.upper(), bar.timeframe.lower())].append(bar)
    return {key: sorted(value, key=lambda bar: bar.timestamp) for key, value in result.items()}


def _select_timeframe(groups: Mapping[tuple[str, str], Sequence[MarketBar]], preference: Sequence[str]) -> str | None:
    for timeframe in preference:
        if any(len(rows) >= ROLLING_MEAN_BARS + 2 for (_, item), rows in groups.items() if item == timeframe):
            return timeframe
    return None


def _mean_std(values: Sequence[float]) -> tuple[float, float]:
    mean = sum(values) / len(values)
    return mean, math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))


def _range_measure(bars: Sequence[MarketBar]) -> tuple[float, float]:
    returns = [_return_bps(left.close, right.close) for left, right in zip(bars, bars[1:])]
    _, std = _mean_std(returns)
    return _return_bps(bars[0].close, bars[-1].close), RANGE_SIGMA_MULTIPLIER * std * math.sqrt(len(returns))


def _cost_parts(config: ExecutionCostConfig) -> dict[str, float]:
    return {
        "fees_bps": config.fee_for_order_type(config.default_entry_order_type) + config.fee_for_order_type(config.default_exit_order_type),
        "spread_cost_bps": config.fallback_spread_bps * (config.spread_charge_fraction(config.default_entry_order_type) + config.spread_charge_fraction(config.default_exit_order_type)) / 2.0,
        "slippage_bps": 2.0 * config.slippage_bps,
        "latency_cost_bps": 2.0 * config.latency_buffer_bps,
    }


def _available_at(bar: MarketBar) -> datetime:
    value = bar.metadata.get("available_time") or bar.metadata.get("candle_close_time")
    if value is None:
        return bar.timestamp.astimezone(timezone.utc) + timedelta(seconds=TIMEFRAME_SECONDS[bar.timeframe.lower()])
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("available_time must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _inside_evaluation_window(
    config: VolatilityReversalResearchConfig,
    signal_at: datetime,
    opened_at: datetime,
    closed_at: datetime,
) -> bool:
    """Keep evaluation records fully inside an explicitly bounded OOS window."""

    if config.evaluation_start_at is not None:
        start = config.evaluation_start_at.astimezone(timezone.utc)
        if signal_at < start or opened_at < start:
            return False
    if config.evaluation_end_at is not None:
        end = config.evaluation_end_at.astimezone(timezone.utc)
        if signal_at >= end or closed_at > end:
            return False
    return True


def _return_bps(start: float, end: float) -> float:
    if start <= 0.0 or end <= 0.0:
        raise ValueError("prices must be positive")
    return ((end / start) - 1.0) * 10_000.0


def _max_drawdown(values: Sequence[float]) -> float:
    equity = peak = drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown


def _label(variant: Mapping[str, Any]) -> str:
    return f"z{float(variant['zscore_entry']):g}__target{float(variant['mean_target_fraction']):g}__hold{float(variant['max_hold_hours']):g}h"
