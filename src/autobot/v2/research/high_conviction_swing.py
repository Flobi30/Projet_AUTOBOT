"""Research-only high-conviction swing replay for AUTOBOT.

The module reads persisted decision and market samples, then asks a narrow
question: would recent rejected/observed signals have behaved better if AUTOBOT
only accepted larger, multi-timeframe opportunities with wider exits?

It never submits orders, never mutates the runtime database, never promotes a
strategy, and never changes paper/live flags.
"""

from __future__ import annotations

import bisect
import json
import math
import sqlite3
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any, Literal, Sequence

from .execution_cost_model import ExecutionCostConfig, execution_cost_config_for_profile
from .symbol_normalization import normalize_research_symbol


ExitMode = Literal["fixed_tp_sl", "trailing", "partial_runner"]
SignalSide = Literal["buy", "sell"]

EXPECTED_MOVE_BUCKETS = (
    ("unknown", None, None),
    ("lt_50_bps", None, 50.0),
    ("50_99_bps", 50.0, 100.0),
    ("100_149_bps", 100.0, 150.0),
    ("150_249_bps", 150.0, 250.0),
    ("250_399_bps", 250.0, 400.0),
    ("400_999_bps", 400.0, 1000.0),
    ("gte_1000_bps", 1000.0, None),
)


@dataclass(frozen=True)
class HighConvictionSwingConfig:
    run_id: str
    state_db_path: Path
    output_dir: Path = Path("reports/research/high_conviction_swing")
    symbols: tuple[str, ...] = ()
    lookback_hours: float = 72.0
    start_at: str | None = None
    end_at: str | None = None
    initial_capital_eur: float = 1_000.0
    order_notional_eur: float = 100.0
    min_expected_move_bps: tuple[float, ...] = (100.0, 200.0, 500.0, 1000.0)
    risk_reward_ratios: tuple[float, ...] = (1.5, 2.0, 3.0)
    max_hold_hours: tuple[float, ...] = (6.0, 24.0, 72.0, 168.0)
    exit_modes: tuple[ExitMode, ...] = ("fixed_tp_sl", "trailing", "partial_runner")
    require_mtf_alignment: bool = True
    cost_config: ExecutionCostConfig = field(default_factory=execution_cost_config_for_profile)
    min_sample_trades_for_candidate: int = 20
    candidate_min_profit_factor: float = 1.20
    candidate_max_drawdown_bps: float = 1_500.0

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id must not be empty")
        if self.lookback_hours <= 0:
            raise ValueError("lookback_hours must be positive")
        if self.initial_capital_eur <= 0 or self.order_notional_eur <= 0:
            raise ValueError("capital and notional must be positive")
        if not self.min_expected_move_bps:
            raise ValueError("min_expected_move_bps must not be empty")
        if not self.risk_reward_ratios:
            raise ValueError("risk_reward_ratios must not be empty")
        if not self.max_hold_hours:
            raise ValueError("max_hold_hours must not be empty")
        if not self.exit_modes:
            raise ValueError("exit_modes must not be empty")
        if self.min_sample_trades_for_candidate <= 0:
            raise ValueError("min_sample_trades_for_candidate must be positive")
        for value in (*self.min_expected_move_bps, *self.risk_reward_ratios, *self.max_hold_hours):
            if not math.isfinite(float(value)) or float(value) <= 0:
                raise ValueError("scenario numeric values must be positive and finite")
        for mode in self.exit_modes:
            if mode not in {"fixed_tp_sl", "trailing", "partial_runner"}:
                raise ValueError(f"unsupported exit mode: {mode}")
        self.cost_config.validate()


@dataclass(frozen=True)
class MarketSample:
    symbol: str
    observed_at: datetime
    price: float

    def to_dict(self) -> dict[str, Any]:
        return {"symbol": self.symbol, "observed_at": self.observed_at.isoformat(), "price": self.price}


@dataclass(frozen=True)
class SignalCandidate:
    ledger_id: int
    event_id: str | None
    decision_id: str | None
    signal_id: str | None
    symbol: str
    raw_symbol: str
    strategy: str
    engine: str | None
    side: SignalSide
    timestamp: datetime
    reason: str
    event_type: str
    event_status: str | None
    price: float | None
    gross_edge_bps: float | None
    cost_bps: float | None
    net_edge_bps: float | None
    min_edge_bps: float | None
    spread_bps: float | None
    slippage_bps: float | None
    expected_move_bps: float | None
    adverse_selection_risk: float | None
    blockers: tuple[str, ...]
    raw_payload: dict[str, Any]

    @property
    def usable_for_replay(self) -> bool:
        return self.price is not None and self.expected_move_bps is not None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        return data


@dataclass(frozen=True)
class MultiTimeframeContext:
    return_5m_bps: float | None
    return_15m_bps: float | None
    return_1h_bps: float | None
    return_4h_bps: float | None
    aligned_for_buy: bool
    alignment_score: float
    available_timeframes: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CandidateReplayStats:
    ledger_id: int
    symbol: str
    strategy: str
    timestamp: str
    expected_move_bps: float | None
    cost_bps: float
    mfe_bps: float | None
    mae_bps: float | None
    horizon_available_hours: float
    mtf_context: dict[str, Any]
    asymmetric_score: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ScenarioConfig:
    min_expected_move_bps: float
    risk_reward_ratio: float
    max_hold_hours: float
    exit_mode: ExitMode
    require_mtf_alignment: bool

    @property
    def take_profit_bps(self) -> float:
        return self.min_expected_move_bps

    @property
    def stop_loss_bps(self) -> float:
        return self.take_profit_bps / self.risk_reward_ratio

    def label(self) -> str:
        mtf = "mtf" if self.require_mtf_alignment else "no_mtf"
        return (
            f"{self.exit_mode}__min{self.min_expected_move_bps:g}bps"
            f"__rr{self.risk_reward_ratio:g}__hold{self.max_hold_hours:g}h__{mtf}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "min_expected_move_bps": self.min_expected_move_bps,
            "risk_reward_ratio": self.risk_reward_ratio,
            "take_profit_bps": self.take_profit_bps,
            "stop_loss_bps": self.stop_loss_bps,
            "max_hold_hours": self.max_hold_hours,
            "exit_mode": self.exit_mode,
            "require_mtf_alignment": self.require_mtf_alignment,
            "label": self.label(),
        }


