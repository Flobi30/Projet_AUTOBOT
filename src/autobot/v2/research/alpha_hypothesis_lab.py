"""Research-only alpha hypothesis registry and validation gates.

This module does not generate orders, does not allocate paper capital, and does
not promote strategies. It defines a small contract for future alpha ideas so
they must pass data, cost, walk-forward, Monte-Carlo, and shadow gates before
any later human review.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence


ALLOWED_STATUSES = frozenset(
    {
        "idea",
        "data_check",
        "quick_test",
        "walk_forward",
        "monte_carlo",
        "shadow",
        "rejected",
        "paused",
    }
)
RESEARCH_ONLY_CAPITAL_FLAGS = {
    "promotable": False,
    "paper_capital_allowed": False,
    "live_allowed": False,
}

# The canonical experiment progression is intentionally independent from the
# historical report labels used by older runners.  The registry/scheduler may
# normalize aliases, but no later stage may be recorded before its predecessor.
CANONICAL_RESEARCH_STAGES = (
    "DATA_CHECK",
    "NET_SMOKE",
    "WALK_FORWARD",
    "STRESS_MONTE_CARLO",
    "SHADOW_REVIEW",
)
RESEARCH_STAGE_ALIASES = {
    "DATA_CHECK": "DATA_CHECK",
    "data_check": "DATA_CHECK",
    "NET_SMOKE": "NET_SMOKE",
    "quick_net_test": "NET_SMOKE",
    "FAST_NET_EDGE_TEST": "NET_SMOKE",
    "WALK_FORWARD": "WALK_FORWARD",
    "walk_forward": "WALK_FORWARD",
    "STRESS_MONTE_CARLO": "STRESS_MONTE_CARLO",
    "monte_carlo_stress": "STRESS_MONTE_CARLO",
    "SHADOW_REVIEW": "SHADOW_REVIEW",
    "shadow_observation": "SHADOW_REVIEW",
    "SHADOW_REVIEW_CANDIDATE": "SHADOW_REVIEW",
}


REQUIRED_HYPOTHESIS_FIELDS = (
    "id",
    "thesis",
    "data",
    "symbols",
    "timeframe",
    "metrics",
    "kill_rules",
    "status",
)


@dataclass(frozen=True)
class AlphaGateBudget:
    max_cpu_minutes: int
    max_variants: int
    max_symbols: int

    def to_dict(self) -> dict[str, int]:
        return {
            "max_cpu_minutes": self.max_cpu_minutes,
            "max_variants": self.max_variants,
            "max_symbols": self.max_symbols,
        }


@dataclass(frozen=True)
class AlphaValidationStep:
    name: str
    required_inputs: tuple[str, ...]
    pass_conditions: tuple[str, ...]
    budget: AlphaGateBudget
    autostop_rules: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "required_inputs": list(self.required_inputs),
            "pass_conditions": list(self.pass_conditions),
            "budget": self.budget.to_dict(),
            "autostop_rules": list(self.autostop_rules),
            **RESEARCH_ONLY_CAPITAL_FLAGS,
        }


DEFAULT_PIPELINE: tuple[AlphaValidationStep, ...] = (
    AlphaValidationStep(
        name="data_check",
        required_inputs=("ohlcv", "cost_profile", "symbol_mapping"),
        pass_conditions=(
            "minimum_history_days_met",
            "no_duplicate_bars",
            "gap_report_created",
            "cost_profile_present",
        ),
        budget=AlphaGateBudget(max_cpu_minutes=5, max_variants=1, max_symbols=14),
        autostop_rules=("stop_if_missing_required_data",),
    ),
    AlphaValidationStep(
        name="quick_net_test",
        required_inputs=("signals", "fees", "spread", "slippage"),
        pass_conditions=("net_pnl_after_costs_positive", "profit_factor_net_above_1"),
        budget=AlphaGateBudget(max_cpu_minutes=10, max_variants=3, max_symbols=14),
        autostop_rules=("stop_if_pf_net_below_0_9_after_30_trades",),
    ),
    AlphaValidationStep(
        name="walk_forward",
        required_inputs=("time_ordered_folds", "baseline", "cost_profile"),
        pass_conditions=("positive_oos_folds_ratio_at_least_0_6", "baseline_beaten_net"),
        budget=AlphaGateBudget(max_cpu_minutes=20, max_variants=5, max_symbols=14),
        autostop_rules=("stop_if_two_consecutive_oos_folds_negative",),
    ),
    AlphaValidationStep(
        name="monte_carlo_stress",
        required_inputs=("closed_trades", "cost_stress_profile"),
        pass_conditions=("survival_probability_acceptable", "drawdown_under_limit"),
        budget=AlphaGateBudget(max_cpu_minutes=10, max_variants=2, max_symbols=14),
        autostop_rules=("stop_if_bootstrap_expectancy_p95_below_zero",),
    ),
    AlphaValidationStep(
        name="shadow_observation",
        required_inputs=("registry_record", "shadow_ledger", "no_live_flags"),
        pass_conditions=("shadow_sample_size_met", "no_promotion", "no_paper_capital"),
        budget=AlphaGateBudget(max_cpu_minutes=5, max_variants=1, max_symbols=14),
        autostop_rules=("stop_if_rolling_pf_below_0_9", "stop_if_drawdown_above_10pct"),
    ),
)


class AlphaHypothesisError(ValueError):
    """Raised when the alpha hypothesis lab contract is invalid."""


def load_alpha_hypotheses(path: str | Path) -> dict[str, Any]:
    registry_path = Path(path)
    with registry_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    validate_alpha_hypotheses(payload)
    return payload


def validate_alpha_hypotheses(payload: Mapping[str, Any]) -> None:
    if not isinstance(payload, Mapping):
        raise AlphaHypothesisError("alpha hypotheses root must be an object")
    hypotheses = payload.get("hypotheses")
    if not isinstance(hypotheses, list) or not hypotheses:
        raise AlphaHypothesisError("alpha hypotheses must contain a non-empty hypotheses list")
    seen: set[str] = set()
    for entry in hypotheses:
        if not isinstance(entry, Mapping):
            raise AlphaHypothesisError("each alpha hypothesis must be an object")
        missing = [field for field in REQUIRED_HYPOTHESIS_FIELDS if field not in entry]
        if missing:
            raise AlphaHypothesisError(f"alpha hypothesis missing fields: {', '.join(missing)}")
        hypothesis_id = str(entry.get("id") or "").strip()
        if not hypothesis_id:
            raise AlphaHypothesisError("alpha hypothesis id is required")
        if hypothesis_id in seen:
            raise AlphaHypothesisError(f"duplicate alpha hypothesis id: {hypothesis_id}")
        seen.add(hypothesis_id)
        status = str(entry.get("status") or "").strip()
        if status not in ALLOWED_STATUSES:
            raise AlphaHypothesisError(f"invalid alpha hypothesis status for {hypothesis_id}: {status}")
        if bool(entry.get("paper_capital_allowed")) or bool(entry.get("live_allowed")):
            raise AlphaHypothesisError(f"{hypothesis_id} cannot allow paper capital or live")
        if bool(entry.get("promotable")):
            raise AlphaHypothesisError(f"{hypothesis_id} cannot be promotable")


def default_pipeline_payload() -> list[dict[str, Any]]:
    return [step.to_dict() for step in DEFAULT_PIPELINE]


def normalize_research_stage(value: str) -> str:
    """Normalize one legacy/current gate label to the canonical pipeline."""

    try:
        return RESEARCH_STAGE_ALIASES[str(value)]
    except KeyError as exc:
        raise AlphaHypothesisError(f"unsupported research stage: {value}") from exc


def next_research_stage(stage: str | None) -> str:
    """Return the sole stage allowed after ``stage`` in the research pipeline."""

    if stage is None:
        return CANONICAL_RESEARCH_STAGES[0]
    normalized = normalize_research_stage(stage)
    index = CANONICAL_RESEARCH_STAGES.index(normalized)
    if index + 1 >= len(CANONICAL_RESEARCH_STAGES):
        raise AlphaHypothesisError("research pipeline is complete; new material fingerprint is required")
    return CANONICAL_RESEARCH_STAGES[index + 1]


def evaluate_research_gate(
    *,
    metrics: Mapping[str, Any],
    current_step: str,
    minimum_trade_count: int = 50,
    minimum_profit_factor: float = 1.0,
    maximum_drawdown_pct: float = 10.0,
) -> dict[str, Any]:
    """Return a research-only gate result for one hypothesis checkpoint."""

    reasons: list[str] = []
    trade_count = int(float(metrics.get("trade_count") or 0))
    pf_net = _to_float(metrics.get("profit_factor_net"))
    expectancy = _to_float(metrics.get("expectancy_net"))
    max_drawdown = _to_float(metrics.get("max_drawdown_pct"))
    fees_present = bool(metrics.get("fees_present"))
    slippage_present = bool(metrics.get("slippage_present"))
    baseline_present = bool(metrics.get("baseline_present"))

    if trade_count < minimum_trade_count:
        reasons.append("sample_size_insufficient")
    if pf_net is None or pf_net <= minimum_profit_factor:
        reasons.append("profit_factor_net_below_required")
    if expectancy is None or expectancy <= 0:
        reasons.append("expectancy_net_not_positive")
    if max_drawdown is None or max_drawdown > maximum_drawdown_pct:
        reasons.append("drawdown_above_limit")
    if not fees_present:
        reasons.append("fees_missing")
    if not slippage_present:
        reasons.append("slippage_missing")
    if not baseline_present:
        reasons.append("baseline_missing")

    return {
        "current_step": current_step,
        "passed": not reasons,
        "reasons": reasons,
        "checks": {
            "trade_count": trade_count,
            "profit_factor_net": pf_net,
            "expectancy_net": expectancy,
            "max_drawdown_pct": max_drawdown,
            "fees_present": fees_present,
            "slippage_present": slippage_present,
            "baseline_present": baseline_present,
        },
        **RESEARCH_ONLY_CAPITAL_FLAGS,
    }


def _to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None

