"""Research-only statistical validation helpers for AUTOBOT.

The functions in this module score already-produced research trades and
metrics.  They do not import runtime trading, paper execution, Kraken clients,
or persistence layers, and they never promote a strategy by themselves.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from statistics import NormalDist, mean, pstdev
from typing import Any, Mapping, Sequence

from .trade_journal import TradeRecord


RESEARCH_DECISIONS = (
    "no_trade_research",
    "observe_research",
    "simulated_allocation_low",
    "simulated_allocation_medium",
    "simulated_allocation_high",
    "candidate_review_blocked",
    "candidate_review_possible",
    "high_quality_candidate",
    "paper_limited_future",
    "scale_candidate_future",
)


@dataclass(frozen=True)
class DeflatedSharpeConfig:
    """Conservative DSR proxy inputs.

    ``assumed_trial_count`` is explicit because the real number of tried
    variants is rarely available in a small research report.  The result labels
    itself as a proxy and should be treated as one guard among several.
    """

    initial_capital_eur: float = 500.0
    assumed_trial_count: int = 8
    min_trade_count: int = 50
    acceptable_probability: float = 0.65

    def __post_init__(self) -> None:
        if not math.isfinite(self.initial_capital_eur) or self.initial_capital_eur <= 0.0:
            raise ValueError("initial_capital_eur must be positive and finite")
        if self.assumed_trial_count < 1:
            raise ValueError("assumed_trial_count must be at least one")
        if self.min_trade_count < 2:
            raise ValueError("min_trade_count must be at least two")
        if not 0.0 < self.acceptable_probability < 1.0:
            raise ValueError("acceptable_probability must be in (0, 1)")


@dataclass(frozen=True)
class DeflatedSharpeResult:
    sample_count: int
    sharpe_like: float | None
    expected_max_sharpe: float | None
    deflated_sharpe_probability: float | None
    skewness: float | None
    kurtosis: float | None
    assumed_trial_count: int
    status: str
    overfitting_risk_score: float
    acceptable: bool
    method: str = "deflated_sharpe_proxy"
    research_only: bool = True
    paper_candidate_allowed: bool = False
    live_promotion_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["research_only"] = True
        payload["paper_candidate_allowed"] = False
        payload["live_promotion_allowed"] = False
        return payload


@dataclass(frozen=True)
class PFQualityAssessment:
    strategy_name: str
    decision: str
    profit_factor_quality_score: float
    reasons: tuple[str, ...]
    blockers: tuple[str, ...]
    gates_passed: tuple[str, ...]
    metrics: Mapping[str, Any]
    research_only: bool = True
    paper_candidate_allowed: bool = False
    live_promotion_allowed: bool = False

    def __post_init__(self) -> None:
        if self.decision not in RESEARCH_DECISIONS:
            raise ValueError(f"unsupported research decision: {self.decision}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_name": self.strategy_name,
            "decision": self.decision,
            "profit_factor_quality_score": round(self.profit_factor_quality_score, 6),
            "reasons": list(self.reasons),
            "blockers": list(self.blockers),
            "gates_passed": list(self.gates_passed),
            "metrics": dict(self.metrics),
            "research_only": True,
            "paper_candidate_allowed": False,
            "live_promotion_allowed": False,
        }


def assess_deflated_sharpe(
    trades: Sequence[TradeRecord],
    config: DeflatedSharpeConfig = DeflatedSharpeConfig(),
) -> DeflatedSharpeResult:
    """Estimate DSR-like overfitting risk from closed research trades.

    This is intentionally labelled a proxy: it uses per-trade returns and an
    explicit assumed trial count.  It is useful for ranking caution, not for
    academic certification or live promotion.
    """

    returns = [
        float(trade.net_pnl_eur) / config.initial_capital_eur
        for trade in trades
        if math.isfinite(float(trade.net_pnl_eur))
    ]
    if len(returns) < 2:
        return DeflatedSharpeResult(
            sample_count=len(returns),
            sharpe_like=None,
            expected_max_sharpe=None,
            deflated_sharpe_probability=None,
            skewness=None,
            kurtosis=None,
            assumed_trial_count=config.assumed_trial_count,
            status="insufficient_sample",
            overfitting_risk_score=100.0,
            acceptable=False,
        )

    deviation = pstdev(returns)
    if deviation <= 0.0:
        return DeflatedSharpeResult(
            sample_count=len(returns),
            sharpe_like=None,
            expected_max_sharpe=None,
            deflated_sharpe_probability=None,
            skewness=None,
            kurtosis=None,
            assumed_trial_count=config.assumed_trial_count,
            status="zero_return_variance",
            overfitting_risk_score=100.0,
            acceptable=False,
        )

    sample_mean = mean(returns)
    sharpe = sample_mean / deviation * math.sqrt(len(returns))
    skew = _skewness(returns)
    kurt = _kurtosis(returns)
    expected_max = _expected_max_sharpe(config.assumed_trial_count)
    standard_error = _sharpe_standard_error(
        sharpe=sharpe,
        skewness=skew,
        kurtosis=kurt,
        sample_count=len(returns),
    )
    probability = NormalDist().cdf((sharpe - expected_max) / standard_error)
    probability = _clamp(probability, 0.0, 1.0)
    insufficient = len(returns) < config.min_trade_count
    acceptable = (not insufficient) and probability >= config.acceptable_probability
    if insufficient:
        status = "insufficient_sample"
    elif acceptable:
        status = "acceptable_proxy"
    else:
        status = "overfitting_risk_high"
    risk = 100.0 - (probability * 100.0)
    if insufficient:
        risk = max(risk, 70.0)
    return DeflatedSharpeResult(
        sample_count=len(returns),
        sharpe_like=sharpe,
        expected_max_sharpe=expected_max,
        deflated_sharpe_probability=probability,
        skewness=skew,
        kurtosis=kurt,
        assumed_trial_count=config.assumed_trial_count,
        status=status,
        overfitting_risk_score=round(_clamp(risk, 0.0, 100.0), 6),
        acceptable=acceptable,
    )


def evaluate_progressive_pf_quality(
    *,
    strategy_name: str,
    status: str,
    metrics: Mapping[str, Any],
    robustness: Mapping[str, Any] | None = None,
    deflated_sharpe: Mapping[str, Any] | DeflatedSharpeResult | None = None,
    available_cash_eur: float | None = None,
) -> PFQualityAssessment:
    """Apply AUTOBOT's progressive research gates without promotion."""

    normalized = _normal_metrics(metrics)
    reasons: list[str] = ["progressive_pf_gate_research_only"]
    blockers: list[str] = []
    gates: list[str] = []

    if status in {"archived", "no_go"}:
        return PFQualityAssessment(
            strategy_name=strategy_name,
            decision="no_trade_research",
            profit_factor_quality_score=0.0,
            reasons=("strategy_status_not_tradeable",),
            blockers=(f"status_{status}",),
            gates_passed=(),
            metrics=normalized,
        )
    if status == "research_signal_only":
        return PFQualityAssessment(
            strategy_name=strategy_name,
            decision="observe_research",
            profit_factor_quality_score=0.0,
            reasons=("strategy_signal_only_no_capital",),
            blockers=("no_portfolio_validated_evidence",),
            gates_passed=(),
            metrics=normalized,
        )

    trade_count = int(normalized["trade_count"])
    profit_factor = float(normalized["profit_factor"])
    drawdown = float(normalized["max_drawdown_pct"])
    folds = int(normalized["total_folds"])
    positive_folds = int(normalized["positive_folds"])
    concentration = float(normalized["largest_positive_symbol_share"])
    validation_days = int(normalized["validation_days"])
    costs_covered = bool(normalized["costs_covered"])
    runtime_comparable = bool(normalized["runtime_comparable"])
    net_pnl = float(normalized["net_pnl_eur"])
    fold_ratio_ok = folds >= 5 and positive_folds >= 4
    stress_positive = _stress_positive(robustness)
    mc_positive = _monte_carlo_positive(robustness)
    dsr_payload = deflated_sharpe.to_dict() if isinstance(deflated_sharpe, DeflatedSharpeResult) else dict(deflated_sharpe or {})
    dsr_acceptable = bool(dsr_payload.get("acceptable"))
    overfit_score = _float(dsr_payload.get("overfitting_risk_score"), 100.0)

    if profit_factor > 1.10:
        gates.append("A_active_research_pf_above_1_10")
    else:
        blockers.append("pf_not_above_active_research_1_10")
    if net_pnl <= 0.0:
        blockers.append("net_pnl_not_positive")
    if not costs_covered:
        blockers.append("costs_not_covered")
    if not runtime_comparable:
        blockers.append("cost_profile_not_runtime_comparable")
    if available_cash_eur is not None and available_cash_eur < 5.0:
        blockers.append("instance_treasury_insufficient")

    candidate_blockers = _gate_blockers(
        trade_count=trade_count,
        min_trades=50,
        profit_factor=profit_factor,
        min_profit_factor=1.30,
        drawdown=drawdown,
        max_drawdown=10.0,
        folds_ok=fold_ratio_ok,
        concentration=concentration,
        max_concentration=0.40,
        validation_days=validation_days,
        min_validation_days=1,
        costs_covered=costs_covered,
        runtime_comparable=runtime_comparable,
        stress_required=False,
        stress_positive=stress_positive,
        dsr_required=False,
        dsr_acceptable=dsr_acceptable,
    )
    if not candidate_blockers:
        gates.append("B_candidate_review_possible")

    high_blockers = _gate_blockers(
        trade_count=trade_count,
        min_trades=75,
        profit_factor=profit_factor,
        min_profit_factor=1.50,
        drawdown=drawdown,
        max_drawdown=8.0,
        folds_ok=fold_ratio_ok,
        concentration=concentration,
        max_concentration=0.40,
        validation_days=validation_days,
        min_validation_days=1,
        costs_covered=costs_covered,
        runtime_comparable=runtime_comparable,
        stress_required=True,
        stress_positive=stress_positive,
        dsr_required=True,
        dsr_acceptable=dsr_acceptable,
        mc_required=True,
        mc_positive=mc_positive,
    )
    if not high_blockers:
        gates.append("C_high_quality_candidate")

    paper_blockers = _gate_blockers(
        trade_count=trade_count,
        min_trades=100,
        profit_factor=profit_factor,
        min_profit_factor=1.70,
        drawdown=drawdown,
        max_drawdown=7.0,
        folds_ok=fold_ratio_ok,
        concentration=concentration,
        max_concentration=0.40,
        validation_days=validation_days,
        min_validation_days=7,
        costs_covered=costs_covered,
        runtime_comparable=runtime_comparable,
        stress_required=True,
        stress_positive=stress_positive,
        dsr_required=True,
        dsr_acceptable=dsr_acceptable,
        mc_required=True,
        mc_positive=mc_positive,
        overfit_score=overfit_score,
        max_overfit_score=35.0,
    )
    if not paper_blockers:
        gates.append("D_paper_limited_future")

    scale_blockers = _gate_blockers(
        trade_count=trade_count,
        min_trades=150,
        profit_factor=profit_factor,
        min_profit_factor=2.00,
        drawdown=drawdown,
        max_drawdown=6.0,
        folds_ok=fold_ratio_ok,
        concentration=concentration,
        max_concentration=0.40,
        validation_days=validation_days,
        min_validation_days=7,
        costs_covered=costs_covered,
        runtime_comparable=runtime_comparable,
        stress_required=True,
        stress_positive=stress_positive,
        dsr_required=True,
        dsr_acceptable=dsr_acceptable,
        mc_required=True,
        mc_positive=mc_positive,
        overfit_score=overfit_score,
        max_overfit_score=30.0,
    )
    if not scale_blockers:
        gates.append("E_scale_candidate_future")

    decision = "candidate_review_blocked"
    blocking_source = candidate_blockers
    if "E_scale_candidate_future" in gates:
        decision = "scale_candidate_future"
        blocking_source = ()
    elif "D_paper_limited_future" in gates:
        decision = "paper_limited_future"
        blocking_source = ()
    elif "C_high_quality_candidate" in gates:
        decision = "high_quality_candidate"
        blocking_source = ()
    elif "B_candidate_review_possible" in gates:
        decision = "candidate_review_possible"
        blocking_source = ()
    elif "A_active_research_pf_above_1_10" in gates:
        decision = "observe_research"
        blocking_source = candidate_blockers

    blockers.extend(item for item in blocking_source if item not in blockers)
    score = _pf_quality_score(
        trade_count=trade_count,
        profit_factor=profit_factor,
        drawdown=drawdown,
        positive_folds=positive_folds,
        total_folds=folds,
        concentration=concentration,
        stress_positive=stress_positive,
        dsr_acceptable=dsr_acceptable,
        mc_positive=mc_positive,
    )
    normalized["stress_positive"] = stress_positive
    normalized["monte_carlo_positive"] = mc_positive
    normalized["dsr_acceptable"] = dsr_acceptable
    normalized["overfitting_risk_score"] = overfit_score
    return PFQualityAssessment(
        strategy_name=strategy_name,
        decision=decision,
        profit_factor_quality_score=score,
        reasons=tuple(reasons),
        blockers=tuple(dict.fromkeys(blockers)),
        gates_passed=tuple(gates),
        metrics=normalized,
    )


