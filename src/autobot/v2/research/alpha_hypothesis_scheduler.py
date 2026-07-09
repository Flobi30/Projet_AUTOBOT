"""Bounded Alpha Hypothesis Scheduler and research memory.

P18E keeps this layer research-only.  It ranks template-backed alpha
hypotheses, records trial counts, and recommends the next bounded runner
command.  It never generates code, never touches runtime trading, and never
promotes strategies.
"""

from __future__ import annotations

import csv
import json
import math
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .alpha_hypothesis_lab import RESEARCH_ONLY_CAPITAL_FLAGS, load_alpha_hypotheses
from .alpha_hypothesis_runner import AlphaHypothesisRunnerReport, canonical_hypothesis_id


REQUIRED_FAMILY_FIELDS = (
    "alpha_family_id",
    "economic_thesis",
    "why_it_might_persist",
    "required_data",
    "optional_data",
    "compatible_timeframes",
    "compatible_assets",
    "expected_trade_frequency",
    "cost_sensitivity",
    "typical_failure_modes",
    "minimum_validation",
    "suitable_for_current_vps",
    "suitable_for_spot_only",
    "requires_derivatives_data",
    "requires_orderbook_data",
    "requires_news_data",
    "default_rejection_rules",
    "hard_do_not_trade_conditions",
)
REQUIRED_TEMPLATE_FIELDS = (
    "template_id",
    "alpha_family_id",
    "signal_inputs",
    "entry_logic_description",
    "exit_logic_description",
    "risk_logic_description",
    "required_adapter",
    "max_variants",
    "max_symbols",
    "max_runtime_seconds",
    "allowed_parameter_ranges",
    "forbidden_optimizations",
    "anti_lookahead_rules",
    "expected_cost_model",
    "minimum_sample_size",
    "rejection_rules",
)
KNOWN_ADAPTERS = {
    "volatility_breakout": "alpha-hypothesis-runner",
    "long_trend": "alpha-hypothesis-runner",
}
FAMILY_TO_HYPOTHESIS = {
    "volatility_breakout": "volatility_breakout",
    "trend_momentum": "long_trend",
    "funding_basis": "funding_basis",
    "liquidation_cascade": "liquidation_cascade",
    "cross_sectional_momentum": "cross_momentum",
}
DERIVATIVES_DATA = {"derivatives_funding", "basis", "liquidation_events", "open_interest"}
ORDERBOOK_DATA = {"orderbook_depth", "bid_ask", "trade_ticks", "multi_exchange_quotes", "latency", "inventory_model"}
NEWS_DATA = {"timestamped_news_or_events", "sentiment"}
OHLCV_DATA = {
    "spot_ohlcv",
    "spot_ohlcv_multi_symbol",
    "atr",
    "range_compression",
    "fees_slippage",
    "multi_timeframe_trend",
    "realized_volatility",
    "volatility_expansion",
    "relative_momentum",
    "rolling_correlation",
    "relative_strength_rank",
    "volatility_regime",
}
STATUSES = {
    "REJECTED_CURRENT_CONFIG",
    "DATA_MISSING",
    "ADAPTER_MISSING",
    "RUNNABLE_SMOKE",
    "RUNNABLE_WALK_FORWARD",
    "WAITING_FOR_MORE_DATA",
    "HUMAN_REVIEW_REQUIRED",
}
REJECTED_MEMORY_STATUSES = {
    "ARCHIVED",
    "BENCHMARK_REJECTED",
    "DATA_MISSING",
    "HISTORICAL_RESULT_MISSING",
    "NO_GO",
    "REJECT",
    "REJECTED",
    "REJECT_FAST",
    "REJECTED_CURRENT_CONFIG",
    "RETIRED",
    "RETIRED_FROM_EXECUTION",
}
BACKFILL_SOURCE_REPORTS = {
    "p17_high_conviction_history_20260709": Path("reports/research/p17_high_conviction_historical_validation_2026-07-09.md"),
    "p18b_volatility_breakout_smoke_20260709": Path("reports/research/alpha_smoke/p18b_alpha_smoke_20260709.json"),
    "p18d_alpha_hypothesis_runner_walk_forward_20260709": Path("reports/research/alpha_hypothesis_runner/p18d_alpha_hypothesis_runner_walk_forward_20260709.json"),
    "p18e_alpha_runner_selected_smoke_20260709": Path("reports/research/alpha_hypothesis_runner/p18e_alpha_runner_selected_smoke_20260709.json"),
    "strategy_edge_review_20260629": Path("reports/research/strategy_edge_improvement_2026_06_29.json"),
    "relative_value_20260622": Path("reports/research/relative_value_2026_06_22/relative_value_2026_06_22.json"),
    "strategy_hypotheses_registry": Path("docs/research/strategy_hypotheses.json"),
}


class AlphaSchedulerError(ValueError):
    """Raised when knowledge, templates, or memory are invalid."""


