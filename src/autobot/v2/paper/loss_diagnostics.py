"""Post-P2 loss diagnostics for attributed shadow paper observations.

The diagnostics are read-only and deliberately conservative. They explain where
shadow-paper performance is lost without promoting strategies, changing router
state, or altering live/paper execution behavior.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Mapping, Sequence

from autobot.v2.paper.ledger_quality import critical_warning_counts, has_critical_ledger_warning, loader_warning_counts
from autobot.v2.paper.ledger_loader import load_state_db_paper_ledger
from autobot.v2.research.trade_journal import TradeRecord
from autobot.v2.strategy_runtime_policy import (
    EXECUTION_MODE_SHADOW_PAPER,
    LEGACY_UNATTRIBUTED_STRATEGY_ID,
    shadow_paper_strategy_block_reason,
)


DIAGNOSTIC_STRATEGIES = ("trend_momentum", "mean_reversion")
OBSERVATION_ONLY_STRATEGIES = ("high_conviction_swing", "opportunity_scoring")
DEFAULT_MIN_SEGMENT_TRADES = 30


@dataclass(frozen=True)
class PaperLossDiagnosticsConfig:
    state_db_path: Path
    registry_path: Path = Path("docs/research/strategy_hypotheses.json")
    output_dir: Path = Path("reports/paper/loss_diagnostics")
    run_id: str | None = None
    initial_capital_eur: float = 1_000.0
    min_segment_trades: int = DEFAULT_MIN_SEGMENT_TRADES
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def resolved_run_id(self) -> str:
        if self.run_id:
            return self.run_id
        return f"paper_loss_diagnostics_{self.generated_at.strftime('%Y%m%d_%H%M%S')}"


@dataclass(frozen=True)
class SegmentMetrics:
    key: dict[str, str]
    trade_count: int
    gross_pnl_eur: float
    net_pnl_eur: float
    fees_eur: float
    slippage_eur: float
    total_cost_eur: float
    cost_drag_eur: float
    gross_profit_factor: float | None
    net_profit_factor: float | None
    gross_expectancy_eur: float | None
    net_expectancy_eur: float | None
    winrate_net_pct: float | None
    average_win_eur: float | None
    average_loss_eur: float | None
    average_holding_seconds: float | None
    max_drawdown_eur: float
    max_drawdown_pct: float
    cost_to_abs_gross_ratio: float | None
    dominant_loss_source: str
    recommendation: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["reasons"] = list(self.reasons)
        return data


@dataclass(frozen=True)
class OpportunityScoringDiagnostics:
    score_coverage_trade_count: int
    total_shadow_trade_count: int
    status: str
    bucket_metrics: dict[str, Any] = field(default_factory=dict)
    high_score_metrics: dict[str, Any] = field(default_factory=dict)
    low_score_metrics: dict[str, Any] = field(default_factory=dict)
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["notes"] = list(self.notes)
        return data


@dataclass(frozen=True)
class StrategyLossDiagnostics:
    strategy_id: str
    status: str
    trade_count: int
    summary: SegmentMetrics
    best_segments: tuple[SegmentMetrics, ...]
    worst_segments: tuple[SegmentMetrics, ...]
    gross_profitable_net_unprofitable: tuple[SegmentMetrics, ...]
    disabled_segment_candidates: tuple[SegmentMetrics, ...]
    root_causes: tuple[str, ...]
    policy: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "status": self.status,
            "trade_count": self.trade_count,
            "summary": self.summary.to_dict(),
            "best_segments": [item.to_dict() for item in self.best_segments],
            "worst_segments": [item.to_dict() for item in self.worst_segments],
            "gross_profitable_net_unprofitable": [
                item.to_dict() for item in self.gross_profitable_net_unprofitable
            ],
            "disabled_segment_candidates": [item.to_dict() for item in self.disabled_segment_candidates],
            "root_causes": list(self.root_causes),
            "policy": dict(self.policy),
        }


@dataclass(frozen=True)
class PaperLossDiagnosticsReport:
    run_id: str
    generated_at: str
    state_db_path: str
    registry_path: str
    source: str
    execution_mode: str
    legacy_excluded_trade_count: int
    non_shadow_excluded_trade_count: int
    quality_excluded_trade_count: int
    quality_exclusion_counts: dict[str, int]
    warning_counts: dict[str, int]
    strategy_diagnostics: tuple[StrategyLossDiagnostics, ...]
    high_conviction_diagnostic: dict[str, Any]
    opportunity_scoring_diagnostic: OpportunityScoringDiagnostics
    segment_tables: dict[str, list[dict[str, Any]]]
    safety_notes: tuple[str, ...]
    warnings: tuple[str, ...] = ()
    json_report_path: str | None = None
    markdown_report_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "state_db_path": self.state_db_path,
            "registry_path": self.registry_path,
            "source": self.source,
            "execution_mode": self.execution_mode,
            "legacy_excluded_trade_count": self.legacy_excluded_trade_count,
            "non_shadow_excluded_trade_count": self.non_shadow_excluded_trade_count,
            "quality_excluded_trade_count": self.quality_excluded_trade_count,
            "quality_exclusion_counts": dict(self.quality_exclusion_counts),
            "warning_counts": dict(self.warning_counts),
            "strategy_diagnostics": [item.to_dict() for item in self.strategy_diagnostics],
            "high_conviction_diagnostic": dict(self.high_conviction_diagnostic),
            "opportunity_scoring_diagnostic": self.opportunity_scoring_diagnostic.to_dict(),
            "segment_tables": self.segment_tables,
            "safety_notes": list(self.safety_notes),
            "warnings": list(self.warnings),
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
        }


def build_paper_loss_diagnostics_report(
    config: PaperLossDiagnosticsConfig,
    *,
    write_report: bool = True,
) -> PaperLossDiagnosticsReport:
    if config.initial_capital_eur <= 0.0:
        raise ValueError("initial_capital_eur must be positive")
    if config.min_segment_trades <= 0:
        raise ValueError("min_segment_trades must be positive")

    loaded = load_state_db_paper_ledger(config.state_db_path, include_decisions=True)
    all_records = tuple(loaded.journal.records)
    legacy_excluded = tuple(record for record in all_records if _is_legacy(record))
    shadow_policy_records = tuple(record for record in all_records if _is_shadow_record_policy_candidate(record))
    quality_excluded = tuple(record for record in shadow_policy_records if has_critical_ledger_warning(record))
    shadow_records = tuple(record for record in shadow_policy_records if not has_critical_ledger_warning(record))
    diagnostic_records = tuple(record for record in shadow_records if record.strategy_id in DIAGNOSTIC_STRATEGIES)
    non_shadow_excluded = len(all_records) - len(shadow_policy_records) - len(legacy_excluded)

    segment_tables = _build_segment_tables(
        diagnostic_records,
        initial_capital_eur=config.initial_capital_eur,
        min_segment_trades=config.min_segment_trades,
    )
    by_strategy_summary = {
        item.key["strategy_id"]: item
        for item in _segment_group(
            diagnostic_records,
            ("strategy_id",),
            initial_capital_eur=config.initial_capital_eur,
            min_segment_trades=config.min_segment_trades,
        )
    }
    diagnostics: list[StrategyLossDiagnostics] = []
    for strategy_id in DIAGNOSTIC_STRATEGIES:
        records = tuple(record for record in diagnostic_records if record.strategy_id == strategy_id)
        summary = by_strategy_summary.get(
            strategy_id,
            _metrics_for_segment(
                (),
                {"strategy_id": strategy_id},
                initial_capital_eur=config.initial_capital_eur,
                min_segment_trades=config.min_segment_trades,
            ),
        )
        segments = [
            item
            for item in _segment_group(
                records,
                ("strategy_id", "symbol", "timeframe", "regime"),
                initial_capital_eur=config.initial_capital_eur,
                min_segment_trades=config.min_segment_trades,
            )
        ]
        diagnostics.append(
            StrategyLossDiagnostics(
                strategy_id=strategy_id,
                status="shadow_only",
                trade_count=len(records),
                summary=summary,
                best_segments=_top_segments(segments, reverse=True),
                worst_segments=_top_segments(segments, reverse=False),
                gross_profitable_net_unprofitable=tuple(
                    item
                    for item in segments
                    if _gt(item.gross_profit_factor, 1.0) and not _gt(item.net_profit_factor, 1.0)
                )[:10],
                disabled_segment_candidates=tuple(
                    item for item in segments if item.recommendation == "disabled_segment_recommended"
                )[:10],
                root_causes=_root_causes(summary, segments),
                policy={
                    "paper_capital_allowed": False,
                    "live_allowed": False,
                    "reason": "shadow_only_until_net_pf_above_1_and_promotion_gates_pass",
                    "segment_policy": "disabled_segment_recommended blocks paper_capital routing for that segment",
                },
            )
        )

    high_conviction = _high_conviction_diagnostic(shadow_records)
    opportunity = _opportunity_scoring_diagnostic(shadow_records, config.initial_capital_eur)
    report = PaperLossDiagnosticsReport(
        run_id=config.resolved_run_id,
        generated_at=config.generated_at.isoformat(),
        state_db_path=str(config.state_db_path),
        registry_path=str(config.registry_path),
        source="post_p2_shadow_paper_trade_ledger",
        execution_mode=EXECUTION_MODE_SHADOW_PAPER,
        legacy_excluded_trade_count=len(legacy_excluded),
        non_shadow_excluded_trade_count=max(0, non_shadow_excluded),
        quality_excluded_trade_count=len(quality_excluded),
        quality_exclusion_counts=critical_warning_counts(quality_excluded),
        warning_counts={
            **loader_warning_counts(loaded.warnings),
            **{f"critical_{key}": value for key, value in critical_warning_counts(shadow_policy_records).items()},
        },
        strategy_diagnostics=tuple(diagnostics),
        high_conviction_diagnostic=high_conviction,
        opportunity_scoring_diagnostic=opportunity,
        segment_tables=segment_tables,
        safety_notes=(
            "Read-only diagnostics.",
            "Only attributed shadow_paper observations are analyzed.",
            "Legacy/unattributed trades are excluded.",
            "No strategy is promoted.",
            "No paper_capital or live order is created.",
            "Grid remains blocked.",
        ),
        warnings=tuple(loaded.warnings),
    )
    if write_report:
        return write_paper_loss_diagnostics_report(report, config.output_dir)
    return report


def segment_paper_capital_block_reason(segment: SegmentMetrics | Mapping[str, Any]) -> str | None:
    """Return why a segment must not route to official paper capital."""

    recommendation = (
        segment.recommendation
        if isinstance(segment, SegmentMetrics)
        else str(segment.get("recommendation") or "")
    )
    if recommendation == "disabled_segment_recommended":
        return "disabled_segment"
    net_pf = (
        segment.net_profit_factor
        if isinstance(segment, SegmentMetrics)
        else _optional_float(segment.get("net_profit_factor"))
    )
    if net_pf is None or net_pf <= 1.0:
        return "net_profit_factor_not_above_1"
    return None


def write_paper_loss_diagnostics_report(
    report: PaperLossDiagnosticsReport,
    output_dir: str | Path,
) -> PaperLossDiagnosticsReport:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    base = output / report.run_id
    json_path = base.with_suffix(".json")
    md_path = base.with_suffix(".md")
    report_with_paths = replace(report, json_report_path=str(json_path), markdown_report_path=str(md_path))
    json_path.write_text(json.dumps(report_with_paths.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_markdown(report_with_paths), encoding="utf-8")
    return report_with_paths


def _is_shadow_record(record: TradeRecord) -> bool:
    return _is_shadow_record_policy_candidate(record) and not has_critical_ledger_warning(record)


def _is_shadow_record_policy_candidate(record: TradeRecord) -> bool:
    if record.strategy_id in ("", LEGACY_UNATTRIBUTED_STRATEGY_ID):
        return False
    if _execution_mode(record) != EXECUTION_MODE_SHADOW_PAPER:
        return False
    return shadow_paper_strategy_block_reason(record.strategy_id) is None


def _is_legacy(record: TradeRecord) -> bool:
    return record.strategy_id in ("", LEGACY_UNATTRIBUTED_STRATEGY_ID)


def _execution_mode(record: TradeRecord) -> str:
    value = record.metadata.get("execution_mode")
    if value not in (None, ""):
        return str(value)
    for source_name in ("closing_leg", "opening_leg"):
        source = record.metadata.get(source_name)
        if isinstance(source, Mapping) and source.get("execution_mode") not in (None, ""):
            return str(source.get("execution_mode"))
    return ""


def _build_segment_tables(
    records: Sequence[TradeRecord],
    *,
    initial_capital_eur: float,
    min_segment_trades: int,
) -> dict[str, list[dict[str, Any]]]:
    tables: dict[str, list[dict[str, Any]]] = {}
    definitions = {
        "by_strategy": ("strategy_id",),
        "by_strategy_symbol": ("strategy_id", "symbol"),
        "by_strategy_timeframe": ("strategy_id", "timeframe"),
        "by_strategy_regime": ("strategy_id", "regime"),
        "by_strategy_symbol_timeframe_regime": ("strategy_id", "symbol", "timeframe", "regime"),
    }
    for name, fields in definitions.items():
        tables[name] = [
            item.to_dict()
            for item in _segment_group(
                records,
                fields,
                initial_capital_eur=initial_capital_eur,
                min_segment_trades=min_segment_trades,
            )
        ]
    return tables


def _segment_group(
    records: Sequence[TradeRecord],
    fields: Sequence[str],
    *,
    initial_capital_eur: float,
    min_segment_trades: int,
) -> tuple[SegmentMetrics, ...]:
    groups: dict[tuple[tuple[str, str], ...], list[TradeRecord]] = defaultdict(list)
    for record in records:
        key = _segment_key(record, fields)
        groups[tuple(sorted(key.items()))].append(record)
    segments = [
        _metrics_for_segment(
            tuple(group_records),
            dict(key),
            initial_capital_eur=initial_capital_eur,
            min_segment_trades=min_segment_trades,
        )
        for key, group_records in groups.items()
    ]
    return tuple(
        sorted(
            segments,
            key=lambda item: (item.net_pnl_eur, item.net_profit_factor or -1.0, item.trade_count),
            reverse=True,
        )
    )


def _segment_key(record: TradeRecord, fields: Sequence[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for field in fields:
        if field == "strategy_id":
            value = record.strategy_id
        elif field == "symbol":
            value = record.symbol
        elif field == "timeframe":
            value = _metadata_value(record, "timeframe") or "unknown"
        elif field == "regime":
            value = record.regime or _metadata_value(record, "regime") or "unknown"
        elif field == "signal_source":
            value = _metadata_value(record, "signal_source") or "unknown"
        else:
            value = "unknown"
        result[field] = str(value or "unknown")
    return result


def _metrics_for_segment(
    records: Sequence[TradeRecord],
    key: Mapping[str, str],
    *,
    initial_capital_eur: float,
    min_segment_trades: int,
) -> SegmentMetrics:
    records = tuple(records)
    gross_values = [record.gross_pnl_eur for record in records]
    net_values = [record.net_pnl_eur for record in records]
    fees = sum(record.fees_eur for record in records)
    slippage = sum(record.slippage_eur for record in records)
    gross_pnl = sum(gross_values)
    net_pnl = sum(net_values)
    total_cost = fees + slippage + sum(record.spread_cost_eur + record.latency_cost_eur for record in records)
    cost_drag = gross_pnl - net_pnl
    wins = [value for value in net_values if value > 0.0]
    losses = [value for value in net_values if value < 0.0]
    max_dd_eur, max_dd_pct = _max_drawdown(records, initial_capital_eur)
    count = len(records)
    gross_pf = _profit_factor(gross_values)
    net_pf = _profit_factor(net_values)
    reasons = _segment_reasons(
        records,
        gross_pf=gross_pf,
        net_pf=net_pf,
        gross_pnl=gross_pnl,
        net_pnl=net_pnl,
        total_cost=total_cost,
        cost_drag=cost_drag,
        min_segment_trades=min_segment_trades,
    )
    recommendation = _recommendation(reasons)
    return SegmentMetrics(
        key=dict(key),
        trade_count=count,
        gross_pnl_eur=gross_pnl,
        net_pnl_eur=net_pnl,
        fees_eur=fees,
        slippage_eur=slippage,
        total_cost_eur=total_cost,
        cost_drag_eur=cost_drag,
        gross_profit_factor=gross_pf,
        net_profit_factor=net_pf,
        gross_expectancy_eur=(gross_pnl / count) if count else None,
        net_expectancy_eur=(net_pnl / count) if count else None,
        winrate_net_pct=(len(wins) / count * 100.0) if count else None,
        average_win_eur=mean(wins) if wins else None,
        average_loss_eur=mean(losses) if losses else None,
        average_holding_seconds=mean([record.duration_seconds for record in records]) if records else None,
        max_drawdown_eur=max_dd_eur,
        max_drawdown_pct=max_dd_pct,
        cost_to_abs_gross_ratio=(total_cost / abs(gross_pnl)) if gross_pnl else None,
        dominant_loss_source=_dominant_loss_source(
            gross_pnl=gross_pnl,
            net_pnl=net_pnl,
            fees=fees,
            slippage=slippage,
            cost_drag=cost_drag,
        ),
        recommendation=recommendation,
        reasons=reasons,
    )


def _segment_reasons(
    records: Sequence[TradeRecord],
    *,
    gross_pf: float | None,
    net_pf: float | None,
    gross_pnl: float,
    net_pnl: float,
    total_cost: float,
    cost_drag: float,
    min_segment_trades: int,
) -> tuple[str, ...]:
    reasons: list[str] = []
    count = len(records)
    if count < min_segment_trades:
        reasons.append("too_few_trades")
    if not _gt(gross_pf, 1.0):
        reasons.append("gross_signal_unprofitable")
    if _gt(gross_pf, 1.0) and not _gt(net_pf, 1.0):
        reasons.append("gross_edge_eroded_by_costs")
    if net_pnl < 0.0:
        reasons.append("negative_net_pnl")
    if gross_pnl > 0.0 and net_pnl < 0.0:
        reasons.append("costs_flip_positive_gross_to_negative_net")
    if total_cost > abs(gross_pnl) and gross_pnl != 0.0:
        reasons.append("costs_exceed_absolute_gross_pnl")
    if cost_drag > 0.0 and total_cost > 0.0 and cost_drag / total_cost > 1.25:
        reasons.append("unexplained_cost_drag")
    if _frequency_per_day(records) > 80.0:
        reasons.append("high_trade_frequency")
    return tuple(dict.fromkeys(reasons))


def _recommendation(reasons: Sequence[str]) -> str:
    reason_set = set(reasons)
    if "too_few_trades" in reason_set:
        return "continue_observation"
    if {
        "gross_signal_unprofitable",
        "negative_net_pnl",
    }.issubset(reason_set):
        return "disabled_segment_recommended"
    if "costs_flip_positive_gross_to_negative_net" in reason_set:
        return "cost_review_required"
    if "gross_edge_eroded_by_costs" in reason_set:
        return "cost_aware_review_required"
    return "continue_observation"


def _dominant_loss_source(
    *,
    gross_pnl: float,
    net_pnl: float,
    fees: float,
    slippage: float,
    cost_drag: float,
) -> str:
    if gross_pnl < 0.0:
        return "signal_brut_negative"
    if gross_pnl > 0.0 and net_pnl < 0.0:
        if fees >= slippage and fees >= max(0.0, cost_drag - fees - slippage):
            return "fees_erode_edge"
        if slippage > fees:
            return "slippage_erodes_edge"
        return "costs_erode_edge"
    if net_pnl < 0.0:
        return "net_negative_mixed"
    return "not_loss_segment"


def _root_causes(summary: SegmentMetrics, segments: Sequence[SegmentMetrics]) -> tuple[str, ...]:
    causes: list[str] = []
    if summary.dominant_loss_source != "not_loss_segment":
        causes.append(summary.dominant_loss_source)
    if not _gt(summary.gross_profit_factor, 1.0):
        causes.append("mauvais_signaux_bruts")
    if _gt(summary.gross_profit_factor, 1.0) and not _gt(summary.net_profit_factor, 1.0):
        causes.append("edge_brut_mange_par_couts")
    if summary.reasons and "high_trade_frequency" in summary.reasons:
        causes.append("frequence_trop_elevee")
    disabled = [item for item in segments if item.recommendation == "disabled_segment_recommended"]
    if disabled:
        causes.append("certaines_paires_regimes_detruisent_le_resultat")
    if summary.slippage_eur > summary.fees_eur * 1.5:
        causes.append("slippage_dominant")
    elif summary.fees_eur > summary.slippage_eur * 1.5:
        causes.append("fees_dominants")
    return tuple(dict.fromkeys(causes)) or ("non_conclusive",)


def _high_conviction_diagnostic(shadow_records: Sequence[TradeRecord]) -> dict[str, Any]:
    count = sum(1 for record in shadow_records if record.strategy_id == "high_conviction_swing")
    if count:
        return {
            "strategy_id": "high_conviction_swing",
            "status": "shadow_observations_present",
            "trade_count": count,
            "missing": [],
        }
    return {
        "strategy_id": "high_conviction_swing",
        "status": "no_closed_shadow_source",
        "trade_count": 0,
        "missing": [
            "closed setup journal for high-conviction entries/exits",
            "entry/exit prices with fees and slippage",
            "position lifecycle events linked to strategy_id",
        ],
        "recommendation": "wire a closed research/shadow journal before drawing performance conclusions",
    }


def _opportunity_scoring_diagnostic(
    shadow_records: Sequence[TradeRecord],
    initial_capital_eur: float,
) -> OpportunityScoringDiagnostics:
    scored = tuple(record for record in shadow_records if _opportunity_score(record) is not None)
    bucketed = _records_by_score_bucket(shadow_records)
    if not scored:
        return OpportunityScoringDiagnostics(
            score_coverage_trade_count=0,
            total_shadow_trade_count=len(shadow_records),
            status="score_not_available_on_shadow_trades",
            bucket_metrics={
                bucket: _metrics_for_segment(
                    records,
                    {"score_bucket": bucket},
                    initial_capital_eur=initial_capital_eur,
                    min_segment_trades=1,
                ).to_dict()
                for bucket, records in bucketed.items()
                if records
            },
            notes=(
                "opportunity_scoring is a filter/scoring layer, not an alpha strategy",
                "no score fields were found in shadow_paper trade metadata",
            ),
        )
    metrics_by_bucket = {
        bucket: _metrics_for_segment(
            records,
            {"score_bucket": bucket},
            initial_capital_eur=initial_capital_eur,
            min_segment_trades=1,
        ).to_dict()
        for bucket, records in bucketed.items()
        if records
    }
    return OpportunityScoringDiagnostics(
        score_coverage_trade_count=len(scored),
        total_shadow_trade_count=len(shadow_records),
        status="score_filter_analysis_available",
        bucket_metrics=metrics_by_bucket,
        high_score_metrics=metrics_by_bucket.get("high", {}),
        low_score_metrics=metrics_by_bucket.get("low", {}),
        notes=("Compare score buckets as a filter only; do not treat opportunity_scoring as executable alpha.",),
    )


def _records_by_score_bucket(records: Sequence[TradeRecord]) -> dict[str, tuple[TradeRecord, ...]]:
    grouped: dict[str, list[TradeRecord]] = {bucket: [] for bucket in ("high", "medium", "low", "missing")}
    for record in records:
        grouped[_opportunity_score_bucket(record)].append(record)
    return {key: tuple(value) for key, value in grouped.items()}


def _opportunity_score_bucket(record: TradeRecord) -> str:
    bucket = record.metadata.get("score_bucket")
    if bucket in {"high", "medium", "low", "missing"}:
        return str(bucket)
    score = _opportunity_score(record)
    if score is None:
        return "missing"
    if score >= 70.0:
        return "high"
    if score >= 40.0:
        return "medium"
    return "low"


def _opportunity_score(record: TradeRecord) -> float | None:
    for key in ("opportunity_score", "score", "final_score", "base_score"):
        parsed = _optional_float(record.metadata.get(key))
        if parsed is not None:
            return parsed
    for source_name in ("closing_decision", "opening_decision", "closing_leg", "opening_leg", "position"):
        source = record.metadata.get(source_name)
        parsed = _score_from_mapping(source)
        if parsed is not None:
            return parsed
    ledger_metadata = record.metadata.get("ledger_metadata")
    parsed = _score_from_mapping(ledger_metadata)
    if parsed is not None:
        return parsed
    return None


def _score_from_mapping(source: Any) -> float | None:
    if not isinstance(source, Mapping):
        return None
    for key in ("opportunity_score", "score", "final_score", "base_score"):
        parsed = _optional_float(source.get(key))
        if parsed is not None:
            return parsed
    for value in source.values():
        if isinstance(value, Mapping):
            parsed = _score_from_mapping(value)
            if parsed is not None:
                return parsed
    return None


def _metadata_value(record: TradeRecord, key: str) -> str | None:
    for source_name in ("closing_leg", "opening_leg", "position", "closing_decision", "opening_decision"):
        source = record.metadata.get(source_name)
        if isinstance(source, Mapping):
            value = source.get(key)
            if value not in (None, ""):
                return str(value)
    return None


def _top_segments(segments: Sequence[SegmentMetrics], *, reverse: bool) -> tuple[SegmentMetrics, ...]:
    return tuple(
        sorted(
            segments,
            key=lambda item: (
                item.net_pnl_eur,
                item.net_profit_factor if item.net_profit_factor is not None else -1.0,
                item.trade_count,
            ),
            reverse=reverse,
        )[:10]
    )


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
            max_drawdown_pct = max(max_drawdown_pct, (drawdown / peak) * 100.0)
    return max_drawdown, max_drawdown_pct


def _frequency_per_day(records: Sequence[TradeRecord]) -> float:
    if len(records) < 2:
        return 0.0
    ordered = sorted(records, key=lambda item: item.closed_at)
    seconds = max(1.0, (ordered[-1].closed_at - ordered[0].closed_at).total_seconds())
    return len(records) / (seconds / 86_400.0)


def _gt(value: float | None, threshold: float) -> bool:
    return value is not None and math.isfinite(value) and value > threshold


def _optional_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _markdown(report: PaperLossDiagnosticsReport) -> str:
    lines = [
        f"# Paper Loss Diagnostics - {report.run_id}",
        "",
        f"- Generated: `{report.generated_at}`",
        f"- Source: `{report.source}`",
        f"- Execution mode analyzed: `{report.execution_mode}`",
        f"- Legacy excluded trades: `{report.legacy_excluded_trade_count}`",
        f"- Non-shadow excluded trades: `{report.non_shadow_excluded_trade_count}`",
        f"- Quality excluded trades: `{report.quality_excluded_trade_count}`",
        "",
        "## Strategy Summary",
        "",
        "| Strategy | Trades | Gross PnL | Net PnL | PF gross | PF net | Costs | Dominant loss | Recommendation |",
        "|---|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for diag in report.strategy_diagnostics:
        summary = diag.summary
        lines.append(
            "| {strategy} | {trades} | {gross:.2f} | {net:.2f} | {gpf} | {npf} | {cost:.2f} | {source} | {rec} |".format(
                strategy=diag.strategy_id,
                trades=summary.trade_count,
                gross=summary.gross_pnl_eur,
                net=summary.net_pnl_eur,
                gpf=_fmt(summary.gross_profit_factor),
                npf=_fmt(summary.net_profit_factor),
                cost=summary.total_cost_eur,
                source=summary.dominant_loss_source,
                rec=summary.recommendation,
            )
        )
    lines.extend(["", "## Root Causes", ""])
    for diag in report.strategy_diagnostics:
        lines.append(f"- `{diag.strategy_id}`: {', '.join(diag.root_causes)}")
    lines.extend(["", "## Worst Segments", ""])
    for diag in report.strategy_diagnostics:
        lines.append(f"### {diag.strategy_id}")
        lines.append("| Segment | Trades | Net PnL | PF net | Dominant loss | Recommendation |")
        lines.append("|---|---:|---:|---:|---|---|")
        for segment in diag.worst_segments[:5]:
            lines.append(
                "| {segment} | {trades} | {net:.2f} | {pf} | {loss} | {rec} |".format(
                    segment=", ".join(f"{k}={v}" for k, v in segment.key.items()),
                    trades=segment.trade_count,
                    net=segment.net_pnl_eur,
                    pf=_fmt(segment.net_profit_factor),
                    loss=segment.dominant_loss_source,
                    rec=segment.recommendation,
                )
            )
    lines.extend(
        [
            "",
            "## High Conviction",
            "",
            f"- Status: `{report.high_conviction_diagnostic.get('status')}`",
            f"- Recommendation: `{report.high_conviction_diagnostic.get('recommendation', 'n/a')}`",
            "",
            "## Opportunity Scoring",
            "",
            f"- Status: `{report.opportunity_scoring_diagnostic.status}`",
            f"- Score coverage: `{report.opportunity_scoring_diagnostic.score_coverage_trade_count}/{report.opportunity_scoring_diagnostic.total_shadow_trade_count}`",
            "",
            "| Score bucket | Trades | Net PnL | PF gross | PF net | Expectancy net | Max DD |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for bucket in ("high", "medium", "low", "missing"):
        metrics = report.opportunity_scoring_diagnostic.bucket_metrics.get(bucket)
        if not metrics:
            continue
        lines.append(
            "| {bucket} | {trades} | {net:.2f} | {gpf} | {npf} | {exp} | {dd:.2f} |".format(
                bucket=bucket,
                trades=metrics["trade_count"],
                net=metrics["net_pnl_eur"],
                gpf=_fmt(metrics["gross_profit_factor"]),
                npf=_fmt(metrics["net_profit_factor"]),
                exp=_fmt(metrics["net_expectancy_eur"]),
                dd=metrics["max_drawdown_eur"],
            )
        )
    lines.extend(["", "## Ledger Warnings", ""])
    if report.warning_counts:
        lines.extend(f"- `{key}`: `{value}`" for key, value in sorted(report.warning_counts.items()))
    else:
        lines.append("- none")
    lines.extend(["", "## Quality Exclusions", ""])
    if report.quality_exclusion_counts:
        lines.extend(f"- `{key}`: `{value}`" for key, value in sorted(report.quality_exclusion_counts.items()))
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Safety",
            "",
        ]
    )
    lines.extend(f"- {note}" for note in report.safety_notes)
    return "\n".join(lines) + "\n"


def _fmt(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.4f}"
