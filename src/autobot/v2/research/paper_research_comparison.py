"""Compare official paper evidence with research matrix evidence.

This module is read-only and report-only. It helps answer whether official
paper trading is telling the same story as replay/research validation without
changing runtime execution, strategy routing, risk, sizing, or the registry.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable, Mapping

from .decision_trace_audit import DecisionTrace, DecisionTraceAuditReport
from .metrics_engine import MetricsEngine
from .registry_recommendations import STRATEGY_TO_REGISTRY_ID
from .trade_journal import TradeJournal, TradeRecord
from .validation_matrix import MatrixCellResult, MatrixRunResult


STRATEGY_ALIASES: dict[str, str] = {
    "grid": "dynamic_grid",
    "dynamic_grid": "dynamic_grid",
    "trend": "trend_momentum",
    "trend_momentum": "trend_momentum",
    "mean_reversion": "mean_reversion",
}


@dataclass(frozen=True)
class EvidenceSummary:
    trade_count: int
    net_pnl_eur: float
    gross_pnl_eur: float | None = None
    fees_eur: float | None = None
    spread_cost_eur: float | None = None
    slippage_eur: float | None = None
    latency_cost_eur: float | None = None
    profit_factor: float | None = None
    winrate_pct: float | None = None
    max_drawdown_pct: float | None = None
    decisions: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["decisions"] = list(self.decisions)
        payload["reasons"] = list(self.reasons)
        return payload


@dataclass(frozen=True)
class DecisionTraceBucketSummary:
    trace_count: int
    canonical_complete_count: int
    rejected_count: int
    execution_count: int
    missing_stage_counts: dict[str, int]
    top_reasons: dict[str, int]
    net_pnl_eur: float

    @property
    def canonical_complete_ratio(self) -> float:
        return (self.canonical_complete_count / self.trace_count * 100.0) if self.trace_count else 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"canonical_complete_ratio": self.canonical_complete_ratio}


@dataclass(frozen=True)
class PaperResearchComparisonBucket:
    strategy_id: str
    symbol: str
    paper: EvidenceSummary
    research: EvidenceSummary
    delta_net_pnl_eur: float
    alignment: str
    recommendation: str
    diagnostics: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    decision_traces: DecisionTraceBucketSummary | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "paper": self.paper.to_dict(),
            "research": self.research.to_dict(),
            "delta_net_pnl_eur": self.delta_net_pnl_eur,
            "alignment": self.alignment,
            "recommendation": self.recommendation,
            "diagnostics": list(self.diagnostics),
            "warnings": list(self.warnings),
            "decision_traces": self.decision_traces.to_dict() if self.decision_traces else None,
        }


@dataclass(frozen=True)
class PaperResearchComparisonReport:
    run_id: str
    matrix_run_id: str
    paper_source_type: str
    paper_source_path: str
    bucket_count: int
    divergent_bucket_count: int
    paper_trade_count: int
    research_trade_count: int
    paper_net_pnl_eur: float
    research_net_pnl_eur: float
    buckets: tuple[PaperResearchComparisonBucket, ...]
    alignment_counts: dict[str, int] = field(default_factory=dict)
    diagnostic_counts: dict[str, int] = field(default_factory=dict)
    recommendation_counts: dict[str, int] = field(default_factory=dict)
    warning_counts: dict[str, int] = field(default_factory=dict)
    priority_buckets: tuple[dict[str, Any], ...] = ()
    warnings: tuple[str, ...] = ()
    decision_trace_run_id: str | None = None
    json_report_path: str | None = None
    markdown_report_path: str | None = None
    safety_notes: tuple[str, ...] = field(
        default=(
            "Read-only paper/research comparison.",
            "No paper or live order is created.",
            "No strategy registry mutation is performed.",
            "No live trading permission is granted.",
        )
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "matrix_run_id": self.matrix_run_id,
            "paper_source_type": self.paper_source_type,
            "paper_source_path": self.paper_source_path,
            "bucket_count": self.bucket_count,
            "divergent_bucket_count": self.divergent_bucket_count,
            "paper_trade_count": self.paper_trade_count,
            "research_trade_count": self.research_trade_count,
            "paper_net_pnl_eur": self.paper_net_pnl_eur,
            "research_net_pnl_eur": self.research_net_pnl_eur,
            "buckets": [bucket.to_dict() for bucket in self.buckets],
            "alignment_counts": dict(self.alignment_counts),
            "diagnostic_counts": dict(self.diagnostic_counts),
            "recommendation_counts": dict(self.recommendation_counts),
            "warning_counts": dict(self.warning_counts),
            "priority_buckets": list(self.priority_buckets),
            "warnings": list(self.warnings),
            "decision_trace_run_id": self.decision_trace_run_id,
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
            "safety_notes": list(self.safety_notes),
        }


def compare_paper_to_research(
    journal: TradeJournal,
    matrix: MatrixRunResult,
    *,
    run_id: str,
    paper_source_type: str,
    paper_source_path: str,
    initial_capital_eur: float = 1_000.0,
    warnings: Iterable[str] = (),
    decision_trace_report: DecisionTraceAuditReport | None = None,
) -> PaperResearchComparisonReport:
    """Compare paper ledger buckets with research matrix cells."""

    paper_groups = _group_paper_trades(journal.records)
    research_groups = _group_research_cells(matrix.results)
    trace_groups = _group_decision_traces(decision_trace_report.traces if decision_trace_report else ())
    keys = sorted(set(paper_groups) | set(research_groups) | set(trace_groups))
    buckets = tuple(
        _compare_bucket(
            strategy_id=strategy_id,
            symbol=symbol,
            paper_records=paper_groups.get((strategy_id, symbol), ()),
            research_cells=research_groups.get((strategy_id, symbol), ()),
            decision_trace_summary=trace_groups.get((strategy_id, symbol)),
            initial_capital_eur=initial_capital_eur,
        )
        for strategy_id, symbol in keys
    )
    divergent = sum(1 for bucket in buckets if bucket.alignment in _DIVERGENT_ALIGNMENTS)
    alignment_counts = Counter(bucket.alignment for bucket in buckets)
    diagnostic_counts = Counter(diagnostic for bucket in buckets for diagnostic in bucket.diagnostics)
    recommendation_counts = Counter(bucket.recommendation for bucket in buckets)
    warning_counts = Counter(warning for bucket in buckets for warning in bucket.warnings)
    return PaperResearchComparisonReport(
        run_id=run_id,
        matrix_run_id=matrix.run_id,
        paper_source_type=paper_source_type,
        paper_source_path=paper_source_path,
        bucket_count=len(buckets),
        divergent_bucket_count=divergent,
        paper_trade_count=sum(bucket.paper.trade_count for bucket in buckets),
        research_trade_count=sum(bucket.research.trade_count for bucket in buckets),
        paper_net_pnl_eur=sum(bucket.paper.net_pnl_eur for bucket in buckets),
        research_net_pnl_eur=sum(bucket.research.net_pnl_eur for bucket in buckets),
        buckets=buckets,
        alignment_counts=dict(alignment_counts),
        diagnostic_counts=dict(diagnostic_counts.most_common()),
        recommendation_counts=dict(recommendation_counts.most_common()),
        warning_counts=dict(warning_counts.most_common()),
        priority_buckets=_priority_buckets(buckets),
        warnings=tuple(warnings),
        decision_trace_run_id=decision_trace_report.run_id if decision_trace_report else None,
    )


def write_paper_research_comparison_report(
    report: PaperResearchComparisonReport,
    output_dir: str | Path,
) -> PaperResearchComparisonReport:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / f"{report.run_id}.json"
    md_path = output_path / f"{report.run_id}.md"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(render_paper_research_comparison_report(report), encoding="utf-8")
    return replace(report, json_report_path=str(json_path), markdown_report_path=str(md_path))


def render_paper_research_comparison_report(report: PaperResearchComparisonReport) -> str:
    lines = [
        f"# Paper vs Research Comparison - {report.run_id}",
        "",
        f"Matrix run: `{report.matrix_run_id}`",
        f"Paper source: `{report.paper_source_type}` / `{report.paper_source_path}`",
        f"Buckets: `{report.bucket_count}`",
        f"Divergent buckets: `{report.divergent_bucket_count}`",
        f"Paper trades: `{report.paper_trade_count}`",
        f"Research trades: `{report.research_trade_count}`",
        f"Paper net PnL EUR: `{report.paper_net_pnl_eur:.6f}`",
        f"Research net PnL EUR: `{report.research_net_pnl_eur:.6f}`",
        "",
        "## Triage Summary",
        "",
        f"Alignment counts: `{json.dumps(report.alignment_counts, sort_keys=True)}`",
        f"Top diagnostics: `{json.dumps(dict(list(report.diagnostic_counts.items())[:10]), sort_keys=True)}`",
        f"Top warnings: `{json.dumps(dict(list(report.warning_counts.items())[:10]), sort_keys=True)}`",
        "",
        "### Priority Buckets",
        "",
        "| Rank | Strategy | Symbol | Alignment | Paper Net | Research Net | Delta | Primary Diagnostic | Recommendation |",
        "| ---: | --- | --- | --- | ---: | ---: | ---: | --- | --- |",
    ]
    for idx, bucket in enumerate(report.priority_buckets, start=1):
        lines.append(
            f"| {idx} | {bucket['strategy_id']} | {bucket['symbol']} | {bucket['alignment']} | "
            f"{bucket['paper_net_pnl_eur']:.6f} | {bucket['research_net_pnl_eur']:.6f} | "
            f"{bucket['delta_net_pnl_eur']:.6f} | {bucket['primary_diagnostic']} | {bucket['recommendation']} |"
        )
    if not report.priority_buckets:
        lines.append("|  |  |  |  |  |  |  | none |  |")
    lines.extend(
        [
            "",
            "## Buckets",
            "",
            "| Strategy | Symbol | Paper Trades | Paper Net | Paper PF | Research Trades | Research Net | Research PF | Trace Count | Trace Missing | Delta | Alignment | Diagnostics | Recommendation |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | --- | --- | --- |",
        ]
    )
    for bucket in sorted(report.buckets, key=lambda item: (item.alignment, item.strategy_id, item.symbol)):
        trace_count = bucket.decision_traces.trace_count if bucket.decision_traces else 0
        trace_missing = _format_missing_stage_counts(bucket.decision_traces)
        lines.append(
            f"| {bucket.strategy_id} | {bucket.symbol} | "
            f"{bucket.paper.trade_count} | {bucket.paper.net_pnl_eur:.6f} | {_fmt(bucket.paper.profit_factor)} | "
            f"{bucket.research.trade_count} | {bucket.research.net_pnl_eur:.6f} | "
            f"{_fmt(bucket.research.profit_factor)} | {trace_count} | {trace_missing} | {bucket.delta_net_pnl_eur:.6f} | "
            f"{bucket.alignment} | {', '.join(bucket.diagnostics) or 'none'} | {bucket.recommendation} |"
        )
    if report.warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in report.warnings)
    lines.extend(["", "## Safety", ""])
    lines.extend(f"- {note}" for note in report.safety_notes)
    lines.append("")
    return "\n".join(lines)


def _group_paper_trades(records: Iterable[TradeRecord]) -> dict[tuple[str, str], tuple[TradeRecord, ...]]:
    grouped: dict[tuple[str, str], list[TradeRecord]] = {}
    for record in records:
        key = (_canonical_strategy(record.strategy_id), record.symbol.upper())
        grouped.setdefault(key, []).append(record)
    return {key: tuple(value) for key, value in grouped.items()}


def _group_research_cells(cells: Iterable[MatrixCellResult]) -> dict[tuple[str, str], tuple[MatrixCellResult, ...]]:
    grouped: dict[tuple[str, str], list[MatrixCellResult]] = {}
    for cell in cells:
        key = (_canonical_strategy(cell.strategy), cell.symbol.upper())
        grouped.setdefault(key, []).append(cell)
    return {key: tuple(value) for key, value in grouped.items()}


def _group_decision_traces(traces: Iterable[DecisionTrace]) -> dict[tuple[str, str], DecisionTraceBucketSummary]:
    grouped: dict[tuple[str, str], list[DecisionTrace]] = defaultdict(list)
    for trace in traces:
        symbol = str(trace.symbol or "").upper()
        if not symbol:
            continue
        strategy = _canonical_strategy(trace.engine or trace.strategy or "unknown")
        grouped[(strategy, symbol)].append(trace)
    return {key: _decision_trace_summary(value) for key, value in grouped.items()}


def _decision_trace_summary(traces: Iterable[DecisionTrace]) -> DecisionTraceBucketSummary:
    trace_list = tuple(traces)
    missing = Counter(stage for trace in trace_list for stage in trace.missing_stages)
    reasons = Counter(reason for trace in trace_list for reason in trace.reasons)
    return DecisionTraceBucketSummary(
        trace_count=len(trace_list),
        canonical_complete_count=sum(1 for trace in trace_list if trace.canonical_complete),
        rejected_count=sum(1 for trace in trace_list if trace.is_rejected),
        execution_count=sum(1 for trace in trace_list if trace.is_execution_path),
        missing_stage_counts=dict(missing),
        top_reasons=dict(reasons.most_common(8)),
        net_pnl_eur=sum(trace.net_pnl_eur for trace in trace_list),
    )


def _compare_bucket(
    *,
    strategy_id: str,
    symbol: str,
    paper_records: tuple[TradeRecord, ...],
    research_cells: tuple[MatrixCellResult, ...],
    decision_trace_summary: DecisionTraceBucketSummary | None,
    initial_capital_eur: float,
) -> PaperResearchComparisonBucket:
    paper = _paper_summary(paper_records, initial_capital_eur=initial_capital_eur)
    research = _research_summary(research_cells)
    delta = paper.net_pnl_eur - research.net_pnl_eur
    alignment = _alignment(paper, research)
    recommendation = _recommendation(alignment)
    diagnostics = list(_bucket_diagnostics(paper, research, alignment, decision_trace_summary))
    warnings = list(_bucket_warnings(paper, research, alignment))
    if strategy_id == "unknown" and paper.trade_count:
        diagnostics.append("paper_strategy_attribution_missing")
        warnings.append("paper_strategy_unknown")
        recommendation = "fix_paper_strategy_attribution_before_strategy_comparison"
    return PaperResearchComparisonBucket(
        strategy_id=strategy_id,
        symbol=symbol,
        paper=paper,
        research=research,
        delta_net_pnl_eur=delta,
        alignment=alignment,
        recommendation=recommendation,
        diagnostics=tuple(dict.fromkeys(diagnostics)),
        warnings=tuple(dict.fromkeys(warnings)),
        decision_traces=decision_trace_summary,
    )


def _paper_summary(records: tuple[TradeRecord, ...], *, initial_capital_eur: float) -> EvidenceSummary:
    if not records:
        return EvidenceSummary(trade_count=0, net_pnl_eur=0.0)
    metrics = MetricsEngine().calculate(records, initial_capital_eur=initial_capital_eur)
    return EvidenceSummary(
        trade_count=metrics.closed_trade_count,
        net_pnl_eur=metrics.total_net_pnl_eur,
        gross_pnl_eur=metrics.total_gross_pnl_eur,
        fees_eur=metrics.total_fees_eur,
        spread_cost_eur=metrics.total_spread_cost_eur,
        slippage_eur=metrics.total_slippage_eur,
        latency_cost_eur=metrics.total_latency_cost_eur,
        profit_factor=metrics.profit_factor,
        winrate_pct=metrics.winrate_pct,
        max_drawdown_pct=metrics.max_drawdown_pct,
        decisions=(),
        reasons=tuple(sorted({record.entry_reason for record in records if record.entry_reason})),
    )


def _research_summary(cells: tuple[MatrixCellResult, ...]) -> EvidenceSummary:
    if not cells:
        return EvidenceSummary(trade_count=0, net_pnl_eur=0.0)
    ok_cells = tuple(cell for cell in cells if cell.status == "ok")
    return EvidenceSummary(
        trade_count=sum(max(0, cell.closed_trades) for cell in ok_cells),
        net_pnl_eur=sum(cell.net_pnl_eur or 0.0 for cell in ok_cells),
        gross_pnl_eur=None,
        fees_eur=_sum_optional(cell.fees_eur for cell in ok_cells),
        spread_cost_eur=_sum_optional(cell.spread_cost_eur for cell in ok_cells),
        slippage_eur=_sum_optional(cell.slippage_eur for cell in ok_cells),
        latency_cost_eur=_sum_optional(cell.latency_cost_eur for cell in ok_cells),
        profit_factor=_max_optional(cell.profit_factor for cell in ok_cells),
        winrate_pct=None,
        max_drawdown_pct=_max_optional(cell.max_drawdown_pct for cell in ok_cells),
        decisions=tuple(sorted({str(cell.decision) for cell in ok_cells if cell.decision})),
        reasons=tuple(sorted({str(cell.reason) for cell in ok_cells if cell.reason})),
    )


_DIVERGENT_ALIGNMENTS = {
    "paper_positive_research_negative",
    "paper_negative_research_positive",
    "paper_missing_research_has_trades",
    "paper_has_trades_research_missing",
}


def _alignment(paper: EvidenceSummary, research: EvidenceSummary) -> str:
    if paper.trade_count == 0 and research.trade_count == 0:
        return "no_evidence"
    if paper.trade_count == 0:
        return "paper_missing_research_has_trades"
    if research.trade_count == 0:
        return "paper_has_trades_research_missing"
    paper_positive = paper.net_pnl_eur > 0.0
    research_positive = research.net_pnl_eur > 0.0
    if paper_positive and research_positive:
        return "aligned_positive"
    if not paper_positive and not research_positive:
        return "aligned_negative"
    if paper_positive:
        return "paper_positive_research_negative"
    return "paper_negative_research_positive"


def _recommendation(alignment: str) -> str:
    return {
        "aligned_positive": "keep_testing_require_baselines_before_promotion",
        "aligned_negative": "keep_blocked_or_modify_strategy",
        "paper_positive_research_negative": "investigate_runtime_or_sample_difference",
        "paper_negative_research_positive": "investigate_execution_or_router_gap",
        "paper_missing_research_has_trades": "check_router_or_paper_gate_coverage",
        "paper_has_trades_research_missing": "check_research_adapter_coverage",
        "no_evidence": "collect_more_data",
    }.get(alignment, "manual_review")


def _bucket_warnings(paper: EvidenceSummary, research: EvidenceSummary, alignment: str) -> tuple[str, ...]:
    warnings: list[str] = []
    if alignment in _DIVERGENT_ALIGNMENTS:
        warnings.append("paper_research_divergence")
    if paper.trade_count and paper.trade_count < 30:
        warnings.append("paper_sample_below_30_trades")
    if research.trade_count and research.trade_count < 30:
        warnings.append("research_sample_below_30_trades")
    if paper.profit_factor is None and paper.trade_count:
        warnings.append("paper_profit_factor_unavailable")
    if research.profit_factor is None and research.trade_count:
        warnings.append("research_profit_factor_unavailable")
    return tuple(warnings)


def _bucket_diagnostics(
    paper: EvidenceSummary,
    research: EvidenceSummary,
    alignment: str,
    decision_trace_summary: DecisionTraceBucketSummary | None,
) -> tuple[str, ...]:
    diagnostics: list[str] = []
    if alignment == "paper_positive_research_negative":
        diagnostics.append("runtime_or_sample_difference")
    elif alignment == "paper_negative_research_positive":
        diagnostics.append("router_risk_or_execution_gap")
    elif alignment == "paper_missing_research_has_trades":
        diagnostics.append("official_paper_missing_research_trades")
    elif alignment == "paper_has_trades_research_missing":
        diagnostics.append("research_adapter_missing_official_paper_trades")
    elif alignment == "aligned_negative":
        diagnostics.append("both_sources_unprofitable")
    elif alignment == "aligned_positive":
        diagnostics.append("both_sources_positive_requires_baseline_review")
    elif alignment == "no_evidence":
        diagnostics.append("no_comparable_trading_evidence")

    if paper.trade_count and paper.trade_count < 30:
        diagnostics.append("paper_sample_too_small")
    if research.trade_count and research.trade_count < 30:
        diagnostics.append("research_sample_too_small")
    if paper.trade_count and paper.profit_factor is None:
        diagnostics.append("paper_profit_factor_unavailable")
    if research.trade_count and research.profit_factor is None:
        diagnostics.append("research_profit_factor_unavailable")
    if research.trade_count and (
        research.fees_eur is None or research.spread_cost_eur is None or research.slippage_eur is None
    ):
        diagnostics.append("research_cost_breakdown_unavailable_from_matrix_summary")
    if "non_positive_net_pnl" in research.reasons:
        diagnostics.append("research_rejected_negative_net_pnl")
    if "negative_net_pnl" in research.reasons:
        diagnostics.append("research_rejected_negative_net_pnl")
    diagnostics.extend(_decision_trace_diagnostics(paper, research, decision_trace_summary))
    return tuple(dict.fromkeys(diagnostics))


def _priority_buckets(buckets: tuple[PaperResearchComparisonBucket, ...], *, limit: int = 8) -> tuple[dict[str, Any], ...]:
    ranked = sorted(
        buckets,
        key=lambda bucket: (
            bucket.alignment not in _DIVERGENT_ALIGNMENTS,
            -abs(bucket.delta_net_pnl_eur),
            bucket.strategy_id,
            bucket.symbol,
        ),
    )
    payloads: list[dict[str, Any]] = []
    for bucket in ranked[:limit]:
        payloads.append(
            {
                "strategy_id": bucket.strategy_id,
                "symbol": bucket.symbol,
                "alignment": bucket.alignment,
                "paper_trade_count": bucket.paper.trade_count,
                "research_trade_count": bucket.research.trade_count,
                "paper_net_pnl_eur": bucket.paper.net_pnl_eur,
                "research_net_pnl_eur": bucket.research.net_pnl_eur,
                "delta_net_pnl_eur": bucket.delta_net_pnl_eur,
                "primary_diagnostic": _primary_diagnostic(bucket.diagnostics),
                "recommendation": bucket.recommendation,
            }
        )
    return tuple(payloads)


def _primary_diagnostic(diagnostics: tuple[str, ...]) -> str:
    priority = (
        "paper_strategy_attribution_missing",
        "official_paper_missing_research_trades",
        "research_adapter_missing_official_paper_trades",
        "router_risk_or_execution_gap",
        "runtime_or_sample_difference",
        "both_sources_unprofitable",
    )
    for item in priority:
        if item in diagnostics:
            return item
    return diagnostics[0] if diagnostics else "none"


def _decision_trace_diagnostics(
    paper: EvidenceSummary,
    research: EvidenceSummary,
    summary: DecisionTraceBucketSummary | None,
) -> tuple[str, ...]:
    if summary is None:
        if paper.trade_count or research.trade_count:
            return ("decision_trace_missing_for_bucket",)
        return ()

    diagnostics: list[str] = []
    if summary.trace_count and summary.canonical_complete_count == 0:
        diagnostics.append("decision_trace_no_complete_pipeline")
    if summary.rejected_count:
        diagnostics.append("decision_trace_has_rejections")
    if summary.execution_count and summary.canonical_complete_count < summary.execution_count:
        diagnostics.append("decision_trace_execution_incomplete")
    for stage in sorted(summary.missing_stage_counts):
        diagnostics.append(f"decision_trace_missing_{stage}")
    if paper.trade_count == 0 and summary.execution_count:
        diagnostics.append("decision_trace_execution_without_closed_paper_trade")
    if paper.trade_count and summary.trace_count == 0:
        diagnostics.append("closed_paper_trade_without_decision_trace")
    return tuple(diagnostics)


def _format_missing_stage_counts(summary: DecisionTraceBucketSummary | None) -> str:
    if summary is None:
        return ""
    if not summary.missing_stage_counts:
        return "none"
    return ", ".join(f"{stage}:{count}" for stage, count in sorted(summary.missing_stage_counts.items()))


def _canonical_strategy(strategy: str) -> str:
    value = str(strategy or "unknown").strip()
    if not value:
        return "unknown"
    if value in STRATEGY_TO_REGISTRY_ID:
        return STRATEGY_TO_REGISTRY_ID[value]
    return STRATEGY_ALIASES.get(value, value)


def _max_optional(values: Iterable[float | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    return max(present) if present else None


def _sum_optional(values: Iterable[float | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    return sum(present) if present else None


def _fmt(value: float | None) -> str:
    return "" if value is None else f"{value:.6f}"
