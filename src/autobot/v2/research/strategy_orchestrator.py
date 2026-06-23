"""Research-only multi-strategy orchestration and instance treasury simulation.

This module is deliberately outside AUTOBOT's runtime order path. It turns
research signals into a common contract, scores their evidence, and simulates
how a single virtual instance would reserve capital. It does not import the
runtime orchestrator, paper executor, order router, Kraken client, or state DB.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Iterable, Literal, Mapping, Sequence

from autobot.v2.instance_split_policy import (
    EXECUTION_FLAG_NAME,
    InstanceSplitDecision,
    InstanceSplitEvidence,
    InstanceSplitPolicy,
    InstanceSplitPolicyConfig,
)

from .backtest_engine import BacktestSignal
from .high_conviction_discovery import HighConvictionDiscoveryConfig, DiscoverySetup, _group_by_symbol_timeframe, _load_ohlcv_bars
from .high_conviction_walk_forward import (
    HighConvictionWalkForwardConfig,
    HighConvictionWalkForwardReport,
    _deduplicate_bars,
    build_high_conviction_walk_forward_report,
)
from .metrics_engine import MetricsEngine
from .relative_value_engine import RelativeValueSignal
from .strategy_signal_generators import MeanReversionResearchSignalGenerator, TrendResearchSignalGenerator
from .trade_journal import TradeJournal, TradeRecord


InstanceRole = Literal["parent", "child", "standalone"]
StrategyResearchStatus = Literal[
    "archived",
    "no_go",
    "research_signal_only",
    "active_research",
    "candidate_paper",
    "paper_limited",
]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, float(value)))


def _as_datetime(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _positive_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) and result > 0.0 else default


def _float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


@dataclass(frozen=True)
class InstanceTreasury:
    """Virtual capital state for one research instance.

    ``realized_equity_eur`` is the only equity value allowed to drive a new
    allocation. ``unrealized_pnl_eur`` is retained for observability only.
    """

    instance_id: str
    parent_instance_id: str | None
    instance_role: InstanceRole
    instance_treasury_eur: float
    realized_equity_eur: float
    available_cash_eur: float
    reserved_exposure_eur: float
    realized_pnl_eur: float
    unrealized_pnl_eur: float
    max_instance_exposure_pct: float
    max_strategy_exposure_pct: float
    max_symbol_exposure_pct: float
    max_daily_loss_pct: float
    max_drawdown_pct: float

    def __post_init__(self) -> None:
        if not self.instance_id.strip():
            raise ValueError("instance_id must not be empty")
        if self.instance_role not in {"parent", "child", "standalone"}:
            raise ValueError("unsupported instance_role")
        for value in (
            self.instance_treasury_eur,
            self.realized_equity_eur,
            self.available_cash_eur,
            self.reserved_exposure_eur,
        ):
            if not math.isfinite(float(value)) or float(value) < 0.0:
                raise ValueError("treasury amounts must be finite and non-negative")
        for value in (
            self.max_instance_exposure_pct,
            self.max_strategy_exposure_pct,
            self.max_symbol_exposure_pct,
            self.max_daily_loss_pct,
            self.max_drawdown_pct,
        ):
            if not 0.0 < float(value) <= 1.0:
                raise ValueError("treasury risk fractions must be in (0, 1]")

    @property
    def sizing_equity_eur(self) -> float:
        """Realized equity only: floating PnL cannot increase a new position."""

        return max(0.0, float(self.realized_equity_eur))

    @classmethod
    def starting(
        cls,
        *,
        instance_id: str,
        capital_eur: float = 500.0,
        parent_instance_id: str | None = None,
        instance_role: InstanceRole = "standalone",
        max_instance_exposure_pct: float = 0.60,
        max_strategy_exposure_pct: float = 0.50,
        max_symbol_exposure_pct: float = 0.20,
        max_daily_loss_pct: float = 0.03,
        max_drawdown_pct: float = 0.10,
    ) -> "InstanceTreasury":
        if not math.isfinite(float(capital_eur)) or float(capital_eur) <= 0.0:
            raise ValueError("capital_eur must be positive and finite")
        return cls(
            instance_id=instance_id,
            parent_instance_id=parent_instance_id,
            instance_role=instance_role,
            instance_treasury_eur=float(capital_eur),
            realized_equity_eur=float(capital_eur),
            available_cash_eur=float(capital_eur),
            reserved_exposure_eur=0.0,
            realized_pnl_eur=0.0,
            unrealized_pnl_eur=0.0,
            max_instance_exposure_pct=max_instance_exposure_pct,
            max_strategy_exposure_pct=max_strategy_exposure_pct,
            max_symbol_exposure_pct=max_symbol_exposure_pct,
            max_daily_loss_pct=max_daily_loss_pct,
            max_drawdown_pct=max_drawdown_pct,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["sizing_equity_eur"] = round(self.sizing_equity_eur, 6)
        payload["research_only"] = True
        return payload


@dataclass(frozen=True)
class StrategyResearchSignal:
    strategy_name: str
    symbol: str
    timestamp: datetime
    direction: str
    confidence: float
    expected_move_bps: float
    cost_profile: str
    regime: str
    reason: str
    metadata: Mapping[str, Any]
    research_only: bool
    instance_id: str
    signal_id: str = ""

    def __post_init__(self) -> None:
        if not self.research_only:
            raise ValueError("StrategyResearchSignal must remain research_only")
        if not self.strategy_name.strip() or not self.symbol.strip() or not self.instance_id.strip():
            raise ValueError("strategy_name, symbol and instance_id are required")
        if self.direction.lower() not in {"buy", "sell"}:
            raise ValueError("direction must be buy or sell")
        if not math.isfinite(float(self.confidence)) or not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("confidence must be in [0, 1]")
        if not math.isfinite(float(self.expected_move_bps)):
            raise ValueError("expected_move_bps must be finite")
        if not self.signal_id:
            raw = "|".join(
                (
                    self.strategy_name,
                    self.symbol,
                    self.timestamp.isoformat(),
                    self.direction.lower(),
                    self.reason,
                    self.cost_profile,
                    self.instance_id,
                )
            )
            object.__setattr__(self, "signal_id", hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20])

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "direction": self.direction.lower(),
            "confidence": round(self.confidence, 6),
            "expected_move_bps": round(self.expected_move_bps, 6),
            "cost_profile": self.cost_profile,
            "regime": self.regime,
            "reason": self.reason,
            "metadata": dict(self.metadata),
            "research_only": True,
            "instance_id": self.instance_id,
        }


@dataclass(frozen=True)
class StrategyPerformanceEvidence:
    strategy_name: str
    status: StrategyResearchStatus
    cost_profile: str
    signal_count: int
    trade_count: int
    net_pnl_eur: float | None
    profit_factor: float | None
    winrate_pct: float | None
    max_drawdown_pct: float | None
    positive_folds: int
    total_folds: int
    largest_positive_symbol_share: float | None
    validation_days: int
    costs_covered: bool
    runtime_comparable: bool
    failure_reasons: tuple[str, ...] = ()
    source: str = "research"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["failure_reasons"] = list(self.failure_reasons)
        return payload


@dataclass(frozen=True)
class StrategyMetaScore:
    strategy_name: str
    score: float
    status: StrategyResearchStatus
    candidate_paper_recommended: bool
    reasons: tuple[str, ...]
    blockers: tuple[str, ...]
    evidence: StrategyPerformanceEvidence
    live_promotion_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_name": self.strategy_name,
            "score": round(self.score, 6),
            "status": self.status,
            "candidate_paper_recommended": self.candidate_paper_recommended,
            "reasons": list(self.reasons),
            "blockers": list(self.blockers),
            "evidence": self.evidence.to_dict(),
            "live_promotion_allowed": False,
        }


@dataclass(frozen=True)
class PairResearchScore:
    symbol: str
    signal_count: int
    closed_trade_count: int
    net_pnl_eur: float | None
    profit_factor: float | None
    winrate_pct: float | None
    score: float
    regime: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reasons"] = list(self.reasons)
        return payload


@dataclass(frozen=True)
class RegimeResearchScore:
    regime: str
    signal_count: int
    closed_trade_count: int
    net_pnl_eur: float | None
    profit_factor: float | None
    score: float
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reasons"] = list(self.reasons)
        return payload


@dataclass(frozen=True)
class SignalMetaScore:
    signal_id: str
    strategy_name: str
    symbol: str
    regime: str
    cost_profile: str
    score: float
    strategy_score: float
    pair_score: float
    regime_score: float
    cost_score: float
    confidence_score: float
    capital_eligible: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reasons"] = list(self.reasons)
        return payload


@dataclass(frozen=True)
class TreasuryAllocationDecision:
    signal_id: str
    strategy_name: str
    symbol: str
    timestamp: str
    accepted: bool
    allocated_notional_eur: float
    reason: str
    sizing_equity_eur: float
    available_cash_eur: float
    research_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InstanceTreasurySimulation:
    instance: InstanceTreasury
    cost_profile: str
    initial_treasury: InstanceTreasury
    allocation_decisions: tuple[TreasuryAllocationDecision, ...]
    metrics: Mapping[str, Any]
    final_treasury: InstanceTreasury
    max_realized_drawdown_pct: float
    estimated_intratrade_drawdown_pct: float
    daily_loss_stop_days: tuple[str, ...]
    critical_drawdown_stop: bool
    strategy_exposure: Mapping[str, float]
    symbol_exposure: Mapping[str, float]
    status: StrategyResearchStatus = "active_research"
    live_promotion_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "instance": self.instance.to_dict(),
            "cost_profile": self.cost_profile,
            "initial_treasury": self.initial_treasury.to_dict(),
            "allocation_decisions": [item.to_dict() for item in self.allocation_decisions],
            "metrics": dict(self.metrics),
            "final_treasury": self.final_treasury.to_dict(),
            "max_realized_drawdown_pct": round(self.max_realized_drawdown_pct, 6),
            "estimated_intratrade_drawdown_pct": round(self.estimated_intratrade_drawdown_pct, 6),
            "daily_loss_stop_days": list(self.daily_loss_stop_days),
            "critical_drawdown_stop": self.critical_drawdown_stop,
            "strategy_exposure": {key: round(value, 6) for key, value in self.strategy_exposure.items()},
            "symbol_exposure": {key: round(value, 6) for key, value in self.symbol_exposure.items()},
            "status": self.status,
            "research_only": True,
            "live_promotion_allowed": False,
        }


@dataclass(frozen=True)
class SimulatedChildTreasuryPlan:
    virtual_child_instance_id: str
    parent_instance_id: str
    proposed_treasury_eur: float
    minimum_parent_reserve_eur: float
    split_decision: InstanceSplitDecision
    lineage_source: str
    child_created: bool = False
    live_promotion_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "virtual_child_instance_id": self.virtual_child_instance_id,
            "parent_instance_id": self.parent_instance_id,
            "proposed_treasury_eur": round(self.proposed_treasury_eur, 6),
            "minimum_parent_reserve_eur": round(self.minimum_parent_reserve_eur, 6),
            "split_decision": self.split_decision.to_dict(),
            "lineage_source": self.lineage_source,
            "child_created": False,
            "research_only": True,
            "live_promotion_allowed": False,
        }


@dataclass(frozen=True)
class StrategyOrchestratorConfig:
    run_id: str
    data_paths: tuple[Path, ...]
    output_dir: Path = Path("reports/research/strategy_orchestrator")
    instance_id: str = "research-parent-001"
    parent_instance_id: str | None = None
    instance_role: InstanceRole = "standalone"
    initial_treasury_eur: float = 500.0
    symbols: tuple[str, ...] = ()
    cost_profiles: tuple[str, ...] = ("paper_current_taker", "research_stress")
    max_instance_exposure_pct: float = 0.60
    max_strategy_exposure_pct: float = 0.50
    max_symbol_exposure_pct: float = 0.20
    risk_per_trade_pct: float = 0.01
    max_open_positions: int = 3
    cooldown_hours: float = 6.0
    max_daily_loss_pct: float = 0.03
    max_drawdown_pct: float = 0.10
    drawdown_reduce_start_pct: float = 0.05
    min_drawdown_exposure_multiplier: float = 0.35
    min_research_meta_score: float = 20.0
    signal_history_bars: int = 384
    high_conviction_min_expected_move_bps: float = 500.0
    high_conviction_risk_reward_ratio: float = 2.0
    high_conviction_max_hold_hours: float = 72.0
    high_conviction_train_window_bars: int = 288
    high_conviction_test_window_bars: int = 192
    high_conviction_step_window_bars: int | None = 192
    high_conviction_min_folds: int = 3
    high_conviction_exit_mode: str = "fixed_tp_sl"

    def __post_init__(self) -> None:
        if not self.run_id.strip() or not self.data_paths or not self.instance_id.strip():
            raise ValueError("run_id, data_paths and instance_id are required")
        if self.instance_role not in {"parent", "child", "standalone"}:
            raise ValueError("unsupported instance_role")
        if self.max_open_positions < 1 or self.signal_history_bars < 24:
            raise ValueError("max_open_positions and signal_history_bars are too small")
        for value in (
            self.initial_treasury_eur,
            self.max_instance_exposure_pct,
            self.max_strategy_exposure_pct,
            self.max_symbol_exposure_pct,
            self.risk_per_trade_pct,
            self.cooldown_hours,
            self.max_daily_loss_pct,
            self.max_drawdown_pct,
            self.drawdown_reduce_start_pct,
            self.min_drawdown_exposure_multiplier,
            self.high_conviction_min_expected_move_bps,
            self.high_conviction_risk_reward_ratio,
            self.high_conviction_max_hold_hours,
        ):
            if not math.isfinite(float(value)) or float(value) <= 0.0:
                raise ValueError("orchestrator numeric inputs must be positive and finite")
        if any(
            value > 1.0
            for value in (
                self.max_instance_exposure_pct,
                self.max_strategy_exposure_pct,
                self.max_symbol_exposure_pct,
                self.risk_per_trade_pct,
                self.max_daily_loss_pct,
                self.max_drawdown_pct,
                self.drawdown_reduce_start_pct,
                self.min_drawdown_exposure_multiplier,
            )
        ):
            raise ValueError("orchestrator fractions cannot exceed one")
        if self.drawdown_reduce_start_pct >= self.max_drawdown_pct:
            raise ValueError("drawdown_reduce_start_pct must be below max_drawdown_pct")
        if not self.cost_profiles:
            raise ValueError("cost_profiles must not be empty")


@dataclass(frozen=True)
class StrategyOrchestratorReport:
    run_id: str
    generated_at: str
    audit: Mapping[str, Any]
    config: Mapping[str, Any]
    instance_treasury: InstanceTreasury
    standardized_signals: tuple[StrategyResearchSignal, ...]
    strategy_scores: tuple[StrategyMetaScore, ...]
    pair_scores: tuple[PairResearchScore, ...]
    regime_scores: tuple[RegimeResearchScore, ...]
    signal_scores: tuple[SignalMetaScore, ...]
    treasury_simulations: tuple[InstanceTreasurySimulation, ...]
    simulated_child_plan: SimulatedChildTreasuryPlan
    high_conviction_walk_forward: Mapping[str, Any]
    final_status: StrategyResearchStatus
    paper_candidate_allowed: bool = False
    live_promotion_allowed: bool = False
    json_report_path: str | None = None
    markdown_report_path: str | None = None
    safety_notes: tuple[str, ...] = (
        "Research-only strategy orchestration.",
        "No runtime paper/live component, order router, executor or Kraken client is imported.",
        "No strategy is promoted automatically.",
        "No child instance is created; the split result is a virtual plan only.",
        "Sizing uses realized equity and available treasury only, never floating PnL.",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "audit": dict(self.audit),
            "config": dict(self.config),
            "instance_treasury": self.instance_treasury.to_dict(),
            "standardized_signals": [signal.to_dict() for signal in self.standardized_signals],
            "strategy_scores": [score.to_dict() for score in self.strategy_scores],
            "pair_scores": [score.to_dict() for score in self.pair_scores],
            "regime_scores": [score.to_dict() for score in self.regime_scores],
            "signal_scores": [score.to_dict() for score in self.signal_scores],
            "treasury_simulations": [simulation.to_dict() for simulation in self.treasury_simulations],
            "simulated_child_plan": self.simulated_child_plan.to_dict(),
            "high_conviction_walk_forward": dict(self.high_conviction_walk_forward),
            "final_status": self.final_status,
            "paper_candidate_allowed": False,
            "live_promotion_allowed": False,
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
            "safety_notes": list(self.safety_notes),
        }


@dataclass(frozen=True)
class _ReservedResearchPosition:
    signal: StrategyResearchSignal
    notional_eur: float
    exit_at: datetime


def adapt_high_conviction_setup(
    setup: DiscoverySetup,
    *,
    instance_id: str,
    cost_profile: str,
) -> StrategyResearchSignal:
    """Adapt an OHLCV High Conviction setup without granting it capital."""

    confidence = _clamp(
        (float(setup.expected_move_bps) / 1_000.0) * min(1.0, float(setup.risk_reward_estimate) / 3.0),
        0.0,
        1.0,
    )
    regime = "multi_timeframe_swing"
    return StrategyResearchSignal(
        strategy_name="high_conviction_swing",
        symbol=setup.symbol,
        timestamp=_as_datetime(setup.entry_at),
        direction=setup.side,
        confidence=confidence,
        expected_move_bps=float(setup.expected_move_bps),
        cost_profile=cost_profile,
        regime=regime,
        reason=setup.reason,
        metadata={
            "family": setup.family,
            "logical_stop_bps": setup.logical_stop_bps,
            "risk_reward_estimate": setup.risk_reward_estimate,
            "timeframe_signal": setup.timeframe_signal,
            "source": "high_conviction_discovery",
            "capital_eligible": True,
            **dict(setup.features),
        },
        research_only=True,
        instance_id=instance_id,
    )


def adapt_backtest_signal(
    signal: BacktestSignal,
    *,
    strategy_name: str,
    instance_id: str,
    cost_profile: str,
) -> StrategyResearchSignal:
    """Adapt existing trend/mean-reversion research generators to one schema."""

    metadata = dict(signal.metadata)
    edge = _float(metadata.get("gross_edge_bps"))
    estimated_cost = _positive_float(metadata.get("estimated_round_trip_cost_bps"), 80.0)
    confidence = _clamp(max(0.0, edge) / max(estimated_cost * 3.0, 1.0), 0.0, 1.0)
    return StrategyResearchSignal(
        strategy_name=strategy_name,
        symbol=signal.symbol,
        timestamp=_as_datetime(signal.timestamp),
        direction=signal.side,
        confidence=confidence,
        expected_move_bps=edge,
        cost_profile=cost_profile,
        regime=str(metadata.get("regime") or "unknown"),
        reason=signal.reason,
        metadata={
            **metadata,
            "source": "research_signal_generator",
            "capital_eligible": False,
            "no_capital_reason": "unvalidated_research_signal_only",
        },
        research_only=True,
        instance_id=instance_id,
    )


def adapt_relative_value_signal(
    signal: RelativeValueSignal,
    *,
    instance_id: str,
    cost_profile: str,
) -> StrategyResearchSignal:
    """Normalize a long-only relative-value signal while keeping it no-capital."""

    confidence = _clamp(abs(float(signal.zscore)) / 4.0 * max(0.0, float(signal.correlation)), 0.0, 1.0)
    return StrategyResearchSignal(
        strategy_name="relative_value",
        symbol=signal.target_symbol,
        timestamp=signal.entry_at,
        direction=signal.side,
        confidence=confidence,
        expected_move_bps=float(signal.expected_move_bps),
        cost_profile=cost_profile,
        regime="relative_value",
        reason="relative_value_zscore_entry",
        metadata={
            "relationship_id": signal.relationship_id,
            "reference_symbols": list(signal.reference_symbols),
            "zscore": signal.zscore,
            "correlation": signal.correlation,
            "cointegration_pvalue": signal.cointegration_pvalue,
            "capital_eligible": False,
            "no_capital_reason": "relative_value_no_go_research_signal_only",
        },
        research_only=True,
        instance_id=instance_id,
    )


def build_strategy_orchestrator_report(config: StrategyOrchestratorConfig) -> StrategyOrchestratorReport:
    """Build a multi-strategy research report without changing AUTOBOT runtime."""

    treasury = InstanceTreasury.starting(
        instance_id=config.instance_id,
        capital_eur=config.initial_treasury_eur,
        parent_instance_id=config.parent_instance_id,
        instance_role=config.instance_role,
        max_instance_exposure_pct=config.max_instance_exposure_pct,
        max_strategy_exposure_pct=config.max_strategy_exposure_pct,
        max_symbol_exposure_pct=config.max_symbol_exposure_pct,
        max_daily_loss_pct=config.max_daily_loss_pct,
        max_drawdown_pct=config.max_drawdown_pct,
    )
    high_conviction = _build_high_conviction_walk_forward(config)
    signals = list(_high_conviction_signals(high_conviction, config.instance_id))
    bars = _load_research_bars(config)
    signals.extend(_observation_signals_from_generators(bars, config))
    signals.sort(key=lambda item: (item.timestamp, item.strategy_name, item.symbol, item.signal_id))

    evidence = _build_strategy_evidence(high_conviction, signals)
    scores = tuple(_score_evidence(item, treasury) for item in evidence)
    score_by_strategy = {score.strategy_name: score for score in scores}
    pair_scores = _pair_research_scores(signals)
    pair_score_by_symbol = {score.symbol: score for score in pair_scores}
    regime_scores = _regime_research_scores(signals)
    regime_score_by_name = {score.regime: score for score in regime_scores}
    signal_scores = tuple(
        _score_signal(signal, score_by_strategy, pair_score_by_symbol, regime_score_by_name)
        for signal in signals
    )
    signal_score_by_id = {score.signal_id: score for score in signal_scores}
    simulations = tuple(
        simulate_instance_treasury(
            treasury=treasury,
            signals=signals,
            cost_profile=profile,
            scores=score_by_strategy,
            signal_scores=signal_score_by_id,
            config=config,
        )
        for profile in config.cost_profiles
    )
    high_score = score_by_strategy["high_conviction_swing"]
    child_plan = _simulated_child_plan(treasury, high_score, simulations)
    return StrategyOrchestratorReport(
        run_id=config.run_id,
        generated_at=_utc_now().isoformat(),
        audit=_duplication_audit(),
        config=_config_to_dict(config),
        instance_treasury=treasury,
        standardized_signals=tuple(signals),
        strategy_scores=scores,
        pair_scores=pair_scores,
        regime_scores=regime_scores,
        signal_scores=signal_scores,
        treasury_simulations=simulations,
        simulated_child_plan=child_plan,
        high_conviction_walk_forward={
            "run_id": high_conviction.run_id,
            "fold_count": high_conviction.fold_count,
            "decision": high_conviction.decision.to_dict(),
            "primary_aggregate": dict(high_conviction.primary_aggregate or {}),
        },
        final_status="active_research",
    )


def write_strategy_orchestrator_report(
    report: StrategyOrchestratorReport,
    output_dir: str | Path,
) -> StrategyOrchestratorReport:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / f"{report.run_id}.json"
    markdown_path = output / f"{report.run_id}.md"
    final = replace(report, json_report_path=str(json_path), markdown_report_path=str(markdown_path))
    json_path.write_text(json.dumps(final.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(render_strategy_orchestrator_report(final), encoding="utf-8")
    return final


def render_strategy_orchestrator_report(report: StrategyOrchestratorReport) -> str:
    lines = [
        f"# Strategy Orchestrator and Instance Treasury - {report.run_id}",
        "",
        "## Status",
        "",
        f"- Final status: `{report.final_status}`",
        "- Research-only: `true`",
        "- Paper candidate allowed: `false`",
        "- Live promotion allowed: `false`",
        f"- Instance split executor: `{report.audit['execution_flag']['effective']}`",
        "",
        "## Instance Treasury",
        "",
        "| Instance | Role | Treasury | Realized equity | Available cash | Reserved exposure | Unrealized PnL |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    treasury = report.instance_treasury
    lines.append(
        f"| {treasury.instance_id} | {treasury.instance_role} | {treasury.instance_treasury_eur:.2f} | "
        f"{treasury.realized_equity_eur:.2f} | {treasury.available_cash_eur:.2f} | "
        f"{treasury.reserved_exposure_eur:.2f} | {treasury.unrealized_pnl_eur:.2f} |"
    )
    lines.extend(
        [
            "",
            "## Signal Layer",
            "",
            "| Strategy | Signals | Capital eligible signals |",
            "| --- | ---: | ---: |",
        ]
    )
    by_strategy: dict[str, list[StrategyResearchSignal]] = defaultdict(list)
    for signal in report.standardized_signals:
        by_strategy[signal.strategy_name].append(signal)
    for strategy in ("high_conviction_swing", "trend_momentum", "mean_reversion", "relative_value", "grid"):
        rows = by_strategy.get(strategy, [])
        eligible = sum(1 for row in rows if bool(row.metadata.get("capital_eligible")))
        lines.append(f"| {strategy} | {len(rows)} | {eligible} |")

    lines.extend(
        [
            "",
            "## Meta Scores",
            "",
            "| Strategy | Score | Status | Candidate paper | Main blockers |",
            "| --- | ---: | --- | --- | --- |",
        ]
    )
    for score in report.strategy_scores:
        lines.append(
            f"| {score.strategy_name} | {score.score:.1f} | {score.status} | "
            f"{'yes' if score.candidate_paper_recommended else 'no'} | {', '.join(score.blockers) or '-'} |"
        )

    lines.extend(
        [
            "",
            "## Pair Scores",
            "",
            "| Pair | Score | Signals | Closed OOS trades | Net PnL | PF | Regime |",
            "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for score in report.pair_scores:
        lines.append(
            f"| {score.symbol} | {score.score:.1f} | {score.signal_count} | {score.closed_trade_count} | "
            f"{_metric_text(score.net_pnl_eur)} | {_metric_text(score.profit_factor)} | {score.regime} |"
        )

    lines.extend(
        [
            "",
            "## Regime Scores",
            "",
            "| Regime | Score | Signals | Closed OOS trades | Net PnL | PF |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for score in report.regime_scores:
        lines.append(
            f"| {score.regime} | {score.score:.1f} | {score.signal_count} | {score.closed_trade_count} | "
            f"{_metric_text(score.net_pnl_eur)} | {_metric_text(score.profit_factor)} |"
        )

    lines.extend(
        [
            "",
            "## Treasury Simulations",
            "",
            "| Cost profile | Net PnL | PF | Trades | Win rate | Realized DD | Intratrade DD | Accepted allocations |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for simulation in report.treasury_simulations:
        metrics = simulation.metrics
        accepted = sum(1 for item in simulation.allocation_decisions if item.accepted)
        lines.append(
            f"| {simulation.cost_profile} | {_float(metrics.get('total_net_pnl_eur')):.2f} | "
            f"{_metric_text(metrics.get('profit_factor'))} | {int(_float(metrics.get('trade_count')))} | "
            f"{_metric_text(metrics.get('winrate_pct'))} | {simulation.max_realized_drawdown_pct:.2f}% | "
            f"{simulation.estimated_intratrade_drawdown_pct:.2f}% | {accepted} |"
        )

    child = report.simulated_child_plan
    lines.extend(
        [
            "",
            "## Future Split Compatibility",
            "",
            f"- Virtual child id: `{child.virtual_child_instance_id}`",
            f"- Child created: `false`",
            f"- Proposed child treasury: `{child.proposed_treasury_eur:.2f} EUR`",
            f"- Parent reserve after proposal: `{child.minimum_parent_reserve_eur:.2f} EUR`",
            f"- Policy status: `{child.split_decision.status}`",
            f"- Blockers: `{', '.join(child.split_decision.blockers) or 'none'}`",
            f"- Executor flag is not read for execution; effective value: `{child.split_decision.executor_enabled}`",
            "",
            "## Existing Duplication Audit",
            "",
        ]
    )
    for item in report.audit["findings"]:
        lines.append(f"- {item}")
    lines.extend(["", "## Safety", ""])
    lines.extend(f"- {note}" for note in report.safety_notes)
    lines.append("")
    return "\n".join(lines)


def simulate_instance_treasury(
    *,
    treasury: InstanceTreasury,
    signals: Sequence[StrategyResearchSignal],
    cost_profile: str,
    scores: Mapping[str, StrategyMetaScore],
    config: StrategyOrchestratorConfig,
    signal_scores: Mapping[str, SignalMetaScore] | None = None,
) -> InstanceTreasurySimulation:
    """Replay known research outcomes using cash and realized equity only.

    A signal must carry a known simulated exit and net return. Trend,
    mean-reversion and relative-value signals remain observable but cannot
    reserve capital until their own validation evidence passes.
    """

    cash = float(treasury.available_cash_eur)
    realized_pnl = float(treasury.realized_pnl_eur)
    reserved = 0.0
    peak_realized_equity = float(treasury.realized_equity_eur)
    max_realized_drawdown = 0.0
    max_intratrade_drawdown = 0.0
    open_positions: list[_ReservedResearchPosition] = []
    cooldown_until: dict[str, datetime] = {}
    daily_pnl: dict[date, float] = defaultdict(float)
    daily_start_equity: dict[date, float] = {}
    daily_stops: set[date] = set()
    decisions: list[TreasuryAllocationDecision] = []
    records: list[TradeRecord] = []
    strategy_exposure: dict[str, float] = defaultdict(float)
    symbol_exposure: dict[str, float] = defaultdict(float)
    critical_stop = False

    profile_signals = [
        signal
        for signal in signals
        if signal.cost_profile == cost_profile and signal.direction.lower() == "buy"
    ]
    profile_signals.sort(key=lambda item: (item.timestamp, item.signal_id))

    def realized_equity() -> float:
        return max(0.0, treasury.instance_treasury_eur + realized_pnl)

    def settle_due(at: datetime) -> None:
        nonlocal cash, realized_pnl, reserved, peak_realized_equity, max_realized_drawdown
        remaining: list[_ReservedResearchPosition] = []
        for position in open_positions:
            if position.exit_at > at:
                remaining.append(position)
                continue
            record = _trade_record_from_signal(position.signal, position.notional_eur, config.run_id)
            cash += position.notional_eur + record.net_pnl_eur
            realized_pnl += record.net_pnl_eur
            reserved -= position.notional_eur
            strategy_exposure[position.signal.strategy_name] -= position.notional_eur
            symbol_exposure[position.signal.symbol] -= position.notional_eur
            records.append(record)
            cooldown_until[position.signal.symbol] = position.exit_at.replace(tzinfo=timezone.utc) + timedelta(
                hours=config.cooldown_hours
            )
            current_equity = realized_equity()
            peak_realized_equity = max(peak_realized_equity, current_equity)
            drawdown = max(0.0, peak_realized_equity - current_equity)
            drawdown_pct = drawdown / peak_realized_equity if peak_realized_equity else 0.0
            max_realized_drawdown = max(max_realized_drawdown, drawdown_pct)
            exit_day = position.exit_at.date()
            daily_pnl[exit_day] += record.net_pnl_eur
            daily_start_equity.setdefault(exit_day, max(0.0, current_equity - record.net_pnl_eur))
            if daily_pnl[exit_day] <= -(daily_start_equity[exit_day] * treasury.max_daily_loss_pct):
                daily_stops.add(exit_day)
        open_positions[:] = remaining

    for signal in profile_signals:
        settle_due(signal.timestamp)
        current_equity = realized_equity()
        current_day = signal.timestamp.date()
        daily_start_equity.setdefault(current_day, current_equity)
        score = scores.get(signal.strategy_name)
        signal_score = (signal_scores or {}).get(signal.signal_id)
        rejection = _allocation_blocker(
            signal=signal,
            score=score,
            signal_score=signal_score,
            at=signal.timestamp,
            treasury=treasury,
            open_positions=open_positions,
            cooldown_until=cooldown_until,
            daily_stops=daily_stops,
            critical_stop=critical_stop,
            config=config,
        )
        if rejection is not None:
            decisions.append(
                TreasuryAllocationDecision(
                    signal_id=signal.signal_id,
                    strategy_name=signal.strategy_name,
                    symbol=signal.symbol,
                    timestamp=signal.timestamp.isoformat(),
                    accepted=False,
                    allocated_notional_eur=0.0,
                    reason=rejection,
                    sizing_equity_eur=current_equity,
                    available_cash_eur=cash,
                )
            )
            continue

        multiplier = _drawdown_multiplier(config, max_realized_drawdown)
        strategy_cap = current_equity * treasury.max_strategy_exposure_pct * multiplier
        symbol_cap = current_equity * treasury.max_symbol_exposure_pct * multiplier
        instance_cap = current_equity * treasury.max_instance_exposure_pct * multiplier
        stop_bps = max(_positive_float(signal.metadata.get("logical_stop_bps"), 100.0), 1.0)
        risk_cap = current_equity * config.risk_per_trade_pct / (stop_bps / 10_000.0)
        notional = min(
            cash,
            max(0.0, strategy_cap - strategy_exposure[signal.strategy_name]),
            max(0.0, symbol_cap - symbol_exposure[signal.symbol]),
            max(0.0, instance_cap - reserved),
            risk_cap,
        )
        if notional < 5.0:
            decisions.append(
                TreasuryAllocationDecision(
                    signal_id=signal.signal_id,
                    strategy_name=signal.strategy_name,
                    symbol=signal.symbol,
                    timestamp=signal.timestamp.isoformat(),
                    accepted=False,
                    allocated_notional_eur=0.0,
                    reason="treasury_or_risk_limit_below_minimum_notional",
                    sizing_equity_eur=current_equity,
                    available_cash_eur=cash,
                )
            )
            continue

        exit_at = _signal_exit_at(signal)
        cash -= notional
        reserved += notional
        strategy_exposure[signal.strategy_name] += notional
        symbol_exposure[signal.symbol] += notional
        open_positions.append(_ReservedResearchPosition(signal=signal, notional_eur=notional, exit_at=exit_at))
        adverse_bps = abs(min(0.0, _float(signal.metadata.get("mae_bps"))))
        adverse_equity = current_equity - (notional * adverse_bps / 10_000.0)
        if peak_realized_equity > 0.0:
            max_intratrade_drawdown = max(
                max_intratrade_drawdown,
                max(0.0, peak_realized_equity - adverse_equity) / peak_realized_equity,
            )
        if max(max_realized_drawdown, max_intratrade_drawdown) > treasury.max_drawdown_pct:
            critical_stop = True
        decisions.append(
            TreasuryAllocationDecision(
                signal_id=signal.signal_id,
                strategy_name=signal.strategy_name,
                symbol=signal.symbol,
                timestamp=signal.timestamp.isoformat(),
                accepted=True,
                allocated_notional_eur=round(notional, 6),
                reason="research_treasury_allocation",
                sizing_equity_eur=current_equity,
                available_cash_eur=cash,
            )
        )

    for position in sorted(open_positions, key=lambda item: item.exit_at):
        settle_due(position.exit_at)

    final_equity = realized_equity()
    final_treasury = replace(
        treasury,
        realized_equity_eur=final_equity,
        available_cash_eur=max(0.0, cash),
        reserved_exposure_eur=max(0.0, reserved),
        realized_pnl_eur=realized_pnl,
        unrealized_pnl_eur=0.0,
    )
    metrics = MetricsEngine().calculate(TradeJournal(records).records, initial_capital_eur=treasury.instance_treasury_eur)
    return InstanceTreasurySimulation(
        instance=treasury,
        cost_profile=cost_profile,
        initial_treasury=treasury,
        allocation_decisions=tuple(decisions),
        metrics=metrics.to_dict(),
        final_treasury=final_treasury,
        max_realized_drawdown_pct=max_realized_drawdown * 100.0,
        estimated_intratrade_drawdown_pct=max_intratrade_drawdown * 100.0,
        daily_loss_stop_days=tuple(sorted(day.isoformat() for day in daily_stops)),
        critical_drawdown_stop=critical_stop,
        strategy_exposure={key: max(0.0, value) for key, value in strategy_exposure.items()},
        symbol_exposure={key: max(0.0, value) for key, value in symbol_exposure.items()},
    )


def _build_high_conviction_walk_forward(config: StrategyOrchestratorConfig) -> HighConvictionWalkForwardReport:
    return build_high_conviction_walk_forward_report(
        HighConvictionWalkForwardConfig(
            run_id=f"{config.run_id}_high_conviction",
            data_paths=config.data_paths,
            symbols=config.symbols,
            cost_profiles=config.cost_profiles,
            policies=("conservative",),
            primary_cost_profile="research_stress" if "research_stress" in config.cost_profiles else config.cost_profiles[0],
            primary_policy="conservative",
            initial_capital_eur=config.initial_treasury_eur,
            max_position_fraction=config.max_symbol_exposure_pct,
            risk_per_trade_pct=config.risk_per_trade_pct,
            max_global_exposure_pct=config.max_instance_exposure_pct,
            max_open_positions=config.max_open_positions,
            cooldown_hours=config.cooldown_hours,
            max_daily_loss_pct=config.max_daily_loss_pct,
            critical_drawdown_pct=config.max_drawdown_pct,
            drawdown_reduce_start_pct=config.drawdown_reduce_start_pct,
            min_drawdown_exposure_multiplier=config.min_drawdown_exposure_multiplier,
            min_expected_move_bps=config.high_conviction_min_expected_move_bps,
            risk_reward_ratio=config.high_conviction_risk_reward_ratio,
            max_hold_hours=config.high_conviction_max_hold_hours,
            exit_modes=(config.high_conviction_exit_mode,),
            primary_exit_mode=config.high_conviction_exit_mode,
            train_window_bars=config.high_conviction_train_window_bars,
            test_window_bars=config.high_conviction_test_window_bars,
            step_window_bars=config.high_conviction_step_window_bars,
            min_folds=config.high_conviction_min_folds,
            min_closed_trades_for_review=50,
            min_profit_factor=1.30,
            max_drawdown_pct=0.10,
            min_positive_fold_ratio=0.80,
            max_single_symbol_positive_pnl_share=0.40,
        )
    )


def _load_research_bars(config: StrategyOrchestratorConfig):
    discovery_config = HighConvictionDiscoveryConfig(
        run_id=f"{config.run_id}_signal_layer",
        data_paths=config.data_paths,
        symbols=config.symbols,
        min_expected_move_bps=(config.high_conviction_min_expected_move_bps,),
        risk_reward_ratios=(config.high_conviction_risk_reward_ratio,),
        max_hold_hours=(config.high_conviction_max_hold_hours,),
        exit_modes=(config.high_conviction_exit_mode,),
    )
    bars, _duplicates = _deduplicate_bars(_load_ohlcv_bars(discovery_config))
    return bars


def _high_conviction_signals(
    report: HighConvictionWalkForwardReport,
    instance_id: str,
) -> Iterable[StrategyResearchSignal]:
    for fold in report.folds:
        if fold.policy != "conservative" or fold.scenario.get("exit_mode") != "fixed_tp_sl":
            continue
        for record in fold.portfolio.trade_records:
            source_notional = max(record.quantity * record.entry_price, 1e-12)
            net_return_bps = record.net_pnl_eur / source_notional * 10_000.0
            gross_return_bps = record.gross_pnl_eur / source_notional * 10_000.0
            expected_move_bps = _positive_float(record.metadata.get("expected_move_bps"), 0.0)
            yield StrategyResearchSignal(
                strategy_name="high_conviction_swing",
                symbol=record.symbol,
                timestamp=record.opened_at,
                direction=record.side,
                confidence=_clamp(expected_move_bps / 1_000.0, 0.0, 1.0),
                expected_move_bps=expected_move_bps,
                cost_profile=fold.cost_profile,
                regime="multi_timeframe_swing",
                reason=record.entry_reason,
                metadata={
                    "capital_eligible": True,
                    "exit_at": record.closed_at.isoformat(),
                    "entry_price": record.entry_price,
                    "exit_price": record.exit_price,
                    "source_notional_eur": source_notional,
                    "gross_pnl_eur": record.gross_pnl_eur,
                    "net_pnl_eur": record.net_pnl_eur,
                    "fees_eur": record.fees_eur,
                    "spread_cost_eur": record.spread_cost_eur,
                    "slippage_eur": record.slippage_eur,
                    "latency_cost_eur": record.latency_cost_eur,
                    "exit_reason": record.exit_reason,
                    "gross_return_bps": gross_return_bps,
                    "net_return_bps": net_return_bps,
                    "logical_stop_bps": record.metadata.get("logical_stop_bps"),
                    "mae_bps": record.metadata.get("mae_bps"),
                    "mfe_bps": record.metadata.get("mfe_bps"),
                    "family": record.metadata.get("family"),
                    "source": "high_conviction_walk_forward_out_of_sample",
                },
                research_only=True,
                instance_id=instance_id,
                signal_id=f"{fold.cost_profile}:{record.run_id}:{record.symbol}:{record.opened_at.isoformat()}",
            )


def _observation_signals_from_generators(
    bars: Sequence[Any],
    config: StrategyOrchestratorConfig,
) -> list[StrategyResearchSignal]:
    groups = _group_by_symbol_timeframe(bars)
    signals: list[StrategyResearchSignal] = []
    factories = (
        ("trend_momentum", TrendResearchSignalGenerator),
        ("mean_reversion", MeanReversionResearchSignalGenerator),
    )
    for (symbol, timeframe), rows in groups.items():
        if timeframe != "15m":
            continue
        window = list(rows)[-config.signal_history_bars :]
        for strategy_name, factory in factories:
            generator = factory()
            history: list[Any] = []
            for bar in window:
                history.append(bar)
                for raw_signal in generator(bar, tuple(history)):
                    signals.append(
                        adapt_backtest_signal(
                            raw_signal,
                            strategy_name=strategy_name,
                            instance_id=config.instance_id,
                            cost_profile="research_stress",
                        )
                    )
    return signals


def _build_strategy_evidence(
    high_conviction: HighConvictionWalkForwardReport,
    signals: Sequence[StrategyResearchSignal],
) -> tuple[StrategyPerformanceEvidence, ...]:
    primary = high_conviction.primary_aggregate or {}
    high_signals = sum(1 for signal in signals if signal.strategy_name == "high_conviction_swing")
    high_evidence = StrategyPerformanceEvidence(
        strategy_name="high_conviction_swing",
        status="active_research",
        cost_profile=str(primary.get("cost_profile") or "research_stress"),
        signal_count=high_signals,
        trade_count=int(_float(primary.get("total_trade_count"))),
        net_pnl_eur=_float(primary.get("total_net_pnl_eur")),
        profit_factor=_optional_metric(primary.get("profit_factor")),
        winrate_pct=_optional_metric(primary.get("winrate_pct")),
        max_drawdown_pct=_optional_metric(primary.get("worst_fold_drawdown_pct")),
        positive_folds=int(_float(primary.get("positive_fold_count"))),
        total_folds=int(_float(primary.get("fold_count"))),
        largest_positive_symbol_share=_optional_metric(primary.get("largest_positive_symbol_share")),
        validation_days=_validation_days(high_conviction),
        costs_covered=_float(primary.get("total_net_pnl_eur")) > 0.0,
        runtime_comparable=str(primary.get("cost_profile") or "") != "research_legacy",
        failure_reasons=tuple(high_conviction.decision.reasons),
        source="high_conviction_walk_forward_out_of_sample",
    )
    evidence: list[StrategyPerformanceEvidence] = [high_evidence]
    for strategy_name in ("trend_momentum", "mean_reversion"):
        evidence.append(
            StrategyPerformanceEvidence(
                strategy_name=strategy_name,
                status="research_signal_only",
                cost_profile="research_stress",
                signal_count=sum(1 for signal in signals if signal.strategy_name == strategy_name),
                trade_count=0,
                net_pnl_eur=None,
                profit_factor=None,
                winrate_pct=None,
                max_drawdown_pct=None,
                positive_folds=0,
                total_folds=0,
                largest_positive_symbol_share=None,
                validation_days=0,
                costs_covered=False,
                runtime_comparable=True,
                failure_reasons=("no_portfolio_aware_walk_forward_evidence",),
                source="research_signal_generator_observation",
            )
        )
    evidence.extend(
        (
            StrategyPerformanceEvidence(
                strategy_name="relative_value",
                status="no_go",
                cost_profile="research_stress",
                signal_count=0,
                trade_count=0,
                net_pnl_eur=None,
                profit_factor=None,
                winrate_pct=None,
                max_drawdown_pct=None,
                positive_folds=0,
                total_folds=0,
                largest_positive_symbol_share=None,
                validation_days=0,
                costs_covered=False,
                runtime_comparable=True,
                failure_reasons=("relative_value_last_validation_no_go", "no_capital_allocation"),
                source="relative_value_research_verdict",
            ),
            StrategyPerformanceEvidence(
                strategy_name="grid",
                status="archived",
                cost_profile="research_stress",
                signal_count=0,
                trade_count=0,
                net_pnl_eur=None,
                profit_factor=None,
                winrate_pct=None,
                max_drawdown_pct=None,
                positive_folds=0,
                total_folds=0,
                largest_positive_symbol_share=None,
                validation_days=0,
                costs_covered=False,
                runtime_comparable=True,
                failure_reasons=("grid_archived_no_go_after_costs",),
                source="grid_retirement",
            ),
        )
    )
    return tuple(evidence)


def _score_evidence(evidence: StrategyPerformanceEvidence, treasury: InstanceTreasury) -> StrategyMetaScore:
    if evidence.status in {"archived", "no_go"}:
        return StrategyMetaScore(
            strategy_name=evidence.strategy_name,
            score=0.0,
            status=evidence.status,
            candidate_paper_recommended=False,
            reasons=("strategy_is_not_capital_eligible",),
            blockers=evidence.failure_reasons,
            evidence=evidence,
        )
    if evidence.status == "research_signal_only":
        return StrategyMetaScore(
            strategy_name=evidence.strategy_name,
            score=0.0,
            status="research_signal_only",
            candidate_paper_recommended=False,
            reasons=("signals_are_observed_but_not_portfolio_validated",),
            blockers=evidence.failure_reasons,
            evidence=evidence,
        )

    pf = evidence.profit_factor or 0.0
    winrate = evidence.winrate_pct or 0.0
    drawdown = evidence.max_drawdown_pct if evidence.max_drawdown_pct is not None else 100.0
    concentration = evidence.largest_positive_symbol_share if evidence.largest_positive_symbol_share is not None else 1.0
    fold_ratio = evidence.positive_folds / evidence.total_folds if evidence.total_folds else 0.0
    score = (
        min(max(pf - 1.0, 0.0) / 0.30, 1.0) * 25.0
        + min(evidence.trade_count / 50.0, 1.0) * 20.0
        + min(fold_ratio / 0.80, 1.0) * 20.0
        + max(0.0, 1.0 - (drawdown / 10.0)) * 15.0
        + max(0.0, 1.0 - (concentration / 0.40)) * 10.0
        + min(max(winrate, 0.0) / 60.0, 1.0) * 5.0
        + (5.0 if evidence.costs_covered and evidence.runtime_comparable else 0.0)
    )
    blockers: list[str] = []
    if evidence.trade_count < 50:
        blockers.append("insufficient_closed_trades_under_50")
    if pf <= 1.30:
        blockers.append("profit_factor_not_above_1_30")
    if drawdown > 10.0:
        blockers.append("max_drawdown_above_10_pct")
    if evidence.total_folds < 5 or evidence.positive_folds < 4:
        blockers.append("fewer_than_4_of_5_positive_folds")
    if concentration > 0.40:
        blockers.append("single_symbol_positive_pnl_above_40_pct")
    if not evidence.costs_covered:
        blockers.append("costs_not_covered")
    if not evidence.runtime_comparable:
        blockers.append("legacy_or_non_comparable_cost_profile")
    if evidence.validation_days < 7:
        blockers.append("validation_window_too_short")
    if treasury.available_cash_eur < 5.0:
        blockers.append("instance_treasury_insufficient")
    candidate = not blockers
    return StrategyMetaScore(
        strategy_name=evidence.strategy_name,
        score=round(score, 6),
        status="candidate_paper" if candidate else "active_research",
        candidate_paper_recommended=candidate,
        reasons=("meta_score_combines_costs_folds_drawdown_and_concentration",),
        blockers=tuple(blockers),
        evidence=evidence,
    )


def _pair_research_scores(signals: Sequence[StrategyResearchSignal]) -> tuple[PairResearchScore, ...]:
    """Score pair evidence without treating a single positive pair as proof."""

    grouped: dict[str, list[StrategyResearchSignal]] = defaultdict(list)
    for signal in signals:
        grouped[signal.symbol].append(signal)
    results: list[PairResearchScore] = []
    for symbol, rows in grouped.items():
        outcomes = [
            row
            for row in rows
            if row.strategy_name == "high_conviction_swing"
            and row.cost_profile == "research_stress"
            and "net_pnl_eur" in row.metadata
        ]
        pnl_values = [_float(row.metadata.get("net_pnl_eur")) for row in outcomes]
        gains = sum(value for value in pnl_values if value > 0.0)
        losses = abs(sum(value for value in pnl_values if value < 0.0))
        pf = (gains / losses) if losses > 0.0 else (None if not gains else float("inf"))
        winrate = (sum(1 for value in pnl_values if value > 0.0) / len(pnl_values) * 100.0) if pnl_values else None
        confidence = mean(row.confidence for row in rows) if rows else 0.0
        pf_component = 25.0 if pf is not None and math.isfinite(pf) and pf >= 1.30 else 0.0
        pnl_component = 25.0 if sum(pnl_values) > 0.0 else 0.0
        sample_component = min(len(outcomes) / 10.0, 1.0) * 20.0
        confidence_component = confidence * 15.0
        win_component = min((winrate or 0.0) / 60.0, 1.0) * 15.0
        reasons = ["research_pair_score"]
        if not outcomes:
            reasons.append("no_closed_out_of_sample_trade_for_pair")
        elif len(outcomes) < 10:
            reasons.append("pair_sample_small")
        if sum(pnl_values) <= 0.0:
            reasons.append("pair_net_pnl_not_positive")
        results.append(
            PairResearchScore(
                symbol=symbol,
                signal_count=len(rows),
                closed_trade_count=len(outcomes),
                net_pnl_eur=round(sum(pnl_values), 6) if outcomes else None,
                profit_factor=pf if pf is None or math.isfinite(pf) else None,
                winrate_pct=winrate,
                score=round(pf_component + pnl_component + sample_component + confidence_component + win_component, 6),
                regime=_dominant_regime(outcomes or rows),
                reasons=tuple(reasons),
            )
        )
    return tuple(sorted(results, key=lambda item: (item.score, item.symbol), reverse=True))


def _regime_research_scores(signals: Sequence[StrategyResearchSignal]) -> tuple[RegimeResearchScore, ...]:
    grouped: dict[str, list[StrategyResearchSignal]] = defaultdict(list)
    for signal in signals:
        grouped[signal.regime].append(signal)
    results: list[RegimeResearchScore] = []
    for regime, rows in grouped.items():
        outcomes = [
            row
            for row in rows
            if row.strategy_name == "high_conviction_swing"
            and row.cost_profile == "research_stress"
            and "net_pnl_eur" in row.metadata
        ]
        values = [_float(row.metadata.get("net_pnl_eur")) for row in outcomes]
        gains = sum(value for value in values if value > 0.0)
        losses = abs(sum(value for value in values if value < 0.0))
        pf = (gains / losses) if losses > 0.0 else (None if not gains else float("inf"))
        confidence = mean(row.confidence for row in rows) if rows else 0.0
        score = (
            (30.0 if values and sum(values) > 0.0 else 0.0)
            + (25.0 if pf is not None and math.isfinite(pf) and pf >= 1.30 else 0.0)
            + min(len(outcomes) / 20.0, 1.0) * 25.0
            + confidence * 20.0
        )
        reasons = ["research_regime_score"]
        if not outcomes:
            reasons.append("no_closed_out_of_sample_trade_for_regime")
        results.append(
            RegimeResearchScore(
                regime=regime,
                signal_count=len(rows),
                closed_trade_count=len(outcomes),
                net_pnl_eur=round(sum(values), 6) if outcomes else None,
                profit_factor=pf if pf is None or math.isfinite(pf) else None,
                score=round(score, 6),
                reasons=tuple(reasons),
            )
        )
    return tuple(sorted(results, key=lambda item: (item.score, item.regime), reverse=True))


def _score_signal(
    signal: StrategyResearchSignal,
    strategy_scores: Mapping[str, StrategyMetaScore],
    pair_scores: Mapping[str, PairResearchScore],
    regime_scores: Mapping[str, RegimeResearchScore],
) -> SignalMetaScore:
    strategy = strategy_scores.get(signal.strategy_name)
    pair = pair_scores.get(signal.symbol)
    strategy_score = strategy.score if strategy else 0.0
    pair_score = pair.score if pair else 0.0
    regime_score = regime_scores.get(signal.regime).score if signal.regime in regime_scores else 0.0
    cost_score = 10.0 if signal.cost_profile != "research_legacy" else 0.0
    confidence_score = signal.confidence * 10.0
    score = _clamp(
        strategy_score * 0.45
        + pair_score * 0.25
        + regime_score * 0.15
        + cost_score
        + confidence_score,
        0.0,
        100.0,
    )
    reasons = ["strategy_pair_regime_cost_confidence_weighted"]
    if not bool(signal.metadata.get("capital_eligible")):
        reasons.append(str(signal.metadata.get("no_capital_reason") or "research_signal_only"))
    return SignalMetaScore(
        signal_id=signal.signal_id,
        strategy_name=signal.strategy_name,
        symbol=signal.symbol,
        regime=signal.regime,
        cost_profile=signal.cost_profile,
        score=round(score, 6),
        strategy_score=round(strategy_score, 6),
        pair_score=round(pair_score, 6),
        regime_score=round(regime_score, 6),
        cost_score=round(cost_score, 6),
        confidence_score=round(confidence_score, 6),
        capital_eligible=bool(signal.metadata.get("capital_eligible")),
        reasons=tuple(reasons),
    )


def _dominant_regime(signals: Sequence[StrategyResearchSignal]) -> str:
    if not signals:
        return "unknown"
    counts = Counter(signal.regime for signal in signals)
    return counts.most_common(1)[0][0]


def _allocation_blocker(
    *,
    signal: StrategyResearchSignal,
    score: StrategyMetaScore | None,
    signal_score: SignalMetaScore | None,
    at: datetime,
    treasury: InstanceTreasury,
    open_positions: Sequence[_ReservedResearchPosition],
    cooldown_until: Mapping[str, datetime],
    daily_stops: set[date],
    critical_stop: bool,
    config: StrategyOrchestratorConfig,
) -> str | None:
    if not signal.research_only:
        return "research_only_contract_violation"
    if not bool(signal.metadata.get("capital_eligible")):
        return str(signal.metadata.get("no_capital_reason") or "research_signal_only_no_capital")
    if score is None or score.status in {"archived", "no_go", "research_signal_only"}:
        return "strategy_not_capital_eligible"
    effective_score = signal_score.score if signal_score is not None else score.score
    if effective_score < config.min_research_meta_score:
        return "meta_score_below_research_allocation_minimum"
    if critical_stop:
        return "critical_drawdown_stop"
    if at.date() in daily_stops:
        return "daily_loss_stop"
    if any(position.signal.symbol == signal.symbol for position in open_positions):
        return "one_position_per_symbol"
    if len(open_positions) >= config.max_open_positions:
        return "max_open_positions"
    if cooldown_until.get(signal.symbol, datetime.min.replace(tzinfo=timezone.utc)) > at:
        return "symbol_cooldown"
    return None


def _trade_record_from_signal(signal: StrategyResearchSignal, notional_eur: float, run_id: str) -> TradeRecord:
    metadata = signal.metadata
    source_notional = max(_positive_float(metadata.get("source_notional_eur"), notional_eur), 1e-12)
    scale = notional_eur / source_notional
    entry_price = max(_positive_float(metadata.get("entry_price"), 1.0), 1e-12)
    exit_price = max(_positive_float(metadata.get("exit_price"), entry_price), 1e-12)
    return TradeRecord(
        run_id=run_id,
        strategy_id=signal.strategy_name,
        symbol=signal.symbol,
        side=signal.direction,
        opened_at=signal.timestamp,
        closed_at=_signal_exit_at(signal),
        quantity=notional_eur / entry_price,
        entry_price=entry_price,
        exit_price=exit_price,
        gross_pnl_eur=_float(metadata.get("gross_pnl_eur")) * scale,
        net_pnl_eur=_float(metadata.get("net_pnl_eur")) * scale,
        fees_eur=_float(metadata.get("fees_eur")) * scale,
        spread_cost_eur=_float(metadata.get("spread_cost_eur")) * scale,
        slippage_eur=_float(metadata.get("slippage_eur")) * scale,
        latency_cost_eur=_float(metadata.get("latency_cost_eur")) * scale,
        entry_reason=signal.reason,
        exit_reason=str(metadata.get("exit_reason") or "research_simulated_exit"),
        metadata={"source_signal_id": signal.signal_id, "cost_profile": signal.cost_profile, **dict(metadata)},
    )


def _signal_exit_at(signal: StrategyResearchSignal) -> datetime:
    raw = signal.metadata.get("exit_at")
    if raw:
        return _as_datetime(raw)
    return signal.timestamp


def _drawdown_multiplier(config: StrategyOrchestratorConfig, drawdown_pct: float) -> float:
    threshold = config.drawdown_reduce_start_pct
    if drawdown_pct <= threshold:
        return 1.0
    progress = (drawdown_pct - threshold) / max(config.max_drawdown_pct - threshold, 1e-12)
    return max(
        config.min_drawdown_exposure_multiplier,
        1.0 - min(1.0, progress) * (1.0 - config.min_drawdown_exposure_multiplier),
    )


def _simulated_child_plan(
    treasury: InstanceTreasury,
    score: StrategyMetaScore,
    simulations: Sequence[InstanceTreasurySimulation],
) -> SimulatedChildTreasuryPlan:
    reference = next((item for item in simulations if item.cost_profile == "research_stress"), simulations[0])
    metrics = reference.metrics
    # Explicit config means the host environment cannot turn a report into an
    # executor even if someone exports ENABLE_INSTANCE_SPLIT_EXECUTOR=true.
    policy = InstanceSplitPolicy(InstanceSplitPolicyConfig(executor_enabled=False))
    decision = policy.evaluate(
        InstanceSplitEvidence(
            parent_instance_id=treasury.instance_id,
            parent_capital_eur=reference.final_treasury.realized_equity_eur,
            parent_available_eur=reference.final_treasury.available_cash_eur,
            parent_lifetime_split_count=0,
            lineage_verified=False,
            paper_mode=True,
            strategy_id=score.strategy_name,
            strategy_status="paper_validated" if score.candidate_paper_recommended else "research_only",
            net_pnl_eur=_float(metrics.get("total_net_pnl_eur")),
            profit_factor=_optional_metric(metrics.get("profit_factor")),
            trade_count=int(_float(metrics.get("trade_count"))),
            validation_days=score.evidence.validation_days,
            max_drawdown_pct=reference.estimated_intratrade_drawdown_pct,
            strategy_scorecard=score.score,
            dominant_failure_mode=None,
            official_paper_net_pnl_eur=0.0,
            live_promotion_allowed=False,
            metadata={"source": "research_instance_treasury", "lineage": "virtual_unverified"},
        )
    )
    proposed = decision.planned_child_capital_eur
    return SimulatedChildTreasuryPlan(
        virtual_child_instance_id=f"{treasury.instance_id}-research-child-1",
        parent_instance_id=treasury.instance_id,
        proposed_treasury_eur=proposed,
        minimum_parent_reserve_eur=max(0.0, reference.final_treasury.realized_equity_eur - proposed),
        split_decision=decision,
        lineage_source="virtual_plan_only; persistent instance_lineage intentionally not written",
    )


def _validation_days(report: HighConvictionWalkForwardReport) -> int:
    if not report.folds:
        return 0
    starts = [_as_datetime(fold.test_start_at) for fold in report.folds]
    ends = [_as_datetime(fold.test_end_at) for fold in report.folds]
    return max(0, int((max(ends) - min(starts)).total_seconds() // 86_400))


def _optional_metric(value: Any) -> float | None:
    if value is None:
        return None
    result = _float(value, float("nan"))
    return result if math.isfinite(result) else None


def _config_to_dict(config: StrategyOrchestratorConfig) -> dict[str, Any]:
    payload = asdict(config)
    payload["data_paths"] = [str(path) for path in config.data_paths]
    payload["output_dir"] = str(config.output_dir)
    payload["symbols"] = list(config.symbols)
    payload["cost_profiles"] = list(config.cost_profiles)
    payload["research_only"] = True
    payload["paper_candidate_allowed"] = False
    payload["live_promotion_allowed"] = False
    return payload


def _duplication_audit() -> dict[str, Any]:
    return {
        "execution_flag": {
            "name": EXECUTION_FLAG_NAME,
            "effective": False,
            "reason": "research orchestrator constructs InstanceSplitPolicyConfig(executor_enabled=False)",
        },
        "findings": [
            "instance_split_policy.py evaluates capital, validation, lineage and failure-mode evidence; execution is disabled by default.",
            "instance_split_planner.py is read-only and only counts persisted instance_lineage rows before planning.",
            "persistence.py owns the real instance_lineage table; this research module never opens or writes it.",
            "instance_split_validation_harness.py proves mechanics in an isolated SQLite sandbox only.",
            "No existing production meta-allocator connects strategy research evidence to child treasury creation.",
            "This module prepares that contract as a virtual treasury plan while leaving child creation blocked.",
        ],
        "runtime_boundary": "No runtime orchestrator, paper executor, order router, Kraken client or state database is imported.",
    }


def _metric_text(value: Any) -> str:
    metric = _optional_metric(value)
    return "-" if metric is None else f"{metric:.2f}"