@dataclass(frozen=True)
class ResearchMemoryRecord:
    run_id: str
    hypothesis_id: str
    alpha_family_id: str
    template_id: str
    created_at: str
    data_snapshot: dict[str, Any]
    parameters_tested: dict[str, Any]
    variant_count: int
    symbols_tested: tuple[str, ...]
    gate_results: tuple[dict[str, Any], ...]
    final_status: str
    rejection_reasons: tuple[str, ...]
    trial_count_for_family: int
    trial_count_for_template: int
    related_rejected_hypotheses: tuple[str, ...]
    do_not_rerun_until: str | None
    requires_new_data_before_rerun: bool
    paper_capital_allowed: bool = False
    live_allowed: bool = False
    promotable: bool = False
    metrics: dict[str, Any] = field(default_factory=dict)
    fold_results: tuple[dict[str, Any], ...] = ()
    source_report_path: str | None = None
    source_report_status: str = "available"

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ResearchMemoryRecord":
        return cls(
            run_id=str(payload["run_id"]),
            hypothesis_id=str(payload["hypothesis_id"]),
            alpha_family_id=str(payload["alpha_family_id"]),
            template_id=str(payload["template_id"]),
            created_at=str(payload["created_at"]),
            data_snapshot=dict(payload.get("data_snapshot") or {}),
            parameters_tested=dict(payload.get("parameters_tested") or {}),
            variant_count=max(1, int(payload.get("variant_count") or 1)),
            symbols_tested=tuple(str(item) for item in payload.get("symbols_tested", ())),
            gate_results=tuple(dict(item) for item in payload.get("gate_results", ())),
            final_status=str(payload.get("final_status") or "UNKNOWN"),
            rejection_reasons=tuple(str(item) for item in payload.get("rejection_reasons", ())),
            trial_count_for_family=max(1, int(payload.get("trial_count_for_family") or payload.get("variant_count") or 1)),
            trial_count_for_template=max(1, int(payload.get("trial_count_for_template") or payload.get("variant_count") or 1)),
            related_rejected_hypotheses=tuple(str(item) for item in payload.get("related_rejected_hypotheses", ())),
            do_not_rerun_until=payload.get("do_not_rerun_until"),
            requires_new_data_before_rerun=bool(payload.get("requires_new_data_before_rerun", False)),
            paper_capital_allowed=bool(payload.get("paper_capital_allowed", False)),
            live_allowed=bool(payload.get("live_allowed", False)),
            promotable=bool(payload.get("promotable", False)),
            metrics=dict(payload.get("metrics") or {}),
            fold_results=tuple(dict(item) for item in payload.get("fold_results", ())),
            source_report_path=payload.get("source_report_path"),
            source_report_status=str(payload.get("source_report_status") or "available"),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["symbols_tested"] = list(self.symbols_tested)
        payload["gate_results"] = [dict(item) for item in self.gate_results]
        payload["rejection_reasons"] = list(self.rejection_reasons)
        payload["related_rejected_hypotheses"] = list(self.related_rejected_hypotheses)
        payload["fold_results"] = [dict(item) for item in self.fold_results]
        return payload


@dataclass(frozen=True)
class AlphaResearchMemory:
    path: Path | None
    records: tuple[ResearchMemoryRecord, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "research_only": True,
            "paper_capital_allowed": False,
            "live_allowed": False,
            "free_code_generation_allowed": False,
            "records": [record.to_dict() for record in self.records],
        }

    def trial_count_by_family(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for record in self.records:
            counts[record.alpha_family_id] += max(1, record.variant_count)
        return dict(counts)

    def trial_count_by_template(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for record in self.records:
            counts[record.template_id] += max(1, record.variant_count)
        return dict(counts)

    def rejected_hypotheses(self) -> set[str]:
        rejected = set()
        for record in self.records:
            if record.final_status.upper() in REJECTED_MEMORY_STATUSES:
                rejected.add(record.hypothesis_id)
                rejected.update(record.related_rejected_hypotheses)
        return rejected

    def add_record(self, record: ResearchMemoryRecord) -> "AlphaResearchMemory":
        records = [existing for existing in self.records if existing.run_id != record.run_id]
        records.append(record)
        return AlphaResearchMemory(self.path, tuple(_with_running_counts(records)))

    def write(self, path: str | Path | None = None) -> None:
        target = Path(path) if path else self.path
        if target is None:
            raise AlphaSchedulerError("memory path is required")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True), encoding="utf-8")


@dataclass(frozen=True)
class DataReadiness:
    symbols: tuple[str, ...]
    timeframes: tuple[str, ...]
    row_count: int
    duplicate_count: int
    gap_count: int
    start_at: str | None
    end_at: str | None
    has_spot_ohlcv: bool
    has_multi_symbol_ohlcv: bool
    has_5m: bool
    has_15m: bool
    has_1h: bool
    has_orderbook: bool = False
    has_derivatives: bool = False
    has_news: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ScheduledHypothesis:
    hypothesis_id: str
    alpha_family_id: str
    template_id: str
    status: str
    priority_score: float
    reason_for_priority: str
    next_action: str
    recommended_command: str | None
    data_readiness: dict[str, Any]
    adapter_ready: bool
    trial_count_for_family: int
    trial_count_for_template: int
    estimated_cost: str
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    safety: dict[str, bool] = field(default_factory=lambda: dict(RESEARCH_ONLY_CAPITAL_FLAGS))

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["blockers"] = list(self.blockers)
        payload["warnings"] = list(self.warnings)
        return payload


@dataclass(frozen=True)
class AdapterBacklogItem:
    adapter_id: str
    template_id: str
    alpha_family_id: str
    hypotheses_blocked: tuple[str, ...]
    data_ready: bool
    data_missing_reasons: tuple[str, ...]
    estimated_implementation_complexity: str
    estimated_cpu_cost: str
    expected_trade_frequency: str
    current_vps_suitable: bool
    expected_reuse_score: float
    priority_score: float
    reason_for_priority: str
    blockers: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["hypotheses_blocked"] = list(self.hypotheses_blocked)
        payload["data_missing_reasons"] = list(self.data_missing_reasons)
        payload["blockers"] = list(self.blockers)
        return payload


@dataclass(frozen=True)
class MemoryBackfillSummary:
    before_count: int
    after_count: int
    added_count: int
    updated_count: int
    imported_run_ids: tuple[str, ...]
    missing_sources: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "before_count": self.before_count,
            "after_count": self.after_count,
            "added_count": self.added_count,
            "updated_count": self.updated_count,
            "imported_run_ids": list(self.imported_run_ids),
            "missing_sources": list(self.missing_sources),
        }


@dataclass(frozen=True)
class AlphaSchedulerConfig:
    state_db: Path | None
    data_paths: tuple[Path, ...]
    knowledge_base_path: Path = Path("docs/research/alpha_knowledge_base.json")
    templates_path: Path = Path("docs/research/strategy_templates.json")
    hypotheses_path: Path = Path("docs/research/alpha_hypotheses.json")
    memory_path: Path = Path("reports/research/alpha_research_memory.json")
    output_dir: Path = Path("reports/research/alpha_hypothesis_runner")
    run_id: str = "alpha_hypothesis_scheduler"
    max_variants: int = 5
    max_symbols: int = 6
    max_runtime_seconds: int = 300

    def __post_init__(self) -> None:
        if self.max_variants <= 0 or self.max_variants > 5:
            raise ValueError("max_variants must be between 1 and 5")
        if self.max_symbols <= 0 or self.max_symbols > 14:
            raise ValueError("max_symbols must be between 1 and 14")
        if self.max_runtime_seconds <= 0:
            raise ValueError("max_runtime_seconds must be positive")


@dataclass(frozen=True)
class AlphaSchedulerReport:
    run_id: str
    generated_at: str
    state_db: str | None
    data_paths: tuple[str, ...]
    families: tuple[dict[str, Any], ...]
    templates: tuple[dict[str, Any], ...]
    data_readiness: dict[str, Any]
    adapter_readiness: dict[str, str]
    trial_counts_by_family: dict[str, int]
    trial_counts_by_template: dict[str, int]
    candidates: tuple[ScheduledHypothesis, ...]
    selected: ScheduledHypothesis | None
    adapter_backlog: tuple[AdapterBacklogItem, ...]
    top_recommended_adapter: AdapterBacklogItem | None
    next_runner_command: str | None
    safety_notes: tuple[str, ...]
    memory_backfill: MemoryBackfillSummary | None = None
    json_report_path: str | None = None
    markdown_report_path: str | None = None
    paper_capital_allowed: bool = False
    live_allowed: bool = False
    promotable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "state_db": self.state_db,
            "data_paths": list(self.data_paths),
            "families": [dict(item) for item in self.families],
            "templates": [dict(item) for item in self.templates],
            "data_readiness": dict(self.data_readiness),
            "adapter_readiness": dict(self.adapter_readiness),
            "trial_counts_by_family": dict(self.trial_counts_by_family),
            "trial_counts_by_template": dict(self.trial_counts_by_template),
            "candidates": [item.to_dict() for item in self.candidates],
            "selected": self.selected.to_dict() if self.selected else None,
            "adapter_backlog": [item.to_dict() for item in self.adapter_backlog],
            "top_recommended_adapter": self.top_recommended_adapter.to_dict() if self.top_recommended_adapter else None,
            "next_runner_command": self.next_runner_command,
            "safety_notes": list(self.safety_notes),
            "memory_backfill": self.memory_backfill.to_dict() if self.memory_backfill else None,
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
            "paper_capital_allowed": self.paper_capital_allowed,
            "live_allowed": self.live_allowed,
            "promotable": self.promotable,
        }


def load_alpha_knowledge_base(path: str | Path) -> dict[str, Any]:
    payload = _load_json(path)
    _validate_root_research_only(payload, "alpha knowledge base")
    families = payload.get("families")
    if not isinstance(families, list) or not families:
        raise AlphaSchedulerError("alpha knowledge base must contain families")
    seen: set[str] = set()
    for family in families:
        _require_fields(family, REQUIRED_FAMILY_FIELDS, "alpha family")
        family_id = str(family["alpha_family_id"])
        if family_id in seen:
            raise AlphaSchedulerError(f"duplicate alpha family: {family_id}")
        seen.add(family_id)
    return payload


def load_strategy_templates(path: str | Path) -> dict[str, Any]:
    payload = _load_json(path)
    _validate_root_research_only(payload, "strategy templates")
    templates = payload.get("templates")
    if not isinstance(templates, list) or not templates:
        raise AlphaSchedulerError("strategy templates must contain templates")
    seen: set[str] = set()
    for template in templates:
        _require_fields(template, REQUIRED_TEMPLATE_FIELDS, "strategy template")
        template_id = str(template["template_id"])
        if template_id in seen:
            raise AlphaSchedulerError(f"duplicate strategy template: {template_id}")
        seen.add(template_id)
        if int(template["max_variants"]) > 5:
            raise AlphaSchedulerError(f"{template_id} max_variants must stay bounded")
        if bool(template.get("paper_capital_allowed")) or bool(template.get("live_allowed")):
            raise AlphaSchedulerError(f"{template_id} cannot allow paper/live")
    return payload