@dataclass(frozen=True)
class SimulatedSwingTrade:
    ledger_id: int
    symbol: str
    strategy: str
    side: SignalSide
    entry_at: str
    exit_at: str
    entry_price: float
    exit_price: float
    gross_return_bps: float
    cost_bps: float
    net_return_bps: float
    pnl_eur: float
    duration_minutes: float
    exit_reason: str
    mfe_bps: float
    mae_bps: float
    asymmetric_score: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ScenarioResult:
    scenario: dict[str, Any]
    evaluated_signals: int
    skipped_low_expected_move: int
    skipped_mtf_misaligned: int
    skipped_missing_market_data: int
    trade_count: int
    net_pnl_eur: float
    gross_return_bps_total: float
    net_return_bps_total: float
    profit_factor: float | None
    winrate_pct: float | None
    expectancy_bps: float | None
    average_win_bps: float | None
    average_loss_bps: float | None
    max_drawdown_bps: float
    average_duration_minutes: float | None
    average_mfe_bps: float | None
    average_mae_bps: float | None
    best_symbol: str | None
    worst_symbol: str | None
    trades_by_symbol: dict[str, dict[str, Any]]
    status: str
    blockers: tuple[str, ...]
    sample_trades: tuple[dict[str, Any], ...]
    live_promotion_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["blockers"] = list(self.blockers)
        data["sample_trades"] = [dict(item) for item in self.sample_trades]
        return data


@dataclass(frozen=True)
class HighConvictionSwingReport:
    run_id: str
    generated_at: str
    state_db_path: str
    decision_window: dict[str, str]
    symbols: tuple[str, ...]
    cost_config: dict[str, Any]
    total_decision_rows: int
    signal_candidates: int
    usable_signal_candidates: int
    expected_move_distribution: dict[str, dict[str, Any]]
    micro_trade_assessment: dict[str, Any]
    top_candidates: tuple[dict[str, Any], ...]
    scenario_results: tuple[ScenarioResult, ...]
    best_scenario: dict[str, Any] | None
    conclusion: str
    recommendations: tuple[str, ...]
    json_report_path: str | None = None
    markdown_report_path: str | None = None
    safety_notes: tuple[str, ...] = (
        "Research-only replay from decision_ledger and market_price_samples.",
        "No official paper/live runtime component is modified or restarted.",
        "No Kraken order can be created by this command.",
        "No strategy registry mutation or promotion is performed.",
        "No instance duplication or live permission is enabled.",
    )
    live_promotion_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "state_db_path": self.state_db_path,
            "decision_window": dict(self.decision_window),
            "symbols": list(self.symbols),
            "cost_config": dict(self.cost_config),
            "total_decision_rows": self.total_decision_rows,
            "signal_candidates": self.signal_candidates,
            "usable_signal_candidates": self.usable_signal_candidates,
            "expected_move_distribution": self.expected_move_distribution,
            "micro_trade_assessment": self.micro_trade_assessment,
            "top_candidates": [dict(item) for item in self.top_candidates],
            "scenario_results": [item.to_dict() for item in self.scenario_results],
            "best_scenario": self.best_scenario,
            "conclusion": self.conclusion,
            "recommendations": list(self.recommendations),
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
            "safety_notes": list(self.safety_notes),
            "live_promotion_allowed": self.live_promotion_allowed,
        }


class _SampleIndex:
    def __init__(self, samples: Sequence[MarketSample]) -> None:
        self._by_symbol: dict[str, list[MarketSample]] = defaultdict(list)
        for sample in sorted(samples, key=lambda item: (item.symbol, item.observed_at)):
            self._by_symbol[sample.symbol].append(sample)
        self._times: dict[str, list[datetime]] = {
            symbol: [sample.observed_at for sample in symbol_samples]
            for symbol, symbol_samples in self._by_symbol.items()
        }

    def at_or_before(self, symbol: str, timestamp: datetime) -> MarketSample | None:
        samples = self._by_symbol.get(symbol, [])
        times = self._times.get(symbol, [])
        index = bisect.bisect_right(times, timestamp) - 1
        if index < 0:
            return None
        return samples[index]

    def after_until(self, symbol: str, start: datetime, end: datetime) -> list[MarketSample]:
        samples = self._by_symbol.get(symbol, [])
        times = self._times.get(symbol, [])
        left = bisect.bisect_right(times, start)
        right = bisect.bisect_right(times, end)
        return samples[left:right]


