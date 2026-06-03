"""Compare official paper evidence with research matrix evidence.

This module is read-only and report-only. It helps answer whether official
paper trading is telling the same story as replay/research validation without
changing runtime execution, strategy routing, risk, sizing, or the registry.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable, Mapping

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
    slippage_eur: float | None = None
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
class PaperResearchComparisonBucket:
    strategy_id: str
    symbol: str
    paper: EvidenceSummary
    research: EvidenceSummary
    delta_net_pnl_eur: float
    alignment: str
    recommendation: str
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "paper": self.paper.to_dict(),
            "research": self.research.to_dict(),
            "delta_net_pnl_eur": self.delta_net_pnl_eur,
            "alignment": self.alignment,
            "recommendation": self.recommendation,
            "warnings": list(self.warnings),
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
    warnings: tuple[str, ...] = ()
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
            "warnings": list(self.warnings),
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
) -> PaperResearchComparisonReport:
    """Compare paper ledger buckets with research matrix cells."""

    paper_groups = _group_paper_trades(journal.records)
    research_groups = _group_research_cells(matrix.results)
    keys = sorted(set(paper_groups) | set(research_groups))
    buckets = tuple(
        _compare_bucket(
            strategy_id=strategy_id,
            symbol=symbol,
            paper_records=paper_groups.get((strategy_id, symbol), ()),
            research_cells=research_groups.get((strategy_id, symbol), ()),
            initial_capital_eur=initial_capital_eur,
        )
        for strategy_id, symbol in keys
    )
    divergent = sum(1 for bucket in buckets if bucket.alignment in _DIVERGENT_ALIGNMENTS)
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
        warnings=tuple(warnings),
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
        "## Buckets",
        "",
        "| Strategy | Symbol | Paper Trades | Paper Net | Paper PF | Research Trades | Research Net | Research PF | Delta | Alignment | Recommendation |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for bucket in sorted(report.buckets, key=lambda item: (item.alignment, item.strategy_id, item.symbol)):
        lines.append(
            f"| {bucket.strategy_id} | {bucket.symbol} | "
            f"{bucket.paper.trade_count} | {bucket.paper.net_pnl_eur:.6f} | {_fmt(bucket.paper.profit_factor)} | "
            f"{bucket.research.trade_count} | {bucket.research.net_pnl_eur:.6f} | "
            f"{_fmt(bucket.research.profit_factor)} | {bucket.delta_net_pnl_eur:.6f} | "
            f"{bucket.alignment} | {bucket.recommendation} |"
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


def _compare_bucket(
    *,
    strategy_id: str,
    symbol: str,
    paper_records: tuple[TradeRecord, ...],
    research_cells: tuple[MatrixCellResult, ...],
    initial_capital_eur: float,
) -> PaperResearchComparisonBucket:
    paper = _paper_summary(paper_records, initial_capital_eur=initial_capital_eur)
    research = _research_summary(research_cells)
    delta = paper.net_pnl_eur - research.net_pnl_eur
    alignment = _alignment(paper, research)
    recommendation = _recommendation(alignment)
    warnings = _bucket_warnings(paper, research, alignment)
    return PaperResearchComparisonBucket(
        strategy_id=strategy_id,
        symbol=symbol,
        paper=paper,
        research=research,
        delta_net_pnl_eur=delta,
        alignment=alignment,
        recommendation=recommendation,
        warnings=warnings,
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
        slippage_eur=metrics.total_slippage_eur,
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
        fees_eur=None,
        slippage_eur=None,
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


def _fmt(value: float | None) -> str:
    return "" if value is None else f"{value:.6f}"
