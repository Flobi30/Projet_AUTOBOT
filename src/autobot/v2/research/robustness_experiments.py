"""Research-only robustness diagnostics for closed simulated trades.

The module intentionally works on :class:`TradeRecord` values already produced
by a replay.  It never imports an order router, a broker, or a runtime trading
component.  Its job is to quantify how fragile an already measured result is,
not to select parameters or promote a strategy.
"""

from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Sequence

from .metrics_engine import MetricsEngine, MetricsResult
from .trade_journal import TradeRecord


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class MonteCarloConfig:
    """Deterministic bootstrap settings for one closed-trade sequence."""

    iterations: int = 2_000
    seed: int = 260624
    min_trade_count: int = 50
    confidence_level: float = 0.95

    def __post_init__(self) -> None:
        if self.iterations < 100:
            raise ValueError("Monte Carlo iterations must be at least 100")
        if self.min_trade_count < 1:
            raise ValueError("min_trade_count must be positive")
        if not 0.0 < self.confidence_level < 1.0:
            raise ValueError("confidence_level must be in (0, 1)")


@dataclass(frozen=True)
class CostStressScenario:
    """Conservative research-only cost and adverse-move shock."""

    name: str
    fee_multiplier: float = 1.0
    spread_multiplier: float = 1.0
    slippage_multiplier: float = 1.0
    latency_multiplier: float = 1.0
    fat_tail_loss_multiplier: float = 1.0

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("stress scenario name is required")
        for value in (
            self.fee_multiplier,
            self.spread_multiplier,
            self.slippage_multiplier,
            self.latency_multiplier,
            self.fat_tail_loss_multiplier,
        ):
            if not math.isfinite(float(value)) or float(value) < 1.0:
                raise ValueError("stress multipliers must be finite and at least one")


DEFAULT_COST_STRESS_SCENARIOS: tuple[CostStressScenario, ...] = (
    CostStressScenario(name="base"),
    CostStressScenario(
        name="moderate_execution_shock",
        fee_multiplier=1.10,
        spread_multiplier=1.25,
        slippage_multiplier=1.50,
        latency_multiplier=1.50,
        fat_tail_loss_multiplier=1.10,
    ),
    CostStressScenario(
        name="severe_fat_tail_execution_shock",
        fee_multiplier=1.25,
        spread_multiplier=1.75,
        slippage_multiplier=2.00,
        latency_multiplier=2.00,
        fat_tail_loss_multiplier=1.50,
    ),
)


@dataclass(frozen=True)
class MonteCarloSummary:
    sample_count: int
    iterations: int
    seed: int
    confidence_level: float
    probability_positive_net_pnl: float | None
    net_pnl_p05_eur: float | None
    net_pnl_p50_eur: float | None
    net_pnl_p95_eur: float | None
    profit_factor_p05: float | None
    profit_factor_p50: float | None
    max_drawdown_p50_pct: float | None
    max_drawdown_p95_pct: float | None
    mean_trade_return_lower: float | None
    mean_trade_return_p50: float | None
    mean_trade_return_upper: float | None
    status: str
    mean_trade_return_unit: str = "fraction_of_initial_capital"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StressScenarioResult:
    scenario: CostStressScenario
    metrics: MetricsResult

    def to_dict(self) -> dict[str, Any]:
        return {"scenario": asdict(self.scenario), "metrics": self.metrics.to_dict()}


@dataclass(frozen=True)
class RobustnessExperimentConfig:
    run_id: str
    initial_capital_eur: float = 500.0
    monte_carlo: MonteCarloConfig = MonteCarloConfig()
    scenarios: tuple[CostStressScenario, ...] = DEFAULT_COST_STRESS_SCENARIOS

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id is required")
        if not math.isfinite(float(self.initial_capital_eur)) or self.initial_capital_eur <= 0.0:
            raise ValueError("initial_capital_eur must be positive and finite")
        if not self.scenarios:
            raise ValueError("at least one stress scenario is required")


