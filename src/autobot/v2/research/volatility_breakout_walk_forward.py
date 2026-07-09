"""Strict research-only walk-forward for the P18B volatility breakout signal."""

from __future__ import annotations

import json
import os
import subprocess
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .alpha_hypothesis_lab import RESEARCH_ONLY_CAPITAL_FLAGS
from .execution_cost_model import ExecutionCostConfig, execution_cost_config_for_profile
from .high_conviction_discovery import (
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
from .high_conviction_walk_forward import _deduplicate_bars
from .market_data_repository import MarketBar


DEFAULT_SYMBOLS: tuple[str, ...] = ("BTCZEUR", "ETHZEUR", "BCHEUR", "ADAEUR", "XRPZEUR", "SOLEUR")
PRIMARY_SCENARIO = DiscoveryScenario(500.0, 2.0, 72.0, "fixed_tp_sl")
DEFAULT_SCENARIOS: tuple[DiscoveryScenario, ...] = (
    DiscoveryScenario(450.0, 2.0, 72.0, "fixed_tp_sl"),
    PRIMARY_SCENARIO,
    DiscoveryScenario(600.0, 2.0, 72.0, "fixed_tp_sl"),
    DiscoveryScenario(500.0, 2.5, 72.0, "fixed_tp_sl"),
    DiscoveryScenario(500.0, 2.0, 72.0, "trailing"),
)


@dataclass(frozen=True)
class VolatilityBreakoutWalkForwardConfig:
    run_id: str
    data_paths: tuple[Path, ...]
    output_dir: Path = Path("reports/research")
    symbols: tuple[str, ...] = DEFAULT_SYMBOLS
    cost_profile: str = "research_stress"
    max_variants: int = 5
    folds: int = 5
    train_fraction: float = 0.45
    order_notional_eur: float = 100.0
    max_cpu_seconds: float = 120.0

    def __post_init__(self) -> None:
        if not self.run_id.strip() or not self.data_paths:
            raise ValueError("run_id and data_paths are required")
        if self.max_variants <= 0 or self.max_variants > 5:
            raise ValueError("max_variants must be between 1 and 5")
        if self.folds < 3 or self.folds > 8:
            raise ValueError("folds must be between 3 and 8")
        if not 0.2 <= self.train_fraction <= 0.7:
            raise ValueError("train_fraction must stay bounded between 0.2 and 0.7")
        if self.order_notional_eur <= 0.0:
            raise ValueError("order_notional_eur must be positive")
        if self.max_cpu_seconds <= 0.0:
            raise ValueError("max_cpu_seconds must be positive")
        execution_cost_config_for_profile(self.cost_profile).validate()


@dataclass(frozen=True)
class BreakoutMetrics:
    trade_count: int
    net_pnl_eur: float
    profit_factor_net: float | None
    expectancy_net: float | None
    winrate_pct: float | None
    max_drawdown_eur: float
    max_drawdown_pct: float
    fees_slippage_spread_bps: float
    no_trade_baseline_eur: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FoldResult:
    fold_id: str
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    train_metrics: BreakoutMetrics
    test_metrics: BreakoutMetrics
    test_by_symbol: dict[str, dict[str, Any]]
    test_by_period: dict[str, dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "fold_id": self.fold_id,
            "train_start": self.train_start,
            "train_end": self.train_end,
            "test_start": self.test_start,
            "test_end": self.test_end,
            "train_metrics": self.train_metrics.to_dict(),
            "test_metrics": self.test_metrics.to_dict(),
            "test_by_symbol": self.test_by_symbol,
            "test_by_period": self.test_by_period,
        }


@dataclass(frozen=True)
class VolatilityBreakoutWalkForwardReport:
    run_id: str
    generated_at: str
    commit: str | None
    data_paths: tuple[str, ...]
    period: dict[str, Any]
    scenarios: tuple[dict[str, Any], ...]
    primary_scenario: dict[str, Any]
    data_quality: dict[str, Any]
    overall: BreakoutMetrics
    by_symbol: dict[str, dict[str, Any]]
    by_period: dict[str, dict[str, Any]]
    folds: tuple[FoldResult, ...]
    scenario_summary: dict[str, dict[str, Any]]
    concentration: dict[str, Any]
    diagnostics: dict[str, Any]
    verdict: str
    verdict_reasons: tuple[str, ...]
    recommendation_p18d: str
    safety: dict[str, bool] = field(default_factory=lambda: dict(RESEARCH_ONLY_CAPITAL_FLAGS))
    json_report_path: str | None = None
    markdown_report_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "commit": self.commit,
            "data_paths": list(self.data_paths),
            "period": dict(self.period),
            "scenarios": [dict(row) for row in self.scenarios],
            "primary_scenario": dict(self.primary_scenario),
            "data_quality": dict(self.data_quality),
            "overall": self.overall.to_dict(),
            "by_symbol": self.by_symbol,
            "by_period": self.by_period,
            "folds": [fold.to_dict() for fold in self.folds],
            "scenario_summary": self.scenario_summary,
            "concentration": self.concentration,
            "diagnostics": self.diagnostics,
            "verdict": self.verdict,
            "verdict_reasons": list(self.verdict_reasons),
            "recommendation_p18d": self.recommendation_p18d,
            "safety": dict(self.safety),
            "paper_capital_allowed": False,
            "live_allowed": False,
            "promotable": False,
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
        }


