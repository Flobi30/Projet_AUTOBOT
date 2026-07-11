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
from .data_capability_scanner import build_data_capability_scan_report
from .research_memory_store import ResearchMemoryStore


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
    "generic_cross_sectional_ohlcv_adapter": "alpha-hypothesis-runner",
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

DEFAULT_RESEARCH_MEMORY_PATH = Path("data/research/alpha_research_memory.sqlite3")
LEGACY_RESEARCH_MEMORY_PATH = Path("reports/research/alpha_research_memory.json")


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
    adapter_id: str | None = None
    mode_used: str | None = None

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
            adapter_id=payload.get("adapter_id"),
            mode_used=payload.get("mode_used"),
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
                template_specific = any(
                    item.startswith(f"{record.hypothesis_id}__")
                    for item in record.related_rejected_hypotheses
                )
                if not template_specific:
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
        if target.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
            ResearchMemoryStore(target).append_many(record.to_dict() for record in self.records)
            return
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
    memory_path: Path = DEFAULT_RESEARCH_MEMORY_PATH
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
    data_capabilities: dict[str, Any]
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
    promotabl×~:ÞÚ$z{-®éÜj×        status = "RUNNABLE_WALK_FORWARD"
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
        f"--max-runtime-seconds {max_runtime} "
        f"--template-id {template['template_id']}"
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


def _related_rejected_hypotheses(report: AlphaHypothesisRunnerReport, template_id: str) -> tuple[str, ...]:
    if not _is_rejected_status(report.final_status):
        return ()
    if report.hypothesis_id == "cross_momentum":
        return (f"{report.hypothesis_id}__{template_id}",)
    return (report.hypothesis_id,)


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
