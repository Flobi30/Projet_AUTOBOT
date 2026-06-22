"""Portfolio-aware research replay for High Conviction swing setups.

The discovery runner intentionally evaluates each setup independently. This
module is the stricter next step: it replays those setups chronologically with
finite cash, one open position per symbol, bounded exposure, cooldowns, and
drawdown/day-loss brakes. It is research-only and has no runtime or Kraken
dependencies.
"""

from __future__ import annotations

import json
import math
from bisect import bisect_right
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Iterable, Literal, Sequence

from .execution_cost_model import ExecutionCostConfig, execution_cost_config_for_profile
from .high_conviction_discovery import (
    DEFAULT_EXIT_MODES,
    DEFAULT_SETUP_FAMILIES,
    DiscoveryScenario,
    DiscoverySetup,
    DiscoveryTrade,
    HighConvictionDiscoveryConfig,
    _discover_setups,
    _future_5m_path,
    _group_by_symbol_timeframe,
    _load_ohlcv_bars,
    _simulate_trade,
    _with_resampled_4h,
)
from .market_data_repository import MarketBar
from .metrics_engine import MetricsEngine, MetricsResult
from .trade_journal import TradeJournal, TradeRecord


PortfolioPolicyName = Literal["conservative", "dynamic_scaling"]


@dataclass(frozen=True)
class HighConvictionPortfolioConfig:
    run_id: str
    data_paths: tuple[Path, ...]
    output_dir: Path = Path("reports/research/high_conviction_portfolio")
    symbols: tuple[str, ...] = ()
    setup_families: tuple[str, ...] = DEFAULT_SETUP_FAMILIES
    min_expected_move_bps: tuple[float, ...] = (200.0, 500.0, 1000.0)
    risk_reward_ratios: tuple[float, ...] = (2.0, 3.0)
    max_hold_hours: tuple[float, ...] = (24.0, 72.0)
    exit_modes: tuple[str, ...] = DEFAULT_EXIT_MODES
    cost_profiles: tuple[str, ...] = ("research_stress", "paper_current_taker")
    initial_capital_eur: float = 500.0
    legacy_notional_eur: float = 100.0
    max_position_fraction: float = 0.20
    risk_per_trade_pct: float = 0.01
    max_global_exposure_pct: float = 0.60
    max_open_positions: int = 3
    cooldown_hours: float = 6.0
    max_daily_loss_pct: float = 0.03
    critical_drawdown_pct: float = 0.12
    drawdown_reduce_start_pct: float = 0.05
    min_drawdown_exposure_multiplier: float = 0.35
    min_sample_trades_for_candidate: int = 30
    candidate_min_profit_factor: float = 1.20
    candidate_max_drawdown_pct: float = 0.12

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id must not be empty")
        if not self.data_paths:
            raise ValueError("data_paths must not be empty")
        for value in (
            self.initial_capital_eur,
            self.legacy_notional_eur,
            self.max_position_fraction,
            self.risk_per_trade_pct,
            self.max_global_exposure_pct,
            self.cooldown_hours,
            self.max_daily_loss_pct,
            self.critical_drawdown_pct,
            self.drawdown_reduce_start_pct,
            self.min_drawdown_exposure_multiplier,
        ):
            if not math.isfinite(float(value)) or float(value) <= 0.0:
                raise ValueError("portfolio numeric inputs must be positive and finite")
        if (
            self.max_position_fraction > 1.0
            or self.risk_per_trade_pct > 1.0
            or self.max_global_exposure_pct > 1.0
            or self.max_daily_loss_pct > 1.0
        ):
            raise ValueError("portfolio risk and exposure fractions must not exceed 1")
        if self.critical_drawdown_pct >= 1.0:
            raise ValueError("critical_drawdown_pct must be below 1")
        if self.drawdown_reduce_start_pct >= self.critical_drawdown_pct:
            raise ValueError("drawdown_reduce_start_pct must be below critical_drawdown_pct")
        if not 0.0 < self.min_drawdown_exposure_multiplier <= 1.0:
            raise ValueError("min_drawdown_exposure_multiplier must be in (0, 1]")
        if self.max_open_positions < 1:
            raise ValueError("max_open_positions must be positive")
        if not self.cost_profiles:
            raise ValueError("cost_profiles must not be empty")
        for profile in self.cost_profiles:
            execution_cost_config_for_profile(profile).validate()


