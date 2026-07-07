"""Research-only audit of AUTOBOT opportunity scoring and alpha signal quality.

The audit explains why current ``opportunity_score`` values can remain
compressed, compares score buckets with forward-safe net-edge estimates, and
simulates alternative score formulas without changing runtime routing.

All simulated scores are non-promotable and read-only. Realized PnL is used
only after a bucket/group is selected to evaluate whether the score would have
separated better and worse observations.
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Callable, Mapping, Sequence

from autobot.v2.cost_profiles import DEFAULT_PAPER_COST_PROFILE, get_cost_profile
from autobot.v2.opportunity_scoring import OpportunityConfig
from autobot.v2.paper.forward_edge_simulation import (
    SCORE_BUCKETS,
    ForwardSafeNetEdgeEstimate,
    LookaheadInputError,
    _estimate_records,
    _is_legacy,
    _is_policy_candidate,
    _pre_entry_metadata_sources,
    audit_forward_edge_input,
)
from autobot.v2.paper.forward_edge_validation import resolve_cutoff
from autobot.v2.paper.ledger_quality import has_critical_ledger_warning, loader_warning_counts
from autobot.v2.paper.ledger_loader import load_state_db_paper_ledger
from autobot.v2.research.trade_journal import TradeRecord


SCORE_VARIANTS = (
    "current_score",
    "recalibrated_v1",
    "cost_aware",
    "high_conviction_aware",
    "forward_edge_aware",
)
HIGH_THRESHOLD = 70.0
MEDIUM_THRESHOLD = 40.0
NEAR_HIGH_LOWER_BOUND = 60.0
HIGH_CONVICTION_STRATEGY_ID = "high_conviction_swing"
HIGH_CONVICTION_COMPONENTS: dict[str, tuple[str, ...]] = {
    "breakout_quality": ("breakout_quality", "breakout_score", "breakout_strength"),
    "volatility_expansion": ("volatility_expansion", "volatility_expansion_score", "atr_expansion_bps"),
    "momentum_confirmation": ("momentum_confirmation", "momentum_score", "momentum_persistence", "trend_strength"),
    "support_resistance": ("support_resistance", "support_strength", "support_distance_bps", "resistance_distance_bps"),
    "trend_context": ("trend_context", "trend_regime", "trend_timeframe_alignment", "multi_timeframe_alignment"),
    "risk_reward": ("risk_reward", "risk_reward_ratio", "rr", "tp_sl_ratio"),
    "liquidity_spread": ("estimated_spread_cost_bps", "spread_bps", "liquidity_score", "depth_score"),
    "pair_health": ("pair_health_penalty_bps", "pair_health_score", "pair_health"),
    "segment_health": ("segment_health_penalty_bps", "segment_health_score", "segment_health"),
}
FORBIDDEN_SCORE_VARIANT_KEYS = frozenset(
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


@dataclass(frozen=True)
class OpportunityScoreAuditConfig:
    state_db_path: Path
    since: str | None = None
    since_commit: str | None = None
    output_dir: Path = Path("reports/paper/opportunity_score_audit")
    run_id: str | None = None
    initial_capital_eur: float = 1_000.0
    cost_profile_name: str = DEFAULT_PAPER_COST_PROFILE
    write_report: bool = True
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def resolved_run_id(self) -> str:
        if self.run_id:
            return self.run_id
        return f"opportunity_score_audit_{self.generated_at.strftime('%Y%m%d_%H%M%S')}"


@dataclass(frozen=True)
class ScoreDistribution:
    count: int
    min_score: float | None
    max_score: float | None
    median_score: float | None
    p90_score: float | None
    high_count: int
    near_high_count: int
    bucket_counts: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BucketMetrics:
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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ScoreVariantReport:
    name: str
    description: str
    uses_future_data: bool
    promotable: bool
    paper_capital_allowed: bool
    live_allowed: bool
    distribution: ScoreDistribution
    bucket_metrics: dict[str, BucketMetrics]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "uses_future_data": self.uses_future_data,
            "promotable": self.promotable,
            "paper_capital_allowed": self.paper_capital_allowed,
            "live_allowed": self.live_allowed,
            "distribution": self.distribution.to_dict(),
            "bucket_metrics": {bucket: metrics.to_dict() for bucket, metrics in self.bucket_metrics.items()},
        }


@dataclass(frozen=True)
class OpportunityScoreAuditReport:
    run_id: str
    generated_at: str
    state_db_path: str
    cutoff: dict[str, Any]
    cost_profile: dict[str, Any]
    opportunity_formula: dict[str, Any]
    total_trade_count: int
    eligible_trade_count: int
    legacy_excluded_trade_count: int
    policy_excluded_trade_count: int
    quality_excluded_trade_count: int
    current_distribution: ScoreDistribution
    current_bucket_metrics: dict[str, BucketMetrics]
    formula_diagnostics: dict[str, Any]
    correlations: dict[str, Any]
    forward_edge_alignment: dict[str, Any]
    high_conviction_analysis: dict[str, Any]
    score_variants: tuple[ScoreVariantReport, ...]
    anti_lookahead_audit: dict[str, Any]
    root_causes: tuple[str, ...]
    p13_recommendations: tuple[str, ...]
    safety_notes: tuple[str, ...]
    warnings: tuple[str, ...] = ()
    json_report_path: str | None = None
    markdown_report_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "state_db_path": self.state_db_path,
            "cutoff": dict(self.cutoff),
            "cost_profile": dict(self.cost_profile),
            "opportunity_formula": dict(self.opportunity_formula),
            "total_trade_count": self.total_trade_count,
            "eligible_trade_count": self.eligible_trade_count,
            "legacy_excluded_trade_count": self.legacy_excluded_trade_count,
            "policy_excluded_trade_count": self.policy_excluded_trade_count,
            "quality_excluded_trade_count": self.quality_excluded_trade_count,
            "current_distribution": self.current_distribution.to_dict(),
            "current_bucket_metrics": {bucket: metrics.to_dict() for bucket, metrics in self.current_bucket_metrics.items()},
            "formula_diagnostics": dict(self.formula_diagnostics),
            "correlations": dict(self.correlations),
            "forward_edge_alignment": dict(self.forward_edge_alignment),
            "high_conviction_analysis": dict(self.high_conviction_analysis),
            "score_variants": [variant.to_dict() for variant in self.score_variants],
            "anti_lookahead_audit": dict(self.anti_lookahead_audit),
            "root_causes": list(self.root_causes),
            "p13_recommendations": list(self.p13_recommendations),
            "safety_notes": list(self.safety_notes),
            "warnings": list(self.warnings),
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
        }


def build_opportunity_score_audit_report(config: OpportunityScoreAuditConfig) -> OpportunityScoreAuditReport:
    if config.initial_capital_eur <= 0.0:
        raise ValueError("initial_capital_eur must be positive")
    cost_profile = get_cost_profile(config.cost_profile_name)
    loaded = load_state_db_paper_ledger(config.state_db_path, include_decisions=True)
    all_records = tuple(loaded.journal.records)
    filtered_records = _filter_since(all_records, config)
    policy_candidates = tuple(record for record in filtered_records if _is_policy_candidate(record))
    quality_excluded = tuple(record for record in policy_candidates if has_critical_ledger_warning(record))
    eligible = tuple(record for record in policy_candidates if not has_critical_ledger_warning(record))
    legacy = tuple(record for record in filtered_records if _is_legacy(record))
    policy_excluded = tuple(
        record for record in filtered_records if not _is_legacy(record) and not _is_policy_candidate(record)
    )
    estimate_pairs = _estimate_records(eligible, cost_profile)
    current_scores = _scores_for_variant(estimate_pairs, "current_score")
    current_distribution = _distribution(current_scores)
    current_bucket_metrics = _bucket_metrics_for_scores(estimate_pairs, current_scores, config.initial_capital_eur)
    formula_diagnostics = _formula_diagnostics(estimate_pairs)
    correlations = _correlations(estimate_pairs, current_scores)
    forward_alignment = _forward_edge_alignment(estimate_pairs, current_scores)
    high_conviction = _high_conviction_analysis(estimate_pairs)
    variants = tuple(_variant_report(estimate_pairs, name, config.initial_capital_eur) for name in SCORE_VARIANTS)
    anti_lookahead = _anti_lookahead_audit(estimate_pairs)
    root_causes = _root_causes(current_distribution, forward_alignment, high_conviction, formula_diagnostics)
    report = OpportunityScoreAuditReport(
        run_id=config.resolved_run_id,
        generated_at=config.generated_at.isoformat(),
        state_db_path=str(config.state_db_path),
        cutoff=_cutoff_summary(config),
        cost_profile=cost_profile.to_dict(),
        opportunity_formula=_opportunity_formula_summary(),
        total_trade_count=len(filtered_records),
        eligible_trade_count=len(eligible),
        legacy_excluded_trade_count=len(legacy),
        policy_excluded_trade_count=len(policy_excluded),
        quality_excluded_trade_count=len(quality_excluded),
        current_distribution=current_distribution,
        current_bucket_metrics=current_bucket_metrics,
        formula_diagnostics=formula_diagnostics,
        correlations=correlations,
        forward_edge_alignment=forward_alignment,
        high_conviction_analysis=high_conviction,
        score_variants=variants,
        anti_lookahead_audit=anti_lookahead,
        root_causes=root_causes,
        p13_recommendations=_p13_recommendations(root_causes, high_conviction),
        safety_notes=(
            "Read-only score audit over attributed shadow observations.",
            "Recalibrated scores are simulations only and do not mutate router, registry, ledger, paper capital, or live flags.",
            "High threshold remains 70.0 for every simulated variant.",
            "Variant scoring uses only sanitized pre-entry fields and forward-safe estimates.",
            "Realized PnL is used only after grouping to evaluate buckets.",
            "All variants are promotable=false, paper_capital_allowed=false, live_allowed=false.",
            "Grid/legacy/unattributed rows and critical ledger-warning rows are excluded from executable conclusions.",
        ),
        warnings=tuple(loaded.warnings),
    )
    if not config.write_report:
        return report
    return write_opportunity_score_audit_report(report, config.output_dir)


def write_opportunity_score_audit_report(
    report: OpportunityScoreAuditReport,
    output_dir: str | Path,
) -> OpportunityScoreAuditReport:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    base = output / report.run_id
    json_path = base.with_suffix(".json")
    markdown_path = base.with_suffix(".md")
    report_with_paths = replace(report, json_report_path=str(json_path), markdown_report_path=str(markdown_path))
    json_path.write_text(json.dumps(report_with_paths.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(_markdown(report_with_paths), encoding="utf-8")
    return report_with_paths


def calculate_score_variant(name: str, source: Mapping[str, Any]) -> float | None:
    """Calculate one research-only score variant from pre-entry fields.

    The function intentionally raises when post-trade/outcome keys are present.
    Tests use it as the public anti-lookahead contract for P12.
    """

    _audit_score_variant_input(source)
    if name not in SCORE_VARIANTS:
        raise ValueError(f"unknown score variant: {name}")
    current_score = _optional_float(source.get("opportunity_score"))
    if name == "current_score":
        return _clamp_score(current_score) if current_score is not None else None
    expected_move = _optional_float(source.get("expected_move_bps"))
    total_cost = _optional_float(source.get("estimated_total_cost_bps"))
    estimated_net_edge = _optional_float(source.get("estimated_net_edge_bps"))
    risk_penalties = _safe_float(source.get("risk_penalties_bps"))
    strategy_id = str(source.get("strategy_id") or "")
    if expected_move is None or total_cost is None or estimated_net_edge is None:
        return None
    if name == "recalibrated_v1":
        return _recalibrated_v1_score(current_score, expected_move, total_cost, estimated_net_edge, risk_penalties)
    if name == "cost_aware":
        return _cost_aware_score(current_score, expected_move, total_cost, estimated_net_edge, risk_penalties)
    if name == "high_conviction_aware":
        return _high_conviction_aware_score(
            current_score,
            expected_move,
            total_cost,
            estimated_net_edge,
            risk_penalties,
            strategy_id=strategy_id,
            source=source,
        )
    if name == "forward_edge_aware":
        return _forward_edge_aware_score(current_score, expected_move, total_cost, estimated_net_edge, risk_penalties)
    return None


def _filter_since(records: Sequence[TradeRecord], config: OpportunityScoreAuditConfig) -> tuple[TradeRecord, ...]:
    if not config.since and not config.since_commit:
        return tuple(records)
    cutoff = resolve_cutoff(config.since, config.since_commit)
    return tuple(record for record in records if record.opened_at >= cutoff)


def _cutoff_summary(config: OpportunityScoreAuditConfig) -> dict[str, Any]:
    if not config.since and not config.since_commit:
        return {"criterion": "all_loaded_records", "since": None, "since_commit": None}
    cutoff = resolve_cutoff(config.since, config.since_commit)
    return {
        "criterion": "record.opened_at >= cutoff",
        "since": cutoff.isoformat(),
        "since_commit": config.since_commit,
    }


def _opportunity_formula_summary() -> dict[str, Any]:
    cfg = OpportunityConfig()
    return {
        "runtime_formula": "base_score + regime_adjustment + health_adjustment",
        "min_score_high_threshold": cfg.min_score,
        "bucket_thresholds": {"high": HIGH_THRESHOLD, "medium": MEDIUM_THRESHOLD, "low": 0.0},
        "normalizers": {
            "gross_edge": f"gross_edge_bps / ({cfg.min_gross_edge_bps} * 2)",
            "net_edge": f"(net_edge_bps - {cfg.min_net_edge_bps}) / {cfg.min_gross_edge_bps}",
            "cost": f"1 - cost_bps / {cfg.max_cost_bps}",
            "volatility": f"ATR bps in [{cfg.min_atr_bps}, {cfg.max_atr_bps}]",
            "spread": f"1 - spread_bps / {cfg.max_spread_bps}",
            "liquidity": "market composite/volume normalized 0..1",
            "stability": "recent same-side signal stability 0..1",
        },
        "weights": {
            "gross_edge": 20.0,
            "net_edge": 30.0,
            "cost": 15.0,
            "volatility": 15.0,
            "spread": 10.0,
            "liquidity": 5.0,
            "stability": 5.0,
        },
        "blockers": {
            "gross_edge_below": cfg.min_gross_edge_bps,
            "net_edge_below": cfg.min_net_edge_bps,
            "atr_below": cfg.min_atr_bps,
            "spread_above": cfg.max_spread_bps,
            "stability_below": cfg.min_stability,
            "score_below": cfg.min_score,
        },
        "p12_note": "P12 does not change this runtime formula or thresholds.",
    }


def _formula_diagnostics(
    estimate_pairs: Sequence[tuple[TradeRecord, ForwardSafeNetEdgeEstimate]],
) -> dict[str, Any]:
    scores = [estimate.opportunity_score for _record, estimate in estimate_pairs if estimate.opportunity_score is not None]
    expected = [estimate.expected_move_bps for _record, estimate in estimate_pairs if estimate.expected_move_bps is not None]
    valid_edges = [
        estimate.estimated_net_edge_bps for _record, estimate in estimate_pairs if estimate.estimated_net_edge_bps is not None
    ]
    missing_components = _missing_component_counts(estimate_pairs)
    by_strategy: dict[str, dict[str, Any]] = {}
    grouped: dict[str, list[tuple[TradeRecord, ForwardSafeNetEdgeEstimate]]] = defaultdict(list)
    for record, estimate in estimate_pairs:
        grouped[str(record.strategy_id or "unknown")].append((record, estimate))
    for strategy_id, pairs in grouped.items():
        strategy_scores = [estimate.opportunity_score for _record, estimate in pairs if estimate.opportunity_score is not None]
        strategy_edges = [
            estimate.estimated_net_edge_bps for _record, estimate in pairs if estimate.estimated_net_edge_bps is not None
        ]
        by_strategy[strategy_id] = {
            "trade_count": len(pairs),
            "score_distribution": _score_distribution_dict(strategy_scores),
            "positive_forward_edge_count": sum(1 for value in strategy_edges if value is not None and value > 0.0),
        }
    return {
        "score_distribution": _score_distribution_dict(scores),
        "expected_move_distribution_bps": _numeric_distribution(expected),
        "estimated_net_edge_distribution_bps": _numeric_distribution(valid_edges),
        "scores_above_60_count": sum(1 for value in scores if value >= NEAR_HIGH_LOWER_BOUND),
        "scores_60_to_69_count": sum(1 for value in scores if NEAR_HIGH_LOWER_BOUND <= value < HIGH_THRESHOLD),
        "scores_high_count": sum(1 for value in scores if value >= HIGH_THRESHOLD),
        "missing_component_counts": missing_components,
        "by_strategy": by_strategy,
    }


def _correlations(
    estimate_pairs: Sequence[tuple[TradeRecord, ForwardSafeNetEdgeEstimate]],
    current_scores: Sequence[float | None],
) -> dict[str, Any]:
    scored_edges: list[tuple[float, float]] = []
    scored_net_pnl: list[tuple[float, float]] = []
    forward_net_pnl: list[tuple[float, float]] = []
    for (record, estimate), score in zip(estimate_pairs, current_scores):
        if score is not None and estimate.estimated_net_edge_bps is not None:
            scored_edges.append((float(score), float(estimate.estimated_net_edge_bps)))
        if score is not None:
            scored_net_pnl.append((float(score), float(record.net_pnl_eur)))
        if estimate.estimated_net_edge_bps is not None:
            forward_net_pnl.append((float(estimate.estimated_net_edge_bps), float(record.net_pnl_eur)))
    return {
        "current_score_vs_forward_safe_net_edge": _correlation_payload(scored_edges),
        "current_score_vs_realized_net_pnl_evaluation_only": _correlation_payload(scored_net_pnl),
        "forward_safe_net_edge_vs_realized_net_pnl_evaluation_only": _correlation_payload(forward_net_pnl),
        "note": "Realized net PnL correlations are evaluation-only and never used to score or select trades.",
    }


def _forward_edge_alignment(
    estimate_pairs: Sequence[tuple[TradeRecord, ForwardSafeNetEdgeEstimate]],
    current_scores: Sequence[float | None],
) -> dict[str, Any]:
    positive_pairs = [
        (record, estimate, score)
        for (record, estimate), score in zip(estimate_pairs, current_scores)
        if estimate.estimated_net_edge_bps is not None and estimate.estimated_net_edge_bps > 0.0
    ]
    positive_by_bucket: Counter[str] = Counter(_bucket(score) for _record, _estimate, score in positive_pairs)
    top_positive = sorted(
        positive_pairs,
        key=lambda item: float(item[1].estimated_net_edge_bps or -1e12),
        reverse=True,
    )[:20]
    top_score_pairs = sorted(
        ((record, estimate, score) for (record, estimate), score in zip(estimate_pairs, current_scores) if score is not None),
        key=lambda item: float(item[2] or -1e12),
        reverse=True,
    )[:20]
    return {
        "positive_forward_edge_count": len(positive_pairs),
        "positive_forward_edge_bucket_counts": dict(sorted(positive_by_bucket.items())),
        "positive_forward_edge_not_high_count": sum(1 for _record, _estimate, score in positive_pairs if _bucket(score) != "high"),
        "top_positive_forward_edge": [_alignment_row(record, estimate, score) for record, estimate, score in top_positive],
        "top_current_scores": [_alignment_row(record, estimate, score) for record, estimate, score in top_score_pairs],
    }


def _high_conviction_analysis(
    estimate_pairs: Sequence[tuple[TradeRecord, ForwardSafeNetEdgeEstimate]],
) -> dict[str, Any]:
    hcs_pairs = [(record, estimate) for record, estimate in estimate_pairs if record.strategy_id == HIGH_CONVICTION_STRATEGY_ID]
    scores = [estimate.opportunity_score for _record, estimate in hcs_pairs]
    positive = [(record, estimate) for record, estimate in hcs_pairs if (estimate.estimated_net_edge_bps or 0.0) > 0.0]
    missing_components = _missing_component_counts(hcs_pairs, high_conviction_only=True)
    variant_scores = {
        name: _scores_for_variant(hcs_pairs, name)
        for name in SCORE_VARIANTS
    }
    return {
        "strategy_id": HIGH_CONVICTION_STRATEGY_ID,
        "trade_count": len(hcs_pairs),
        "positive_forward_edge_count": len(positive),
        "current_distribution": _score_distribution_dict(scores),
        "current_bucket_counts": _distribution(scores).bucket_counts,
        "variant_distributions": {name: _distribution(values).to_dict() for name, values in variant_scores.items()},
        "missing_pretrade_component_counts": missing_components,
        "positive_forward_edge_rows": [
            _alignment_row(record, estimate, estimate.opportunity_score)
            for record, estimate in sorted(
                positive,
                key=lambda item: float(item[1].estimated_net_edge_bps or -1e12),
                reverse=True,
            )
        ],
        "diagnosis": _high_conviction_diagnosis(hcs_pairs, missing_components),
        "promotable": False,
        "paper_capital_allowed": False,
        "live_allowed": False,
    }


def _high_conviction_diagnosis(
    hcs_pairs: Sequence[tuple[TradeRecord, ForwardSafeNetEdgeEstimate]],
    missing_components: Mapping[str, int],
) -> list[str]:
    reasons: list[str] = []
    if not hcs_pairs:
        return ["high_conviction_has_no_eligible_shadow_observations"]
    scores = [estimate.opportunity_score for _record, estimate in hcs_pairs if estimate.opportunity_score is not None]
    if scores and max(scores) < HIGH_THRESHOLD:
        reasons.append("high_conviction_scores_below_existing_high_threshold")
    positive = [estimate for _record, estimate in hcs_pairs if (estimate.estimated_net_edge_bps or 0.0) > 0.0]
    if positive and all((estimate.opportunity_score or 0.0) < HIGH_THRESHOLD for estimate in positive):
        reasons.append("positive_forward_edge_not_recognized_as_high")
    for component, count in sorted(missing_components.items()):
        if count >= max(1, len(hcs_pairs) // 2):
            reasons.append(f"missing_or_underreported_{component}")
    if len(hcs_pairs) < 50:
        reasons.append("sample_size_below_50")
    return reasons or ["no_clear_high_conviction_score_issue_detected"]


def _variant_report(
    estimate_pairs: Sequence[tuple[TradeRecord, ForwardSafeNetEdgeEstimate]],
    name: str,
    initial_capital_eur: float,
) -> ScoreVariantReport:
    scores = _scores_for_variant(estimate_pairs, name)
    return ScoreVariantReport(
        name=name,
        description=_variant_description(name),
        uses_future_data=False,
        promotable=False,
        paper_capital_allowed=False,
        live_allowed=False,
        distribution=_distribution(scores),
        bucket_metrics=_bucket_metrics_for_scores(estimate_pairs, scores, initial_capital_eur),
    )


def _scores_for_variant(
    estimate_pairs: Sequence[tuple[TradeRecord, ForwardSafeNetEdgeEstimate]],
    name: str,
) -> tuple[float | None, ...]:
    scores: list[float | None] = []
    for record, estimate in estimate_pairs:
        scores.append(calculate_score_variant(name, _score_variant_source(record, estimate)))
    return tuple(scores)


def _score_variant_source(record: TradeRecord, estimate: ForwardSafeNetEdgeEstimate) -> dict[str, Any]:
    source = dict(estimate.input_used_for_decision)
    source.update(
        {
            "strategy_id": estimate.strategy_id or record.strategy_id,
            "symbol": estimate.symbol or record.symbol,
            "timeframe": estimate.timeframe or record.metadata.get("timeframe"),
            "score_bucket": estimate.score_bucket,
            "opportunity_score": estimate.opportunity_score,
            "expected_move_bps": estimate.expected_move_bps,
            "estimated_fees_bps": estimate.estimated_fees_bps,
            "estimated_spread_cost_bps": estimate.estimated_spread_cost_bps,
            "estimated_slippage_bps": estimate.estimated_slippage_bps,
            "latency_buffer_bps": estimate.latency_buffer_bps,
            "estimated_total_cost_bps": estimate.estimated_total_cost_bps,
            "estimated_net_edge_bps": estimate.estimated_net_edge_bps,
            "risk_penalties_bps": estimate.risk_penalties_bps,
        }
    )
    for metadata in _pre_entry_metadata_sources(record):
        for component, aliases in HIGH_CONVICTION_COMPONENTS.items():
            for alias in aliases:
                value = _deep_get(metadata, alias)
                if value is not None:
                    source.setdefault(alias, value)
                    source.setdefault(component, value)
    return _sanitize_variant_source(source)


def _sanitize_variant_source(source: Mapping[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in source.items():
        normalized = str(key).lower()
        if normalized in FORBIDDEN_SCORE_VARIANT_KEYS:
            continue
        if isinstance(value, Mapping):
            nested = _sanitize_variant_source(value)
            if nested:
                cleaned[str(key)] = nested
            continue
        if isinstance(value, (list, tuple)):
            cleaned[str(key)] = [
                _sanitize_variant_source(item) if isinstance(item, Mapping) else item
                for item in value
                if not isinstance(item, (list, tuple))
            ]
            continue
        cleaned[str(key)] = value
    return cleaned


def _audit_score_variant_input(source: Mapping[str, Any]) -> None:
    audit_forward_edge_input(source)
    forbidden = _forbidden_score_paths(source)
    if forbidden:
        raise LookaheadInputError(f"score variant input contains post-entry fields: {', '.join(forbidden)}")


def _forbidden_score_paths(source: Any, prefix: str = "") -> tuple[str, ...]:
    paths: list[str] = []
    if isinstance(source, Mapping):
        for key, value in source.items():
            normalized = str(key).lower()
            path = f"{prefix}.{key}" if prefix else str(key)
            if normalized in FORBIDDEN_SCORE_VARIANT_KEYS:
                paths.append(path)
                continue
            paths.extend(_forbidden_score_paths(value, path))
    elif isinstance(source, (list, tuple)):
        for index, value in enumerate(source):
            paths.extend(_forbidden_score_paths(value, f"{prefix}[{index}]"))
    return tuple(paths)


def _recalibrated_v1_score(
    current_score: float | None,
    expected_move_bps: float,
    total_cost_bps: float,
    estimated_net_edge_bps: float,
    risk_penalties_bps: float,
) -> float:
    expected_quality = _clamp(expected_move_bps / 500.0) * 25.0
    net_quality = _clamp(estimated_net_edge_bps / 300.0) * 30.0
    cost_efficiency = _cost_efficiency(expected_move_bps, total_cost_bps) * 20.0
    source_quality = _clamp((current_score or 0.0) / 100.0) * 15.0
    risk_penalty = min(35.0, max(0.0, risk_penalties_bps) / 2.0)
    return _clamp_score(expected_quality + net_quality + cost_efficiency + source_quality + 10.0 - risk_penalty)


def _cost_aware_score(
    current_score: float | None,
    expected_move_bps: float,
    total_cost_bps: float,
    estimated_net_edge_bps: float,
    risk_penalties_bps: float,
) -> float:
    base = float(current_score or 0.0)
    expected = max(expected_move_bps, 1.0)
    cost_ratio = max(0.0, total_cost_bps / expected)
    penalty = 0.0
    if cost_ratio > 0.40:
        penalty += min(35.0, (cost_ratio - 0.40) * 80.0)
    if estimated_net_edge_bps <= 0.0:
        penalty += min(35.0, abs(estimated_net_edge_bps) / 8.0)
    penalty += min(25.0, risk_penalties_bps / 2.0)
    bonus = min(20.0, max(0.0, estimated_net_edge_bps) / 25.0)
    return _clamp_score(base + bonus - penalty)


def _high_conviction_aware_score(
    current_score: float | None,
    expected_move_bps: float,
    total_cost_bps: float,
    estimated_net_edge_bps: float,
    risk_penalties_bps: float,
    *,
    strategy_id: str,
    source: Mapping[str, Any],
) -> float:
    score = _recalibrated_v1_score(current_score, expected_move_bps, total_cost_bps, estimated_net_edge_bps, risk_penalties_bps)
    if strategy_id == HIGH_CONVICTION_STRATEGY_ID and expected_move_bps >= 200.0 and estimated_net_edge_bps > 0.0:
        score += 8.0
    if _cost_efficiency(expected_move_bps, total_cost_bps) >= 0.75:
        score += 4.0
    if _component_available(source, "risk_reward") and estimated_net_edge_bps > total_cost_bps:
        score += 4.0
    if _component_available(source, "trend_context"):
        score += 3.0
    if _component_available(source, "breakout_quality") or _component_available(source, "volatility_expansion"):
        score += 3.0
    return _clamp_score(score)


def _forward_edge_aware_score(
    current_score: float | None,
    expected_move_bps: float,
    total_cost_bps: float,
    estimated_net_edge_bps: float,
    risk_penalties_bps: float,
) -> float:
    expected_quality = _clamp(expected_move_bps / 700.0) * 20.0
    net_quality = _clamp(estimated_net_edge_bps / 500.0) * 40.0
    cost_efficiency = _cost_efficiency(expected_move_bps, total_cost_bps) * 20.0
    source_quality = _clamp((current_score or 0.0) / 100.0) * 10.0
    penalty = min(35.0, risk_penalties_bps / 1.5)
    if estimated_net_edge_bps <= 0.0:
        penalty += 25.0
    return _clamp_score(expected_quality + net_quality + cost_efficiency + source_quality + 10.0 - penalty)


def _variant_description(name: str) -> str:
    return {
        "current_score": "Stored pre-entry opportunity_score and existing high/medium/low thresholds.",
        "recalibrated_v1": "Research-only score that gives explicit weight to expected move, net edge, cost efficiency, and risk penalties.",
        "cost_aware": "Research-only adjustment of current score by estimated cost pressure and forward-safe net edge.",
        "high_conviction_aware": "Research-only variant that allows high-conviction swing context components to contribute when present.",
        "forward_edge_aware": "Research-only score centered on forward_safe_net_edge without realized outcome fields.",
    }[name]


def _distribution(scores: Sequence[float | None]) -> ScoreDistribution:
    values = sorted(float(value) for value in scores if value is not None and math.isfinite(float(value)))
    bucket_counts = {bucket: 0 for bucket in SCORE_BUCKETS}
    for score in scores:
        bucket_counts[_bucket(score)] += 1
    return ScoreDistribution(
        count=len(values),
        min_score=values[0] if values else None,
        max_score=values[-1] if values else None,
        median_score=median(values) if values else None,
        p90_score=_percentile(values, 0.90) if values else None,
        high_count=sum(1 for value in values if value >= HIGH_THRESHOLD),
        near_high_count=sum(1 for value in values if NEAR_HIGH_LOWER_BOUND <= value < HIGH_THRESHOLD),
        bucket_counts=bucket_counts,
    )


def _score_distribution_dict(scores: Sequence[float | None]) -> dict[str, Any]:
    return _distribution(scores).to_dict()


def _numeric_distribution(values: Sequence[float | None]) -> dict[str, Any]:
    parsed = sorted(float(value) for value in values if value is not None and math.isfinite(float(value)))
    return {
        "count": len(parsed),
        "min": parsed[0] if parsed else None,
        "max": parsed[-1] if parsed else None,
        "median": median(parsed) if parsed else None,
        "p90": _percentile(parsed, 0.90) if parsed else None,
    }


def _bucket_metrics_for_scores(
    estimate_pairs: Sequence[tuple[TradeRecord, ForwardSafeNetEdgeEstimate]],
    scores: Sequence[float | None],
    initial_capital_eur: float,
) -> dict[str, BucketMetrics]:
    grouped: dict[str, list[TradeRecord]] = {bucket: [] for bucket in SCORE_BUCKETS}
    for (record, _estimate), score in zip(estimate_pairs, scores):
        grouped[_bucket(score)].append(record)
    return {bucket: _bucket_metrics(tuple(records), initial_capital_eur) for bucket, records in grouped.items()}


def _bucket_metrics(records: Sequence[TradeRecord], initial_capital_eur: float) -> BucketMetrics:
    net_values = [record.net_pnl_eur for record in records]
    gross_values = [record.gross_pnl_eur for record in records]
    count = len(records)
    net_pnl = sum(net_values)
    max_dd_eur, max_dd_pct = _max_drawdown(records, initial_capital_eur)
    return BucketMetrics(
        trade_count=count,
        gross_pnl_eur=sum(gross_values),
        net_pnl_eur=net_pnl,
        fees_eur=sum(record.fees_eur for record in records),
        slippage_eur=sum(record.slippage_eur for record in records),
        gross_profit_factor=_profit_factor(gross_values),
        net_profit_factor=_profit_factor(net_values),
        net_expectancy_eur=(net_pnl / count) if count else None,
        winrate_net_pct=(sum(1 for value in net_values if value > 0.0) / count * 100.0) if count else None,
        max_drawdown_eur=max_dd_eur,
        max_drawdown_pct=max_dd_pct,
    )


def _missing_component_counts(
    estimate_pairs: Sequence[tuple[TradeRecord, ForwardSafeNetEdgeEstimate]],
    *,
    high_conviction_only: bool = False,
) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for record, estimate in estimate_pairs:
        if high_conviction_only and record.strategy_id != HIGH_CONVICTION_STRATEGY_ID:
            continue
        source = _score_variant_source(record, estimate)
        for component in HIGH_CONVICTION_COMPONENTS:
            if not _component_available(source, component):
                counts[component] += 1
        if estimate.expected_move_bps is None:
            counts["expected_move_bps"] += 1
        if estimate.estimated_total_cost_bps is None:
            counts["estimated_total_cost_bps"] += 1
        if estimate.opportunity_score is None:
            counts["opportunity_score"] += 1
    return dict(sorted(counts.items()))


def _component_available(source: Mapping[str, Any], component: str) -> bool:
    for key in HIGH_CONVICTION_COMPONENTS.get(component, (component,)):
        if _deep_get(source, key) is not None:
            return True
    return _deep_get(source, component) is not None


def _deep_get(source: Any, key: str) -> Any:
    if isinstance(source, Mapping):
        if key in source:
            return source[key]
        for value in source.values():
            result = _deep_get(value, key)
            if result is not None:
                return result
    elif isinstance(source, (list, tuple)):
        for item in source:
            result = _deep_get(item, key)
            if result is not None:
                return result
    return None


def _anti_lookahead_audit(
    estimate_pairs: Sequence[tuple[TradeRecord, ForwardSafeNetEdgeEstimate]],
) -> dict[str, Any]:
    forbidden_seen: Counter[str] = Counter()
    checked = 0
    for record, estimate in estimate_pairs:
        source = _score_variant_source(record, estimate)
        _audit_score_variant_input(source)
        checked += 1
        for path in _forbidden_score_paths(record.metadata):
            forbidden_seen[path] += 1
    return {
        "decision_uses_post_trade_data": False,
        "sanitized_inputs_checked": checked,
        "forbidden_fields_used": [],
        "raw_forbidden_fields_seen_but_excluded": dict(sorted(forbidden_seen.items())),
        "note": "Variant scores are calculated from sanitized pre-entry metadata and forward-safe estimates; realized PnL is evaluation-only.",
    }


def _root_causes(
    distribution: ScoreDistribution,
    forward_alignment: Mapping[str, Any],
    high_conviction: Mapping[str, Any],
    diagnostics: Mapping[str, Any],
) -> tuple[str, ...]:
    causes: list[str] = []
    if distribution.max_score is not None and distribution.max_score < HIGH_THRESHOLD:
        causes.append("current_score_compressed_below_high_threshold")
    if distribution.near_high_count == 0:
        causes.append("no_scores_in_60_69_transition_zone")
    if forward_alignment.get("positive_forward_edge_not_high_count", 0):
        causes.append("positive_forward_edge_not_reflected_in_current_bucket")
    hc_diagnosis = high_conviction.get("diagnosis") or []
    causes.extend(str(item) for item in hc_diagnosis if str(item).startswith("missing_or_underreported"))
    missing = diagnostics.get("missing_component_counts") if isinstance(diagnostics, Mapping) else {}
    if isinstance(missing, Mapping):
        if missing.get("risk_reward", 0) or missing.get("trend_context", 0):
            causes.append("high_conviction_specific_features_not_available_to_current_score")
    return tuple(dict.fromkeys(causes)) or ("no_single_score_root_cause_detected",)


def _p13_recommendations(root_causes: Sequence[str], high_conviction: Mapping[str, Any]) -> tuple[str, ...]:
    recommendations: list[str] = [
        "Keep all score variants research-only until at least 50 closed observations per segment.",
        "Do not lower the high threshold; first improve pre-trade components feeding the score.",
    ]
    if "positive_forward_edge_not_reflected_in_current_bucket" in root_causes:
        recommendations.append("Add a forward-edge-aware score component that uses expected move minus estimated costs before entry.")
    if "high_conviction_specific_features_not_available_to_current_score" in root_causes:
        recommendations.append("Feed high_conviction_swing with explicit breakout/trend/risk-reward metadata before scoring.")
    if high_conviction.get("trade_count", 0) < 50:
        recommendations.append("Continue high_conviction_swing shadow collection before any paper-capital discussion.")
    recommendations.append("Run forward-only validation again after the next daily collection cycle.")
    return tuple(dict.fromkeys(recommendations))


def _alignment_row(record: TradeRecord, estimate: ForwardSafeNetEdgeEstimate, score: float | None) -> dict[str, Any]:
    return {
        "strategy_id": record.strategy_id,
        "symbol": record.symbol,
        "timeframe": estimate.timeframe or record.metadata.get("timeframe"),
        "regime": record.regime,
        "opportunity_score": _round(score),
        "score_bucket": _bucket(score),
        "expected_move_bps": _round(estimate.expected_move_bps),
        "estimated_total_cost_bps": _round(estimate.estimated_total_cost_bps),
        "estimated_net_edge_bps": _round(estimate.estimated_net_edge_bps),
        "net_pnl_eur_evaluation_only": _round(record.net_pnl_eur),
        "fees_eur": _round(record.fees_eur),
        "slippage_eur": _round(record.slippage_eur),
        "reject_reason": estimate.reject_reason,
    }


def _correlation_payload(pairs: Sequence[tuple[float, float]]) -> dict[str, Any]:
    return {
        "sample_size": len(pairs),
        "pearson": _pearson(pairs),
    }


def _pearson(pairs: Sequence[tuple[float, float]]) -> float | None:
    if len(pairs) < 2:
        return None
    xs = [item[0] for item in pairs]
    ys = [item[1] for item in pairs]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    denom_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    denom_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if denom_x == 0.0 or denom_y == 0.0:
        return None
    return numerator / (denom_x * denom_y)


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


def _cost_efficiency(expected_move_bps: float, total_cost_bps: float) -> float:
    expected = max(expected_move_bps, 1.0)
    return _clamp(1.0 - max(0.0, total_cost_bps) / expected)


def _bucket(score: float | None) -> str:
    if score is None:
        return "missing"
    if score >= HIGH_THRESHOLD:
        return "high"
    if score >= MEDIUM_THRESHOLD:
        return "medium"
    return "low"


def _percentile(values: Sequence[float], quantile: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    pos = (len(values) - 1) * quantile
    lower = int(math.floor(pos))
    upper = int(math.ceil(pos))
    if lower == upper:
        return values[lower]
    return values[lower] + (values[upper] - values[lower]) * (pos - lower)


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, float(value)))


def _clamp_score(value: float | None) -> float | None:
    if value is None or not math.isfinite(float(value)):
        return None
    return max(0.0, min(100.0, float(value)))


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


def _round(value: float | None, digits: int = 4) -> float | None:
    if value is None or not math.isfinite(float(value)):
        return None
    return round(float(value), digits)


def _fmt(value: float | None) -> str:
    if value is None or not math.isfinite(float(value)):
        return "n/a"
    return f"{float(value):.4f}"


def _markdown(report: OpportunityScoreAuditReport) -> str:
    lines = [
        f"# Opportunity Score Audit - {report.run_id}",
        "",
        f"- Generated: `{report.generated_at}`",
        f"- Cutoff: `{report.cutoff.get('since') or 'all records'}`",
        f"- Eligible trades: `{report.eligible_trade_count}`",
        f"- Legacy excluded: `{report.legacy_excluded_trade_count}`",
        f"- Policy excluded: `{report.policy_excluded_trade_count}`",
        f"- Quality excluded: `{report.quality_excluded_trade_count}`",
        f"- Cost profile: `{report.cost_profile.get('name')}`",
        "",
        "## Runtime Formula",
        "",
    ]
    weights = report.opportunity_formula.get("weights", {})
    for key, value in weights.items():
        lines.append(f"- `{key}`: `{value}` points")
    lines.extend(
        [
            f"- High threshold: `{HIGH_THRESHOLD}`",
            f"- Runtime min_score unchanged: `{report.opportunity_formula.get('min_score_high_threshold')}`",
            "",
            "## Current Distribution",
            "",
        ]
    )
    dist = report.current_distribution
    lines.extend(
        [
            f"- Scored count: `{dist.count}`",
            f"- Max score: `{_fmt(dist.max_score)}`",
            f"- Median score: `{_fmt(dist.median_score)}`",
            f"- P90 score: `{_fmt(dist.p90_score)}`",
            f"- High count: `{dist.high_count}`",
            f"- 60-69 count: `{dist.near_high_count}`",
            f"- Buckets: `{dist.bucket_counts}`",
            "",
            "## Current Bucket Metrics",
            "",
            "| Bucket | Trades | Net PnL | PF gross | PF net | Expectancy | Fees | Slippage | Max DD |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for bucket in SCORE_BUCKETS:
        metrics = report.current_bucket_metrics[bucket]
        lines.append(
            f"| {bucket} | {metrics.trade_count} | {metrics.net_pnl_eur:.2f} | {_fmt(metrics.gross_profit_factor)} | "
            f"{_fmt(metrics.net_profit_factor)} | {_fmt(metrics.net_expectancy_eur)} | {metrics.fees_eur:.2f} | "
            f"{metrics.slippage_eur:.2f} | {metrics.max_drawdown_eur:.2f} |"
        )
    lines.extend(["", "## Score Vs Forward Edge", ""])
    align = report.forward_edge_alignment
    lines.extend(
        [
            f"- Positive forward-edge trades: `{align.get('positive_forward_edge_count', 0)}`",
            f"- Positive forward-edge not high: `{align.get('positive_forward_edge_not_high_count', 0)}`",
            f"- Positive forward-edge buckets: `{align.get('positive_forward_edge_bucket_counts', {})}`",
            "",
            "### Top Positive Forward Edge",
            "",
            "| Strategy | Symbol | Score | Bucket | Expected bps | Cost bps | Forward net bps | Net PnL eval |",
            "|---|---|---:|---|---:|---:|---:|---:|",
        ]
    )
    for row in align.get("top_positive_forward_edge", [])[:12]:
        lines.append(
            f"| {row.get('strategy_id')} | {row.get('symbol')} | {_fmt(row.get('opportunity_score'))} | "
            f"{row.get('score_bucket')} | {_fmt(row.get('expected_move_bps'))} | "
            f"{_fmt(row.get('estimated_total_cost_bps'))} | {_fmt(row.get('estimated_net_edge_bps'))} | "
            f"{_fmt(row.get('net_pnl_eur_evaluation_only'))} |"
        )
    lines.extend(["", "## High Conviction Swing", ""])
    hc = report.high_conviction_analysis
    lines.extend(
        [
            f"- Trades: `{hc.get('trade_count', 0)}`",
            f"- Positive forward edge: `{hc.get('positive_forward_edge_count', 0)}`",
            f"- Current buckets: `{hc.get('current_bucket_counts', {})}`",
            f"- Diagnosis: `{hc.get('diagnosis', [])}`",
            f"- Missing components: `{hc.get('missing_pretrade_component_counts', {})}`",
            "",
            "## Research-Only Score Variants",
            "",
            "| Variant | High | Medium | Low | Missing | Max | Median | High PF net | High trades | Promotable |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for variant in report.score_variants:
        vdist = variant.distribution
        high_metrics = variant.bucket_metrics["high"]
        lines.append(
            f"| {variant.name} | {vdist.bucket_counts.get('high', 0)} | {vdist.bucket_counts.get('medium', 0)} | "
            f"{vdist.bucket_counts.get('low', 0)} | {vdist.bucket_counts.get('missing', 0)} | "
            f"{_fmt(vdist.max_score)} | {_fmt(vdist.median_score)} | {_fmt(high_metrics.net_profit_factor)} | "
            f"{high_metrics.trade_count} | {str(variant.promotable).lower()} |"
        )
    lines.extend(["", "## Correlations", ""])
    for key, value in report.correlations.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Anti-Lookahead Audit", ""])
    for key, value in report.anti_lookahead_audit.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Root Causes", ""])
    lines.extend(f"- `{cause}`" for cause in report.root_causes)
    lines.extend(["", "## P13 Recommendations", ""])
    lines.extend(f"- {item}" for item in report.p13_recommendations)
    lines.extend(["", "## Safety Notes", ""])
    lines.extend(f"- {note}" for note in report.safety_notes)
    if report.warnings:
        lines.extend(["", "## Loader Warnings", ""])
        counts = loader_warning_counts(report.warnings)
        lines.extend(f"- `{key}`: `{value}`" for key, value in sorted(counts.items()))
    return "\n".join(lines) + "\n"