def load_alpha_research_memory(path: str | Path) -> AlphaResearchMemory:
    memory_path = Path(path)
    if not memory_path.exists():
        return AlphaResearchMemory(memory_path, ())
    payload = _load_json(memory_path)
    _validate_root_research_only(payload, "alpha research memory")
    records = tuple(ResearchMemoryRecord.from_mapping(item) for item in payload.get("records", ()))
    for record in records:
        if record.paper_capital_allowed or record.live_allowed or record.promotable:
            raise AlphaSchedulerError(f"memory record {record.run_id} cannot allow paper/live/promotion")
    return AlphaResearchMemory(memory_path, tuple(_with_running_counts(records)))


def record_alpha_runner_trial(
    report: AlphaHypothesisRunnerReport,
    *,
    memory_path: str | Path,
    template_id: str,
    alpha_family_id: str,
) -> ResearchMemoryRecord:
    memory = load_alpha_research_memory(memory_path)
    variant_count = _variant_count_from_report(report)
    record = ResearchMemoryRecord(
        run_id=report.run_id,
        hypothesis_id=report.hypothesis_id,
        alpha_family_id=alpha_family_id,
        template_id=template_id,
        created_at=report.generated_at,
        data_snapshot={
            "data_paths": list(report.data_paths),
            "state_db": report.state_db,
        },
        parameters_tested={
            "mode": report.mode,
            "max_stage_reached": report.gates[-1].gate if report.gates else None,
        },
        variant_count=variant_count,
        symbols_tested=(),
        gate_results=tuple(
            {"gate": gate.gate, "status": gate.status, "passed": gate.passed}
            for gate in report.gates
        ),
        final_status=_memory_final_status(report.final_status),
        rejection_reasons=tuple(report.reasons),
        trial_count_for_family=variant_count,
        trial_count_for_template=variant_count,
        related_rejected_hypotheses=(report.hypothesis_id,) if _is_rejected_status(report.final_status) else (),
        do_not_rerun_until=None,
        requires_new_data_before_rerun=_is_rejected_status(report.final_status),
        metrics=_metrics_from_runner_report(report),
    )
    updated = memory.add_record(record)
    updated.write(memory_path)
    return updated.records[-1]


def backfill_alpha_research_memory(
    *,
    memory_path: str | Path,
    repo_root: str | Path = ".",
) -> MemoryBackfillSummary:
    """Import bounded historical results into research memory.

    The backfill is intentionally conservative: it imports metrics only from
    known source reports, marks unavailable reports explicitly, and keeps all
    imported records research-only/non-promotable.
    """

    root = Path(repo_root)
    memory = load_alpha_research_memory(memory_path)
    before_by_run = {record.run_id: record for record in memory.records}
    imported: list[ResearchMemoryRecord] = []
    missing_sources: list[str] = []
    for record in _historical_backfill_records(root):
        imported.append(record)
        if record.source_report_status != "available":
            missing_sources.append(record.run_id)
        memory = memory.add_record(record)
    memory.write(memory_path)
    after_by_run = {record.run_id: record for record in memory.records}
    added = [run_id for run_id in after_by_run if run_id not in before_by_run]
    updated = [run_id for run_id in after_by_run if run_id in before_by_run and after_by_run[run_id] != before_by_run[run_id]]
    return MemoryBackfillSummary(
        before_count=len(before_by_run),
        after_count=len(after_by_run),
        added_count=len(added),
        updated_count=len(updated),
        imported_run_ids=tuple(record.run_id for record in imported),
        missing_sources=tuple(missing_sources),
    )


def build_alpha_hypothesis_scheduler_report(config: AlphaSchedulerConfig) -> AlphaSchedulerReport:
    knowledge = load_alpha_knowledge_base(config.knowledge_base_path)
    templates = load_strategy_templates(config.templates_path)
    hypotheses = load_alpha_hypotheses(config.hypotheses_path)
    memory = load_alpha_research_memory(config.memory_path)
    readiness = scan_data_readiness(config.data_paths)
    adapter_readiness = _adapter_readiness(templates)
    family_counts = memory.trial_count_by_family()
    template_counts = memory.trial_count_by_template()
    hypothesis_ids = {str(item["id"]) for item in hypotheses.get("hypotheses", ())}
    candidates: list[ScheduledHypothesis] = []
    family_by_id = {str(item["alpha_family_id"]): item for item in knowledge["families"]}
    for template in templates["templates"]:
        family_id = str(template["alpha_family_id"])
        family = family_by_id.get(family_id)
        if family is None:
            candidates.append(_candidate_missing_family(template, readiness))
            continue
        hypothesis_id = FAMILY_TO_HYPOTHESIS.get(family_id, family_id)
        if hypothesis_id not in hypothesis_ids:
            hypothesis_id = f"{family_id}__{template['template_id']}"
        candidates.append(
            _schedule_template(
                template=template,
                family=family,
                hypothesis_id=hypothesis_id,
                data=readiness,
                adapter_status=adapter_readiness.get(str(template["template_id"]), "ADAPTER_MISSING"),
                memory=memory,
                family_trial_count=family_counts.get(family_id, 0),
                template_trial_count=template_counts.get(str(template["template_id"]), 0),
                config=config,
            )
        )
    ranked = tuple(sorted(candidates, key=lambda item: (-item.priority_score, item.template_id)))
    selected = next((item for item in ranked if item.status == "RUNNABLE_SMOKE"), None)
    command = selected.recommended_command if selected else None
    adapter_backlog = _build_adapter_backlog(
        templates=templates,
        families=family_by_id,
        candidates=ranked,
        memory=memory,
        data=readiness,
    )
    top_adapter = next((item for item in adapter_backlog if item.priority_score > 0), None)
    return AlphaSchedulerReport(
        run_id=config.run_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        state_db=str(config.state_db) if config.state_db else None,
        data_paths=tuple(str(path) for path in config.data_paths),
        families=tuple(knowledge["families"]),
        templates=tuple(templates["templates"]),
        data_readiness=readiness.to_dict(),
        adapter_readiness=adapter_readiness,
        trial_counts_by_family=family_counts,
        trial_counts_by_template=template_counts,
        candidates=ranked,
        selected=selected,
        adapter_backlog=adapter_backlog,
        top_recommended_adapter=top_adapter,
        next_runner_command=command,
        safety_notes=(
            "Research-only scheduler.",
            "No free code generation.",
            "No runtime order path, paper capital, live activation, promotion, sizing, leverage, or UI change.",
            "Rejected hypotheses receive zero priority until new data or a new thesis is recorded.",
        ),
    )


def write_alpha_hypothesis_scheduler_report(
    report: AlphaSchedulerReport,
    output_dir: str | Path,
) -> AlphaSchedulerReport:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / f"{report.run_id}.json"
    markdown_path = output / f"{report.run_id}.md"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(render_alpha_hypothesis_scheduler_report(report), encoding="utf-8")
    return replace(report, json_report_path=str(json_path), markdown_report_path=str(markdown_path))