def _normal_metrics(metrics: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "trade_count": int(_float(metrics.get("trade_count"), 0.0)),
        "signal_count": int(_float(metrics.get("signal_count"), 0.0)),
        "net_pnl_eur": _float(metrics.get("net_pnl_eur", metrics.get("total_net_pnl_eur")), 0.0),
        "profit_factor": _float(metrics.get("profit_factor"), 0.0),
        "winrate_pct": _float(metrics.get("winrate_pct"), 0.0),
        "max_drawdown_pct": _float(metrics.get("max_drawdown_pct"), 100.0),
        "positive_folds": int(_float(metrics.get("positive_folds", metrics.get("positive_fold_count")), 0.0)),
        "total_folds": int(_float(metrics.get("total_folds", metrics.get("fold_count")), 0.0)),
        "largest_positive_symbol_share": _float(metrics.get("largest_positive_symbol_share"), 1.0),
        "validation_days": int(_float(metrics.get("validation_days"), 0.0)),
        "costs_covered": bool(metrics.get("costs_covered")),
        "runtime_comparable": bool(metrics.get("runtime_comparable", True)),
    }


def _gate_blockers(
    *,
    trade_count: int,
    min_trades: int,
    profit_factor: float,
    min_profit_factor: float,
    drawdown: float,
    max_drawdown: float,
    folds_ok: bool,
    concentration: float,
    max_concentration: float,
    validation_days: int,
    min_validation_days: int,
    costs_covered: bool,
    runtime_comparable: bool,
    stress_required: bool,
    stress_positive: bool,
    dsr_required: bool,
    dsr_acceptable: bool,
    mc_required: bool = False,
    mc_positive: bool = False,
    overfit_score: float | None = None,
    max_overfit_score: float | None = None,
) -> tuple[str, ...]:
    blockers: list[str] = []
    if trade_count < min_trades:
        blockers.append(f"trade_count_below_{min_trades}")
    if profit_factor <= min_profit_factor:
        blockers.append(f"profit_factor_not_above_{str(min_profit_factor).replace('.', '_')}")
    if drawdown > max_drawdown:
        blockers.append(f"max_drawdown_above_{str(max_drawdown).replace('.', '_')}_pct")
    if not folds_ok:
        blockers.append("fewer_than_4_of_5_positive_folds")
    if concentration > max_concentration:
        blockers.append("single_symbol_positive_pnl_above_40_pct")
    if validation_days < min_validation_days:
        blockers.append(f"validation_days_below_{min_validation_days}")
    if not costs_covered:
        blockers.append("costs_not_covered")
    if not runtime_comparable:
        blockers.append("cost_profile_not_runtime_comparable")
    if stress_required and not stress_positive:
        blockers.append("stress_result_not_positive")
    if dsr_required and not dsr_acceptable:
        blockers.append("deflated_sharpe_not_acceptable")
    if mc_required and not mc_positive:
        blockers.append("monte_carlo_survival_not_positive")
    if max_overfit_score is not None and overfit_score is not None and overfit_score > max_overfit_score:
        blockers.append(f"overfitting_risk_above_{int(max_overfit_score)}")
    return tuple(blockers)