def build_volatility_breakout_walk_forward_report(
    config: VolatilityBreakoutWalkForwardConfig,
    *,
    commit: str | None = None,
) -> VolatilityBreakoutWalkForwardReport:
    started = time.perf_counter()
    report_commit = commit or _current_git_commit()
    cost_config = execution_cost_config_for_profile(config.cost_profile)
    discovery_config = _discovery_config(config, cost_config)
    raw_bars = _load_ohlcv_bars(discovery_config)
    bars, duplicate_count = _deduplicate_bars(raw_bars)
    groups = _with_resampled_4h(_group_by_symbol_timeframe(bars))
    setups = _discover_setups(discovery_config, dict(groups))
    scenarios = DEFAULT_SCENARIOS[: config.max_variants]
    primary = PRIMARY_SCENARIO if PRIMARY_SCENARIO in scenarios else scenarios[0]

    scenario_trades = {scenario.label(): _run_scenario_trades(discovery_config, scenario, setups, groups) for scenario in scenarios}
    if time.perf_counter() - started > config.max_cpu_seconds:
        diagnostics = {"warning": "max_cpu_seconds_exceeded_after_scenario_replay"}
    else:
        diagnostics = {}

    primary_trades = scenario_trades[primary.label()]
    folds = tuple(_build_folds(config, primary_trades))
    overall = _metrics(primary_trades)
    by_symbol = _by_symbol(primary_trades)
    by_period = _by_period(primary_trades)
    scenario_summary = {label: _scenario_summary(trades) for label, trades in scenario_trades.items()}
    concentration = _concentration(primary_trades)
    verdict, reasons = _verdict(overall, folds, concentration)
    diagnostics.update(
        {
            "setup_count": len(setups),
            "setup_count_by_symbol": dict(Counter(setup.symbol for setup in setups)),
            "scenario_count": len(scenarios),
            "anti_lookahead": (
                "Features are generated from OHLCV history ending at detection time; "
                "exits/PnL are used only after entry for evaluation."
            ),
            "p18b_period_gap_fix": (
                "P18B volatility period table was empty because the smoke summary stored "
                "scenario samples, not the full trade list. P18C reconstructs all trades "
                "from setups and reports period/fold attribution."
            ),
        }
    )
    return VolatilityBreakoutWalkForwardReport(
        run_id=config.run_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        commit=report_commit,
        data_paths=tuple(str(path) for path in config.data_paths),
        period=_period_payload(bars),
        scenarios=tuple(scenario.to_dict() for scenario in scenarios),
        primary_scenario=primary.to_dict(),
        data_quality={
            "raw_rows": len(raw_bars),
            "deduped_rows": len(bars),
            "duplicate_count": duplicate_count,
            "gap_count": _gap_count(groups),
            "symbols": sorted({bar.symbol for bar in bars}),
            "timeframes": sorted({bar.timeframe for bar in bars}),
        },
        overall=overall,
        by_symbol=by_symbol,
        by_period=by_period,
        folds=folds,
        scenario_summary=scenario_summary,
        concentration=concentration,
        diagnostics=diagnostics,
        verdict=verdict,
        verdict_reasons=tuple(reasons),
        recommendation_p18d=_recommendation(verdict, reasons),
    )