def render_alpha_hypothesis_scheduler_report(report: AlphaSchedulerReport) -> str:
    lines = [
        f"# P18E Alpha Hypothesis Scheduler - {report.run_id}",
        "",
        "## Scope",
        "",
        "- Mode: `research_only`.",
        "- No live, no paper capital, no promotion, no shadow activation.",
        "- No runtime order path, no UI, no sizing/leverage change.",
        "- No self-modifying code and no free strategy code generation.",
        "",
        "## Data Readiness",
        "",
    ]
    for key, value in report.data_readiness.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Candidates", ""])
    lines.append("| Rank | Hypothesis | Template | Status | Priority | Reason | Next action |")
    lines.append("|---:|---|---|---|---:|---|---|")
    for index, candidate in enumerate(report.candidates, start=1):
        lines.append(
            f"| {index} | `{candidate.hypothesis_id}` | `{candidate.template_id}` | `{candidate.status}` | "
            f"{candidate.priority_score:.2f} | {candidate.reason_for_priority} | {candidate.next_action} |"
        )
    lines.extend(["", "## Selected Next Hypothesis", ""])
    if report.selected:
        lines.append(f"- Hypothesis: `{report.selected.hypothesis_id}`")
        lines.append(f"- Template: `{report.selected.template_id}`")
        lines.append(f"- Command: `{report.next_runner_command}`")
    else:
        lines.append("- No runnable smoke hypothesis. Build missing data/adapters first.")
    lines.extend(["", "## Adapter Backlog", ""])
    if report.adapter_backlog:
        lines.append("| Rank | Adapter | Template | Family | Data ready | Priority | Reason |")
        lines.append("|---:|---|---|---|---:|---:|---|")
        for index, item in enumerate(report.adapter_backlog, start=1):
            lines.append(
                f"| {index} | `{item.adapter_id}` | `{item.template_id}` | `{item.alpha_family_id}` | "
                f"`{item.data_ready}` | {item.priority_score:.2f} | {item.reason_for_priority} |"
            )
    else:
        lines.append("- No missing adapters detected.")
    lines.extend(["", "## Top Adapter Recommendation", ""])
    if report.top_recommended_adapter:
        item = report.top_recommended_adapter
        lines.append(f"- Adapter: `{item.adapter_id}`")
        lines.append(f"- Template: `{item.template_id}`")
        lines.append(f"- Priority: `{item.priority_score:.2f}`")
        lines.append(f"- Reason: {item.reason_for_priority}")
    else:
        lines.append("- No adapter is currently worth building before data/thesis changes.")
    if report.memory_backfill:
        lines.extend(["", "## Memory Backfill", ""])
        for key, value in report.memory_backfill.to_dict().items():
            lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Trial Counts", ""])
    lines.append(f"- By family: `{report.trial_counts_by_family}`")
    lines.append(f"- By template: `{report.trial_counts_by_template}`")
    lines.extend(["", "## Safety", ""])
    lines.extend(f"- {note}" for note in report.safety_notes)
    lines.append(f"- paper_capital_allowed: `{report.paper_capital_allowed}`")
    lines.append(f"- live_allowed: `{report.live_allowed}`")
    lines.append(f"- promotable: `{report.promotable}`")
    return "\n".join(lines) + "\n"


def _historical_backfill_records(repo_root: Path) -> tuple[ResearchMemoryRecord, ...]:
    records: list[ResearchMemoryRecord] = []
    records.append(_record_from_p17_high_conviction(repo_root))
    records.append(_record_from_p18b_volatility(repo_root))
    records.append(_record_from_runner_json(repo_root, "p18d_alpha_hypothesis_runner_walk_forward_20260709"))
    records.append(_record_from_runner_json(repo_root, "p18e_alpha_runner_selected_smoke_20260709"))
    records.extend(_records_from_strategy_edge(repo_root))
    records.append(_record_from_relative_value(repo_root))
    records.append(_record_from_grid_registry(repo_root))
    return tuple(records)


def _record_from_p17_high_conviction(repo_root: Path) -> ResearchMemoryRecord:
    report_path = BACKFILL_SOURCE_REPORTS["p17_high_conviction_history_20260709"]
    if not (repo_root / report_path).exists():
        return _missing_source_record(
            run_id="p17_high_conviction_history_20260709",
            hypothesis_id="high_conviction_swing",
            alpha_family_id="volatility_breakout",
            template_id="breakout_after_compression",
            source_report_path=report_path,
        )
    return ResearchMemoryRecord(
        run_id="p17_high_conviction_history_20260709",
        hypothesis_id="high_conviction_swing",
        alpha_family_id="volatility_breakout",
        template_id="breakout_after_compression",
        created_at="2026-07-09T00:00:00+00:00",
        data_snapshot={
            "source": "historical_ohlcv_walk_forward",
            "start_at": "2026-05-16T16:00:00Z",
            "end_at": "2026-07-09T00:15:00Z",
            "deduped_rows": 159782,
            "folds": 13,
        },
        parameters_tested={
            "min_expected_move_bps": 500,
            "risk_reward_ratio": 2,
            "max_hold_hours": 72,
            "primary_exit_mode": "fixed_tp_sl",
            "initial_capital_eur": 500,
        },
        variant_count=4,
        symbols_tested=("AAVEEUR", "ADAEUR", "ATOMEUR", "AVAXEUR", "BCHEUR", "BTCZEUR", "DOTEUR", "ETHZEUR", "LINKEUR", "LTCZEUR", "SOLEUR", "TRXEUR", "XLMZEUR", "XRPZEUR"),
        gate_results=(
            {"gate": "WALK_FORWARD", "status": "REJECT", "passed": False},
        ),
        final_status="REJECTED",
        rejection_reasons=(
            "net_pnl_negative_after_costs",
            "profit_factor_below_1",
            "expectancy_negative",
            "insufficient_positive_out_of_sample_folds",
            "single_symbol_concentration",
        ),
        trial_count_for_family=4,
        trial_count_for_template=4,
        related_rejected_hypotheses=("high_conviction_swing",),
        do_not_rerun_until=None,
        requires_new_data_before_rerun=True,
        metrics={
            "trade_count": 82,
            "profit_factor_net": 0.8772,
            "net_pnl_eur": -16.53,
            "expectancy_net": -0.2016,
            "winrate_pct": 34.15,
            "positive_folds": 4,
            "fold_count": 13,
            "max_drawdown_pct": 4.22,
            "largest_positive_symbol_share": 0.4741,
        },
        fold_results=(
            {"fold": 1, "net_pnl_eur": 0.0, "trade_count": 0},
            {"fold": 2, "net_pnl_eur": 24.30, "profit_factor_net": 12.51, "trade_count": 5},
            {"fold": 3, "net_pnl_eur": 18.70, "profit_factor_net": 3.93, "trade_count": 7},
            {"fold": 4, "net_pnl_eur": -18.95, "profit_factor_net": 0.0, "trade_count": 6},
            {"fold": 5, "net_pnl_eur": -2.89, "profit_factor_net": 0.61, "trade_count": 6},
            {"fold": 6, "net_pnl_eur": -6.03, "profit_factor_net": 0.0, "trade_count": 3},
            {"fold": 7, "net_pnl_eur": -4.69, "profit_factor_net": 0.67, "trade_count": 9},
            {"fold": 8, "net_pnl_eur": -3.30, "profit_factor_net": 0.81, "trade_count": 9},
            {"fold": 9, "net_pnl_eur": -14.00, "profit_factor_net": 0.0, "trade_count": 6},
            {"fold": 10, "net_pnl_eur": -11.97, "profit_factor_net": 0.38, "trade_count": 10},
            {"fold": 11, "net_pnl_eur": 5.02, "profit_factor_net": 1.44, "trade_count": 10},
            {"fold": 12, "net_pnl_eur": 12.22, "profit_factor_net": 5.46, "trade_count": 5},
            {"fold": 13, "net_pnl_eur": -14.92, "profit_factor_net": 0.0, "trade_count": 6},
        ),
        source_report_path=str(report_path),
    )