@dataclass(frozen=True)
class RobustnessExperimentReport:
    run_id: str
    generated_at: str
    trade_count: int
    initial_capital_eur: float
    monte_carlo: MonteCarloSummary
    stress_scenarios: tuple[StressScenarioResult, ...]
    verdict: str
    reasons: tuple[str, ...]
    research_only: bool = True
    paper_candidate_allowed: bool = False
    live_promotion_allowed: bool = False
    json_report_path: str | None = None
    markdown_report_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "trade_count": self.trade_count,
            "initial_capital_eur": self.initial_capital_eur,
            "monte_carlo": self.monte_carlo.to_dict(),
            "stress_scenarios": [item.to_dict() for item in self.stress_scenarios],
            "verdict": self.verdict,
            "reasons": list(self.reasons),
            "research_only": True,
            "paper_candidate_allowed": False,
            "live_promotion_allowed": False,
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
        }


def bootstrap_trade_sequence(
    trades: Sequence[TradeRecord],
    *,
    initial_capital_eur: float,
    config: MonteCarloConfig = MonteCarloConfig(),
) -> MonteCarloSummary:
    """Resample the closed-trade sequence with replacement.

    This is intentionally a trade-sequence bootstrap, not an IID claim about
    market returns.  It highlights sensitivity to order and a small sample; it
    must not be used as a promotion gate by itself.
    """

    if initial_capital_eur <= 0.0:
        raise ValueError("initial_capital_eur must be positive")
    values = [float(trade.net_pnl_eur) for trade in trades if math.isfinite(float(trade.net_pnl_eur))]
    if not values:
        return MonteCarloSummary(
            sample_count=0,
            iterations=config.iterations,
            seed=config.seed,
            confidence_level=config.confidence_level,
            probability_positive_net_pnl=None,
            net_pnl_p05_eur=None,
            net_pnl_p50_eur=None,
            net_pnl_p95_eur=None,
            profit_factor_p05=None,
            profit_factor_p50=None,
            max_drawdown_p50_pct=None,
            max_drawdown_p95_pct=None,
            mean_trade_return_lower=None,
            mean_trade_return_p50=None,
            mean_trade_return_upper=None,
            status="no_closed_trades",
        )

    rng = random.Random(config.seed)
    pnls: list[float] = []
    profit_factors: list[float] = []
    drawdowns: list[float] = []
    mean_trade_returns: list[float] = []
    for _ in range(config.iterations):
        sample = [values[rng.randrange(len(values))] for _ in range(len(values))]
        pnls.append(sum(sample))
        mean_trade_returns.append((sum(sample) / len(sample)) / initial_capital_eur)
        factor = _profit_factor(sample)
        if factor is not None:
            profit_factors.append(factor)
        drawdowns.append(_max_drawdown_pct(sample, initial_capital_eur))

    tail = (1.0 - config.confidence_level) / 2.0
    return MonteCarloSummary(
        sample_count=len(values),
        iterations=config.iterations,
        seed=config.seed,
        confidence_level=config.confidence_level,
        probability_positive_net_pnl=sum(value > 0.0 for value in pnls) / len(pnls),
        net_pnl_p05_eur=_quantile(pnls, 0.05),
        net_pnl_p50_eur=_quantile(pnls, 0.50),
        net_pnl_p95_eur=_quantile(pnls, 0.95),
        profit_factor_p05=_quantile(profit_factors, 0.05),
        profit_factor_p50=_quantile(profit_factors, 0.50),
        max_drawdown_p50_pct=_quantile(drawdowns, 0.50),
        max_drawdown_p95_pct=_quantile(drawdowns, 0.95),
        mean_trade_return_lower=_quantile(mean_trade_returns, tail),
        mean_trade_return_p50=_quantile(mean_trade_returns, 0.50),
        mean_trade_return_upper=_quantile(mean_trade_returns, 1.0 - tail),
        status=("insufficient_sample" if len(values) < config.min_trade_count else "observation_ready"),
    )


