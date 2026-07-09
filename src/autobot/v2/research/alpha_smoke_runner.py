"""Read-only smoke runner for the Alpha Hypothesis Lab.

P18B deliberately runs tiny, bounded checks on accessible OHLCV hypotheses. It
does not submit orders, does not write paper trades, and never promotes an
alpha. Its only output is JSON/Markdown evidence.
"""

from __future__ import annotations

import json
import math
import subprocess
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .alpha_hypothesis_lab import RESEARCH_ONLY_CAPITAL_FLAGS, load_alpha_hypotheses
from .execution_cost_model import ExecutionCostConfig, execution_cost_config_for_profile
from .high_conviction_discovery import (
    DiscoveryScenario,
    HighConvictionDiscoveryConfig,
    _discover_setups,
    _group_by_symbol_timeframe,
    _load_ohlcv_bars,
    _run_discovery_scenario,
    _with_resampled_4h,
)
from .high_conviction_walk_forward import _deduplicate_bars
from .market_data_repository import MarketBar


LIQUID_SYMBOLS: tuple[str, ...] = ("BTCZEUR", "ETHZEUR", "BCHEUR", "ADAEUR", "XRPZEUR", "SOLEUR")
P18B_TESTED_HYPOTHESES: tuple[str, ...] = (
    "volatility_breakout_high_conviction",
    "long_timeframe_adaptive_trend",
)
P18B_SKIPPED_HYPOTHESES: tuple[str, ...] = ("funding_basis", "liquidation_cascade")


def _current_git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    commit = result.stdout.strip()
    return commit or None


@dataclass(frozen=True)
class AlphaSmokeConfig:
    run_id: str
    data_paths: tuple[Path, ...]
    output_dir: Path = Path("reports/research/alpha_smoke")
    hypotheses_path: Path = Path("docs/research/alpha_hypotheses.json")
    symbols: tuple[str, ...] = LIQUID_SYMBOLS
    cost_profile: str = "research_stress"
    max_variants: int = 5
    max_symbols: int = 6
    max_cpu_seconds: float = 60.0
    order_notional_eur: float = 100.0

    def __post_init__(self) -> None:
        if not self.run_id.strip() or not self.data_paths:
            raise ValueError("run_id and data_paths are required")
        if self.max_variants <= 0 or self.max_variants > 5:
            raise ValueError("max_variants must be between 1 and 5")
        if self.max_symbols <= 0:
            raise ValueError("max_symbols must be positive")
        if self.max_cpu_seconds <= 0.0:
            raise ValueError("max_cpu_seconds must be positive")
        if self.order_notional_eur <= 0.0:
            raise ValueError("order_notional_eur must be positive")
        execution_cost_config_for_profile(self.cost_profile).validate()


@dataclass(frozen=True)
class DataAvailability:
    hypothesis_id: str
    status: str
    available: bool
    symbols: tuple[str, ...]
    timeframes: tuple[str, ...]
    start_at: str | None
    end_at: str | None
    row_count: int
    duplicate_count: int
    gap_count: int
    cost_estimate: str
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SmokeMetrics:
    trade_count: int
    net_pnl_eur: float
    profit_factor_net: float | None
    expectancy_net: float | None
    winrate_pct: float | None
    max_drawdown_eur: float
    total_cost_bps: float
    no_trade_baseline_eur: float
    by_symbol: dict[str, dict[str, Any]]
    by_period: dict[str, dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SmokeResult:
    hypothesis_id: str
    variant_count: int
    best_variant: str | None
    decision: str
    reasons: tuple[str, ...]
    metrics: SmokeMetrics
    variants: tuple[dict[str, Any], ...]
    elapsed_seconds: float
    safety: dict[str, bool] = field(default_factory=lambda: dict(RESEARCH_ONLY_CAPITAL_FLAGS))

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "variant_count": self.variant_count,
            "best_variant": self.best_variant,
            "decision": self.decision,
            "reasons": list(self.reasons),
            "metrics": self.metrics.to_dict(),
            "variants": [dict(row) for row in self.variants],
            "elapsed_seconds": self.elapsed_seconds,
            "safety": dict(self.safety),
        }


