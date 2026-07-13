"""Research-only statistical gate for fixed funding/basis walk-forward trades.

This module consumes already produced, out-of-sample spot-EUR trades.  It does
not tune parameters and cannot unlock shadow, paper, or live trading.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence

from .alpha_hypothesis_lab import RESEARCH_ONLY_CAPITAL_FLAGS
from .funding_basis_research_adapter import FundingBasisTrade, funding_basis_trade_records
from .robustness_experiments import (
    MonteCarloConfig,
    RobustnessExperimentConfig,
    build_robustness_experiment_report,
)
from .statistical_validation import (
    DeflatedSharpeConfig,
    ProbabilisticSharpeConfig,
    assess_deflated_sharpe,
    assess_probabilistic_sharpe,
)


@dataclass(frozen=True)
class FundingBasisStatisticalValidationConfig:
    run_id: str
    assumed_trial_count: int
    initial_capital_eur: float = 500.0
    min_trade_count: int = 50
    bootstrap_iterations: int = 1_000
    seed: int = 260624

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id is required")
        if self.assumed_trial_count < 1:
            raise ValueError("assumed_trial_count must be positive")
        if self.initial_capital_eur <= 0.0:
            raise ValueError("initial_capital_eur must be positive")
        if self.min_trade_count < 2:
            raise ValueError("min_trade_count must be at least two")
        if self.bootstrap_iterations < 100:
            raise ValueError("bootstrap_iterations must be at least 100")


@dataclass(frozen=True)
class FundingBasisStatisticalValidationReport:
    run_id: str
    decision: str
    reasons: tuple[str, ...]
    trade_count: int
    assumed_trial_count: int
    deflated_sharpe: Mapping[str, Any]
    probabilistic_sharpe: Mapping[str, Any]
    robustness: Mapping[str, Any]
    safety: Mapping[str, bool] = field(default_factory=lambda: dict(RESEARCH_ONLY_CAPITAL_FLAGS))
    paper_capital_allowed: bool = False
    live_allowed: bool = False
    promotable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "deflated_sharpe": dict(self.deflated_sharpe),
            "probabilistic_sharpe": dict(self.probabilistic_sharpe),
            "robustness": dict(self.robustness),
            "safety": dict(self.safety),
            "paper_capital_allowed": False,
            "live_allowed": False,
            "promotable": False,
        }


def build_funding_basis_statistical_validation_report(
    trades: Sequence[FundingBasisTrade],
    config: FundingBasisStatisticalValidationConfig,
    *,
    walk_forward_passed: bool,
) -> FundingBasisStatisticalValidationReport:
    """Assess fixed OOS trades after a prior walk-forward gate only."""

    if not walk_forward_passed:
        return FundingBasisStatisticalValidationReport(
            run_id=config.run_id,
            decision="INSUFFICIENT_DATA",
            reasons=("walk_forward_gate_not_passed",),
            trade_count=0,
            assumed_trial_count=config.assumed_trial_count,
            deflated_sharpe={},
            probabilistic_sharpe={},
            robustness={},
        )
    records = funding_basis_trade_records(trades, run_id=config.run_id)
    dsr = assess_deflated_sharpe(
        records,
        DeflatedSharpeConfig(
            initial_capital_eur=config.initial_capital_eur,
            assumed_trial_count=config.assumed_trial_count,
            min_trade_count=config.min_trade_count,
        ),
    )
    psr = assess_probabilistic_sharpe(
        records,
        ProbabilisticSharpeConfig(
            initial_capital_eur=config.initial_capital_eur,
            min_trade_count=config.min_trade_count,
        ),
    )
    robustness = build_robustness_experiment_report(
        records,
        RobustnessExperimentConfig(
            run_id=config.run_id,
            initial_capital_eur=config.initial_capital_eur,
            monte_carlo=MonteCarloConfig(
                iterations=config.bootstrap_iterations,
                seed=config.seed,
                min_trade_count=config.min_trade_count,
            ),
        ),
    )
    reasons: list[str] = ["research_only_statistical_gate_after_fixed_walk_forward"]
    if len(records) < config.min_trade_count:
        reasons.append("oos_trade_count_below_statistical_minimum")
    if not dsr.acceptable:
        reasons.append("deflated_sharpe_proxy_not_acceptable")
    if not psr.acceptable:
        reasons.append("probabilistic_sharpe_proxy_not_acceptable")
    if robustness.verdict != "observation_ready_not_promoted":
        reasons.append(f"robustness_{robustness.verdict}")
    decision = "KEEP_RESEARCH" if len(reasons) == 1 else "REJECTED"
    return FundingBasisStatisticalValidationReport(
        run_id=config.run_id,
        decision=decision,
        reasons=tuple(reasons),
        trade_count=len(records),
        assumed_trial_count=config.assumed_trial_count,
        deflated_sharpe=dsr.to_dict(),
        probabilistic_sharpe=psr.to_dict(),
        robustness=robustness.to_dict(),
    )
