"""Conservative, research-only summary gate for statistical evidence.

This module combines *already computed* deterministic diagnostics into one
immutable verdict.  It does not calculate a strategy, write a registry, or
import any runtime, broker, paper, ledger, or order-routing component.

``SHADOW_REVIEW_ELIGIBLE`` means only that the supplied research evidence may
be reviewed by a human for a future shadow decision.  It is never a claim
about future performance and cannot enable paper capital, live trading, or
promotion.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any

from .robustness_experiments import RobustnessExperimentReport
from .statistical_validation import DeflatedSharpeResult, ProbabilisticSharpeResult


@dataclass(frozen=True)
class StatisticalGateConfig:
    """Explicit conservative thresholds for a research-only evidence review."""

    min_trade_count: int = 50
    max_trial_count: int = 16
    min_bootstrap_positive_probability: float = 0.55

    def __post_init__(self) -> None:
        if self.min_trade_count < 2:
            raise ValueError("min_trade_count must be at least two")
        if self.max_trial_count < 1:
            raise ValueError("max_trial_count must be positive")
        if not 0.0 < self.min_bootstrap_positive_probability <= 1.0:
            raise ValueError("min_bootstrap_positive_probability must be in (0, 1]")


@dataclass(frozen=True)
class StatisticalGateEvidence:
    """Inputs produced by earlier research stages; missing evidence blocks.

    ``trial_count`` is deliberately explicit rather than inferred from an
    individual DSR proxy.  A caller must account for the research variants it
    knows about; zero or an invalid count is treated as unknown and fails
    closed.
    """

    trade_count: object
    trial_count: object
    net_pnl_eur: object
    out_of_sample_confirmed: object
    net_of_costs: object
    probabilistic_sharpe: ProbabilisticSharpeResult | None
    deflated_sharpe: DeflatedSharpeResult | None
    robustness: RobustnessExperimentReport | None


@dataclass(frozen=True)
class StatisticalGateSummary:
    """Immutable non-promotional conclusion from statistical research evidence."""

    decision: str
    blockers: tuple[str, ...]
    reasons: tuple[str, ...]
    method_notes: tuple[str, ...]
    trade_count: int | None
    trial_count: int | None
    net_pnl_eur: float | None
    out_of_sample_confirmed: bool
    net_of_costs: bool
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False
    promotable: bool = False

    def __post_init__(self) -> None:
        if self.decision not in {"RESEARCH_BLOCKED", "SHADOW_REVIEW_ELIGIBLE"}:
            raise ValueError(f"unsupported statistical gate decision: {self.decision}")
        if not self.research_only or self.paper_capital_allowed or self.live_allowed or self.promotable:
            raise ValueError("statistical gate summaries are research-only and non-promotional")
        if self.decision == "SHADOW_REVIEW_ELIGIBLE" and self.blockers:
            raise ValueError("shadow review eligibility cannot carry blockers")

    @property
    def shadow_review_eligible(self) -> bool:
        return self.decision == "SHADOW_REVIEW_ELIGIBLE"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["shadow_review_eligible"] = self.shadow_review_eligible
        payload["research_only"] = True
        payload["paper_capital_allowed"] = False
        payload["live_allowed"] = False
        payload["promotable"] = False
        return payload


def summarize_statistical_gate(
    evidence: StatisticalGateEvidence,
    config: StatisticalGateConfig = StatisticalGateConfig(),
) -> StatisticalGateSummary:
    """Fail closed unless supplied net/OOS/statistical evidence is complete.

    The PSR and DSR implementations used by AUTOBOT are explicitly marked as
    proxies.  This summary preserves that limitation: it can only permit a
    later *research* review, never declare a strategy profitable or route it
    toward execution.
    """

    blockers: list[str] = []
    reasons = ["research_only_statistical_gate_summary", "no_paper_live_or_promotion_path"]
    method_notes = (
        "probabilistic_sharpe_per_trade_proxy",
        "deflated_sharpe_proxy",
        "bootstrap_and_cost_stress_are_research_diagnostics",
        "shadow_review_eligibility_is_not_a_performance_claim",
    )

    trade_count = _positive_int(evidence.trade_count)
    trial_count = _positive_int(evidence.trial_count)
    net_pnl_eur = _finite_float(evidence.net_pnl_eur)
    out_of_sample_confirmed = evidence.out_of_sample_confirmed is True
    net_of_costs = evidence.net_of_costs is True

    if trade_count is None:
        blockers.append("trade_count_missing_or_invalid")
    elif trade_count < config.min_trade_count:
        blockers.append(f"trade_count_below_{config.min_trade_count}")
    if trial_count is None:
        blockers.append("trial_count_missing_or_invalid")
    elif trial_count > config.max_trial_count:
        blockers.append(f"trial_count_exceeds_maximum_{config.max_trial_count}")
    if net_pnl_eur is None:
        blockers.append("net_pnl_missing_or_invalid")
    elif net_pnl_eur <= 0.0:
        blockers.append("net_pnl_not_positive_after_costs")
    if not net_of_costs:
        blockers.append("net_of_costs_not_confirmed")
    if not out_of_sample_confirmed:
        blockers.append("out_of_sample_not_confirmed")

    _check_probabilistic_sharpe(evidence.probabilistic_sharpe, trade_count, blockers)
    _check_deflated_sharpe(evidence.deflated_sharpe, trade_count, trial_count, blockers)
    _check_robustness(evidence.robustness, trade_count, config, blockers)

    blockers = list(dict.fromkeys(blockers))
    if blockers:
        reasons.append("evidence_incomplete_or_conservative_gate_not_met")
        decision = "RESEARCH_BLOCKED"
    else:
        reasons.append("all_required_research_evidence_passed_conservative_summary")
        decision = "SHADOW_REVIEW_ELIGIBLE"
    return StatisticalGateSummary(
        decision=decision,
        blockers=tuple(blockers),
        reasons=tuple(reasons),
        method_notes=method_notes,
        trade_count=trade_count,
        trial_count=trial_count,
        net_pnl_eur=net_pnl_eur,
        out_of_sample_confirmed=out_of_sample_confirmed,
        net_of_costs=net_of_costs,
    )


def _check_probabilistic_sharpe(
    result: ProbabilisticSharpeResult | None,
    trade_count: int | None,
    blockers: list[str],
) -> None:
    if not isinstance(result, ProbabilisticSharpeResult):
        blockers.append("probabilistic_sharpe_missing")
        return
    if not result.research_only or result.paper_candidate_allowed or result.live_promotion_allowed:
        blockers.append("probabilistic_sharpe_not_research_only")
    if trade_count is not None and result.sample_count != trade_count:
        blockers.append("probabilistic_sharpe_sample_count_mismatch")
    if not result.acceptable:
        blockers.append("probabilistic_sharpe_proxy_not_acceptable")


def _check_deflated_sharpe(
    result: DeflatedSharpeResult | None,
    trade_count: int | None,
    trial_count: int | None,
    blockers: list[str],
) -> None:
    if not isinstance(result, DeflatedSharpeResult):
        blockers.append("deflated_sharpe_missing")
        return
    if not result.research_only or result.paper_candidate_allowed or result.live_promotion_allowed:
        blockers.append("deflated_sharpe_not_research_only")
    if trade_count is not None and result.sample_count != trade_count:
        blockers.append("deflated_sharpe_sample_count_mismatch")
    if trial_count is not None and result.assumed_trial_count != trial_count:
        blockers.append("deflated_sharpe_trial_count_mismatch")
    if not result.acceptable:
        blockers.append("deflated_sharpe_proxy_not_acceptable")


def _check_robustness(
    report: RobustnessExperimentReport | None,
    trade_count: int | None,
    config: StatisticalGateConfig,
    blockers: list[str],
) -> None:
    if not isinstance(report, RobustnessExperimentReport):
        blockers.append("robustness_evidence_missing")
        return
    if not report.research_only or report.paper_candidate_allowed or report.live_promotion_allowed:
        blockers.append("robustness_evidence_not_research_only")
    if trade_count is not None and report.trade_count != trade_count:
        blockers.append("robustness_trade_count_mismatch")
    if report.verdict != "observation_ready_not_promoted":
        blockers.append(f"robustness_{report.verdict}")
    probability = report.monte_carlo.probability_positive_net_pnl
    if probability is None or not math.isfinite(float(probability)):
        blockers.append("bootstrap_positive_net_probability_missing_or_invalid")
    elif float(probability) < config.min_bootstrap_positive_probability:
        blockers.append("bootstrap_positive_net_probability_below_threshold")
    if not report.stress_scenarios:
        blockers.append("stress_scenarios_missing")
    for item in report.stress_scenarios:
        net_pnl = item.metrics.total_net_pnl_eur
        if not math.isfinite(float(net_pnl)) or float(net_pnl) <= 0.0:
            blockers.append("stress_scenario_net_pnl_not_positive")
            break


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return None
    return value


def _finite_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None
