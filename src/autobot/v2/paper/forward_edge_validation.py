"""Forward-only validation for P10 forward edge filters.

This module is research-only and read-only. It validates the P10
``forward_safe_net_edge`` filter on observations opened after a supplied cutoff
commit/date, so old shadow results cannot be used as forward evidence.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from autobot.v2.cost_profiles import DEFAULT_PAPER_COST_PROFILE, get_cost_profile
from autobot.v2.paper.forward_edge_simulation import (
    SCORE_BUCKETS,
    ForwardEdgeScenario,
    ForwardEdgeSegmentPolicy,
    _build_scenarios,
    _build_segment_policy,
    _bucket_counts,
    _estimate_counts,
    _estimate_records,
    _is_legacy,
    _is_policy_candidate,
    _scenario,
)
from autobot.v2.paper.ledger_quality import (
    critical_warning_counts,
    has_critical_ledger_warning,
    loader_warning_counts,
)
from autobot.v2.paper.ledger_loader import load_state_db_paper_ledger
from autobot.v2.research.trade_journal import TradeRecord


P10_COMMIT_CUTOFFS: dict[str, str] = {
    "780354683e1bc4077fe35387686fa3bfb3ab3a05": "2026-07-04T07:56:35+02:00",
    "85199ba235062d3cdc273d015ec67a573ad7d82e": "2026-07-04T08:06:17+02:00",
}


@dataclass(frozen=True)
class ForwardEdgeValidationConfig:
    state_db_path: Path
    since: str | None = None
    since_commit: str | None = None
    output_dir: Path = Path("reports/paper/forward_edge_validation")
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
        return f"forward_edge_validation_{self.generated_at.strftime('%Y%m%d_%H%M%S')}"


@dataclass(frozen=True)
class CohortSummary:
    name: str
    cutoff_relation: str
    total_trade_count: int
    eligible_trade_count: int
    legacy_excluded_trade_count: int
    policy_excluded_trade_count: int
    quality_excluded_trade_count: int
    bucket_counts: dict[str, int]
    estimate_counts: dict[str, int]
    pretrade_coverage: dict[str, Any]
    first_opened_at: str | None
    last_opened_at: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ForwardEdgeValidationReport:
    run_id: str
    generated_at: str
    state_db_path: str
    cutoff: dict[str, Any]
    cost_profile: dict[str, Any]
    pre_p10: CohortSummary
    post_p10: CohortSummary
    scenarios: tuple[ForwardEdgeScenario, ...]
    segment_policy: tuple[ForwardEdgeSegmentPolicy, ...]
    coverage_delta: dict[str, Any]
    forward_only_result: dict[str, Any]
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
            "pre_p10": self.pre_p10.to_dict(),
            "post_p10": self.post_p10.to_dict(),
            "scenarios": [item.to_dict() for item in self.scenarios],
            "segment_policy": [item.to_dict() for item in self.segment_policy],
            "coverage_delta": dict(self.coverage_delta),
            "forward_only_result": dict(self.forward_only_result),
            "safety_notes": list(self.safety_notes),
            "warnings": list(self.warnings),
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
        }


def build_forward_edge_validation_report(config: ForwardEdgeValidationConfig) -> ForwardEdgeValidationReport:
    if config.initial_capital_eur <= 0.0:
        raise ValueError("initial_capital_eur must be positive")
    if not (0.0 < config.top_quantile_fraction <= 1.0):
        raise ValueError("top_quantile_fraction must be in (0, 1]")

    cutoff = resolve_cutoff(config.since, config.since_commit)
    cost_profile = get_cost_profile(config.cost_profile_name)
    loaded = load_state_db_paper_ledger(config.state_db_path, include_decisions=True)
    all_records = tuple(loaded.journal.records)
    pre_records = tuple(record for record in all_records if record.opened_at < cutoff)
    post_records = tuple(record for record in all_records if record.opened_at >= cutoff)
    pre_summary, _pre_pairs = _cohort_summary("pre_p10", "opened_before_cutoff", pre_records, cost_profile)
    post_summary, post_pairs = _cohort_summary("post_p10", "opened_at_or_after_cutoff", post_records, cost_profile)
    scenarios = _p11_scenarios(post_pairs, config.initial_capital_eur, config.top_quantile_fraction)
    segment_policy = _build_segment_policy(post_pairs, config.initial_capital_eur)
    report = ForwardEdgeValidationReport(
        run_id=config.resolved_run_id,
        generated_at=config.generated_at.isoformat(),
        state_db_path=str(config.state_db_path),
        cutoff={
            "since": cutoff.isoformat(),
            "since_commit": config.since_commit,
            "known_commit_cutoff": _known_commit_cutoff(config.since_commit),
            "criterion": "record.opened_at >= cutoff",
        },
        cost_profile=cost_profile.to_dict(),
        pre_p10=pre_summary,
        post_p10=post_summary,
        scenarios=scenarios,
        segment_policy=segment_policy,
        coverage_delta=_coverage_delta(pre_summary.pretrade_coverage, post_summary.pretrade_coverage),
        forward_only_result=_forward_only_result(scenarios, post_summary),
        safety_notes=(
            "Read-only validation over closed attributed shadow observations.",
            "The forward cohort uses only records opened at or after the P10 cutoff.",
            "Forward-safe selection uses sanitized pre-entry metadata only.",
            "Realized PnL is used only after group selection for evaluation.",
            "All groups and segment policies are non-promotable.",
            "No paper capital, live order, strategy promotion, sizing change, or UI change is made.",
            "Grid/legacy/unattributed rows are excluded from executable conclusions.",
        ),
        warnings=tuple(loaded.warnings),
    )
    if not config.write_report:
        return report
    return write_forward_edge_validation_report(report, config.output_dir)


def resolve_cutoff(since: str | None, since_commit: str | None) -> datetime:
    if since:
        return _parse_datetime(since)
    if since_commit:
        known = _known_commit_cutoff(since_commit)
        if not known:
            known_values = ", ".join(sorted(P10_COMMIT_CUTOFFS))
            raise ValueError(
                "unknown since_commit; pass --since ISO8601 or one of the known P10 commits: "
                f"{known_values}"
            )
        return _parse_datetime(known)
    raise ValueError("forward-edge-validation requires --since or --since-commit")


def write_forward_edge_validation_report(
    report: ForwardEdgeValidationReport,
    output_dir: str | Path,
) -> ForwardEdgeValidationReport:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    base = output / report.run_id
    json_path = base.with_suffix(".json")
    markdown_path = base.with_suffix(".md")
    report_with_paths = replace(report, json_report_path=str(json_path), markdown_report_path=str(markdown_path))
    json_path.write_text(json.dumps(report_with_paths.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(_markdown(report_with_paths), encoding="utf-8")
    return report_with_paths


def _cohort_summary(
    name: str,
    cutoff_relation: str,
    records: Sequence[TradeRecord],
    cost_profile: Any,
) -> tuple[CohortSummary, tuple[tuple[TradeRecord, Any], ...]]:
    policy_candidates = tuple(record for record in records if _is_policy_candidate(record))
    quality_excluded = tuple(record for record in policy_candidates if has_critical_ledger_warning(record))
    eligible = tuple(record for record in policy_candidates if not has_critical_ledger_warning(record))
    legacy = tuple(record for record in records if _is_legacy(record))
    policy_excluded = tuple(
        record for record in records if not _is_legacy(record) and not _is_policy_candidate(record)
    )
    estimate_pairs = _estimate_records(eligible, cost_profile)
    return (
        CohortSummary(
            name=name,
            cutoff_relation=cutoff_relation,
            total_trade_count=len(records),
            eligible_trade_count=len(eligible),
            legacy_excluded_trade_count=len(legacy),
            policy_excluded_trade_count=len(policy_excluded),
            quality_excluded_trade_count=len(quality_excluded),
            bucket_counts=_bucket_counts(eligible),
            estimate_counts=_estimate_counts(estimate_pairs),
            pretrade_coverage=_pretrade_coverage(eligible, estimate_pairs),
            first_opened_at=min((record.opened_at for record in records), default=None).isoformat()
            if records
            else None,
            last_opened_at=max((record.opened_at for record in records), default=None).isoformat()
            if records
            else None,
        ),
        estimate_pairs,
    )


def _p11_scenarios(
    estimate_pairs: Sequence[tuple[TradeRecord, Any]],
    initial_capital_eur: float,
    top_quantile_fraction: float,
) -> tuple[ForwardEdgeScenario, ...]:
    base = list(_build_scenarios(estimate_pairs, initial_capital_eur, top_quantile_fraction))
    rejected_or_insufficient = tuple(
        pair
        for pair in estimate_pairs
        if pair[1].reject_reason
        or pair[1].confidence_level == "insufficient_data"
        or pair[1].estimated_net_edge_bps is None
    )
    segment_policy = _build_segment_policy(estimate_pairs, initial_capital_eur)
    blocked_keys = {
        (
            str(item.key.get("score_bucket") or ""),
            str(item.key.get("strategy_id") or ""),
            str(item.key.get("symbol") or ""),
        )
        for item in segment_policy
        if item.policy == "block_shadow_future"
    }
    block_shadow_pairs = tuple(
        pair
        for pair in estimate_pairs
        if (
            str(pair[1].score_bucket or ""),
            str(pair[0].strategy_id or ""),
            str(pair[0].symbol or ""),
        )
        in blocked_keys
    )
    base.extend(
        [
            _scenario(
                "rejected_or_insufficient_data",
                "Post-P10 observations with missing pre-entry data or rejected forward estimates.",
                rejected_or_insufficient,
                initial_capital_eur,
            ),
            _scenario(
                "block_shadow_future",
                "Post-P10 observations whose segment policy is block_shadow_future.",
                block_shadow_pairs,
                initial_capital_eur,
            ),
        ]
    )
    return tuple(base)


def _pretrade_coverage(
    records: Sequence[TradeRecord],
    estimate_pairs: Sequence[tuple[TradeRecord, Any]],
) -> dict[str, Any]:
    score_available = 0
    expected_move_available = 0
    estimated_cost_available = 0
    spread_available = 0
    slippage_available = 0
    fees_available = 0
    timeframe_available = 0
    regime_available = 0
    for record, estimate in estimate_pairs:
        if estimate.opportunity_score is not None:
            score_available += 1
        if estimate.expected_move_bps is not None:
            expected_move_available += 1
        if estimate.estimated_total_cost_bps is not None:
            estimated_cost_available += 1
        if estimate.estimated_spread_cost_bps is not None:
            spread_available += 1
        if estimate.estimated_slippage_bps is not None:
            slippage_available += 1
        if estimate.estimated_fees_bps is not None:
            fees_available += 1
        if estimate.timeframe:
            timeframe_available += 1
        if record.regime:
            regime_available += 1
    count = len(estimate_pairs)
    reject_counts: Counter[str] = Counter()
    for _record, estimate in estimate_pairs:
        if estimate.reject_reason:
            for reason in str(estimate.reject_reason).split(";"):
                reject_counts[reason] += 1
    critical_counts = critical_warning_counts(records)
    return {
        "eligible_trade_count": count,
        "opportunity_score_available": score_available,
        "expected_move_available": expected_move_available,
        "estimated_cost_available": estimated_cost_available,
        "fees_available": fees_available,
        "spread_available": spread_available,
        "slippage_available": slippage_available,
        "timeframe_available": timeframe_available,
        "regime_available": regime_available,
        "forward_edge_valid": sum(1 for _record, estimate in estimate_pairs if estimate.is_valid),
        "forward_edge_positive": sum(
            1 for _record, estimate in estimate_pairs if (estimate.estimated_net_edge_bps or 0.0) > 0.0
        ),
        "score_coverage_pct": _pct(score_available, count),
        "expected_move_coverage_pct": _pct(expected_move_available, count),
        "cost_coverage_pct": _pct(estimated_cost_available, count),
        "forward_edge_valid_coverage_pct": _pct(
            sum(1 for _record, estimate in estimate_pairs if estimate.is_valid),
            count,
        ),
        "reject_reason_counts": dict(sorted(reject_counts.items())),
        "critical_warning_counts": critical_counts,
    }


def _coverage_delta(pre: Mapping[str, Any], post: Mapping[str, Any]) -> dict[str, Any]:
    fields = (
        "score_coverage_pct",
        "expected_move_coverage_pct",
        "cost_coverage_pct",
        "forward_edge_valid_coverage_pct",
    )
    return {
        field: {
            "pre_p10": pre.get(field),
            "post_p10": post.get(field),
            "delta_pct_points": _round((post.get(field) or 0.0) - (pre.get(field) or 0.0)),
        }
        for field in fields
    }


def _forward_only_result(
    scenarios: Sequence[ForwardEdgeScenario],
    post_summary: CohortSummary,
) -> dict[str, Any]:
    scenario_by_name = {scenario.name: scenario for scenario in scenarios}
    combined = scenario_by_name.get("forward_safe_net_edge_plus_score_high")
    if post_summary.eligible_trade_count == 0:
        confidence = "insufficient_data"
        recommendation = "continue_collection"
        reason = "no_post_p10_eligible_observations"
    elif combined is None or combined.trade_count < 50:
        confidence = "insufficient_data"
        recommendation = "continue_collection"
        reason = "forward_edge_plus_score_high_sample_below_50"
    elif (
        combined.net_profit_factor is None
        or combined.net_profit_factor <= 1.0
        or combined.net_expectancy_eur is None
        or combined.net_expectancy_eur <= 0.0
    ):
        confidence = "rejected"
        recommendation = "keep_shadow_only_and_rework_filter"
        reason = "forward_edge_plus_score_high_not_profitable_net"
    else:
        confidence = "early_signal"
        recommendation = "continue_forward_only_validation"
        reason = "positive_but_non_promotable_forward_sample"
    return {
        "confidence_level": confidence,
        "recommendation": recommendation,
        "reason": reason,
        "promotable": False,
        "paper_capital_allowed": False,
        "live_allowed": False,
    }


def _known_commit_cutoff(commit: str | None) -> str | None:
    if not commit:
        return None
    commit = commit.strip().lower()
    for known, timestamp in P10_COMMIT_CUTOFFS.items():
        if known.startswith(commit) or commit.startswith(known):
            return timestamp
    return None


def _parse_datetime(value: str) -> datetime:
    text = str(value).strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _pct(part: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return _round(part / total * 100.0)


def _round(value: float | None, digits: int = 4) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(value, digits)


def _fmt(value: float | None) -> str:
    if value is None or not math.isfinite(value):
        return "n/a"
    return f"{value:.4f}"


def _markdown(report: ForwardEdgeValidationReport) -> str:
    lines = [
        f"# Forward Edge Validation - {report.run_id}",
        "",
        f"- Generated: `{report.generated_at}`",
        f"- Cutoff: `{report.cutoff.get('since')}`",
        f"- Since commit: `{report.cutoff.get('since_commit')}`",
        f"- Cutoff criterion: `{report.cutoff.get('criterion')}`",
        f"- Cost profile: `{report.cost_profile.get('name')}`",
        "",
        "## Cohorts",
        "",
        "| Cohort | Total | Eligible | Legacy excluded | Policy excluded | Quality excluded | First opened | Last opened |",
        "|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for cohort in (report.pre_p10, report.post_p10):
        lines.append(
            "| {name} | {total} | {eligible} | {legacy} | {policy} | {quality} | {first} | {last} |".format(
                name=cohort.name,
                total=cohort.total_trade_count,
                eligible=cohort.eligible_trade_count,
                legacy=cohort.legacy_excluded_trade_count,
                policy=cohort.policy_excluded_trade_count,
                quality=cohort.quality_excluded_trade_count,
                first=cohort.first_opened_at or "n/a",
                last=cohort.last_opened_at or "n/a",
            )
        )
    lines.extend(["", "## Coverage", ""])
    for label, cohort in (("pre_p10", report.pre_p10), ("post_p10", report.post_p10)):
        coverage = cohort.pretrade_coverage
        lines.extend(
            [
                f"### {label}",
                "",
                f"- Score coverage: `{_fmt(coverage.get('score_coverage_pct'))}%`",
                f"- Expected move coverage: `{_fmt(coverage.get('expected_move_coverage_pct'))}%`",
                f"- Cost coverage: `{_fmt(coverage.get('cost_coverage_pct'))}%`",
                f"- Forward edge valid coverage: `{_fmt(coverage.get('forward_edge_valid_coverage_pct'))}%`",
                f"- Forward edge positive: `{coverage.get('forward_edge_positive', 0)}`",
                f"- Reject reasons: `{coverage.get('reject_reason_counts', {})}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Forward-Only Scenarios",
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
    policy_counts = Counter(item.policy for item in report.segment_policy)
    lines.extend(["", "## Segment Policy P11", ""])
    if policy_counts:
        lines.extend(f"- `{key}`: `{value}`" for key, value in sorted(policy_counts.items()))
    else:
        lines.append("- none")
    lines.extend(["", "## Forward-Only Result", ""])
    for key, value in report.forward_only_result.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Safety Notes", ""])
    lines.extend(f"- {note}" for note in report.safety_notes)
    if report.warnings:
        lines.extend(["", "## Loader Warnings", ""])
        counts = loader_warning_counts(report.warnings)
        lines.extend(f"- `{key}`: `{value}`" for key, value in sorted(counts.items()))
    return "\n".join(lines) + "\n"
