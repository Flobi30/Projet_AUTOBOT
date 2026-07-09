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
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["symbols_tested"] = list(self.symbols_tested)
        payload["gate_results"] = [dict(item) for item in self.gate_results]
        payload["rejection_reasons"] = list(self.rejection_reasons)
        payload["related_rejected_hypotheses"] = list(self.related_rejected_hypotheses)
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
            if record.final_status in {"REJECT", "REJECTED", "REJECT_FAST", "DATA_MISSING"}:
                rejected.add(record.hypothesis_id)
                rejected.update(record.related_rejected_hypotheses)
        return rejected

    def add_record(self, record: ResearchMemoryRecord) -> "AlphaResearchMemory":
        records = [*self.records, record]
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
    next_runner_command: str | None
    safety_notes: tuple[str, ...]
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
            "next_runner_command": self.next_runner_command,
            "safety_notes": list(self.safety_notes),
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
    )
    updated = memory.add_record(record)
    updated.write(memory_path)
    return updated.records[-1]


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
    lines.extend(["", "## Trial Counts", ""])
    lines.append(f"- By family: `{report.trial_counts_by_family}`")
    lines.append(f"- By template: `{report.trial_counts_by_template}`")
    lines.extend(["", "## Safety", ""])
    lines.extend(f"- {note}" for note in report.safety_notes)
    lines.append(f"- paper_capital_allowed: `{report.paper_capital_allowed}`")
    lines.append(f"- live_allowed: `{report.live_allowed}`")
    lines.append(f"- promotable: `{report.promotable}`")
    return "\n".join(lines) + "\n"


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