def _pf_quality_score(
    *,
    trade_count: int,
    profit_factor: float,
    drawdown: float,
    positive_folds: int,
    total_folds: int,
    concentration: float,
    stress_positive: bool,
    dsr_acceptable: bool,
    mc_positive: bool,
) -> float:
    fold_ratio = (positive_folds / total_folds) if total_folds else 0.0
    score = (
        min(max(profit_factor - 1.0, 0.0) / 1.0, 1.0) * 30.0
        + min(trade_count / 150.0, 1.0) * 20.0
        + max(0.0, 1.0 - drawdown / 12.0) * 15.0
        + min(fold_ratio / 0.80, 1.0) * 15.0
        + max(0.0, 1.0 - concentration / 0.40) * 10.0
        + (4.0 if stress_positive else 0.0)
        + (3.0 if dsr_acceptable else 0.0)
        + (3.0 if mc_positive else 0.0)
    )
    return round(_clamp(score, 0.0, 100.0), 6)


def _stress_positive(robustness: Mapping[str, Any] | None) -> bool:
    if not robustness:
        return False
    scenarios = robustness.get("stress_scenarios") or ()
    if not scenarios:
        return False
    for item in scenarios:
        metrics = dict(item.get("metrics") or {})
        if _float(metrics.get("total_net_pnl_eur"), -1.0) <= 0.0:
            return False
        pf = _float(metrics.get("profit_factor"), 0.0)
        if pf <= 1.0:
            return False
    return True