def _record_from_p18b_volatility(repo_root: Path) -> ResearchMemoryRecord:
    source_path = BACKFILL_SOURCE_REPORTS["p18b_volatility_breakout_smoke_20260709"]
    payload = _safe_load_json(repo_root / source_path)
    if payload is None:
        return _missing_source_record(
            run_id="p18b_volatility_breakout_smoke_20260709",
            hypothesis_id="volatility_breakout",
            alpha_family_id="volatility_breakout",
            template_id="breakout_after_compression",
            source_report_path=source_path,
        )
    tested = next(
        (item for item in payload.get("tested", ()) if item.get("hypothesis_id") == "volatility_breakout_high_conviction"),
        {},
    )
    metrics = dict(tested.get("metrics") or {})
    return ResearchMemoryRecord(
        run_id="p18b_volatility_breakout_smoke_20260709",
        hypothesis_id="volatility_breakout",
        alpha_family_id="volatility_breakout",
        template_id="breakout_after_compression",
        created_at=str(payload.get("generated_at") or "2026-07-09T00:00:00+00:00"),
        data_snapshot=_availability_for(payload, "volatility_breakout_high_conviction"),
        parameters_tested={"best_variant": tested.get("best_variant"), "stage": "smoke"},
        variant_count=max(1, int(tested.get("variant_count") or 1)),
        symbols_tested=tuple((metrics.get("by_symbol") or {}).keys()),
        gate_results=({"gate": "FAST_NET_EDGE_TEST", "status": tested.get("decision", "UNKNOWN"), "passed": tested.get("decision") == "KEEP_RESEARCH"},),
        final_status=str(tested.get("decision") or "UNKNOWN"),
        rejection_reasons=tuple(str(item) for item in tested.get("reasons", ())),
        trial_count_for_family=max(1, int(tested.get("variant_count") or 1)),
        trial_count_for_template=max(1, int(tested.get("variant_count") or 1)),
        related_rejected_hypotheses=(),
        do_not_rerun_until=None,
        requires_new_data_before_rerun=False,
        metrics={
            "trade_count": metrics.get("trade_count"),
            "profit_factor_net": metrics.get("profit_factor_net"),
            "net_pnl_eur": metrics.get("net_pnl_eur"),
            "expectancy_net": metrics.get("expectancy_net"),
            "max_drawdown_eur": metrics.get("max_drawdown_eur"),
            "winrate_pct": metrics.get("winrate_pct"),
        },
        source_report_path=str(source_path),
    )


def _record_from_runner_json(repo_root: Path, run_id: str) -> ResearchMemoryRecord:
    source_path = BACKFILL_SOURCE_REPORTS.get(run_id, Path(f"reports/research/alpha_hypothesis_runner/{run_id}.json"))
    payload = _safe_load_json(repo_root / source_path)
    if payload is None:
        return _missing_source_record(
            run_id=run_id,
            hypothesis_id="unknown",
            alpha_family_id="unknown",
            template_id="unknown",
            source_report_path=source_path,
        )
    hypothesis_id = str(payload.get("hypothesis_id") or payload.get("requested_hypothesis_id") or "unknown")
    alpha_family_id = "trend_momentum" if hypothesis_id == "long_trend" else hypothesis_id
    template_id = "regime_filtered_trend" if hypothesis_id == "long_trend" else "breakout_after_compression"
    gates = tuple(dict(item) for item in payload.get("gates", ()))
    metrics = _metrics_from_gates(gates)
    return ResearchMemoryRecord(
        run_id=run_id,
        hypothesis_id=hypothesis_id,
        alpha_family_id=alpha_family_id,
        template_id=template_id,
        created_at=str(payload.get("generated_at") or "2026-07-09T00:00:00+00:00"),
        data_snapshot={
            "data_paths": list(payload.get("data_paths") or ()),
            "state_db": payload.get("state_db"),
        },
        parameters_tested={
            "mode": payload.get("mode"),
            "max_stage_reached": gates[-1]["gate"] if gates else None,
        },
        variant_count=max(1, int(metrics.get("variant_count") or _variant_count_from_gate_dicts(gates))),
        symbols_tested=tuple((metrics.get("by_symbol") or {}).keys()),
        gate_results=tuple({"gate": item.get("gate"), "status": item.get("status"), "passed": item.get("passed")} for item in gates),
        final_status=_memory_final_status(str(payload.get("final_status") or "UNKNOWN")),
        rejection_reasons=tuple(str(item) for item in payload.get("reasons", ())),
        trial_count_for_family=max(1, int(metrics.get("variant_count") or _variant_count_from_gate_dicts(gates))),
        trial_count_for_template=max(1, int(metrics.get("variant_count") or _variant_count_from_gate_dicts(gates))),
        related_rejected_hypotheses=(hypothesis_id,) if _is_rejected_status(str(payload.get("final_status") or "")) else (),
        do_not_rerun_until="2026-07-16T00:00:00+00:00" if hypothesis_id == "volatility_breakout" else None,
        requires_new_data_before_rerun=_is_rejected_status(str(payload.get("final_status") or "")),
        metrics=metrics,
        fold_results=tuple(_fold_results_from_gates(gates)),
        source_report_path=str(source_path),
    )


def _records_from_strategy_edge(repo_root: Path) -> tuple[ResearchMemoryRecord, ...]:
    source_path = BACKFILL_SOURCE_REPORTS["strategy_edge_review_20260629"]
    payload = _safe_load_json(repo_root / source_path)
    if payload is None:
        return (
            _missing_source_record(
                run_id="strategy_edge_review_20260629",
                hypothesis_id="strategy_edge_review",
                alpha_family_id="strategy_edge",
                template_id="strategy_edge_review",
                source_report_path=source_path,
            ),
        )
    records: list[ResearchMemoryRecord] = []
    for item in payload.get("strategy_triage", ()):
        strategy_name = str(item.get("strategy_name") or "unknown")
        if strategy_name == "high_conviction_swing":
            continue
        final_status = _triage_status(strategy_name, item)
        records.append(
            ResearchMemoryRecord(
                run_id=f"strategy_edge_review_20260629_{strategy_name}",
                hypothesis_id=strategy_name,
                alpha_family_id=_family_for_strategy(strategy_name),
                template_id=_template_for_strategy(strategy_name),
                created_at=str(payload.get("generated_at") or "2026-06-29T00:00:00+00:00"),
                data_snapshot={"source": "strategy_edge_review"},
                parameters_tested={"status_review": item.get("requested_status")},
                variant_count=1,
                symbols_tested=(),
                gate_results=({"gate": "STRATEGY_TRIAGE", "status": final_status, "passed": False},),
                final_status=final_status,
                rejection_reasons=tuple(str(value) for value in item.get("blockers", ())),
                trial_count_for_family=1,
                trial_count_for_template=1,
                related_rejected_hypotheses=(strategy_name,),
                do_not_rerun_until=None,
                requires_new_data_before_rerun=True,
                metrics={
                    "trade_count": item.get("trade_count"),
                    "profit_factor_net": item.get("profit_factor"),
                    "net_pnl_eur": item.get("net_pnl_eur"),
                    "positive_folds": item.get("positive_folds"),
                    "fold_count": item.get("total_folds"),
                    "max_drawdown_pct": item.get("max_drawdown_pct"),
                    "winrate_pct": item.get("winrate_pct"),
                },
                source_report_path=str(source_path),
            )
        )
    return tuple(records)


def _record_from_relative_value(repo_root: Path) -> ResearchMemoryRecord:
    source_path = BACKFILL_SOURCE_REPORTS["relative_value_20260622"]
    payload = _safe_load_json(repo_root / source_path)
    if payload is None:
        return _missing_source_record(
            run_id="relative_value_20260622",
            hypothesis_id="relative_value",
            alpha_family_id="relative_value",
            template_id="relative_value_pair_spread",
            source_report_path=source_path,
        )
    base = next((item for item in payload.get("portfolio_results", ()) if item.get("cost_profile") == "paper_current_taker"), {})
    stress = next((item for item in payload.get("portfolio_results", ()) if item.get("cost_profile") == "research_stress"), {})
    blockers = tuple(str(item) for item in base.get("blockers", ()))
    return ResearchMemoryRecord(
        run_id="relative_value_20260622",
        hypothesis_id="relative_value",
        alpha_family_id="relative_value",
        template_id="relative_value_pair_spread",
        created_at=str(payload.get("generated_at") or "2026-06-22T00:00:00+00:00"),
        data_snapshot={"data_paths": list(payload.get("data_paths") or ()), "timeframe": payload.get("timeframe")},
        parameters_tested={"relationships": len(payload.get("relationships", ())), "cost_profiles": ("paper_current_taker", "research_stress")},
        variant_count=2,
        symbols_tested=tuple((base.get("pnl_by_symbol") or {}).keys()),
        gate_results=({"gate": "PORTFOLIO_REPLAY", "status": "NO_GO", "passed": False},),
        final_status="NO_GO",
        rejection_reasons=blockers or ("relative_value_validation_failed",),
        trial_count_for_family=2,
        trial_count_for_template=2,
        related_rejected_hypotheses=("relative_value",),
        do_not_rerun_until=None,
        requires_new_data_before_rerun=True,
        metrics={
            "trade_count": base.get("accepted_trade_count"),
            "profit_factor_net": base.get("profit_factor"),
            "net_pnl_eur": base.get("net_pnl_eur"),
            "expectancy_net": base.get("expectancy_eur"),
            "max_drawdown_pct": base.get("max_drawdown_pct"),
            "winrate_pct": base.get("winrate_pct"),
            "stress_profit_factor_net": stress.get("profit_factor"),
            "stress_net_pnl_eur": stress.get("net_pnl_eur"),
        },
        source_report_path=str(source_path),
    )