@dataclass(frozen=True)
class AlphaSmokeReport:
    run_id: str
    generated_at: str
    commit: str | None
    data_paths: tuple[str, ...]
    availability: tuple[DataAvailability, ...]
    tested: tuple[SmokeResult, ...]
    skipped: tuple[dict[str, Any], ...]
    safety_notes: tuple[str, ...]
    json_report_path: str | None = None
    markdown_report_path: str | None = None
    live_promotion_allowed: bool = False
    paper_capital_allowed: bool = False
    promotable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "commit": self.commit,
            "data_paths": list(self.data_paths),
            "availability": [item.to_dict() for item in self.availability],
            "tested": [item.to_dict() for item in self.tested],
            "skipped": [dict(item) for item in self.skipped],
            "safety_notes": list(self.safety_notes),
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
            "live_promotion_allowed": self.live_promotion_allowed,
            "paper_capital_allowed": self.paper_capital_allowed,
            "promotable": self.promotable,
        }


@dataclass(frozen=True)
class _SmokeTrade:
    symbol: str
    opened_at: datetime
    closed_at: datetime
    gross_bps: float
    cost_bps: float
    net_bps: float
    pnl_eur: float
    variant: str


def build_alpha_smoke_report(config: AlphaSmokeConfig, *, commit: str | None = None) -> AlphaSmokeReport:
    started = time.perf_counter()
    report_commit = commit or _current_git_commit()
    load_alpha_hypotheses(config.hypotheses_path)
    raw_bars = _load_bars(config)
    bars, duplicate_count = _deduplicate_bars(raw_bars)
    groups = _with_resampled_4h(_group_by_symbol_timeframe(bars))
    availability = tuple(_availability_rows(config, bars, duplicate_count, groups))
    cost_config = execution_cost_config_for_profile(config.cost_profile)
    tested: list[SmokeResult] = []
    for hypothesis_id in P18B_TESTED_HYPOTHESES:
        if time.perf_counter() - started > config.max_cpu_seconds:
            tested.append(_timeout_result(hypothesis_id, started))
            break
        if hypothesis_id == "volatility_breakout_high_conviction":
            tested.append(_run_volatility_breakout(config, groups, cost_config))
        elif hypothesis_id == "long_timeframe_adaptive_trend":
            tested.append(_run_long_trend(config, groups, cost_config))
    skipped = tuple(
        {
            "hypothesis_id": item,
            "status": "MISSING_DATA",
            "reason": "requires derivatives funding/liquidation data not collected in the current Kraken Spot OHLCV research store",
            **RESEARCH_ONLY_CAPITAL_FLAGS,
        }
        for item in P18B_SKIPPED_HYPOTHESES
    )
    return AlphaSmokeReport(
        run_id=config.run_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        commit=report_commit,
        data_paths=tuple(str(path) for path in config.data_paths),
        availability=availability,
        tested=tuple(tested),
        skipped=skipped,
        safety_notes=(
            "Read-only Alpha Hypothesis Lab smoke runner.",
            "No runtime trading component is imported or called.",
            "No order, paper capital, live flag, sizing, leverage, dashboard, or promotion path is touched.",
            "Grid remains archived/no-go; trend and mean reversion remain benchmarks only.",
        ),
    )


def write_alpha_smoke_report(report: AlphaSmokeReport, output_dir: str | Path) -> AlphaSmokeReport:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / f"{report.run_id}.json"
    markdown_path = output / f"{report.run_id}.md"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(render_alpha_smoke_report(report), encoding="utf-8")
    return replace(report, json_report_path=str(json_path), markdown_report_path=str(markdown_path))