def build_high_conviction_swing_report(config: HighConvictionSwingConfig) -> HighConvictionSwingReport:
    """Build the read-only high-conviction replay report."""

    rows = _load_decision_rows(config.state_db_path)
    ref_time = _resolve_reference_time(rows, config.end_at)
    start_time = _parse_dt(config.start_at) if config.start_at else ref_time - timedelta(hours=config.lookback_hours)
    end_time = ref_time
    symbols = tuple(normalize_research_symbol(symbol) for symbol in config.symbols if normalize_research_symbol(symbol))
    filtered_rows = [
        row for row in rows
        if _row_in_window(row, start_time, end_time)
        and (not symbols or normalize_research_symbol(str(row.get("symbol") or "")) in symbols)
    ]
    candidates = tuple(_candidate_from_row(row) for row in filtered_rows if _is_signal_candidate(row))

    max_hold = max(config.max_hold_hours) if config.max_hold_hours else 0.0
    samples = _load_market_samples(
        config.state_db_path,
        start_time - timedelta(hours=4),
        end_time + timedelta(hours=max_hold),
        symbols=symbols,
    )
    index = _SampleIndex(samples)
    candidates = tuple(_fill_missing_candidate_price(candidate, index) for candidate in candidates)
    candidate_stats = tuple(
        _candidate_replay_stats(candidate, index, config)
        for candidate in candidates
    )

    scenarios = tuple(
        ScenarioConfig(
            min_expected_move_bps=float(min_move),
            risk_reward_ratio=float(rr),
            max_hold_hours=float(hold),
            exit_mode=mode,
            require_mtf_alignment=config.require_mtf_alignment,
        )
        for min_move in config.min_expected_move_bps
        for rr in config.risk_reward_ratios
        for hold in config.max_hold_hours
        for mode in config.exit_modes
    )
    scenario_results = tuple(_run_scenario(config, scenario, candidates, candidate_stats, index) for scenario in scenarios)
    best = _best_scenario(scenario_results)
    distribution = _expected_move_distribution(candidates)
    micro_assessment = _micro_trade_assessment(candidates, distribution)
    conclusion, recommendations = _build_conclusion(best, scenario_results, micro_assessment)

    return HighConvictionSwingReport(
        run_id=config.run_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        state_db_path=str(config.state_db_path),
        decision_window={"start_at": start_time.isoformat(), "end_at": end_time.isoformat()},
        symbols=tuple(sorted(symbols or {candidate.symbol for candidate in candidates})),
        cost_config=config.cost_config.to_dict(),
        total_decision_rows=len(filtered_rows),
        signal_candidates=len(candidates),
        usable_signal_candidates=sum(1 for candidate in candidates if candidate.usable_for_replay),
        expected_move_distribution=distribution,
        micro_trade_assessment=micro_assessment,
        top_candidates=tuple(_top_candidate_dicts(candidate_stats, limit=20)),
        scenario_results=scenario_results,
        best_scenario=best.to_dict() if best else None,
        conclusion=conclusion,
        recommendations=recommendations,
    )


def write_high_conviction_swing_report(
    report: HighConvictionSwingReport,
    output_dir: str | Path,
) -> HighConvictionSwingReport:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / f"{report.run_id}.json"
    markdown_path = output / f"{report.run_id}.md"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(render_high_conviction_swing_report(report), encoding="utf-8")
    return replace(report, json_report_path=str(json_path), markdown_report_path=str(markdown_path))