def stress_trade_records(
    trades: Sequence[TradeRecord],
    scenario: CostStressScenario,
) -> tuple[TradeRecord, ...]:
    """Return cost- and tail-stressed copies of research trade records."""

    stressed: list[TradeRecord] = []
    for trade in trades:
        fees = trade.fees_eur * scenario.fee_multiplier
        spread = trade.spread_cost_eur * scenario.spread_multiplier
        slippage = trade.slippage_eur * scenario.slippage_multiplier
        latency = trade.latency_cost_eur * scenario.latency_multiplier
        added_cost = (fees + spread + slippage + latency) - (
            trade.fees_eur + trade.spread_cost_eur + trade.slippage_eur + trade.latency_cost_eur
        )
        tail_loss = max(0.0, -trade.gross_pnl_eur) * (scenario.fat_tail_loss_multiplier - 1.0)
        stressed.append(
            replace(
                trade,
                gross_pnl_eur=trade.gross_pnl_eur - tail_loss,
                net_pnl_eur=trade.net_pnl_eur - added_cost - tail_loss,
                fees_eur=fees,
                spread_cost_eur=spread,
                slippage_eur=slippage,
                latency_cost_eur=latency,
                metadata={**trade.metadata, "research_stress_scenario": scenario.name},
            )
        )
    return tuple(stressed)


def build_robustness_experiment_report(
    trades: Sequence[TradeRecord],
    config: RobustnessExperimentConfig,
) -> RobustnessExperimentReport:
    """Build non-promotional bootstrap and cost-shock diagnostics."""

    records = tuple(sorted(trades, key=lambda item: (item.closed_at, item.opened_at, item.symbol)))
    monte_carlo = bootstrap_trade_sequence(
        records,
        initial_capital_eur=config.initial_capital_eur,
        config=config.monte_carlo,
    )
    metrics_engine = MetricsEngine()
    stress = tuple(
        StressScenarioResult(
            scenario=scenario,
            metrics=metrics_engine.calculate(
                stress_trade_records(records, scenario),
                initial_capital_eur=config.initial_capital_eur,
            ),
        )
        for scenario in config.scenarios
    )
    reasons: list[str] = [
        "research_only_no_execution_or_promotion",
        "bootstrap_is_a_robustness_diagnostic_not_a_promotion_gate",
    ]
    if len(records) < config.monte_carlo.min_trade_count:
        verdict = "insufficient_sample"
        reasons.append(f"closed_trade_count_below_{config.monte_carlo.min_trade_count}")
    elif any((item.metrics.total_net_pnl_eur or 0.0) <= 0.0 for item in stress):
        verdict = "fragile_under_stress"
        reasons.append("at_least_one_cost_or_fat_tail_stress_scenario_is_non_positive")
    elif (monte_carlo.probability_positive_net_pnl or 0.0) < 0.55:
        verdict = "fragile_bootstrap_distribution"
        reasons.append("bootstrap_probability_of_positive_net_pnl_below_55_pct")
    else:
        verdict = "observation_ready_not_promoted"
        reasons.append("requires_existing_walk_forward_and_governance_gates")
    return RobustnessExperimentReport(
        run_id=config.run_id,
        generated_at=_utc_now().isoformat(),
        trade_count=len(records),
        initial_capital_eur=config.initial_capital_eur,
        monte_carlo=monte_carlo,
        stress_scenarios=stress,
        verdict=verdict,
        reasons=tuple(reasons),
    )


