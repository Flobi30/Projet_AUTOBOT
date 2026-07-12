"""Bounded, research-only funding/basis spot-context adapter.

The adapter consumes a point-in-time Kraken Futures feature snapshot as a
*directional context* and evaluates only the mapped AUTOBOT spot-EUR OHLCV
series.  Perpetual USD prices are never converted or used to calculate EUR
returns: all simulated gross/net PnL is computed from the spot bars.

It deliberately imports no runtime router, paper executor, order handler, or
strategy-promotion code.  A positive smoke result remains research-only and
must pass the separate walk-forward/statistical gates before any human review.
"""

from __future__ import annotations

import csv
import itertools
import math
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .alpha_hypothesis_lab import RESEARCH_ONLY_CAPITAL_FLAGS
from .derivatives_feature_snapshot import (
    DerivativesFeatureSnapshotManifestError,
    inspect_derivatives_feature_snapshot_manifest,
)
from .execution_cost_model import ExecutionCostConfig, execution_cost_config_for_profile
from .market_data_repository import MarketBar


ADAPTER_ID = "funding_basis_research_adapter"
SUPPORTED_MODE = "funding_extreme_reversion"
REQUIRED_DERIVATIVES_FEATURES = {"funding_rate_relative", "basis_bps"}


@dataclass(frozen=True)
class FundingBasisResearchConfig:
    run_id: str
    spot_data_paths: tuple[Path, ...]
    derivatives_feature_snapshot_manifest: Path
    template: Mapping[str, Any]
    symbols: tuple[str, ...]
    cost_profile: str = "research_stress"
    max_variants: int = 2
    max_symbols: int = 4
    max_runtime_seconds: float = 120.0
    max_data_rows: int = 250_000
    order_notional_eur: float = 100.0
    min_funding_observations: int = 30
    timeframe_preference: tuple[str, ...] = ("1h", "15m")

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id is required")
        if not self.spot_data_paths:
            raise ValueError("spot_data_paths is required")
        if not self.symbols:
            raise ValueError("symbols is required")
        if self.max_variants <= 0 or self.max_variants > 2:
            raise ValueError("max_variants must be between 1 and 2")
        if self.max_symbols <= 0 or self.max_symbols > 4:
            raise ValueError("max_symbols must be between 1 and 4")
        if self.max_runtime_seconds <= 0.0:
            raise ValueError("max_runtime_seconds must be positive")
        if self.max_data_rows <= 0:
            raise ValueError("max_data_rows must be positive")
        if self.order_notional_eur <= 0.0:
            raise ValueError("order_notional_eur must be positive")
        if self.min_funding_observations < 10:
            raise ValueError("min_funding_observations must be at least 10")
        execution_cost_config_for_profile(self.cost_profile).validate()


@dataclass(frozen=True)
class FundingBasisAvailability:
    adapter_id: str
    status: str
    available: bool
    selected_timeframe: str | None
    symbols: tuple[str, ...]
    futures_to_spot: Mapping[str, str]
    spot_row_count: int
    derivatives_feature_count: int
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "futures_to_spot": dict(self.futures_to_spot),
        }


@dataclass(frozen=True)
class FundingBasisTrade:
    spot_symbol: str
    futures_symbol: str
    signal_at: datetime
    opened_at: datetime
    closed_at: datetime
    timeframe: str
    variant_label: str
    funding_rate_relative: float
    funding_percentile_threshold: float
    basis_bps: float
    gross_bps: float
    cost_bps: float
    net_bps: float
    gross_pnl_eur: float
    net_pnl_eur: float
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in ("signal_at", "opened_at", "closed_at"):
            payload[key] = getattr(self, key).isoformat()
        return payload


@dataclass(frozen=True)
class FundingBasisMetrics:
    trade_count: int
    gross_pnl_eur: float
    net_pnl_eur: float
    profit_factor_net: float | None
    expectancy_net: float | None
    winrate_pct: float | None
    max_drawdown_eur: float
    total_cost_bps: float
    no_trade_baseline_eur: float
    by_symbol: Mapping[str, Mapping[str, Any]]
    by_period: Mapping[str, Mapping[str, Any]]
    concentration: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "by_symbol": {key: dict(value) for key, value in self.by_symbol.items()},
            "by_period": {key: dict(value) for key, value in self.by_period.items()},
            "concentration": dict(self.concentration),
        }


