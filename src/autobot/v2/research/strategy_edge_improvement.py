"""Research-only strategy edge triage and improvement reporting.

The module reads existing AUTOBOT research reports and produces a conservative
strategy review. It never imports runtime orchestrators, paper executors, order
routers, Kraken clients, or any state-mutating component.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


REQUIRED_STRATEGY_TRIAGE: dict[str, tuple[str, str]] = {
    "high_conviction_swing": ("active_research_keep_testing", "capital_research_limited"),
    "trend_momentum": ("research_signal_only", "no_capital_redesign_required"),
    "mean_reversion": ("research_signal_only", "no_capital_cost_aware_review_required"),
    "relative_value": ("no_go", "no_capital"),
    "grid": ("archived", "no_go"),
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    result = _float(value, float("nan"))
    return result if math.isfinite(result) else None


def _latest_json(directory: Path, pattern: str = "*.json") -> Path | None:
    if not directory.exists():
        return None
    candidates = [path for path in directory.glob(pattern) if path.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _load_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _as_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _safe_ratio(numerator: float, denominator: float) -> float | None:
    if abs(denominator) < 1e-12:
        return None
    return numerator / denominator


def _strategy_key(value: str) -> str:
    raw = value.lower().strip()
    aliases = {
        "trend": "trend_momentum",
        "trend_momentum_shadow": "trend_momentum",
        "mean_reversion_shadow": "mean_reversion",
        "high_conviction": "high_conviction_swing",
        "high_conviction_swing": "high_conviction_swing",
        "relative_value": "relative_value",
        "grid": "grid",
    }
    return aliases.get(raw, raw)


def _pf_gate(profit_factor: float | None, trade_count: int, positive_folds: int, total_folds: int) -> str:
    pf = profit_factor if profit_factor is not None else 0.0
    fold_ratio = positive_folds / total_folds if total_folds else 0.0
    if trade_count >= 50 and pf >= 1.50 and fold_ratio >= 0.60:
        return "A"
    if trade_count >= 50 and pf >= 1.30 and fold_ratio >= 0.50:
        return "B"
    if pf >= 1.10 and trade_count >= 20:
        return "C"
    if pf >= 0.95:
        return "D"
    return "E"


@dataclass(frozen=True)
class StrategyEdgeReviewConfig:
    run_id: str
    output_dir: Path = Path("reports/research")
    report_date: str | None = None
    strategy_orchestrator_report_path: Path | None = None
    high_conviction_report_path: Path | None = None
    min_candidate_trades: int = 50
    min_candidate_pf: float = 1.30
    high_quality_pf: float = 1.50
    max_drawdown_pct: float = 10.0
    max_single_symbol_positive_share: float = 0.40

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id is required")
        if self.min_candidate_trades <= 0:
            raise ValueError("min_candidate_trades must be positive")
        for value in (self.min_candidate_pf, self.high_quality_pf, self.max_drawdown_pct):
            if not math.isfinite(float(value)) or float(value) <= 0.0:
                raise ValueError("strategy edge thresholds must be positive")
        if not 0.0 < float(self.max_single_symbol_positive_share) <= 1.0:
            raise ValueError("max_single_symbol_positive_share must be in (0, 1]")


@dataclass(frozen=True)
class StrategyTriage:
    strategy_name: str
    requested_status: str
    capital_status: str
    observed_status: str
    profit_factor: float | None
    net_pnl_eur: float | None
    trade_count: int
    winrate_pct: float | None
    max_drawdown_pct: float | None
    positive_folds: int
    total_folds: int
    pf_gate: str
    blockers: tuple[str, ...]
    next_action: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["blockers"] = list(self.blockers)
        return payload


@dataclass(frozen=True)
class PairEdgeAttribution:
    symbol: str
    net_pnl_eur: float
    trade_count: int
    profit_factor: float | None
    winrate_pct: float | None
    positive_pnl_share: float
    action: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reasons"] = list(self.reasons)
        return payload


@dataclass(frozen=True)
class LeaveOneSymbolOutResult:
    symbol_removed: str
    baseline_net_pnl_eur: float
    net_pnl_without_symbol_eur: float
    pnl_delta_eur: float
    trade_count_without_symbol: int
    interpretation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StrategyEdgeImprovementReport:
    run_id: str
    generated_at: str
    report_date: str
    source_reports: Mapping[str, str | None]
    strategy_triage: tuple[StrategyTriage, ...]
    high_conviction_summary: Mapping[str, Any]
    pair_attribution: tuple[PairEdgeAttribution, ...]
    leave_one_symbol_out: tuple[LeaveOneSymbolOutResult, ...]
    trend_redesign_plan: tuple[Mapping[str, Any], ...]
    mean_reversion_cost_review_plan: tuple[Mapping[str, Any], ...]
    candidate_family_reviews: tuple[Mapping[str, Any], ...]
    recommendations: tuple[str, ...]
    safety: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "report_date": self.report_date,
            "source_reports": dict(self.source_reports),
            "strategy_triage": [item.to_dict() for item in self.strategy_triage],
            "high_conviction_summary": dict(self.high_conviction_summary),
            "pair_attribution": [item.to_dict() for item in self.pair_attribution],
            "leave_one_symbol_out": [item.to_dict() for item in self.leave_one_symbol_out],
            "trend_redesign_plan": [dict(item) for item in self.trend_redesign_plan],
            "mean_reversion_cost_review_plan": [dict(item) for item in self.mean_reversion_cost_review_plan],
            "candidate_family_reviews": [dict(item) for item in self.candidate_family_reviews],
            "recommendations": list(self.recommendations),
            "safety": dict(self.safety),
        }


@dataclass(frozen=True)
class StrategyEdgeWrittenReport:
    review_markdown_path: str
    improvement_markdown_path: str
    json_report_path: str
    report: StrategyEdgeImprovementReport

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_markdown_path": self.review_markdown_path,
            "improvement_markdown_path": self.improvement_markdown_path,
            "json_report_path": self.json_report_path,
            "paper_candidate_allowed": False,
            "live_promotion_allowed": False,
            "orders_created": False,
            "runtime_modified": False,
            "report": self.report.to_dict(),
        }


def build_strategy_edge_improvement_report(config: StrategyEdgeReviewConfig) -> StrategyEdgeImprovementReport:
    """Build a conservative research-only strategy edge review."""

    orchestrator_path = config.strategy_orchestrator_report_path or _latest_json(
        Path("reports/research/strategy_orchestrator")
    )
    high_conviction_path = config.high_conviction_report_path or _latest_json(
        Path("reports/research/high_conviction_walk_forward")
    )
    orchestrator = _load_json(orchestrator_path)
    high_conviction = _load_json(high_conviction_path)
    if not high_conviction:
        high_conviction = dict(orchestrator.get("high_conviction_walk_forward") or {})

    primary = _primary_high_conviction_aggregate(orchestrator, high_conviction)
    paper = _matching_or_best_aggregate(high_conviction, cost_profile="paper_current_taker")
    stress = _matching_or_best_aggregate(high_conviction, cost_profile="research_stress") or primary
    strategy_triage = _build_strategy_triage(
        orchestrator=orchestrator,
        primary=primary,
        config=config,
    )
    pair_attribution = _build_pair_attribution(
        orchestrator=orchestrator,
        primary=primary,
        config=config,
    )
    leave_one_out = _leave_one_symbol_out(primary, pair_attribution)
    high_summary = _high_conviction_summary(
        primary=primary,
        paper=paper,
        stress=stress,
        pair_attribution=pair_attribution,
        config=config,
    )
    report_date = config.report_date or date.today().isoformat()
    return StrategyEdgeImprovementReport(
        run_id=config.run_id,
        generated_at=_utc_now().isoformat(),
        report_date=report_date,
        source_reports={
            "strategy_orchestrator": str(orchestrator_path) if orchestrator_path else None,
            "high_conviction_walk_forward": str(high_conviction_path) if high_conviction_path else "embedded_in_orchestrator",
        },
        strategy_triage=strategy_triage,
        high_conviction_summary=high_summary,
        pair_attribution=pair_attribution,
        leave_one_symbol_out=leave_one_out,
        trend_redesign_plan=_trend_redesign_plan(),
        mean_reversion_cost_review_plan=_mean_reversion_plan(),
        candidate_family_reviews=_candidate_family_reviews(),
        recommendations=_recommendations(strategy_triage, high_summary),
        safety={
            "research_only": True,
            "orders_created": False,
            "official_paper_modified": False,
            "live_modified": False,
            "runtime_router_modified": False,
            "runtime_sizing_modified": False,
            "child_instance_created": False,
            "live_promotion_allowed": False,
        },
    )


def write_strategy_edge_improvement_report(
    report: StrategyEdgeImprovementReport,
    output_dir: Path | None = None,
) -> StrategyEdgeWrittenReport:
    output_dir = output_dir or Path("reports/research")
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = report.report_date.replace("-", "_")
    review_path = output_dir / f"strategy_edge_review_{suffix}.md"
    improvement_path = output_dir / f"strategy_edge_improvement_{suffix}.md"
    json_path = output_dir / f"strategy_edge_improvement_{suffix}.json"
    review_path.write_text(render_strategy_edge_review_markdown(report), encoding="utf-8")
    improvement_path.write_text(render_strategy_edge_improvement_markdown(report), encoding="utf-8")
    json_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return StrategyEdgeWrittenReport(
        review_markdown_path=str(review_path),
        improvement_markdown_path=str(improvement_path),
        json_report_path=str(json_path),
        report=report,
    )


def _primary_high_conviction_aggregate(
    orchestrator: Mapping[str, Any],
    high_conviction: Mapping[str, Any],
) -> dict[str, Any]:
    primary = dict(high_conviction.get("primary_aggregate") or {})
    if primary:
        return primary
    embedded = dict((orchestrator.get("high_conviction_walk_forward") or {}).get("primary_aggregate") or {})
    if embedded:
        return embedded
    return _matching_or_best_aggregate(high_conviction, cost_profile="research_stress") or {}


def _matching_or_best_aggregate(report: Mapping[str, Any], *, cost_profile: str) -> dict[str, Any]:
    aggregates = _as_list(report.get("aggregates"))
    candidates = [item for item in aggregates if item.get("cost_profile") == cost_profile]
    if not candidates:
        primary = dict(report.get("primary_aggregate") or {})
        return primary if primary.get("cost_profile") == cost_profile else {}
    candidates.sort(
        key=lambda item: (
            str((item.get("scenario") or {}).get("exit_mode") or "") == "fixed_tp_sl",
            _float(item.get("total_net_pnl_eur")),
        ),
        reverse=True,
    )
    return dict(candidates[0])


def _build_strategy_triage(
    *,
    orchestrator: Mapping[str, Any],
    primary: Mapping[str, Any],
    config: StrategyEdgeReviewConfig,
) -> tuple[StrategyTriage, ...]:
    score_by_strategy = {
        _strategy_key(str(item.get("strategy_name") or "")): dict(item)
        for item in _as_list(orchestrator.get("strategy_scores"))
    }
    rows: list[StrategyTriage] = []
    for strategy, (requested_status, capital_status) in REQUIRED_STRATEGY_TRIAGE.items():
        observed = score_by_strategy.get(strategy, {})
        evidence = dict(observed.get("evidence") or {})
        if strategy == "high_conviction_swing":
            metrics = primary
            trade_count = int(_float(metrics.get("total_trade_count") or evidence.get("trade_count")))
            pf = _optional_float(metrics.get("profit_factor") or evidence.get("profit_factor"))
            pnl = _optional_float(metrics.get("total_net_pnl_eur") or evidence.get("net_pnl_eur"))
            winrate = _optional_float(metrics.get("winrate_pct") or evidence.get("winrate_pct"))
            drawdown = _optional_float(metrics.get("worst_fold_drawdown_pct") or evidence.get("max_drawdown_pct"))
            positive_folds = int(_float(metrics.get("positive_fold_count") or evidence.get("positive_folds")))
            total_folds = int(_float(metrics.get("fold_count") or evidence.get("total_folds")))
        else:
            trade_count = int(_float(evidence.get("trade_count")))
            pf = _optional_float(evidence.get("profit_factor"))
            pnl = _optional_float(evidence.get("net_pnl_eur"))
            winrate = _optional_float(evidence.get("winrate_pct"))
            drawdown = _optional_float(evidence.get("max_drawdown_pct"))
            positive_folds = int(_float(evidence.get("positive_folds")))
            total_folds = int(_float(evidence.get("total_folds")))
        blockers = _strategy_blockers(
            strategy=strategy,
            pf=pf,
            trade_count=trade_count,
            drawdown=drawdown,
            positive_folds=positive_folds,
            total_folds=total_folds,
            primary=primary,
            config=config,
        )
        rows.append(
            StrategyTriage(
                strategy_name=strategy,
                requested_status=requested_status,
                capital_status=capital_status,
                observed_status=str(observed.get("status") or "not_observed"),
                profit_factor=pf,
                net_pnl_eur=pnl,
                trade_count=trade_count,
                winrate_pct=winrate,
                max_drawdown_pct=drawdown,
                positive_folds=positive_folds,
                total_folds=total_folds,
                pf_gate=_pf_gate(pf, trade_count, positive_folds, total_folds),
                blockers=tuple(blockers),
                next_action=_strategy_next_action(strategy),
            )
        )
    return tuple(rows)


def _strategy_blockers(
    *,
    strategy: str,
    pf: float | None,
    trade_count: int,
    drawdown: float | None,
    positive_folds: int,
    total_folds: int,
    primary: Mapping[str, Any],
    config: StrategyEdgeReviewConfig,
) -> list[str]:
    blockers: list[str] = []
    if strategy in {"relative_value", "grid"}:
        return ["strategy_currently_no_go_or_archived"]
    if trade_count < config.min_candidate_trades:
        blockers.append("insufficient_trade_count_for_candidate_review")
    if pf is None or pf < config.min_candidate_pf:
        blockers.append("profit_factor_below_candidate_threshold")
    if drawdown is not None and drawdown > config.max_drawdown_pct:
        blockers.append("drawdown_above_research_limit")
    if total_folds and (positive_folds / total_folds) < 0.60:
        blockers.append("insufficient_positive_fold_ratio")
    if strategy == "high_conviction_swing":
        share = _float(primary.get("largest_positive_symbol_share"))
        if share > config.max_single_symbol_positive_share:
            blockers.append("single_symbol_concentration_above_limit")
    if strategy == "trend_momentum":
        blockers.append("redesign_required_before_capital")
    if strategy == "mean_reversion":
        blockers.append("cost_aware_review_required_before_capital")
    return blockers


def _strategy_next_action(strategy: str) -> str:
    return {
        "high_conviction_swing": "keep_researching_with_pair_attribution_and_walk_forward_filters",
        "trend_momentum": "redesign_signal_quality_filters_before_any_capital",
        "mean_reversion": "run_cost_aware_range_only_review_before_any_capital",
        "relative_value": "keep_no_go_until_relation_and_cost_survival_retested",
        "grid": "keep_archived_no_go",
    }.get(strategy, "observe_only")


def _build_pair_attribution(
    *,
    orchestrator: Mapping[str, Any],
    primary: Mapping[str, Any],
    config: StrategyEdgeReviewConfig,
) -> tuple[PairEdgeAttribution, ...]:
    pair_scores = {
        str(item.get("symbol") or "").upper(): dict(item)
        for item in _as_list(orchestrator.get("pair_scores"))
        if item.get("symbol")
    }
    contributors = {
        str(item.get("symbol") or "").upper(): dict(item)
        for item in _as_list(primary.get("contributors"))
        if item.get("symbol")
    }
    symbols = sorted(set(pair_scores) | set(contributors))
    positive_total = sum(max(0.0, _float(item.get("net_pnl_eur"))) for item in contributors.values())
    rows: list[PairEdgeAttribution] = []
    for symbol in symbols:
        contributor = contributors.get(symbol, {})
        score = pair_scores.get(symbol, {})
        net_pnl = _float(contributor.get("net_pnl_eur"), _float(score.get("net_pnl_eur")))
        trade_count = int(_float(contributor.get("trade_count"), _float(score.get("closed_trade_count"))))
        pf = _optional_float(score.get("profit_factor"))
        winrate = _optional_float(score.get("winrate_pct"))
        share = max(0.0, net_pnl) / positive_total if positive_total > 0.0 else 0.0
        action, reasons = _pair_action(
            net_pnl=net_pnl,
            trade_count=trade_count,
            profit_factor=pf,
            positive_share=share,
            config=config,
        )
        rows.append(
            PairEdgeAttribution(
                symbol=symbol,
                net_pnl_eur=round(net_pnl, 6),
                trade_count=trade_count,
                profit_factor=pf,
                winrate_pct=winrate,
                positive_pnl_share=round(share, 6),
                action=action,
                reasons=tuple(reasons),
            )
        )
    return tuple(sorted(rows, key=lambda item: (item.net_pnl_eur, item.symbol), reverse=True))


def _pair_action(
    *,
    net_pnl: float,
    trade_count: int,
    profit_factor: float | None,
    positive_share: float,
    config: StrategyEdgeReviewConfig,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if trade_count < 5:
        reasons.append("sample_too_small")
        return "observe_more", reasons
    if positive_share > config.max_single_symbol_positive_share:
        reasons.append("positive_pnl_concentration")
        return "concentration_watch_research_only", reasons
    if net_pnl < -5.0 or (profit_factor is not None and profit_factor < 0.75):
        reasons.append("material_negative_contribution")
        if profit_factor is not None and profit_factor < 0.75:
            reasons.append("weak_pair_profit_factor")
        return "research_quarantine_candidate", reasons
    if net_pnl > 0.0 and (profit_factor is None or profit_factor >= 1.10):
        reasons.append("positive_after_costs")
        return "keep_testing_research", reasons
    reasons.append("mixed_or_cost_sensitive")
    return "cost_aware_review", reasons


def _leave_one_symbol_out(
    primary: Mapping[str, Any],
    pair_attribution: Sequence[PairEdgeAttribution],
) -> tuple[LeaveOneSymbolOutResult, ...]:
    baseline = _float(primary.get("total_net_pnl_eur"))
    total_trades = int(_float(primary.get("total_trade_count")))
    rows: list[LeaveOneSymbolOutResult] = []
    for item in pair_attribution:
        without = baseline - item.net_pnl_eur
        delta = without - baseline
        if item.net_pnl_eur > 0.0 and without < baseline:
            interpretation = "depends_on_positive_pair"
        elif item.net_pnl_eur < 0.0 and without > baseline:
            interpretation = "pair_damages_portfolio"
        else:
            interpretation = "neutral_or_small_sample"
        rows.append(
            LeaveOneSymbolOutResult(
                symbol_removed=item.symbol,
                baseline_net_pnl_eur=round(baseline, 6),
                net_pnl_without_symbol_eur=round(without, 6),
                pnl_delta_eur=round(delta, 6),
                trade_count_without_symbol=max(0, total_trades - item.trade_count),
                interpretation=interpretation,
            )
        )
    return tuple(sorted(rows, key=lambda item: item.pnl_delta_eur, reverse=True))


def _high_conviction_summary(
    *,
    primary: Mapping[str, Any],
    paper: Mapping[str, Any],
    stress: Mapping[str, Any],
    pair_attribution: Sequence[PairEdgeAttribution],
    config: StrategyEdgeReviewConfig,
) -> dict[str, Any]:
    pf = _optional_float(primary.get("profit_factor"))
    trade_count = int(_float(primary.get("total_trade_count")))
    positive_folds = int(_float(primary.get("positive_fold_count")))
    fold_count = int(_float(primary.get("fold_count")))
    net = _float(primary.get("total_net_pnl_eur"))
    paper_net = _optional_float(paper.get("total_net_pnl_eur"))
    stress_net = _optional_float(stress.get("total_net_pnl_eur"))
    paper_pf = _optional_float(paper.get("profit_factor"))
    stress_pf = _optional_float(stress.get("profit_factor"))
    positive_share = max((item.positive_pnl_share for item in pair_attribution), default=0.0)
    damaging = [item.symbol for item in pair_attribution if item.action == "research_quarantine_candidate"]
    return {
        "status": "active_research_keep_testing",
        "cost_profile": primary.get("cost_profile"),
        "net_pnl_eur": round(net, 6),
        "profit_factor": pf,
        "trade_count": trade_count,
        "winrate_pct": _optional_float(primary.get("winrate_pct")),
        "worst_fold_drawdown_pct": _optional_float(primary.get("worst_fold_drawdown_pct")),
        "positive_folds": positive_folds,
        "fold_count": fold_count,
        "pf_gate": _pf_gate(pf, trade_count, positive_folds, fold_count),
        "largest_positive_symbol_share": round(positive_share, 6),
        "concentration_penalty": round(max(0.0, positive_share - config.max_single_symbol_positive_share) * 100.0, 6),
        "paper_current_taker_net_pnl_eur": paper_net,
        "paper_current_taker_profit_factor": paper_pf,
        "research_stress_net_pnl_eur": stress_net,
        "research_stress_profit_factor": stress_pf,
        "stress_delta_net_pnl_eur": (
            round(stress_net - paper_net, 6) if stress_net is not None and paper_net is not None else None
        ),
        "stress_delta_profit_factor": (
            round(stress_pf - paper_pf, 6) if stress_pf is not None and paper_pf is not None else None
        ),
        "pair_quarantine_candidates": damaging,
        "paper_candidate_allowed": False,
        "reason": "positive_but_not_robust_enough_for_paper_candidate",
    }


def _trend_redesign_plan() -> tuple[Mapping[str, Any], ...]:
    return (
        {"filter": "strong_multi_timeframe_trend", "purpose": "avoid weak single-timeframe momentum", "capital": "no_capital"},
        {"filter": "range_chop_avoidance", "purpose": "block momentum in sideways regimes", "capital": "no_capital"},
        {"filter": "minimum_volatility", "purpose": "require enough movement to cover costs", "capital": "no_capital"},
        {"filter": "volume_confirmation", "purpose": "avoid low-liquidity momentum signals", "capital": "no_capital"},
        {"filter": "momentum_persistence", "purpose": "require continuation across multiple bars", "capital": "no_capital"},
        {"filter": "spread_cost_floor", "purpose": "reject trades whose edge cannot exceed costs", "capital": "no_capital"},
        {"filter": "strict_cooldown", "purpose": "reduce clustered false signals", "capital": "no_capital"},
    )


def _mean_reversion_plan() -> tuple[Mapping[str, Any], ...]:
    return (
        {"filter": "tp_above_round_trip_cost_plus_margin", "purpose": "avoid gross wins that become net flat"},
        {"filter": "spread_filter", "purpose": "only trade cheap symbols"},
        {"filter": "minimum_volatility", "purpose": "ensure mean reversion amplitude covers cost"},
        {"filter": "range_regime_only", "purpose": "avoid catching falling/strong trending assets"},
        {"filter": "strong_trend_block", "purpose": "block reversion against dominant trend"},
        {"filter": "exit_timing_review", "purpose": "reduce winners decaying back to cost"},
        {"filter": "portfolio_aware_walk_forward", "purpose": "validate net effect with capital constraints"},
    )


def _candidate_family_reviews() -> tuple[Mapping[str, Any], ...]:
    return (
        {
            "family": "breakout_volatility",
            "status": "research_design_ready",
            "baseline_to_beat": "high_conviction_current",
            "notes": "use 1h/4h volatility expansion and cost-aware breakout confirmation",
        },
        {
            "family": "range_breakout",
            "status": "research_design_only",
            "baseline_to_beat": "no_trade,buy_and_hold,random_signal_same_frequency,high_conviction_current",
            "notes": "requires range identification before breakout validation",
        },
        {
            "family": "liquidity_sweep_fakeout",
            "status": "research_design_only",
            "baseline_to_beat": "high_conviction_current",
            "notes": "needs spread/depth snapshots; no order-book-dependent capital until coverage is long enough",
        },
        {
            "family": "volume_anomaly",
            "status": "research_design_only",
            "baseline_to_beat": "high_conviction_current",
            "notes": "needs reliable OHLCV volume and anti-overfit walk-forward",
        },
        {
            "family": "multi_timeframe_confirmation",
            "status": "already_represented_by_high_conviction",
            "baseline_to_beat": "high_conviction_current",
            "notes": "improve with pair/regime attribution instead of broad parameter tuning",
        },
        {
            "family": "volatility_expansion",
            "status": "already_represented_by_high_conviction",
            "baseline_to_beat": "high_conviction_current",
            "notes": "split attribution by family in future walk-forward reports",
        },
        {
            "family": "regime_switch_strategy",
            "status": "research_design_only",
            "baseline_to_beat": "high_conviction_current",
            "notes": "use existing regime/entropy tools as filters, not price prediction",
        },
    )


def _recommendations(
    strategy_triage: Sequence[StrategyTriage],
    high_summary: Mapping[str, Any],
) -> tuple[str, ...]:
    by_strategy = {item.strategy_name: item for item in strategy_triage}
    recommendations = [
        "Keep High Conviction in active_research only; do not promote until trade count, folds and concentration improve.",
        "Run leave-one-symbol-out and research-only quarantine analysis before trusting any positive headline PnL.",
        "Keep Trend Momentum no_capital until redesigned filters lift stress PF above 1.10.",
        "Keep Mean Reversion no_capital until TP/cost and range-only filters prove net profitability after costs.",
        "Keep Relative Value no_go and Grid archived/no_go.",
        "Add family-level attribution to future High Conviction walk-forward outputs before adding new strategy families.",
    ]
    if by_strategy.get("high_conviction_swing") and by_strategy["high_conviction_swing"].pf_gate in {"A", "B"}:
        recommendations.append("Even if PF gate improves, require human review before any paper candidate.")
    if high_summary.get("pair_quarantine_candidates"):
        recommendations.append(
            "Test research-only pair quarantine for: "
            + ", ".join(str(item) for item in high_summary["pair_quarantine_candidates"])
        )
    return tuple(recommendations)


def render_strategy_edge_review_markdown(report: StrategyEdgeImprovementReport) -> str:
    lines = [
        f"# Strategy Edge Review - {report.report_date}",
        "",
        f"- run_id: `{report.run_id}`",
        f"- generated_at: `{report.generated_at}`",
        "- scope: research_only",
        "- orders_created: false",
        "- paper/live runtime modified: false",
        "",
        "## Strategy triage",
        "",
        "| Strategy | Requested status | Capital status | Observed status | PF | PnL EUR | Trades | Folds | Gate | Blockers |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for item in report.strategy_triage:
        lines.append(
            "| "
            + " | ".join(
                [
                    item.strategy_name,
                    item.requested_status,
                    item.capital_status,
                    item.observed_status,
                    _fmt(item.profit_factor),
                    _fmt(item.net_pnl_eur),
                    str(item.trade_count),
                    f"{item.positive_folds}/{item.total_folds}",
                    item.pf_gate,
                    ", ".join(item.blockers) or "-",
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## High Conviction summary",
            "",
            f"- net_pnl_eur: `{_fmt(report.high_conviction_summary.get('net_pnl_eur'))}`",
            f"- profit_factor: `{_fmt(report.high_conviction_summary.get('profit_factor'))}`",
            f"- trades: `{report.high_conviction_summary.get('trade_count')}`",
            f"- folds: `{report.high_conviction_summary.get('positive_folds')}/{report.high_conviction_summary.get('fold_count')}`",
            f"- largest_positive_symbol_share: `{_fmt(report.high_conviction_summary.get('largest_positive_symbol_share'))}`",
            f"- pair_quarantine_candidates: `{', '.join(report.high_conviction_summary.get('pair_quarantine_candidates') or []) or '-'}`",
            "",
            "## Safety",
            "",
            "- live_promotion_allowed: false",
            "- official_paper_modified: false",
            "- child_instance_created: false",
        ]
    )
    return "\n".join(lines) + "\n"


def render_strategy_edge_improvement_markdown(report: StrategyEdgeImprovementReport) -> str:
    lines = [
        f"# Strategy Edge Improvement - {report.report_date}",
        "",
        "This report is research-only. It does not promote strategies, create orders,",
        "modify official paper trading, or change live/runtime flags.",
        "",
        "## Pair attribution",
        "",
        "| Symbol | Net PnL EUR | Trades | PF | Winrate % | Positive share | Research action | Reasons |",
        "|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for item in report.pair_attribution:
        lines.append(
            "| "
            + " | ".join(
                [
                    item.symbol,
                    _fmt(item.net_pnl_eur),
                    str(item.trade_count),
                    _fmt(item.profit_factor),
                    _fmt(item.winrate_pct),
                    _fmt(item.positive_pnl_share),
                    item.action,
                    ", ".join(item.reasons) or "-",
                ]
            )
            + " |"
        )
    lines.extend(["", "## Leave-one-symbol-out", "", "| Removed | Net without symbol | Delta | Interpretation |", "|---|---:|---:|---|"])
    for item in report.leave_one_symbol_out:
        lines.append(
            f"| {item.symbol_removed} | {_fmt(item.net_pnl_without_symbol_eur)} | {_fmt(item.pnl_delta_eur)} | {item.interpretation} |"
        )
    lines.extend(["", "## Trend Momentum redesign plan", ""])
    for item in report.trend_redesign_plan:
        lines.append(f"- {item['filter']}: {item['purpose']} ({item['capital']})")
    lines.extend(["", "## Mean Reversion cost-aware review plan", ""])
    for item in report.mean_reversion_cost_review_plan:
        lines.append(f"- {item['filter']}: {item['purpose']}")
    lines.extend(
        [
            "",
            "## Candidate families",
            "",
            "| Family | Status | Baseline | Notes |",
            "|---|---|---|---|",
        ]
    )
    for item in report.candidate_family_reviews:
        lines.append(
            f"| {item['family']} | {item['status']} | {item['baseline_to_beat']} | {item['notes']} |"
        )
    lines.extend(["", "## Recommendations", ""])
    for item in report.recommendations:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Safety confirmation",
            "",
            "- research_only: true",
            "- orders_created: false",
            "- official_paper_modified: false",
            "- live_modified: false",
            "- runtime_router_modified: false",
            "- runtime_sizing_modified: false",
            "- child_instance_created: false",
            "- live_promotion_allowed: false",
        ]
    )
    return "\n".join(lines) + "\n"


def _fmt(value: Any) -> str:
    metric = _optional_float(value)
    if metric is None:
        return "-"
    return f"{metric:.4f}"