def write_robustness_experiment_report(
    report: RobustnessExperimentReport,
    output_dir: str | Path,
) -> RobustnessExperimentReport:
    import json

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / f"{report.run_id}.json"
    markdown_path = output / f"{report.run_id}.md"
    final = replace(report, json_report_path=str(json_path), markdown_report_path=str(markdown_path))
    json_path.write_text(json.dumps(final.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(render_robustness_experiment_report(final), encoding="utf-8")
    return final


def render_robustness_experiment_report(report: RobustnessExperimentReport) -> str:
    monte = report.monte_carlo
    lines = [
        f"# Research Robustness Diagnostics - {report.run_id}",
        "",
        "- Scope: `research_only`; closed simulated trades only.",
        "- No runtime/paper/live order path, promotion, or instance creation is invoked.",
        f"- Closed trades: `{report.trade_count}`; virtual starting capital: `{report.initial_capital_eur:.2f} EUR`.",
        "",
        "## Bootstrap Trade Sequence",
        "",
        f"- Status: `{monte.status}`; iterations: `{monte.iterations}`; sample: `{monte.sample_count}`.",
        f"- Seed / confidence: `{monte.seed}` / `{monte.confidence_level:.2%}`.",
        f"- Probability positive net PnL: `{_fmt_pct(monte.probability_positive_net_pnl)}`.",
        f"- Net PnL P05 / P50 / P95: `{_fmt(monte.net_pnl_p05_eur)}` / `{_fmt(monte.net_pnl_p50_eur)}` / `{_fmt(monte.net_pnl_p95_eur)}` EUR.",
        f"- PF P05 / P50: `{_fmt(monte.profit_factor_p05)}` / `{_fmt(monte.profit_factor_p50)}`.",
        f"- Max DD P50 / P95: `{_fmt(monte.max_drawdown_p50_pct)}` / `{_fmt(monte.max_drawdown_p95_pct)}` %.",
        f"- Mean trade return CI ({monte.mean_trade_return_unit}) lower / P50 / upper: "
        f"`{_fmt(monte.mean_trade_return_lower)}` / `{_fmt(monte.mean_trade_return_p50)}` / `{_fmt(monte.mean_trade_return_upper)}`.",
        "",
        "## Cost and Fat-tail Stress",
        "",
        "| Scenario | Net PnL EUR | PF | Max DD % | Fees EUR | Spread EUR | Slippage EUR | Latency EUR |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in report.stress_scenarios:
        metrics = item.metrics
        lines.append(
            f"| {item.scenario.name} | {_fmt(metrics.total_net_pnl_eur)} | {_fmt(metrics.profit_factor)} | "
            f"{_fmt(metrics.max_drawdown_pct)} | {_fmt(metrics.total_fees_eur)} | "
            f"{_fmt(metrics.total_spread_cost_eur)} | {_fmt(metrics.total_slippage_eur)} | "
            f"{_fmt(metrics.total_latency_cost_eur)} |"
        )
    lines.extend(["", "## Verdict", "", f"`{report.verdict}`", ""])
    lines.extend(f"- {reason}" for reason in report.reasons)
    lines.extend(["", "## Safety", "", "- paper_candidate_allowed: `false`", "- live_promotion_allowed: `false`", ""])
    return "\n".join(lines)


def _profit_factor(values: Sequence[float]) -> float | None:
    wins = sum(value for value in values if value > 0.0)
    losses = abs(sum(value for value in values if value < 0.0))
    if losses <= 0.0:
        return None
    return wins / losses


def _max_drawdown_pct(values: Sequence[float], initial_capital_eur: float) -> float:
    equity = float(initial_capital_eur)
    peak = equity
    max_drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        if peak > 0.0:
            max_drawdown = max(max_drawdown, ((peak - equity) / peak) * 100.0)
    return max_drawdown


def _quantile(values: Sequence[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    location = (len(ordered) - 1) * quantile
    lower = int(math.floor(location))
    upper = int(math.ceil(location))
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (location - lower)


def _fmt(value: float | None) -> str:
    return "-" if value is None else f"{value:.4f}"


def _fmt_pct(value: float | None) -> str:
    return "-" if value is None else f"{value * 100.0:.2f}%"
