"""Research-only long-only relative-value replay for Kraken Spot OHLCV.

This module deliberately has no dependency on the AUTOBOT runtime, router,
paper executor, or Kraken private API.  A reference asset is statistical input
only: every generated trade is a spot BUY followed by a spot SELL of the target
symbol.  It cannot open a short, use margin, submit an order, or promote a
strategy.

The signal is intentionally simple and reproducible:

* rolling log-price OLS hedge ratio against one reference or a small basket;
* rolling return correlation and an optional Engle-Granger p-value;
* a negative residual z-score identifies a potentially under-valued target;
* a portfolio replay applies RiskManagerV2, ExecutionCostModel, TradeJournal,
  and MetricsEngine before producing a research-only verdict.
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Iterable, Sequence

from autobot.v2.risk.risk_manager_v2 import (
    RiskManagerV2,
    RiskManagerV2Config,
    RiskPortfolioState,
    RiskTradeRequest,
)

from .execution_cost_model import (
    ExecutionCostConfig,
    ExecutionCostModel,
    FillRequest,
    execution_cost_config_for_profile,
)
from .market_data_repository import MarketBar, MarketDataRepository
from .metrics_engine import MetricsEngine
from .symbol_normalization import normalize_research_symbol
from .trade_journal import TradeJournal, TradeRecord


DEFAULT_RELATIONSHIPS: tuple["RelativeValueRelation", ...] = ()


@dataclass(frozen=True)
class RelativeValueRelation:
    """A long-only target and one or more reference symbols.

    The target is the sole tradable asset.  References must never be placed in
    an order request by this module.
    """

    target_symbol: str
    reference_symbols: tuple[str, ...]

    def __post_init__(self) -> None:
        target = normalize_research_symbol(self.target_symbol)
        references = tuple(
            symbol
            for symbol in (normalize_research_symbol(value) for value in self.reference_symbols)
            if symbol
        )
        if not target:
            raise ValueError("target_symbol is required")
        if not references:
            raise ValueError("reference_symbols must not be empty")
        if target in references:
            raise ValueError("target_symbol cannot also be a reference")
        object.__setattr__(self, "target_symbol", target)
        object.__setattr__(self, "reference_symbols", tuple(dict.fromkeys(references)))

    @property
    def relationship_id(self) -> str:
        return f"{self.target_symbol}_vs_{'_'.join(self.reference_symbols)}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "relationship_id": self.relationship_id,
            "target_symbol": self.target_symbol,
            "reference_symbols": list(self.reference_symbols),
            "execution": "long_only_target_spot_buy",
        }


DEFAULT_RELATIONSHIPS = (
    RelativeValueRelation("ADAEUR", ("XRPZEUR",)),
    RelativeValueRelation("XLMEUR", ("TRXEUR",)),
    RelativeValueRelation("LINKEUR", ("DOTEUR",)),
    RelativeValueRelation("AVAXEUR", ("SOLEUR",)),
)


def parse_relationships(value: str | None) -> tuple[RelativeValueRelation, ...]:
    """Parse ``TARGET:REF`` or ``TARGET:REF1|REF2`` relationship definitions."""

    if value is None or not value.strip():
        return DEFAULT_RELATIONSHIPS
    parsed: list[RelativeValueRelation] = []
    for raw_relationship in value.split(","):
        raw_relationship = raw_relationship.strip()
        if not raw_relationship:
            continue
        target, separator, references = raw_relationship.partition(":")
        if not separator:
            raise ValueError(
                "relationships must use TARGET:REFERENCE or TARGET:REFERENCE1|REFERENCE2"
            )
        parsed.append(
            RelativeValueRelation(
                target_symbol=target.strip(),
                reference_symbols=tuple(item.strip() for item in references.split("|") if item.strip()),
            )
        )
    if not parsed:
        raise ValueError("at least one relative-value relationship is required")
    relationship_ids = [item.relationship_id for item in parsed]
    if len(relationship_ids) != len(set(relationship_ids)):
        raise ValueError("duplicate relative-value relationship")
    return tuple(parsed)


@dataclass(frozen=True)
class RelativeValueConfig:
    run_id: str
    data_paths: tuple[Path, ...]
    output_dir: Path = Path("reports/research/relative_value")
    relationships: tuple[RelativeValueRelation, ...] = DEFAULT_RELATIONSHIPS
    timeframe: str = "15m"
    rolling_window_bars: int = 96
    entry_zscore: float = -2.0
    exit_zscore: float = -0.25
    min_correlation: float = 0.50
    max_cointegration_pvalue: float = 0.10
    require_cointegration_when_available: bool = True
    cointegration_refresh_bars: int = 24
    min_expected_move_bps: float = 150.0
    min_expected_mfe_to_cost: float = 1.5
    fixed_take_profit_bps: float = 400.0
    fixed_stop_loss_bps: float = 200.0
    trailing_activation_bps: float = 200.0
    trailing_distance_bps: float = 125.0
    max_hold_bars: int = 96
    initial_capital_eur: float = 500.0
    max_position_fraction: float = 0.20
    risk_per_trade_pct: float = 0.01
    max_global_exposure_pct: float = 0.60
    max_open_positions: int = 3
    cooldown_hours: float = 6.0
    max_daily_loss_pct: float = 0.03
    max_drawdown_pct: float = 0.10
    min_order_notional_eur: float = 5.0
    max_volatility_bps: float = 600.0
    cost_profiles: tuple[str, ...] = ("paper_current_taker", "research_stress")
    comparison_high_conviction_report_path: Path | None = None

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id must not be empty")
        if not self.data_paths:
            raise ValueError("data_paths must not be empty")
        if not self.relationships:
            raise ValueError("relationships must not be empty")
        if self.rolling_window_bars < 20:
            raise ValueError("rolling_window_bars must be at least 20")
        if self.max_hold_bars < 1 or self.cointegration_refresh_bars < 1:
            raise ValueError("bar counts must be positive")
        if not self.entry_zscore < self.exit_zscore < 0.0:
            raise ValueError("entry_zscore must be below exit_zscore, both negative")
        for name, value in {
            "min_correlation": self.min_correlation,
            "max_cointegration_pvalue": self.max_cointegration_pvalue,
            "risk_per_trade_pct": self.risk_per_trade_pct,
            "max_position_fraction": self.max_position_fraction,
            "max_global_exposure_pct": self.max_global_exposure_pct,
            "max_daily_loss_pct": self.max_daily_loss_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
        }.items():
            if not math.isfinite(float(value)) or not 0.0 < float(value) <= 1.0:
                raise ValueError(f"{name} must be in (0, 1]")
        for name, value in {
            "min_expected_move_bps": self.min_expected_move_bps,
            "min_expected_mfe_to_cost": self.min_expected_mfe_to_cost,
            "fixed_take_profit_bps": self.fixed_take_profit_bps,
            "fixed_stop_loss_bps": self.fixed_stop_loss_bps,
            "trailing_activation_bps": self.trailing_activation_bps,
            "trailing_distance_bps": self.trailing_distance_bps,
            "initial_capital_eur": self.initial_capital_eur,
            "cooldown_hours": self.cooldown_hours,
            "min_order_notional_eur": self.min_order_notional_eur,
            "max_volatility_bps": self.max_volatility_bps,
        }.items():
            if not math.isfinite(float(value)) or float(value) <= 0.0:
                raise ValueError(f"{name} must be positive and finite")
        if self.max_open_positions < 1:
            raise ValueError("max_open_positions must be positive")
        if not self.cost_profiles:
            raise ValueError("cost_profiles must not be empty")
        for profile in self.cost_profiles:
            execution_cost_config_for_profile(profile).validate()


@dataclass(frozen=True)
class RelativeValueSignal:
    signal_id: str
    relationship_id: str
    target_symbol: str
    reference_symbols: tuple[str, ...]
    side: str
    detected_at: datetime
    entry_at: datetime
    entry_index: int
    entry_price: float
    zscore: float
    correlation: float
    hedge_ratio: float
    intercept: float
    cointegration_pvalue: float | None
    expected_move_bps: float
    stop_loss_bps: float
    take_profit_bps: float
    volatility_bps: float

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["detected_at"] = self.detected_at.isoformat()
        data["entry_at"] = self.entry_at.isoformat()
        data["reference_symbols"] = list(self.reference_symbols)
        data["reference_execution"] = "none"
        return data


@dataclass(frozen=True)
class RelativeValueOutcome:
    signal: RelativeValueSignal
    exit_at: datetime
    exit_price: float
    exit_reason: str
    gross_return_bps: float
    mfe_bps: float
    mae_bps: float
    exit_index: int
    entry_liquidity_eur: float | None
    exit_liquidity_eur: float | None


@dataclass(frozen=True)
class RelativeValuePortfolioResult:
    cost_profile: str
    cost_config: dict[str, Any]
    relationship_count: int
    raw_signal_count: int
    accepted_trade_count: int
    net_pnl_eur: float
    final_equity_eur: float
    total_return_pct: float
    profit_factor: float | None
    winrate_pct: float | None
    expectancy_eur: float | None
    max_drawdown_pct: float
    average_cost_eur: float | None
    average_trade_duration_minutes: float | None
    exit_reason_count: dict[str, int]
    pnl_by_relationship: dict[str, dict[str, Any]]
    pnl_by_symbol: dict[str, dict[str, Any]]
    rejection_count: dict[str, int]
    max_open_positions_seen: int
    max_planned_exposure_pct: float
    status: str
    blockers: tuple[str, ...]
    records: tuple[TradeRecord, ...] = field(repr=False)
    live_promotion_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("records", None)
        payload["blockers"] = list(self.blockers)
        return payload


@dataclass(frozen=True)
class RelativeValueReport:
    run_id: str
    generated_at: str
    data_paths: tuple[str, ...]
    relationships: tuple[dict[str, Any], ...]
    timeframe: str
    statsmodels_available: bool
    signal_rejections: dict[str, int]
    signal_count: int
    portfolio_results: tuple[RelativeValuePortfolioResult, ...]
    comparison_high_conviction: dict[str, Any]
    conclusion: str
    recommendations: tuple[str, ...]
    validation: dict[str, Any]
    artifacts: dict[str, str] = field(default_factory=dict)
    live_promotion_allowed: bool = False
    safety_notes: tuple[str, ...] = (
        "Research-only; no runtime router or paper/live executor is imported.",
        "Kraken Spot long-only proxy: BUY/SELL target symbol only; references are never traded.",
        "No leverage, margin, auto-promotion, instance split, or Kraken order is possible.",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "data_paths": list(self.data_paths),
            "relationships": [dict(item) for item in self.relationships],
            "timeframe": self.timeframe,
            "statsmodels_available": self.statsmodels_available,
            "signal_rejections": dict(self.signal_rejections),
            "signal_count": self.signal_count,
            "portfolio_results": [result.to_dict() for result in self.portfolio_results],
            "comparison_high_conviction": dict(self.comparison_high_conviction),
            "conclusion": self.conclusion,
            "recommendations": list(self.recommendations),
            "validation": dict(self.validation),
            "artifacts": dict(self.artifacts),
            "live_promotion_allowed": self.live_promotion_allowed,
            "safety_notes": list(self.safety_notes),
        }


@dataclass(frozen=True)
class _RelationSeries:
    relation: RelativeValueRelation
    timestamps: tuple[datetime, ...]
    target_bars: tuple[MarketBar, ...]
    reference_log_prices: tuple[float, ...]


@dataclass(frozen=True)
class _Candidate:
    outcome: RelativeValueOutcome
    series: _RelationSeries

    @property
    def signal(self) -> RelativeValueSignal:
        return self.outcome.signal

    @property
    def selection_score(self) -> tuple[float, float, float, str]:
        return (
            abs(self.signal.zscore),
            self.signal.expected_move_bps,
            self.signal.correlation,
            self.signal.relationship_id,
        )


@dataclass
class _OpenPosition:
    candidate: _Candidate
    notional_eur: float
    quantity: float
    entry_cost_eur: float
    estimated_exit_cost_eur: float


def build_relative_value_report(config: RelativeValueConfig) -> RelativeValueReport:
    """Run only deterministic historical research; never touch AUTOBOT runtime state."""

    bars = _load_ohlcv(config.data_paths)
    groups = _group_by_symbol_timeframe(bars)
    series = tuple(
        value
        for relation in config.relationships
        if (value := _build_relation_series(relation, groups, config.timeframe)) is not None
    )
    signals, signal_rejections, statsmodels_available = _discover_signals(config, series)
    candidates = tuple(
        candidate
        for series_item in series
        for signal in signals
        if signal.relationship_id == series_item.relation.relationship_id
        if (candidate := _candidate_for_signal(config, signal, series_item)) is not None
    )
    candidates = tuple(sorted(candidates, key=lambda item: (item.signal.entry_at, item.signal.target_symbol)))
    results = tuple(
        _run_portfolio(config, candidates, profile)
        for profile in config.cost_profiles
    )
    comparison = _high_conviction_comparison(config.comparison_high_conviction_report_path, results)
    validation = _validation_summary(results)
    conclusion, recommendations = _conclusion(results, validation, statsmodels_available)
    return RelativeValueReport(
        run_id=config.run_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        data_paths=tuple(str(path) for path in config.data_paths),
        relationships=tuple(item.to_dict() for item in config.relationships),
        timeframe=config.timeframe,
        statsmodels_available=statsmodels_available,
        signal_rejections=dict(sorted(signal_rejections.items())),
        signal_count=len(signals),
        portfolio_results=results,
        comparison_high_conviction=comparison,
        conclusion=conclusion,
        recommendations=recommendations,
        validation=validation,
    )


def write_relative_value_report(report: RelativeValueReport, output_dir: str | Path) -> RelativeValueReport:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, str] = {}
    for result in report.portfolio_results:
        journal = TradeJournal(result.records)
        stem = f"{report.run_id}_{result.cost_profile}_trade_journal"
        artifacts[f"{result.cost_profile}_journal_json"] = str(journal.to_json(output / f"{stem}.json"))
        artifacts[f"{result.cost_profile}_journal_csv"] = str(journal.to_csv(output / f"{stem}.csv"))
    final_report = replace(report, artifacts=artifacts)
    json_path = output / f"{report.run_id}.json"
    markdown_path = output / f"{report.run_id}.md"
    json_path.write_text(json.dumps(final_report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(render_relative_value_report(final_report), encoding="utf-8")
    return replace(final_report, artifacts={**artifacts, "json_report": str(json_path), "markdown_report": str(markdown_path)})


def render_relative_value_report(report: RelativeValueReport) -> str:
    lines = [
        f"# Relative Value / Statistical Arbitrage Research - {report.run_id}",
        "",
        "## Scope",
        "",
        "- Venue: `Kraken Spot OHLCV research data`.",
        "- Direction: `long_only`; only the target symbol is bought and sold.",
        "- References: statistical only; no reference short or hedge order exists.",
        "- Mode: `research_only`; no runtime, paper, live, or promotion mutation.",
        f"- Timeframe: `{report.timeframe}`.",
        f"- Signals found: `{report.signal_count}`.",
        f"- statsmodels / Engle-Granger available: `{report.statsmodels_available}`.",
        "",
        "## Relationships",
        "",
        "| Target (BUY only) | Reference basket (not traded) |",
        "| --- | --- |",
    ]
    for relation in report.relationships:
        lines.append(
            f"| {relation['target_symbol']} | {', '.join(relation['reference_symbols'])} |"
        )
    lines.extend(["", "## Portfolio Results", ""])
    lines.extend([
        "| Cost profile | Trades | Net PnL EUR | Final equity EUR | PF | Winrate % | Max DD % | Avg cost EUR | Status |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ])
    for result in report.portfolio_results:
        lines.append(
            f"| {result.cost_profile} | {result.accepted_trade_count} | {_fmt(result.net_pnl_eur)} | "
            f"{_fmt(result.final_equity_eur)} | {_fmt(result.profit_factor)} | {_fmt(result.winrate_pct)} | "
            f"{_fmt(result.max_drawdown_pct)} | {_fmt(result.average_cost_eur)} | {result.status} |"
        )
    for result in report.portfolio_results:
        lines.extend(["", f"## {result.cost_profile} Attribution", ""])
        lines.extend(["| Relationship | Trades | Net PnL EUR |", "| --- | ---: | ---: |"])
        for relation, row in sorted(result.pnl_by_relationship.items()):
            lines.append(f"| {relation} | {row['trade_count']} | {_fmt(row['net_pnl_eur'])} |")
        lines.extend(["", "| Symbol | Trades | Net PnL EUR |", "| --- | ---: | ---: |"])
        for symbol, row in sorted(result.pnl_by_symbol.items()):
            lines.append(f"| {symbol} | {row['trade_count']} | {_fmt(row['net_pnl_eur'])} |")
        lines.append("")
        lines.append(f"- exit_reason_count: `{result.exit_reason_count}`")
        lines.append(f"- rejected_entries: `{result.rejection_count}`")
        lines.append(f"- blockers: `{list(result.blockers)}`")
    lines.extend(["", "## High Conviction Comparison", ""])
    for key, value in report.comparison_high_conviction.items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Validation", ""])
    for key, value in report.validation.items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Signal Rejections", ""])
    for reason, count in report.signal_rejections.items():
        lines.append(f"- {reason}: `{count}`")
    lines.extend(["", "## Conclusion", "", f"`{report.conclusion}`", "", "## Recommendations", ""])
    lines.extend(f"- {item}" for item in report.recommendations)
    lines.extend(["", "## Safety", ""])
    lines.extend(f"- {item}" for item in report.safety_notes)
    lines.append(f"- live_promotion_allowed: `{report.live_promotion_allowed}`")
    return "\n".join(lines) + "\n"


def _load_ohlcv(paths: Sequence[Path]) -> list[MarketBar]:
    repository = MarketDataRepository()
    bars: list[MarketBar] = []
    for path in _expand_paths(paths):
        if path.suffix.lower() == ".csv":
            loaded = repository.load_csv(path)
        elif path.suffix.lower() == ".parquet":
            loaded = repository.load_parquet(path)
        else:
            continue
        bars.extend(loaded)
    normalized = repository.normalize(
        replace(bar, symbol=normalize_research_symbol(bar.symbol) or bar.symbol.upper())
        for bar in bars
    )
    if not normalized:
        raise ValueError("no OHLCV bars found for relative-value research")
    return normalized


def _expand_paths(paths: Sequence[Path]) -> list[Path]:
    expanded: list[Path] = []
    for path in paths:
        if path.is_dir():
            expanded.extend(sorted(item for item in path.rglob("*") if item.suffix.lower() in {".csv", ".parquet"}))
        elif path.exists():
            expanded.append(path)
    return list(dict.fromkeys(expanded))


def _group_by_symbol_timeframe(bars: Iterable[MarketBar]) -> dict[tuple[str, str], list[MarketBar]]:
    groups: dict[tuple[str, str], list[MarketBar]] = defaultdict(list)
    for bar in bars:
        groups[(bar.symbol, bar.timeframe.lower())].append(bar)
    return {key: sorted(rows, key=lambda item: item.timestamp) for key, rows in groups.items()}


def _build_relation_series(
    relation: RelativeValueRelation,
    groups: dict[tuple[str, str], list[MarketBar]],
    timeframe: str,
) -> _RelationSeries | None:
    target = {bar.timestamp: bar for bar in groups.get((relation.target_symbol, timeframe.lower()), [])}
    references = [
        {bar.timestamp: bar for bar in groups.get((symbol, timeframe.lower()), [])}
        for symbol in relation.reference_symbols
    ]
    if not target or any(not values for values in references):
        return None
    timestamps = tuple(sorted(set(target).intersection(*(set(values) for values in references))))
    if len(timestamps) < 3:
        return None
    target_bars = tuple(target[item] for item in timestamps)
    reference_log_prices = tuple(
        mean(math.log(max(references[index][timestamp].close, 1e-12)) for index in range(len(references)))
        for timestamp in timestamps
    )
    return _RelationSeries(relation, timestamps, target_bars, reference_log_prices)


def _discover_signals(
    config: RelativeValueConfig,
    series_items: Sequence[_RelationSeries],
) -> tuple[tuple[RelativeValueSignal, ...], Counter[str], bool]:
    signals: list[RelativeValueSignal] = []
    rejected: Counter[str] = Counter()
    statsmodels_available = _statsmodels_available()
    for series in series_items:
        for index in range(config.rolling_window_bars, len(series.timestamps) - 1):
            metrics = _relation_metrics(series, index, config.rolling_window_bars)
            if metrics is None:
                rejected["insufficient_relation_history"] += 1
                continue
            zscore, correlation, beta, intercept, residual_std, volatility_bps = metrics
            if correlation < config.min_correlation:
                rejected["correlation_below_threshold"] += 1
                continue
            if zscore > config.entry_zscore:
                continue
            pvalue = _cointegration_pvalue(series, index, config.rolling_window_bars) if statsmodels_available else None
            if (
                config.require_cointegration_when_available
                and pvalue is not None
                and pvalue > config.max_cointegration_pvalue
            ):
                rejected["cointegration_pvalue_above_threshold"] += 1
                continue
            entry_bar = series.target_bars[index + 1]
            expected_move_bps = abs(zscore) * residual_std * 10_000.0
            signal = RelativeValueSignal(
                signal_id=f"relative_value:{series.relation.relationship_id}:{entry_bar.timestamp.isoformat()}",
                relationship_id=series.relation.relationship_id,
                target_symbol=series.relation.target_symbol,
                reference_symbols=series.relation.reference_symbols,
                side="buy",
                detected_at=series.timestamps[index],
                entry_at=entry_bar.timestamp,
                entry_index=index + 1,
                entry_price=float(entry_bar.open),
                zscore=round(zscore, 8),
                correlation=round(correlation, 8),
                hedge_ratio=round(beta, 8),
                intercept=round(intercept, 8),
                cointegration_pvalue=round(pvalue, 8) if pvalue is not None else None,
                expected_move_bps=round(expected_move_bps, 6),
                stop_loss_bps=config.fixed_stop_loss_bps,
                take_profit_bps=config.fixed_take_profit_bps,
                volatility_bps=round(volatility_bps, 6),
            )
            signals.append(signal)
    return tuple(sorted(signals, key=lambda item: (item.entry_at, item.target_symbol))), rejected, statsmodels_available


def _relation_metrics(
    series: _RelationSeries,
    index: int,
    window: int,
) -> tuple[float, float, float, float, float, float] | None:
    start = index - window + 1
    if start < 0:
        return None
    target_logs = [math.log(max(item.close, 1e-12)) for item in series.target_bars[start : index + 1]]
    references = list(series.reference_log_prices[start : index + 1])
    beta, intercept = _ols(target_logs, references)
    residuals = [target - (intercept + beta * reference) for target, reference in zip(target_logs, references)]
    residual_std = pstdev(residuals) if len(residuals) > 1 else 0.0
    if residual_std <= 1e-12:
        return None
    zscore = (residuals[-1] - mean(residuals)) / residual_std
    target_returns = [target_logs[item] - target_logs[item - 1] for item in range(1, len(target_logs))]
    reference_returns = [references[item] - references[item - 1] for item in range(1, len(references))]
    correlation = _correlation(target_returns, reference_returns)
    volatility_bps = (pstdev(target_returns) * 10_000.0) if len(target_returns) > 1 else 0.0
    return zscore, correlation, beta, intercept, residual_std, volatility_bps


def _ols(target_values: Sequence[float], reference_values: Sequence[float]) -> tuple[float, float]:
    if len(target_values) != len(reference_values) or len(target_values) < 2:
        return 0.0, 0.0
    ref_mean = mean(reference_values)
    target_mean = mean(target_values)
    variance = sum((value - ref_mean) ** 2 for value in reference_values)
    if variance <= 1e-18:
        return 0.0, target_mean
    covariance = sum(
        (reference - ref_mean) * (target - target_mean)
        for target, reference in zip(target_values, reference_values)
    )
    beta = covariance / variance
    return beta, target_mean - beta * ref_mean


def _correlation(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or len(left) < 2:
        return 0.0
    left_std = pstdev(left)
    right_std = pstdev(right)
    if left_std <= 1e-18 or right_std <= 1e-18:
        return 0.0
    left_mean = mean(left)
    right_mean = mean(right)
    covariance = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right)) / len(left)
    return covariance / (left_std * right_std)


def _statsmodels_available() -> bool:
    try:
        from statsmodels.tsa.stattools import coint  # type: ignore # noqa: F401
    except Exception:
        return False
    return True


def _cointegration_pvalue(series: _RelationSeries, index: int, window: int) -> float | None:
    try:
        from statsmodels.tsa.stattools import coint  # type: ignore
    except Exception:
        return None
    start = index - window + 1
    target = [math.log(max(item.close, 1e-12)) for item in series.target_bars[start : index + 1]]
    reference = list(series.reference_log_prices[start : index + 1])
    try:
        _stat, pvalue, _critical = coint(target, reference)
    except Exception:
        return None
    return float(pvalue) if math.isfinite(float(pvalue)) else None


def _candidate_for_signal(
    config: RelativeValueConfig,
    signal: RelativeValueSignal,
    series: _RelationSeries,
) -> _Candidate | None:
    outcome = _simulate_outcome(config, signal, series)
    return _Candidate(outcome=outcome, series=series) if outcome else None


def _simulate_outcome(
    config: RelativeValueConfig,
    signal: RelativeValueSignal,
    series: _RelationSeries,
) -> RelativeValueOutcome | None:
    entry = signal.entry_price
    if entry <= 0.0:
        return None
    last_index = min(len(series.target_bars) - 1, signal.entry_index + config.max_hold_bars)
    if last_index <= signal.entry_index + 1:
        return None
    stop_price = entry * (1.0 - signal.stop_loss_bps / 10_000.0)
    take_profit_price = entry * (1.0 + signal.take_profit_bps / 10_000.0)
    peak_bps = -math.inf
    trough_bps = math.inf
    trailing_active = False
    trailing_peak_bps = -math.inf
    exit_bar = series.target_bars[last_index]
    exit_price = float(exit_bar.close)
    exit_reason = "time_stop"
    # The signal is observed on the prior bar and the position enters at this
    # bar's open. Start exit evaluation on the following bar to avoid using the
    # entry candle's completed high/low/close as if it were known at entry.
    for index in range(signal.entry_index + 1, last_index + 1):
        bar = series.target_bars[index]
        high_bps = _return_bps(entry, bar.high)
        low_bps = _return_bps(entry, bar.low)
        peak_bps = max(peak_bps, high_bps)
        trough_bps = min(trough_bps, low_bps)
        # A bar that reaches both levels is treated conservatively as stop first.
        if bar.low <= stop_price:
            exit_bar, exit_price, exit_reason = bar, stop_price, "fixed_stop_loss"
            break
        if bar.high >= take_profit_price:
            exit_bar, exit_price, exit_reason = bar, take_profit_price, "fixed_take_profit"
            break
        if high_bps >= config.trailing_activation_bps:
            trailing_active = True
            trailing_peak_bps = max(trailing_peak_bps, high_bps)
        if trailing_active:
            trailing_peak_bps = max(trailing_peak_bps, high_bps)
            trail_bps = trailing_peak_bps - config.trailing_distance_bps
            if low_bps <= trail_bps:
                exit_bar = bar
                exit_price = entry * (1.0 + trail_bps / 10_000.0)
                exit_reason = "trailing_stop"
                break
        metrics = _relation_metrics(series, index, config.rolling_window_bars)
        if metrics is not None:
            zscore, correlation, _beta, _intercept, _std, _volatility = metrics
            if zscore >= config.exit_zscore:
                exit_bar, exit_price, exit_reason = bar, float(bar.close), "zscore_mean_reversion"
                break
            if correlation < config.min_correlation:
                exit_bar, exit_price, exit_reason = bar, float(bar.close), "relationship_invalidated"
                break
            if (
                _statsmodels_available()
                and index % config.cointegration_refresh_bars == 0
                and config.require_cointegration_when_available
            ):
                pvalue = _cointegration_pvalue(series, index, config.rolling_window_bars)
                if pvalue is not None and pvalue > config.max_cointegration_pvalue:
                    exit_bar, exit_price, exit_reason = bar, float(bar.close), "relationship_invalidated"
                    break
    entry_liquidity = _liquidity_eur(series.target_bars[signal.entry_index])
    exit_liquidity = _liquidity_eur(exit_bar)
    return RelativeValueOutcome(
        signal=signal,
        exit_at=exit_bar.timestamp,
        exit_price=float(exit_price),
        exit_reason=exit_reason,
        gross_return_bps=round(_return_bps(entry, exit_price), 6),
        mfe_bps=round(peak_bps if math.isfinite(peak_bps) else 0.0, 6),
        mae_bps=round(trough_bps if math.isfinite(trough_bps) else 0.0, 6),
        exit_index=series.target_bars.index(exit_bar),
        entry_liquidity_eur=entry_liquidity,
        exit_liquidity_eur=exit_liquidity,
    )


def _run_portfolio(
    config: RelativeValueConfig,
    candidates: Sequence[_Candidate],
    cost_profile: str,
) -> RelativeValuePortfolioResult:
    cost_config = execution_cost_config_for_profile(cost_profile)
    cost_model = ExecutionCostModel(cost_config)
    risk_manager = RiskManagerV2(
        RiskManagerV2Config(
            default_risk_per_trade_pct=config.risk_per_trade_pct,
            max_risk_per_trade_pct=config.risk_per_trade_pct,
            max_symbol_exposure_pct=config.max_position_fraction,
            max_global_exposure_pct=config.max_global_exposure_pct,
            max_order_notional_pct=config.max_position_fraction,
            max_open_trades=config.max_open_positions,
            max_daily_loss_pct=config.max_daily_loss_pct,
            max_drawdown_pct=config.max_drawdown_pct,
            min_order_notional_eur=max(config.min_order_notional_eur, cost_config.min_notional_eur),
            max_spread_bps=cost_config.max_spread_bps,
            max_volatility_bps=config.max_volatility_bps,
            min_data_points=config.rolling_window_bars,
            allow_leverage=False,
            max_leverage=1.0,
            kelly_enabled=False,
            live_human_approved=False,
        )
    )
    candidates_by_entry: dict[datetime, list[_Candidate]] = defaultdict(list)
    timeline: set[datetime] = set()
    for candidate in candidates:
        candidates_by_entry[candidate.signal.entry_at].append(candidate)
        timeline.add(candidate.signal.entry_at)
        timeline.add(candidate.outcome.exit_at)
        # Mark every 15m bar while positions are open. Sizing still uses only
        # realized equity, but drawdown must not ignore adverse movement between
        # the discrete entry and exit events.
        timeline.update(candidate.series.timestamps)
    cash = float(config.initial_capital_eur)
    realized_equity = cash
    peak_marked_equity = cash
    max_drawdown_pct = 0.0
    open_positions: list[_OpenPosition] = []
    cooldown_until: dict[str, datetime] = {}
    records: list[TradeRecord] = []
    rejections: Counter[str] = Counter()
    exit_reasons: Counter[str] = Counter()
    daily_pnl: dict[date, float] = defaultdict(float)
    consecutive_losses = 0
    peak_realized_equity = realized_equity
    max_open_seen = 0
    max_planned_exposure_pct = 0.0
    blocked_by_drawdown = False

    for current_time in sorted(timeline):
        remaining: list[_OpenPosition] = []
        for position in open_positions:
            if position.candidate.outcome.exit_at > current_time:
                remaining.append(position)
                continue
            record = _close_position(config.run_id, position, cost_model)
            raw_exit_proceeds = record.quantity * position.candidate.outcome.exit_price
            exit_cost = record.fees_eur + record.spread_cost_eur + record.slippage_eur + record.latency_cost_eur - position.entry_cost_eur
            cash += raw_exit_proceeds - max(0.0, exit_cost)
            realized_equity += record.net_pnl_eur
            peak_realized_equity = max(peak_realized_equity, realized_equity)
            records.append(record)
            exit_reasons[record.exit_reason] += 1
            daily_pnl[record.closed_at.date()] += record.net_pnl_eur
            consecutive_losses = consecutive_losses + 1 if record.net_pnl_eur < 0.0 else 0
            cooldown_until[record.symbol] = record.closed_at + timedelta(hours=config.cooldown_hours)
        open_positions = remaining

        marked_equity = _marked_equity(cash, open_positions, current_time, cost_config)
        peak_marked_equity = max(peak_marked_equity, marked_equity)
        if peak_marked_equity > 0.0:
            max_drawdown_pct = max(max_drawdown_pct, (peak_marked_equity - marked_equity) / peak_marked_equity * 100.0)
        if max_drawdown_pct >= config.max_drawdown_pct * 100.0:
            blocked_by_drawdown = True

        for candidate in sorted(candidates_by_entry.get(current_time, []), key=lambda item: item.selection_score, reverse=True):
            signal = candidate.signal
            if blocked_by_drawdown:
                rejections["portfolio_drawdown_stop"] += 1
                continue
            if any(position.candidate.signal.target_symbol == signal.target_symbol for position in open_positions):
                rejections["one_position_per_symbol"] += 1
                continue
            if cooldown_until.get(signal.target_symbol, datetime.min.replace(tzinfo=timezone.utc)) > current_time:
                rejections["symbol_cooldown"] += 1
                continue
            if not _passes_cost_guard(signal, cost_config, config):
                rejections["cost_guard_expected_mfe_below_cost"] += 1
                continue
            current_day = current_time.date()
            risk_state = RiskPortfolioState(
                equity_eur=max(realized_equity, cost_config.min_notional_eur),
                available_cash_eur=max(cash, 0.0),
                open_trade_count=len(open_positions),
                global_exposure_eur=sum(position.notional_eur for position in open_positions),
                symbol_exposure_eur=0.0,
                daily_realized_pnl_eur=daily_pnl[current_day],
                peak_equity_eur=peak_realized_equity,
                consecutive_losses=consecutive_losses,
                validated_trade_count=0,
                spread_bps=cost_config.fallback_spread_bps,
                volatility_bps=signal.volatility_bps,
                data_points=signal.entry_index,
            )
            requested_notional = realized_equity * config.max_position_fraction
            request = RiskTradeRequest(
                strategy_id="relative_value_long_only",
                symbol=signal.target_symbol,
                side="buy",
                entry_price=signal.entry_price,
                stop_loss_price=signal.entry_price * (1.0 - signal.stop_loss_bps / 10_000.0),
                requested_notional_eur=requested_notional,
                requested_risk_pct=config.risk_per_trade_pct,
                leverage=1.0,
                mode="replay",
                order_type="market",
                is_add_to_existing=False,
                use_kelly=False,
                metadata={"research_only": True, "relationship_id": signal.relationship_id},
            )
            decision = risk_manager.evaluate(request, risk_state)
            if not decision.approved:
                rejections[f"risk_manager_{decision.reason}"] += 1
                continue
            liquidity_cap = _two_leg_liquidity_notional_cap(candidate, cost_config)
            approved_notional = min(decision.approved_notional_eur, liquidity_cap)
            if approved_notional < cost_config.min_notional_eur:
                rejections["two_leg_liquidity_below_min_notional"] += 1
                continue
            if approved_notional < decision.approved_notional_eur:
                rejections["two_leg_liquidity_size_reduced"] += 1
            approved_quantity = approved_notional / signal.entry_price
            entry_fill = cost_model.simulate_fill(
                FillRequest(
                    symbol=signal.target_symbol,
                    side="buy",
                    price=signal.entry_price,
                    quantity=approved_quantity,
                    timestamp=signal.entry_at,
                    order_type=cost_config.default_entry_order_type,
                    liquidity_eur=candidate.outcome.entry_liquidity_eur,
                    metadata={"strategy_id": "relative_value_long_only", "relationship_id": signal.relationship_id},
                )
            )
            if not entry_fill.accepted:
                rejections[f"execution_{entry_fill.reason}"] += 1
                continue
            required_cash = approved_notional + entry_fill.total_cost_eur
            if required_cash > cash:
                rejections["cash_insufficient_after_costs"] += 1
                continue
            cash -= required_cash
            estimated_exit_cost = approved_notional * (cost_config.round_trip_cost_estimate_bps() / 20_000.0)
            open_positions.append(
                _OpenPosition(
                    candidate=candidate,
                    notional_eur=approved_notional,
                    quantity=approved_quantity,
                    entry_cost_eur=entry_fill.total_cost_eur,
                    estimated_exit_cost_eur=estimated_exit_cost,
                )
            )
            max_open_seen = max(max_open_seen, len(open_positions))
            planned_exposure = sum(position.notional_eur for position in open_positions)
            if realized_equity > 0.0:
                max_planned_exposure_pct = max(max_planned_exposure_pct, planned_exposure / realized_equity * 100.0)

    # All replay candidates have an outcome. This guard closes malformed tails
    # at their recorded outcome instead of allowing an unaccounted open state.
    for position in open_positions:
        record = _close_position(config.run_id, position, cost_model)
        raw_exit_proceeds = record.quantity * position.candidate.outcome.exit_price
        exit_cost = record.fees_eur + record.spread_cost_eur + record.slippage_eur + record.latency_cost_eur - position.entry_cost_eur
        cash += raw_exit_proceeds - max(0.0, exit_cost)
        realized_equity += record.net_pnl_eur
        records.append(record)
        exit_reasons[record.exit_reason] += 1

    journal = TradeJournal(records)
    metrics = MetricsEngine().calculate(journal.records, initial_capital_eur=config.initial_capital_eur)
    pnl_by_relation = _attribution(records, "relationship_id")
    pnl_by_symbol = _attribution(records, "symbol")
    concentration = _single_relationship_concentration(metrics.total_net_pnl_eur, pnl_by_relation)
    blockers = _result_blockers(config, metrics, max_drawdown_pct, concentration)
    return RelativeValuePortfolioResult(
        cost_profile=cost_profile,
        cost_config=cost_config.to_dict(),
        relationship_count=len(config.relationships),
        raw_signal_count=len(candidates),
        accepted_trade_count=metrics.trade_count,
        net_pnl_eur=round(metrics.total_net_pnl_eur, 6),
        final_equity_eur=round(cash, 6),
        total_return_pct=round((cash - config.initial_capital_eur) / config.initial_capital_eur * 100.0, 6),
        profit_factor=metrics.profit_factor,
        winrate_pct=metrics.winrate_pct,
        expectancy_eur=metrics.expectancy_eur,
        max_drawdown_pct=round(max(max_drawdown_pct, metrics.max_drawdown_pct), 6),
        average_cost_eur=round(
            mean(
                record.fees_eur + record.spread_cost_eur + record.slippage_eur + record.latency_cost_eur
                for record in records
            ),
            6,
        ) if records else None,
        average_trade_duration_minutes=(metrics.average_trade_duration_seconds / 60.0) if metrics.average_trade_duration_seconds is not None else None,
        exit_reason_count=dict(sorted(exit_reasons.items())),
        pnl_by_relationship=pnl_by_relation,
        pnl_by_symbol=pnl_by_symbol,
        rejection_count=dict(sorted(rejections.items())),
        max_open_positions_seen=max_open_seen,
        max_planned_exposure_pct=round(max_planned_exposure_pct, 6),
        status="research_only",
        blockers=tuple(blockers),
        records=tuple(records),
    )


def _passes_cost_guard(
    signal: RelativeValueSignal,
    cost_config: ExecutionCostConfig,
    config: RelativeValueConfig,
) -> bool:
    required_move = max(
        config.min_expected_move_bps,
        cost_config.round_trip_cost_estimate_bps() * config.min_expected_mfe_to_cost,
    )
    return signal.expected_move_bps >= required_move


def _two_leg_liquidity_notional_cap(candidate: _Candidate, cost_config: ExecutionCostConfig) -> float:
    """Cap the entry notional so both historical legs satisfy participation.

    This is deliberately conservative: a replay does not get to assume that a
    future exit can consume more than the configured portion of that bar's
    available EUR volume. The cap can only reject or reduce a trade.
    """

    outcome = candidate.outcome
    entry_liquidity = outcome.entry_liquidity_eur
    exit_liquidity = outcome.exit_liquidity_eur
    if entry_liquidity is None or exit_liquidity is None:
        return 0.0
    entry_cap = entry_liquidity * cost_config.max_liquidity_participation
    exit_cap_at_entry = (
        exit_liquidity
        * cost_config.max_liquidity_participation
        * outcome.signal.entry_price
        / max(outcome.exit_price, 1e-12)
    )
    # Leave a tiny deterministic buffer for floating-point price conversion
    # between entry notional and exit quantity/notional.
    return max(0.0, min(entry_cap, exit_cap_at_entry) * 0.999)


def _close_position(run_id: str, position: _OpenPosition, cost_model: ExecutionCostModel) -> TradeRecord:
    outcome = position.candidate.outcome
    signal = outcome.signal
    exit_fill = cost_model.simulate_fill(
        FillRequest(
            symbol=signal.target_symbol,
            side="sell",
            price=outcome.exit_price,
            quantity=position.quantity,
            timestamp=outcome.exit_at,
            order_type=cost_model.config.default_exit_order_type,
            liquidity_eur=outcome.exit_liquidity_eur,
            metadata={"strategy_id": "relative_value_long_only", "relationship_id": signal.relationship_id},
        )
    )
    if not exit_fill.accepted:
        raise RuntimeError(f"research exit fill rejected: {exit_fill.reason}")
    gross_pnl = (outcome.exit_price - signal.entry_price) * position.quantity
    # The entry fill components are reconstructed from its explicit share below.
    # Keeping the entry cost on the position avoids any hidden perfect-fill path.
    entry_cost = position.entry_cost_eur
    exit_total_cost = exit_fill.total_cost_eur
    total_cost = entry_cost + exit_total_cost
    entry_fee_share, entry_spread_share, entry_slippage_share, entry_latency_share = _cost_component_shares(cost_model.config)
    exit_fee_share, exit_spread_share, exit_slippage_share, exit_latency_share = _cost_component_shares(cost_model.config)
    return TradeRecord(
        run_id=run_id,
        strategy_id="relative_value_long_only",
        symbol=signal.target_symbol,
        side="buy",
        opened_at=signal.entry_at,
        closed_at=outcome.exit_at,
        quantity=position.quantity,
        entry_price=signal.entry_price,
        exit_price=outcome.exit_price,
        gross_pnl_eur=gross_pnl,
        net_pnl_eur=gross_pnl - total_cost,
        fees_eur=entry_cost * entry_fee_share + exit_total_cost * exit_fee_share,
        spread_cost_eur=entry_cost * entry_spread_share + exit_total_cost * exit_spread_share,
        slippage_eur=entry_cost * entry_slippage_share + exit_total_cost * exit_slippage_share,
        latency_cost_eur=entry_cost * entry_latency_share + exit_total_cost * exit_latency_share,
        entry_reason="relative_value_negative_zscore_long_only",
        exit_reason=outcome.exit_reason,
        metadata={
            "relationship_id": signal.relationship_id,
            "reference_symbols": list(signal.reference_symbols),
            "reference_execution": "none",
            "zscore": signal.zscore,
            "correlation": signal.correlation,
            "hedge_ratio": signal.hedge_ratio,
            "cointegration_pvalue": signal.cointegration_pvalue,
            "expected_move_bps": signal.expected_move_bps,
            "mfe_bps": outcome.mfe_bps,
            "mae_bps": outcome.mae_bps,
            "cost_profile": cost_model.config.cost_profile,
        },
    )


def _cost_component_shares(cost_config: ExecutionCostConfig) -> tuple[float, float, float, float]:
    fee = cost_config.fee_for_order_type(cost_config.default_entry_order_type)
    spread = cost_config.fallback_spread_bps * cost_config.spread_charge_fraction(cost_config.default_entry_order_type) / 2.0
    slippage = cost_config.slippage_bps
    latency = cost_config.latency_buffer_bps
    total = max(fee + spread + slippage + latency, 1e-12)
    return fee / total, spread / total, slippage / total, latency / total


def _marked_equity(
    cash: float,
    open_positions: Sequence[_OpenPosition],
    at: datetime,
    cost_config: ExecutionCostConfig,
) -> float:
    total = cash
    for position in open_positions:
        bars = position.candidate.series.target_bars
        prices = [bar.close for bar in bars if bar.timestamp <= at]
        mark_price = float(prices[-1]) if prices else position.candidate.signal.entry_price
        total += position.quantity * mark_price - position.estimated_exit_cost_eur
    return max(0.0, total)


def _attribution(records: Sequence[TradeRecord], key: str) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for record in records:
        if key == "relationship_id":
            label = str(record.metadata.get("relationship_id") or "unknown")
        else:
            label = record.symbol
        row = rows.setdefault(label, {"trade_count": 0, "net_pnl_eur": 0.0})
        row["trade_count"] += 1
        row["net_pnl_eur"] += record.net_pnl_eur
    return {
        label: {"trade_count": value["trade_count"], "net_pnl_eur": round(value["net_pnl_eur"], 6)}
        for label, value in sorted(rows.items())
    }


def _single_relationship_concentration(net_pnl: float, rows: dict[str, dict[str, Any]]) -> bool:
    if net_pnl <= 0.0 or not rows:
        return False
    strongest = max(float(row["net_pnl_eur"]) for row in rows.values())
    return strongest > net_pnl * 0.50


def _result_blockers(
    config: RelativeValueConfig,
    metrics: Any,
    max_drawdown_pct: float,
    concentration: bool,
) -> list[str]:
    blockers = ["research_only_no_auto_promotion"]
    if metrics.trade_count < 30:
        blockers.append("sample_size_below_first_observation_minimum")
    if metrics.total_net_pnl_eur <= 0.0:
        blockers.append("net_pnl_not_positive_after_costs")
    if metrics.profit_factor is None or metrics.profit_factor <= 1.20:
        blockers.append("profit_factor_not_above_base_threshold")
    if max_drawdown_pct >= config.max_drawdown_pct * 100.0:
        blockers.append("drawdown_not_below_threshold")
    if concentration:
        blockers.append("single_relationship_carries_majority_of_result")
    return blockers


def _validation_summary(results: Sequence[RelativeValuePortfolioResult]) -> dict[str, Any]:
    by_profile = {result.cost_profile: result for result in results}
    base = by_profile.get("paper_current_taker")
    stress = by_profile.get("research_stress")
    base_pass = bool(
        base
        and base.accepted_trade_count >= 30
        and base.net_pnl_eur > 0.0
        and base.profit_factor is not None
        and base.profit_factor > 1.20
        and base.max_drawdown_pct < 10.0
        and "single_relationship_carries_majority_of_result" not in base.blockers
    )
    stress_pass = bool(
        stress
        and stress.accepted_trade_count >= 30
        and stress.net_pnl_eur > 0.0
        and stress.profit_factor is not None
        and stress.profit_factor > 1.10
        and stress.max_drawdown_pct < 10.0
        and "single_relationship_carries_majority_of_result" not in stress.blockers
    )
    return {
        "first_observation_min_trades": 30,
        "base_profile": "paper_current_taker",
        "base_pf_threshold_strictly_greater_than": 1.20,
        "stress_profile": "research_stress",
        "stress_pf_threshold_strictly_greater_than": 1.10,
        "max_drawdown_pct_strictly_below": 10.0,
        "base_pass": base_pass,
        "stress_pass": stress_pass,
        "overall_preliminary_pass": base_pass and stress_pass,
        "live_promotion_allowed": False,
    }


def _high_conviction_comparison(
    path: Path | None,
    results: Sequence[RelativeValuePortfolioResult],
) -> dict[str, Any]:
    best = max(results, key=lambda item: item.net_pnl_eur, default=None)
    payload: dict[str, Any] = {
        "high_conviction_report_path": str(path) if path else None,
        "high_conviction_report_loaded": False,
        "relative_value_best_net_pnl_eur": best.net_pnl_eur if best else None,
        "relative_value_best_profit_factor": best.profit_factor if best else None,
    }
    if path is None or not path.exists():
        payload["status"] = "high_conviction_report_not_provided"
        return payload
    try:
        high_conviction = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload["status"] = "high_conviction_report_unreadable"
        return payload
    high_best = high_conviction.get("best_portfolio_result") or {}
    payload.update(
        {
            "high_conviction_report_loaded": True,
            "high_conviction_net_pnl_eur": high_best.get("net_pnl_eur"),
            "high_conviction_profit_factor": high_best.get("profit_factor"),
            "high_conviction_trade_count": high_best.get("trade_count"),
            "status": "compared_to_high_conviction_portfolio",
        }
    )
    if best and isinstance(high_best.get("net_pnl_eur"), (int, float)):
        payload["net_pnl_delta_vs_high_conviction_eur"] = round(
            best.net_pnl_eur - float(high_best["net_pnl_eur"]), 6
        )
    return payload


def _conclusion(
    results: Sequence[RelativeValuePortfolioResult],
    validation: dict[str, Any],
    statsmodels_available: bool,
) -> tuple[str, tuple[str, ...]]:
    recommendations = [
        "Keep Relative Value isolated in research-only replay; do not connect it to the router or official paper execution.",
        "Use the same frozen relationships and thresholds on longer Kraken OHLCV before considering any controlled shadow experiment.",
        "Do not add a reference short, leverage, margin, or pair scaling to compensate for a failed long-only result.",
        "Collect bid/ask and depth before treating fixed spread assumptions as sufficient for an intraday paper-candidate review.",
    ]
    if not statsmodels_available:
        recommendations.insert(0, "Engle-Granger was unavailable; install statsmodels only for a later validation pass, not to change the signal threshold.")
    if not any(result.accepted_trade_count for result in results):
        recommendations.insert(0, "NO GO: no trade survived the cost/risk/exposure gates on this dataset.")
        return "NO_GO_no_cost_and_risk_qualified_relative_value_trades", tuple(recommendations)
    if not validation["overall_preliminary_pass"]:
        recommendations.insert(0, "NO GO: the frozen long-only Relative Value model did not meet every base and stress validation gate.")
        return "NO_GO_relative_value_validation_failed", tuple(recommendations)
    recommendations.insert(0, "Preliminary research pass only; still no paper or live promotion is authorized.")
    return "RESEARCH_ONLY_PRELIMINARY_PASS_NO_PROMOTION", tuple(recommendations)


def _liquidity_eur(bar: MarketBar) -> float | None:
    estimated = float(bar.volume) * float(bar.close)
    return estimated if math.isfinite(estimated) and estimated > 0.0 else None


def _return_bps(entry: float, exit_price: float) -> float:
    if entry <= 0.0:
        return 0.0
    return ((exit_price / entry) - 1.0) * 10_000.0


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)