def render_alpha_smoke_report(report: AlphaSmokeReport) -> str:
    lines = [
        f"# P18B Alpha Smoke Runner - {report.run_id}",
        "",
        "## Scope",
        "",
        "- Mode: `research_only`.",
        "- No live, no paper capital, no promotion, no UI change, no sizing/leverage change.",
        f"- Commit: `{report.commit}`.",
        "",
        "## Data Availability",
        "",
        "| Hypothesis | Status | Rows | Symbols | Timeframes | Period | Duplicates | Gaps | Cost | Reason |",
        "|---|---|---:|---:|---|---|---:|---:|---|---|",
    ]
    for item in report.availability:
        period = f"{item.start_at} -> {item.end_at}" if item.start_at and item.end_at else "n/a"
        lines.append(
            f"| `{item.hypothesis_id}` | `{item.status}` | {item.row_count} | {len(item.symbols)} | "
            f"{', '.join(item.timeframes)} | {period} | {item.duplicate_count} | {item.gap_count} | "
            f"{item.cost_estimate} | {item.reason or ''} |"
        )
    lines.extend(["", "## Smoke Results", ""])
    for result in report.tested:
        m = result.metrics
        lines.extend(
            [
                f"### {result.hypothesis_id}",
                "",
                f"- decision: `{result.decision}`",
                f"- variants: `{result.variant_count}`",
                f"- best_variant: `{result.best_variant}`",
                f"- trade_count: `{m.trade_count}`",
                f"- PF net: `{_fmt(m.profit_factor_net)}`",
                f"- expectancy net: `{_fmt(m.expectancy_net)}`",
                f"- net PnL EUR: `{_fmt(m.net_pnl_eur)}`",
                f"- max drawdown EUR: `{_fmt(m.max_drawdown_eur)}`",
                f"- win rate: `{_fmt(m.winrate_pct)}`",
                f"- no_trade_baseline_eur: `{m.no_trade_baseline_eur}`",
                f"- elapsed_seconds: `{_fmt(result.elapsed_seconds)}`",
                "",
                "Reasons:",
            ]
        )
        lines.extend(f"- {reason}" for reason in result.reasons)
        lines.extend(["", "| Symbol | Trades | Net PnL EUR |", "|---|---:|---:|"])
        for symbol, row in sorted(m.by_symbol.items(), key=lambda item: item[1]["net_pnl_eur"], reverse=True):
            lines.append(f"| `{symbol}` | {row['trade_count']} | {_fmt(row['net_pnl_eur'])} |")
        lines.extend(["", "| Period | Trades | Net PnL EUR |", "|---|---:|---:|"])
        for period, row in sorted(m.by_period.items()):
            lines.append(f"| `{period}` | {row['trade_count']} | {_fmt(row['net_pnl_eur'])} |")
        lines.append("")
    lines.extend(["## Hypotheses Not Tested", "", "| Hypothesis | Status | Reason |", "|---|---|---|"])
    for item in report.skipped:
        lines.append(f"| `{item['hypothesis_id']}` | `{item['status']}` | {item['reason']} |")
    lines.extend(["", "## Safety", ""])
    lines.extend(f"- {note}" for note in report.safety_notes)
    lines.append(f"- paper_capital_allowed: `{report.paper_capital_allowed}`")
    lines.append(f"- live_promotion_allowed: `{report.live_promotion_allowed}`")
    lines.append(f"- promotable: `{report.promotable}`")
    lines.extend(["", "## Recommendation P18C", ""])
    lines.append(_recommendation(report))
    return "\n".join(lines) + "\n"


def _load_bars(config: AlphaSmokeConfig) -> list[MarketBar]:
    discovery_config = HighConvictionDiscoveryConfig(
        run_id=config.run_id,
        data_paths=config.data_paths,
        symbols=tuple(config.symbols[: config.max_symbols]),
        min_expected_move_bps=(200.0,),
        risk_reward_ratios=(2.0,),
        max_hold_hours=(72.0,),
        exit_modes=("fixed_tp_sl",),
        cost_config=execution_cost_config_for_profile(config.cost_profile),
    )
    return _load_ohlcv_bars(discovery_config)


