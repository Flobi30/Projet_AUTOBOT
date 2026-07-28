"""Research-only statistical gate for volatility-reversal OOS trades.

This module consumes only closed records emitted by the fixed-template
walk-forward adapter.  It neither selects parameters nor imports execution,
paper, runtime, or order-routing code.  A passing result is merely research
evidence for a later human shadow review; it is not a promotion decision.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence

from .alpha_hypothesis_lab import RESEARCH_ONLY_CAPITAL_FLAGS
from .generic_cross_sectional_ohlcv_adapter import CrossSectionalTrade
from .robustness_experiments import (
    MonteCarloConfig,
    RobustnessExperimentConfig,
    build_robustness_experiment_report,
)
from .statistical_gate_summary import (
    StatisticalGateConfig,
    StatisticalGateEvidence,
    summarize_statistical_gate,
)
from .statistical_validation import (
    DeflatedSharpeConfig,
    ProbabilisticSharpeConfig,
    assess_deflated_sharpe,
    assess_probabilistic_sharpe,
)
from .trade_journal import TradeRecord


@dataclass(frozen=True)
class VolatilityReversalStatisticalValidationConfig:
    run_id: str
    assumed_trial_count: int
    initial_capital_eur: float = 500.0
    min_trade_count: int = 50
    bootstrap_iterations: int = 1_000
    seed: int = 260729
    trial_scope_id: str = "hypothesis_mean_reversion_volatility_reversal"

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id is required")
        if self.assumed_trial_count < 1:
            raise ValueError("assumed_trial_count must be positive")
        scope_id = str(self.trial_scope_id or "").strip().lower()
        if not scope_id or not all(character.isalnum() or character in "_.-" for character in scope_id):
            raise ValueError("trial_scope_id must contain only letters, digits, _, . or -")
        object.__setattr__(self, "trial_scope_id", scope_id)
        if self.initial_capital_eur <= 0.0:
            raise ValueError("initial_capital_eur must be positive")
        if self.min_trade_count < 2:
            raise ValueError("min_trade_count must be at least two")
        if self.bootstrap_iterations < 100:
            raise ValueError("bootstrap_iterations must be at least 100")


@dataclass(frozen=True)
class VolatilityReversalStatisticalValidationReport:
    run_id: str
    decision: str
    reasons: tuple[str, ...]
    trade_count: int
    assumed_trial_count: int
    deflated_sharpe: Mapping[str, Any]
    probabilistic_sharpe: Mapping[str, Any]
    robustness: Mapping[str, Any]
    trial_scope_id: str = "hypothesis_mean_reversion_volatility_reversal"
    statistical_gate: Mapping[str, Any] = field(default_factory=dict)
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
            "statistical_gate": dict(self.statistical_gate),
            "safety": dict(self.safety),
            "paper_capital_allowed": False,
            "live_allowed": False,
            "promotable": False,
        }


def volatility_reversal_trade_records(
    trades: Sequence[CrossSectionalTrade],
    *,
    run_id: str,
    strategy_id: str = "mean_reversion_volatility_reversal",
) -> tuple[TradeRecord, ...]:
    """Convert complete OOS evidence without inventing fill prices or costs."""

    records: list[TradeRecord] = []
    required_costs = ("fees_eur", "spread_cost_eur", "slippage_eur", "latency_cost_eur")
    for trade in trades:
        metadata = dict(trade.metadata)
        entry_price = _finite_positive(metadata.get("entry_price"), "entry_price")
        exit_price = _finite_positive(metadata.get("exit_price"), "exit_price")
        notional = _finite_positive(metadata.get("order_notional_eur"), "order_notional_eur")
        costs = metadata.get("cost_components_eur")
        if not isinstance(costs, Mapping):
            raise ValueError("cost_components_eur_missing")
        cost_values = {key: _finite_non_negative(costs.get(key), key) for key in required_costs}
        explicit_cost = sum(cost_values.values())
        expected_cost = float(trade.gross_pnl_eur) - float(trade.net_pnl_eur)
        if not math.isclose(explicit_cost, expected_cost, rel_tol=1e-8, abs_tol=1e-8):
            raise ValueError("explicit_cost_does_not_match_net_pnl")
        cost_bps = metadata.get("cost_components_bps")
        if not isinstance(cost_bps, Mapping):
            raise ValueError("cost_bps_evidence_missing_or_mismatched")
        if not math.isclose(
            sum(
                _finite_non_negative(value, "cost_bps_evidence_missing_or_mismatched")
                for value in cost_bps.values()
            ),
            trade.cost_bps,
            rel_tol=1e-8,
            abs_tol=1e-8,
        ):
            raise ValueError("cost_bps_evidence_missing_or_mismatched")
        records.append(
            TradeRecord(
                run_id=run_id,
                strategy_id=strategy_id,
                symbol=trade.symbol,
                side="buy",
                opened_at=trade.opened_at,
                closed_at=trade.closed_at,
                quantity=notional / entry_price,
                entry_price=entry_price,
                exit_price=exit_price,
                gross_pnl_eur=trade.gross_pnl_eur,
                net_pnl_eur=trade.net_pnl_eur,
                fees_eur=cost_values["fees_eur"],
                spread_cost_eur=cost_values["spread_cost_eur"],
                slippage_eur=cost_values["slippage_eur"],
                latency_cost_eur=cost_values["latency_cost_eur"],
                entry_reason="downside_extension_range_reversion",
                exit_reason=str(metadata.get("exit_reason") or "bounded_research_exit"),
                regime=str(metadata.get("regime") or "range_like"),
                metadata={
                    **metadata,
                    "source": "volatility_reversal_walk_forward_oos",
                    "research_only": True,
                },
            )
        )
    return tuple(records)


def build_volatility_reversal_statistical_validation_report(
    trades: Sequence[CrossSectionalTrade],
    config: VolatilityReversalStatisticalValidationConfig,
    *,
    walk_forward_passed: bool,
) -> VolatilityReversalStatisticalValidationReport:
    """Assess fixed OOS evidence after a successful walk-forward only."""

    if not walk_forward_passed:
        return _empty_report(config, "INSUFFICIENT_DATA", ("walk_forward_gate_not_passed",))
    try:
        records = volatility_reversal_trade_records(trades, run_id=config.run_id)
    except ValueError as exc:
        return _empty_report(config, "REJECTED", (f"oos_trade_evidence_invalid:{exc}",))
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
    statistical_gate = summarize_statistical_gate(
        StatisticalGateEvidence(
            trade_count=len(records),
            trial_count=config.assumed_trial_count,
            net_pnl_eur=sum(record.net_pnl_eur for record in records),
            out_of_sample_confirmed=True,
            net_of_costs=True,
            probabilistic_sharpe=psr,
            deflated_sharpe=dsr,
            robustness=robustness,
        ),
        StatisticalGateConfig(min_trade_count=config.min_trade_count),
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
    if not statistical_gate.shadow_review_eligible:
        reasons.append("consolidated_statistical_gate_blocked")
        reasons.extend(f"statistical_gate_{blocker}" for blocker in statistical_gate.blockers)
    return VolatilityReversalStatisticalValidationReport(
        run_id=config.run_id,
        decision="KEEP_RESEARCH" if len(reasons) == 1 else "REJECTED",
        reasons=tuple(dict.fromkeys(reasons)),
        trade_count=len(records),
        assumed_trial_count=config.assumed_trial_count,
        trial_scope_id=config.trial_scope_id,
        deflated_sharpe=dsr.to_dict(),
        probabilistic_sharpe=psr.to_dict(),
        robustness=robustness.to_dict(),
        statistical_gate=statistical_gate.to_dict(),
    )


def _empty_report(
    config: VolatilityReversalStatisticalValidationConfig,
    decision: str,
    reasons: tuple[str, ...],
) -> VolatilityReversalStatisticalValidationReport:
    return VolatilityReversalStatisticalValidationReport(
        run_id=config.run_id,
        decision=decision,
        reasons=reasons,
        trade_count=0,
        assumed_trial_count=config.assumed_trial_count,
        trial_scope_id=config.trial_scope_id,
        deflated_sharpe={},
        probabilistic_sharpe={},
        robustness={},
        statistical_gate={},
    )


def _finite_positive(value: object, field_name: str) -> float:
    numeric = _finite_non_negative(value, field_name)
    if numeric <= 0.0:
        raise ValueError(f"{field_name}_must_be_positive")
    return numeric


def _finite_non_negative(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"{field_name}_missing_or_invalid")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name}_missing_or_invalid") from exc
    if not math.isfinite(numeric) or numeric < 0.0:
        raise ValueError(f"{field_name}_missing_or_invalid")
    return numeric
