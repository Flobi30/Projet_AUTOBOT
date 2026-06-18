"""Research-only high-conviction setup discovery from OHLCV data.

This module deliberately does not use AUTOBOT's recent grid decisions as the
source of truth.  It scans historical OHLCV bars directly for larger swing-style
setups, then replays them with conservative costs and explicit exits.

It never submits orders, never mutates runtime state, never promotes a strategy,
and never enables live or instance duplication.
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median, mean, pstdev
from typing import Any, Literal, Sequence

from .execution_cost_model import ExecutionCostConfig, execution_cost_config_for_profile
from .market_data_repository import MarketBar, MarketDataRepository
from .symbol_normalization import normalize_research_symbol


SetupFamily = Literal[
    "breakout_1h_4h",
    "pullback_trend",
    "major_support_mean_reversion",
    "volatility_expansion",
    "trend_continuation",
]
ExitMode = Literal["fixed_tp_sl", "trailing", "partial_runner", "trend_invalidation"]

DEFAULT_SETUP_FAMILIES: tuple[SetupFamily, ...] = (
    "breakout_1h_4h",
    "pullback_trend",
    "major_support_mean_reversion",
    "volatility_expansion",
    "trend_continuation",
)
DEFAULT_EXIT_MODES: tuple[ExitMode, ...] = (
    "fixed_tp_sl",
    "trailing",
    "partial_runner",
    "trend_invalidation",
)


@dataclass(frozen=True)
class HighConvictionDiscoveryConfig:
    run_id: str
    data_paths: tuple[Path, ...]
    output_dir: Path = Path("reports/research/high_conviction_discovery")
    symbols: tuple[str, ...] = ()
    setup_families: tuple[SetupFamily, ...] = DEFAULT_SETUP_FAMILIES
    min_expected_move_bps: tuple[float, ...] = (200.0, 500.0, 1000.0)
    risk_reward_ratios: tuple[float, ...] = (2.0, 3.0)
    max_hold_hours: tuple[float, ...] = (6.0, 24.0, 72.0, 168.0)
    exit_modes: tuple[ExitMode, ...] = DEFAULT_EXIT_MODES
    initial_capital_eur: float = 1_000.0
    order_notional_eur: float = 100.0
    cost_config: ExecutionCostConfig = field(default_factory=execution_cost_config_for_profile)
    min_sample_trades_for_candidate: int = 20
    candidate_min_profit_factor: float = 1.20
    candidate_max_drawdown_bps: float = 1_500.0
    comparison_micro_report_path: Path | None = None

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id must not be empty")
        if not self.data_paths:
            raise ValueError("data_paths must not be empty")
        if self.initial_capital_eur <= 0.0 or self.order_notional_eur <= 0.0:
            raise ValueError("capital and notional must be positive")
        if not self.min_expected_move_bps:
            raise ValueError("min_expected_move_bps must not be empty")
        if not self.risk_reward_ratios:
            raise ValueError("risk_reward_ratios must not be empty")
        if not self.max_hold_hours:
            raise ValueError("max_hold_hours must not be empty")
        if not self.exit_modes:
            raise ValueError("exit_modes must not be empty")
        if not self.setup_families:
            raise ValueError("setup_families must not be empty")
        valid_families = set(DEFAULT_SETUP_FAMILIES)
        for family in self.setup_families:
            if family not in valid_families:
                raise ValueError(f"unsupported setup family: {family}")
        valid_exits = set(DEFAULT_EXIT_MODES)
        for mode in self.exit_modes:
            if mode not in valid_exits:
                raise ValueError(f"unsupported exit mode: {mode}")
        for value in (*self.min_expected_move_bps, *self.risk_reward_ratios, *self.max_hold_hours):
            if not math.isfinite(float(value)) or float(value) <= 0.0:
                raise ValueError("scenario numeric values must be positive and finite")
        if self.min_sample_trades_for_candidate <= 0:
            raise ValueError("min_sample_trades_for_candidate must be positive")
        self.cost_config.validate()


@dataclass(frozen=True)
class DiscoverySetup:
    setup_id: str
    family: str
    symbol: str
    side: str
    detected_at: str
    entry_at: str
    entry_price: float
    expected_move_bps: float
    logical_stop_bps: float
    risk_reward_estimate: float
    trend_1h_bps: float | None
    trend_4h_bps: float | None
    atr_15m_bps: float | None
    atr_1h_bps: float | None
    support_bps: float | None
    resistance_bps: float | None
    timeframe_signal: str
    reason: str
    features: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DiscoveryScenario:
    min_expected_move_bps: float
    risk_reward_ratio: float
    max_hold_hours: float
    exit_mode: ExitMode

    def label(self) -> str:
        return (
            f"{self.exit_mode}__min{self.min_expected_move_bps:g}bps"
            f"__rr{self.risk_reward_ratio:g}__hold{self.max_hold_hours:g}h"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label(),
            "min_expected_move_bps": self.min_expected_move_bps,
            "risk_reward_ratio": self.risk_reward_ratio,
            "max_hold_hours": self.max_hold_hours,
            "exit_mode": self.exit_mode,
        }


@dataclass(frozen=True)
class DiscoveryTrade:
    setup_id: str
    family: str
    symbol: str
    side: str
    entry_at: str
    exit_at: str
    entry_price: float
    exit_price: float
    gross_return_bps: float
    cost_bps: float
    net_return_bps: float
    pnl_eur: float
    mfe_bps: float
    mae_bps: float
    mfe_mae_ratio: float | None
    duration_minutes: float
    exit_reason: str
    expected_move_bps: float
    logical_stop_bps: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DiscoveryScenarioResult:
    scenario: dict[str, Any]
    evaluated_setups: int
    skipped_expected_move: int
    skipped_rr: int
    skipped_missing_path: int
    trade_count: int
    net_pnl_eur: float
    total_gross_return_bps: float
    total_net_return_bps: float
    profit_factor: float | None
    winrate_pct: float | None
    expectancy_bps: float | None
    average_win_bps: float | None
    average_loss_bps: float | None
    max_drawdown_bps: float
    average_duration_minutes: float | None
    average_mfe_bps: float | None
    average_mae_bps: float | None
    average_mfe_mae_ratio: float | None
    best_symbol: str | None
    worst_symbol: str | None
    best_family: str | None
    worst_family: str | None
    trades_by_symbol: dict[str, dict[str, Any]]
    trades_by_family: dict[str, dict[str, Any]]
    status: str
    blockers: tuple[str, ...]
    sample_trades: tuple[dict[str, Any], ...]
    live_promotion_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["blockers"] = list(self.blockers)
        payload["sample_trades"] = [dict(row) for row in self.sample_trades]
        return payload


@dataclass(frozen=True)
class HighConvictionDiscoveryReport:
    run_id: str
    generated_at: str
    data_paths: tuple[str, ...]
    symbols: tuple[str, ...]
    timeframes: tuple[str, ...]
    cost_config: dict[str, Any]
    setup_families: tuple[str, ...]
    setup_count: int
    setup_count_by_family: dict[str, int]
    setup_count_by_symbol: dict[str, int]
    expected_move_distribution: dict[str, int]
    top_setups: tuple[dict[str, Any], ...]
    scenario_results: tuple[DiscoveryScenarioResult, ...]
    best_scenario: dict[str, Any] | None
    grid_micro_comparison: dict[str, Any]
    conclusion: str
    recommendations: tuple[str, ...]
    json_report_path: str | None = None
    markdown_report_path: str | None = None
    safety_notes: tuple[str, ...] = (
        "Research-only OHLCV setup discovery.",
        "No decision_ledger signal is required for discovery.",
        "No official paper/live runtime component is modified or restarted.",
        "No Kraken order can be created by this command.",
        "No strategy registry mutation or promotion is performed.",
        "No instance duplication, leverage or live permission is enabled.",
    )
    live_promotion_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "data_paths": list(self.data_paths),
            "symbols": list(self.symbols),
            "timeframes": list(self.timeframes),
            "cost_config": dict(self.cost_config),
            "setup_families": list(self.setup_families),
            "setup_count": self.setup_count,
            "setup_count_by_family": dict(self.setup_count_by_family),
            "setup_count_by_symbol": dict(self.setup_count_by_symbol),
            "expected_move_distribution": dict(self.expected_move_distribution),
            "top_setups": [dict(row) for row in self.top_setups],
            "scenario_results": [row.to_dict() for row in self.scenario_results],
            "best_scenario": self.best_scenario,
            "grid_micro_comparison": dict(self.grid_micro_comparison),
            "conclusion": self.conclusion,
            "recommendations": list(self.recommendations),
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
            "safety_notes": list(self.safety_notes),
            "live_promotion_allowed": self.live_promotion_allowed,
        }


def build_high_conviction_discovery_report(
    config: HighConvictionDiscoveryConfig,
) -> HighConvictionDiscoveryReport:
    bars = _load_ohlcv_bars(config)
    bars_by_symbol_tf = _group_by_symbol_timeframe(bars)
    enriched = _with_resampled_4h(bars_by_symbol_tf)
    setups = tuple(_discover_setups(config, enriched))
    scenarios = tuple(
        DiscoveryScenario(
            min_expected_move_bps=float(min_move),
            risk_reward_ratio=float(rr),
            max_hold_hours=float(hold),
            exit_mode=mode,
        )
        for min_move in config.min_expected_move_bps
        for rr in config.risk_reward_ratios
        for hold in config.max_hold_hours
        for mode in config.exit_modes
    )
    results = tuple(_run_discovery_scenario(config, scenario, setups, enriched) for scenario in scenarios)
    best = _best_scenario(results)
    comparison = _grid_micro_comparison(config.comparison_micro_report_path, best)
    conclusion, recommendations = _build_conclusion(best, setups, comparison)
    symbols = tuple(sorted({bar.symbol for bar in bars}))
    timeframes = tuple(sorted({bar.timeframe for bar in bars}))
    return HighConvictionDiscoveryReport(
        run_id=config.run_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        data_paths=tuple(str(path) for path in config.data_paths),
        symbols=symbols,
        timeframes=timeframes,
        cost_config=config.cost_config.to_dict(),
        setup_families=tuple(config.setup_families),
        setup_count=len(setups),
        setup_count_by_family=dict(Counter(setup.family for setup in setups)),
        setup_count_by_symbol=dict(Counter(setup.symbol for setup in setups)),
        expected_move_distribution=_expected_move_distribution(setups),
        top_setups=tuple(setup.to_dict() for setup in sorted(setups, key=_setup_sort_key, reverse=True)[:30]),
        scenario_results=results,
        best_scenario=best.to_dict() if best else None,
        grid_micro_comparison=comparison,
        conclusion=conclusion,
        recommendations=recommendations,
    )


def write_high_conviction_discovery_report(
    report: HighConvictionDiscoveryReport,
    output_dir: str | Path,
) -> HighConvictionDiscoveryReport:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / f"{report.run_id}.json"
    md_path = output / f"{report.run_id}.md"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(render_high_conviction_discovery_report(report), encoding="utf-8")
    return replace(report, json_report_path=str(json_path), markdown_report_path=str(md_path))


def render_high_conviction_discovery_report(report: HighConvictionDiscoveryReport) -> str:
    lines = [
        f"# High Conviction Discovery - {report.run_id}",
        "",
        "## Summary",
        "",
        f"- Generated at: `{report.generated_at}`",
        f"- Data paths: `{len(report.data_paths)}`",
        f"- Symbols: `{', '.join(report.symbols)}`",
        f"- Timeframes: `{', '.join(report.timeframes)}`",
        f"- Cost profile: `{report.cost_config.get('cost_profile')}`",
        f"- Round-trip cost estimate: `{_fmt(report.cost_config.get('round_trip_cost_estimate_bps'))} bps`",
        f"- Setups detected: `{report.setup_count}`",
        f"- Conclusion: **{report.conclusion}**",
        "",
        "This report generates swing/high-conviction candidates directly from OHLCV. It does not assume the existing grid signals are the available opportunity set.",
        "",
        "## Setups By Family",
        "",
        "| Family | Count |",
        "| --- | ---: |",
    ]
    for family, count in sorted(report.setup_count_by_family.items()):
        lines.append(f"| {family} | {count} |")
    lines.extend(["", "## Setups By Symbol", "", "| Symbol | Count |", "| --- | ---: |"])
    for symbol, count in sorted(report.setup_count_by_symbol.items()):
        lines.append(f"| {symbol} | {count} |")
    lines.extend(["", "## Expected Move Distribution", "", "| Bucket | Count |", "| --- | ---: |"])
    for bucket, count in report.expected_move_distribution.items():
        lines.append(f"| {bucket} | {count} |")
    lines.extend([
        "",
        "## Top Scenarios",
        "",
        "| Scenario | Status | Trades | Net PnL EUR | PF | Winrate | Expectancy bps | Max DD bps | Avg MFE/MAE | Best | Worst |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ])
    for result in sorted(report.scenario_results, key=lambda row: row.net_pnl_eur, reverse=True)[:25]:
        lines.append(
            f"| {result.scenario['label']} | {result.status} | {result.trade_count} | "
            f"{_fmt(result.net_pnl_eur)} | {_fmt(result.profit_factor)} | "
            f"{_fmt(result.winrate_pct)} | {_fmt(result.expectancy_bps)} | "
            f"{_fmt(result.max_drawdown_bps)} | {_fmt(result.average_mfe_mae_ratio)} | "
            f"{result.best_symbol or '-'} | {result.worst_symbol or '-'} |"
        )
    lines.extend([
        "",
        "## Top Raw Setups",
        "",
        "| Symbol | Family | Entry | Expected bps | Stop bps | RR est. | Trend 1h | Trend 4h | ATR 15m | ATR 1h | Reason |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ])
    for setup in report.top_setups[:25]:
        lines.append(
            f"| {setup.get('symbol')} | {setup.get('family')} | {setup.get('entry_at')} | "
            f"{_fmt(setup.get('expected_move_bps'))} | {_fmt(setup.get('logical_stop_bps'))} | "
            f"{_fmt(setup.get('risk_reward_estimate'))} | {_fmt(setup.get('trend_1h_bps'))} | "
            f"{_fmt(setup.get('trend_4h_bps'))} | {_fmt(setup.get('atr_15m_bps'))} | "
            f"{_fmt(setup.get('atr_1h_bps'))} | {setup.get('reason')} |"
        )
    lines.extend(["", "## Grid/Micro Comparison", ""])
    for key, value in report.grid_micro_comparison.items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Recommendations", ""])
    lines.extend(f"- {item}" for item in report.recommendations)
    lines.extend(["", "## Safety", ""])
    lines.extend(f"- {item}" for item in report.safety_notes)
    lines.append(f"- live_promotion_allowed: `{report.live_promotion_allowed}`")
    return "\n".join(lines) + "\n"


def _load_ohlcv_bars(config: HighConvictionDiscoveryConfig) -> list[MarketBar]:
    repository = MarketDataRepository()
    paths = _expand_paths(config.data_paths)
    if not paths:
        raise FileNotFoundError("no CSV/Parquet OHLCV files found")
    symbols = {normalize_research_symbol(symbol) for symbol in config.symbols if normalize_research_symbol(symbol)}
    bars: list[MarketBar] = []
    for path in paths:
        suffix = path.suffix.lower()
        if suffix == ".csv":
            rows = repository.load_csv(path)
        elif suffix == ".parquet":
            rows = repository.load_parquet(path)
        else:
            continue
        if symbols:
            rows = [bar for bar in rows if normalize_research_symbol(bar.symbol) in symbols]
        bars.extend(rows)
    normalized = repository.normalize(
        replace(bar, symbol=normalize_research_symbol(bar.symbol) or bar.symbol.upper())
        for bar in bars
    )
    if not normalized:
        raise ValueError("no OHLCV bars matched the discovery config")
    return normalized


def _expand_paths(paths: Sequence[Path]) -> list[Path]:
    expanded: list[Path] = []
    for path in paths:
        if path.is_dir():
            expanded.extend(sorted(item for item in path.rglob("*") if item.suffix.lower() in {".csv", ".parquet"}))
        elif any(char in str(path) for char in "*?["):
            expanded.extend(sorted(Path().glob(str(path))))
        elif path.exists():
            expanded.append(path)
    return list(dict.fromkeys(expanded))


def _group_by_symbol_timeframe(bars: Sequence[MarketBar]) -> dict[tuple[str, str], list[MarketBar]]:
    groups: dict[tuple[str, str], list[MarketBar]] = defaultdict(list)
    for bar in bars:
        groups[(bar.symbol, bar.timeframe.lower())].append(bar)
    return {key: sorted(rows, key=lambda row: row.timestamp) for key, rows in groups.items()}


def _with_resampled_4h(
    groups: dict[tuple[str, str], list[MarketBar]],
) -> dict[tuple[str, str], list[MarketBar]]:
    enriched = dict(groups)
    symbols = {symbol for symbol, _timeframe in groups}
    for symbol in symbols:
        if (symbol, "4h") not in enriched and (symbol, "1h") in enriched:
            enriched[(symbol, "4h")] = _resample_bars(enriched[(symbol, "1h")], "4h", 4 * 60 * 60)
    return enriched


def _resample_bars(bars: Sequence[MarketBar], timeframe: str, interval_seconds: int) -> list[MarketBar]:
    buckets: dict[int, list[MarketBar]] = defaultdict(list)
    for bar in bars:
        epoch = int(bar.timestamp.timestamp())
        buckets[epoch - (epoch % interval_seconds)].append(bar)
    result: list[MarketBar] = []
    for bucket_start, rows in sorted(buckets.items()):
        rows = sorted(rows, key=lambda row: row.timestamp)
        if not rows:
            continue
        result.append(
            MarketBar(
                timestamp=datetime.fromtimestamp(bucket_start, timezone.utc),
                open=rows[0].open,
                high=max(row.high for row in rows),
                low=min(row.low for row in rows),
                close=rows[-1].close,
                volume=sum(row.volume for row in rows),
                symbol=rows[0].symbol,
                timeframe=timeframe,
                metadata={"source": "resampled_from_1h", "bar_count": len(rows)},
            )
        )
    return result


def _discover_setups(
    config: HighConvictionDiscoveryConfig,
    groups: dict[tuple[str, str], list[MarketBar]],
) -> list[DiscoverySetup]:
    symbols = tuple(sorted({symbol for symbol, _ in groups}))
    wanted = {normalize_research_symbol(symbol) for symbol in config.symbols if normalize_research_symbol(symbol)}
    if wanted:
        symbols = tuple(symbol for symbol in symbols if symbol in wanted)
    setups: list[DiscoverySetup] = []
    for symbol in symbols:
        five = groups.get((symbol, "5m"), [])
        fifteen = groups.get((symbol, "15m"), [])
        one_hour = groups.get((symbol, "1h"), [])
        four_hour = groups.get((symbol, "4h"), [])
        if len(five) < 10 or len(fifteen) < 40 or len(one_hour) < 12:
            continue
        for index in range(40, len(fifteen) - 1):
            bar = fifteen[index]
            history_15m = fifteen[: index + 1]
            history_1h = _bars_at_or_before(one_hour, bar.timestamp)
            history_4h = _bars_at_or_before(four_hour, bar.timestamp)
            if len(history_1h) < 12:
                continue
            entry = _first_bar_after(five, bar.timestamp)
            if entry is None:
                continue
            context = _context_for_bar(history_15m, history_1h, history_4h)
            for setup in _setups_for_context(config, symbol, bar, entry, context):
                if setup.expected_move_bps >= min(config.min_expected_move_bps):
                    setups.append(setup)
    return _dedupe_setups(setups)


def _setups_for_context(
    config: HighConvictionDiscoveryConfig,
    symbol: str,
    bar: MarketBar,
    entry: MarketBar,
    context: dict[str, Any],
) -> list[DiscoverySetup]:
    families = set(config.setup_families)
    setups: list[DiscoverySetup] = []
    price = float(entry.close)
    atr_15m = float(context.get("atr_15m_bps") or 0.0)
    atr_1h = float(context.get("atr_1h_bps") or 0.0)
    trend_1h = float(context.get("trend_1h_bps") or 0.0)
    trend_4h = float(context.get("trend_4h_bps") or 0.0)
    resistance_bps = _distance_bps(price, float(context.get("resistance_1h") or price), direction="up")
    support_bps = _distance_bps(price, float(context.get("support_1h") or price), direction="down")
    range_width_bps = max(0.0, resistance_bps + support_bps)
    vol_ratio = float(context.get("vol_expansion_ratio") or 0.0)

    previous_high_15m = float(context.get("previous_high_15m") or price)
    breakout_bps = _distance_bps(previous_high_15m, float(bar.close), direction="up")
    if (
        "breakout_1h_4h" in families
        and trend_1h >= 120.0
        and trend_4h >= -80.0
        and breakout_bps >= 12.0
        and atr_15m >= 8.0
    ):
        expected = _cap_expected(max(200.0, atr_1h * 3.0, range_width_bps * 0.75))
        stop = _cap_stop(max(80.0, atr_15m * 1.7, support_bps * 0.35))
        setups.append(_make_setup(symbol, "breakout_1h_4h", bar, entry, expected, stop, context, "1h/4h trend breakout"))

    sma20_15m = float(context.get("sma20_15m") or price)
    sma50_15m = float(context.get("sma50_15m") or price)
    recovered_from_pullback = float(bar.close) >= sma20_15m and float(bar.low) <= sma20_15m * (1.0 + _bps_to_rate(35.0))
    if (
        "pullback_trend" in families
        and trend_1h >= 150.0
        and trend_4h >= -50.0
        and recovered_from_pullback
        and sma20_15m >= sma50_15m * (1.0 - _bps_to_rate(30.0))
    ):
        expected = _cap_expected(max(200.0, resistance_bps, atr_1h * 2.8))
        stop = _cap_stop(max(90.0, atr_15m * 1.6, support_bps * 0.45))
        setups.append(_make_setup(symbol, "pullback_trend", bar, entry, expected, stop, context, "trend pullback recovery"))

    z50 = float(context.get("zscore_50_15m") or 0.0)
    near_support = support_bps <= max(80.0, atr_15m * 1.2)
    if (
        "major_support_mean_reversion" in families
        and near_support
        and z50 <= -1.2
        and trend_4h >= -450.0
        and atr_15m >= 6.0
    ):
        mean_revert_bps = _distance_bps(price, sma50_15m, direction="up")
        expected = _cap_expected(max(200.0, mean_revert_bps, atr_1h * 2.2))
        stop = _cap_stop(max(80.0, atr_15m * 1.4, support_bps + 35.0))
        setups.append(_make_setup(symbol, "major_support_mean_reversion", bar, entry, expected, stop, context, "support reversion with 15m dislocation"))

    if (
        "volatility_expansion" in families
        and vol_ratio >= 1.45
        and breakout_bps >= 8.0
        and trend_1h >= 50.0
        and atr_1h >= 12.0
    ):
        expected = _cap_expected(max(250.0, atr_1h * 3.8, range_width_bps * 0.6))
        stop = _cap_stop(max(100.0, atr_15m * 2.0))
        setups.append(_make_setup(symbol, "volatility_expansion", bar, entry, expected, stop, context, "volatility expansion breakout"))

    if (
        "trend_continuation" in families
        and trend_1h >= 260.0
        and trend_4h >= 100.0
        and float(bar.close) >= sma20_15m
        and sma20_15m >= sma50_15m
        and atr_15m >= 6.0
    ):
        expected = _cap_expected(max(300.0, atr_1h * 4.2, resistance_bps + atr_1h))
        stop = _cap_stop(max(110.0, atr_15m * 2.0))
        setups.append(_make_setup(symbol, "trend_continuation", bar, entry, expected, stop, context, "multi-timeframe trend continuation"))
    return setups


def _make_setup(
    symbol: str,
    family: SetupFamily,
    bar: MarketBar,
    entry: MarketBar,
    expected_move_bps: float,
    logical_stop_bps: float,
    context: dict[str, Any],
    reason: str,
) -> DiscoverySetup:
    rr = expected_move_bps / max(logical_stop_bps, 1e-12)
    setup_id = f"{symbol}:{family}:{entry.timestamp.isoformat()}"
    return DiscoverySetup(
        setup_id=setup_id,
        family=family,
        symbol=symbol,
        side="buy",
        detected_at=bar.timestamp.isoformat(),
        entry_at=entry.timestamp.isoformat(),
        entry_price=float(entry.close),
        expected_move_bps=round(expected_move_bps, 6),
        logical_stop_bps=round(logical_stop_bps, 6),
        risk_reward_estimate=round(rr, 6),
        trend_1h_bps=_optional_round(context.get("trend_1h_bps")),
        trend_4h_bps=_optional_round(context.get("trend_4h_bps")),
        atr_15m_bps=_optional_round(context.get("atr_15m_bps")),
        atr_1h_bps=_optional_round(context.get("atr_1h_bps")),
        support_bps=_optional_round(_distance_bps(float(entry.close), float(context.get("support_1h") or entry.close), direction="down")),
        resistance_bps=_optional_round(_distance_bps(float(entry.close), float(context.get("resistance_1h") or entry.close), direction="up")),
        timeframe_signal="15m_structure_with_1h_4h_context",
        reason=reason,
        features={key: _jsonable(value) for key, value in context.items()},
    )


def _context_for_bar(
    history_15m: Sequence[MarketBar],
    history_1h: Sequence[MarketBar],
    history_4h: Sequence[MarketBar],
) -> dict[str, Any]:
    closes_15 = [bar.close for bar in history_15m]
    closes_1h = [bar.close for bar in history_1h]
    closes_4h = [bar.close for bar in history_4h]
    current = history_15m[-1]
    previous_15 = history_15m[:-1]
    atr_15 = _atr_bps(history_15m[-32:])
    atr_1h = _atr_bps(history_1h[-24:])
    recent_atr = _atr_bps(history_15m[-16:])
    baseline_atr = _atr_bps(history_15m[-64:-16]) if len(history_15m) >= 80 else atr_15
    sma20_15 = _sma(closes_15, 20) or current.close
    sma50_15 = _sma(closes_15, 50) or current.close
    std50 = _std(closes_15[-50:])
    z50 = ((current.close - sma50_15) / std50) if std50 and std50 > 0 else 0.0
    support_1h = min((bar.low for bar in history_1h[-48:]), default=current.low)
    resistance_1h = max((bar.high for bar in history_1h[-48:]), default=current.high)
    return {
        "atr_15m_bps": atr_15,
        "atr_1h_bps": atr_1h,
        "trend_1h_bps": _return_bps(closes_1h[-25], closes_1h[-1]) if len(closes_1h) >= 25 else _return_bps(closes_1h[0], closes_1h[-1]),
        "trend_4h_bps": _return_bps(closes_4h[-7], closes_4h[-1]) if len(closes_4h) >= 7 else (_return_bps(closes_4h[0], closes_4h[-1]) if len(closes_4h) >= 2 else 0.0),
        "sma20_15m": sma20_15,
        "sma50_15m": sma50_15,
        "zscore_50_15m": z50,
        "support_1h": support_1h,
        "resistance_1h": resistance_1h,
        "previous_high_15m": max((bar.high for bar in previous_15[-32:]), default=current.high),
        "previous_low_15m": min((bar.low for bar in previous_15[-32:]), default=current.low),
        "vol_expansion_ratio": recent_atr / max(baseline_atr, 1e-12),
    }


def _run_discovery_scenario(
    config: HighConvictionDiscoveryConfig,
    scenario: DiscoveryScenario,
    setups: Sequence[DiscoverySetup],
    groups: dict[tuple[str, str], list[MarketBar]],
) -> DiscoveryScenarioResult:
    trades: list[DiscoveryTrade] = []
    skipped_expected = 0
    skipped_rr = 0
    skipped_path = 0
    evaluated = 0
    for setup in setups:
        evaluated += 1
        if setup.expected_move_bps < scenario.min_expected_move_bps:
            skipped_expected += 1
            continue
        if setup.risk_reward_estimate < scenario.risk_reward_ratio:
            skipped_rr += 1
            continue
        path = _future_5m_path(groups.get((setup.symbol, "5m"), []), setup.entry_at, scenario.max_hold_hours)
        if not path:
            skipped_path += 1
            continue
        trade = _simulate_trade(config, scenario, setup, path)
        if trade is not None:
            trades.append(trade)
        else:
            skipped_path += 1
    return _scenario_result(config, scenario, trades, evaluated, skipped_expected, skipped_rr, skipped_path)


def _simulate_trade(
    config: HighConvictionDiscoveryConfig,
    scenario: DiscoveryScenario,
    setup: DiscoverySetup,
    path: Sequence[MarketBar],
) -> DiscoveryTrade | None:
    entry = setup.entry_price
    if entry <= 0.0:
        return None
    target = max(scenario.min_expected_move_bps, setup.expected_move_bps)
    stop = min(setup.logical_stop_bps, target / scenario.risk_reward_ratio)
    stop = max(10.0, stop)
    cost_bps = config.cost_config.round_trip_cost_estimate_bps()
    best_high_bps = -math.inf
    worst_low_bps = math.inf
    exit_bar = path[-1]
    exit_return_bps = _close_return_bps(entry, exit_bar)
    exit_reason = "time_horizon"
    activated_trailing = False
    trailing_peak = -math.inf
    partial_taken = False
    partial_return = 0.0
    rolling_closes: list[float] = []
    for bar in path:
        high_bps = _high_return_bps(entry, bar)
        low_bps = _low_return_bps(entry, bar)
        close_bps = _close_return_bps(entry, bar)
        best_high_bps = max(best_high_bps, high_bps)
        worst_low_bps = min(worst_low_bps, low_bps)
        rolling_closes.append(float(bar.close))

        if low_bps <= -stop:
            exit_bar = bar
            exit_return_bps = -stop
            exit_reason = "logical_stop"
            break
        if scenario.exit_mode == "fixed_tp_sl":
            if high_bps >= target:
                exit_bar = bar
                exit_return_bps = target
                exit_reason = "take_profit"
                break
        elif scenario.exit_mode == "trailing":
            activation = target * 0.45
            if high_bps >= activation:
                activated_trailing = True
                trailing_peak = max(trailing_peak, high_bps)
            if activated_trailing:
                trailing_peak = max(trailing_peak, high_bps)
                trail_level = trailing_peak - stop
                if low_bps <= trail_level:
                    exit_bar = bar
                    exit_return_bps = trail_level
                    exit_reason = "trailing_stop"
                    break
        elif scenario.exit_mode == "partial_runner":
            if not partial_taken and high_bps >= target:
                partial_taken = True
                partial_return = target
                trailing_peak = high_bps
                continue
            if partial_taken:
                trailing_peak = max(trailing_peak, high_bps)
                trail_level = trailing_peak - stop
                if low_bps <= trail_level:
                    exit_bar = bar
                    exit_return_bps = (partial_return * 0.5) + (trail_level * 0.5)
                    exit_reason = "partial_tp_runner_trailing"
                    break
        elif scenario.exit_mode == "trend_invalidation":
            if high_bps >= target:
                exit_bar = bar
                exit_return_bps = target
                exit_reason = "take_profit"
                break
            if len(rolling_closes) >= 8:
                short_return = _return_bps(rolling_closes[-8], rolling_closes[-1])
                if close_bps < max(-stop * 0.70, -120.0) or (best_high_bps < target * 0.40 and short_return < -stop * 0.35):
                    exit_bar = bar
                    exit_return_bps = close_bps
                    exit_reason = "trend_invalidation"
                    break
    else:
        if scenario.exit_mode == "partial_runner" and partial_taken:
            final_return = _close_return_bps(entry, path[-1])
            exit_bar = path[-1]
            exit_return_bps = (partial_return * 0.5) + (final_return * 0.5)
            exit_reason = "partial_tp_runner_horizon"

    mfe = best_high_bps if math.isfinite(best_high_bps) else 0.0
    mae = worst_low_bps if math.isfinite(worst_low_bps) else 0.0
    ratio = mfe / abs(mae) if mae < 0 else None
    net = exit_return_bps - cost_bps
    entry_time = _parse_dt(setup.entry_at)
    duration = max(0.0, (exit_bar.timestamp - entry_time).total_seconds() / 60.0)
    return DiscoveryTrade(
        setup_id=setup.setup_id,
        family=setup.family,
        symbol=setup.symbol,
        side=setup.side,
        entry_at=setup.entry_at,
        exit_at=exit_bar.timestamp.isoformat(),
        entry_price=entry,
        exit_price=float(exit_bar.close),
        gross_return_bps=round(exit_return_bps, 6),
        cost_bps=round(cost_bps, 6),
        net_return_bps=round(net, 6),
        pnl_eur=round(config.order_notional_eur * (net / 10_000.0), 6),
        mfe_bps=round(mfe, 6),
        mae_bps=round(mae, 6),
        mfe_mae_ratio=round(ratio, 6) if ratio is not None else None,
        duration_minutes=round(duration, 6),
        exit_reason=exit_reason,
        expected_move_bps=setup.expected_move_bps,
        logical_stop_bps=setup.logical_stop_bps,
    )


def _scenario_result(
    config: HighConvictionDiscoveryConfig,
    scenario: DiscoveryScenario,
    trades: Sequence[DiscoveryTrade],
    evaluated: int,
    skipped_expected: int,
    skipped_rr: int,
    skipped_path: int,
) -> DiscoveryScenarioResult:
    nets = [trade.net_return_bps for trade in trades]
    gross = [trade.gross_return_bps for trade in trades]
    wins = [value for value in nets if value > 0.0]
    losses = [value for value in nets if value < 0.0]
    pnl_by_symbol: dict[str, float] = defaultdict(float)
    count_by_symbol: Counter[str] = Counter()
    pnl_by_family: dict[str, float] = defaultdict(float)
    count_by_family: Counter[str] = Counter()
    for trade in trades:
        pnl_by_symbol[trade.symbol] += trade.pnl_eur
        count_by_symbol[trade.symbol] += 1
        pnl_by_family[trade.family] += trade.pnl_eur
        count_by_family[trade.family] += 1
    profit_factor = None
    if losses:
        profit_factor = sum(wins) / abs(sum(losses)) if wins else 0.0
    elif wins:
        profit_factor = None
    blockers = _candidate_blockers(config, trades, profit_factor, nets)
    status = "manual_shadow_review_candidate" if not blockers else "research_only"
    mfe_mae_values = [trade.mfe_mae_ratio for trade in trades if trade.mfe_mae_ratio is not None]
    return DiscoveryScenarioResult(
        scenario=scenario.to_dict(),
        evaluated_setups=evaluated,
        skipped_expected_move=skipped_expected,
        skipped_rr=skipped_rr,
        skipped_missing_path=skipped_path,
        trade_count=len(trades),
        net_pnl_eur=round(sum(trade.pnl_eur for trade in trades), 6),
        total_gross_return_bps=round(sum(gross), 6),
        total_net_return_bps=round(sum(nets), 6),
        profit_factor=profit_factor,
        winrate_pct=(len(wins) / len(nets) * 100.0) if nets else None,
        expectancy_bps=(sum(nets) / len(nets)) if nets else None,
        average_win_bps=(sum(wins) / len(wins)) if wins else None,
        average_loss_bps=(sum(losses) / len(losses)) if losses else None,
        max_drawdown_bps=_max_drawdown(nets),
        average_duration_minutes=_avg([trade.duration_minutes for trade in trades]),
        average_mfe_bps=_avg([trade.mfe_bps for trade in trades]),
        average_mae_bps=_avg([trade.mae_bps for trade in trades]),
        average_mfe_mae_ratio=_avg(mfe_mae_values),
        best_symbol=max(pnl_by_symbol, key=pnl_by_symbol.get) if pnl_by_symbol else None,
        worst_symbol=min(pnl_by_symbol, key=pnl_by_symbol.get) if pnl_by_symbol else None,
        best_family=max(pnl_by_family, key=pnl_by_family.get) if pnl_by_family else None,
        worst_family=min(pnl_by_family, key=pnl_by_family.get) if pnl_by_family else None,
        trades_by_symbol={
            symbol: {"trade_count": count_by_symbol[symbol], "net_pnl_eur": round(pnl_by_symbol[symbol], 6)}
            for symbol in sorted(count_by_symbol)
        },
        trades_by_family={
            family: {"trade_count": count_by_family[family], "net_pnl_eur": round(pnl_by_family[family], 6)}
            for family in sorted(count_by_family)
        },
        status=status,
        blockers=tuple(blockers),
        sample_trades=tuple(trade.to_dict() for trade in sorted(trades, key=lambda row: row.pnl_eur, reverse=True)[:12]),
    )


def _candidate_blockers(
    config: HighConvictionDiscoveryConfig,
    trades: Sequence[DiscoveryTrade],
    profit_factor: float | None,
    nets: Sequence[float],
) -> list[str]:
    blockers: list[str] = []
    if len(trades) < config.min_sample_trades_for_candidate:
        blockers.append("sample_size_below_candidate_minimum")
    if sum(nets) <= 0.0:
        blockers.append("net_pnl_not_positive_after_costs")
    if profit_factor is None:
        blockers.append("profit_factor_unbounded_or_no_losses_needs_more_sample")
    elif profit_factor < config.candidate_min_profit_factor:
        blockers.append("profit_factor_below_candidate_minimum")
    if _max_drawdown(nets) > config.candidate_max_drawdown_bps:
        blockers.append("drawdown_above_candidate_maximum")
    symbols = {trade.symbol for trade in trades}
    if len(symbols) <= 1 and len(trades) >= config.min_sample_trades_for_candidate:
        blockers.append("single_symbol_dominance_requires_more_review")
    return blockers


def _best_scenario(results: Sequence[DiscoveryScenarioResult]) -> DiscoveryScenarioResult | None:
    viable = [row for row in results if row.trade_count > 0]
    if not viable:
        return None
    return sorted(
        viable,
        key=lambda row: (
            row.status == "manual_shadow_review_candidate",
            row.net_pnl_eur,
            row.profit_factor or 0.0,
            -(row.max_drawdown_bps or 0.0),
        ),
        reverse=True,
    )[0]


def _grid_micro_comparison(
    micro_report_path: Path | None,
    best: DiscoveryScenarioResult | None,
) -> dict[str, Any]:
    comparison: dict[str, Any] = {
        "micro_report_path": str(micro_report_path) if micro_report_path else None,
        "micro_report_loaded": False,
        "discovery_best_net_pnl_eur": best.net_pnl_eur if best else None,
        "discovery_best_profit_factor": best.profit_factor if best else None,
    }
    if not micro_report_path or not micro_report_path.exists():
        comparison["status"] = "micro_report_not_provided"
        return comparison
    try:
        payload = json.loads(micro_report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        comparison["status"] = "micro_report_invalid_json"
        return comparison
    micro_best = payload.get("best_scenario") or {}
    comparison.update(
        {
            "micro_report_loaded": True,
            "micro_conclusion": payload.get("conclusion"),
            "micro_best_net_pnl_eur": micro_best.get("net_pnl_eur"),
            "micro_best_profit_factor": micro_best.get("profit_factor"),
            "micro_best_trade_count": micro_best.get("trade_count"),
            "status": "discovery_compared_to_micro_report",
        }
    )
    if best and isinstance(micro_best.get("net_pnl_eur"), (int, float)):
        comparison["net_pnl_delta_vs_micro_eur"] = best.net_pnl_eur - float(micro_best["net_pnl_eur"])
    return comparison


def _build_conclusion(
    best: DiscoveryScenarioResult | None,
    setups: Sequence[DiscoverySetup],
    comparison: dict[str, Any],
) -> tuple[str, tuple[str, ...]]:
    recommendations = [
        "Keep discovery research-only; do not promote any setup to official paper without longer data and manual review.",
        "Use this report to decide which setup family deserves deeper OHLCV walk-forward, not to authorize live trading.",
        "Keep existing micro/grid trades learning-only unless they prove net profitability after runtime-comparable costs.",
        "Do not enable leverage or instance duplication before a setup passes profit factor, drawdown and sample-size gates.",
    ]
    if not setups:
        recommendations.insert(0, "No high-conviction OHLCV setups were detected; extend historical data before changing runtime.")
        return "no_high_conviction_setups_detected", tuple(recommendations)
    if best is None or best.trade_count == 0:
        recommendations.insert(0, "Setups were detected, but no scenario produced executable replay trades.")
        return "setups_detected_no_executable_replay", tuple(recommendations)
    if best.status == "manual_shadow_review_candidate":
        recommendations.insert(0, "A high-conviction scenario may deserve controlled shadow investigation, not automatic promotion.")
        return "manual_shadow_review_candidate_found", tuple(recommendations)
    if best.net_pnl_eur > 0.0:
        recommendations.insert(0, "Best scenario is positive but still blocked by candidate gates; collect more evidence before paper.")
        return "positive_but_not_validated", tuple(recommendations)
    if comparison.get("micro_report_loaded"):
        recommendations.insert(0, "Discovery ran on independent OHLCV setups; compare its net PnL and PF against the micro report before deciding.")
    else:
        recommendations.insert(0, "Discovery ran independently, but no micro/grid report was supplied for direct comparison.")
    return "no_profitable_high_conviction_candidate_yet", tuple(recommendations)


def _dedupe_setups(setups: Sequence[DiscoverySetup]) -> list[DiscoverySetup]:
    seen: set[str] = set()
    result: list[DiscoverySetup] = []
    for setup in sorted(setups, key=lambda row: (row.symbol, row.entry_at, row.family, -row.expected_move_bps)):
        key = f"{setup.symbol}:{setup.family}:{setup.entry_at}"
        if key in seen:
            continue
        seen.add(key)
        result.append(setup)
    return result


def _future_5m_path(bars: Sequence[MarketBar], entry_at: str, max_hold_hours: float) -> list[MarketBar]:
    start = _parse_dt(entry_at)
    end = start + timedelta(hours=max_hold_hours)
    return [bar for bar in bars if start < bar.timestamp <= end]


def _bars_at_or_before(bars: Sequence[MarketBar], timestamp: datetime) -> list[MarketBar]:
    return [bar for bar in bars if bar.timestamp <= timestamp]


def _first_bar_after(bars: Sequence[MarketBar], timestamp: datetime) -> MarketBar | None:
    for bar in bars:
        if bar.timestamp > timestamp:
            return bar
    return None


def _expected_move_distribution(setups: Sequence[DiscoverySetup]) -> dict[str, int]:
    buckets = {
        "lt_200_bps": 0,
        "200_499_bps": 0,
        "500_999_bps": 0,
        "gte_1000_bps": 0,
    }
    for setup in setups:
        value = setup.expected_move_bps
        if value < 200.0:
            buckets["lt_200_bps"] += 1
        elif value < 500.0:
            buckets["200_499_bps"] += 1
        elif value < 1000.0:
            buckets["500_999_bps"] += 1
        else:
            buckets["gte_1000_bps"] += 1
    return buckets


def _setup_sort_key(setup: DiscoverySetup) -> tuple[float, float, float]:
    return (setup.expected_move_bps, setup.risk_reward_estimate, setup.trend_1h_bps or 0.0)


def _cap_expected(value: float) -> float:
    return max(0.0, min(2_500.0, float(value)))


def _cap_stop(value: float) -> float:
    return max(20.0, min(600.0, float(value)))


def _return_bps(start: float, end: float) -> float:
    if start <= 0.0:
        return 0.0
    return ((end / start) - 1.0) * 10_000.0


def _distance_bps(price: float, level: float, *, direction: Literal["up", "down"]) -> float:
    if price <= 0.0 or level <= 0.0:
        return 0.0
    if direction == "up":
        return max(0.0, ((level / price) - 1.0) * 10_000.0)
    return max(0.0, ((price / level) - 1.0) * 10_000.0)


def _close_return_bps(entry: float, bar: MarketBar) -> float:
    return _return_bps(entry, float(bar.close))


def _high_return_bps(entry: float, bar: MarketBar) -> float:
    return _return_bps(entry, float(bar.high))


def _low_return_bps(entry: float, bar: MarketBar) -> float:
    return _return_bps(entry, float(bar.low))


def _atr_bps(bars: Sequence[MarketBar]) -> float:
    if len(bars) < 2:
        return 0.0
    true_ranges: list[float] = []
    previous_close = float(bars[0].close)
    for bar in bars[1:]:
        high = float(bar.high)
        low = float(bar.low)
        close = float(bar.close)
        tr = max(high - low, abs(high - previous_close), abs(low - previous_close))
        if previous_close > 0.0:
            true_ranges.append((tr / previous_close) * 10_000.0)
        previous_close = close
    return sum(true_ranges) / len(true_ranges) if true_ranges else 0.0


def _sma(values: Sequence[float], window: int) -> float | None:
    if len(values) < window:
        return None
    tail = values[-window:]
    return sum(tail) / len(tail)


def _std(values: Sequence[float]) -> float | None:
    if len(values) < 2:
        return None
    value = pstdev(values)
    return value if math.isfinite(value) else None


def _avg(values: Sequence[float | None]) -> float | None:
    cleaned = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    return sum(cleaned) / len(cleaned) if cleaned else None


def _max_drawdown(values: Sequence[float]) -> float:
    peak = 0.0
    cumulative = 0.0
    max_dd = 0.0
    for value in values:
        cumulative += value
        peak = max(peak, cumulative)
        max_dd = max(max_dd, peak - cumulative)
    return max_dd


def _optional_round(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return round(result, 6)


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _bps_to_rate(value: float) -> float:
    return float(value) / 10_000.0


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    return str(value)


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(number):
        return "n/a"
    return f"{number:.3f}"