def _availability_rows(
    config: AlphaSmokeConfig,
    bars: Sequence[MarketBar],
    duplicate_count: int,
    groups: Mapping[tuple[str, str], Sequence[MarketBar]],
) -> Iterable[DataAvailability]:
    symbols = tuple(sorted({bar.symbol for bar in bars}))
    timeframes = tuple(sorted({bar.timeframe.lower() for bar in bars}))
    start = min((bar.timestamp for bar in bars), default=None)
    end = max((bar.timestamp for bar in bars), default=None)
    gap_count = _gap_count(groups)
    common = {
        "symbols": symbols,
        "timeframes": timeframes,
        "start_at": start.isoformat() if start else None,
        "end_at": end.isoformat() if end else None,
        "row_count": len(bars),
        "duplicate_count": duplicate_count,
        "gap_count": gap_count,
        "cost_estimate": "L/M bounded smoke",
    }
    has_5m_15m_1h = {"5m", "15m", "1h"}.issubset(set(timeframes))
    has_1h = "1h" in timeframes
    yield DataAvailability(
        hypothesis_id="volatility_breakout_high_conviction",
        status="READY" if has_5m_15m_1h and len(bars) > 0 else "MISSING_DATA",
        available=has_5m_15m_1h and len(bars) > 0,
        reason=None if has_5m_15m_1h else "requires 5m, 15m and 1h OHLCV",
        **common,
    )
    yield DataAvailability(
        hypothesis_id="long_timeframe_adaptive_trend",
        status="READY" if has_1h and len(bars) > 0 else "MISSING_DATA",
        available=has_1h and len(bars) > 0,
        reason=None if has_1h else "requires at least 1h OHLCV",
        **common,
    )
    for hypothesis_id in P18B_SKIPPED_HYPOTHESES:
        yield DataAvailability(
            hypothesis_id=hypothesis_id,
            status="MISSING_DATA",
            available=False,
            reason="requires non-OHLCV derivatives/event data not available in this smoke runner",
            **common,
        )


def _run_volatility_breakout(
    config: AlphaSmokeConfig,
    groups: Mapping[tuple[str, str], Sequence[MarketBar]],
    cost_config: ExecutionCostConfig,
) -> SmokeResult:
    started = time.perf_counter()
    discovery_config = HighConvictionDiscoveryConfig(
        run_id=f"{config.run_id}_volatility_breakout",
        data_paths=config.data_paths,
        symbols=tuple(config.symbols[: config.max_symbols]),
        setup_families=("volatility_expansion", "breakout_1h_4h"),
        min_expected_move_bps=(200.0,),
        risk_reward_ratios=(2.0,),
        max_hold_hours=(72.0,),
        exit_modes=("fixed_tp_sl",),
        order_notional_eur=config.order_notional_eur,
        cost_config=cost_config,
        min_sample_trades_for_candidate=50,
    )
    setups = _discover_setups(discovery_config, dict(groups))
    variants = (
        DiscoveryScenario(300.0, 2.0, 48.0, "fixed_tp_sl"),
        DiscoveryScenario(500.0, 2.0, 72.0, "fixed_tp_sl"),
        DiscoveryScenario(500.0, 3.0, 72.0, "fixed_tp_sl"),
    )[: config.max_variants]
    results = [_run_discovery_scenario(discovery_config, scenario, setups, dict(groups)) for scenario in variants]
    variant_rows = tuple(row.to_dict() for row in results)
    best = _best_variant(variant_rows)
    best_label = best.get("scenario", {}).get("label") if best else None
    best_result = next((row for row in results if row.scenario.get("label") == best_label), None)
    metrics = _metrics_from_discovery_result(best_result) if best_result else _metrics(())
    decision, reasons = _decision(metrics, variant_rows, "volatility_breakout_high_conviction")
    return SmokeResult(
        hypothesis_id="volatility_breakout_high_conviction",
        variant_count=len(variants),
        best_variant=best_label,
        decision=decision,
        reasons=tuple(reasons),
        metrics=metrics,
        variants=variant_rows,
        elapsed_seconds=round(time.perf_counter() - started, 6),
    )


