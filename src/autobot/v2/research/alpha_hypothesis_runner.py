"""Research-only Alpha Hypothesis Runner.

The runner is the durable P18C orchestration layer.  It advances hypotheses
through bounded research gates and stops on failures or human-review gates. It
never touches runtime trading, paper capital, live activation, or order paths.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .alpha_hypothesis_lab import RESEARCH_ONLY_CAPITAL_FLAGS, load_alpha_hypotheses
from .alpha_smoke_runner import AlphaSmokeConfig, build_alpha_smoke_report
from .generic_cross_sectional_ohlcv_adapter import (
    ADAPTER_ID as GENERIC_CROSS_SECTIONAL_ADAPTER_ID,
    GenericCrossSectionalConfig,
    build_cross_sectional_availability,
    load_cross_sectional_bars,
    run_generic_cross_sectional_ohlcv_smoke,
)
from .funding_basis_research_adapter import (
    ADAPTER_ID as FUNDING_BASIS_ADAPTER_ID,
    FundingBasisResearchConfig,
    run_funding_basis_research_smoke,
)
from .funding_basis_walk_forward import (
    FundingBasisWalkForwardConfig,
    build_funding_basis_walk_forward_report,
)
from .volatility_breakout_walk_forward import (
    VolatilityBreakoutWalkForwardConfig,
    build_volatility_breakout_walk_forward_report,
)


AUTO_ALLOWED = "AUTO_ALLOWED"
HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"
CANONICAL_ALIASES = {
    "volatility_breakout_high_conviction": "volatility_breakout",
}
MODE_STAGE_LIMITS = {
    "data_check": "DATA_CHECK",
    "smoke": "FAST_NET_EDGE_TEST",
    "walk_forward": "WALK_FORWARD",
    "full_research": "STRESS_MONTE_CARLO",
}
STAGE_ORDER = (
    "DATA_CHECK",
    "FAST_NET_EDGE_TEST",
    "WALK_FORWARD",
    "STRESS_MONTE_CARLO",
    "SHADOW_REVIEW_CANDIDATE",
)
SMOKE_ADAPTER_IDS = {
    "volatility_breakout": "volatility_breakout_high_conviction",
    "long_trend": "long_timeframe_adaptive_trend",
    "cross_momentum": GENERIC_CROSS_SECTIONAL_ADAPTER_ID,
}
MISSING_DATA_IDS = {"liquidation_cascade"}
FUNDING_BASIS_REQUIRED_DERIVATIVES_FEATURES = {"funding_rate_relative", "basis_bps"}


@dataclass(frozen=True)
class AlphaHypothesisRunnerConfig:
    run_id: str
    hypothesis_id: str
    mode: str
    hypotheses_path: Path = Path("docs/research/alpha_hypotheses.json")
    autonomy_policy_path: Path = Path("docs/research/alpha_autonomy_policy.json")
    templates_path: Path = Path("docs/research/strategy_templates.json")
    template_id: str | None = None
    state_db: Path | None = None
    data_paths: tuple[Path, ...] = ()
    output_dir: Path = Path("reports/research/alpha_hypothesis_runner")
    symbols: tuple[str, ...] = ("BTCZEUR", "ETHZEUR", "BCHEUR", "ADAEUR", "XRPZEUR", "SOLEUR")
    cost_profile: str = "research_stress"
    max_runtime_seconds: float = 120.0
    max_variants: int = 5
    max_symbols: int = 6
    max_data_rows: int = 250_000
    feature_snapshot_manifest: Path | None = None
    derivatives_feature_snapshot_manifest: Path | None = None

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id is required")
        if self.mode not in MODE_STAGE_LIMITS:
            raise ValueError(f"unsupported alpha runner mode: {self.mode}")
        if self.max_runtime_seconds <= 0.0:
            raise ValueError("max_runtime_seconds must be positive")
        if self.max_variants <= 0 or self.max_variants > 5:
            raise ValueError("max_variants must be between 1 and 5")
        if self.max_symbols <= 0 or self.max_symbols > 14:
            raise ValueError("max_symbols must be between 1 and 14")
        if self.max_data_rows <= 0:
            raise ValueError("max_data_rows must be positive")


@dataclass(frozen=True)
class AlphaGateResult:
    gate: str
    status: str
    passed: bool
    stopped: bool
    reasons: tuple[str, ...]
    autonomy_level: str
    risk_direction: str
    requires_human_approval: bool
    runtime_seconds: float
    metrics: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    safety: dict[str, bool] = field(default_factory=lambda: dict(RESEARCH_ONLY_CAPITAL_FLAGS))

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate": self.gate,
            "status": self.status,
            "passed": self.passed,
            "stopped": self.stopped,
            "reasons": list(self.reasons),
            "autonomy_level": self.autonomy_level,
            "risk_direction": self.risk_direction,
            "requires_human_approval": self.requires_human_approval,
            "runtime_seconds": self.runtime_seconds,
            "metrics": self.metrics,
            "artifacts": self.artifacts,
            "safety": dict(self.safety),
        }


@dataclass(frozen=True)
class AlphaHypothesisRunnerReport:
    run_id: str
    generated_at: str
    commit: str | None
    hypothesis_id: str
    requested_hypothesis_id: str
    mode: str
    state_db: str | None
    data_paths: tuple[str, ...]
    gates: tuple[AlphaGateResult, ...]
    final_status: str
    next_allowed_stage: str | None
    final_decision: str
    reasons: tuple[str, ...]
    autonomy_policy_summary: dict[str, Any]
    runtime_seconds: float
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
            "commit": self.commit,
            "hypothesis_id": self.hypothesis_id,
            "requested_hypothesis_id": self.requested_hypothesis_id,
            "mode": self.mode,
            "state_db": self.state_db,
            "data_paths": list(self.data_paths),
            "gates": [gate.to_dict() for gate in self.gates],
            "final_status": self.final_status,
            "next_allowed_stage": self.next_allowed_stage,
            "final_decision": self.final_decision,
            "reasons": list(self.reasons),
            "autonomy_policy_summary": dict(self.autonomy_policy_summary),
            "runtime_seconds": self.runtime_seconds,
            "safety_notes": list(self.safety_notes),
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
            "paper_capital_allowed": self.paper_capital_allowed,
            "live_allowed": self.live_allowed,
            "promotable": self.promotable,
        }


def build_alpha_hypothesis_runner_report(
    config: AlphaHypothesisRunnerConfig,
    *,
    commit: str | None = None,
) -> AlphaHypothesisRunnerReport:
    started = time.perf_counter()
    report_commit = commit or _current_git_commit()
    policy = load_alpha_autonomy_policy(config.autonomy_policy_path)
    registry = load_alpha_hypotheses(config.hypotheses_path)
    hypothesis_id = canonical_hypothesis_id(config.hypothesis_id)
    hypothesis = _find_hypothesis(registry, hypothesis_id)
    gates: list[AlphaGateResult] = []
    final_status = "IDEA"
    final_decision = "KEEP_RESEARCH"
    reasons: list[str] = []
    max_stage = MODE_STAGE_LIMITS[config.mode]

    for stage in STAGE_ORDER:
        if time.perf_counter() - started > config.max_runtime_seconds:
            gates.append(_gate(stage, "REJECTED", False, True, ["max_runtime_seconds_exceeded"], policy, started))
            final_status = "REJECTED"
            final_decision = "STOPPED"
            reasons.append("max_runtime_seconds_exceeded")
            break
        gate_policy = gate_policy_for(policy, stage)
        if gate_policy["requires_human_approval"]:
            gates.append(_gate(stage, "HUMAN_REVIEW_REQUIRED", False, True, ["stage_requires_human_review"], policy, started))
            final_status = "SHADOW_REVIEW_LATER"
            final_decision = "HUMAN_REVIEW_REQUIRED"
            reasons.append("stage_requires_human_review")
            break
        if stage == "DATA_CHECK":
            result = _data_check(config, hypothesis, policy, started)
        elif stage == "FAST_NET_EDGE_TEST":
            result = _fast_net_edge_test(config, hypothesis_id, policy, started, report_commit)
        elif stage == "WALK_FORWARD":
            result = _walk_forward(config, hypothesis_id, policy, started, report_commit)
        elif stage == "STRESS_MONTE_CARLO":
            result = _stress_placeholder(policy, started)
        else:
            result = _gate(stage, "HUMAN_REVIEW_REQUIRED", False, True, ["stage_requires_human_review"], policy, started)
        gates.append(result)
        if not result.passed or result.stopped:
            final_status = result.status
            final_decision = "STOPPED" if result.status != "HUMAN_REVIEW_REQUIRED" else "HUMAN_REVIEW_REQUIRED"
            reasons.extend(result.reasons)
            break
        final_status = result.status
        if stage == max_stage:
            final_decision = "NEXT_STAGE_AVAILABLE"
            reasons.append("requested_mode_stage_completed")
            break

    next_stage = _next_stage(gates[-1].gate if gates else None)
    return AlphaHypothesisRunnerReport(
        run_id=config.run_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        commit=report_commit,
        hypothesis_id=hypothesis_id,
        requested_hypothesis_id=config.hypothesis_id,
        mode=config.mode,
        state_db=str(config.state_db) if config.state_db else None,
        data_paths=tuple(str(path) for path in config.data_paths),
        gates=tuple(gates),
        final_status=final_status,
        next_allowed_stage=next_stage if final_decision == "NEXT_STAGE_AVAILABLE" else None,
        final_decision=final_decision,
        reasons=tuple(reasons),
        autonomy_policy_summary=_policy_summary(policy),
        runtime_seconds=round(time.perf_counter() - started, 6),
        safety_notes=(
            "Research-only alpha hypothesis runner.",
            "No runtime order path is imported or called.",
            "No paper capital, live activation, promotion, sizing, leverage, or UI path is changed.",
            "Risk-reducing actions may be automatic; risk-increasing actions require human review.",
        ),
    )


def write_alpha_hypothesis_runner_report(
    report: AlphaHypothesisRunnerReport,
    output_dir: str | Path,
) -> AlphaHypothesisRunnerReport:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / f"{report.run_id}.json"
    markdown_path = output / f"{report.run_id}.md"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(render_alpha_hypothesis_runner_report(report), encoding="utf-8")
    return replace(report, json_report_path=str(json_path), markdown_report_path=str(markdown_path))


def render_alpha_hypothesis_runner_report(report: AlphaHypothesisRunnerReport) -> str:
    lines = [
        f"# P18C Alpha Hypothesis Runner - {report.run_id}",
        "",
        "## Scope",
        "",
        "- Mode: `research_only`.",
        "- No live, no paper capital, no promotion, no UI change, no sizing/leverage change.",
        f"- Commit: `{report.commit}`.",
        f"- Hypothesis: `{report.hypothesis_id}`.",
        f"- Runner mode: `{report.mode}`.",
        f"- Final status: `{report.final_status}`.",
        f"- Final decision: `{report.final_decision}`.",
        "",
        "## Architecture",
        "",
        "Market data research store -> hypothesis registry -> autonomy policy -> sequential gates -> report.",
        "",
        "## Gates",
        "",
        "| Gate | Status | Passed | Stopped | Autonomy | Risk | Runtime s | Reasons |",
        "|---|---|---:|---:|---|---|---:|---|",
    ]
    for gate in report.gates:
        lines.append(
            f"| `{gate.gate}` | `{gate.status}` | {gate.passed} | {gate.stopped} | "
            f"`{gate.autonomy_level}` | `{gate.risk_direction}` | {gate.runtime_seconds} | {', '.join(gate.reasons)} |"
        )
    lines.extend(["", "## First Smoke Result", ""])
    smoke = next((gate for gate in report.gates if gate.gate == "FAST_NET_EDGE_TEST"), None)
    if smoke:
        for key, value in smoke.metrics.items():
            lines.append(f"- `{key}`: `{value}`")
    else:
        lines.append("- Smoke was not reached.")
    lines.extend(["", "## Autonomy Policy", ""])
    for key, value in report.autonomy_policy_summary.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Safety", ""])
    lines.extend(f"- {note}" for note in report.safety_notes)
    lines.append(f"- paper_capital_allowed: `{report.paper_capital_allowed}`")
    lines.append(f"- live_allowed: `{report.live_allowed}`")
    lines.append(f"- promotable: `{report.promotable}`")
    lines.extend(["", "## Recommendation P18D", ""])
    lines.append(_recommendation(report))
    return "\n".join(lines) + "\n"


def load_alpha_autonomy_policy(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    gates = payload.get("gates")
    if not isinstance(gates, list) or not gates:
        raise ValueError("alpha autonomy policy must contain gates")
    for gate in gates:
        if gate.get("autonomy_level") not in {AUTO_ALLOWED, HUMAN_REVIEW_REQUIRED}:
            raise ValueError(f"invalid autonomy level for {gate.get('name')}")
        if gate.get("risk_direction") not in {"reduce", "neutral", "increase"}:
            raise ValueError(f"invalid risk direction for {gate.get('name')}")
        if gate.get("risk_direction") == "increase" and not bool(gate.get("requires_human_approval")):
            raise ValueError(f"risk increase must require human approval for {gate.get('name')}")
    return payload


def gate_policy_for(policy: Mapping[str, Any], gate_name: str) -> dict[str, Any]:
    for gate in policy.get("gates", []):
        if gate.get("name") == gate_name:
            return dict(gate)
    raise ValueError(f"missing autonomy policy for gate: {gate_name}")


def canonical_hypothesis_id(value: str) -> str:
    raw = str(value or "").strip()
    return CANONICAL_ALIASES.get(raw, raw)


def _find_hypothesis(registry: Mapping[str, Any], hypothesis_id: str) -> Mapping[str, Any]:
    for entry in registry.get("hypotheses", []):
        if entry.get("id") == hypothesis_id:
            return entry
    raise ValueError(f"unknown alpha hypothesis: {hypothesis_id}")


def _data_check(
    config: AlphaHypothesisRunnerConfig,
    hypothesis: Mapping[str, Any],
    policy: Mapping[str, Any],
    started: float,
) -> AlphaGateResult:
    hypothesis_id = str(hypothesis["id"])
    if hypothesis_id == "funding_basis":
        return _funding_basis_data_check(config, policy, started)
    if hypothesis_id in MISSING_DATA_IDS:
        return _gate(
            "DATA_CHECK",
            "DATA_MISSING",
            False,
            True,
            ["required_non_ohlcv_data_missing"],
            policy,
            started,
            metrics={"required_data": list(hypothesis.get("data", []))},
        )
    if not config.data_paths:
        return _gate("DATA_CHECK", "DATA_MISSING", False, True, ["data_paths_missing"], policy, started)
    if hypothesis_id == "cross_momentum":
        template = _cross_sectional_template(config)
        bars, duplicate_count = load_cross_sectional_bars(config.data_paths, max_rows=config.max_data_rows)
        groups = _group_cross_sectional_for_availability(bars, config.symbols[: config.max_symbols])
        availability = build_cross_sectional_availability(
            _cross_sectional_config(config, template),
            groups,
            duplicate_count,
        )
        if not availability.available:
            return _gate(
                "DATA_CHECK",
                "DATA_MISSING",
                False,
                True,
                [availability.reason or "generic_cross_sectional_data_missing"],
                policy,
                started,
                metrics=availability.to_dict(),
            )
        return _gate(
            "DATA_CHECK",
            "KEEP_RESEARCH",
            True,
            False,
            ["data_ready"],
            policy,
            started,
            metrics=availability.to_dict(),
        )
    smoke = _build_smoke(config, commit=None)
    adapter_id = SMOKE_ADAPTER_IDS.get(hypothesis_id)
    availability = next((row for row in smoke.availability if row.hypothesis_id == adapter_id), None)
    if availability is None or not availability.available:
        return _gate(
            "DATA_CHECK",
            "DATA_MISSING",
            False,
            True,
            [availability.reason if availability else "adapter_availability_missing"],
            policy,
            started,
        )
    if availability.row_count > config.max_data_rows:
        return _gate(
            "DATA_CHECK",
            "REJECTED",
            False,
            True,
            ["max_data_rows_exceeded"],
            policy,
            started,
            metrics=availability.to_dict(),
        )
    return _gate(
        "DATA_CHECK",
        "KEEP_RESEARCH",
        True,
        False,
        ["data_ready"],
        policy,
        started,
        metrics=availability.to_dict(),
    )


def _funding_basis_data_check(
    config: AlphaHypothesisRunnerConfig,
    policy: Mapping[str, Any],
    started: float,
) -> AlphaGateResult:
    """Gate funding/basis research on explicit, immutable input manifests.

    This validates only research input readiness.  It deliberately does not
    create a signal, trade, shadow write, paper order, or promotion path; the
    alpha adapter is evaluated separately by the bounded smoke gate.
    """

    if not config.data_paths:
        return _gate(
            "DATA_CHECK",
            "DATA_MISSING",
            False,
            True,
            ["spot_ohlcv_data_paths_missing"],
            policy,
            started,
        )
    if config.feature_snapshot_manifest is None:
        return _gate(
            "DATA_CHECK",
            "DATA_MISSING",
            False,
            True,
            ["spot_feature_snapshot_manifest_missing"],
            policy,
            started,
        )
    if config.derivatives_feature_snapshot_manifest is None:
        return _gate(
            "DATA_CHECK",
            "DATA_MISSING",
            False,
            True,
            ["derivatives_feature_snapshot_manifest_missing"],
            policy,
            started,
        )

    from .derivatives_feature_snapshot import (
        DerivativesFeatureSnapshotManifestError,
        inspect_derivatives_feature_snapshot_manifest,
    )
    from .manifested_experiment import ManifestedExperimentError, load_feature_snapshot_provenance

    try:
        spot = load_feature_snapshot_provenance(config.feature_snapshot_manifest)
    except ManifestedExperimentError as exc:
        return _gate(
            "DATA_CHECK",
            "DATA_MISSING",
            False,
            True,
            [f"spot_feature_snapshot_invalid:{exc}"],
            policy,
            started,
        )
    if spot.snapshot_kind == "DERIVATIVES_POINT_IN_TIME":
        return _gate(
            "DATA_CHECK",
            "DATA_MISSING",
            False,
            True,
            ["spot_feature_snapshot_kind_invalid"],
            policy,
            started,
        )
    try:
        derivatives = inspect_derivatives_feature_snapshot_manifest(
            config.derivatives_feature_snapshot_manifest
        )
    except DerivativesFeatureSnapshotManifestError as exc:
        return _gate(
            "DATA_CHECK",
            "DATA_MISSING",
            False,
            True,
            [f"derivatives_feature_snapshot_invalid:{exc}"],
            policy,
            started,
        )

    metrics = {
        "spot_feature_snapshot_id": spot.feature_snapshot_id,
        "spot_runtime_parity_proven": spot.runtime_parity_proven,
        **derivatives.to_dict(),
        "required_derivatives_features": sorted(FUNDING_BASIS_REQUIRED_DERIVATIVES_FEATURES),
    }
    if derivatives.status == "WAITING_FOR_MORE_DATA":
        return _gate(
            "DATA_CHECK",
            "INSUFFICIENT_DATA",
            False,
            True,
            ["derivatives_waiting_for_more_data", *derivatives.blockers],
            policy,
            started,
            metrics=metrics,
        )
    if derivatives.status != "READY":
        return _gate(
            "DATA_CHECK",
            "DATA_MISSING",
            False,
            True,
            ["derivatives_feature_snapshot_not_ready", *derivatives.blockers],
            policy,
            started,
            metrics=metrics,
        )
    missing_features = sorted(FUNDING_BASIS_REQUIRED_DERIVATIVES_FEATURES - set(derivatives.feature_ids))
    if missing_features or derivatives.feature_count <= 0 or not derivatives.parity_ok:
        reasons = ["derivatives_feature_requirements_not_met", *derivatives.blockers]
        reasons.extend(f"derivatives_feature_missing:{feature_id}" for feature_id in missing_features)
        if not derivatives.parity_ok:
            reasons.append("derivatives_feature_parity_failed")
        return _gate(
            "DATA_CHECK",
            "DATA_MISSING",
            False,
            True,
            reasons,
            policy,
            started,
            metrics=metrics,
        )
    return _gate(
        "DATA_CHECK",
        "KEEP_RESEARCH",
        True,
        False,
        ["funding_basis_research_inputs_ready"],
        policy,
        started,
        metrics=metrics,
    )


def _fast_net_edge_test(
    config: AlphaHypothesisRunnerConfig,
    hypothesis_id: str,
    policy: Mapping[str, Any],
    started: float,
    commit: str | None,
) -> AlphaGateResult:
    if hypothesis_id == "funding_basis":
        template = _funding_basis_template(config)
        if config.derivatives_feature_snapshot_manifest is None:
            return _gate(
                "FAST_NET_EDGE_TEST",
                "INSUFFICIENT_DATA",
                False,
                True,
                ["derivatives_feature_snapshot_manifest_missing"],
                policy,
                started,
            )
        result = run_funding_basis_research_smoke(
            FundingBasisResearchConfig(
                run_id=f"{config.run_id}_{template['template_id']}",
                spot_data_paths=config.data_paths,
                derivatives_feature_snapshot_manifest=config.derivatives_feature_snapshot_manifest,
                template=template,
                symbols=config.symbols,
                cost_profile=config.cost_profile,
                max_variants=min(config.max_variants, int(template.get("max_variants", config.max_variants))),
                max_symbols=min(config.max_symbols, int(template.get("max_symbols", config.max_symbols))),
                max_runtime_seconds=min(config.max_runtime_seconds, float(template.get("max_runtime_seconds", config.max_runtime_seconds))),
                max_data_rows=config.max_data_rows,
            )
        )
        metrics = result.metrics.to_dict()
        metrics.update(
            {
                "adapter_id": result.adapter_id,
                "mode_used": result.mode,
                "template_id": result.template_id,
                "adapter_decision": result.decision,
                "variant_count": result.variant_count,
                "primary_variant": result.primary_variant,
                "availability": result.availability.to_dict(),
            }
        )
        passed = result.decision in {"WALK_FORWARD_AVAILABLE"}
        status = "KEEP_RESEARCH" if passed else result.decision
        return _gate(
            "FAST_NET_EDGE_TEST",
            status,
            passed,
            not passed,
            result.reasons,
            policy,
            started,
            metrics=metrics,
            artifacts={
                "variants": [dict(item) for item in result.variants],
                "primary_trades": [item.to_dict() for item in result.primary_trades],
            },
        )
    adapter_id = SMOKE_ADAPTER_IDS.get(hypothesis_id)
    if not adapter_id:
        return _gate("FAST_NET_EDGE_TEST", "REJECT_FAST", False, True, ["fast_adapter_missing"], policy, started)
    if adapter_id == GENERIC_CROSS_SECTIONAL_ADAPTER_ID:
        template = _cross_sectional_template(config)
        result = run_generic_cross_sectional_ohlcv_smoke(_cross_sectional_config(config, template))
        metrics = result.metrics.to_dict()
        metrics["adapter_id"] = result.adapter_id
        metrics["mode_used"] = result.mode
        metrics["template_id"] = result.template_id
        metrics["adapter_decision"] = result.decision
        metrics["variant_count"] = result.variant_count
        metrics["primary_variant"] = result.primary_variant
        metrics["availability"] = result.availability.to_dict()
        passed = result.decision in {"KEEP_RESEARCH", "WALK_FORWARD_AVAILABLE"}
        status = "KEEP_RESEARCH" if passed else result.decision
        return _gate(
            "FAST_NET_EDGE_TEST",
            status,
            passed,
            not passed,
            tuple(result.reasons),
            policy,
            started,
            metrics=metrics,
            artifacts={"variants": [dict(item) for item in result.variants]},
        )
    smoke = _build_smoke(config, commit=commit)
    result = next((row for row in smoke.tested if row.hypothesis_id == adapter_id), None)
    if result is None:
        return _gate("FAST_NET_EDGE_TEST", "REJECT_FAST", False, True, ["fast_result_missing"], policy, started)
    metrics = result.metrics.to_dict()
    metrics["adapter_decision"] = result.decision
    metrics["best_variant"] = result.best_variant
    metrics["variant_count"] = result.variant_count
    passed = result.decision in {"KEEP_RESEARCH", "NEEDS_MORE_DATA"}
    status = "KEEP_RESEARCH" if passed else "REJECT_FAST"
    return _gate(
        "FAST_NET_EDGE_TEST",
        status,
        passed,
        not passed,
        tuple(result.reasons),
        policy,
        started,
        metrics=metrics,
    )


def _walk_forward(
    config: AlphaHypothesisRunnerConfig,
    hypothesis_id: str,
    policy: Mapping[str, Any],
    started: float,
    commit: str | None,
) -> AlphaGateResult:
    if hypothesis_id == "funding_basis":
        if config.derivatives_feature_snapshot_manifest is None:
            return _gate(
                "WALK_FORWARD",
                "INSUFFICIENT_DATA",
                False,
                True,
                ["derivatives_feature_snapshot_manifest_missing"],
                policy,
                started,
            )
        template = _funding_basis_template(config)
        report = build_funding_basis_walk_forward_report(
            FundingBasisWalkForwardConfig(
                run_id=f"{config.run_id}_walk_forward",
                spot_data_paths=config.data_paths,
                derivatives_feature_snapshot_manifest=config.derivatives_feature_snapshot_manifest,
                template=template,
                symbols=config.symbols,
                cost_profile=config.cost_profile,
                max_variants=min(config.max_variants, int(template.get("max_variants", config.max_variants))),
                max_symbols=min(config.max_symbols, int(template.get("max_symbols", config.max_symbols))),
                max_runtime_seconds=config.max_runtime_seconds,
                max_data_rows=config.max_data_rows,
            )
        )
        passed = report.decision == "KEEP_RESEARCH"
        return _gate(
            "WALK_FORWARD",
            report.decision,
            passed,
            not passed,
            report.reasons,
            policy,
            started,
            metrics=report.overall_oos.to_dict(),
            artifacts={"folds": [fold.to_dict() for fold in report.folds], "diagnostics": dict(report.diagnostics)},
        )
    if hypothesis_id != "volatility_breakout":
        return _gate("WALK_FORWARD", "REJECTED", False, True, ["walk_forward_adapter_missing"], policy, started)
    report = build_volatility_breakout_walk_forward_report(
        VolatilityBreakoutWalkForwardConfig(
            run_id=f"{config.run_id}_walk_forward",
            data_paths=config.data_paths,
            symbols=config.symbols[: config.max_symbols],
            cost_profile=config.cost_profile,
            max_variants=config.max_variants,
            max_cpu_seconds=config.max_runtime_seconds,
        ),
        commit=commit,
    )
    passed = report.verdict in {"KEEP_RESEARCH", "SHADOW_CANDIDATE_LATER"}
    return _gate(
        "WALK_FORWARD",
        report.verdict,
        passed,
        not passed,
        report.verdict_reasons,
        policy,
        started,
        metrics=report.overall.to_dict(),
        artifacts={"verdict": report.verdict, "concentration": report.concentration},
    )


def _stress_placeholder(policy: Mapping[str, Any], started: float) -> AlphaGateResult:
    return _gate(
        "STRESS_MONTE_CARLO",
        "WEAK_SIGNAL",
        False,
        True,
        ["stress_not_run_without_prior_walk_forward_pass"],
        policy,
        started,
    )


def _build_smoke(config: AlphaHypothesisRunnerConfig, commit: str | None):
    return build_alpha_smoke_report(
        AlphaSmokeConfig(
            run_id=f"{config.run_id}_smoke",
            data_paths=config.data_paths,
            hypotheses_path=config.hypotheses_path,
            output_dir=config.output_dir,
            symbols=config.symbols[: config.max_symbols],
            cost_profile=config.cost_profile,
            max_variants=min(config.max_variants, 5),
            max_symbols=config.max_symbols,
            max_cpu_seconds=config.max_runtime_seconds,
        ),
        commit=commit,
    )


def _cross_sectional_template(config: AlphaHypothesisRunnerConfig) -> dict[str, Any]:
    payload = json.loads(config.templates_path.read_text(encoding="utf-8"))
    templates = [
        dict(item)
        for item in payload.get("templates", [])
        if item.get("alpha_family_id") == "cross_sectional_momentum"
        and item.get("required_adapter") == GENERIC_CROSS_SECTIONAL_ADAPTER_ID
    ]
    if not templates:
        raise ValueError("generic cross-sectional template is missing")
    if config.template_id:
        for template in templates:
            if template.get("template_id") == config.template_id:
                return template
        raise ValueError(f"unknown cross-sectional template: {config.template_id}")
    return templates[0]


def _funding_basis_template(config: AlphaHypothesisRunnerConfig) -> dict[str, Any]:
    payload = json.loads(config.templates_path.read_text(encoding="utf-8"))
    templates = [
        dict(item)
        for item in payload.get("templates", [])
        if item.get("alpha_family_id") == "funding_basis"
        and item.get("required_adapter") == FUNDING_BASIS_ADAPTER_ID
    ]
    if not templates:
        raise ValueError("funding/basis research template is missing")
    if config.template_id:
        for template in templates:
            if template.get("template_id") == config.template_id:
                return template
        raise ValueError(f"unknown funding/basis template: {config.template_id}")
    return templates[0]


def _cross_sectional_config(
    config: AlphaHypothesisRunnerConfig,
    template: Mapping[str, Any],
) -> GenericCrossSectionalConfig:
    return GenericCrossSectionalConfig(
        run_id=f"{config.run_id}_{template['template_id']}",
        mode=str(template["template_id"]),
        data_paths=config.data_paths,
        template=template,
        symbols=config.symbols,
        cost_profile=config.cost_profile,
        max_variants=min(config.max_variants, int(template.get("max_variants", config.max_variants))),
        max_symbols=min(config.max_symbols, int(template.get("max_symbols", config.max_symbols))),
        max_runtime_seconds=min(config.max_runtime_seconds, float(template.get("max_runtime_seconds", config.max_runtime_seconds))),
        max_data_rows=config.max_data_rows,
    )


def _group_cross_sectional_for_availability(
    bars: Sequence[Any],
    symbols: Sequence[str],
) -> dict[tuple[str, str], list[Any]]:
    allowed = {symbol.upper() for symbol in symbols}
    groups: dict[tuple[str, str], list[Any]] = {}
    for bar in bars:
        symbol = str(bar.symbol).upper()
        if allowed and symbol not in allowed:
            continue
        groups.setdefault((symbol, str(bar.timeframe).lower()), []).append(bar)
    return groups


def _gate(
    gate_name: str,
    status: str,
    passed: bool,
    stopped: bool,
    reasons: Sequence[str],
    policy: Mapping[str, Any],
    started: float,
    *,
    metrics: dict[str, Any] | None = None,
    artifacts: dict[str, Any] | None = None,
) -> AlphaGateResult:
    gate_policy = gate_policy_for(policy, gate_name)
    return AlphaGateResult(
        gate=gate_name,
        status=status,
        passed=passed,
        stopped=stopped,
        reasons=tuple(str(reason) for reason in reasons if reason),
        autonomy_level=str(gate_policy["autonomy_level"]),
        risk_direction=str(gate_policy["risk_direction"]),
        requires_human_approval=bool(gate_policy["requires_human_approval"]),
        runtime_seconds=round(time.perf_counter() - started, 6),
        metrics=metrics or {},
        artifacts=artifacts or {},
    )


def _next_stage(stage: str | None) -> str | None:
    if stage not in STAGE_ORDER:
        return None
    index = STAGE_ORDER.index(stage)
    if index + 1 >= len(STAGE_ORDER):
        return None
    return STAGE_ORDER[index + 1]


def _policy_summary(policy: Mapping[str, Any]) -> dict[str, Any]:
    gates = policy.get("gates", [])
    return {
        "auto_allowed_gates": [gate["name"] for gate in gates if gate.get("autonomy_level") == AUTO_ALLOWED],
        "human_review_gates": [gate["name"] for gate in gates if gate.get("autonomy_level") == HUMAN_REVIEW_REQUIRED],
        "principle": policy.get("principle"),
    }


def _recommendation(report: AlphaHypothesisRunnerReport) -> str:
    if report.final_status in {"REJECT_FAST", "DATA_MISSING", "REJECTED"}:
        return "Do not advance this hypothesis; keep it rejected/research-only until new data or a redesigned hypothesis exists."
    if report.final_decision == "HUMAN_REVIEW_REQUIRED":
        return "Prepare a human review package only; no automatic shadow, paper, or live activation."
    return "Continue with the next research-only gate only if explicitly requested by CLI mode; no paper/live promotion."


def _current_git_commit() -> str | None:
    env_commit = os.environ.get("AUTOBOT_COMMIT") or os.environ.get("GIT_COMMIT")
    if env_commit:
        return env_commit.strip() or None
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None