def _record_from_grid_registry(repo_root: Path) -> ResearchMemoryRecord:
    source_path = BACKFILL_SOURCE_REPORTS["strategy_hypotheses_registry"]
    status = "RETIRED_FROM_EXECUTION" if (repo_root / source_path).exists() else "HISTORICAL_RESULT_MISSING"
    reasons = ("grid_archived_no_go", "runtime_disabled", "not_part_of_alpha_runner")
    return ResearchMemoryRecord(
        run_id="strategy_hypotheses_grid_no_go",
        hypothesis_id="grid",
        alpha_family_id="grid",
        template_id="dynamic_grid",
        created_at="2026-07-09T00:00:00+00:00",
        data_snapshot={"source": "strategy_hypotheses_registry"},
        parameters_tested={},
        variant_count=1,
        symbols_tested=(),
        gate_results=({"gate": "RUNTIME_POLICY", "status": status, "passed": False},),
        final_status=status,
        rejection_reasons=reasons,
        trial_count_for_family=1,
        trial_count_for_template=1,
        related_rejected_hypotheses=("grid", "dynamic_grid"),
        do_not_rerun_until=None,
        requires_new_data_before_rerun=True,
        source_report_path=str(source_path),
        source_report_status="available" if (repo_root / source_path).exists() else "source_report_not_found",
    )


def _missing_source_record(
    *,
    run_id: str,
    hypothesis_id: str,
    alpha_family_id: str,
    template_id: str,
    source_report_path: Path,
) -> ResearchMemoryRecord:
    return ResearchMemoryRecord(
        run_id=run_id,
        hypothesis_id=hypothesis_id,
        alpha_family_id=alpha_family_id,
        template_id=template_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        data_snapshot={},
        parameters_tested={},
        variant_count=1,
        symbols_tested=(),
        gate_results=({"gate": "SOURCE_REPORT_CHECK", "status": "HISTORICAL_RESULT_MISSING", "passed": False},),
        final_status="HISTORICAL_RESULT_MISSING",
        rejection_reasons=("source_report_not_found",),
        trial_count_for_family=1,
        trial_count_for_template=1,
        related_rejected_hypotheses=(hypothesis_id,),
        do_not_rerun_until=None,
        requires_new_data_before_rerun=True,
        source_report_path=str(source_report_path),
        source_report_status="source_report_not_found",
    )


def _build_adapter_backlog(
    *,
    templates: Mapping[str, Any],
    families: Mapping[str, Mapping[str, Any]],
    candidates: Sequence[ScheduledHypothesis],
    memory: AlphaResearchMemory,
    data: DataReadiness,
) -> tuple[AdapterBacklogItem, ...]:
    candidate_by_template = {item.template_id: item for item in candidates}
    family_counts = memory.trial_count_by_family()
    rejected = memory.rejected_hypotheses()
    backlog: list[AdapterBacklogItem] = []
    for template in templates.get("templates", ()):
        required_adapter = str(template["required_adapter"])
        if required_adapter in KNOWN_ADAPTERS:
            continue
        template_id = str(template["template_id"])
        adapter_id = required_adapter if required_adapter != "missing" else f"{template_id}_adapter"
        family_id = str(template["alpha_family_id"])
        family = families.get(family_id, {})
        candidate = candidate_by_template.get(template_id)
        required_data = set(str(item) for item in template.get("signal_inputs", ())) | set(str(item) for item in family.get("required_data", ()))
        missing = tuple(_missing_data_reasons(required_data, data, family))
        hypotheses_blocked = tuple(sorted(_hypotheses_for_template(family_id, template_id)))
        rejected_blockers = tuple(
            f"rejected_current_config:{hypothesis}"
            for hypothesis in hypotheses_blocked
            if hypothesis in rejected
        )
        data_ready = not missing
        complexity = _adapter_complexity(template, family, required_data)
        cpu_cost = _adapter_cpu_cost(template)
        reuse = _adapter_reuse_score(family_id, template_id, required_data)
        priority = _adapter_priority_score(
            data_ready=data_ready,
            missing=missing,
            complexity=complexity,
            cpu_cost=cpu_cost,
            reuse=reuse,
            family_trial_count=family_counts.get(family_id, 0),
            rejected_blockers=rejected_blockers,
            current_vps_suitable=bool(family.get("suitable_for_current_vps", False)),
            spot_only=not bool(family.get("requires_derivatives_data", False)),
        )
        blockers = tuple(dict.fromkeys((*missing, *rejected_blockers, *(candidate.blockers if candidate else ()))))
        backlog.append(
            AdapterBacklogItem(
                adapter_id=adapter_id,
                template_id=template_id,
                alpha_family_id=family_id,
                hypotheses_blocked=hypotheses_blocked,
                data_ready=data_ready,
                data_missing_reasons=missing,
                estimated_implementation_complexity=complexity,
                estimated_cpu_cost=cpu_cost,
                expected_trade_frequency=str(family.get("expected_trade_frequency") or "unknown"),
                current_vps_suitable=bool(family.get("suitable_for_current_vps", False)),
                expected_reuse_score=reuse,
                priority_score=priority,
                reason_for_priority=_adapter_priority_reason(data_ready, missing, complexity, cpu_cost, reuse, rejected_blockers),
                blockers=blockers,
            )
        )
    return tuple(sorted(backlog, key=lambda item: (-item.priority_score, item.template_id)))


def scan_data_readiness(data_paths: Sequence[Path]) -> DataReadiness:
    rows: list[tuple[str, str, str]] = []
    duplicate_count = 0
    seen: set[tuple[str, str, str]] = set()
    starts: list[str] = []
    ends: list[str] = []
    for path in _iter_csv_paths(data_paths):
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                timestamp = str(row.get("timestamp") or row.get("datetime") or row.get("time") or "").strip()
                symbol = str(row.get("symbol") or _symbol_from_filename(path)).strip().upper()
                timeframe = str(row.get("timeframe") or _timeframe_from_filename(path)).strip().lower()
                if not timestamp or not symbol or not timeframe:
                    continue
                key = (symbol, timeframe, timestamp)
                if key in seen:
                    duplicate_count += 1
                    continue
                seen.add(key)
                rows.append(key)
                starts.append(timestamp)
                ends.append(timestamp)
    symbols = tuple(sorted({symbol for symbol, _, _ in rows}))
    timeframes = tuple(sorted({timeframe for _, timeframe, _ in rows}))
    return DataReadiness(
        symbols=symbols,
        timeframes=timeframes,
        row_count=len(rows),
        duplicate_count=duplicate_count,
        gap_count=0,
        start_at=min(starts) if starts else None,
        end_at=max(ends) if ends else None,
        has_spot_ohlcv=bool(rows),
        has_multi_symbol_ohlcv=len(symbols) >= 2,
        has_5m="5m" in timeframes,
        has_15m="15m" in timeframes,
        has_1h="1h" in timeframes,
    )