def _run_long_trend(
    config: AlphaSmokeConfig,
    groups: Mapping[tuple[str, str], Sequence[MarketBar]],
    cost_config: ExecutionCostConfig,
) -> SmokeResult:
    started = time.perf_counter()
    variants = (
        {"label": "1h_sma20_50_trend150_hold72_rr2", "min_trend_bps": 150.0, "max_hold_bars": 72, "rr": 2.0},
        {"label": "1h_sma20_50_trend250_hold72_rr2", "min_trend_bps": 250.0, "max_hold_bars": 72, "rr": 2.0},
        {"label": "1h_sma20_50_trend250_hold168_rr3", "min_trend_bps": 250.0, "max_hold_bars": 168, "rr": 3.0},
    )[: config.max_variants]
    variant_rows: list[dict[str, Any]] = []
    all_trades: list[_SmokeTrade] = []
    for variant in variants:
        trades = _long_trend_trades(config, groups, cost_config, variant)
        all_trades.extend(trades)
        metrics = _metrics(trades)
        variant_rows.append(
            {
                "scenario": dict(variant),
                "trade_count": metrics.trade_count,
                "net_pnl_eur": metrics.net_pnl_eur,
                "profit_factor": metrics.profit_factor_net,
                "expectancy": metrics.expectancy_net,
                "winrate_pct": metrics.winrate_pct,
                "max_drawdown_eur": metrics.max_drawdown_eur,
                "status": "research_only",
                **RESEARCH_ONLY_CAPITAL_FLAGS,
            }
        )
    best = _best_variant(tuple(variant_rows))
    metrics = _metrics(all_trades)
    decision, reasons = _decision(metrics, tuple(variant_rows), "long_timeframe_adaptive_trend")
    return SmokeResult(
        hypothesis_id="long_timeframe_adaptive_trend",
        variant_count=len(variants),
        best_variant=best.get("scenario", {}).get("label") if best else None,
        decision=decision,
        reasons=tuple(reasons),
        metrics=metrics,
        variants=tuple(variant_rows),
        elapsed_seconds=round(time.perf_counter() - started, 6),
    )


def _long_trend_trades(
    config: AlphaSmokeConfig,
    groups: Mapping[tuple[str, str], Sequence[MarketBar]],
    cost_config: ExecutionCostConfig,
    variant: Mapping[str, Any],
) -> list[_SmokeTrade]:
    trades: list[_SmokeTrade] = []
    cost_bps = cost_config.round_trip_cost_estimate_bps()
    for symbol in config.symbols[: config.max_symbols]:
        rows = list(groups.get((symbol, "1h"), ()))
        if len(rows) < 90:
            continue
        cooldown_until = -1
        for index in range(60, len(rows) - 2):
            if index < cooldown_until:
                continue
            history = rows[: index + 1]
            closes = [bar.close for bar in history]
            sma20 = sum(closes[-20:]) / 20
            sma50 = sum(closes[-50:]) / 50
            trend = _return_bps(closes[-25], closes[-1])
            atr = _atr_bps(history[-24:])
            if sma20 <= sma50 or trend < float(variant["min_trend_bps"]) or atr < 15.0:
                continue
            entry_index = index + 1
            entry = rows[entry_index]
            max_hold = min(int(variant["max_hold_bars"]), len(rows) - entry_index - 1)
            if max_hold <= 0:
                continue
            target = max(300.0, atr * 4.0)
            stop = max(80.0, target / float(variant["rr"]))
            future = rows[entry_index + 1 : entry_index + 1 + max_hold]
            trade = _simulate_long_only_trade(
                symbol=symbol,
                entry=entry,
                future=future,
                target_bps=target,
                stop_bps=stop,
                cost_bps=cost_bps,
                notional_eur=config.order_notional_eur,
                variant=str(variant["label"]),
            )
            if trade:
                trades.append(trade)
                cooldown_until = entry_index + 12
    return trades