def write_volatility_breakout_walk_forward_report(
    report: VolatilityBreakoutWalkForwardReport,
    output_dir: str | Path,
) -> VolatilityBreakoutWalkForwardReport:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / f"{report.run_id}.json"
    markdown_path = output / f"{report.run_id}.md"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(render_volatility_breakout_walk_forward_report(report), encoding="utf-8")
    return replace(report, json_report_path=str(json_path), markdown_report_path=str(markdown_path))


def render_volatility_breakout_walk_forward_report(report: VolatilityBreakoutWalkForwardReport) -> str:
    lines = [
        f"# P18C Volatility Breakout Walk-Forward - {report.run_id}",
        "",
        "## Scope",
        "",
        "- Mode: `research_only`.",
        "- No live, no paper capital, no promotion, no shadow activation, no UI change, no sizing/leverage change.",
        f"- Commit: `{report.commit}`.",
        f"- Verdict: `{report.verdict}`.",
        "",
        "## Data",
        "",
        f"- Paths: `{', '.join(report.data_paths)}`",
        f"- Period: `{report.period.get('start_at')}` -> `{report.period.get('end_at')}`",
        f"- Deduped rows: `{report.data_quality['deduped_rows']}`",
        f"- Duplicates removed: `{report.data_quality['duplicate_count']}`",
        f"- Gaps: `{report.data_quality['gap_count']}`",
        f"- Symbols: `{', '.join(report.data_quality['symbols'])}`",
        f"- Timeframes: `{', '.join(report.data_quality['timeframes'])}`",
        "",
        "## Primary Scenario",
        "",
        f"- `{report.primary_scenario['label']}`",
        "",
        "## Overall Primary Result",
        "",
        _metrics_lines(report.overall),
        "",
        "## Walk-Forward Folds",
        "",
        "| Fold | Train Period | Test Period | Test Trades | Test PF | Test Expectancy | Test Net PnL | Test DD EUR |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for fold in report.folds:
        test = fold.test_metrics
        lines.append(
            f"| `{fold.fold_id}` | {fold.train_start} -> {fold.train_end} | "
            f"{fold.test_start} -> {fold.test_end} | {test.trade_count} | {_fmt(test.profit_factor_net)} | "
            f"{_fmt(test.expectancy_net)} | {_fmt(test.net_pnl_eur)} | {_fmt(test.max_drawdown_eur)} |"
        )
    lines.extend(["", "## By Symbol", "", "| Symbol | Trades | Net PnL | PF Net | Expectancy | Contribution Positive PnL % |", "|---|---:|---:|---:|---:|---:|"])
    for symbol, row in sorted(report.by_symbol.items(), key=lambda item: item[1]["net_pnl_eur"], reverse=True):
        lines.append(
            f"| `{symbol}` | {row['trade_count']} | {_fmt(row['net_pnl_eur'])} | "
            f"{_fmt(row['profit_factor_net'])} | {_fmt(row['expectancy_net'])} | {_fmt(row.get('positive_pnl_share_pct'))} |"
        )
    lines.extend(["", "## By Period", "", "| Period | Trades | Net PnL |", "|---|---:|---:|"])
    for period, row in sorted(report.by_period.items()):
        lines.append(f"| `{period}` | {row['trade_count']} | {_fmt(row['net_pnl_eur'])} |")
    lines.extend(["", "## Scenario Summary", "", "| Scenario | Trades | PF Net | Expectancy | Net PnL |", "|---|---:|---:|---:|---:|"])
    for label, row in report.scenario_summary.items():
        lines.append(
            f"| `{label}` | {row['trade_count']} | {_fmt(row['profit_factor_net'])} | "
            f"{_fmt(row['expectancy_net'])} | {_fmt(row['net_pnl_eur'])} |"
        )
    lines.extend(["", "## Concentration Diagnostics", ""])
    for key, value in report.concentration.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Verdict Reasons", ""])
    lines.extend(f"- {reason}" for reason in report.verdict_reasons)
    lines.extend(["", "## Diagnostics", ""])
    for key, value in report.diagnostics.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Safety", ""])
    lines.append(f"- paper_capital_allowed: `{report.safety['paper_capital_allowed']}`")
    lines.append(f"- live_allowed: `{report.safety['live_allowed']}`")
    lines.append(f"- promotable: `{report.safety['promotable']}`")
    lines.append("- No order path called; runtime trading untouched; grid remains blocked/no-go.")
    lines.extend(["", "## Recommendation P18D", "", report.recommendation_p18d])
    return "\n".join(lines) + "\n"


def _discovery_config(
    config: VolatilityBreakoutWalkForwardConfig,
    cost_config: ExecutionCostConfig,
) -> HighConvictionDiscoveryConfig:
    return HighConvictionDiscoveryConfig(
        run_id=config.run_id,
        data_paths=config.data_paths,
        symbols=config.symbols,
        setup_families=("volatility_expansion", "breakout_1h_4h"),
        min_expected_move_bps=(500.0,),
        risk_reward_ratios=(2.0,),
        max_hold_hours=(72.0,),
        exit_modes=("fixed_tp_sl",),
        order_notional_eur=config.order_notional_eur,
        cost_config=cost_config,
        min_sample_trades_for_candidate=50,
    )


def _run_scenario_trades(
    config: HighConvictionDiscoveryConfig,
    scenario: DiscoveryScenario,
    setups: Sequence[DiscoverySetup],
    groups: Mapping[tuple[str, str], Sequence[MarketBar]],
) -> list[DiscoveryTrade]:
    trades: list[DiscoveryTrade] = []
    for setup in setups:
        if setup.expected_move_bps < scenario.min_expected_move_bps:
            continue
        if setup.risk_reward_estimate < scenario.risk_reward_ratio:
            continue
        path = _future_5m_path(list(groups.get((setup.symbol, "5m"), ())), setup.entry_at, scenario.max_hold_hours)
        if not path:
            continue
        trade = _simulate_trade(config, scenario, setup, path)
        if trade is not None:
            trades.append(trade)
    return sorted(trades, key=lambda trade: (trade.entry_at, trade.symbol, trade.setup_id))


def _build_folds(config: VolatilityBreakoutWalkForwardConfig, trades: Sequence[DiscoveryTrade]) -> list[FoldResult]:
    if not trades:
        return []
    times = sorted(_parse_dt(trade.entry_at) for trade in trades)
    start = times[0]
    end = times[-1]
    total_seconds = max(1.0, (end - start).total_seconds())
    fold_span = total_seconds / config.folds
    train_span = fold_span * config.train_fraction
    results: list[FoldResult] = []
    for index in range(config.folds):
        train_start = start + _seconds(fold_span * index)
        train_end = train_start + _seconds(train_span)
        test_start = train_end
        test_end = start + _seconds(fold_span * (index + 1))
        if index == config.folds - 1:
            test_end = end
        train_trades = [trade for trade in trades if train_start <= _parse_dt(trade.entry_at) < train_end]
        test_trades = [trade for trade in trades if test_start <= _parse_dt(trade.entry_at) <= test_end]
        results.append(
            FoldResult(
                fold_id=f"fold_{index + 1}",
                train_start=train_start.isoformat(),
                train_end=train_end.isoformat(),
                test_start=test_start.isoformat(),
                test_end=test_end.isoformat(),
                train_metrics=_metrics(train_trades),
                test_metrics=_metrics(test_trades),
                test_by_symbol=_by_symbol(test_trades),
                test_by_period=_by_period(test_trades),
            )
        )
    return results


def _metrics(trades: Sequence[DiscoveryTrade]) -> BreakoutMetrics:
    pnl = [float(trade.pnl_eur) for trade in trades]
    wins = [value for value in pnl if value > 0]
    losses = [value for value in pnl if value < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    notional = 100.0
    return BreakoutMetrics(
        trade_count=len(trades),
        net_pnl_eur=round(sum(pnl), 6),
        profit_factor_net=(gross_profit / gross_loss if gross_loss else (None if gross_profit else 0.0)),
        expectancy_net=(sum(pnl) / len(pnl) if pnl else None),
        winrate_pct=(len(wins) / len(pnl) * 100.0 if pnl else None),
        max_drawdown_eur=round(_max_drawdown(pnl), 6),
        max_drawdown_pct=round((_max_drawdown(pnl) / notional) * 100.0, 6),
        fees_slippage_spread_bps=round(sum(float(trade.cost_bps) for trade in trades), 6),
    )


def _by_symbol(trades: Sequence[DiscoveryTrade]) -> dict[str, dict[str, Any]]:
    positive_total = sum(float(trade.pnl_eur) for trade in trades if float(trade.pnl_eur) > 0)
    grouped: dict[str, list[DiscoveryTrade]] = defaultdict(list)
    for trade in trades:
        grouped[trade.symbol].append(trade)
    rows: dict[str, dict[str, Any]] = {}
    for symbol, symbol_trades in sorted(grouped.items()):
        metrics = _metrics(symbol_trades)
        positive = sum(float(trade.pnl_eur) for trade in symbol_trades if float(trade.pnl_eur) > 0)
        rows[symbol] = {
            "trade_count": metrics.trade_count,
            "net_pnl_eur": metrics.net_pnl_eur,
            "profit_factor_net": metrics.profit_factor_net,
            "expectancy_net": metrics.expectancy_net,
            "winrate_pct": metrics.winrate_pct,
            "max_drawdown_eur": metrics.max_drawdown_eur,
            "positive_pnl_share_pct": (positive / positive_total * 100.0 if positive_total > 0 else 0.0),
        }
    return rows


def _by_period(trades: Sequence[DiscoveryTrade]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[DiscoveryTrade]] = defaultdict(list)
    for trade in trades:
        grouped[_parse_dt(trade.exit_at).date().isoformat()].append(trade)
    return {
        period: {"trade_count": len(rows), "net_pnl_eur": round(sum(float(trade.pnl_eur) for trade in rows), 6)}
        for period, rows in sorted(grouped.items())
    }


def _scenario_summary(trades: Sequence[DiscoveryTrade]) -> dict[str, Any]:
    metrics = _metrics(trades)
    return metrics.to_dict()


def _concentration(trades: Sequence[DiscoveryTrade]) -> dict[str, Any]:
    overall = _metrics(trades)
    without_bch = [trade for trade in trades if trade.symbol != "BCHEUR"]
    without_bch_ada = [trade for trade in trades if trade.symbol not in {"BCHEUR", "ADAEUR"}]
    only_bch_ada = [trade for trade in trades if trade.symbol in {"BCHEUR", "ADAEUR"}]
    by_symbol = _by_symbol(trades)
    positive_symbol_pnl = {symbol: max(0.0, float(row["net_pnl_eur"])) for symbol, row in by_symbol.items()}
    positive_total = sum(positive_symbol_pnl.values())
    top_symbol = max(positive_symbol_pnl, key=positive_symbol_pnl.get) if positive_symbol_pnl else None
    return {
        "top_positive_symbol": top_symbol,
        "top_positive_symbol_share_pct": (
            positive_symbol_pnl[top_symbol] / positive_total * 100.0 if top_symbol and positive_total > 0 else 0.0
        ),
        "bcheur_positive_share_pct": by_symbol.get("BCHEUR", {}).get("positive_pnl_share_pct", 0.0),
        "adaeur_positive_share_pct": by_symbol.get("ADAEUR", {}).get("positive_pnl_share_pct", 0.0),
        "overall_net_pnl_eur": overall.net_pnl_eur,
        "without_bcheur": _metrics(without_bch).to_dict(),
        "without_bcheur_adaeur": _metrics(without_bch_ada).to_dict(),
        "only_bcheur_adaeur": _metrics(only_bch_ada).to_dict(),
        "diagnostic_only": True,
    }


def _verdict(
    overall: BreakoutMetrics,
    folds: Sequence[FoldResult],
    concentration: Mapping[str, Any],
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    positive_folds = sum(1 for fold in folds if fold.test_metrics.net_pnl_eur > 0 and (fold.test_metrics.profit_factor_net or 0.0) > 1.0)
    fold_count = len(folds)
    positive_fold_ratio = positive_folds / fold_count if fold_count else 0.0
    top_share = float(concentration.get("top_positive_symbol_share_pct") or 0.0)
    without_bch = concentration.get("without_bcheur", {})
    without_bch_ada = concentration.get("without_bcheur_adaeur", {})

    if overall.trade_count < 50:
        reasons.append("less_than_50_usable_trades")
    if overall.profit_factor_net is None or overall.profit_factor_net < 1.0:
        reasons.append("pf_net_walk_forward_below_1")
    if overall.expectancy_net is None or overall.expectancy_net <= 0.0:
        reasons.append("expectancy_net_not_positive")
    if overall.max_drawdown_pct > 12.0:
        reasons.append("drawdown_above_12_pct_proxy")
    if positive_fold_ratio <= 0.5:
        reasons.append("majority_folds_not_positive")
    if top_share > 60.0:
        reasons.append("positive_pnl_concentrated_in_one_symbol")
    if float(without_bch.get("net_pnl_eur") or 0.0) <= 0.0:
        reasons.append("fails_without_bcheur")
    if float(without_bch_ada.get("net_pnl_eur") or 0.0) <= 0.0:
        reasons.append("fails_without_bcheur_adaeur")
    if reasons and (
        (overall.profit_factor_net is None or overall.profit_factor_net < 1.0)
        or overall.expectancy_net is None
        or overall.expectancy_net <= 0.0
        or positive_fold_ratio <= 0.5
    ):
        return "REJECT", reasons
    if reasons:
        return "WEAK_SIGNAL", reasons
    if (
        overall.profit_factor_net is not None
        and overall.profit_factor_net >= 1.25
        and positive_fold_ratio >= 0.60
        and overall.max_drawdown_pct <= 12.0
        and top_share <= 55.0
    ):
        return "SHADOW_CANDIDATE_LATER", ["strict_criteria_passed_but_human_approval_required"]
    if overall.profit_factor_net is not None and overall.profit_factor_net > 1.2:
        return "KEEP_RESEARCH", ["positive_pf_above_1_2_but_not_shadow_candidate"]
    return "WEAK_SIGNAL", ["pf_between_1_and_1_2_or_fragile_walk_forward"]


def _recommendation(verdict: str, reasons: Sequence[str]) -> str:
    if verdict == "REJECT":
        return "Do not advance this hypothesis. Keep it as research evidence only or redesign the signal before another smoke."
    if verdict == "WEAK_SIGNAL":
        return "Keep research-only, focus on fold stability and concentration diagnostics before any shadow discussion."
    if verdict == "KEEP_RESEARCH":
        return "Run a second strict walk-forward with fresh data and stress tests; no shadow activation yet."
    return "Prepare a human review package only; do not activate shadow automatically."


def _period_payload(bars: Sequence[MarketBar]) -> dict[str, Any]:
    start = min((bar.timestamp for bar in bars), default=None)
    end = max((bar.timestamp for bar in bars), default=None)
    return {
        "start_at": start.isoformat() if start else None,
        "end_at": end.isoformat() if end else None,
        "row_count": len(bars),
    }


def _gap_count(groups: Mapping[tuple[str, str], Sequence[MarketBar]]) -> int:
    expected = {"5m": 5 * 60, "15m": 15 * 60, "1h": 60 * 60, "4h": 4 * 60 * 60}
    gaps = 0
    for (_symbol, timeframe), rows in groups.items():
        seconds = expected.get(timeframe)
        if not seconds:
            continue
        ordered = sorted(rows, key=lambda row: row.timestamp)
        for prev, cur in zip(ordered, ordered[1:]):
            if (cur.timestamp - prev.timestamp).total_seconds() > seconds * 1.5:
                gaps += 1
    return gaps


def _max_drawdown(values: Sequence[float]) -> float:
    cumulative = 0.0
    peak = 0.0
    worst = 0.0
    for value in values:
        cumulative += value
        peak = max(peak, cumulative)
        worst = max(worst, peak - cumulative)
    return worst


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _seconds(value: float):
    from datetime import timedelta

    return timedelta(seconds=value)


def _current_git_commit() -> str | None:
    env_commit = os.environ.get("AUTOBOT_COMMIT") or os.environ.get("GIT_COMMIT")
    if env_commit:
        return env_commit.strip() or None
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def _metrics_lines(metrics: BreakoutMetrics) -> str:
    return "\n".join(
        [
            f"- trade_count: `{metrics.trade_count}`",
            f"- PF net: `{_fmt(metrics.profit_factor_net)}`",
            f"- expectancy net: `{_fmt(metrics.expectancy_net)}`",
            f"- net PnL EUR: `{_fmt(metrics.net_pnl_eur)}`",
            f"- max drawdown EUR: `{_fmt(metrics.max_drawdown_eur)}`",
            f"- max drawdown pct proxy: `{_fmt(metrics.max_drawdown_pct)}`",
            f"- win rate: `{_fmt(metrics.winrate_pct)}`",
            f"- no_trade_baseline_eur: `{metrics.no_trade_baseline_eur}`",
        ]
    )


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.6g}"
    except (TypeError, ValueError):
        return str(value)
