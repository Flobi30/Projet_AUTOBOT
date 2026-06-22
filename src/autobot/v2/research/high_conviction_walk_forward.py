"""Out-of-sample, portfolio-aware validation for High Conviction swing research.

The module consumes locally collected OHLCV only. Every fold uses history as a
warm-up, accepts entries only in its out-of-sample window, and starts with a
finite portfolio. It cannot invoke runtime, paper execution, or Kraken APIs.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from .execution_cost_model import execution_cost_config_for_profile
from .high_conviction_discovery import (
    DEFAULT_SETUP_FAMILIES,
    DiscoveryScenario,
    HighConvictionDiscoveryConfig,
    _discover_setups,
    _group_by_symbol_timeframe,
    _load_ohlcv_bars,
    _with_resampled_4h,
)
from .high_conviction_portfolio import (
    HighConvictionPortfolioConfig,
    PortfolioPolicyName,
    PortfolioScenarioResult,
    _PriceBook,
    _candidates_for_scenario,
    _run_portfolio_scenario,
)
from .market_data_repository import MarketBar
from .metrics_engine import MetricsEngine
from .trade_journal import TradeRecord


@dataclass(frozen=True)
class HighConvictionWalkForwardConfig:
    run_id: str
    data_paths: tuple[Path, ...]
    output_dir: Path = Path("reports/research/high_conviction_walk_forward")
    symbols: tuple[str, ...] = ()
    setup_families: tuple[str, ...] = DEFAULT_SETUP_FAMILIES
    min_expected_move_bps: float = 500.0
    risk_reward_ratio: float = 2.0
    max_hold_hours: float = 72.0
    exit_modes: tuple[str, ...] = ("fixed_tp_sl", "trailing")
    primary_exit_mode: str = "fixed_tp_sl"
    cost_profiles: tuple[str, ...] = ("paper_current_taker", "research_stress")
    policies: tuple[PortfolioPolicyName, ...] = ("conservative", "dynamic_scaling")
    primary_cost_profile: str = "research_stress"
    primary_policy: PortfolioPolicyName = "conservative"
    initial_capital_eur: float = 500.0
    max_position_fraction: float = 0.20
    risk_per_trade_pct: float = 0.01
    max_global_exposure_pct: float = 0.60
    max_open_positions: int = 3
    cooldown_hours: float = 6.0
    max_daily_loss_pct: float = 0.03
    critical_drawdown_pct: float = 0.12
    drawdown_reduce_start_pct: float = 0.05
    min_drawdown_exposure_multiplier: float = 0.35
    train_window_bars: int = 288
    test_window_bars: int = 192
    step_window_bars: int | None = None
    min_folds: int = 3
    min_positive_fold_ratio: float = 0.60
    min_closed_trades_for_review: int = 50
    min_profit_factor: float = 1.20
    max_drawdown_pct: float = 0.12
    max_single_symbol_positive_pnl_share: float = 0.60

    def __post_init__(self) -> None:
        if not self.run_id.strip() or not self.data_paths:
            raise ValueError("run_id and data_paths are required")
        if not self.exit_modes or self.primary_exit_mode not in self.exit_modes:
            raise ValueError("primary_exit_mode must be one of exit_modes")
        if not self.cost_profiles or self.primary_cost_profile not in self.cost_profiles:
            raise ValueError("primary_cost_profile must be one of cost_profiles")
        if not self.policies or self.primary_policy not in self.policies:
            raise ValueError("primary_policy must be one of policies")
        if self.train_window_bars <= 0 or self.test_window_bars <= 0 or self.min_folds < 1:
            raise ValueError("walk-forward windows and folds must be positive")
        if self.step_window_bars is not None and self.step_window_bars <= 0:
            raise ValueError("step_window_bars must be positive")
        if self.min_closed_trades_for_review < 50:
            raise ValueError("at least 50 closed trades are required for review")
        for value in (
            self.min_expected_move_bps,
            self.risk_reward_ratio,
            self.max_hold_hours,
            self.initial_capital_eur,
            self.max_position_fraction,
            self.risk_per_trade_pct,
            self.max_global_exposure_pct,
            self.cooldown_hours,
            self.max_daily_loss_pct,
            self.critical_drawdown_pct,
            self.drawdown_reduce_start_pct,
            self.min_drawdown_exposure_multiplier,
            self.min_positive_fold_ratio,
            self.max_drawdown_pct,
            self.max_single_symbol_positive_pnl_share,
        ):
            if not math.isfinite(float(value)) or float(value) <= 0.0:
                raise ValueError("walk-forward numeric inputs must be positive and finite")
        if self.critical_drawdown_pct >= 1.0 or self.max_drawdown_pct >= 1.0:
            raise ValueError("drawdown thresholds must be below one")
        if self.drawdown_reduce_start_pct >= self.critical_drawdown_pct:
            raise ValueError("drawdown_reduce_start_pct must be below critical_drawdown_pct")
        if any(value > 1.0 for value in (self.max_position_fraction, self.risk_per_trade_pct, self.max_global_exposure_pct, self.min_positive_fold_ratio, self.max_single_symbol_positive_pnl_share)):
            raise ValueError("walk-forward fractions must not exceed one")
        for profile in self.cost_profiles:
            execution_cost_config_for_profile(profile).validate()


@dataclass(frozen=True)
class HighConvictionWalkForwardFoldResult:
    fold_index: int
    train_start_at: str
    train_end_at: str
    test_start_at: str
    test_end_at: str
    available_setups: int
    out_of_sample_setups: int
    scenario: dict[str, Any]
    cost_profile: str
    policy: str
    portfolio: PortfolioScenarioResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "fold_index": self.fold_index,
            "train_start_at": self.train_start_at,
            "train_end_at": self.train_end_at,
            "test_start_at": self.test_start_at,
            "test_end_at": self.test_end_at,
            "available_setups": self.available_setups,
            "out_of_sample_setups": self.out_of_sample_setups,
            "scenario": dict(self.scenario),
            "cost_profile": self.cost_profile,
            "policy": self.policy,
            "portfolio": self.portfolio.to_dict(),
        }


@dataclass(frozen=True)
class HighConvictionWalkForwardAggregate:
    scenario: dict[str, Any]
    cost_profile: str
    policy: str
    fold_count: int
    positive_fold_count: int
    total_trade_count: int
    total_net_pnl_eur: float
    profit_factor: float | None
    winrate_pct: float | None
    expectancy_eur: float | None
    worst_fold_drawdown_pct: float
    average_fold_drawdown_pct: float
    contributors: tuple[dict[str, Any], ...]
    losing_periods: tuple[dict[str, Any], ...]
    largest_positive_symbol_share: float | None
    is_single_symbol_dominated: bool
    live_promotion_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["contributors"] = [dict(row) for row in self.contributors]
        payload["losing_periods"] = [dict(row) for row in self.losing_periods]
        return payload


@dataclass(frozen=True)
class HighConvictionWalkForwardDecision:
    status: str
    reasons: tuple[str, ...]
    paper_candidate_allowed: bool = False
    live_promotion_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reasons": list(self.reasons),
            "paper_candidate_allowed": self.paper_candidate_allowed,
            "live_promotion_allowed": self.live_promotion_allowed,
        }


@dataclass(frozen=True)
class HighConvictionWalkForwardReport:
    run_id: str
    generated_at: str
    data_paths: tuple[str, ...]
    symbols: tuple[str, ...]
    input_bar_count: int
    deduplicated_bar_count: int
    duplicate_bar_count: int
    fold_count: int
    folds: tuple[HighConvictionWalkForwardFoldResult, ...]
    aggregates: tuple[HighConvictionWalkForwardAggregate, ...]
    primary_aggregate: dict[str, Any] | None
    decision: HighConvictionWalkForwardDecision
    json_report_path: str | None = None
    markdown_report_path: str | None = None
    live_promotion_allowed: bool = False
    safety_notes: tuple[str, ...] = (
        "Research-only High Conviction walk-forward validation.",
        "Every out-of-sample fold starts with finite 500 EUR-equivalent capital.",
        "No runtime paper/live component is modified by this command.",
        "No paper or Kraken order can be created by this command.",
        "No strategy or instance is promoted automatically.",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "data_paths": list(self.data_paths),
            "symbols": list(self.symbols),
            "input_bar_count": self.input_bar_count,
            "deduplicated_bar_count": self.deduplicated_bar_count,
            "duplicate_bar_count": self.duplicate_bar_count,
            "fold_count": self.fold_count,
            "folds": [fold.to_dict() for fold in self.folds],
            "aggregates": [aggregate.to_dict() for aggregate in self.aggregates],
            "primary_aggregate": dict(self.primary_aggregate) if self.primary_aggregate else None,
            "decision": self.decision.to_dict(),
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
            "live_promotion_allowed": self.live_promotion_allowed,
            "safety_notes": list(self.safety_notes),
        }


def build_high_conviction_walk_forward_report(
    config: HighConvictionWalkForwardConfig,
) -> HighConvictionWalkForwardReport:
    discovery_config = HighConvictionDiscoveryConfig(
        run_id=config.run_id,
        data_paths=config.data_paths,
        symbols=config.symbols,
        setup_families=config.setup_families,  # type: ignore[arg-type]
        min_expected_move_bps=(config.min_expected_move_bps,),
        risk_reward_ratios=(config.risk_reward_ratio,),
        max_hold_hours=(config.max_hold_hours,),
        exit_modes=config.exit_modes,  # type: ignore[arg-type]
        initial_capital_eur=config.initial_capital_eur,
        order_notional_eur=config.initial_capital_eur * config.max_position_fraction,
    )
    raw_bars = _load_ohlcv_bars(discovery_config)
    bars, duplicate_count = _deduplicate_bars(raw_bars)
    groups = _with_resampled_4h(_group_by_symbol_timeframe(bars))
    timeline = tuple(
        sorted(
            {
                bar.timestamp
                for (_symbol, timeframe), rows in groups.items()
                if timeframe == "15m"
                for bar in rows
            }
        )
    )
    windows = _fold_windows(config, timeline)
    folds: list[HighConvictionWalkForwardFoldResult] = []

    for fold_index, (train_start, train_end, test_start, test_end) in enumerate(windows, start=1):
        fold_groups = _groups_until(groups, test_end)
        setups = tuple(_discover_setups(discovery_config, fold_groups))
        price_book = _PriceBook(fold_groups)
        portfolio_config = _portfolio_config(config, run_id=f"{config.run_id}_fold_{fold_index:03d}")
        for scenario in _scenarios(config):
            for profile in config.cost_profiles:
                cost_config = execution_cost_config_for_profile(profile)
                candidates = _candidates_for_scenario(
                    replace(discovery_config, cost_config=cost_config),
                    scenario,
                    setups,
                    fold_groups,
                )
                out_of_sample = tuple(
                    candidate
                    for candidate in candidates
                    if candidate.entry_at >= test_start and candidate.exit_at <= test_end
                )
                for policy in config.policies:
                    portfolio = _run_portfolio_scenario(
                        portfolio_config,
                        scenario,
                        profile,
                        policy,
                        out_of_sample,
                        price_book,
                        cost_config,
                    )
                    folds.append(
                        HighConvictionWalkForwardFoldResult(
                            fold_index=fold_index,
                            train_start_at=train_start.isoformat(),
                            train_end_at=train_end.isoformat(),
                            test_start_at=test_start.isoformat(),
                            test_end_at=test_end.isoformat(),
                            available_setups=len(setups),
                            out_of_sample_setups=len(out_of_sample),
                            scenario=scenario.to_dict(),
                            cost_profile=profile,
                            policy=policy,
                            portfolio=portfolio,
                        )
                    )

    aggregates = _aggregates(config, folds)
    primary = next(
        (
            row
            for row in aggregates
            if row.cost_profile == config.primary_cost_profile
            and row.policy == config.primary_policy
            and row.scenario.get("exit_mode") == config.primary_exit_mode
        ),
        None,
    )
    return HighConvictionWalkForwardReport(
        run_id=config.run_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        data_paths=tuple(str(path) for path in config.data_paths),
        symbols=tuple(sorted({bar.symbol for bar in bars})),
        input_bar_count=len(raw_bars),
        deduplicated_bar_count=len(bars),
        duplicate_bar_count=duplicate_count,
        fold_count=len(windows),
        folds=tuple(folds),
        aggregates=tuple(aggregates),
        primary_aggregate=primary.to_dict() if primary else None,
        decision=_decision(config, primary),
    )


def write_high_conviction_walk_forward_report(
    report: HighConvictionWalkForwardReport,
    output_dir: str | Path,
) -> HighConvictionWalkForwardReport:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / f"{report.run_id}.json"
    markdown_path = output / f"{report.run_id}.md"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(render_high_conviction_walk_forward_report(report), encoding="utf-8")
    return replace(report, json_report_path=str(json_path), markdown_report_path=str(markdown_path))


def render_high_conviction_walk_forward_report(report: HighConvictionWalkForwardReport) -> str:
    lines = [
        f"# High Conviction Portfolio Walk-Forward - {report.run_id}",
        "",
        "## Scope",
        "",
        "- Mode: `research_only`; no runtime, paper or live order path is called.",
        "- Capital resets to `500 EUR` per out-of-sample fold.",
        f"- Input bars: `{report.input_bar_count}`; deduplicated: `{report.deduplicated_bar_count}`; duplicates removed: `{report.duplicate_bar_count}`.",
        f"- Folds: `{report.fold_count}`.",
        "",
        "## Aggregate Results",
        "",
        "| Scenario | Cost Profile | Policy | Folds + | Trades | Net PnL EUR | PF | Winrate | Worst DD % | Single Pair |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in sorted(report.aggregates, key=lambda item: item.total_net_pnl_eur, reverse=True):
        lines.append(
            f"| {row.scenario.get('label')} | {row.cost_profile} | {row.policy} | "
            f"{row.positive_fold_count}/{row.fold_count} | {row.total_trade_count} | {_fmt(row.total_net_pnl_eur)} | "
            f"{_fmt(row.profit_factor)} | {_fmt(row.winrate_pct)} | {_fmt(row.worst_fold_drawdown_pct)} | "
            f"{'yes' if row.is_single_symbol_dominated else 'no'} |"
        )
    lines.extend(["", "## Primary Conservative Stress Result", ""])
    primary = report.primary_aggregate or {}
    if primary:
        for key in (
            "scenario", "cost_profile", "policy", "fold_count", "positive_fold_count", "total_trade_count",
            "total_net_pnl_eur", "profit_factor", "winrate_pct", "expectancy_eur", "worst_fold_drawdown_pct",
            "largest_positive_symbol_share", "is_single_symbol_dominated",
        ):
            lines.append(f"- {key}: `{primary.get(key)}`")
        lines.extend(["", "### Pair Contributors", "", "| Symbol | Trades | Net PnL EUR |", "| --- | ---: | ---: |"])
        for row in primary.get("contributors", []):
            lines.append(f"| {row.get('symbol')} | {row.get('trade_count')} | {_fmt(row.get('net_pnl_eur'))} |")
        lines.extend(["", "### Losing Periods", ""])
        for row in primary.get("losing_periods", []):
            lines.append(f"- `{row.get('date')}`: `{_fmt(row.get('net_pnl_eur'))} EUR`")
    lines.extend(["", "## Fold Results", "", "| Fold | Test Window | Scenario | Costs | Policy | Trades | Net PnL EUR | PF | DD % |", "| ---: | --- | --- | --- | --- | ---: | ---: | ---: | ---: |"])
    for fold in report.folds:
        portfolio = fold.portfolio
        lines.append(
            f"| {fold.fold_index} | {fold.test_start_at} to {fold.test_end_at} | {fold.scenario.get('label')} | "
            f"{fold.cost_profile} | {fold.policy} | {portfolio.trade_count} | {_fmt(portfolio.net_pnl_eur)} | "
            f"{_fmt(portfolio.profit_factor)} | {_fmt(portfolio.max_drawdown_pct)} |"
        )
    lines.extend(["", "## Decision", "", f"Status: `{report.decision.status}`", ""])
    lines.extend(f"- {reason}" for reason in report.decision.reasons)
    lines.extend(["", "## Safety", ""])
    lines.extend(f"- {note}" for note in report.safety_notes)
    lines.append(f"- paper_candidate_allowed: `{report.decision.paper_candidate_allowed}`")
    lines.append(f"- live_promotion_allowed: `{report.decision.live_promotion_allowed}`")
    return "\n".join(lines) + "\n"


def _deduplicate_bars(bars: Sequence[MarketBar]) -> tuple[list[MarketBar], int]:
    latest: dict[tuple[str, str, datetime], MarketBar] = {}
    for bar in bars:
        latest[bar.key()] = bar
    rows = sorted(latest.values(), key=lambda bar: (bar.symbol, bar.timeframe, bar.timestamp))
    return rows, len(bars) - len(rows)


def _fold_windows(config: HighConvictionWalkForwardConfig, timeline: Sequence[datetime]) -> list[tuple[datetime, datetime, datetime, datetime]]:
    if len(timeline) < config.train_window_bars + config.test_window_bars:
        return []
    step = config.step_window_bars or config.test_window_bars
    result: list[tuple[datetime, datetime, datetime, datetime]] = []
    start = 0
    while start + config.train_window_bars + config.test_window_bars <= len(timeline):
        train_end_index = start + config.train_window_bars
        test_end_index = train_end_index + config.test_window_bars - 1
        result.append((timeline[start], timeline[train_end_index - 1], timeline[train_end_index], timeline[test_end_index]))
        start += step
    return result


def _groups_until(groups: dict[tuple[str, str], list[MarketBar]], end_at: datetime) -> dict[tuple[str, str], list[MarketBar]]:
    return {key: [bar for bar in rows if bar.timestamp <= end_at] for key, rows in groups.items()}


def _scenarios(config: HighConvictionWalkForwardConfig) -> tuple[DiscoveryScenario, ...]:
    return tuple(
        DiscoveryScenario(config.min_expected_move_bps, config.risk_reward_ratio, config.max_hold_hours, exit_mode)  # type: ignore[arg-type]
        for exit_mode in config.exit_modes
    )


def _portfolio_config(config: HighConvictionWalkForwardConfig, *, run_id: str) -> HighConvictionPortfolioConfig:
    return HighConvictionPortfolioConfig(
        run_id=run_id,
        data_paths=config.data_paths,
        symbols=config.symbols,
        setup_families=config.setup_families,
        min_expected_move_bps=(config.min_expected_move_bps,),
        risk_reward_ratios=(config.risk_reward_ratio,),
        max_hold_hours=(config.max_hold_hours,),
        exit_modes=config.exit_modes,
        cost_profiles=config.cost_profiles,
        initial_capital_eur=config.initial_capital_eur,
        legacy_notional_eur=config.initial_capital_eur * config.max_position_fraction,
        max_position_fraction=config.max_position_fraction,
        risk_per_trade_pct=config.risk_per_trade_pct,
        max_global_exposure_pct=config.max_global_exposure_pct,
        max_open_positions=config.max_open_positions,
        cooldown_hours=config.cooldown_hours,
        max_daily_loss_pct=config.max_daily_loss_pct,
        critical_drawdown_pct=config.critical_drawdown_pct,
        drawdown_reduce_start_pct=config.drawdown_reduce_start_pct,
        min_drawdown_exposure_multiplier=config.min_drawdown_exposure_multiplier,
        min_sample_trades_for_candidate=config.min_closed_trades_for_review,
        candidate_min_profit_factor=config.min_profit_factor,
        candidate_max_drawdown_pct=config.max_drawdown_pct,
    )


def _aggregates(config: HighConvictionWalkForwardConfig, folds: Sequence[HighConvictionWalkForwardFoldResult]) -> list[HighConvictionWalkForwardAggregate]:
    grouped: dict[tuple[str, str, str], list[HighConvictionWalkForwardFoldResult]] = defaultdict(list)
    for fold in folds:
        grouped[(str(fold.scenario.get("label")), fold.cost_profile, fold.policy)].append(fold)
    result: list[HighConvictionWalkForwardAggregate] = []
    for rows in grouped.values():
        records = tuple(record for row in rows for record in row.portfolio.trade_records)
        metrics = MetricsEngine().calculate(records, initial_capital_eur=config.initial_capital_eur)
        contributors = _contributors(records)
        positive_pnl = sum(max(0.0, float(row["net_pnl_eur"])) for row in contributors)
        largest_share = max((float(row["net_pnl_eur"]) for row in contributors), default=0.0) / positive_pnl if positive_pnl > 0.0 else None
        result.append(
            HighConvictionWalkForwardAggregate(
                scenario=dict(rows[0].scenario),
                cost_profile=rows[0].cost_profile,
                policy=rows[0].policy,
                fold_count=len(rows),
                positive_fold_count=sum(1 for row in rows if row.portfolio.net_pnl_eur > 0.0),
                total_trade_count=metrics.trade_count,
                total_net_pnl_eur=round(metrics.total_net_pnl_eur, 6),
                profit_factor=metrics.profit_factor,
                winrate_pct=metrics.winrate_pct,
                expectancy_eur=metrics.expectancy_eur,
                worst_fold_drawdown_pct=round(max((row.portfolio.max_drawdown_pct for row in rows), default=0.0), 6),
                average_fold_drawdown_pct=round(sum(row.portfolio.max_drawdown_pct for row in rows) / max(len(rows), 1), 6),
                contributors=tuple(contributors),
                losing_periods=tuple(_losing_periods(records)),
                largest_positive_symbol_share=round(largest_share, 6) if largest_share is not None else None,
                is_single_symbol_dominated=largest_share is not None and largest_share > config.max_single_symbol_positive_pnl_share,
            )
        )
    return sorted(result, key=lambda row: (row.total_net_pnl_eur, row.total_trade_count), reverse=True)


def _decision(config: HighConvictionWalkForwardConfig, primary: HighConvictionWalkForwardAggregate | None) -> HighConvictionWalkForwardDecision:
    if primary is None:
        return HighConvictionWalkForwardDecision("keep_collecting_ohlcv", ("no_primary_walk_forward_result", "paper_promotion_remains_disabled"))
    required_positive = max(config.min_folds, math.ceil(primary.fold_count * config.min_positive_fold_ratio))
    reasons: list[str] = []
    if primary.fold_count < config.min_folds:
        reasons.append("insufficient_walk_forward_folds")
    if primary.total_trade_count < config.min_closed_trades_for_review:
        reasons.append("insufficient_closed_trades_for_paper_review")
    if primary.positive_fold_count < required_positive:
        reasons.append("insufficient_positive_out_of_sample_folds")
    if primary.total_net_pnl_eur <= 0.0:
        reasons.append("non_positive_net_pnl_after_costs")
    if primary.profit_factor is None or primary.profit_factor < config.min_profit_factor:
        reasons.append("profit_factor_below_threshold")
    if primary.worst_fold_drawdown_pct > config.max_drawdown_pct * 100.0:
        reasons.append("walk_forward_drawdown_above_threshold")
    if primary.is_single_symbol_dominated:
        reasons.append("single_symbol_concentration")
    if reasons:
        return HighConvictionWalkForwardDecision("research_only_keep_testing", tuple(reasons + ["no_automatic_paper_or_live_promotion"]))
    return HighConvictionWalkForwardDecision(
        "research_only_human_review_required",
        ("all configured research thresholds passed under conservative stress costs", "manual review required", "no_automatic_paper_or_live_promotion"),
    )


def _contributors(records: Iterable[TradeRecord]) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for record in records:
        row = rows.setdefault(record.symbol, {"symbol": record.symbol, "trade_count": 0, "net_pnl_eur": 0.0})
        row["trade_count"] += 1
        row["net_pnl_eur"] += record.net_pnl_eur
    return [{"symbol": row["symbol"], "trade_count": row["trade_count"], "net_pnl_eur": round(row["net_pnl_eur"], 6)} for row in sorted(rows.values(), key=lambda item: item["net_pnl_eur"], reverse=True)]


def _losing_periods(records: Iterable[TradeRecord]) -> list[dict[str, Any]]:
    daily: dict[str, float] = defaultdict(float)
    for record in records:
        daily[record.closed_at.date().isoformat()] += record.net_pnl_eur
    return [{"date": day, "net_pnl_eur": round(pnl, 6)} for day, pnl in sorted(daily.items()) if pnl < 0.0]


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    return f"{float(value):.4f}" if isinstance(value, (int, float)) else str(value)