def render_high_conviction_swing_report(report: HighConvictionSwingReport) -> str:
    lines = [
        f"# High Conviction Swing Research - {report.run_id}",
        "",
        "## Summary",
        "",
        f"- Generated at: `{report.generated_at}`",
        f"- State DB: `{report.state_db_path}`",
        f"- Window: `{report.decision_window['start_at']}` -> `{report.decision_window['end_at']}`",
        f"- Decision rows scanned: `{report.total_decision_rows}`",
        f"- Signal candidates: `{report.signal_candidates}`",
        f"- Usable for replay: `{report.usable_signal_candidates}`",
        f"- Cost profile: `{report.cost_config.get('cost_profile')}`",
        f"- Round-trip cost estimate: `{_fmt(report.cost_config.get('round_trip_cost_estimate_bps'))} bps`",
        f"- Conclusion: **{report.conclusion}**",
        "",
        "## Expected Move Distribution",
        "",
        "| Bucket | Count | Net-positive | Meets min edge | Avg gross bps | Avg net bps |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for bucket, payload in report.expected_move_distribution.items():
        lines.append(
            f"| {bucket} | {payload['count']} | {payload['net_positive_count']} | "
            f"{payload['meets_min_edge_count']} | {_fmt(payload.get('avg_gross_edge_bps'))} | "
            f"{_fmt(payload.get('avg_net_edge_bps'))} |"
        )

    lines.extend([
        "",
        "## Micro-Trade Assessment",
        "",
    ])
    for key, value in report.micro_trade_assessment.items():
        lines.append(f"- {key}: `{value}`")

    lines.extend([
        "",
        "## Best Scenarios",
        "",
        "| Scenario | Status | Trades | Net PnL EUR | PF | Winrate | Expectancy bps | Max DD bps |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    for result in sorted(report.scenario_results, key=lambda item: item.net_pnl_eur, reverse=True)[:20]:
        lines.append(
            f"| {result.scenario['label']} | {result.status} | {result.trade_count} | "
            f"{_fmt(result.net_pnl_eur)} | {_fmt(result.profit_factor)} | "
            f"{_fmt(result.winrate_pct)} | {_fmt(result.expectancy_bps)} | "
            f"{_fmt(result.max_drawdown_bps)} |"
        )

    lines.extend([
        "",
        "## Top Asymmetric Candidates",
        "",
        "| Symbol | Strategy | Expected bps | Cost bps | MFE bps | MAE bps | MTF score | Asym score | Reason |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ])
    for item in report.top_candidates:
        mtf = item.get("mtf_context", {})
        lines.append(
            f"| {item.get('symbol')} | {item.get('strategy')} | {_fmt(item.get('expected_move_bps'))} | "
            f"{_fmt(item.get('cost_bps'))} | {_fmt(item.get('mfe_bps'))} | {_fmt(item.get('mae_bps'))} | "
            f"{_fmt(mtf.get('alignment_score'))} | {_fmt(item.get('asymmetric_score'))} | "
            f"{item.get('reason')} |"
        )

    lines.extend(["", "## Recommendations", ""])
    lines.extend(f"- {item}" for item in report.recommendations)
    lines.extend(["", "## Safety", ""])
    lines.extend(f"- {item}" for item in report.safety_notes)
    lines.append(f"- live_promotion_allowed: `{report.live_promotion_allowed}`")
    return "\n".join(lines) + "\n"


def _load_decision_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(path)
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        if not _table_exists(connection, "decision_ledger"):
            return []
        columns = _table_columns(connection, "decision_ledger")
        wanted = [
            "id", "event_id", "decision_id", "signal_id", "instance_id", "symbol",
            "strategy", "engine", "event_type", "event_status", "reason", "source",
            "payload_json", "created_at",
        ]
        selected = [column for column in wanted if column in columns]
        if not selected:
            return []
        rows = connection.execute(
            f"SELECT {', '.join(selected)} FROM decision_ledger ORDER BY created_at ASC, id ASC"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def _load_market_samples(
    path: Path,
    start_at: datetime,
    end_at: datetime,
    *,
    symbols: tuple[str, ...],
) -> list[MarketSample]:
    if not path.exists():
        return []
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        if not _table_exists(connection, "market_price_samples"):
            return []
        columns = _table_columns(connection, "market_price_samples")
        if not {"symbol", "price", "observed_at"}.issubset(columns):
            return []
        query = (
            "SELECT symbol, price, observed_at FROM market_price_samples "
            "WHERE observed_at >= ? AND observed_at <= ? ORDER BY observed_at ASC"
        )
        rows = connection.execute(query, (start_at.isoformat(), end_at.isoformat())).fetchall()
    finally:
        connection.close()
    wanted = set(symbols)
    samples: list[MarketSample] = []
    for row in rows:
        symbol = normalize_research_symbol(str(row["symbol"] or ""))
        if wanted and symbol not in wanted:
            continue
        timestamp = _parse_dt(row["observed_at"])
        price = _to_float(row["price"])
        if symbol and price is not None and price > 0:
            samples.append(MarketSample(symbol=symbol, observed_at=timestamp, price=price))
    return samples


def _candidate_from_row(row: dict[str, Any]) -> SignalCandidate:
    payload = _loads_payload(row.get("payload_json"))
    symbol = normalize_research_symbol(str(row.get("symbol") or _find_value(payload, ("symbol", "pair")) or ""))
    reason = str(row.get("reason") or _find_value(payload, ("reason", "rejection_reason", "block_reason")) or "unknown")
    strategy = str(row.get("strategy") or _find_value(payload, ("strategy", "strategy_id")) or "unknown")
    side = _normalize_side(_find_value(payload, ("side", "direction", "action", "signal")) or "buy")
    price = _first_float(payload, ("signal_price", "reference_price", "current_price", "last_price", "market_price", "price"))
    gross = _first_float(payload, ("gross_edge_bps", "expected_gross_edge_bps", "gross_return_bps", "edge_bps"))
    expected = _first_float(payload, ("expected_move_bps", "gross_edge_bps", "expected_gross_edge_bps", "gross_return_bps", "edge_bps"))
    cost = _first_float(payload, ("cost_bps", "total_cost_bps", "estimated_cost_bps", "round_trip_cost_bps"))
    net = _first_float(payload, ("net_edge_bps", "net_return_bps"))
    if net is None and gross is not None and cost is not None:
        net = gross - cost
    min_edge = _first_float(payload, ("min_edge_bps", "required_edge_bps", "adaptive_min_edge_bps"))
    return SignalCandidate(
        ledger_id=int(row.get("id") or 0),
        event_id=_optional_str(row.get("event_id")),
        decision_id=_optional_str(row.get("decision_id")),
        signal_id=_optional_str(row.get("signal_id")),
        symbol=symbol,
        raw_symbol=str(row.get("symbol") or ""),
        strategy=strategy,
        engine=_optional_str(row.get("engine")),
        side=side,
        timestamp=_parse_dt(row.get("created_at")),
        reason=reason,
        event_type=str(row.get("event_type") or ""),
        event_status=_optional_str(row.get("event_status")),
        price=price,
        gross_edge_bps=gross,
        cost_bps=cost,
        net_edge_bps=net,
        min_edge_bps=min_edge,
        spread_bps=_first_float(payload, ("spread_bps", "estimated_spread_bps")),
        slippage_bps=_first_float(payload, ("slippage_bps", "expected_slippage_bps")),
        expected_move_bps=expected,
        adverse_selection_risk=_first_float(payload, ("adverse_selection_risk", "adverse_risk")),
        blockers=_extract_blockers(payload),
        raw_payload=payload,
    )


def _is_signal_candidate(row: dict[str, Any]) -> bool:
    text = " ".join(
        str(row.get(key) or "").lower()
        for key in ("event_type", "event_status", "reason", "payload_json")
    )
    if "router_selected_no_trade" in text and "signal" not in text:
        return False
    return any(token in text for token in (
        "signal", "cost_guard", "microstructure", "opportunity_selection", "rejected",
    ))


def _fill_missing_candidate_price(candidate: SignalCandidate, index: _SampleIndex) -> SignalCandidate:
    if candidate.price is not None and candidate.price > 0:
        return candidate
    sample = index.at_or_before(candidate.symbol, candidate.timestamp)
    if sample is None:
        return candidate
    return replace(candidate, price=sample.price)


def _candidate_replay_stats(
    candidate: SignalCandidate,
    index: _SampleIndex,
    config: HighConvictionSwingConfig,
) -> CandidateReplayStats:
    cost_bps = _candidate_cost_bps(candidate, config)
    max_horizon = max(config.max_hold_hours)
    future = _future_returns(candidate, index, max_horizon)
    returns = [item[1] for item in future]
    mfe = max(returns) if returns else None
    mae = min(returns) if returns else None
    horizon = (future[-1][0] - candidate.timestamp).total_seconds() / 3600.0 if future else 0.0
    mtf = _mtf_context(candidate, index)
    score = _asymmetric_score(candidate, cost_bps, mfe, mae, mtf)
    return CandidateReplayStats(
        ledger_id=candidate.ledger_id,
        symbol=candidate.symbol,
        strategy=candidate.strategy,
        timestamp=candidate.timestamp.isoformat(),
        expected_move_bps=candidate.expected_move_bps,
        cost_bps=cost_bps,
        mfe_bps=mfe,
        mae_bps=mae,
        horizon_available_hours=horizon,
        mtf_context=mtf.to_dict(),
        asymmetric_score=score,
        reason=candidate.reason,
    )


def _run_scenario(
    config: HighConvictionSwingConfig,
    scenario: ScenarioConfig,
    candidates: tuple[SignalCandidate, ...],
    candidate_stats: tuple[CandidateReplayStats, ...],
    index: _SampleIndex,
) -> ScenarioResult:
    stats_by_id = {item.ledger_id: item for item in candidate_stats}
    skipped_low = skipped_mtf = skipped_data = 0
    trades: list[SimulatedSwingTrade] = []
    for candidate in candidates:
        expected = candidate.expected_move_bps
        if expected is None or expected < scenario.min_expected_move_bps:
            skipped_low += 1
            continue
        mtf = _mtf_context(candidate, index)
        if scenario.require_mtf_alignment and not _mtf_passes(candidate, mtf):
            skipped_mtf += 1
            continue
        trade = _simulate_candidate_trade(
            config=config,
            scenario=scenario,
            candidate=candidate,
            index=index,
            candidate_stat=stats_by_id.get(candidate.ledger_id),
        )
        if trade is None:
            skipped_data += 1
            continue
        trades.append(trade)
    return _scenario_result(config, scenario, trades, len(candidates), skipped_low, skipped_mtf, skipped_data)


def _simulate_candidate_trade(
    *,
    config: HighConvictionSwingConfig,
    scenario: ScenarioConfig,
    candidate: SignalCandidate,
    index: _SampleIndex,
    candidate_stat: CandidateReplayStats | None,
) -> SimulatedSwingTrade | None:
    if candidate.price is None or candidate.price <= 0:
        return None
    path = _future_returns(candidate, index, scenario.max_hold_hours)
    if not path:
        return None
    tp = scenario.take_profit_bps
    sl = -scenario.stop_loss_bps
    cost_bps = _candidate_cost_bps(candidate, config)
    mfe = max(value for _, value, _ in path)
    mae = min(value for _, value, _ in path)
    exit_at, exit_return_bps, exit_price, reason = path[-1][0], path[-1][1], path[-1][2], "time_horizon"

    if scenario.exit_mode == "fixed_tp_sl":
        for timestamp, return_bps, price in path:
            if return_bps <= sl:
                exit_at, exit_return_bps, exit_price, reason = timestamp, sl, price, "stop_loss"
                break
            if return_bps >= tp:
                exit_at, exit_return_bps, exit_price, reason = timestamp, tp, price, "take_profit"
                break
    elif scenario.exit_mode == "trailing":
        activated = False
        peak = -math.inf
        activation = tp * 0.5
        for timestamp, return_bps, price in path:
            if not activated and return_bps <= sl:
                exit_at, exit_return_bps, exit_price, reason = timestamp, sl, price, "stop_loss"
                break
            if return_bps >= activation:
                activated = True
                peak = max(peak, return_bps)
            if activated:
                peak = max(peak, return_bps)
                if peak - return_bps >= scenario.stop_loss_bps:
                    exit_at, exit_return_bps, exit_price, reason = timestamp, peak - scenario.stop_loss_bps, price, "trailing_stop"
                    break
    elif scenario.exit_mode == "partial_runner":
        hit_tp = False
        runner_peak = -math.inf
        partial_return = 0.0
        for timestamp, return_bps, price in path:
            if not hit_tp and return_bps <= sl:
                exit_at, exit_return_bps, exit_price, reason = timestamp, sl, price, "stop_loss"
                break
            if not hit_tp and return_bps >= tp:
                hit_tp = True
                partial_return = tp
                runner_peak = return_bps
                exit_at, exit_price, reason = timestamp, price, "partial_tp"
                continue
            if hit_tp:
                runner_peak = max(runner_peak, return_bps)
                if runner_peak - return_bps >= scenario.stop_loss_bps:
                    runner_return = runner_peak - scenario.stop_loss_bps
                    exit_return_bps = (partial_return * 0.5) + (runner_return * 0.5)
                    exit_at, exit_price, reason = timestamp, price, "partial_tp_runner_trailing"
                    break
        else:
            if hit_tp:
                runner_return = path[-1][1]
                exit_return_bps = (partial_return * 0.5) + (runner_return * 0.5)
                exit_at, exit_price, reason = path[-1][0], path[-1][2], "partial_tp_runner_horizon"

    net = exit_return_bps - cost_bps
    duration = max(0.0, (exit_at - candidate.timestamp).total_seconds() / 60.0)
    score = candidate_stat.asymmetric_score if candidate_stat is not None else 0.0
    return SimulatedSwingTrade(
        ledger_id=candidate.ledger_id,
        symbol=candidate.symbol,
        strategy=candidate.strategy,
        side=candidate.side,
        entry_at=candidate.timestamp.isoformat(),
        exit_at=exit_at.isoformat(),
        entry_price=candidate.price,
        exit_price=exit_price,
        gross_return_bps=exit_return_bps,
        cost_bps=cost_bps,
        net_return_bps=net,
        pnl_eur=config.order_notional_eur * (net / 10_000.0),
        duration_minutes=duration,
        exit_reason=reason,
        mfe_bps=mfe,
        mae_bps=mae,
        asymmetric_score=score,
    )


def _scenario_result(
    config: HighConvictionSwingConfig,
    scenario: ScenarioConfig,
    trades: list[SimulatedSwingTrade],
    evaluated: int,
    skipped_low: int,
    skipped_mtf: int,
    skipped_data: int,
) -> ScenarioResult:
    nets = [trade.net_return_bps for trade in trades]
    gross = [trade.gross_return_bps for trade in trades]
    wins = [value for value in nets if value > 0]
    losses = [value for value in nets if value < 0]
    symbol_pnl: dict[str, float] = defaultdict(float)
    symbol_counts: Counter[str] = Counter()
    for trade in trades:
        symbol_pnl[trade.symbol] += trade.pnl_eur
        symbol_counts[trade.symbol] += 1
    trades_by_symbol = {
        symbol: {"trade_count": symbol_counts[symbol], "net_pnl_eur": round(symbol_pnl[symbol], 6)}
        for symbol in sorted(symbol_counts)
    }
    profit_factor = None
    if losses:
        profit_factor = sum(wins) / abs(sum(losses)) if wins else 0.0
    elif wins:
        profit_factor = None
    blockers = _scenario_blockers(config, trades, profit_factor, nets)
    status = "shadow_candidate" if not blockers else "research_only"
    return ScenarioResult(
        scenario=scenario.to_dict(),
        evaluated_signals=evaluated,
        skipped_low_expected_move=skipped_low,
        skipped_mtf_misaligned=skipped_mtf,
        skipped_missing_market_data=skipped_data,
        trade_count=len(trades),
        net_pnl_eur=round(sum(trade.pnl_eur for trade in trades), 6),
        gross_return_bps_total=round(sum(gross), 6),
        net_return_bps_total=round(sum(nets), 6),
        profit_factor=profit_factor,
        winrate_pct=(len(wins) / len(nets) * 100.0) if nets else None,
        expectancy_bps=(sum(nets) / len(nets)) if nets else None,
        average_win_bps=(sum(wins) / len(wins)) if wins else None,
        average_loss_bps=(sum(losses) / len(losses)) if losses else None,
        max_drawdown_bps=_max_drawdown(nets),
        average_duration_minutes=(sum(trade.duration_minutes for trade in trades) / len(trades)) if trades else None,
        average_mfe_bps=(sum(trade.mfe_bps for trade in trades) / len(trades)) if trades else None,
        average_mae_bps=(sum(trade.mae_bps for trade in trades) / len(trades)) if trades else None,
        best_symbol=max(symbol_pnl, key=symbol_pnl.get) if symbol_pnl else None,
        worst_symbol=min(symbol_pnl, key=symbol_pnl.get) if symbol_pnl else None,
        trades_by_symbol=trades_by_symbol,
        status=status,
        blockers=tuple(blockers),
        sample_trades=tuple(trade.to_dict() for trade in sorted(trades, key=lambda item: item.pnl_eur, reverse=True)[:10]),
    )


def _scenario_blockers(
    config: HighConvictionSwingConfig,
    trades: list[SimulatedSwingTrade],
    profit_factor: float | None,
    nets: list[float],
) -> list[str]:
    blockers: list[str] = []
    if len(trades) < config.min_sample_trades_for_candidate:
        blockers.append("sample_size_below_candidate_minimum")
    if sum(nets) <= 0:
        blockers.append("net_return_not_positive_after_costs")
    if profit_factor is None:
        blockers.append("profit_factor_unbounded_or_no_losses_needs_more_sample")
    elif profit_factor < config.candidate_min_profit_factor:
        blockers.append("profit_factor_below_candidate_minimum")
    if _max_drawdown(nets) > config.candidate_max_drawdown_bps:
        blockers.append("drawdown_above_candidate_maximum")
    return blockers


def _future_returns(
    candidate: SignalCandidate,
    index: _SampleIndex,
    horizon_hours: float,
) -> list[tuple[datetime, float, float]]:
    if candidate.price is None or candidate.price <= 0:
        return []
    end = candidate.timestamp + timedelta(hours=horizon_hours)
    samples = index.after_until(candidate.symbol, candidate.timestamp, end)
    result: list[tuple[datetime, float, float]] = []
    for sample in samples:
        if candidate.side == "sell":
            return_bps = ((candidate.price / sample.price) - 1.0) * 10_000.0
        else:
            return_bps = ((sample.price / candidate.price) - 1.0) * 10_000.0
        result.append((sample.observed_at, return_bps, sample.price))
    return result


def _mtf_context(candidate: SignalCandidate, index: _SampleIndex) -> MultiTimeframeContext:
    returns: dict[str, float | None] = {}
    for label, minutes in (("5m", 5), ("15m", 15), ("1h", 60), ("4h", 240)):
        current = candidate.price or (index.at_or_before(candidate.symbol, candidate.timestamp).price if index.at_or_before(candidate.symbol, candidate.timestamp) else None)
        previous = index.at_or_before(candidate.symbol, candidate.timestamp - timedelta(minutes=minutes))
        if current is None or previous is None or previous.price <= 0:
            returns[label] = None
            continue
        raw = ((current / previous.price) - 1.0) * 10_000.0
        returns[label] = -raw if candidate.side == "sell" else raw
    available = [value for value in returns.values() if value is not None]
    positives = [value for value in available if value >= 0.0]
    alignment_score = len(positives) / len(available) if available else 0.0
    aligned = bool(
        (returns["15m"] is None or returns["15m"] >= 0.0)
        and (returns["1h"] is None or returns["1h"] >= 0.0)
        and (returns["4h"] is None or returns["4h"] >= -50.0)
        and len(available) >= 2
    )
    return MultiTimeframeContext(
        return_5m_bps=returns["5m"],
        return_15m_bps=returns["15m"],
        return_1h_bps=returns["1h"],
        return_4h_bps=returns["4h"],
        aligned_for_buy=aligned,
        alignment_score=alignment_score,
        available_timeframes=len(available),
    )


def _mtf_passes(candidate: SignalCandidate, mtf: MultiTimeframeContext) -> bool:
    if candidate.side == "sell":
        return mtf.aligned_for_buy
    return mtf.aligned_for_buy


def _asymmetric_score(
    candidate: SignalCandidate,
    cost_bps: float,
    mfe_bps: float | None,
    mae_bps: float | None,
    mtf: MultiTimeframeContext,
) -> float:
    expected = candidate.expected_move_bps or 0.0
    net_potential = max(0.0, expected - cost_bps)
    potential_component = min(45.0, net_potential / 10.0)
    mtf_component = mtf.alignment_score * 20.0
    spread_penalty = min(15.0, max(0.0, (candidate.spread_bps or 0.0) - 20.0) / 2.0)
    adverse_penalty = min(15.0, max(0.0, (candidate.adverse_selection_risk or 0.0) - 0.50) * 100.0)
    realized_component = 0.0
    if mfe_bps is not None:
        realized_component += min(15.0, max(0.0, mfe_bps - cost_bps) / 10.0)
    if mae_bps is not None:
        realized_component -= min(10.0, max(0.0, abs(mae_bps) - max(50.0, expected * 0.5)) / 10.0)
    return round(max(0.0, min(100.0, potential_component + mtf_component + realized_component - spread_penalty - adverse_penalty)), 3)


def _expected_move_distribution(candidates: tuple[SignalCandidate, ...]) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[SignalCandidate]] = {name: [] for name, _, _ in EXPECTED_MOVE_BUCKETS}
    for candidate in candidates:
        buckets[_bucket_for_expected_move(candidate.expected_move_bps)].append(candidate)
    result: dict[str, dict[str, Any]] = {}
    for name, _, _ in EXPECTED_MOVE_BUCKETS:
        rows = buckets[name]
        gross = [item.gross_edge_bps for item in rows if item.gross_edge_bps is not None]
        net = [item.net_edge_bps for item in rows if item.net_edge_bps is not None]
        result[name] = {
            "count": len(rows),
            "net_positive_count": sum(1 for item in rows if item.net_edge_bps is not None and item.net_edge_bps > 0),
            "meets_min_edge_count": sum(
                1 for item in rows
                if item.net_edge_bps is not None
                and item.min_edge_bps is not None
                and item.net_edge_bps >= item.min_edge_bps
            ),
            "avg_gross_edge_bps": _average(gross),
            "avg_net_edge_bps": _average(net),
        }
    return result


def _micro_trade_assessment(candidates: tuple[SignalCandidate, ...], distribution: dict[str, dict[str, Any]]) -> dict[str, Any]:
    known = [item for item in candidates if item.expected_move_bps is not None]
    under_50 = distribution["lt_50_bps"]["count"]
    under_100 = under_50 + distribution["50_99_bps"]["count"]
    under_150 = under_100 + distribution["100_149_bps"]["count"]
    under_300 = under_150 + distribution["150_249_bps"]["count"] + sum(
        1 for item in candidates if item.expected_move_bps is not None and 250.0 <= item.expected_move_bps < 300.0
    )
    net_sufficient = sum(
        1 for item in known
        if item.net_edge_bps is not None
        and item.min_edge_bps is not None
        and item.net_edge_bps >= item.min_edge_bps
    )
    return {
        "known_expected_move_signals": len(known),
        "signals_under_50_bps": under_50,
        "signals_under_100_bps": under_100,
        "signals_under_150_bps": under_150,
        "signals_under_300_bps": under_300,
        "signals_with_net_edge_above_required_minimum": net_sufficient,
        "orientation": (
            "micro_oriented"
            if known and under_150 / max(1, len(known)) >= 0.50
            else "not_obviously_micro_oriented"
        ),
    }


def _top_candidate_dicts(stats: tuple[CandidateReplayStats, ...], *, limit: int) -> list[dict[str, Any]]:
    return [
        item.to_dict()
        for item in sorted(stats, key=lambda stat: stat.asymmetric_score, reverse=True)[:limit]
    ]


def _best_scenario(results: tuple[ScenarioResult, ...]) -> ScenarioResult | None:
    viable = [item for item in results if item.trade_count > 0]
    if not viable:
        return None
    return sorted(
        viable,
        key=lambda item: (
            item.status == "shadow_candidate",
            item.net_pnl_eur,
            item.profit_factor or 0.0,
            -(item.max_drawdown_bps or 0.0),
        ),
        reverse=True,
    )[0]


def _build_conclusion(
    best: ScenarioResult | None,
    results: tuple[ScenarioResult, ...],
    micro_assessment: dict[str, Any],
) -> tuple[str, tuple[str, ...]]:
    recommendations: list[str] = [
        "Keep this high-conviction logic in research/paper-only until a larger sample proves net edge after costs.",
        "Do not promote any swing variant automatically; require official paper validation and human review.",
        "Keep micro-trades learning-only unless they beat the same cost profile with enough closed trades.",
        "Use multi-timeframe alignment and mandatory stop-loss/trailing rules for any future controlled paper test.",
        "Do not enable leverage or instance duplication before a strategy/pair passes PF, drawdown and sample-size gates.",
    ]
    if best is None:
        return "insufficient_market_data_for_swing_replay", tuple(recommendations)
    if best.status == "shadow_candidate":
        recommendations.insert(0, "One scenario is worth further shadow/paper-controlled investigation, not live promotion.")
        return "high_conviction_shadow_candidate_found", tuple(recommendations)
    if micro_assessment.get("orientation") == "micro_oriented":
        recommendations.insert(0, "Recent signals are too micro-oriented; larger potential filters should be researched before paper execution.")
        return "micro_trade_bias_detected_no_candidate_yet", tuple(recommendations)
    recommendations.insert(0, "No high-conviction configuration passed candidate gates on this sample.")
    return "no_high_conviction_candidate_yet", tuple(recommendations)


def _bucket_for_expected_move(value: float | None) -> str:
    if value is None:
        return "unknown"
    for name, lower, upper in EXPECTED_MOVE_BUCKETS:
        if name == "unknown":
            continue
        if lower is not None and value < lower:
            continue
        if upper is not None and value >= upper:
            continue
        return name
    return "unknown"


def _candidate_cost_bps(candidate: SignalCandidate, config: HighConvictionSwingConfig) -> float:
    if candidate.cost_bps is not None and candidate.cost_bps >= 0:
        return candidate.cost_bps
    return config.cost_config.round_trip_cost_estimate_bps()


def _max_drawdown(values: Sequence[float]) -> float:
    peak = 0.0
    cumulative = 0.0
    max_dd = 0.0
    for value in values:
        cumulative += value
        peak = max(peak, cumulative)
        max_dd = max(max_dd, peak - cumulative)
    return max_dd


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    row = connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return row is not None


def _table_columns(connection: sqlite3.Connection, name: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({name})").fetchall()}


def _resolve_reference_time(rows: list[dict[str, Any]], end_at: str | None) -> datetime:
    if end_at:
        return _parse_dt(end_at)
    timestamps = [_parse_dt(row.get("created_at")) for row in rows if row.get("created_at")]
    return max(timestamps) if timestamps else datetime.now(timezone.utc)


def _row_in_window(row: dict[str, Any], start_at: datetime, end_at: datetime) -> bool:
    timestamp = _parse_dt(row.get("created_at"))
    return start_at <= timestamp <= end_at


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value or "").strip()
    if not text:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _loads_payload(text: Any) -> dict[str, Any]:
    if not text:
        return {}
    try:
        payload = json.loads(str(text))
    except json.JSONDecodeError:
        return {"_invalid_payload_json": str(text)}
    return payload if isinstance(payload, dict) else {"payload": payload}


def _find_value(payload: Any, keys: tuple[str, ...]) -> Any:
    wanted = {key.lower() for key in keys}
    if isinstance(payload, dict):
        for key, value in payload.items():
            if str(key).lower() in wanted:
                return value
        for value in payload.values():
            nested = _find_value(value, keys)
            if nested is not None:
                return nested
    elif isinstance(payload, list):
        for item in payload:
            nested = _find_value(item, keys)
            if nested is not None:
                return nested
    return None


def _first_float(payload: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    return _to_float(_find_value(payload, keys))


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        result = float(value)
        return result if math.isfinite(result) else None
    text = str(value).strip().replace("%", "")
    try:
        result = float(text)
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def _normalize_side(value: Any) -> SignalSide:
    text = str(value or "").strip().lower()
    if text in {"sell", "short"}:
        return "sell"
    return "buy"


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _extract_blockers(payload: dict[str, Any]) -> tuple[str, ...]:
    raw = _find_value(payload, ("blockers", "risk_blockers", "reasons"))
    if isinstance(raw, list):
        return tuple(str(item) for item in raw)
    if isinstance(raw, tuple):
        return tuple(str(item) for item in raw)
    if raw is None:
        return ()
    return (str(raw),)


def _average(values: Sequence[float | None]) -> float | None:
    cleaned = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    return sum(cleaned) / len(cleaned) if cleaned else None


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, str):
        return value
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(number):
        return "n/a"
    return f"{number:.3f}"