def _monte_carlo_positive(robustness: Mapping[str, Any] | None) -> bool:
    if not robustness:
        return False
    monte = dict(robustness.get("monte_carlo") or {})
    probability = _float(monte.get("probability_positive_net_pnl"), 0.0)
    return probability >= 0.55 and str(monte.get("status")) == "observation_ready"


def _expected_max_sharpe(assumed_trial_count: int) -> float:
    if assumed_trial_count <= 1:
        return 0.0
    distribution = NormalDist()
    count = float(assumed_trial_count)
    euler_gamma = 0.5772156649015329
    left = distribution.inv_cdf(max(1e-9, min(1.0 - 1e-9, 1.0 - 1.0 / count)))
    right = distribution.inv_cdf(max(1e-9, min(1.0 - 1e-9, 1.0 - 1.0 / (count * math.e))))
    return ((1.0 - euler_gamma) * left) + (euler_gamma * right)


def _sharpe_standard_error(
    *,
    sharpe: float,
    skewness: float,
    kurtosis: float,
    sample_count: int,
) -> float:
    numerator = 1.0 - (skewness * sharpe) + (((kurtosis - 1.0) / 4.0) * sharpe * sharpe)
    return math.sqrt(max(numerator, 1e-9) / max(sample_count - 1, 1))


def _skewness(values: Sequence[float]) -> float:
    deviation = pstdev(values)
    if deviation <= 0.0:
        return 0.0
    center = mean(values)
    return mean(((value - center) / deviation) ** 3 for value in values)


def _kurtosis(values: Sequence[float]) -> float:
    deviation = pstdev(values)
    if deviation <= 0.0:
        return 3.0
    center = mean(values)
    return mean(((value - center) / deviation) ** 4 for value in values)


def _float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, float(value)))