def _schedule_template(
    *,
    template: Mapping[str, Any],
    family: Mapping[str, Any],
    hypothesis_id: str,
    data: DataReadiness,
    adapter_status: str,
    memory: AlphaResearchMemory,
    family_trial_count: int,
    template_trial_count: int,
    config: AlphaSchedulerConfig,
) -> ScheduledHypothesis:
    template_id = str(template["template_id"])
    family_id = str(family["alpha_family_id"])
    blockers: list[str] = []
    warnings: list[str] = []
    required_data = set(str(item) for item in template.get("signal_inputs", ())) | set(str(item) for item in family.get("required_data", ()))
    missing = _missing_data_reasons(required_data, data, family)
    blockers.extend(missing)
    if adapter_status != "READY":
        blockers.append("adapter_missing")
    if hypothesis_id in memory.rejected_hypotheses():
        blockers.append("rejected_current_config_requires_new_data")
    if int(template["max_variants"]) > config.max_variants:
        warnings.append("template_variants_clipped_by_scheduler")
    if int(template["max_symbols"]) > config.max_symbols:
        warnings.append("template_symbols_clipped_by_scheduler")
    if int(template["max_runtime_seconds"]) > config.max_runtime_seconds:
        warnings.append("template_runtime_clipped_by_scheduler")

    if "rejected_current_config_requires_new_data" in blockers:
        status = "REJECTED_CURRENT_CONFIG"
    elif any(
        (item.endswith("_missing") or item.startswith("missing_")) and item != "adapter_missing"
        for item in blockers
    ):
        status = "DATA_MISSING"
    elif "adapter_missing" in blockers:
        status = "ADAPTER_MISSING"
    elif family_trial_count >= 10 or template_trial_count >= 10:
        status = "WAITING_FOR_MORE_DATA"
        blockers.append("trial_count_penalty_requires_new_data")
    elif hypothesis_id == "volatility_breakout":
        status = "RUNNABLE_WALK_FORWARD"
    else:
        status = "RUNNABLE_SMOKE"

    priority = _priority_score(status, family_trial_count, template_trial_count, adapter_status, data, template)
    command = None
    if status in {"RUNNABLE_SMOKE", "RUNNABLE_WALK_FORWARD"}:
        mode = "smoke" if status == "RUNNABLE_SMOKE" else "walk_forward"
        command = _runner_command(hypothesis_id, mode, config, template)
    return ScheduledHypothesis(
        hypothesis_id=hypothesis_id,
        alpha_family_id=family_id,
        template_id=template_id,
        status=status,
        priority_score=priority,
        reason_for_priority=_reason_for_priority(status, blockers, family_trial_count, template_trial_count),
        next_action=_next_action(status),
        recommended_command=command,
        data_readiness=data.to_dict(),
        adapter_ready=adapter_status == "READY",
        trial_count_for_family=family_trial_count,
        trial_count_for_template=template_trial_count,
        estimated_cost=_cost_label(template),
        blockers=tuple(blockers),
        warnings=tuple(warnings),
    )


def _safe_load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _availability_for(payload: Mapping[str, Any], hypothesis_id: str) -> dict[str, Any]:
    for item in payload.get("availability", ()):
        if item.get("hypothesis_id") == hypothesis_id:
            return dict(item)
    return {}


