"""Conservative strategy scorecards for AUTOBOT research evidence.

The scorecard converts validation evidence into an operational tier. It is a
research/governance helper only: it never promotes a strategy to live and never
changes the runtime router, paper engine, or registry by itself.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from .metrics_engine import MetricsResult
from .validation_matrix import MatrixCellResult, MatrixRunResult
from .walk_forward import WalkForwardResult


@dataclass(frozen=True)
class StrategyScorecardCriteria:
    """Thresholds used to classify research evidence."""

    min_backtest_trades: int = 30
    min_paper_trades: int = 100
    min_profit_factor: float = 1.25
    paper_min_profit_factor: float = 1.20
    max_drawdown_pct: float = 12.0
    paper_max_drawdown_pct: float = 10.0
    min_score_for_backtest_only: float = 50.0
    min_score_for_shadow_only: float = 65.0
    min_score_for_paper_allowed: float = 75.0
    min_score_for_human_live_review: float = 85.0

    def __post_init__(self) -> None:
        if self.min_backtest_trades <= 0:
            raise ValueError("min_backtest_trades must be positive")
        if self.min_paper_trades <= 0:
            raise ValueError("min_paper_trades must be positive")
        if self.min_profit_factor <= 1.0:
            raise ValueError("min_profit_factor must be greater than 1")
        if self.paper_min_profit_factor <= 1.0:
            raise ValueError("paper_min_profit_factor must be greater than 1")
        if self.max_drawdown_pct <= 0.0:
            raise ValueError("max_drawdown_pct must be positive")
        if self.paper_max_drawdown_pct <= 0.0:
            raise ValueError("paper_max_drawdown_pct must be positive")


@dataclass(frozen=True)
class StrategyEvidence:
    """Normalized evidence for one strategy or strategy bucket."""

    strategy_id: str
    source: str
    closed_trades: int
    net_pnl_eur: float
    gross_pnl_eur: float | None = None
    profit_factor: float | None = None
    expectancy_eur: float | None = None
    max_drawdown_pct: float | None = None
    total_return_pct: float | None = None
    baseline_delta_pct: float | None = None
    baseline_delta_eur: float | None = None
    passing_folds: int | None = None
    total_folds: int | None = None
    regimes_tested: int = 0
    positive_regimes: int = 0
    fees_included: bool = True
    slippage_included: bool = True
    baseline_included: bool = True
    out_of_sample_included: bool = False
    paper_evidence: bool = False
    contract_signal_boundary_enforced: bool = True
    research_only_evidence: bool = False
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.strategy_id:
            raise ValueError("strategy_id must not be empty")
        if self.closed_trades < 0:
            raise ValueError("closed_trades must not be negative")
        if self.regimes_tested < 0:
            raise ValueError("regimes_tested must not be negative")
        if self.positive_regimes < 0:
            raise ValueError("positive_regimes must not be negative")
        if self.positive_regimes > self.regimes_tested:
            raise ValueError("positive_regimes cannot exceed regimes_tested")

    @classmethod
    def from_metrics(
        cls,
        strategy_id: str,
        metrics: MetricsResult,
        *,
        source: str = "backtest",
        fees_included: bool = True,
        slippage_included: bool = True,
        baseline_included: bool | None = None,
        out_of_sample_included: bool = False,
        paper_evidence: bool = False,
        notes: Iterable[str] = (),
    ) -> "StrategyEvidence":
        baseline_present = baseline_included
        if baseline_present is None:
            baseline_present = metrics.baseline_name is not None and metrics.baseline_delta_pct is not None
        performance_by_regime = metrics.performance_by_regime or {}
        positive_regimes = sum(1 for item in performance_by_regime.values() if (item.get("net_pnl_eur") or 0.0) > 0.0)
        return cls(
            strategy_id=strategy_id,
            source=source,
            closed_trades=metrics.closed_trade_count,
            net_pnl_eur=metrics.total_net_pnl_eur,
            gross_pnl_eur=metrics.total_gross_pnl_eur,
            profit_factor=metrics.profit_factor,
            expectancy_eur=metrics.expectancy_eur,
            max_drawdown_pct=metrics.max_drawdown_pct,
            total_return_pct=metrics.total_return_pct,
            baseline_delta_pct=metrics.baseline_delta_pct,
            regimes_tested=len(performance_by_regime),
            positive_regimes=positive_regimes,
            fees_included=fees_included,
            slippage_included=slippage_included,
            baseline_included=baseline_present,
            out_of_sample_included=out_of_sample_included,
            paper_evidence=paper_evidence,
            notes=tuple(notes),
        )

    @classmethod
    def from_walk_forward(
        cls,
        result: WalkForwardResult,
        *,
        fees_included: bool = True,
        slippage_included: bool = True,
        baseline_included: bool = True,
        notes: Iterable[str] = (),
    ) -> "StrategyEvidence":
        return cls(
            strategy_id=result.strategy_id,
            source="walk_forward",
            closed_trades=result.total_closed_trades,
            net_pnl_eur=result.aggregate_net_pnl_eur,
            profit_factor=None,
            max_drawdown_pct=result.worst_fold_drawdown_pct,
            total_return_pct=result.average_fold_return_pct,
            passing_folds=result.passing_fold_count,
            total_folds=result.fold_count,
            fees_included=fees_included,
            slippage_included=slippage_included,
            baseline_included=baseline_included,
            out_of_sample_included=True,
            paper_evidence=False,
            notes=tuple(notes),
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["notes"] = list(self.notes)
        return data


@dataclass(frozen=True)
class StrategyScorecardResult:
    strategy_id: str
    source: str
    score: float
    tier: str
    recommended_status: str
    decision: str
    reason: str
    live_promotion_allowed: bool
    blockers: tuple[str, ...] = ()
    caps_applied: tuple[str, ...] = ()
    evidence: StrategyEvidence | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["blockers"] = list(self.blockers)
        data["caps_applied"] = list(self.caps_applied)
        data["evidence"] = self.evidence.to_dict() if self.evidence else None
        return data


@dataclass(frozen=True)
class StrategyScorecardReport:
    run_id: str
    source: str
    results: tuple[StrategyScorecardResult, ...]
    json_report_path: str | None = None
    markdown_report_path: str | None = None
    safety_notes: tuple[str, ...] = field(
        default=(
            "Research-only scorecard.",
            "No strategy registry mutation is performed.",
            "No live trading permission is granted.",
        )
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "source": self.source,
            "results": [item.to_dict() for item in self.results],
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
            "safety_notes": list(self.safety_notes),
        }


def score_strategy(
    evidence: StrategyEvidence,
    *,
    criteria: StrategyScorecardCriteria | None = None,
) -> StrategyScorecardResult:
    """Score one strategy while preserving conservative promotion caps."""

    criteria = criteria or StrategyScorecardCriteria()
    raw_score = _raw_score(evidence, criteria)
    blockers = _blockers(evidence, criteria)
    caps = _caps(evidence, criteria)
    score = min(raw_score, *[cap_value for _name, cap_value in caps]) if caps else raw_score
    score = max(0.0, min(100.0, round(score, 3)))
    tier, recommended_status = _tier(score, evidence, criteria)
    decision, reason = _decision(evidence, score, tier, blockers)
    return StrategyScorecardResult(
        strategy_id=evidence.strategy_id,
        source=evidence.source,
        score=score,
        tier=tier,
        recommended_status=recommended_status,
        decision=decision,
        reason=reason,
        live_promotion_allowed=False,
        blockers=tuple(blockers),
        caps_applied=tuple(name for name, _value in caps),
        evidence=evidence,
    )


def score_matrix(
    matrix: MatrixRunResult,
    *,
    criteria: StrategyScorecardCriteria | None = None,
    fees_included: bool = True,
    slippage_included: bool = True,
    baseline_included: bool = False,
    out_of_sample_included: bool | None = None,
) -> StrategyScorecardReport:
    """Aggregate a validation matrix into one scorecard per strategy family."""

    criteria = criteria or StrategyScorecardCriteria()
    grouped: dict[str, list[MatrixCellResult]] = {}
    for cell in matrix.results:
        grouped.setdefault(cell.strategy, []).append(cell)
    results = tuple(
        score_strategy(
            _evidence_from_cells(
                strategy,
                tuple(cells),
                matrix_mode=matrix.mode,
                fees_included=fees_included,
                slippage_included=slippage_included,
                baseline_included=baseline_included,
                out_of_sample_included=(
                    matrix.mode == "walk_forward" if out_of_sample_included is None else out_of_sample_included
                ),
            ),
            criteria=criteria,
        )
        for strategy, cells in sorted(grouped.items())
    )
    return StrategyScorecardReport(run_id=matrix.run_id, source=matrix.mode, results=results)


def write_strategy_scorecard_report(
    report: StrategyScorecardReport,
    output_dir: str | Path,
) -> StrategyScorecardReport:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / f"{report.run_id}_strategy_scorecard.json"
    md_path = output_path / f"{report.run_id}_strategy_scorecard.md"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(render_strategy_scorecard_report(report), encoding="utf-8")
    return StrategyScorecardReport(
        run_id=report.run_id,
        source=report.source,
        results=report.results,
        json_report_path=str(json_path),
        markdown_report_path=str(md_path),
        safety_notes=report.safety_notes,
    )


def render_strategy_scorecard_report(report: StrategyScorecardReport) -> str:
    lines = [
        f"# Strategy Scorecard - {report.run_id}",
        "",
        f"Source: `{report.source}`",
        "",
        "| Strategy | Score | Tier | Recommended Status | Decision | Reason | Trades | Net PnL | PF | Max DD | Live Allowed |",
        "| --- | ---: | --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for result in sorted(report.results, key=lambda item: (-item.score, item.strategy_id)):
        evidence = result.evidence
        lines.append(
            f"| {result.strategy_id} | {result.score:.3f} | {result.tier} | {result.recommended_status} | "
            f"{result.decision} | {result.reason} | {evidence.closed_trades if evidence else 0} | "
            f"{_fmt(evidence.net_pnl_eur if evidence else None)} | "
            f"{_fmt(evidence.profit_factor if evidence else None)} | "
            f"{_fmt(evidence.max_drawdown_pct if evidence else None)} | {result.live_promotion_allowed} |"
        )
    lines.extend(["", "## Safety", ""])
    lines.extend(f"- {note}" for note in report.safety_notes)
    lines.append("")
    return "\n".join(lines)


def _evidence_from_cells(
    strategy: str,
    cells: Sequence[MatrixCellResult],
    *,
    matrix_mode: str,
    fees_included: bool,
    slippage_included: bool,
    baseline_included: bool,
    out_of_sample_included: bool,
) -> StrategyEvidence:
    ok_cells = [cell for cell in cells if cell.status == "ok"]
    closed_trades = sum(max(0, cell.closed_trades) for cell in ok_cells)
    net_pnl = sum(cell.net_pnl_eur or 0.0 for cell in ok_cells)
    weighted_pf = _weighted_profit_factor(ok_cells)
    worst_drawdown = _max_optional(cell.max_drawdown_pct for cell in ok_cells)
    total_return = sum(cell.total_return_pct or 0.0 for cell in ok_cells)
    passing_symbols = sum(1 for cell in ok_cells if (cell.net_pnl_eur or 0.0) > 0.0)
    return StrategyEvidence(
        strategy_id=strategy,
        source=matrix_mode,
        closed_trades=closed_trades,
        net_pnl_eur=net_pnl,
        profit_factor=weighted_pf,
        max_drawdown_pct=worst_drawdown,
        total_return_pct=total_return,
        baseline_delta_pct=None,
        regimes_tested=len(ok_cells),
        positive_regimes=passing_symbols,
        fees_included=fees_included,
        slippage_included=slippage_included,
        baseline_included=baseline_included,
        out_of_sample_included=out_of_sample_included,
        paper_evidence=False,
        contract_signal_boundary_enforced=bool(ok_cells) and all(
            cell.contract_signal_boundary_enforced for cell in ok_cells
        ),
        research_only_evidence=True,
        notes=(f"{len(ok_cells)}/{len(cells)} matrix cells succeeded",),
    )


def _raw_score(evidence: StrategyEvidence, criteria: StrategyScorecardCriteria) -> float:
    sample_target = criteria.min_paper_trades if evidence.paper_evidence else criteria.min_backtest_trades
    pf_target = criteria.paper_min_profit_factor if evidence.paper_evidence else criteria.min_profit_factor
    dd_limit = criteria.paper_max_drawdown_pct if evidence.paper_evidence else criteria.max_drawdown_pct
    score = 0.0
    score += _positive_return_score(evidence) * 20.0
    score += _profit_factor_score(evidence.profit_factor, pf_target) * 20.0
    score += _expectancy_score(evidence) * 10.0
    score += _drawdown_score(evidence.max_drawdown_pct, dd_limit) * 15.0
    score += min(1.0, evidence.closed_trades / sample_target) * 15.0
    score += _baseline_score(evidence) * 10.0
    score += _walk_forward_score(evidence) * 5.0
    score += _regime_score(evidence) * 5.0
    return score


def _positive_return_score(evidence: StrategyEvidence) -> float:
    if evidence.net_pnl_eur <= 0.0:
        return 0.0
    if evidence.total_return_pct is not None:
        return min(1.0, max(0.0, evidence.total_return_pct / 5.0))
    gross = abs(evidence.gross_pnl_eur) if evidence.gross_pnl_eur not in (None, 0.0) else evidence.net_pnl_eur
    return min(1.0, evidence.net_pnl_eur / max(1.0, gross))


def _profit_factor_score(value: float | None, target: float) -> float:
    if value is None or value <= 1.0:
        return 0.0
    strong = max(target + 0.5, 1.5)
    return _linear(value, low=1.0, high=strong)


def _expectancy_score(evidence: StrategyEvidence) -> float:
    if evidence.expectancy_eur is not None:
        return 1.0 if evidence.expectancy_eur > 0.0 else 0.0
    if evidence.closed_trades == 0:
        return 0.0
    return 1.0 if evidence.net_pnl_eur / evidence.closed_trades > 0.0 else 0.0


def _drawdown_score(value: float | None, limit: float) -> float:
    if value is None:
        return 0.5
    if value <= limit * 0.5:
        return 1.0
    if value >= limit:
        return 0.0
    return 1.0 - ((value - limit * 0.5) / (limit * 0.5))


def _baseline_score(evidence: StrategyEvidence) -> float:
    if not evidence.baseline_included:
        return 0.0
    delta = evidence.baseline_delta_pct if evidence.baseline_delta_pct is not None else evidence.baseline_delta_eur
    if delta is None:
        return 0.5
    return 1.0 if delta >= 0.0 else 0.0


def _walk_forward_score(evidence: StrategyEvidence) -> float:
    if not evidence.out_of_sample_included:
        return 0.0
    if evidence.total_folds:
        return min(1.0, max(0.0, (evidence.passing_folds or 0) / evidence.total_folds))
    return 0.5


def _regime_score(evidence: StrategyEvidence) -> float:
    if evidence.regimes_tested <= 0:
        return 0.0
    return min(1.0, max(0.0, evidence.positive_regimes / evidence.regimes_tested))


def _blockers(evidence: StrategyEvidence, criteria: StrategyScorecardCriteria) -> list[str]:
    blockers: list[str] = []
    sample_target = criteria.min_paper_trades if evidence.paper_evidence else criteria.min_backtest_trades
    pf_target = criteria.paper_min_profit_factor if evidence.paper_evidence else criteria.min_profit_factor
    dd_limit = criteria.paper_max_drawdown_pct if evidence.paper_evidence else criteria.max_drawdown_pct
    if evidence.closed_trades < sample_target:
        blockers.append("insufficient_closed_trades")
    if evidence.net_pnl_eur <= 0.0:
        blockers.append("non_positive_net_pnl")
    if evidence.profit_factor is None:
        blockers.append("missing_profit_factor")
    elif evidence.profit_factor < pf_target:
        blockers.append("profit_factor_below_threshold")
    if evidence.max_drawdown_pct is None:
        blockers.append("missing_drawdown")
    elif evidence.max_drawdown_pct > dd_limit:
        blockers.append("drawdown_above_threshold")
    if not evidence.fees_included:
        blockers.append("fees_missing")
    if not evidence.slippage_included:
        blockers.append("slippage_missing")
    if not evidence.baseline_included:
        blockers.append("baseline_missing")
    elif evidence.baseline_delta_pct is not None and evidence.baseline_delta_pct < 0.0:
        blockers.append("baseline_underperformed")
    elif evidence.baseline_delta_eur is not None and evidence.baseline_delta_eur < 0.0:
        blockers.append("baseline_underperformed")
    if not evidence.out_of_sample_included:
        blockers.append("out_of_sample_missing")
    if not evidence.contract_signal_boundary_enforced:
        blockers.append("alpha_contract_boundary_missing")
    return blockers


def _caps(evidence: StrategyEvidence, criteria: StrategyScorecardCriteria) -> list[tuple[str, float]]:
    caps: list[tuple[str, float]] = []
    if not evidence.fees_included or not evidence.slippage_included:
        caps.append(("missing_cost_realism_cap_49", 49.0))
    if not evidence.baseline_included:
        caps.append(("missing_baseline_cap_49", 49.0))
    if evidence.net_pnl_eur <= 0.0:
        caps.append(("non_positive_net_pnl_cap_49", 49.0))
    sample_target = criteria.min_paper_trades if evidence.paper_evidence else criteria.min_backtest_trades
    if evidence.closed_trades < sample_target:
        caps.append(("insufficient_sample_cap_64", 64.0))
    if not evidence.out_of_sample_included:
        caps.append(("missing_out_of_sample_cap_65", 65.0))
    if not evidence.contract_signal_boundary_enforced:
        caps.append(("alpha_contract_boundary_missing_cap_64", 64.0))
    if evidence.research_only_evidence:
        # A validation matrix is research evidence.  It can at most justify a
        # shadow review; paper evidence must come from the dedicated runtime
        # parity, OMS and reconciliation gates.
        caps.append(("research_matrix_not_paper_evidence_cap_74", 74.0))
    if evidence.baseline_delta_pct is not None and evidence.baseline_delta_pct < 0.0:
        caps.append(("underperforms_baseline_cap_64", 64.0))
    if evidence.baseline_delta_eur is not None and evidence.baseline_delta_eur < 0.0:
        caps.append(("underperforms_baseline_cap_64", 64.0))
    return caps


def _tier(
    score: float,
    evidence: StrategyEvidence,
    criteria: StrategyScorecardCriteria,
) -> tuple[str, str]:
    if score < criteria.min_score_for_backtest_only:
        return "disabled", "rejected"
    if score < criteria.min_score_for_shadow_only:
        return "backtest_only", "candidate"
    if score < criteria.min_score_for_paper_allowed:
        return "shadow_only", "walk_forward_passed" if evidence.out_of_sample_included else "backtest_passed"
    if score < criteria.min_score_for_human_live_review:
        return "paper_allowed", "shadow_passed"
    return "human_live_review_candidate", "paper_validated"


def _decision(evidence: StrategyEvidence, score: float, tier: str, blockers: Sequence[str]) -> tuple[str, str]:
    if "non_positive_net_pnl" in blockers and evidence.closed_trades > 0:
        return "reject", "non_positive_net_pnl"
    if tier == "disabled":
        return "reject", blockers[0] if blockers else "score_below_execution_floor"
    if blockers:
        return "keep_testing", ";".join(blockers)
    if tier == "human_live_review_candidate":
        return "human_review_only", "score_above_live_review_floor_but_live_still_disabled"
    if tier == "paper_allowed":
        return "paper_candidate", "score_above_paper_floor_for_human_review"
    return "keep_testing", "scorecard_evidence_not_yet_execution_ready"


def _weighted_profit_factor(cells: Sequence[MatrixCellResult]) -> float | None:
    weighted_values = [
        (cell.profit_factor, max(1, cell.closed_trades))
        for cell in cells
        if cell.profit_factor is not None and cell.profit_factor >= 0.0
    ]
    if not weighted_values:
        return None
    total_weight = sum(weight for _value, weight in weighted_values)
    return sum(value * weight for value, weight in weighted_values) / total_weight


def _max_optional(values: Iterable[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return max(present) if present else None


def _linear(value: float, *, low: float, high: float) -> float:
    if value <= low:
        return 0.0
    if value >= high:
        return 1.0
    return (value - low) / (high - low)


def _fmt(value: float | None) -> str:
    return "" if value is None else f"{value:.6f}"
