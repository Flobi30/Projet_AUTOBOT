"""Forward-safe net-edge simulation for shadow-paper observations.

This module is research-only and read-only. It evaluates whether a pre-entry
``forward_safe_net_edge`` estimate could have filtered shadow observations
without using the current trade's realized outcome.
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Mapping, Sequence

from autobot.v2.cost_profiles import DEFAULT_PAPER_COST_PROFILE, CostProfile, get_cost_profile
from autobot.v2.paper.ledger_quality import (
    critical_ledger_warning_reason,
    critical_warning_counts,
    has_critical_ledger_warning,
    loader_warning_counts,
)
from autobot.v2.paper.ledger_loader import load_state_db_paper_ledger
from autobot.v2.research.trade_journal import TradeRecord
from autobot.v2.strategy_runtime_policy import (
    LEGACY_UNATTRIBUTED_STRATEGY_ID,
    shadow_paper_strategy_block_reason,
)


SCORE_BUCKETS = ("high", "medium", "low", "missing")
SEGMENT_POLICIES = ("block_shadow_future", "watch", "forward_edge_watch", "insufficient_data", "observe")
FORBIDDEN_FORWARD_INPUT_KEYS = frozenset(
    {
        "closed_at",
        "closing_decision",
        "closing_leg",
        "exit",
        "exit_price",
        "exit_reason",
        "future_close",
        "gross_pnl",
        "gross_pnl_eur",
        "mae_bps",
        "mfe_bps",
        "net_pnl",
        "net_pnl_eur",
        "outcome",
        "post_trade_bucket",
        "realized_pnl",
        "trade_result",
    }
)
FORBIDDEN_CONTAINER_KEYS = frozenset({"closing_decision", "closing_leg", "slippage"})


class LookaheadInputError(ValueError):
    """Raised when a forward-edge input contains post-entry/outcome fields."""


@dataclass(frozen=True)
class ForwardEdgeSimulationConfig:
    state_db_path: Path
    output_dir: Path = Path("reports/paper/forward_edge_simulation")
    run_id: str | None = None
    initial_capital_eur: float = 1_000.0
    cost_profile_name: str = DEFAULT_PAPER_COST_PROFILE
    top_quantile_fraction: float = 0.20
    write_report: bool = True
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def resolved_run_id(self) -> str:
        if self.run_id:
            return self.run_id
        return f"forward_edge_simulation_{self.generated_at.strftime('%Y%m%d_%H%M%S')}"


@dataclass(frozen=True)
class ForwardSafeNetEdgeInput:
    strategy_id: str
    symbol: str
    opened_at: str
    timeframe: str | None
    regime: str | None
    score_bucket: str
    opportunity_score: float | None
    expected_move_bps: float | None
    estimated_fees_bps: float | None
    estimated_spread_cost_bps: float | None
    estimated_slippage_bps: float | None
    latency_buffer_bps: float | None
    estimated_total_cost_bps: float | None
    pair_health_penalty_bps: float
    segment_health_penalty_bps: float
    trade_frequency_penalty_bps: float
    drawdown_penalty_bps: float
    cost_profile: str
    cost_source: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ForwardSafeNetEdgeEstimate:
    strategy_id: str
    symbol: str
    timeframe: str | None
    score_bucket: str
    opportunity_score: float | None
    expected_move_bps: float | None
    estimated_fees_bps: float | None
    estimated_spread_cost_bps: float | None
    estimated_slippage_bps: float | None
    latency_buffer_bps: float | None
    estimated_total_cost_bps: float | None
    segment_health_penalty_bps: float
    pair_health_penalty_bps: float
    risk_penalties_bps: float
    estimated_net_edge_bps: float | None
    forward_cost_adjusted_score: float | None
    confidence_level: str
    reject_reason: str | None
    input_used_for_decision: dict[str, Any]
    forbidden_input_paths: tuple[str, ...] = ()
    raw_forbidden_paths_seen: tuple[str, ...] = ()
    promotable: bool = False
    paper_capital_allowed: bool = False
    live_allowed: bool = False

    @property
    def is_valid(self) -> bool:
        return self.reject_reason is None and self.estimated_net_edge_bps is not None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["forbidden_input_paths"] = list(self.forbidden_input_paths)
        data["raw_forbidden_paths_seen"] = list(self.raw_forbidden_paths_seen)
        return data


@dataclass(frozen=True)
class ForwardEdgeScenario:
    name: str
    description: str
    trade_count: int
    gross_pnl_eur: float
    net_pnl_eur: float
    fees_eur: float
    slippage_eur: float
    gross_profit_factor: float | None
    net_profit_factor: float | None
    net_expectancy_eur: float | None
    winrate_net_pct: float | None
    max_drawdown_eur: float
    max_drawdown_pct: float
    confidence_level: str
    reject_reason_counts: dict[str, int]
    promotable: bool = False
    paper_capital_allowed: bool = False
    live_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ForwardEdgeSegmentPolicy:
    key: dict[str, str]
    trade_count: int
    policy: str
    reasons: tuple[str, ...]
    average_estimated_net_edge_bps: float | None
    gross_pnl_eur: float
    net_pnl_eur: float
    fees_eur: float
    slippage_eur: float
    gross_profit_factor: float | None
    net_profit_factor: float | None
    net_expectancy_eur: float | None
    confidence_level: str
    shadow_routing_allowed: bool
    paper_capital_allowed: bool = False
    live_allowed: bool = False
    promotable: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["reasons"] = list(self.reasons)
        return data


@dataclass(frozen=True)
class ForwardEdgeSimulationReport:
    run_id: str
    generated_at: str
    state_db_path: str
    cost_profile: dict[str, Any]
    total_trade_count: int
    eligible_trade_count: int
    legacy_excluded_trade_count: int
    policy_excluded_trade_count: int
    quality_excluded_trade_count: int
    input_audit: dict[str, Any]
    bucket_counts: dict[str, int]
    estimate_counts: dict[str, int]
    scenarios: tuple[ForwardEdgeScenario, ...]
    segment_policy: tuple[ForwardEdgeSegmentPolicy, ...]
    safety_notes: tuple[str, ...]
    warnings: tuple[str, ...] = ()
    json_report_path: str | None = None
    markdown_report_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "state_db_path": self.state_db_path,
            "cost_profile": self.cost_profile,
            "total_trade_count": self.total_trade_count,
            "eligible_trade_count": self.eligible_trade_count,
            "legacy_excluded_trade_count": self.legacy_excluded_trade_count,
            "policy_excluded_trade_count": self.policy_excluded_trade_count,
            "quality_excluded_trade_count": self.quality_excluded_trade_count,
            "input_audit": self.input_audit,
            "bucket_counts": dict(self.bucket_counts),
            "estimate_counts": dict(self.estimate_counts),
            "scenarios": [item.to_dict() for item in self.scenarios],
            "segment_policy": [item.to_dict() for item in self.segment_policy],
            "safety_notes": list(self.safety_notes),
            "warnings": list(self.warnings),
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
        }


def audit_forward_edge_input(source: Mapping[str, Any]) -> tuple[str, ...]:
    paths = _forbidden_paths(source)
    if paths:
        raise LookaheadInputError(f"forward edge input contains post-entry fields: {', '.join(paths)}")
    return ()


def estimate_forward_safe_net_edge(source: Mapping[str, Any] | ForwardSafeNetEdgeInput) -> ForwardSafeNetEdgeEstimate:
    if isinstance(source, ForwardSafeNetEdgeInput):
        input_data = source
        audit_source = source.to_dict()
    else:
        audit_forward_edge_input(source)
        input_data = _input_from_mapping(source)
        audit_source = dict(source)
    forbidden = _forbidden_paths(audit_source)
    if forbidden:
        raise LookaheadInputError(f"forward edge input contains post-entry fields: {', '.join(forbidden)}")

    missing: list[str] = []
    if input_data.opportunity_score is None:
        missing.append("opportunity_score_missing")
    if input_data.expected_move_bps is None:
        missing.append("expected_move_missing")
    if input_data.estimated_total_cost_bps is None:
        missing.append("estimated_cost_missing")
    if missing:
        return _estimate_from_input(
            input_data,
            estimated_net_edge_bps=None,
            adjusted_score=None,
            reject_reason=";".join(missing),
            confidence_level="insufficient_data",
            forbidden_input_paths=(),
        )

    risk_penalties = _risk_penalties(input_data)
    estimated_net_edge = (
        float(input_data.expected_move_bps)
        - float(input_data.estimated_total_cost_bps)
        - risk_penalties
    )
    adjusted_score = _forward_cost_adjusted_score(input_data, estimated_net_edge, risk_penalties)
    confidence = "forward_edge_positive" if estimated_net_edge > 0.0 else "forward_edge_negative"
    return _estimate_from_input(
        input_data,
        estimated_net_edge_bps=estimated_net_edge,
        adjusted_score=adjusted_score,
        reject_reason=None,
        confidence_level=confidence,
        forbidden_input_paths=(),
    )


def build_forward_edge_simulation_report(config: ForwardEdgeSimulationConfig) -> ForwardEdgeSimulationReport:
    if config.initial_capital_eur <= 0.0:
        raise ValueError("initial_capital_eur must be positive")
    if not (0.0 < config.top_quantile_fraction <= 1.0):
        raise ValueError("top_quantile_fraction must be in (0, 1]")

    cost_profile = get_cost_profile(config.cost_profile_name)
    loaded = load_state_db_paper_ledger(config.state_db_path, include_decisions=True)
    all_records = tuple(loaded.journal.records)
    policy_candidates = tuple(record for record in all_records if _is_policy_candidate(record))
    quality_excluded = tuple(record for record in policy_candidates if has_critical_ledger_warning(record))
    eligible = tuple(record for record in policy_candidates if not has_critical_ledger_warning(record))
    legacy = tuple(record for record in all_records if _is_legacy(record))
    policy_excluded = tuple(
        record for record in all_records if not _is_legacy(record) and not _is_policy_candidate(record)
    )
    estimate_pairs = _estimate_records(eligible, cost_profile)
    scenarios = _build_scenarios(estimate_pairs, config.initial_capital_eur, config.top_quantile_fraction)
    segment_policy = _build_segment_policy(estimate_pairs, config.initial_capital_eur)
    raw_forbidden_counter: Counter[str] = Counter()
    for _record, estimate in estimate_pairs:
        for path in estimate.raw_forbidden_paths_seen:
            raw_forbidden_counter[path] += 1

    report = ForwardEdgeSimulationReport(
        run_id=config.resolved_run_id,
        generated_at=config.generated_at.isoformat(),
        state_db_path=str(config.state_db_path),
        cost_profile=cost_profile.to_dict(),
        total_trade_count=len(all_records),
        eligible_trade_count=len(eligible),
        legacy_excluded_trade_count=len(legacy),
        policy_excluded_trade_count=len(policy_excluded),
        quality_excluded_trade_count=len(quality_excluded),
        input_audit={
            "decision_uses_post_trade_data": False,
            "forbidden_fields_used": [],
            "raw_forbidden_fields_seen_but_excluded": dict(sorted(raw_forbidden_counter.items())),
            "raw_forbidden_fields_seen_count": sum(raw_forbidden_counter.values()),
            "note": "Raw loaded records contain closing/outcome fields for evaluation only; sanitized estimator inputs exclude them.",
        },
        bucket_counts=_bucket_counts(eligible),
        estimate_counts=_estimate_counts(estimate_pairs),
        scenarios=scenarios,
        segment_policy=segment_policy,
        safety_notes=(
            "Read-only simulation over existing attributed observations.",
            "Forward-safe selection uses sanitized pre-entry fields only.",
            "Realized gross/net PnL is used only after selection to evaluate scenarios.",
            "All scenarios, watch statuses, and segment policies are non-promotable.",
            "No order, paper capital allocation, live flag, or strategy promotion is created.",
            "Grid/legacy/unattributed rows are excluded from executable conclusions.",
            "Rows with critical ledger quality warnings are counted but excluded from scenarios.",
        ),
        warnings=tuple(loaded.warnings),
    )
    if not config.write_report:
        return report
    return write_forward_edge_simulation_report(report, config.output_dir)


def write_forward_edge_simulation_report(
    report: ForwardEdgeSimulationReport,
    output_dir: str | Path,
) -> ForwardEdgeSimulationReport:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    base = output / report.run_id
    json_path = base.with_suffix(".json")
    markdown_path = base.with_suffix(".md")
    report_with_paths = replace(report, json_report_path=str(json_path), markdown_report_path=str(markdown_path))
    json_path.write_text(json.dumps(report_with_paths.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(_markdown(report_with_paths), encoding="utf-8")
    return report_with_paths


def shadow_routing_allowed_by_forward_policy(policy: Mapping[str, Any] | ForwardEdgeSegmentPolicy) -> bool:
    if isinstance(policy, ForwardEdgeSegmentPolicy):
        return policy.policy != "block_shadow_future"
    return str(policy.get("policy") or "") != "block_shadow_future"


def _estimate_from_input(
    input_data: ForwardSafeNetEdgeInput,
    *,
    estimated_net_edge_bps: float | None,
    adjusted_score: float | None,
    reject_reason: str | None,
    confidence_level: str,
    forbidden_input_paths: tuple[str, ...],
) -> ForwardSafeNetEdgeEstimate:
    risk_penalties = _risk_penalties(input_data)
    return ForwardSafeNetEdgeEstimate(
        strategy_id=input_data.strategy_id,
        symbol=input_data.symbol,
        timeframe=input_data.timeframe,
        score_bucket=input_data.score_bucket,
        opportunity_score=input_data.opportunity_score,
        expected_move_bps=input_data.expected_move_bps,
        estimated_fees_bps=input_data.estimated_fees_bps,
        estimated_spread_cost_bps=input_data.estimated_spread_cost_bps,
        estimated_slippage_bps=input_data.estimated_slippage_bps,
        latency_buffer_bps=input_data.latency_buffer_bps,
        estimated_total_cost_bps=input_data.estimated_total_cost_bps,
        segment_health_penalty_bps=input_data.segment_health_penalty_bps,
        pair_health_penalty_bps=input_data.pair_health_penalty_bps,
        risk_penalties_bps=risk_penalties,
        estimated_net_edge_bps=estimated_net_edge_bps,
        forward_cost_adjusted_score=adjusted_score,
        confidence_level=confidence_level,
        reject_reason=reject_reason,
        input_used_for_decision=input_data.to_dict(),
        forbidden_input_paths=forbidden_input_paths,
    )


def _input_from_mapping(source: Mapping[str, Any]) -> ForwardSafeNetEdgeInput:
    return ForwardSafeNetEdgeInput(
        strategy_id=str(source.get("strategy_id") or "unknown"),
        symbol=str(source.get("symbol") or "UNKNOWN").upper(),
        opened_at=str(source.get("opened_at") or ""),
        timeframe=str(source.get("timeframe")) if source.get("timeframe") not in (None, "") else None,
        regime=str(source.get("regime")) if source.get("regime") not in (None, "") else None,
        score_bucket=str(source.get("score_bucket") or _score_bucket(_optional_float(source.get("opportunity_score")))),
        opportunity_score=_optional_float(source.get("opportunity_score")),
        expected_move_bps=_optional_float(source.get("expected_move_bps")),
        estimated_fees_bps=_optional_float(source.get("estimated_fees_bps")),
        estimated_spread_cost_bps=_optional_float(source.get("estimated_spread_cost_bps")),
        estimated_slippage_bps=_optional_float(source.get("estimated_slippage_bps")),
        latency_buffer_bps=_optional_float(source.get("latency_buffer_bps")),
        estimated_total_cost_bps=_optional_float(source.get("estimated_total_cost_bps")),
        pair_health_penalty_bps=_safe_float(source.get("pair_health_penalty_bps")),
        segment_health_penalty_bps=_safe_float(source.get("segment_health_penalty_bps")),
        trade_frequency_penalty_bps=_safe_float(source.get("trade_frequency_penalty_bps")),
        drawdown_penalty_bps=_safe_float(source.get("drawdown_penalty_bps")),
        cost_profile=str(source.get("cost_profile") or DEFAULT_PAPER_COST_PROFILE),
        cost_source=str(source.get("cost_source") or "unknown"),
    )


def _estimate_records(
    records: Sequence[TradeRecord],
    cost_profile: CostProfile,
) -> tuple[tuple[TradeRecord, ForwardSafeNetEdgeEstimate], ...]:
    symbol_history: dict[str, list[TradeRecord]] = defaultdict(list)
    segment_history: dict[tuple[str, str], list[TradeRecord]] = defaultdict(list)
    pairs: list[tuple[TradeRecord, ForwardSafeNetEdgeEstimate]] = []
    for record in sorted(records, key=lambda item: (item.opened_at, item.closed_at, item.strategy_id, item.symbol)):
        input_data = _forward_input_from_record(
            record,
            cost_profile=cost_profile,
            symbol_history=tuple(symbol_history[str(record.symbol)]),
            segment_history=tuple(segment_history[(str(record.strategy_id), str(record.symbol))]),
        )
        estimate = estimate_forward_safe_net_edge(input_data)
        estimate = replace(estimate, raw_forbidden_paths_seen=_forbidden_paths(record.metadata))
        pairs.append((record, estimate))
        symbol_history[str(record.symbol)].append(record)
        segment_history[(str(record.strategy_id), str(record.symbol))].append(record)
    return tuple(pairs)


def _forward_input_from_record(
    record: TradeRecord,
    *,
    cost_profile: CostProfile,
    symbol_history: Sequence[TradeRecord],
    segment_history: Sequence[TradeRecord],
) -> ForwardSafeNetEdgeInput:
    metadata_sources = _pre_entry_metadata_sources(record)
    score = _score_from_sources(metadata_sources)
    expected_move = _first_float_from_sources(
        metadata_sources,
        (
            "expected_move_bps",
            "expected_gross_edge_bps",
            "gross_edge_bps",
            "expected_edge_bps",
            "target_move_bps",
            "gross_edge",
        ),
    )
    fees_bps, spread_bps, slippage_bps, latency_bps, total_cost_bps, cost_source = _cost_components(
        metadata_sources,
        cost_profile,
    )
    segment_penalty = _history_penalty(segment_history)
    pair_penalty = _history_penalty(symbol_history)
    return ForwardSafeNetEdgeInput(
        strategy_id=str(record.strategy_id or "unknown"),
        symbol=str(record.symbol or "UNKNOWN").upper(),
        opened_at=record.opened_at.isoformat(),
        timeframe=_string_from_sources(metadata_sources, ("timeframe",)),
        regime=record.regime,
        score_bucket=_score_bucket(score),
        opportunity_score=score,
        expected_move_bps=expected_move,
        estimated_fees_bps=fees_bps,
        estimated_spread_cost_bps=spread_bps,
        estimated_slippage_bps=slippage_bps,
        latency_buffer_bps=latency_bps,
        estimated_total_cost_bps=total_cost_bps,
        pair_health_penalty_bps=pair_penalty,
        segment_health_penalty_bps=segment_penalty,
        trade_frequency_penalty_bps=_frequency_penalty(segment_history, record.opened_at),
        drawdown_penalty_bps=_drawdown_penalty(segment_history),
        cost_profile=cost_profile.name,
        cost_source=cost_source,
    )


def _pre_entry_metadata_sources(record: TradeRecord) -> tuple[Mapping[str, Any], ...]:
    sources: list[Mapping[str, Any]] = []
    metadata = record.metadata if isinstance(record.metadata, Mapping) else {}
    sanitized_root = _sanitize_pre_entry_mapping(metadata)
    if sanitized_root:
        sources.append(sanitized_root)
    for key in (
        "ledger_metadata",
        "opportunity_components",
        "edge_context",
        "opportunity",
        "regime_context",
        "components",
        "metadata",
    ):
        value = metadata.get(key)
        if isinstance(value, Mapping):
            sanitized = _sanitize_pre_entry_mapping(value)
            if sanitized:
                sources.append(sanitized)
    return tuple(sources)


def _sanitize_pre_entry_mapping(source: Mapping[str, Any]) -> dict[str, Any]:
    """Return a recursive allow-through copy with post-trade containers removed."""

    cleaned: dict[str, Any] = {}
    for key, value in source.items():
        normalized = str(key).lower()
        if normalized in FORBIDDEN_FORWARD_INPUT_KEYS or normalized in FORBIDDEN_CONTAINER_KEYS:
            continue
        if isinstance(value, Mapping):
            nested = _sanitize_pre_entry_mapping(value)
            if nested:
                cleaned[str(key)] = nested
            continue
        if isinstance(value, (list, tuple)):
            nested_items = []
            for item in value:
                if isinstance(item, Mapping):
                    nested = _sanitize_pre_entry_mapping(item)
                    if nested:
                        nested_items.append(nested)
                elif not isinstance(item, (list, tuple)):
                    nested_items.append(item)
            if nested_items:
                cleaned[str(key)] = nested_items
            continue
        cleaned[str(key)] = value
    return cleaned


def _cost_components(
    sources: Sequence[Mapping[str, Any]],
    cost_profile: CostProfile,
) -> tuple[float | None, float | None, float | None, float | None, float | None, str]:
    explicit_total = _first_float_from_sources(
        sources,
        (
            "estimated_total_cost_bps",
            "total_cost_bps",
            "cost_bps",
            "estimated_round_trip_cost_bps",
            "round_trip_cost_bps",
        ),
    )
    fees = _first_float_from_sources(
        sources,
        ("estimated_fees_bps", "estimated_fee_bps", "fee_bps", "fees_bps", "round_trip_fee_bps"),
    )
    spread = _first_float_from_sources(
        sources,
        ("estimated_spread_cost_bps", "estimated_spread_bps", "spread_cost_bps", "spread_bps"),
    )
    slippage = _first_float_from_sources(
        sources,
        (
            "estimated_slippage_bps",
            "expected_slippage_bps",
            "slippage_cost_bps",
            "round_trip_slippage_bps",
        ),
    )
    latency = _first_float_from_sources(sources, ("latency_buffer_bps", "estimated_latency_bps"))
    if explicit_total is not None:
        return (
            fees,
            spread,
            slippage,
            latency,
            max(0.0, explicit_total),
            "metadata_estimated_total_cost",
        )
    fees = fees if fees is not None else cost_profile.fee_bps(cost_profile.entry_liquidity) + cost_profile.fee_bps(
        cost_profile.exit_liquidity
    )
    spread = spread if spread is not None else cost_profile.fallback_spread_bps * cost_profile.spread_charge_fraction
    slippage = slippage if slippage is not None else 2.0 * cost_profile.slippage_bps_per_leg
    latency = latency if latency is not None else 2.0 * cost_profile.latency_buffer_bps_per_leg
    total = max(0.0, fees + spread + slippage + latency)
    return fees, spread, slippage, latency, total, "cost_profile_fallback"


def _risk_penalties(input_data: ForwardSafeNetEdgeInput) -> float:
    return max(
        0.0,
        float(input_data.segment_health_penalty_bps or 0.0)
        + float(input_data.pair_health_penalty_bps or 0.0)
        + float(input_data.trade_frequency_penalty_bps or 0.0)
        + float(input_data.drawdown_penalty_bps or 0.0),
    )


def _forward_cost_adjusted_score(
    input_data: ForwardSafeNetEdgeInput,
    estimated_net_edge_bps: float,
    risk_penalties_bps: float,
) -> float | None:
    if input_data.opportunity_score is None or input_data.expected_move_bps is None:
        return None
    score = float(input_data.opportunity_score)
    expected = max(float(input_data.expected_move_bps), 1.0)
    total_cost = float(input_data.estimated_total_cost_bps or 0.0)
    cost_to_expected = total_cost / expected
    penalty = 0.0
    if cost_to_expected > 0.55:
        penalty += min(45.0, (cost_to_expected - 0.55) * 100.0)
    if estimated_net_edge_bps <= 0.0:
        penalty += min(35.0, abs(estimated_net_edge_bps) / 5.0)
    penalty += min(30.0, risk_penalties_bps / 2.0)
    return _clamp_score(score - penalty)


def _build_scenarios(
    estimate_pairs: Sequence[tuple[TradeRecord, ForwardSafeNetEdgeEstimate]],
    initial_capital_eur: float,
    top_quantile_fraction: float,
) -> tuple[ForwardEdgeScenario, ...]:
    valid = tuple(pair for pair in estimate_pairs if pair[1].is_valid)
    positive = tuple(pair for pair in valid if float(pair[1].estimated_net_edge_bps or 0.0) > 0.0)
    top_count = max(1, int(math.ceil(len(valid) * top_quantile_fraction))) if valid else 0
    top_quantile = tuple(
        sorted(valid, key=lambda pair: float(pair[1].estimated_net_edge_bps or -1e12), reverse=True)[:top_count]
    )
    definitions = (
        (
            "all_scored",
            "All observations with a pre-entry opportunity_score.",
            tuple(pair for pair in estimate_pairs if pair[1].opportunity_score is not None),
        ),
        (
            "opportunity_high_current",
            "Existing high score bucket without forward-edge filtering.",
            tuple(pair for pair in estimate_pairs if pair[1].score_bucket == "high"),
        ),
        (
            "cost_aware_high",
            "Pre-entry score adjusted by estimated costs and prior health penalties.",
            tuple(pair for pair in estimate_pairs if (pair[1].forward_cost_adjusted_score or -1.0) >= 70.0),
        ),
        (
            "forward_safe_net_edge_positive",
            "Sanitized forward_safe_net_edge strictly above zero.",
            positive,
        ),
        (
            "forward_safe_net_edge_top_quantile",
            f"Top {top_quantile_fraction:.0%} valid forward_safe_net_edge observations.",
            top_quantile,
        ),
        (
            "forward_safe_net_edge_plus_score_high",
            "Positive forward_safe_net_edge and existing high bucket.",
            tuple(pair for pair in positive if pair[1].score_bucket == "high"),
        ),
    )
    return tuple(
        _scenario(name, description, pairs, initial_capital_eur)
        for name, description, pairs in definitions
    )


def _scenario(
    name: str,
    description: str,
    estimate_pairs: Sequence[tuple[TradeRecord, ForwardSafeNetEdgeEstimate]],
    initial_capital_eur: float,
) -> ForwardEdgeScenario:
    records = tuple(record for record, _estimate in estimate_pairs)
    gross_values = [record.gross_pnl_eur for record in records]
    net_values = [record.net_pnl_eur for record in records]
    net_pnl = sum(net_values)
    count = len(records)
    pf_net = _profit_factor(net_values)
    expectancy = net_pnl / count if count else None
    max_dd_eur, max_dd_pct = _max_drawdown(records, initial_capital_eur)
    reject_counts: Counter[str] = Counter()
    for _record, estimate in estimate_pairs:
        if estimate.reject_reason:
            reject_counts[estimate.reject_reason] += 1
    return ForwardEdgeScenario(
        name=name,
        description=description,
        trade_count=count,
        gross_pnl_eur=sum(gross_values),
        net_pnl_eur=net_pnl,
        fees_eur=sum(record.fees_eur for record in records),
        slippage_eur=sum(record.slippage_eur for record in records),
        gross_profit_factor=_profit_factor(gross_values),
        net_profit_factor=pf_net,
        net_expectancy_eur=expectancy,
        winrate_net_pct=(sum(1 for value in net_values if value > 0.0) / count * 100.0) if count else None,
        max_drawdown_eur=max_dd_eur,
        max_drawdown_pct=max_dd_pct,
        confidence_level=_confidence_level(count, pf_net, expectancy, net_pnl),
        reject_reason_counts=dict(sorted(reject_counts.items())),
        promotable=False,
        paper_capital_allowed=False,
        live_allowed=False,
    )


def _build_segment_policy(
    estimate_pairs: Sequence[tuple[TradeRecord, ForwardSafeNetEdgeEstimate]],
    initial_capital_eur: float,
) -> tuple[ForwardEdgeSegmentPolicy, ...]:
    groups: dict[tuple[str, str, str], list[tuple[TradeRecord, ForwardSafeNetEdgeEstimate]]] = defaultdict(list)
    for record, estimate in estimate_pairs:
        groups[(estimate.score_bucket, str(record.strategy_id or "unknown"), str(record.symbol or "unknown"))].append(
            (record, estimate)
        )
    policies = [
        _segment_policy_for_pairs(
            {"score_bucket": bucket, "strategy_id": strategy_id, "symbol": symbol},
            tuple(items),
            initial_capital_eur,
        )
        for (bucket, strategy_id, symbol), items in groups.items()
    ]
    return tuple(
        sorted(
            policies,
            key=lambda item: (
                _policy_rank(item.policy),
                item.net_pnl_eur,
                item.net_profit_factor if item.net_profit_factor is not None else -1.0,
                item.trade_count,
            ),
        )
    )


def _segment_policy_for_pairs(
    key: Mapping[str, str],
    estimate_pairs: Sequence[tuple[TradeRecord, ForwardSafeNetEdgeEstimate]],
    initial_capital_eur: float,
) -> ForwardEdgeSegmentPolicy:
    records = tuple(record for record, _estimate in estimate_pairs)
    estimates = tuple(estimate for _record, estimate in estimate_pairs)
    net_values = [record.net_pnl_eur for record in records]
    gross_values = [record.gross_pnl_eur for record in records]
    net_pnl = sum(net_values)
    gross_pnl = sum(gross_values)
    fees = sum(record.fees_eur for record in records)
    slippage = sum(record.slippage_eur for record in records)
    count = len(records)
    net_pf = _profit_factor(net_values)
    gross_pf = _profit_factor(gross_values)
    expectancy = net_pnl / count if count else None
    valid_edges = [
        float(estimate.estimated_net_edge_bps)
        for estimate in estimates
        if estimate.estimated_net_edge_bps is not None
    ]
    avg_forward_edge = mean(valid_edges) if valid_edges else None
    bucket = str(key.get("score_bucket") or "missing")
    reasons: list[str] = []
    if count < 10:
        reasons.append("insufficient_sample_size")
    if bucket == "low":
        reasons.append("low_bucket_non_promotable")
    if bucket == "missing":
        reasons.append("missing_score_non_promotable")
    if avg_forward_edge is None:
        reasons.append("forward_edge_insufficient_data")
    elif avg_forward_edge > 0.0:
        reasons.append("forward_edge_positive_watch_only")
    else:
        reasons.append("forward_edge_not_positive")
    if net_pnl < 0.0:
        reasons.append("negative_net_pnl")
    if net_pf is not None and net_pf < 0.75:
        reasons.append("net_pf_very_weak")
    elif net_pf is not None and net_pf <= 1.0:
        reasons.append("net_pf_not_above_1")
    if gross_pf is not None and gross_pf > 1.0 and (net_pf is None or net_pf < 1.0):
        reasons.append("gross_positive_net_negative_after_costs")

    policy = "observe"
    if count < 10:
        policy = "insufficient_data"
    elif bucket == "low" and ("net_pf_very_weak" in reasons or net_pnl < 0.0):
        policy = "block_shadow_future"
    elif bucket == "missing" and count >= 30 and net_pnl < 0.0:
        policy = "block_shadow_future"
    elif "gross_positive_net_negative_after_costs" in reasons and (net_pf is None or net_pf < 0.75):
        policy = "block_shadow_future"
    elif net_pnl <= -5.0 and (net_pf is None or net_pf < 0.75):
        policy = "block_shadow_future"
    elif avg_forward_edge is not None and avg_forward_edge > 0.0:
        policy = "forward_edge_watch"
    elif bucket == "high" or (net_pf is not None and net_pf > 1.0):
        policy = "watch"
    max_dd_eur, max_dd_pct = _max_drawdown(records, initial_capital_eur)
    return ForwardEdgeSegmentPolicy(
        key=dict(key),
        trade_count=count,
        policy=policy,
        reasons=tuple(dict.fromkeys(reasons)),
        average_estimated_net_edge_bps=avg_forward_edge,
        gross_pnl_eur=gross_pnl,
        net_pnl_eur=net_pnl,
        fees_eur=fees,
        slippage_eur=slippage,
        gross_profit_factor=gross_pf,
        net_profit_factor=net_pf,
        net_expectancy_eur=expectancy,
        confidence_level=_confidence_level(count, net_pf, expectancy, net_pnl),
        shadow_routing_allowed=policy != "block_shadow_future",
        paper_capital_allowed=False,
        live_allowed=False,
        promotable=False,
    )


def _history_penalty(records: Sequence[TradeRecord]) -> float:
    if len(records) < 10:
        return 0.0
    recent = tuple(sorted(records, key=lambda item: item.closed_at)[-50:])
    net_values = [record.net_pnl_eur for record in recent]
    net_pf = _profit_factor(net_values)
    expectancy = sum(net_values) / len(net_values) if net_values else 0.0
    penalty = 0.0
    if net_pf is None:
        penalty += 10.0 if expectancy <= 0.0 else 0.0
    elif net_pf < 1.0:
        penalty += min(35.0, (1.0 - net_pf) * 25.0)
    if expectancy < 0.0:
        penalty += min(25.0, abs(expectancy) * 15.0)
    return min(50.0, penalty)


def _frequency_penalty(records: Sequence[TradeRecord], opened_at: datetime) -> float:
    prior_24h = [
        record for record in records if 0.0 <= (opened_at - record.opened_at).total_seconds() <= 86_400.0
    ]
    if len(prior_24h) <= 25:
        return 0.0
    net_pf = _profit_factor([record.net_pnl_eur for record in prior_24h])
    if net_pf is not None and net_pf > 1.0:
        return 0.0
    return min(25.0, (len(prior_24h) - 25) * 0.75)


def _drawdown_penalty(records: Sequence[TradeRecord]) -> float:
    if len(records) < 10:
        return 0.0
    _dd_eur, dd_pct = _max_drawdown(tuple(sorted(records, key=lambda item: item.closed_at)[-50:]), 1_000.0)
    if dd_pct <= 5.0:
        return 0.0
    return min(30.0, (dd_pct - 5.0) * 1.5)


def _forbidden_paths(source: Any, prefix: str = "") -> tuple[str, ...]:
    paths: list[str] = []
    if isinstance(source, Mapping):
        for key, value in source.items():
            normalized = str(key).lower()
            path = f"{prefix}.{key}" if prefix else str(key)
            if normalized in FORBIDDEN_FORWARD_INPUT_KEYS:
                paths.append(path)
                continue
            if normalized in FORBIDDEN_CONTAINER_KEYS:
                paths.append(path)
                continue
            paths.extend(_forbidden_paths(value, path))
    elif isinstance(source, (list, tuple)):
        for index, value in enumerate(source):
            path = f"{prefix}[{index}]"
            paths.extend(_forbidden_paths(value, path))
    return tuple(paths)


def _first_float_from_sources(sources: Sequence[Mapping[str, Any]], keys: Sequence[str]) -> float | None:
    for source in sources:
        value = _first_float(source, keys)
        if value is not None:
            return value
    return None


def _first_float(source: Mapping[str, Any], keys: Sequence[str]) -> float | None:
    for key in keys:
        value = source.get(key)
        parsed = _optional_float(value)
        if parsed is not None:
            return parsed
    for value in source.values():
        if isinstance(value, Mapping):
            nested = _first_float(value, keys)
            if nested is not None:
                return nested
    return None


def _string_from_sources(sources: Sequence[Mapping[str, Any]], keys: Sequence[str]) -> str | None:
    for source in sources:
        for key in keys:
            value = source.get(key)
            if value not in (None, ""):
                return str(value)
    return None


def _score_from_sources(sources: Sequence[Mapping[str, Any]]) -> float | None:
    return _first_float_from_sources(sources, ("opportunity_score", "score", "final_score", "base_score"))


def _score_bucket(score: float | None) -> str:
    if score is None:
        return "missing"
    if score >= 70.0:
        return "high"
    if score >= 40.0:
        return "medium"
    return "low"


def _bucket_counts(records: Sequence[TradeRecord]) -> dict[str, int]:
    counts = {bucket: 0 for bucket in SCORE_BUCKETS}
    for record in records:
        counts[_score_bucket(_score_from_sources(_pre_entry_metadata_sources(record)))] += 1
    return counts


def _estimate_counts(
    estimate_pairs: Sequence[tuple[TradeRecord, ForwardSafeNetEdgeEstimate]],
) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for _record, estimate in estimate_pairs:
        counts[estimate.confidence_level] += 1
        if estimate.reject_reason:
            counts[estimate.reject_reason] += 1
        elif estimate.estimated_net_edge_bps is not None and estimate.estimated_net_edge_bps > 0.0:
            counts["estimated_net_edge_positive"] += 1
        elif estimate.estimated_net_edge_bps is not None:
            counts["estimated_net_edge_non_positive"] += 1
    return dict(sorted(counts.items()))


def _is_policy_candidate(record: TradeRecord) -> bool:
    if _is_legacy(record):
        return False
    return shadow_paper_strategy_block_reason(record.strategy_id) is None


def _is_legacy(record: TradeRecord) -> bool:
    return record.strategy_id in ("", LEGACY_UNATTRIBUTED_STRATEGY_ID)


def _confidence_level(
    trade_count: int,
    net_profit_factor: float | None,
    expectancy: float | None,
    net_pnl: float,
) -> str:
    if trade_count < 50:
        return "insufficient_data"
    if net_pnl <= 0.0 or expectancy is None or expectancy <= 0.0 or net_profit_factor is None or net_profit_factor <= 1.0:
        return "rejected"
    if trade_count < 100:
        return "early_signal"
    return "usable"


def _profit_factor(values: Sequence[float]) -> float | None:
    if not values:
        return None
    wins = sum(value for value in values if value > 0.0)
    losses = abs(sum(value for value in values if value < 0.0))
    if losses == 0.0:
        return None
    return wins / losses


def _max_drawdown(records: Sequence[TradeRecord], initial_capital_eur: float) -> tuple[float, float]:
    equity = float(initial_capital_eur)
    peak = float(initial_capital_eur)
    max_drawdown = 0.0
    max_drawdown_pct = 0.0
    for record in sorted(records, key=lambda item: item.closed_at):
        equity += record.net_pnl_eur
        peak = max(peak, equity)
        drawdown = max(0.0, peak - equity)
        max_drawdown = max(max_drawdown, drawdown)
        if peak > 0.0:
            max_drawdown_pct = max(max_drawdown_pct, drawdown / peak * 100.0)
    return max_drawdown, max_drawdown_pct


def _policy_rank(policy: str) -> int:
    return {
        "block_shadow_future": 0,
        "forward_edge_watch": 1,
        "watch": 2,
        "insufficient_data": 3,
        "observe": 4,
    }.get(policy, 9)


def _safe_float(value: Any, default: float = 0.0) -> float:
    parsed = _optional_float(value)
    return default if parsed is None else parsed


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _clamp_score(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def _fmt(value: float | None) -> str:
    if value is None or not math.isfinite(value):
        return "n/a"
    return f"{value:.4f}"


def _markdown(report: ForwardEdgeSimulationReport) -> str:
    lines = [
        f"# Forward Edge Simulation - {report.run_id}",
        "",
        f"- Generated: `{report.generated_at}`",
        f"- Eligible trades: `{report.eligible_trade_count}`",
        f"- Legacy excluded trades: `{report.legacy_excluded_trade_count}`",
        f"- Policy excluded trades: `{report.policy_excluded_trade_count}`",
        f"- Quality excluded trades: `{report.quality_excluded_trade_count}`",
        f"- Cost profile: `{report.cost_profile.get('name')}`",
        "",
        "## Anti-Lookahead Audit",
        "",
        f"- Decision uses post-trade data: `{str(report.input_audit.get('decision_uses_post_trade_data')).lower()}`",
        f"- Forbidden fields used: `{len(report.input_audit.get('forbidden_fields_used') or [])}`",
        f"- Raw forbidden fields seen but excluded: `{report.input_audit.get('raw_forbidden_fields_seen_count', 0)}`",
        "",
        "## Bucket Counts",
        "",
    ]
    for bucket in SCORE_BUCKETS:
        lines.append(f"- `{bucket}`: `{report.bucket_counts.get(bucket, 0)}`")
    lines.extend(["", "## Estimate Counts", ""])
    if report.estimate_counts:
        lines.extend(f"- `{key}`: `{value}`" for key, value in sorted(report.estimate_counts.items()))
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Scenarios",
            "",
            "| Scenario | Trades | Net PnL | PF gross | PF net | Expectancy | Fees | Slippage | Max DD | Confidence | Promotable |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
        ]
    )
    for scenario in report.scenarios:
        lines.append(
            "| {name} | {trades} | {net:.2f} | {gpf} | {npf} | {exp} | {fees:.2f} | {slippage:.2f} | {dd:.2f} | {conf} | {promo} |".format(
                name=scenario.name,
                trades=scenario.trade_count,
                net=scenario.net_pnl_eur,
                gpf=_fmt(scenario.gross_profit_factor),
                npf=_fmt(scenario.net_profit_factor),
                exp=_fmt(scenario.net_expectancy_eur),
                fees=scenario.fees_eur,
                slippage=scenario.slippage_eur,
                dd=scenario.max_drawdown_eur,
                conf=scenario.confidence_level,
                promo=str(scenario.promotable).lower(),
            )
        )
    policy_counts: Counter[str] = Counter(item.policy for item in report.segment_policy)
    lines.extend(["", "## Segment Policy P10", ""])
    if policy_counts:
        lines.extend(f"- `{key}`: `{value}`" for key, value in sorted(policy_counts.items()))
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "| Policy | Segment | Trades | Avg forward edge | Net PnL | PF net | Expectancy | Shadow routing | Reasons |",
            "|---|---|---:|---:|---:|---:|---:|---|---|",
        ]
    )
    for item in report.segment_policy[:40]:
        segment = ", ".join(f"{key}={value}" for key, value in item.key.items())
        lines.append(
            "| {policy} | {segment} | {trades} | {edge} | {net:.2f} | {npf} | {exp} | {routing} | {reasons} |".format(
                policy=item.policy,
                segment=segment,
                trades=item.trade_count,
                edge=_fmt(item.average_estimated_net_edge_bps),
                net=item.net_pnl_eur,
                npf=_fmt(item.net_profit_factor),
                exp=_fmt(item.net_expectancy_eur),
                routing=str(item.shadow_routing_allowed).lower(),
                reasons=", ".join(item.reasons) or "none",
            )
        )
    lines.extend(["", "## Safety Notes", ""])
    lines.extend(f"- {note}" for note in report.safety_notes)
    if report.warnings:
        lines.extend(["", "## Loader Warnings", ""])
        counts = loader_warning_counts(report.warnings)
        lines.extend(f"- `{key}`: `{value}`" for key, value in sorted(counts.items()))
    return "\n".join(lines) + "\n"