def _simulate_long_only_trade(
    *,
    symbol: str,
    entry: MarketBar,
    future: Sequence[MarketBar],
    target_bps: float,
    stop_bps: float,
    cost_bps: float,
    notional_eur: float,
    variant: str,
) -> _SmokeTrade | None:
    if not future or entry.close <= 0:
        return None
    exit_bar = future[-1]
    gross = _return_bps(entry.close, exit_bar.close)
    for bar in future:
        high = _return_bps(entry.close, bar.high)
        low = _return_bps(entry.close, bar.low)
        if low <= -stop_bps:
            exit_bar = bar
            gross = -stop_bps
            break
        if high >= target_bps:
            exit_bar = bar
            gross = target_bps
            break
    net = gross - cost_bps
    return _SmokeTrade(
        symbol=symbol,
        opened_at=entry.timestamp,
        closed_at=exit_bar.timestamp,
        gross_bps=round(gross, 6),
        cost_bps=round(cost_bps, 6),
        net_bps=round(net, 6),
        pnl_eur=round(notional_eur * net / 10_000.0, 6),
        variant=variant,
    )


def _metrics_from_discovery_result(result: Any) -> SmokeMetrics:
    by_symbol = {
        str(symbol): {
            "trade_count": int(row.get("trade_count") or 0),
            "net_pnl_eur": round(float(row.get("net_pnl_eur") or 0.0), 6),
        }
        for symbol, row in dict(getattr(result, "trades_by_symbol", {}) or {}).items()
    }
    return SmokeMetrics(
        trade_count=int(getattr(result, "trade_count", 0) or 0),
        net_pnl_eur=round(float(getattr(result, "net_pnl_eur", 0.0) or 0.0), 6),
        profit_factor_net=getattr(result, "profit_factor", None),
        expectancy_net=(
            float(getattr(result, "net_pnl_eur", 0.0) or 0.0) / int(getattr(result, "trade_count", 0) or 1)
            if int(getattr(result, "trade_count", 0) or 0) > 0
            else None
        ),
        winrate_pct=getattr(result, "winrate_pct", None),
        max_drawdown_eur=round(configure_drawdown_proxy(result), 6),
        total_cost_bps=round(float(getattr(result, "total_gross_return_bps", 0.0) or 0.0) - float(getattr(result, "total_net_return_bps", 0.0) or 0.0), 6),
        no_trade_baseline_eur=0.0,
        by_symbol=by_symbol,
        by_period={},
    )


def configure_drawdown_proxy(result: Any) -> float:
    # Discovery reports drawdown in bps on a 100 EUR default notional. Convert
    # to a small EUR proxy only for display; decisions use PF/expectancy/net PnL.
    return float(getattr(result, "max_drawdown_bps", 0.0) or 0.0) / 100.0


def _metrics(trades: Sequence[_SmokeTrade]) -> SmokeMetrics:
    pnl = [trade.pnl_eur for trade in trades]
    wins = [value for value in pnl if value > 0]
    losses = [value for value in pnl if value < 0]
    by_symbol: dict[str, dict[str, Any]] = {}
    symbol_counts: Counter[str] = Counter()
    symbol_pnl: defaultdict[str, float] = defaultdict(float)
    period_counts: Counter[str] = Counter()
    period_pnl: defaultdict[str, float] = defaultdict(float)
    for trade in trades:
        symbol_counts[trade.symbol] += 1
        symbol_pnl[trade.symbol] += trade.pnl_eur
        period = trade.closed_at.date().isoformat()
        period_counts[period] += 1
        period_pnl[period] += trade.pnl_eur
    for symbol in sorted(symbol_counts):
        by_symbol[symbol] = {"trade_count": symbol_counts[symbol], "net_pnl_eur": round(symbol_pnl[symbol], 6)}
    by_period = {
        period: {"trade_count": period_counts[period], "net_pnl_eur": round(period_pnl[period], 6)}
        for period in sorted(period_counts)
    }
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    return SmokeMetrics(
        trade_count=len(trades),
        net_pnl_eur=round(sum(pnl), 6),
        profit_factor_net=(gross_profit / gross_loss if gross_loss else (None if gross_profit else 0.0)),
        expectancy_net=(sum(pnl) / len(pnl) if pnl else None),
        winrate_pct=(len(wins) / len(pnl) * 100.0 if pnl else None),
        max_drawdown_eur=round(_max_drawdown(pnl), 6),
        total_cost_bps=round(sum(trade.cost_bps for trade in trades), 6),
        no_trade_baseline_eur=0.0,
        by_symbol=by_symbol,
        by_period=by_period,
    )