@dataclass(frozen=True)
class FundingBasisSmokeResult:
    adapter_id: str
    mode: str
    template_id: str
    variant_count: int
    primary_variant: str | None
    decision: str
    reasons: tuple[str, ...]
    metrics: FundingBasisMetrics
    variants: tuple[Mapping[str, Any], ...]
    availability: FundingBasisAvailability
    elapsed_seconds: float
    primary_trades: tuple[FundingBasisTrade, ...] = ()
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
            "primary_trades": [item.to_dict() for item in self.primary_trades],
            "availability": self.availability.to_dict(),
            "elapsed_seconds": self.elapsed_seconds,
            "safety": dict(self.safety),
            "paper_capital_allowed": False,
            "live_allowed": False,
            "promotable": False,
        }


@dataclass(frozen=True)
class _FeatureObservation:
    futures_symbol: str
    feature_id: str
    event_time: datetime
    available_time: datetime
    value: float


def run_funding_basis_research_smoke(config: FundingBasisResearchConfig) -> FundingBasisSmokeResult:
    """Run bounded spot-only simulations from pre-entry derivatives context."""

    started = time.perf_counter()
    spot_bars, duplicate_count = _load_spot_bars(config.spot_data_paths, max_rows=config.max_data_rows)
    try:
        availability, observations = _build_availability(config, spot_bars, duplicate_count)
    except (DerivativesFeatureSnapshotManifestError, OSError, ValueError) as exc:
        availability = FundingBasisAvailability(
            adapter_id=ADAPTER_ID,
            status="DATA_MISSING",
            available=False,
            selected_timeframe=None,
            symbols=(),
            futures_to_spot={},
            spot_row_count=len(spot_bars),
            derivatives_feature_count=0,
            blockers=(f"derivatives_snapshot_invalid:{exc}",),
        )
        observations = {}
    if not availability.available:
        return FundingBasisSmokeResult(
            adapter_id=ADAPTER_ID,
            mode=SUPPORTED_MODE,
            template_id=str(config.template.get("template_id") or SUPPORTED_MODE),
            variant_count=0,
            primary_variant=None,
            decision="INSUFFICIENT_DATA",
            reasons=availability.blockers or ("funding_basis_inputs_unavailable",),
            metrics=_metrics(()),
            variants=(),
            availability=availability,
            elapsed_seconds=round(time.perf_counter() - started, 6),
        )

    bars_by_symbol = _spot_groups(
        spot_bars,
        symbols=availability.symbols,
        timeframe=str(availability.selected_timeframe),
    )
    cost_config = execution_cost_config_for_profile(config.cost_profile)
    variants = tuple(_bounded_variants(config))
    primary_trades: list[FundingBasisTrade] = []
    variant_rows: list[dict[str, Any]] = []
    for index, variant in enumerate(variants):
        if time.perf_counter() - started > config.max_runtime_seconds:
            break
        trades = _simulate_variant(
            config=config,
            bars_by_symbol=bars_by_symbol,
            observations=observations,
            futures_to_spot=availability.futures_to_spot,
            timeframe=str(availability.selected_timeframe),
            cost_config=cost_config,
            variant=variant,
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
            primary_trades = trades
    primary_metrics = _metrics(primary_trades)
    decision, reasons = _decision(primary_metrics, variant_rows, config.template)
    return FundingBasisSmokeResult(
        adapter_id=ADAPTER_ID,
        mode=SUPPORTED_MODE,
        template_id=str(config.template.get("template_id") or SUPPORTED_MODE),
        variant_count=len(variant_rows),
        primary_variant=_variant_label(variants[0]) if variants else None,
        decision=decision,
        reasons=tuple(reasons),
        metrics=primary_metrics,
        variants=tuple(variant_rows),
        availability=availability,
        elapsed_seconds=round(time.perf_counter() - started, 6),
        primary_trades=tuple(primary_trades),
    )


def _build_availability(
    config: FundingBasisResearchConfig,
    spot_bars: Sequence[MarketBar],
    duplicate_count: int,
) -> tuple[FundingBasisAvailability, Mapping[str, Mapping[str, tuple[_FeatureObservation, ...]]]]:
    snapshot = inspect_derivatives_feature_snapshot_manifest(config.derivatives_feature_snapshot_manifest)
    if snapshot.status != "READY":
        return (
            FundingBasisAvailability(
                adapter_id=ADAPTER_ID,
                status="WAITING_FOR_MORE_DATA" if snapshot.status == "WAITING_FOR_MORE_DATA" else "DATA_MISSING",
                available=False,
                selected_timeframe=None,
                symbols=(),
                futures_to_spot={},
                spot_row_count=len(spot_bars),
                derivatives_feature_count=snapshot.feature_count,
                blockers=tuple(snapshot.blockers or (f"derivatives_snapshot_{snapshot.status.lower()}",)),
            ),
            {},
        )
    missing_features = REQUIRED_DERIVATIVES_FEATURES - set(snapshot.feature_ids)
    if missing_features or not snapshot.parity_ok:
        blockers = [*(f"derivatives_feature_missing:{item}" for item in sorted(missing_features))]
        if not snapshot.parity_ok:
            blockers.append("derivatives_feature_parity_failed")
        return (
            FundingBasisAvailability(
                adapter_id=ADAPTER_ID,
                status="DATA_MISSING",
                available=False,
                selected_timeframe=None,
                symbols=(),
                futures_to_spot={},
                spot_row_count=len(spot_bars),
                derivatives_feature_count=snapshot.feature_count,
                blockers=tuple(blockers),
            ),
            {},
        )
    manifest = _load_snapshot_manifest(config.derivatives_feature_snapshot_manifest)
    mappings = _validated_directional_mappings(manifest, requested_symbols=config.symbols[: config.max_symbols])
    observations = _load_feature_observations(manifest, mappings)
    futures_to_spot = {futures: spot for futures, spot in mappings.items() if futures in observations}
    selected_timeframe = _select_spot_timeframe(
        spot_bars,
        futures_to_spot.values(),
        config.timeframe_preference,
        min_rows=config.min_funding_observations,
    )
    selected_symbols = tuple(sorted(set(futures_to_spot.values())))
    blockers: list[str] = []
    if duplicate_count:
        blockers.append("spot_ohlcv_duplicates")
    if not selected_symbols:
        blockers.append("explicit_perpetual_to_spot_mapping_missing")
    if not selected_timeframe:
        blockers.append("spot_ohlcv_timeframe_missing")
    for futures_symbol, spot_symbol in futures_to_spot.items():
        funding_count = len(observations.get(futures_symbol, {}).get("funding_rate_relative", ()))
        basis_count = len(observations.get(futures_symbol, {}).get("basis_bps", ()))
        if funding_count < config.min_funding_observations or not basis_count:
            blockers.append(f"derivatives_history_insufficient:{spot_symbol}")
    return (
        FundingBasisAvailability(
            adapter_id=ADAPTER_ID,
            status="READY" if not blockers else "WAITING_FOR_MORE_DATA",
            available=not blockers,
            selected_timeframe=selected_timeframe,
            symbols=selected_symbols,
            futures_to_spot=futures_to_spot,
            spot_row_count=len(spot_bars),
            derivatives_feature_count=sum(
                len(rows) for features in observations.values() for rows in features.values()
            ),
            blockers=tuple(dict.fromkeys(blockers)),
            warnings=(
                "derivatives_context_is_directional_only; spot_eur_returns_are_calculated_without_usd_eur_price_conversion",
            ),
        ),
        observations,
    )


def _load_snapshot_manifest(path: Path) -> Mapping[str, Any]:
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("derivatives feature snapshot manifest must be an object")
    return payload


def _validated_directional_mappings(
    manifest: Mapping[str, Any],
    *,
    requested_symbols: Sequence[str],
) -> dict[str, str]:
    requested = {symbol.upper() for symbol in requested_symbols}
    mappings: dict[str, str] = {}
    for item in manifest.get("market_mappings") or ():
        if not isinstance(item, Mapping):
            continue
        futures_symbol = str(item.get("futures_symbol") or "").upper()
        base_asset = str(item.get("base_asset") or "").upper()
        quote_asset = str(item.get("quote_asset") or "").upper()
        spot_symbol = str(item.get("autobot_spot_symbol") or "").upper()
        if not futures_symbol or not base_asset or quote_asset != "USD" or not spot_symbol:
            continue
        if requested and spot_symbol not in requested:
            continue
        mappings[futures_symbol] = spot_symbol
    return mappings


def _load_feature_observations(
    manifest: Mapping[str, Any],
    mappings: Mapping[str, str],
) -> dict[str, dict[str, tuple[_FeatureObservation, ...]]]:
    accepted: dict[str, dict[str, list[_FeatureObservation]]] = defaultdict(lambda: defaultdict(list))
    for item in manifest.get("files") or ():
        if not isinstance(item, Mapping):
            continue
        path = Path(str(item.get("csv_path") or ""))
        futures_symbol = str(item.get("futures_symbol") or "").upper()
        if futures_symbol not in mappings or not path.exists():
            continue
        with path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                feature_id = str(row.get("feature_id") or "")
                if feature_id not in REQUIRED_DERIVATIVES_FEATURES or str(row.get("status") or "") != "READY":
                    continue
                try:
                    value = float(row.get("value") or "")
                    event_time = _parse_time(row.get("event_time"))
                    available_time = _parse_time(row.get("available_time"))
                except (TypeError, ValueError):
                    continue
                if not math.isfinite(value) or available_time < event_time:
                    continue
                accepted[futures_symbol][feature_id].append(
                    _FeatureObservation(
                        futures_symbol=futures_symbol,
                        feature_id=feature_id,
                        event_time=event_time,
                        available_time=available_time,
                        value=value,
                    )
                )
    return {
        futures: {
            feature_id: tuple(sorted(rows, key=lambda row: (row.available_time, row.event_time)))
            for feature_id, rows in by_feature.items()
        }
        for futures, by_feature in accepted.items()
    }


def _load_spot_bars(paths: Sequence[Path], *, max_rows: int) -> tuple[list[MarketBar], int]:
    rows: list[MarketBar] = []
    seen: set[tuple[str, str, datetime]] = set()
    duplicates = 0
    for path in _iter_csv_paths(paths):
        with path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                if len(rows) >= max_rows:
                    return sorted(rows, key=lambda item: (item.timeframe, item.symbol, item.timestamp)), duplicates
                try:
                    bar = MarketBar.from_mapping(
                        row,
                        default_symbol=_symbol_from_filename(path),
                        default_timeframe=_timeframe_from_filename(path),
                    )
                except ValueError:
                    continue
                key = bar.key()
                if key in seen:
                    duplicates += 1
                    continue
                seen.add(key)
                rows.append(bar)
    return sorted(rows, key=lambda item: (item.timeframe, item.symbol, item.timestamp)), duplicates


def _spot_groups(
    bars: Sequence[MarketBar],
    *,
    symbols: Sequence[str],
    timeframe: str,
) -> Mapping[str, tuple[MarketBar, ...]]:
    allowed = {symbol.upper() for symbol in symbols}
    grouped: dict[str, list[MarketBar]] = defaultdict(list)
    for bar in bars:
        if bar.symbol.upper() in allowed and bar.timeframe.lower() == timeframe:
            grouped[bar.symbol.upper()].append(bar)
    return {symbol: tuple(sorted(rows, key=lambda row: row.timestamp)) for symbol, rows in grouped.items()}


def _select_spot_timeframe(
    bars: Sequence[MarketBar],
    symbols: Iterable[str],
    preference: Sequence[str],
    *,
    min_rows: int,
) -> str | None:
    required = {symbol.upper() for symbol in symbols}
    for timeframe in preference:
        counts: Counter[str] = Counter(
            bar.symbol.upper()
            for bar in bars
            if bar.timeframe.lower() == timeframe and bar.symbol.upper() in required
        )
        present = {symbol for symbol, count in counts.items() if count >= min_rows}
        if required and present == required:
            return timeframe
    return None


def _simulate_variant(
    *,
    config: FundingBasisResearchConfig,
    bars_by_symbol: Mapping[str, Sequence[MarketBar]],
    observations: Mapping[str, Mapping[str, Sequence[_FeatureObservation]]],
    futures_to_spot: Mapping[str, str],
    timeframe: str,
    cost_config: ExecutionCostConfig,
    variant: Mapping[str, Any],
) -> list[FundingBasisTrade]:
    cost_bps = cost_config.round_trip_cost_estimate_bps()
    hold_bars = _hold_hours_to_bars(float(variant["max_hold_hours"]), timeframe)
    trades: list[FundingBasisTrade] = []
    for futures_symbol, spot_symbol in sorted(futures_to_spot.items()):
        bars = tuple(bars_by_symbol.get(spot_symbol, ()))
        funding = tuple(observations.get(futures_symbol, {}).get("funding_rate_relative", ()))
        basis = tuple(observations.get(futures_symbol, {}).get("basis_bps", ()))
        if len(bars) < hold_bars + 2 or len(funding) < config.min_funding_observations or not basis:
            continue
        cooldown_until = -1
        for index, signal_bar in enumerate(bars[:-hold_bars - 1]):
            if index <= cooldown_until:
                continue
            current_funding = _latest_available(funding, signal_bar.timestamp)
            current_basis = _latest_available(basis, signal_bar.timestamp)
            if current_funding is None or current_basis is None:
                continue
            funding_history = [
                item.value
                for item in funding
                if item.available_time <= signal_bar.timestamp
            ]
            if len(funding_history) < config.min_funding_observations:
                continue
            threshold = _percentile(funding_history, float(variant["funding_percentile"]))
            # This is a spot-only long hypothesis.  Both observations are
            # directional contexts; neither USD price level enters the PnL.
            if current_funding.value > threshold or current_basis.value > 0.0:
                continue
            entry = bars[index + 1]
            exit_bar = bars[index + 1 + hold_bars]
            gross_bps = _return_bps(entry.open, exit_bar.close)
            net_bps = gross_bps - cost_bps
            trades.append(
                FundingBasisTrade(
                    spot_symbol=spot_symbol,
                    futures_symbol=futures_symbol,
                    signal_at=signal_bar.timestamp,
                    opened_at=entry.timestamp,
                    closed_at=exit_bar.timestamp,
                    timeframe=timeframe,
                    variant_label=_variant_label(variant),
                    funding_rate_relative=round(current_funding.value, 10),
                    funding_percentile_threshold=round(threshold, 10),
                    basis_bps=round(current_basis.value, 6),
                    gross_bps=round(gross_bps, 6),
                    cost_bps=round(cost_bps, 6),
                    net_bps=round(net_bps, 6),
                    gross_pnl_eur=round(config.order_notional_eur * gross_bps / 10_000.0, 6),
                    net_pnl_eur=round(config.order_notional_eur * net_bps / 10_000.0, 6),
                    metadata={
                        "derivatives_context": "perpetual_usd_directional_only",
                        "spot_pnl_market": spot_symbol,
                        "implicit_usd_eur_price_conversion": False,
                        "funding_event_time": current_funding.event_time.isoformat(),
                        "funding_available_time": current_funding.available_time.isoformat(),
                        "basis_event_time": current_basis.event_time.isoformat(),
                        "basis_available_time": current_basis.available_time.isoformat(),
                        "anti_lookahead": "derivatives_available_before_signal; entry_uses_next_spot_bar",
                    },
                )
            )
            cooldown_until = index + hold_bars
    return trades


def _metrics(trades: Sequence[FundingBasisTrade]) -> FundingBasisMetrics:
    net = [trade.net_pnl_eur for trade in trades]
    gross = [trade.gross_pnl_eur for trade in trades]
    wins = [value for value in net if value > 0.0]
    losses = [value for value in net if value < 0.0]
    by_symbol_counts: Counter[str] = Counter()
    by_symbol_pnl: defaultdict[str, float] = defaultdict(float)
    by_period_counts: Counter[str] = Counter()
    by_period_pnl: defaultdict[str, float] = defaultdict(float)
    for trade in trades:
        by_symbol_counts[trade.spot_symbol] += 1
        by_symbol_pnl[trade.spot_symbol] += trade.net_pnl_eur
        period = trade.closed_at.date().isoformat()
        by_period_counts[period] += 1
        by_period_pnl[period] += trade.net_pnl_eur
    positive = [(symbol, value) for symbol, value in by_symbol_pnl.items() if value > 0.0]
    positive_total = sum(value for _, value in positive)
    top_symbol, top_value = max(positive, key=lambda item: item[1]) if positive else (None, 0.0)
    return FundingBasisMetrics(
        trade_count=len(trades),
        gross_pnl_eur=round(sum(gross), 6),
        net_pnl_eur=round(sum(net), 6),
        # A no-loss sample is not evidence of an infinite edge.  Keep PF
        # unknown until the sample contains a loss to avoid an optimistic gate.
        profit_factor_net=(sum(wins) / abs(sum(losses)) if losses else None),
        expectancy_net=(round(sum(net) / len(net), 6) if net else None),
        winrate_pct=(round(len(wins) / len(net) * 100.0, 6) if net else None),
        max_drawdown_eur=round(_max_drawdown(net), 6),
        total_cost_bps=round(sum(trade.cost_bps for trade in trades), 6),
        no_trade_baseline_eur=0.0,
        by_symbol={
            symbol: {
                "trade_count": by_symbol_counts[symbol],
                "net_pnl_eur": round(by_symbol_pnl[symbol], 6),
            }
            for symbol in sorted(by_symbol_counts)
        },
        by_period={
            period: {
                "trade_count": by_period_counts[period],
                "net_pnl_eur": round(by_period_pnl[period], 6),
            }
            for period in sorted(by_period_counts)
        },
        concentration={
            "top_positive_symbol": top_symbol,
            "top_positive_pnl_share": round(top_value / positive_total, 6) if positive_total else 0.0,
        },
    )


def _decision(
    metrics: FundingBasisMetrics,
    variants: Sequence[Mapping[str, Any]],
    template: Mapping[str, Any],
) -> tuple[str, list[str]]:
    minimum_sample_size = int(template.get("minimum_sample_size") or 30)
    reasons: list[str] = []
    if metrics.trade_count == 0:
        return "INSUFFICIENT_DATA", ["no_executable_funding_basis_trades"]
    if metrics.net_pnl_eur <= 0.0:
        reasons.append("edge_net_not_positive")
    if metrics.profit_factor_net is None or metrics.profit_factor_net <= 1.0:
        reasons.append("profit_factor_net_not_above_1")
    if metrics.expectancy_net is None or metrics.expectancy_net <= 0.0:
        reasons.append("expectancy_net_not_positive")
    if metrics.trade_count < minimum_sample_size:
        reasons.append("sample_size_below_template_minimum")
    if metrics.concentration.get("top_positive_pnl_share", 0.0) > 0.65:
        reasons.append("symbol_concentration_high")
    if all(int(dict(item.get("metrics") or {}).get("trade_count") or 0) == 0 for item in variants):
        reasons.append("all_variants_empty")
    if reasons:
        return "REJECT_FAST", reasons
    return "WALK_FORWARD_AVAILABLE", ["net_cost_smoke_requires_walk_forward_before_shadow_or_paper"]


def _bounded_variants(config: FundingBasisResearchConfig) -> Iterable[dict[str, Any]]:
    ranges = dict(config.template.get("allowed_parameter_ranges") or {})
    percentiles = ranges.get("funding_percentile") or [5]
    holds = ranges.get("max_hold_hours") or [24]
    for percentile, hold_hours in itertools.islice(itertools.product(percentiles, holds), config.max_variants):
        percentile_value = float(percentile)
        if not 0.0 < percentile_value <= 50.0:
            continue
        yield {
            "funding_percentile": percentile_value,
            "max_hold_hours": float(hold_hours),
        }


def _latest_available(rows: Sequence[_FeatureObservation], as_of: datetime) -> _FeatureObservation | None:
    available = [row for row in rows if row.available_time <= as_of]
    return available[-1] if available else None


def _percentile(values: Sequence[float], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("cannot calculate percentile of empty series")
    rank = (len(ordered) - 1) * percentile / 100.0
    lower = int(math.floor(rank))
    upper = int(math.ceil(rank))
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)


def _max_drawdown(pnl: Sequence[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for value in pnl:
        equity += value
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    return max_drawdown


def _hold_hours_to_bars(hours: float, timeframe: str) -> int:
    seconds = {"1h": 3600.0, "15m": 900.0}.get(timeframe)
    if seconds is None:
        raise ValueError(f"unsupported spot timeframe: {timeframe}")
    return max(1, int(math.ceil(hours * 3600.0 / seconds)))


def _return_bps(entry_price: float, exit_price: float) -> float:
    if entry_price <= 0.0 or exit_price <= 0.0:
        raise ValueError("spot prices must be positive")
    return ((exit_price / entry_price) - 1.0) * 10_000.0


def _variant_label(variant: Mapping[str, Any]) -> str:
    return f"funding_p{float(variant['funding_percentile']):g}_hold{float(variant['max_hold_hours']):g}h"


def _parse_time(value: Any) -> datetime:
    text = str(value or "").replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("feature timestamp must be timezone-aware")
    return parsed


def _iter_csv_paths(paths: Sequence[Path]) -> Iterable[Path]:
    for path in paths:
        if path.is_dir():
            yield from sorted(path.rglob("*.csv"))
        elif path.suffix.lower() == ".csv" and path.exists():
            yield path


def _symbol_from_filename(path: Path) -> str:
    return path.stem.split("_")[0].upper()


def _timeframe_from_filename(path: Path) -> str:
    for part in reversed(path.stem.split("_")):
        if part.lower() in {"1h", "15m"}:
            return part.lower()
    return "unknown"