@dataclass(frozen=True)
class PortfolioScenarioResult:
    scenario: dict[str, Any]
    cost_profile: str
    policy: PortfolioPolicyName
    initial_capital_eur: float
    final_equity_eur: float
    net_pnl_eur: float
    total_return_pct: float
    trade_count: int
    profit_factor: float | None
    winrate_pct: float | None
    expectancy_eur: float | None
    max_drawdown_eur: float
    max_drawdown_pct: float
    average_exposure_pct: float
    max_exposure_pct: float
    max_allocated_exposure_pct: float
    average_notional_eur: float | None
    max_notional_eur: float | None
    average_trade_duration_minutes: float | None
    total_fees_eur: float
    total_spread_cost_eur: float
    total_slippage_eur: float
    total_latency_cost_eur: float
    rejected_entries: dict[str, int]
    daily_loss_stop_days: tuple[str, ...]
    critical_drawdown_stop: bool
    contributors: tuple[dict[str, Any], ...]
    losing_periods: tuple[dict[str, Any], ...]
    equity_curve: tuple[dict[str, Any], ...]
    sample_trades: tuple[dict[str, Any], ...]
    status: str
    blockers: tuple[str, ...]
    live_promotion_allowed: bool = False
    # Retained in memory for aggregate research such as walk-forward. Persisted
    # reports intentionally keep only representative sample trades.
    trade_records: tuple[TradeRecord, ...] = field(default_factory=tuple, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("trade_records", None)
        payload["blockers"] = list(self.blockers)
        payload["daily_loss_stop_days"] = list(self.daily_loss_stop_days)
        payload["contributors"] = [dict(row) for row in self.contributors]
        payload["losing_periods"] = [dict(row) for row in self.losing_periods]
        payload["equity_curve"] = [dict(row) for row in self.equity_curve]
        payload["sample_trades"] = [dict(row) for row in self.sample_trades]
        return payload


@dataclass(frozen=True)
class LegacyScenarioResult:
    scenario: dict[str, Any]
    cost_profile: str
    fixed_notional_eur: float
    trade_count: int
    net_pnl_eur: float
    profit_factor: float | None
    winrate_pct: float | None
    max_drawdown_pct: float
    reason: str = "independent_setup_replay_without_portfolio_constraints"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HighConvictionPortfolioReport:
    run_id: str
    generated_at: str
    data_paths: tuple[str, ...]
    symbols: tuple[str, ...]
    setup_count: int
    scenario_count: int
    expected_move_distribution: dict[str, int]
    portfolio_config: dict[str, Any]
    legacy_results: tuple[LegacyScenarioResult, ...]
    portfolio_results: tuple[PortfolioScenarioResult, ...]
    best_legacy_result: dict[str, Any] | None
    best_portfolio_result: dict[str, Any] | None
    comparison: dict[str, Any]
    conclusion: str
    recommendations: tuple[str, ...]
    json_report_path: str | None = None
    markdown_report_path: str | None = None
    live_promotion_allowed: bool = False
    safety_notes: tuple[str, ...] = (
        "Research-only portfolio replay.",
        "No runtime paper/live component is modified by this command.",
        "No Kraken order can be created by this command.",
        "No strategy promotion, live permission, leverage or instance split is enabled.",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "data_paths": list(self.data_paths),
            "symbols": list(self.symbols),
            "setup_count": self.setup_count,
            "scenario_count": self.scenario_count,
            "expected_move_distribution": dict(self.expected_move_distribution),
            "portfolio_config": dict(self.portfolio_config),
            "legacy_results": [row.to_dict() for row in self.legacy_results],
            "portfolio_results": [row.to_dict() for row in self.portfolio_results],
            "best_legacy_result": self.best_legacy_result,
            "best_portfolio_result": self.best_portfolio_result,
            "comparison": dict(self.comparison),
            "conclusion": self.conclusion,
            "recommendations": list(self.recommendations),
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
            "live_promotion_allowed": self.live_promotion_allowed,
            "safety_notes": list(self.safety_notes),
        }


@dataclass(frozen=True)
class _Candidate:
    setup: DiscoverySetup
    trade: DiscoveryTrade
    entry_at: datetime
    exit_at: datetime

    @property
    def selection_score(self) -> tuple[float, float, float, str]:
        return (
            self.setup.risk_reward_estimate,
            self.setup.expected_move_bps,
            -self.setup.logical_stop_bps,
            self.setup.family,
        )


@dataclass
class _OpenPosition:
    candidate: _Candidate
    notional_eur: float
    round_trip_cost_rate: float


class _PriceBook:
    def __init__(self, groups: dict[tuple[str, str], list[MarketBar]]) -> None:
        self._rows: dict[str, list[MarketBar]] = {
            symbol: list(rows)
            for (symbol, timeframe), rows in groups.items()
            if timeframe == "5m"
        }
        self._timestamps = {
            symbol: [bar.timestamp for bar in rows]
            for symbol, rows in self._rows.items()
        }

    def price(self, symbol: str, at: datetime, *, field: str = "close", fallback: float) -> float:
        rows = self._rows.get(symbol, [])
        timestamps = self._timestamps.get(symbol, [])
        index = bisect_right(timestamps, at) - 1
        if index < 0 or index >= len(rows):
            return fallback
        value = getattr(rows[index], field, fallback)
        return float(value) if isinstance(value, (int, float)) and float(value) > 0.0 else fallback

    def timeline(self) -> tuple[datetime, ...]:
        return tuple(sorted({bar.timestamp for rows in self._rows.values() for bar in rows}))


def build_high_conviction_portfolio_report(
    config: HighConvictionPortfolioConfig,
) -> HighConvictionPortfolioReport:
    discovery_config = HighConvictionDiscoveryConfig(
        run_id=config.run_id,
        data_paths=config.data_paths,
        symbols=config.symbols,
        setup_families=config.setup_families,  # type: ignore[arg-type]
        min_expected_move_bps=config.min_expected_move_bps,
        risk_reward_ratios=config.risk_reward_ratios,
        max_hold_hours=config.max_hold_hours,
        exit_modes=config.exit_modes,  # type: ignore[arg-type]
        initial_capital_eur=config.initial_capital_eur,
        order_notional_eur=config.legacy_notional_eur,
    )
    bars = _load_ohlcv_bars(discovery_config)
    groups = _with_resampled_4h(_group_by_symbol_timeframe(bars))
    setups = tuple(_discover_setups(discovery_config, groups))
    price_book = _PriceBook(groups)
    scenarios = _scenarios(config)
    legacy_results: list[LegacyScenarioResult] = []
    portfolio_results: list[PortfolioScenarioResult] = []

    for profile in config.cost_profiles:
        cost_config = execution_cost_config_for_profile(profile)
        scenario_config = replace(discovery_config, cost_config=cost_config)
        for scenario in scenarios:
            candidates = _candidates_for_scenario(scenario_config, scenario, setups, groups)
            legacy_results.append(_legacy_result(config, scenario, profile, candidates))
            for policy in ("conservative", "dynamic_scaling"):
                portfolio_results.append(
                    _run_portfolio_scenario(
                        config,
                        scenario,
                        profile,
                        policy,
                        candidates,
                        price_book,
                        cost_config,
                    )
                )

    best_legacy = _best_legacy(legacy_results)
    best_portfolio = _best_portfolio(portfolio_results)
    best_portfolio_index = next(
        (index for index, row in enumerate(portfolio_results) if row is best_portfolio),
        None,
    )
    # Full 5m equity curves for every trial make a research report enormous
    # without adding decision value. Preserve them only for the selected result;
    # every scenario still retains all comparable performance metrics.
    compact_portfolio_results = tuple(
        row
        if index == best_portfolio_index
        else replace(row, equity_curve=(), sample_trades=())
        for index, row in enumerate(portfolio_results)
    )
    comparison = _comparison(legacy_results, best_legacy, best_portfolio)
    conclusion, recommendations = _conclusion(best_portfolio)
    return HighConvictionPortfolioReport(
        run_id=config.run_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        data_paths=tuple(str(path) for path in config.data_paths),
        symbols=tuple(sorted({bar.symbol for bar in bars})),
        setup_count=len(setups),
        scenario_count=len(scenarios),
        expected_move_distribution=_expected_move_distribution(setups),
        portfolio_config=_public_config(config),
        legacy_results=tuple(legacy_results),
        portfolio_results=compact_portfolio_results,
        best_legacy_result=best_legacy.to_dict() if best_legacy else None,
        best_portfolio_result=best_portfolio.to_dict() if best_portfolio else None,
        comparison=comparison,
        conclusion=conclusion,
        recommendations=recommendations,
    )


def write_high_conviction_portfolio_report(
    report: HighConvictionPortfolioReport,
    output_dir: str | Path,
) -> HighConvictionPortfolioReport:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / f"{report.run_id}.json"
    markdown_path = output / f"{report.run_id}.md"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(render_high_conviction_portfolio_report(report), encoding="utf-8")
    return replace(report, json_report_path=str(json_path), markdown_report_path=str(markdown_path))


def render_high_conviction_portfolio_report(report: HighConvictionPortfolioReport) -> str:
    lines = [
        f"# High Conviction Portfolio Replay - {report.run_id}",
        "",
        "## Scope",
        "",
        f"- Initial capital: `{_fmt(report.portfolio_config['initial_capital_eur'])} EUR`",
        f"- Setups scanned: `{report.setup_count}`",
        f"- Scenario variants tested: `{report.scenario_count}` per cost profile and sizing policy",
        f"- Symbols: `{', '.join(report.symbols)}`",
        "- Mode: `research_only`, no runtime order or promotion.",
        "",
        "## Legacy Independent Replay",
        "",
        "| Cost Profile | Scenario | Trades | Net PnL EUR | PF | Winrate | Max DD % |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in sorted(report.legacy_results, key=lambda item: item.net_pnl_eur, reverse=True)[:12]:
        lines.append(
            f"| {row.cost_profile} | {row.scenario['label']} | {row.trade_count} | "
            f"{_fmt(row.net_pnl_eur)} | {_fmt(row.profit_factor)} | {_fmt(row.winrate_pct)} | {_fmt(row.max_drawdown_pct)} |"
        )
    lines.extend([
        "",
        "## Portfolio-Aware Replay",
        "",
        "| Cost Profile | Policy | Scenario | Trades | Final Equity EUR | Net PnL EUR | PF | Winrate | Max DD % | Planned Exposure % | Marked Exposure % |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    for row in sorted(report.portfolio_results, key=lambda item: item.net_pnl_eur, reverse=True)[:24]:
        lines.append(
            f"| {row.cost_profile} | {row.policy} | {row.scenario['label']} | {row.trade_count} | "
            f"{_fmt(row.final_equity_eur)} | {_fmt(row.net_pnl_eur)} | {_fmt(row.profit_factor)} | "
            f"{_fmt(row.winrate_pct)} | {_fmt(row.max_drawdown_pct)} | {_fmt(row.max_allocated_exposure_pct)} | "
            f"{_fmt(row.max_exposure_pct)} |"
        )
    best = report.best_portfolio_result or {}
    lines.extend(["", "## Best Portfolio Result", ""])
    if best:
        for key in (
            "cost_profile",
            "policy",
            "scenario",
            "final_equity_eur",
            "net_pnl_eur",
            "profit_factor",
            "winrate_pct",
            "max_drawdown_pct",
            "average_exposure_pct",
            "max_allocated_exposure_pct",
            "max_exposure_pct",
            "critical_drawdown_stop",
            "blockers",
        ):
            lines.append(f"- {key}: `{best.get(key)}`")
        lines.extend(["", "### Pair Contributors", "", "| Symbol | Trades | Net PnL EUR |", "| --- | ---: | ---: |"])
        for row in best.get("contributors", [])[:12]:
            lines.append(f"| {row.get('symbol')} | {row.get('trade_count')} | {_fmt(row.get('net_pnl_eur'))} |")
        lines.extend(["", "### Losing Periods", ""])
        for row in best.get("losing_periods", [])[:10]:
            lines.append(f"- `{row.get('date')}`: `{_fmt(row.get('net_pnl_eur'))} EUR`")
    lines.extend(["", "## Comparison", ""])
    for key, value in report.comparison.items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Conclusion", "", f"`{report.conclusion}`", "", "## Recommendations", ""])
    lines.extend(f"- {item}" for item in report.recommendations)
    lines.extend(["", "## Safety", ""])
    lines.extend(f"- {item}" for item in report.safety_notes)
    lines.append(f"- live_promotion_allowed: `{report.live_promotion_allowed}`")
    return "\n".join(lines) + "\n"


def _scenarios(config: HighConvictionPortfolioConfig) -> tuple[DiscoveryScenario, ...]:
    return tuple(
        DiscoveryScenario(
            min_expected_move_bps=float(minimum),
            risk_reward_ratio=float(risk_reward),
            max_hold_hours=float(max_hold),
            exit_mode=str(mode),  # type: ignore[arg-type]
        )
        for minimum in config.min_expected_move_bps
        for risk_reward in config.risk_reward_ratios
        for max_hold in config.max_hold_hours
        for mode in config.exit_modes
    )


def _candidates_for_scenario(
    config: HighConvictionDiscoveryConfig,
    scenario: DiscoveryScenario,
    setups: Sequence[DiscoverySetup],
    groups: dict[tuple[str, str], list[MarketBar]],
) -> tuple[_Candidate, ...]:
    candidates: list[_Candidate] = []
    for setup in setups:
        if setup.expected_move_bps < scenario.min_expected_move_bps:
            continue
        if setup.risk_reward_estimate < scenario.risk_reward_ratio:
            continue
        path = _future_5m_path(groups.get((setup.symbol, "5m"), []), setup.entry_at, scenario.max_hold_hours)
        if not path:
            continue
        trade = _simulate_trade(config, scenario, setup, path)
        if trade is None:
            continue
        candidates.append(
            _Candidate(
                setup=setup,
                trade=trade,
                entry_at=_parse_timestamp(setup.entry_at),
                exit_at=_parse_timestamp(trade.exit_at),
            )
        )
    return tuple(sorted(candidates, key=lambda item: (item.entry_at, item.setup.symbol)))


def _legacy_result(
    config: HighConvictionPortfolioConfig,
    scenario: DiscoveryScenario,
    cost_profile: str,
    candidates: Sequence[_Candidate],
) -> LegacyScenarioResult:
    cost_config = execution_cost_config_for_profile(cost_profile)
    records = [
        _trade_record(
            config.run_id,
            candidate,
            config.legacy_notional_eur,
            "legacy_independent",
            cost_config,
        )
        for candidate in candidates
    ]
    metrics = MetricsEngine().calculate(records, initial_capital_eur=config.initial_capital_eur)
    return LegacyScenarioResult(
        scenario=scenario.to_dict(),
        cost_profile=cost_profile,
        fixed_notional_eur=config.legacy_notional_eur,
        trade_count=metrics.trade_count,
        net_pnl_eur=round(metrics.total_net_pnl_eur, 6),
        profit_factor=metrics.profit_factor,
        winrate_pct=metrics.winrate_pct,
        max_drawdown_pct=metrics.max_drawdown_pct,
    )


def _run_portfolio_scenario(
    config: HighConvictionPortfolioConfig,
    scenario: DiscoveryScenario,
    cost_profile: str,
    policy: PortfolioPolicyName,
    candidates: Sequence[_Candidate],
    price_book: _PriceBook,
    cost_config: ExecutionCostConfig,
) -> PortfolioScenarioResult:
    candidate_by_entry: dict[datetime, list[_Candidate]] = defaultdict(list)
    for candidate in candidates:
        candidate_by_entry[candidate.entry_at].append(candidate)
    timeline = sorted(set(price_book.timeline()) | set(candidate_by_entry))
    cash = float(config.initial_capital_eur)
    peak_equity = cash
    max_drawdown_eur = 0.0
    max_drawdown_pct = 0.0
    open_positions: list[_OpenPosition] = []
    cooldown_until: dict[str, datetime] = {}
    records: list[TradeRecord] = []
    rejected = Counter()
    daily_pnl: dict[date, float] = defaultdict(float)
    daily_start_equity: dict[date, float] = {}
    daily_stopped: set[date] = set()
    critical_drawdown_stop = False
    exposure_values: list[float] = []
    allocated_exposure_values: list[float] = []
    equity_curve: list[dict[str, Any]] = []
    # Open-position equity is marked net of the expected exit as well as entry
    # costs. Otherwise a portfolio can appear healthier than it would be if it
    # had to liquidate at the current bar.
    round_trip_cost_rate = cost_config.round_trip_cost_estimate_bps() / 10_000.0

    def mark_equity(
        at: datetime,
        *,
        conservative_low: bool,
        update_peak: bool,
    ) -> tuple[float, float]:
        nonlocal peak_equity, max_drawdown_eur, max_drawdown_pct
        open_value = 0.0
        gross_exposure = 0.0
        for position in open_positions:
            field = "low" if conservative_low else "close"
            price = price_book.price(
                position.candidate.setup.symbol,
                at,
                field=field,
                fallback=position.candidate.setup.entry_price,
            )
            gross_return = ((price - position.candidate.setup.entry_price) / position.candidate.setup.entry_price)
            open_value += position.notional_eur * max(0.0, 1.0 + gross_return - position.round_trip_cost_rate)
            gross_exposure += position.notional_eur * max(
                0.0,
                price / max(position.candidate.setup.entry_price, 1e-12),
            )
        equity = max(0.0, cash + open_value)
        if update_peak:
            peak_equity = max(peak_equity, equity)
        drawdown = max(0.0, peak_equity - equity)
        drawdown_pct = (drawdown / peak_equity) if peak_equity > 0.0 else 0.0
        max_drawdown_eur = max(max_drawdown_eur, drawdown)
        max_drawdown_pct = max(max_drawdown_pct, drawdown_pct)
        return equity, gross_exposure

    def allocated_exposure_pct() -> float:
        allocated = sum(position.notional_eur for position in open_positions)
        allocation_equity = cash + sum(
            position.notional_eur * (1.0 - position.round_trip_cost_rate)
            for position in open_positions
        )
        return (allocated / allocation_equity * 100.0) if allocation_equity > 0.0 else 0.0

    for current_time in timeline:
        current_day = current_time.date()
        close_equity, _ = mark_equity(current_time, conservative_low=False, update_peak=True)
        daily_start_equity.setdefault(current_day, close_equity)

        remaining: list[_OpenPosition] = []
        for position in open_positions:
            if position.candidate.exit_at > current_time:
                remaining.append(position)
                continue
            record = _trade_record(
                config.run_id,
                position.candidate,
                position.notional_eur,
                policy,
                cost_config,
            )
            cash += position.notional_eur + record.net_pnl_eur
            records.append(record)
            cooldown_until[position.candidate.setup.symbol] = position.candidate.exit_at + timedelta(hours=config.cooldown_hours)
            daily_pnl[position.candidate.exit_at.date()] += record.net_pnl_eur
        open_positions = remaining

        equity, exposure = mark_equity(current_time, conservative_low=False, update_peak=True)
        adverse_equity, _ = mark_equity(current_time, conservative_low=True, update_peak=False)
        if adverse_equity <= 0.0 or max_drawdown_pct >= config.critical_drawdown_pct:
            critical_drawdown_stop = True

        day_start = daily_start_equity[current_day]
        if daily_pnl[current_day] <= -(day_start * config.max_daily_loss_pct):
            daily_stopped.add(current_day)

        for candidate in sorted(candidate_by_entry.get(current_time, []), key=lambda item: item.selection_score, reverse=True):
            symbol = candidate.setup.symbol
            if critical_drawdown_stop:
                rejected["critical_drawdown_stop"] += 1
                continue
            if current_day in daily_stopped:
                rejected["daily_loss_stop"] += 1
                continue
            if any(position.candidate.setup.symbol == symbol for position in open_positions):
                rejected["one_position_per_symbol"] += 1
                continue
            if cooldown_until.get(symbol, datetime.min.replace(tzinfo=timezone.utc)) > current_time:
                rejected["symbol_cooldown"] += 1
                continue
            if len(open_positions) >= config.max_open_positions:
                rejected["max_open_positions"] += 1
                continue

            equity, exposure = mark_equity(current_time, conservative_low=False, update_peak=True)
            multiplier = _drawdown_exposure_multiplier(config, max_drawdown_pct)
            size_equity = equity if policy == "dynamic_scaling" else min(equity, config.initial_capital_eur)
            position_cap = size_equity * config.max_position_fraction * multiplier
            stop_rate = max(candidate.setup.logical_stop_bps / 10_000.0, 1e-9)
            risk_cap = equity * config.risk_per_trade_pct / stop_rate
            target_exposure = equity * config.max_global_exposure_pct * multiplier
            max_new_exposure = max(
                0.0,
                (target_exposure - exposure)
                / max(1.0 + (config.max_global_exposure_pct * multiplier * round_trip_cost_rate), 1e-12),
            )
            notional = min(
                position_cap,
                risk_cap,
                max_new_exposure,
                cash / max(1.0 + round_trip_cost_rate, 1e-12),
            )
            if notional < cost_config.min_notional_eur:
                rejected["insufficient_cash_or_exposure"] += 1
                continue

            cash -= notional
            open_positions.append(
                _OpenPosition(
                    candidate=candidate,
                    notional_eur=notional,
                    round_trip_cost_rate=round_trip_cost_rate,
                )
            )
            equity, exposure = mark_equity(current_time, conservative_low=False, update_peak=True)
            allocated_exposure_values.append(allocated_exposure_pct())

        equity, exposure = mark_equity(current_time, conservative_low=False, update_peak=True)
        exposure_pct = (exposure / equity * 100.0) if equity > 0.0 else 0.0
        exposure_values.append(exposure_pct)
        equity_curve.append(
            {
                "timestamp": current_time.isoformat(),
                "equity_eur": round(equity, 6),
                "cash_eur": round(cash, 6),
                "exposure_eur": round(exposure, 6),
                "exposure_pct": round(exposure_pct, 6),
                "open_positions": len(open_positions),
            }
        )

    # Every candidate has a known exit inside the usable OHLCV horizon. The
    # loop above normally settles all positions; this guard keeps accounting
    # closed if a malformed timestamp ever falls outside the shared timeline.
    for position in sorted(open_positions, key=lambda item: item.candidate.exit_at):
        record = _trade_record(
            config.run_id,
            position.candidate,
            position.notional_eur,
            policy,
            cost_config,
        )
        cash += position.notional_eur + record.net_pnl_eur
        records.append(record)

    journal = TradeJournal(records)
    metrics = MetricsEngine().calculate(journal.records, initial_capital_eur=config.initial_capital_eur)
    contributors = _contributors(records)
    blockers = _portfolio_blockers(
        config,
        metrics,
        contributors,
        critical_drawdown_stop,
        max_drawdown_pct,
    )
    return PortfolioScenarioResult(
        scenario=scenario.to_dict(),
        cost_profile=cost_profile,
        policy=policy,
        initial_capital_eur=config.initial_capital_eur,
        final_equity_eur=round(cash, 6),
        net_pnl_eur=round(metrics.total_net_pnl_eur, 6),
        total_return_pct=round((cash - config.initial_capital_eur) / config.initial_capital_eur * 100.0, 6),
        trade_count=metrics.trade_count,
        profit_factor=metrics.profit_factor,
        winrate_pct=metrics.winrate_pct,
        expectancy_eur=metrics.expectancy_eur,
        max_drawdown_eur=round(max_drawdown_eur, 6),
        max_drawdown_pct=round(max_drawdown_pct * 100.0, 6),
        average_exposure_pct=round(mean(exposure_values), 6) if exposure_values else 0.0,
        max_exposure_pct=round(max(exposure_values), 6) if exposure_values else 0.0,
        max_allocated_exposure_pct=round(max(allocated_exposure_values), 6) if allocated_exposure_values else 0.0,
        average_notional_eur=round(mean([record.quantity * record.entry_price for record in records]), 6) if records else None,
        max_notional_eur=round(max([record.quantity * record.entry_price for record in records]), 6) if records else None,
        average_trade_duration_minutes=(metrics.average_trade_duration_seconds / 60.0) if metrics.average_trade_duration_seconds is not None else None,
        total_fees_eur=round(metrics.total_fees_eur, 6),
        total_spread_cost_eur=round(metrics.total_spread_cost_eur, 6),
        total_slippage_eur=round(metrics.total_slippage_eur, 6),
        total_latency_cost_eur=round(metrics.total_latency_cost_eur, 6),
        rejected_entries=dict(sorted(rejected.items())),
        daily_loss_stop_days=tuple(sorted(day.isoformat() for day in daily_stopped)),
        critical_drawdown_stop=critical_drawdown_stop,
        contributors=tuple(contributors),
        losing_periods=tuple(_losing_periods(daily_pnl)),
        equity_curve=tuple(equity_curve),
        sample_trades=tuple(record.to_dict() for record in sorted(records, key=lambda row: row.net_pnl_eur, reverse=True)[:16]),
        status="research_only",
        blockers=tuple(blockers),
        trade_records=tuple(records),
    )


def _trade_record(
    run_id: str,
    candidate: _Candidate,
    notional: float,
    policy: str,
    cost_config: ExecutionCostConfig,
) -> TradeRecord:
    trade = candidate.trade
    gross_pnl = notional * trade.gross_return_bps / 10_000.0
    net_pnl = notional * trade.net_return_bps / 10_000.0
    cost = max(0.0, gross_pnl - net_pnl)
    fee_share, spread_share, slippage_share, latency_share = _cost_breakdown(cost_config)
    return TradeRecord(
        run_id=run_id,
        strategy_id="high_conviction_swing",
        symbol=trade.symbol,
        side=trade.side,
        opened_at=candidate.entry_at,
        closed_at=candidate.exit_at,
        quantity=notional / max(trade.entry_price, 1e-12),
        entry_price=trade.entry_price,
        exit_price=trade.exit_price,
        gross_pnl_eur=gross_pnl,
        net_pnl_eur=net_pnl,
        fees_eur=cost * fee_share,
        spread_cost_eur=cost * spread_share,
        slippage_eur=cost * slippage_share,
        latency_cost_eur=cost * latency_share,
        entry_reason=candidate.setup.reason,
        exit_reason=trade.exit_reason,
        metadata={
            "family": trade.family,
            "policy": policy,
            "expected_move_bps": trade.expected_move_bps,
            "logical_stop_bps": trade.logical_stop_bps,
            "mfe_bps": trade.mfe_bps,
            "mae_bps": trade.mae_bps,
            "cost_bps": trade.cost_bps,
        },
    )


def _cost_breakdown(cost_config: ExecutionCostConfig) -> tuple[float, float, float, float]:
    """Return the canonical profile cost proportions for report attribution."""
    entry_type = cost_config.default_entry_order_type
    exit_type = cost_config.default_exit_order_type
    fee_bps = cost_config.fee_for_order_type(entry_type) + cost_config.fee_for_order_type(exit_type)
    spread_bps = cost_config.fallback_spread_bps * (
        cost_config.spread_charge_fraction(entry_type) / 2.0
        + cost_config.spread_charge_fraction(exit_type) / 2.0
    )
    slippage_bps = 2.0 * cost_config.slippage_bps
    latency_bps = 2.0 * cost_config.latency_buffer_bps
    total = max(fee_bps + spread_bps + slippage_bps + latency_bps, 1e-12)
    return (
        fee_bps / total,
        spread_bps / total,
        slippage_bps / total,
        latency_bps / total,
    )


def _drawdown_exposure_multiplier(config: HighConvictionPortfolioConfig, drawdown_pct: float) -> float:
    if drawdown_pct <= config.drawdown_reduce_start_pct:
        return 1.0
    progress = (drawdown_pct - config.drawdown_reduce_start_pct) / max(
        config.critical_drawdown_pct - config.drawdown_reduce_start_pct,
        1e-12,
    )
    return max(
        config.min_drawdown_exposure_multiplier,
        1.0 - (min(1.0, progress) * (1.0 - config.min_drawdown_exposure_multiplier)),
    )


def _contributors(records: Sequence[TradeRecord]) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for record in records:
        row = rows.setdefault(record.symbol, {"symbol": record.symbol, "trade_count": 0, "net_pnl_eur": 0.0})
        row["trade_count"] += 1
        row["net_pnl_eur"] += record.net_pnl_eur
    return [
        {"symbol": row["symbol"], "trade_count": row["trade_count"], "net_pnl_eur": round(row["net_pnl_eur"], 6)}
        for row in sorted(rows.values(), key=lambda item: item["net_pnl_eur"], reverse=True)
    ]


def _losing_periods(daily_pnl: dict[date, float]) -> list[dict[str, Any]]:
    return [
        {"date": day.isoformat(), "net_pnl_eur": round(value, 6)}
        for day, value in sorted(daily_pnl.items(), key=lambda item: item[1])
        if value < 0.0
    ]


def _portfolio_blockers(
    config: HighConvictionPortfolioConfig,
    metrics: MetricsResult,
    contributors: Sequence[dict[str, Any]],
    critical_drawdown_stop: bool,
    intrabar_max_drawdown_pct: float,
) -> list[str]:
    blockers = ["research_only_no_auto_promotion"]
    if metrics.trade_count < config.min_sample_trades_for_candidate:
        blockers.append("sample_size_below_candidate_minimum")
    if metrics.total_net_pnl_eur <= 0.0:
        blockers.append("net_pnl_not_positive_after_costs")
    if metrics.profit_factor is None or metrics.profit_factor < config.candidate_min_profit_factor:
        blockers.append("profit_factor_below_candidate_minimum")
    if intrabar_max_drawdown_pct > config.candidate_max_drawdown_pct:
        blockers.append("drawdown_above_candidate_maximum")
    if critical_drawdown_stop:
        blockers.append("critical_drawdown_stop_triggered")
    if contributors:
        dominant = max(abs(float(row["net_pnl_eur"])) for row in contributors)
        total = abs(metrics.total_net_pnl_eur)
        if total > 0.0 and dominant / total >= 0.70:
            blockers.append("single_symbol_concentration_requires_review")
    return blockers


def _best_legacy(rows: Sequence[LegacyScenarioResult]) -> LegacyScenarioResult | None:
    return max(rows, key=lambda row: (row.net_pnl_eur, row.profit_factor or 0.0), default=None)


def _best_portfolio(rows: Sequence[PortfolioScenarioResult]) -> PortfolioScenarioResult | None:
    return max(
        rows,
        key=lambda row: (
            row.net_pnl_eur > 0.0 and row.max_drawdown_pct <= 12.0 and not row.critical_drawdown_stop,
            row.net_pnl_eur,
            row.profit_factor or 0.0,
            -row.max_drawdown_pct,
        ),
        default=None,
    )


def _comparison(
    legacy_rows: Sequence[LegacyScenarioResult],
    best_legacy: LegacyScenarioResult | None,
    portfolio: PortfolioScenarioResult | None,
) -> dict[str, Any]:
    if best_legacy is None or portfolio is None:
        return {"status": "insufficient_trades_for_comparison"}
    matching_legacy = next(
        (
            row
            for row in legacy_rows
            if row.cost_profile == portfolio.cost_profile
            and row.scenario.get("label") == portfolio.scenario.get("label")
        ),
        None,
    )
    if matching_legacy is None:
        return {
            "status": "matching_legacy_scenario_missing",
            "best_legacy_non_portfolio_net_pnl_eur": best_legacy.net_pnl_eur,
            "portfolio_net_pnl_eur": portfolio.net_pnl_eur,
            "legacy_is_not_capital_feasible": True,
        }
    return {
        "matching_scenario_label": portfolio.scenario.get("label"),
        "matching_legacy_non_portfolio_net_pnl_eur": matching_legacy.net_pnl_eur,
        "portfolio_net_pnl_eur": portfolio.net_pnl_eur,
        "net_pnl_delta_eur": round(portfolio.net_pnl_eur - matching_legacy.net_pnl_eur, 6),
        "matching_legacy_max_drawdown_pct": matching_legacy.max_drawdown_pct,
        "portfolio_max_drawdown_pct": portfolio.max_drawdown_pct,
        "legacy_is_not_capital_feasible": True,
        "portfolio_enforces_cash_exposure_cooldown_and_one_position_per_symbol": True,
    }


def _conclusion(best: PortfolioScenarioResult | None) -> tuple[str, tuple[str, ...]]:
    if best is None or best.trade_count == 0:
        return (
            "no_usable_high_conviction_portfolio_result",
            ("Collect more OHLCV before drawing a strategy conclusion.",),
        )
    if "sample_size_below_candidate_minimum" in best.blockers:
        return (
            "high_conviction_insufficient_sample_for_validation",
            (
                "The portfolio replay is not evidence of viability yet: it has fewer than the configured closed-trade minimum.",
                "Treat every positive result as a research lead until longer OHLCV and walk-forward validation confirm it.",
            ),
        )
    if best.net_pnl_eur <= 0.0:
        return (
            "high_conviction_not_viable_on_current_portfolio_replay",
            (
                "Do not promote the swing engine; retain it as research-only.",
                "Use the rejected-entry and contributor diagnostics to investigate setup quality.",
            ),
        )
    if best.max_drawdown_pct > 12.0 or best.critical_drawdown_stop:
        return (
            "high_conviction_positive_but_risk_unacceptable",
            (
                "Positive independent PnL is not capital-feasible until portfolio drawdown is controlled.",
                "Keep the engine research-only and validate on a longer out-of-sample window.",
            ),
        )
    return (
        "high_conviction_research_signal_requires_walk_forward",
        (
            "A portfolio-aware result is promising but remains research-only.",
            "Require longer OHLCV, time-aligned spread/depth and walk-forward validation before controlled paper review.",
        ),
    )


def _expected_move_distribution(setups: Iterable[DiscoverySetup]) -> dict[str, int]:
    result = {"lt_200_bps": 0, "200_499_bps": 0, "500_999_bps": 0, "gte_1000_bps": 0}
    for setup in setups:
        if setup.expected_move_bps < 200.0:
            result["lt_200_bps"] += 1
        elif setup.expected_move_bps < 500.0:
            result["200_499_bps"] += 1
        elif setup.expected_move_bps < 1000.0:
            result["500_999_bps"] += 1
        else:
            result["gte_1000_bps"] += 1
    return result


def _public_config(config: HighConvictionPortfolioConfig) -> dict[str, Any]:
    return {
        "initial_capital_eur": config.initial_capital_eur,
        "legacy_notional_eur": config.legacy_notional_eur,
        "max_position_fraction": config.max_position_fraction,
        "risk_per_trade_pct": config.risk_per_trade_pct,
        "max_global_exposure_pct": config.max_global_exposure_pct,
        "max_open_positions": config.max_open_positions,
        "cooldown_hours": config.cooldown_hours,
        "max_daily_loss_pct": config.max_daily_loss_pct,
        "critical_drawdown_pct": config.critical_drawdown_pct,
        "drawdown_reduce_start_pct": config.drawdown_reduce_start_pct,
        "min_drawdown_exposure_multiplier": config.min_drawdown_exposure_multiplier,
        "cost_profiles": list(config.cost_profiles),
        "live_promotion_allowed": False,
    }


def _parse_timestamp(value: str) -> datetime:
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)