def _best_variant(variants: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    viable = [row for row in variants if int(row.get("trade_count") or 0) > 0]
    if not viable:
        return None
    return sorted(
        viable,
        key=lambda row: (
            float(row.get("net_pnl_eur") or 0.0),
            float(row.get("profit_factor") or 0.0),
            int(row.get("trade_count") or 0),
        ),
        reverse=True,
    )[0]


def _decision(metrics: SmokeMetrics, variants: Sequence[Mapping[str, Any]], hypothesis_id: str) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if metrics.trade_count == 0:
        return "MISSING_DATA", ["no_executable_smoke_trades"]
    if metrics.net_pnl_eur <= 0:
        reasons.append("edge_net_not_positive")
    if metrics.profit_factor_net is None or metrics.profit_factor_net <= 1.0:
        reasons.append("profit_factor_net_not_above_1")
    if metrics.expectancy_net is None or metrics.expectancy_net <= 0:
        reasons.append("expectancy_net_not_positive")
    if metrics.trade_count < 20:
        reasons.append("sample_size_tiny_smoke_only")
    if all(int(row.get("trade_count") or 0) == 0 for row in variants):
        reasons.append("all_variants_empty")
    if reasons:
        return "REJECT_FAST", reasons
    if metrics.trade_count < 50:
        return "NEEDS_MORE_DATA", ["positive_smoke_but_sample_below_50", "no_shadow_or_paper_allowed"]
    return "KEEP_RESEARCH", ["positive_smoke_requires_walk_forward_before_shadow", "no_shadow_or_paper_allowed"]


def _timeout_result(hypothesis_id: str, started: float) -> SmokeResult:
    return SmokeResult(
        hypothesis_id=hypothesis_id,
        variant_count=0,
        best_variant=None,
        decision="TOO_EXPENSIVE",
        reasons=("max_cpu_seconds_reached",),
        metrics=_metrics(()),
        variants=(),
        elapsed_seconds=round(time.perf_counter() - started, 6),
    )


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


def _recommendation(report: AlphaSmokeReport) -> str:
    keep = [item.hypothesis_id for item in report.tested if item.decision in {"KEEP_RESEARCH", "NEEDS_MORE_DATA"}]
    if keep:
        return f"Continue research-only validation for {', '.join(keep)} with walk-forward before any shadow consideration."
    return "Do not advance to shadow. Either collect richer data or redesign the hypotheses before P18C."


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _return_bps(start: float, end: float) -> float:
    if start <= 0:
        return 0.0
    return ((float(end) / float(start)) - 1.0) * 10_000.0


def _atr_bps(rows: Sequence[MarketBar]) -> float:
    if len(rows) < 2:
        return 0.0
    values: list[float] = []
    previous = float(rows[0].close)
    for row in rows[1:]:
        tr = max(float(row.high) - float(row.low), abs(float(row.high) - previous), abs(float(row.low) - previous))
        if previous > 0:
            values.append(tr / previous * 10_000.0)
        previous = float(row.close)
    return sum(values) / len(values) if values else 0.0


def _max_drawdown(values: Sequence[float]) -> float:
    cumulative = 0.0
    peak = 0.0
    worst = 0.0
    for value in values:
        cumulative += value
        peak = max(peak, cumulative)
        worst = max(worst, peak - cumulative)
    return worst


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.6g}"
    except (TypeError, ValueError):
        return str(value)
