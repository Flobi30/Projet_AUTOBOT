"""Fail-closed coordinator for one bounded AUTOBOT research experiment.

The daily scheduler deliberately only ranks possible hypotheses.  This module
is the narrow, auditable bridge from that ranking to one *research-only* smoke
experiment.  It does not execute scheduler command strings, import a runtime
order path, change policy, or enable shadow, paper, or live trading.

The coordinator is intentionally conservative:

* exactly one pre-approved smoke template may run per invocation;
* a verified point-in-time feature manifest is mandatory;
* the material experiment fingerprint is registered before calculation;
* a terminal fingerprint can never be re-run;
* every other scheduler result fails closed with an explanatory report.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .alpha_hypothesis_lab import RESEARCH_ONLY_CAPITAL_FLAGS, load_alpha_hypotheses
from .alpha_hypothesis_runner import (
    AlphaHypothesisRunnerConfig,
    AlphaHypothesisRunnerReport,
    build_alpha_hypothesis_runner_report,
    canonical_hypothesis_id,
    write_alpha_hypothesis_runner_report,
)
from .alpha_hypothesis_scheduler import (
    AlphaSchedulerConfig,
    AlphaSchedulerReport,
    build_alpha_hypothesis_scheduler_report,
    load_strategy_templates,
    record_alpha_runner_trial,
)
from .experiment_registry import ExperimentRegistry
from .manifested_experiment import (
    FeatureSnapshotProvenance,
    ManifestedExperimentError,
    build_manifested_experiment_spec,
)


# Only the generic cross-sectional adapter is safe for unattended *smoke*
# research today.  It is bounded, long-only/research-only, and has no order
# dependency.  Other families remain manually reviewed until their data and
# validation contracts are mature enough for an equivalent allowlist entry.
AUTOMATED_SMOKE_TEMPLATE_IDS = frozenset(
    {
        "leader_laggard_momentum",
        "relative_strength_rotation",
    }
)
AUTOMATED_SMOKE_HYPOTHESIS_IDS = frozenset({"cross_momentum"})
DEFAULT_COORDINATOR_OUTPUT_DIR = Path("data/research/reports/bounded_research_coordinator")


@dataclass(frozen=True)
class BoundedResearchCoordinatorConfig:
    """Inputs for one fail-closed research-only coordination cycle."""

    run_id: str
    scheduler: AlphaSchedulerConfig
    feature_snapshot_manifest: Path
    code_commit: str
    image_commit: str
    output_dir: Path = DEFAULT_COORDINATOR_OUTPUT_DIR
    memory_path: Path = Path("data/research/alpha_research_memory.sqlite3")
    experiment_registry_path: Path = Path("data/research/experiment_registry.sqlite3")
    seed: int = 0
    max_experiments: int = 1
    allowed_template_ids: frozenset[str] = field(default_factory=lambda: AUTOMATED_SMOKE_TEMPLATE_IDS)

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id is required")
        if not self.code_commit.strip() or not self.image_commit.strip():
            raise ValueError("code_commit and image_commit are required")
        if self.max_experiments != 1:
            raise ValueError("bounded research coordinator permits exactly one experiment per invocation")
        if not self.allowed_template_ids:
            raise ValueError("at least one approved research template is required")
        if not set(self.allowed_template_ids).issubset(AUTOMATED_SMOKE_TEMPLATE_IDS):
            raise ValueError("coordinator allowlist contains an unapproved template")
        if self.seed < 0:
            raise ValueError("seed cannot be negative")


@dataclass(frozen=True)
class BoundedResearchCoordinatorReport:
    run_id: str
    generated_at: str
    code_commit: str
    image_commit: str
    image_provenance_verified: bool
    decision: str
    reasons: tuple[str, ...]
    scheduler_report: AlphaSchedulerReport
    selected_hypothesis_id: str | None = None
    selected_template_id: str | None = None
    feature_snapshot: Mapping[str, Any] | None = None
    experiment_registry_state: Mapping[str, Any] | None = None
    runner_report: AlphaHypothesisRunnerReport | None = None
    json_report_path: str | None = None
    markdown_report_path: str | None = None
    paper_capital_allowed: bool = False
    live_allowed: bool = False
    promotable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "code_commit": self.code_commit,
            "image_commit": self.image_commit,
            "image_provenance_verified": self.image_provenance_verified,
            "decision": self.decision,
            "reasons": list(self.reasons),
            "scheduler_report": self.scheduler_report.to_dict(),
            "selected_hypothesis_id": self.selected_hypothesis_id,
            "selected_template_id": self.selected_template_id,
            "feature_snapshot": dict(self.feature_snapshot or {}),
            "experiment_registry_state": dict(self.experiment_registry_state or {}),
            "runner_report": self.runner_report.to_dict() if self.runner_report else None,
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
            "research_only": True,
            "paper_capital_allowed": self.paper_capital_allowed,
            "live_allowed": self.live_allowed,
            "promotable": self.promotable,
        }


def run_bounded_research_coordinator(
    config: BoundedResearchCoordinatorConfig,
) -> BoundedResearchCoordinatorReport:
    """Run at most one allowlisted smoke experiment, otherwise fail closed.

    ``ScheduledHypothesis.recommended_command`` is deliberately never parsed
    or launched.  All runner inputs are reconstructed from typed scheduler,
    template, hypothesis and manifest evidence.
    """

    scheduler_report = build_alpha_hypothesis_scheduler_report(config.scheduler)
    selected = scheduler_report.selected
    base = _base_report(config, scheduler_report)
    if config.image_commit != config.code_commit:
        return replace(
            base,
            decision="BLOCKED_IMAGE_PROVENANCE_MISMATCH",
            reasons=("image_commit_does_not_match_declared_code_commit",),
        )
    if selected is None:
        return replace(base, decision="NO_RUNNABLE_CANDIDATE", reasons=("scheduler_selected_no_runnable_smoke",))
    if selected.status != "RUNNABLE_SMOKE":
        return replace(
            base,
            decision="BLOCKED_BY_SCHEDULER_STATUS",
            selected_hypothesis_id=selected.hypothesis_id,
            selected_template_id=selected.template_id,
            reasons=(f"scheduler_status_{selected.status.lower()}",),
        )
    if selected.hypothesis_id not in AUTOMATED_SMOKE_HYPOTHESIS_IDS:
        return replace(
            base,
            decision="BLOCKED_HYPOTHESIS_NOT_ALLOWLISTED",
            selected_hypothesis_id=selected.hypothesis_id,
            selected_template_id=selected.template_id,
            reasons=("automated_hypothesis_not_allowlisted",),
        )
    if selected.template_id not in config.allowed_template_ids:
        return replace(
            base,
            decision="BLOCKED_TEMPLATE_NOT_ALLOWLISTED",
            selected_hypothesis_id=selected.hypothesis_id,
            selected_template_id=selected.template_id,
            reasons=("automated_template_not_allowlisted",),
        )

    try:
        template, hypothesis, spec, provenance = _build_material_experiment(
            config=config,
            hypothesis_id=selected.hypothesis_id,
            template_id=selected.template_id,
        )
    except (ManifestedExperimentError, ValueError) as exc:
        return replace(
            base,
            decision="BLOCKED_INVALID_PROVENANCE",
            selected_hypothesis_id=selected.hypothesis_id,
            selected_template_id=selected.template_id,
            reasons=(str(exc),),
        )

    registry = ExperimentRegistry(config.experiment_registry_path)
    state = registry.register_experiment(spec)
    common = {
        "selected_hypothesis_id": selected.hypothesis_id,
        "selected_template_id": selected.template_id,
        "feature_snapshot": provenance.to_dict(),
        "experiment_registry_state": state.to_dict(),
    }
    if state.terminal:
        return replace(
            base,
            decision="SKIPPED_TERMINAL_MATERIAL_EXPERIMENT",
            reasons=("material_fingerprint_already_terminal", "new_data_thesis_or_template_required"),
            **common,
        )
    if state.latest_stage is not None:
        return replace(
            base,
            decision="SKIPPED_MATERIAL_EXPERIMENT_ALREADY_ADVANCED",
            reasons=("material_fingerprint_already_has_gate_evidence", "new_data_thesis_or_template_required"),
            **common,
        )
    if not registry.claim_bounded_research_snapshot(
        feature_snapshot_id=provenance.feature_snapshot_id,
        feature_snapshot_fingerprint=provenance.feature_snapshot_fingerprint,
        coordinator_run_id=config.run_id,
    ):
        return replace(
            base,
            decision="SKIPPED_FEATURE_SNAPSHOT_ALREADY_CLAIMED",
            reasons=("feature_snapshot_already_has_bounded_research_attempt", "new_snapshot_required"),
            **common,
        )
    if not registry.claim_bounded_research_execution(
        experiment_id=state.experiment_id,
        coordinator_run_id=config.run_id,
    ):
        return replace(
            base,
            decision="SKIPPED_DUPLICATE_MATERIAL_FINGERPRINT",
            reasons=("bounded_execution_already_claimed", "new_data_thesis_or_template_required"),
            **common,
        )

    symbols = _bounded_symbols(hypothesis, maximum=min(config.scheduler.max_symbols, int(template["max_symbols"])))
    timeframes = _bounded_text(hypothesis.get("timeframe"))
    registry.record_trial_plan(
        experiment_id=state.experiment_id,
        variant_count=min(config.scheduler.max_variants, int(template["max_variants"])),
        symbols=symbols,
        timeframes=timeframes,
    )
    trial_floor = registry.validation_trial_count(
        hypothesis_id=spec.hypothesis_id,
        research_campaign_id=spec.research_campaign_id,
    )
    try:
        runner = write_alpha_hypothesis_runner_report(
            build_alpha_hypothesis_runner_report(
                AlphaHypothesisRunnerConfig(
                    run_id=f"{config.run_id}_{selected.hypothesis_id}_{selected.template_id}",
                    hypothesis_id=selected.hypothesis_id,
                    mode="smoke",
                    hypotheses_path=config.scheduler.hypotheses_path,
                    templates_path=config.scheduler.templates_path,
                    template_id=selected.template_id,
                    state_db=None,
                    data_paths=config.scheduler.data_paths,
                    output_dir=config.output_dir / "runner",
                    symbols=symbols,
                    cost_profile=str(template["expected_cost_model"]),
                    max_runtime_seconds=min(
                        float(config.scheduler.max_runtime_seconds), float(template["max_runtime_seconds"])
                    ),
                    max_variants=min(config.scheduler.max_variants, int(template["max_variants"])),
                    max_symbols=min(config.scheduler.max_symbols, int(template["max_symbols"])),
                    validation_trial_count_floor=trial_floor,
                    feature_snapshot_manifest=config.feature_snapshot_manifest,
                ),
                commit=config.code_commit,
            ),
            config.output_dir / "runner",
        )
        record_alpha_runner_trial(
            runner,
            memory_path=config.memory_path,
            template_id=str(template["template_id"]),
            alpha_family_id=str(template["alpha_family_id"]),
        )
        state = registry.record_runner_evidence(
            spec=spec,
            report=runner,
            variant_count=min(config.scheduler.max_variants, int(template["max_variants"])),
            symbols=symbols,
            timeframes=timeframes,
            record_trial_dimensions=False,
        )
    except Exception as exc:
        # The immutable snapshot/execution claims stay in place deliberately.
        # An interrupted or invalid run must be reviewed, not silently retried
        # against the same point-in-time data.
        return replace(
            base,
            decision="RESEARCH_RUNNER_ERROR_LOCKED",
            reasons=(f"{type(exc).__name__}:{exc}", "same_snapshot_retry_is_blocked"),
            selected_hypothesis_id=selected.hypothesis_id,
            selected_template_id=selected.template_id,
            feature_snapshot=provenance.to_dict(),
            experiment_registry_state=registry.get_state(state.experiment_id).to_dict(),
        )
    return replace(
        base,
        decision="RESEARCH_SMOKE_COMPLETED",
        reasons=("one_allowlisted_smoke_experiment_completed",),
        runner_report=runner,
        experiment_registry_state=state.to_dict(),
        selected_hypothesis_id=selected.hypothesis_id,
        selected_template_id=selected.template_id,
        feature_snapshot=provenance.to_dict(),
    )


def write_bounded_research_coordinator_report(
    report: BoundedResearchCoordinatorReport,
    output_dir: str | Path,
) -> BoundedResearchCoordinatorReport:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / f"{report.run_id}.json"
    markdown_path = output / f"{report.run_id}.md"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(render_bounded_research_coordinator_report(report), encoding="utf-8")
    return replace(report, json_report_path=str(json_path), markdown_report_path=str(markdown_path))


def render_bounded_research_coordinator_report(report: BoundedResearchCoordinatorReport) -> str:
    lines = [
        f"# Bounded Research Coordinator - {report.run_id}",
        "",
        "## Scope",
        "",
        "- One allowlisted research-only smoke experiment at most.",
        "- Scheduler command text is never executed.",
        "- No runtime order path, shadow activation, paper capital, live activation, promotion, sizing, leverage, or UI change.",
        f"- Commit: `{report.code_commit}`.",
        f"- Image commit: `{report.image_commit}`.",
        f"- Image provenance verified: `{str(report.image_provenance_verified).lower()}`.",
        f"- Decision: `{report.decision}`.",
        "",
        "## Selection",
        "",
        f"- Hypothesis: `{report.selected_hypothesis_id or 'none'}`.",
        f"- Template: `{report.selected_template_id or 'none'}`.",
        f"- Reasons: `{', '.join(report.reasons) or 'none'}`.",
        "",
        "## Safety",
        "",
        "- research_only: `true`",
        "- paper_capital_allowed: `false`",
        "- live_allowed: `false`",
        "- promotable: `false`",
    ]
    if report.feature_snapshot:
        lines.extend(["", "## Feature Provenance", ""])
        for key in ("feature_snapshot_id", "source_snapshot_id", "feature_snapshot_fingerprint", "runtime_parity_proven"):
            lines.append(f"- `{key}`: `{report.feature_snapshot.get(key)}`")
    if report.experiment_registry_state:
        lines.extend(["", "## Experiment Registry", ""])
        for key in ("experiment_id", "latest_stage", "latest_status", "terminal", "trial_count"):
            lines.append(f"- `{key}`: `{report.experiment_registry_state.get(key)}`")
    if report.runner_report:
        lines.extend(["", "## Runner", ""])
        lines.append(f"- Final status: `{report.runner_report.final_status}`")
        lines.append(f"- Final decision: `{report.runner_report.final_decision}`")
    return "\n".join(lines) + "\n"


def _base_report(
    config: BoundedResearchCoordinatorConfig,
    scheduler_report: AlphaSchedulerReport,
) -> BoundedResearchCoordinatorReport:
    return BoundedResearchCoordinatorReport(
        run_id=config.run_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        code_commit=config.code_commit,
        image_commit=config.image_commit,
        image_provenance_verified=config.image_commit == config.code_commit,
        decision="BLOCKED",
        reasons=(),
        scheduler_report=scheduler_report,
    )


def _build_material_experiment(
    *,
    config: BoundedResearchCoordinatorConfig,
    hypothesis_id: str,
    template_id: str,
) -> tuple[dict[str, Any], dict[str, Any], Any, FeatureSnapshotProvenance]:
    resolved_hypothesis_id = canonical_hypothesis_id(hypothesis_id)
    templates = load_strategy_templates(config.scheduler.templates_path)
    template = next(
        (
            dict(item)
            for item in templates["templates"]
            if str(item.get("template_id")) == template_id
            and str(item.get("alpha_family_id")) == "cross_sectional_momentum"
            and str(item.get("required_adapter")) == "generic_cross_sectional_ohlcv_adapter"
        ),
        None,
    )
    if template is None:
        raise ValueError("allowlisted template is not a registered generic cross-sectional template")
    hypotheses = load_alpha_hypotheses(config.scheduler.hypotheses_path)
    hypothesis = next(
        (dict(item) for item in hypotheses["hypotheses"] if str(item.get("id")) == resolved_hypothesis_id),
        None,
    )
    if hypothesis is None:
        raise ValueError(f"hypothesis metadata missing for {resolved_hypothesis_id}")
    max_variants = min(config.scheduler.max_variants, int(template["max_variants"]))
    max_symbols = min(config.scheduler.max_symbols, int(template["max_symbols"]))
    symbols = _bounded_symbols(hypothesis, maximum=max_symbols)
    spec, provenance = build_manifested_experiment_spec(
        hypothesis_id=resolved_hypothesis_id,
        template_id=template_id,
        thesis=str(hypothesis["thesis"]),
        code_commit=config.code_commit,
        image_ref=f"oci-revision:{config.image_commit}",
        feature_snapshot_manifest=config.feature_snapshot_manifest,
        parameters={
            "coordinator": "bounded_research_coordinator_v1",
            "mode": "smoke",
            "max_variants": max_variants,
            "max_symbols": max_symbols,
            "symbols": list(symbols),
            "timeframes": list(_bounded_text(hypothesis.get("timeframe"))),
        },
        seed=config.seed,
        cost_model={"profile": str(template["expected_cost_model"])},
        environment={
            "data_paths": [str(path) for path in config.scheduler.data_paths],
            "scheduler_run_id": config.scheduler.run_id,
            **RESEARCH_ONLY_CAPITAL_FLAGS,
        },
        research_campaign_id=f"family_{str(template['alpha_family_id']).strip().lower()}",
    )
    if not provenance.runtime_parity_proven:
        raise ManifestedExperimentError("runtime parity must be proven before automated research smoke")
    return template, hypothesis, spec, provenance


def _bounded_symbols(hypothesis: Mapping[str, Any], *, maximum: int) -> tuple[str, ...]:
    values = _bounded_text(hypothesis.get("symbols"))
    if not values:
        raise ValueError("hypothesis symbols are required")
    return tuple(value.upper() for value in values[:maximum])


def _bounded_text(value: Any) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())