def _metrics_from_gates(gates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for gate in gates:
        candidate = gate.get("metrics")
        if isinstance(candidate, Mapping):
            metrics = dict(candidate)
    return metrics


def _fold_results_from_gates(gates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    metrics = _metrics_from_gates(gates)
    by_period = metrics.get("by_period")
    if not isinstance(by_period, Mapping):
        return []
    return [
        {"period": str(period), **dict(values)}
        for period, values in by_period.items()
        if isinstance(values, Mapping)
    ]


def _variant_count_from_gate_dicts(gates: Sequence[Mapping[str, Any]]) -> int:
    count = 1
    for gate in gates:
        metrics = gate.get("metrics")
        if isinstance(metrics, Mapping) and metrics.get("variant_count") is not None:
            try:
                count = max(count, int(metrics["variant_count"]))
            except (TypeError, ValueError):
                pass
    return count


def _metrics_from_runner_report(report: AlphaHypothesisRunnerReport) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for gate in report.gates:
        metrics = dict(gate.metrics)
    return metrics


def _triage_status(strategy_name: str, item: Mapping[str, Any]) -> str:
    observed = str(item.get("observed_status") or item.get("requested_status") or "").lower()
    if strategy_name in {"grid", "relative_value"} or observed in {"archived", "no_go"}:
        return "NO_GO" if strategy_name == "relative_value" else "RETIRED_FROM_EXECUTION"
    if "redesign_required" in " ".join(str(value) for value in item.get("blockers", ())):
        return "BENCHMARK_REJECTED"
    if "profit_factor_below_candidate_threshold" in item.get("blockers", ()):
        return "BENCHMARK_REJECTED"
    return "RESEARCH_ONLY"


def _family_for_strategy(strategy_name: str) -> str:
    return {
        "trend_momentum": "trend_momentum",
        "mean_reversion": "mean_reversion",
        "relative_value": "relative_value",
        "grid": "grid",
    }.get(strategy_name, strategy_name)


def _template_for_strategy(strategy_name: str) -> str:
    return {
        "trend_momentum": "regime_filtered_trend",
        "mean_reversion": "volatility_reversal_after_extension",
        "relative_value": "relative_value_pair_spread",
        "grid": "dynamic_grid",
    }.get(strategy_name, strategy_name)


def _hypotheses_for_template(family_id: str, template_id: str) -> tuple[str, ...]:
    if family_id == "cross_sectional_momentum":
        return ("cross_momentum", f"cross_momentum__{template_id}")
    if family_id == "mean_reversion":
        return ("mean_reversion", f"mean_reversion__{template_id}")
    return (FAMILY_TO_HYPOTHESIS.get(family_id, family_id), f"{family_id}__{template_id}")


def _adapter_complexity(
    template: Mapping[str, Any],
    family: Mapping[str, Any],
    required_data: set[str],
) -> str:
    if required_data & DERIVATIVES_DATA or required_data & ORDERBOOK_DATA or required_data & NEWS_DATA:
        return "high"
    if int(template["max_runtime_seconds"]) > 180 or int(template["max_variants"]) > 3:
        return "medium"
    if bool(family.get("requires_derivatives_data")) or bool(family.get("requires_orderbook_data")):
        return "high"
    return "low"


def _adapter_cpu_cost(template: Mapping[str, Any]) -> str:
    seconds = int(template["max_runtime_seconds"])
    variants = int(template["max_variants"])
    if seconds >= 240 or variants > 4:
        return "M"
    return "L"


def _adapter_reuse_score(family_id: str, template_id: str, required_data: set[str]) -> float:
    score = 0.45
    if "spot_ohlcv_multi_symbol" in required_data:
        score += 0.25
    if family_id == "cross_sectional_momentum":
        score += 0.15
    if "fees_slippage" in required_data:
        score += 0.05
    if template_id == "leader_laggard_momentum":
        score += 0.05
    if required_data & (DERIVATIVES_DATA | ORDERBOOK_DATA | NEWS_DATA):
        score -= 0.2
    return round(max(0.0, min(1.0, score)), 4)


def _adapter_priority_score(
    *,
    data_ready: bool,
    missing: Sequence[str],
    complexity: str,
    cpu_cost: str,
    reuse: float,
    family_trial_count: int,
    rejected_blockers: Sequence[str],
    current_vps_suitable: bool,
    spot_only: bool,
) -> float:
    if not data_ready:
        return round(max(0.0, 20.0 - len(missing) * 5.0), 4)
    score = 45.0 + reuse * 35.0
    if complexity == "low":
        score += 12.0
    elif complexity == "medium":
        score += 6.0
    else:
        score -= 20.0
    if cpu_cost == "L":
        score += 8.0
    if current_vps_suitable:
        score += 8.0
    if spot_only:
        score += 6.0
    score -= min(25.0, family_trial_count * 3.0)
    score -= len(rejected_blockers) * 18.0
    return round(max(0.0, score), 4)


def _adapter_priority_reason(
    data_ready: bool,
    missing: Sequence[str],
    complexity: str,
    cpu_cost: str,
    reuse: float,
    rejected_blockers: Sequence[str],
) -> str:
    if not data_ready:
        return f"data missing: {', '.join(missing)}"
    parts = [
        "data-ready",
        f"{complexity}-complexity",
        f"cpu-{cpu_cost}",
        f"reuse={reuse:.2f}",
    ]
    if rejected_blockers:
        parts.append("penalized by rejected related config")
    return ", ".join(parts)


def _candidate_missing_family(template: Mapping[str, Any], data: DataReadiness) -> ScheduledHypothesis:
    return ScheduledHypothesis(
        hypothesis_id=str(template["alpha_family_id"]),
        alpha_family_id=str(template["alpha_family_id"]),
        template_id=str(template["template_id"]),
        status="DATA_MISSING",
        priority_score=0.0,
        reason_for_priority="template family is absent from knowledge base",
        next_action="fix_knowledge_base",
        recommended_command=None,
        data_readiness=data.to_dict(),
        adapter_ready=False,
        trial_count_for_family=0,
        trial_count_for_template=0,
        estimated_cost="unknown",
        blockers=("family_missing",),
    )


def _missing_data_reasons(required_data: set[str], data: DataReadiness, family: Mapping[str, Any]) -> list[str]:
    missing: list[str] = []
    if required_data & DERIVATIVES_DATA or bool(family.get("requires_derivatives_data")):
        missing.append("derivatives_data_missing")
    if required_data & ORDERBOOK_DATA or bool(family.get("requires_orderbook_data")):
        missing.append("orderbook_data_missing")
    if required_data & NEWS_DATA or bool(family.get("requires_news_data")):
        missing.append("news_data_missing")
    if required_data & OHLCV_DATA and not data.has_spot_ohlcv:
        missing.append("spot_ohlcv_missing")
    if "spot_ohlcv_multi_symbol" in required_data and not data.has_multi_symbol_ohlcv:
        missing.append("multi_symbol_ohlcv_missing")
    if "multi_timeframe_trend" in required_data and not data.has_1h:
        missing.append("one_hour_ohlcv_missing")
    if "range_compression" in required_data and not (data.has_15m and data.has_1h):
        missing.append("multi_timeframe_ohlcv_missing")
    return list(dict.fromkeys(missing))


def _adapter_readiness(templates: Mapping[str, Any]) -> dict[str, str]:
    readiness: dict[str, str] = {}
    for template in templates.get("templates", ()):
        adapter = str(template["required_adapter"])
        readiness[str(template["template_id"])] = "READY" if adapter in KNOWN_ADAPTERS else "ADAPTER_MISSING"
    return readiness


def _priority_score(
    status: str,
    family_trials: int,
    template_trials: int,
    adapter_status: str,
    data: DataReadiness,
    template: Mapping[str, Any],
) -> float:
    if status in {"REJECTED_CURRENT_CONFIG", "DATA_MISSING", "ADAPTER_MISSING", "HUMAN_REVIEW_REQUIRED"}:
        return 0.0
    score = 100.0
    if adapter_status == "READY":
        score += 20.0
    if data.has_spot_ohlcv:
        score += 10.0
    score -= min(40.0, family_trials * 4.0)
    score -= min(30.0, template_trials * 5.0)
    score -= max(0, int(template["max_variants"]) - 3) * 2.0
    score -= max(0, int(template["max_runtime_seconds"]) - 120) / 30.0
    return round(max(score, 0.0), 4)


def _reason_for_priority(status: str, blockers: Sequence[str], family_trials: int, template_trials: int) -> str:
    if blockers:
        return ", ".join(blockers)
    if status.startswith("RUNNABLE"):
        return f"data-ready, adapter-ready, family_trials={family_trials}, template_trials={template_trials}"
    return status.lower()


def _next_action(status: str) -> str:
    return {
        "REJECTED_CURRENT_CONFIG": "wait_for_new_data_or_new_thesis",
        "DATA_MISSING": "collect_required_data_or_mark_not_suitable",
        "ADAPTER_MISSING": "write_adapter_before_testing",
        "RUNNABLE_SMOKE": "run_alpha_hypothesis_runner_smoke",
        "RUNNABLE_WALK_FORWARD": "run_alpha_hypothesis_runner_walk_forward",
        "WAITING_FOR_MORE_DATA": "wait_for_more_data",
        "HUMAN_REVIEW_REQUIRED": "prepare_review_package",
    }.get(status, "no_action")


def _runner_command(
    hypothesis_id: str,
    mode: str,
    config: AlphaSchedulerConfig,
    template: Mapping[str, Any],
) -> str:
    max_variants = min(config.max_variants, int(template["max_variants"]))
    max_symbols = min(config.max_symbols, int(template["max_symbols"]))
    max_runtime = min(config.max_runtime_seconds, int(template["max_runtime_seconds"]))
    return (
        "python -m autobot.v2.cli alpha-hypothesis-runner "
        f"--hypothesis-id {hypothesis_id} "
        f"--mode {mode} "
        f"--state-db {config.state_db or 'data/autobot_state.db'} "
        f"--data-paths {','.join(str(path) for path in config.data_paths)} "
        f"--output-dir {config.output_dir} "
        f"--max-variants {max_variants} "
        f"--max-symbols {max_symbols} "
        f"--max-runtime-seconds {max_runtime}"
    )


def _cost_label(template: Mapping[str, Any]) -> str:
    seconds = int(template["max_runtime_seconds"])
    variants = int(template["max_variants"])
    if seconds > 240 or variants > 4:
        return "medium"
    return "low"


def _memory_final_status(status: str) -> str:
    if status == "REJECT":
        return "REJECTED"
    return status


def _is_rejected_status(status: str) -> bool:
    return status in {"REJECT", "REJECTED", "REJECT_FAST", "DATA_MISSING"}


def _variant_count_from_report(report: AlphaHypothesisRunnerReport) -> int:
    count = 1
    for gate in report.gates:
        variant = gate.metrics.get("variant_count")
        if variant is not None:
            try:
                count = max(count, int(variant))
            except (TypeError, ValueError):
                pass
    return count


def _with_running_counts(records: Sequence[ResearchMemoryRecord]) -> list[ResearchMemoryRecord]:
    family_counts: Counter[str] = Counter()
    template_counts: Counter[str] = Counter()
    updated: list[ResearchMemoryRecord] = []
    for record in records:
        family_counts[record.alpha_family_id] += max(1, record.variant_count)
        template_counts[record.template_id] += max(1, record.variant_count)
        updated.append(
            replace(
                record,
                trial_count_for_family=family_counts[record.alpha_family_id],
                trial_count_for_template=template_counts[record.template_id],
            )
        )
    return updated


def _iter_csv_paths(paths: Sequence[Path]) -> Iterable[Path]:
    for path in paths:
        if path.is_dir():
            yield from sorted(path.rglob("*.csv"))
        elif path.suffix.lower() == ".csv" and path.exists():
            yield path


def _symbol_from_filename(path: Path) -> str:
    return path.stem.split("_")[0].upper()


def _timeframe_from_filename(path: Path) -> str:
    parts = path.stem.split("_")
    for part in reversed(parts):
        if part.lower() in {"1m", "5m", "15m", "1h", "4h"}:
            return part.lower()
    return "unknown"


def _load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise AlphaSchedulerError(f"{path} must contain a JSON object")
    return payload


def _validate_root_research_only(payload: Mapping[str, Any], label: str) -> None:
    if bool(payload.get("paper_capital_allowed")) or bool(payload.get("live_allowed")):
        raise AlphaSchedulerError(f"{label} cannot allow paper/live")
    if payload.get("free_code_generation_allowed") is not False:
        raise AlphaSchedulerError(f"{label} must disable free code generation")


def _require_fields(payload: Mapping[str, Any], fields: Sequence[str], label: str) -> None:
    missing = [field for field in fields if field not in payload]
    if missing:
        raise AlphaSchedulerError(f"{label} missing fields: {', '.join(missing)}")
