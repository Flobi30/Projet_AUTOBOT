"""Deterministic research-only benchmarks for closed OOS trade evidence.

The helpers here compare a strategy's *already closed* out-of-sample trades to
three deliberately simple references: abstention, buy-and-hold over the same
OOS window, and a deterministic placebo with the same symbols, trade count,
notionals and holding-duration distribution.  They do not create signals,
orders, fills, paper capital or runtime state.

The comparison is intentionally expressed as net return on the aggregate
deployed notional as well as absolute PnL.  This avoids treating a high
turnover strategy as directly comparable to a single buy-and-hold trade by
absolute PnL alone.
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import math
import random
from typing import Iterable, Mapping, Sequence

from .market_data_repository import MarketBar
from .trade_journal import TradeRecord


_READY = "READY"
_INSUFFICIENT = "INSUFFICIENT_DATA"


@dataclass(frozen=True)
class OOSBaselineResult:
    """One non-executable benchmark measured on a bounded OOS window."""

    name: str
    status: str
    net_pnl_eur: float | None
    net_return_bps: float | None
    trade_count: int
    deployed_notional_eur: float
    exposure_notional_hours: float
    notes: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class OOSBenchmarkReport:
    """Immutable diagnostic comparison for one set of closed OOS trades."""

    status: str
    reasons: tuple[str, ...]
    oos_start_at: str | None
    oos_end_at: str | None
    strategy_trade_count: int
    strategy_net_pnl_eur: float | None
    strategy_net_return_bps: float | None
    strategy_deployed_notional_eur: float
    baselines: tuple[OOSBaselineResult, ...]
    best_baseline_name: str | None
    best_baseline_net_return_bps: float | None
    delta_vs_best_baseline_bps: float | None
    beats_all_baselines: bool | None
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False
    promotable: bool = False

    def __post_init__(self) -> None:
        if self.status not in {_READY, _INSUFFICIENT}:
            raise ValueError("unsupported OOS benchmark status")
        if self.paper_capital_allowed or self.live_allowed or self.promotable or not self.research_only:
            raise ValueError("OOS benchmarks must remain research-only and non-promotional")
        if self.status == _READY:
            if not self.baselines or self.beats_all_baselines is None:
                raise ValueError("ready OOS benchmark report requires complete baselines")
        if self.status == _INSUFFICIENT and not self.reasons:
            raise ValueError("insufficient OOS benchmark report requires reasons")

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["baselines"] = [baseline.to_dict() for baseline in self.baselines]
        return payload


def unavailable_oos_benchmark_report(*reasons: str) -> OOSBenchmarkReport:
    """Return an explicit fail-closed report without inventing a baseline."""

    normalized = tuple(str(reason).strip() for reason in reasons if str(reason).strip())
    return OOSBenchmarkReport(
        status=_INSUFFICIENT,
        reasons=normalized or ("oos_benchmark_inputs_missing",),
        oos_start_at=None,
        oos_end_at=None,
        strategy_trade_count=0,
        strategy_net_pnl_eur=None,
        strategy_net_return_bps=None,
        strategy_deployed_notional_eur=0.0,
        baselines=(),
        best_baseline_name=None,
        best_baseline_net_return_bps=None,
        delta_vs_best_baseline_bps=None,
        beats_all_baselines=None,
    )


def evaluate_closed_oos_trade_benchmarks(
    records: Iterable[TradeRecord],
    bars: Sequence[MarketBar],
    *,
    timeframe: str,
    seed_salt: str,
) -> OOSBenchmarkReport:
    """Compare closed long-only OOS trades with bounded transparent baselines.

    ``records`` are the candidate's closed OOS trades, not a signal source.
    The placebo samples only the same symbol/timeframe data inside the global
    OOS window and reuses each candidate's notional, explicit cost and holding
    duration.  The buy-and-hold reference deploys the same aggregate notional
    per symbol once from the first to the last usable OOS bar.  It is therefore
    a reference, not a portfolio or execution simulation.
    """

    candidates = tuple(sorted(records, key=_record_sort_key))
    if not candidates:
        return unavailable_oos_benchmark_report("closed_oos_trades_missing")
    normalized_timeframe = str(timeframe or "").strip().lower()
    if not normalized_timeframe:
        return unavailable_oos_benchmark_report("oos_timeframe_missing")
    try:
        inputs = tuple(_candidate_input(record) for record in candidates)
    except ValueError as exc:
        return unavailable_oos_benchmark_report(f"oos_trade_evidence_invalid:{exc}")

    start = min(item.opened_at for item in inputs)
    end = max(item.closed_at for item in inputs)
    by_symbol = _eligible_bars(
        bars,
        symbols={item.symbol for item in inputs},
        timeframe=normalized_timeframe,
        start=start,
        end=end,
    )
    missing_symbols = sorted({item.symbol for item in inputs} - set(by_symbol))
    if missing_symbols:
        return _insufficient_from_inputs(
            inputs,
            start,
            end,
            reasons=tuple(f"oos_bars_insufficient:{symbol}" for symbol in missing_symbols),
        )

    strategy_notional = round(sum(item.notional_eur for item in inputs), 8)
    strategy_net = round(sum(item.net_pnl_eur for item in inputs), 8)
    strategy_return = _return_bps(strategy_net, strategy_notional)
    no_trade = OOSBaselineResult(
        name="no_trade",
        status=_READY,
        net_pnl_eur=0.0,
        net_return_bps=0.0,
        trade_count=0,
        deployed_notional_eur=0.0,
        exposure_notional_hours=0.0,
        notes="Abstention throughout the candidate's closed OOS window.",
    )
    buy_hold = _buy_and_hold_baseline(inputs, by_symbol)
    placebo = _same_frequency_placebo_baseline(inputs, by_symbol, seed_salt=seed_salt)
    baselines = (no_trade, buy_hold, placebo)
    if any(baseline.status != _READY or baseline.net_return_bps is None for baseline in baselines):
        reasons = tuple(
            f"oos_baseline_unavailable:{baseline.name}:{baseline.notes}"
            for baseline in baselines
            if baseline.status != _READY or baseline.net_return_bps is None
        )
        return OOSBenchmarkReport(
            status=_INSUFFICIENT,
            reasons=reasons or ("oos_baseline_unavailable",),
            oos_start_at=start.isoformat(),
            oos_end_at=end.isoformat(),
            strategy_trade_count=len(inputs),
            strategy_net_pnl_eur=strategy_net,
            strategy_net_return_bps=strategy_return,
            strategy_deployed_notional_eur=strategy_notional,
            baselines=baselines,
            best_baseline_name=None,
            best_baseline_net_return_bps=None,
            delta_vs_best_baseline_bps=None,
            beats_all_baselines=None,
        )
    best = max(baselines, key=lambda baseline: (float(baseline.net_return_bps or 0.0), baseline.name))
    delta = round(float(strategy_return) - float(best.net_return_bps or 0.0), 8)
    return OOSBenchmarkReport(
        status=_READY,
        reasons=(
            "closed_oos_baselines_complete",
            "placebo_reuses_candidate_symbols_notionals_costs_and_holding_durations",
            "buy_and_hold_uses_same_aggregate_notional_per_symbol_over_oos_window",
        ),
        oos_start_at=start.isoformat(),
        oos_end_at=end.isoformat(),
        strategy_trade_count=len(inputs),
        strategy_net_pnl_eur=strategy_net,
        strategy_net_return_bps=strategy_return,
        strategy_deployed_notional_eur=strategy_notional,
        baselines=baselines,
        best_baseline_name=best.name,
        best_baseline_net_return_bps=best.net_return_bps,
        delta_vs_best_baseline_bps=delta,
        beats_all_baselines=delta > 0.0,
    )


@dataclass(frozen=True)
class _CandidateInput:
    symbol: str
    opened_at: datetime
    closed_at: datetime
    notional_eur: float
    explicit_cost_eur: float
    net_pnl_eur: float

    @property
    def duration_hours(self) -> float:
        return (self.closed_at - self.opened_at).total_seconds() / 3_600.0


def _candidate_input(record: TradeRecord) -> _CandidateInput:
    if str(record.side).lower() != "buy":
        raise ValueError("only_long_only_oos_records_supported")
    opened_at = _utc(record.opened_at, "opened_at")
    closed_at = _utc(record.closed_at, "closed_at")
    if closed_at <= opened_at:
        raise ValueError("non_positive_holding_duration")
    quantity = _positive(record.quantity, "quantity")
    entry_price = _positive(record.entry_price, "entry_price")
    exit_price = _positive(record.exit_price, "exit_price")
    notional = quantity * entry_price
    if not math.isfinite(notional) or notional <= 0.0:
        raise ValueError("notional_eur")
    costs = sum(
        _non_negative(value, "explicit_cost_eur")
        for value in (record.fees_eur, record.spread_cost_eur, record.slippage_eur, record.latency_cost_eur)
    )
    gross = notional * ((exit_price / entry_price) - 1.0)
    if not math.isclose(
        _finite(record.gross_pnl_eur, "gross_pnl_eur"),
        gross,
        rel_tol=1e-6,
        abs_tol=1e-6,
    ):
        raise ValueError("gross_pnl_eur_not_reproducible_from_closed_prices")
    net = _finite(record.net_pnl_eur, "net_pnl_eur")
    if not math.isclose(net, gross - costs, rel_tol=1e-6, abs_tol=1e-6):
        raise ValueError("net_pnl_eur_not_reproducible_from_explicit_costs")
    return _CandidateInput(
        symbol=str(record.symbol).strip().upper(),
        opened_at=opened_at,
        closed_at=closed_at,
        notional_eur=notional,
        explicit_cost_eur=costs,
        net_pnl_eur=net,
    )


def _eligible_bars(
    bars: Sequence[MarketBar],
    *,
    symbols: set[str],
    timeframe: str,
    start: datetime,
    end: datetime,
) -> Mapping[str, tuple[MarketBar, ...]]:
    grouped: dict[str, list[MarketBar]] = {}
    for bar in bars:
        symbol = str(bar.symbol).strip().upper()
        timestamp = _utc(bar.timestamp, "bar timestamp")
        if symbol not in symbols or str(bar.timeframe).strip().lower() != timeframe:
            continue
        if timestamp < start or timestamp > end:
            continue
        if not math.isfinite(float(bar.open)) or not math.isfinite(float(bar.close)):
            continue
        if float(bar.open) <= 0.0 or float(bar.close) <= 0.0:
            continue
        grouped.setdefault(symbol, []).append(bar)
    result: dict[str, tuple[MarketBar, ...]] = {}
    for symbol, rows in grouped.items():
        deduplicated: dict[datetime, MarketBar] = {}
        for row in sorted(rows, key=lambda value: value.timestamp):
            timestamp = _utc(row.timestamp, "bar timestamp")
            previous = deduplicated.get(timestamp)
            if previous is not None and (previous.open != row.open or previous.close != row.close):
                continue
            deduplicated[timestamp] = row
        ordered = tuple(deduplicated[key] for key in sorted(deduplicated))
        if len(ordered) >= 2:
            result[symbol] = ordered
    return result


def _buy_and_hold_baseline(
    inputs: Sequence[_CandidateInput],
    bars_by_symbol: Mapping[str, Sequence[MarketBar]],
) -> OOSBaselineResult:
    by_symbol: dict[str, list[_CandidateInput]] = {}
    for item in inputs:
        by_symbol.setdefault(item.symbol, []).append(item)
    net = 0.0
    deployed = 0.0
    exposure = 0.0
    completed = 0
    for symbol, symbol_inputs in sorted(by_symbol.items()):
        bars = tuple(bars_by_symbol.get(symbol, ()))
        if len(bars) < 2:
            return _unavailable_baseline("buy_and_hold", f"bars_missing:{symbol}")
        notional = sum(item.notional_eur for item in symbol_inputs)
        weighted_cost_rate = sum(item.explicit_cost_eur for item in symbol_inputs) / notional
        entry = float(bars[0].open)
        exit_price = float(bars[-1].close)
        gross = notional * ((exit_price / entry) - 1.0)
        net += gross - (notional * weighted_cost_rate)
        deployed += notional
        exposure += notional * ((_utc(bars[-1].timestamp, "bar timestamp") - _utc(bars[0].timestamp, "bar timestamp")).total_seconds() / 3_600.0)
        completed += 1
    return OOSBaselineResult(
        name="buy_and_hold_oos_window",
        status=_READY,
        net_pnl_eur=round(net, 8),
        net_return_bps=_return_bps(net, deployed),
        trade_count=completed,
        deployed_notional_eur=round(deployed, 8),
        exposure_notional_hours=round(exposure, 8),
        notes="One net-of-cost long per candidate symbol across the bounded OOS window; aggregate candidate notional is retained per symbol.",
    )


def _same_frequency_placebo_baseline(
    inputs: Sequence[_CandidateInput],
    bars_by_symbol: Mapping[str, Sequence[MarketBar]],
    *,
    seed_salt: str,
) -> OOSBaselineResult:
    rng = random.Random(_seed(seed_salt, inputs))
    net = 0.0
    deployed = 0.0
    exposure = 0.0
    for item in inputs:
        bars = tuple(bars_by_symbol.get(item.symbol, ()))
        sampled = _sample_same_duration(bars, duration_seconds=(item.closed_at - item.opened_at).total_seconds(), rng=rng)
        if sampled is None:
            return _unavailable_baseline("placebo_same_frequency", f"duration_unavailable:{item.symbol}")
        entry, exit_bar = sampled
        gross = item.notional_eur * ((float(exit_bar.close) / float(entry.open)) - 1.0)
        net += gross - item.explicit_cost_eur
        deployed += item.notional_eur
        exposure += item.notional_eur * ((_utc(exit_bar.timestamp, "bar timestamp") - _utc(entry.timestamp, "bar timestamp")).total_seconds() / 3_600.0)
    return OOSBaselineResult(
        name="placebo_same_frequency",
        status=_READY,
        net_pnl_eur=round(net, 8),
        net_return_bps=_return_bps(net, deployed),
        trade_count=len(inputs),
        deployed_notional_eur=round(deployed, 8),
        exposure_notional_hours=round(exposure, 8),
        notes="Deterministic random long entries on the same symbols/timeframe, reusing candidate notionals, explicit costs, trade count and holding durations.",
    )


def _sample_same_duration(
    bars: Sequence[MarketBar],
    *,
    duration_seconds: float,
    rng: random.Random,
) -> tuple[MarketBar, MarketBar] | None:
    if len(bars) < 2 or not math.isfinite(duration_seconds) or duration_seconds <= 0.0:
        return None
    timestamps = [_utc(bar.timestamp, "bar timestamp") for bar in bars]
    eligible: list[tuple[int, int]] = []
    for index, entry_time in enumerate(timestamps[:-1]):
        exit_index = bisect_left(timestamps, entry_time + timedelta(seconds=duration_seconds), lo=index + 1)
        if exit_index < len(bars):
            eligible.append((index, exit_index))
    if not eligible:
        return None
    entry_index, exit_index = eligible[rng.randrange(len(eligible))]
    return bars[entry_index], bars[exit_index]


def _insufficient_from_inputs(
    inputs: Sequence[_CandidateInput],
    start: datetime,
    end: datetime,
    *,
    reasons: tuple[str, ...],
) -> OOSBenchmarkReport:
    deployed = round(sum(item.notional_eur for item in inputs), 8)
    net = round(sum(item.net_pnl_eur for item in inputs), 8)
    return OOSBenchmarkReport(
        status=_INSUFFICIENT,
        reasons=reasons,
        oos_start_at=start.isoformat(),
        oos_end_at=end.isoformat(),
        strategy_trade_count=len(inputs),
        strategy_net_pnl_eur=net,
        strategy_net_return_bps=_return_bps(net, deployed),
        strategy_deployed_notional_eur=deployed,
        baselines=(),
        best_baseline_name=None,
        best_baseline_net_return_bps=None,
        delta_vs_best_baseline_bps=None,
        beats_all_baselines=None,
    )


def _unavailable_baseline(name: str, reason: str) -> OOSBaselineResult:
    return OOSBaselineResult(
        name=name,
        status=_INSUFFICIENT,
        net_pnl_eur=None,
        net_return_bps=None,
        trade_count=0,
        deployed_notional_eur=0.0,
        exposure_notional_hours=0.0,
        notes=reason,
    )


def _record_sort_key(record: TradeRecord) -> tuple[datetime, datetime, str, float, float]:
    return (
        _utc(record.opened_at, "opened_at"),
        _utc(record.closed_at, "closed_at"),
        str(record.symbol).upper(),
        float(record.entry_price),
        float(record.quantity),
    )


def _seed(seed_salt: str, inputs: Sequence[_CandidateInput]) -> int:
    payload = {
        "seed_salt": str(seed_salt),
        "trades": [
            {
                "symbol": item.symbol,
                "opened_at": item.opened_at.isoformat(),
                "closed_at": item.closed_at.isoformat(),
                "notional_eur": round(item.notional_eur, 12),
                "explicit_cost_eur": round(item.explicit_cost_eur, 12),
            }
            for item in inputs
        ],
    }
    encoded = repr(payload).encode("utf-8")
    return int.from_bytes(sha256(encoded).digest()[:8], "big")


def _return_bps(net_pnl_eur: float, deployed_notional_eur: float) -> float:
    if deployed_notional_eur <= 0.0:
        return 0.0
    return round((net_pnl_eur / deployed_notional_eur) * 10_000.0, 8)


def _utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name}_must_be_timezone_aware")
    return value.astimezone(timezone.utc)


def _finite(value: object, field_name: str) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(field_name) from exc
    if not math.isfinite(numeric):
        raise ValueError(field_name)
    return numeric


def _positive(value: object, field_name: str) -> float:
    numeric = _finite(value, field_name)
    if numeric <= 0.0:
        raise ValueError(field_name)
    return numeric


def _non_negative(value: object, field_name: str) -> float:
    numeric = _finite(value, field_name)
    if numeric < 0.0:
        raise ValueError(field_name)
    return numeric
