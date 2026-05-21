"""Opportunity scoring and paper-first selection for AUTOBOT.

The scorer is deliberately exchange-agnostic: it can score paper and live
contexts, but execution gates decide whether the score is allowed to block
orders in a given mode.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Optional

from .pair_strategy_health import symbol_key
from .regime_features import RegimeFeatureEngine, RegimeFeatureResult


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.getenv(name)
    try:
        value = float(raw) if raw not in (None, "") else default
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    try:
        value = int(raw) if raw not in (None, "") else default
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _env_choice(name: str, default: str, allowed: set[str]) -> str:
    raw = os.getenv(name)
    value = str(raw if raw not in (None, "") else default).strip().lower()
    return value if value in allowed else default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, float(value)))


@dataclass(frozen=True)
class OpportunityConfig:
    enabled: bool = True
    selection_enabled: bool = True
    live_selection_enabled: bool = False
    min_score: float = 70.0
    min_gross_edge_bps: float = 35.0
    min_net_edge_bps: float = 12.0
    min_atr_bps: float = 18.0
    max_atr_bps: float = 220.0
    max_spread_bps: float = 8.0
    max_cost_bps: float = 80.0
    min_stability: float = 0.45
    max_active_symbols: int = 2
    min_order_eur: float = 5.0
    max_order_eur: float = 25.0
    max_symbol_exposure_pct: float = 20.0
    max_total_exposure_pct: float = 40.0
    paper_allow_upsize: bool = True
    paper_min_order_eur: float = 10.0
    paper_max_order_eur: float = 80.0
    paper_order_capital_pct: float = 38.0
    paper_max_symbol_exposure_pct: float = 25.0
    paper_max_total_exposure_pct: float = 80.0
    paper_allow_min_order_floor: bool = True
    paper_dynamic_allocation_enabled: bool = True
    paper_min_order_capital_pct: float = 12.0
    paper_edge_boost_bps: float = 140.0
    atr_mode: str = "strict"
    high_net_edge_bps: float = 80.0
    paper_relaxed_min_atr_bps: float = 5.0
    pair_health_guard_enabled: bool = True
    pair_health_guard_action: str = "observe"
    pair_health_guard_min_closed_trades: int = 20
    pair_health_guard_early_min_closed_trades: int = 8
    pair_health_guard_score_max: float = 35.0
    pair_health_guard_pf_max: float = 0.80

    @classmethod
    def from_env(cls) -> "OpportunityConfig":
        return cls(
            enabled=_env_bool("OPPORTUNITY_SCORING_ENABLED", True),
            selection_enabled=_env_bool("OPPORTUNITY_SELECTION_ENABLED", True),
            live_selection_enabled=_env_bool("OPPORTUNITY_SELECTION_LIVE_ENABLED", False),
            min_score=_env_float("OPPORTUNITY_MIN_SCORE", 70.0, 0.0, 100.0),
            min_gross_edge_bps=_env_float("OPPORTUNITY_MIN_GROSS_EDGE_BPS", 35.0, 0.0, 1000.0),
            min_net_edge_bps=_env_float("OPPORTUNITY_MIN_NET_EDGE_BPS", 12.0, -500.0, 1000.0),
            min_atr_bps=_env_float("OPPORTUNITY_MIN_ATR_BPS", 18.0, 0.0, 1000.0),
            max_atr_bps=_env_float("OPPORTUNITY_MAX_ATR_BPS", 220.0, 1.0, 5000.0),
            max_spread_bps=_env_float("OPPORTUNITY_MAX_SPREAD_BPS", 8.0, 0.1, 1000.0),
            max_cost_bps=_env_float("OPPORTUNITY_MAX_COST_BPS", 80.0, 1.0, 2000.0),
            min_stability=_env_float("OPPORTUNITY_MIN_STABILITY", 0.45, 0.0, 1.0),
            max_active_symbols=_env_int("OPPORTUNITY_MAX_ACTIVE_SYMBOLS", 2, 1, 100),
            min_order_eur=_env_float("OPPORTUNITY_MIN_ORDER_EUR", 5.0, 0.0, 10_000.0),
            max_order_eur=_env_float("OPPORTUNITY_MAX_ORDER_EUR", 25.0, 0.0, 1_000_000.0),
            max_symbol_exposure_pct=_env_float("OPPORTUNITY_MAX_SYMBOL_EXPOSURE_PCT", 20.0, 0.1, 100.0),
            max_total_exposure_pct=_env_float("OPPORTUNITY_MAX_TOTAL_EXPOSURE_PCT", 40.0, 0.1, 100.0),
            paper_allow_upsize=_env_bool("OPPORTUNITY_PAPER_ALLOW_UPSIZE", True),
            paper_min_order_eur=_env_float("OPPORTUNITY_PAPER_MIN_ORDER_EUR", 10.0, 0.0, 10_000.0),
            paper_max_order_eur=_env_float("OPPORTUNITY_PAPER_MAX_ORDER_EUR", 80.0, 0.0, 1_000_000.0),
            paper_order_capital_pct=_env_float("OPPORTUNITY_PAPER_ORDER_CAPITAL_PCT", 38.0, 0.1, 100.0),
            paper_max_symbol_exposure_pct=_env_float("OPPORTUNITY_PAPER_MAX_SYMBOL_EXPOSURE_PCT", 25.0, 0.1, 100.0),
            paper_max_total_exposure_pct=_env_float("OPPORTUNITY_PAPER_MAX_TOTAL_EXPOSURE_PCT", 80.0, 0.1, 100.0),
            paper_allow_min_order_floor=_env_bool("OPPORTUNITY_PAPER_ALLOW_MIN_ORDER_FLOOR", True),
            paper_dynamic_allocation_enabled=_env_bool("OPPORTUNITY_PAPER_DYNAMIC_ALLOCATION_ENABLED", True),
            paper_min_order_capital_pct=_env_float("OPPORTUNITY_PAPER_MIN_ORDER_CAPITAL_PCT", 12.0, 0.1, 100.0),
            paper_edge_boost_bps=_env_float("OPPORTUNITY_PAPER_EDGE_BOOST_BPS", 140.0, 1.0, 5000.0),
            atr_mode=_env_choice("OPPORTUNITY_ATR_MODE", "strict", {"strict", "adaptive", "opportunistic"}),
            high_net_edge_bps=_env_float("OPPORTUNITY_HIGH_NET_EDGE_BPS", 80.0, 0.0, 5000.0),
            paper_relaxed_min_atr_bps=_env_float("OPPORTUNITY_PAPER_RELAXED_MIN_ATR_BPS", 5.0, 0.0, 1000.0),
            pair_health_guard_enabled=_env_bool("OPPORTUNITY_PAIR_HEALTH_GUARD_ENABLED", True),
            pair_health_guard_action=_env_choice("OPPORTUNITY_PAIR_HEALTH_GUARD_ACTION", "observe", {"observe", "block"}),
            pair_health_guard_min_closed_trades=_env_int("OPPORTUNITY_PAIR_HEALTH_GUARD_MIN_CLOSED_TRADES", 20, 1, 10_000),
            pair_health_guard_early_min_closed_trades=_env_int("OPPORTUNITY_PAIR_HEALTH_GUARD_EARLY_MIN_CLOSED_TRADES", 8, 1, 10_000),
            pair_health_guard_score_max=_env_float("OPPORTUNITY_PAIR_HEALTH_GUARD_SCORE_MAX", 35.0, 0.0, 100.0),
            pair_health_guard_pf_max=_env_float("OPPORTUNITY_PAIR_HEALTH_GUARD_PF_MAX", 0.80, 0.0, 10.0),
        )


@dataclass
class OpportunityResult:
    symbol: str
    score: float
    status: str
    reason: str
    base_score: float = 0.0
    gross_edge_bps: float = 0.0
    cost_bps: float = 0.0
    net_edge_bps: float = 0.0
    min_edge_bps: float = 0.0
    atr_bps: float = 0.0
    spread_bps: float = 0.0
    volume_liquidity_score: float = 0.0
    signal_stability: float = 0.0
    allocation_eur: float = 0.0
    recommended_order_eur: float = 0.0
    allocation_capital_pct: float = 0.0
    allocation_reason: str = "ok"
    components: dict[str, float] = field(default_factory=dict)
    blockers: list[str] = field(default_factory=list)
    regime_score: float = 50.0
    regime_adjustment: float = 0.0
    regime_context: dict[str, Any] = field(default_factory=dict)
    health_score: float = 50.0
    health_adjustment: float = 0.0
    health_context: dict[str, Any] = field(default_factory=dict)
    source: str = "runtime"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "score": round(self.score, 2),
            "status": self.status,
            "reason": self.reason,
            "base_score": round(self.base_score, 2),
            "gross_edge_bps": round(self.gross_edge_bps, 3),
            "cost_bps": round(self.cost_bps, 3),
            "net_edge_bps": round(self.net_edge_bps, 3),
            "min_edge_bps": round(self.min_edge_bps, 3),
            "atr_bps": round(self.atr_bps, 3),
            "spread_bps": round(self.spread_bps, 3),
            "volume_liquidity_score": round(self.volume_liquidity_score, 3),
            "signal_stability": round(self.signal_stability, 3),
            "allocation_eur": round(self.allocation_eur, 2),
            "recommended_order_eur": round(self.recommended_order_eur, 2),
            "allocation_capital_pct": round(self.allocation_capital_pct, 3),
            "allocation_reason": self.allocation_reason,
            "components": {k: round(v, 3) for k, v in self.components.items()},
            "blockers": list(self.blockers),
            "regime_score": round(self.regime_score, 2),
            "regime_adjustment": round(self.regime_adjustment, 3),
            "regime_context": dict(self.regime_context),
            "health_score": round(self.health_score, 2),
            "health_adjustment": round(self.health_adjustment, 3),
            "health_context": dict(self.health_context),
            "source": self.source,
            "timestamp": self.timestamp,
        }


class OpportunityScorer:
    """Score trade opportunities from edge, cost, volatility and runtime data."""

    def __init__(
        self,
        config: Optional[OpportunityConfig] = None,
        regime_engine: Optional[RegimeFeatureEngine] = None,
    ) -> None:
        self.config = config or OpportunityConfig.from_env()
        self.regime_engine = regime_engine or RegimeFeatureEngine()

    def execution_gate(self, *, paper_mode: bool) -> dict[str, Any]:
        live_ack = _env_bool("LIVE_TRADING_CONFIRMATION", False)
        if paper_mode:
            applies = self.config.enabled and self.config.selection_enabled
            blockers: list[str] = []
        else:
            applies = (
                self.config.enabled
                and self.config.selection_enabled
                and self.config.live_selection_enabled
                and live_ack
            )
            blockers = []
            if not self.config.live_selection_enabled:
                blockers.append("opportunity_selection_live_disabled")
            if not live_ack:
                blockers.append("live_trading_confirmation_missing")
        return {
            "enabled": self.config.enabled,
            "selection_enabled": self.config.selection_enabled,
            "selection_applies_to_execution": applies,
            "mode": "paper" if paper_mode else "live",
            "blockers": blockers,
        }

    def score_signal(
        self,
        *,
        symbol: str,
        edge_context: Mapping[str, Any],
        atr_pct: float,
        available_capital: float,
        open_positions: int = 0,
        recent_events: Optional[Iterable[Mapping[str, Any]]] = None,
        market_metrics: Optional[Any] = None,
        total_capital: Optional[float] = None,
        paper_mode: bool = False,
        price_history: Optional[Iterable[Any]] = None,
        performance_context: Optional[Mapping[str, Any]] = None,
    ) -> OpportunityResult:
        gross_edge = _safe_float(edge_context.get("expected_move_bps"))
        cost_bps = _safe_float(edge_context.get("total_cost_bps"))
        net_edge = _safe_float(edge_context.get("net_edge_bps"))
        min_edge = _safe_float(edge_context.get("adaptive_min_edge_bps"))
        spread_bps = _safe_float(edge_context.get("spread_bps"))
        atr_bps = max(0.0, _safe_float(atr_pct) * 10000.0)
        liquidity = self._liquidity_score(market_metrics)
        stability = self._signal_stability(symbol, recent_events)
        base_score, components = self._score(
            gross_edge_bps=gross_edge,
            cost_bps=cost_bps,
            net_edge_bps=net_edge,
            atr_bps=atr_bps,
            spread_bps=spread_bps,
            liquidity_score=liquidity,
            stability=stability,
        )
        regime = self._regime_for(symbol, price_history)
        health = self._health_for(symbol, performance_context)
        score = self._score_with_adjustments(base_score, regime.adjustment, health["adjustment"])
        blockers = self._blockers(
            score=score,
            gross_edge_bps=gross_edge,
            net_edge_bps=net_edge,
            atr_bps=atr_bps,
            spread_bps=spread_bps,
            stability=stability,
            open_positions=open_positions,
            paper_mode=paper_mode,
            health=health,
        )
        status = "tradable" if not blockers else "non_tradable"
        reason = "score_ok" if not blockers else blockers[0]
        allocation = self._allocation(
            score=score,
            available_capital=available_capital,
            total_capital=total_capital,
            paper_mode=paper_mode,
            net_edge_bps=net_edge,
            min_edge_bps=min_edge,
        )
        return OpportunityResult(
            symbol=symbol,
            score=score,
            status=status,
            reason=reason,
            base_score=base_score,
            gross_edge_bps=gross_edge,
            cost_bps=cost_bps,
            net_edge_bps=net_edge,
            min_edge_bps=min_edge,
            atr_bps=atr_bps,
            spread_bps=spread_bps,
            volume_liquidity_score=liquidity,
            signal_stability=stability,
            allocation_eur=allocation["symbol_cap_eur"],
            recommended_order_eur=allocation["order_eur"],
            allocation_capital_pct=allocation["capital_pct"],
            allocation_reason=allocation["reason"],
            components=components,
            blockers=blockers,
            regime_score=regime.regime_score,
            regime_adjustment=regime.adjustment,
            regime_context=self._regime_context(regime),
            health_score=health["health_score"],
            health_adjustment=health["adjustment"],
            health_context=health["context"],
        )

    def build_snapshot(
        self,
        *,
        instances: Iterable[Mapping[str, Any]],
        paper_mode: bool,
        total_capital: float = 0.0,
        health_by_symbol: Optional[Mapping[str, Mapping[str, Any]]] = None,
    ) -> dict[str, Any]:
        opportunities: list[OpportunityResult] = []
        for inst in instances:
            opportunities.append(
                self.score_instance(
                    inst,
                    total_capital=total_capital,
                    paper_mode=paper_mode,
                    health_by_symbol=health_by_symbol,
                )
            )

        ranked = sorted(opportunities, key=lambda item: item.score, reverse=True)
        tradable = [item for item in ranked if item.status == "tradable"]
        selected_symbols = [item.symbol for item in tradable[: self.config.max_active_symbols]]
        for item in ranked:
            if item.status == "tradable" and item.symbol not in selected_symbols:
                item.status = "non_tradable"
                item.reason = "below_top_opportunity_cutoff"
                item.blockers.append("below_top_opportunity_cutoff")

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": "paper" if paper_mode else "live",
            "paper_mode": paper_mode,
            "config": {
                "enabled": self.config.enabled,
                "selection_enabled": self.config.selection_enabled,
                "live_selection_enabled": self.config.live_selection_enabled,
                "min_score": self.config.min_score,
                "min_gross_edge_bps": self.config.min_gross_edge_bps,
                "min_net_edge_bps": self.config.min_net_edge_bps,
                "min_atr_bps": self.config.min_atr_bps,
                "max_spread_bps": self.config.max_spread_bps,
                "max_active_symbols": self.config.max_active_symbols,
                "min_order_eur": self.config.min_order_eur,
                "max_order_eur": self.config.max_order_eur,
                "max_symbol_exposure_pct": self.config.max_symbol_exposure_pct,
                "max_total_exposure_pct": self.config.max_total_exposure_pct,
                "paper_allow_upsize": self.config.paper_allow_upsize,
                "paper_min_order_eur": self.config.paper_min_order_eur,
                "paper_max_order_eur": self.config.paper_max_order_eur,
                "paper_order_capital_pct": self.config.paper_order_capital_pct,
                "paper_max_symbol_exposure_pct": self.config.paper_max_symbol_exposure_pct,
                "paper_max_total_exposure_pct": self.config.paper_max_total_exposure_pct,
                "paper_allow_min_order_floor": self.config.paper_allow_min_order_floor,
                "paper_dynamic_allocation_enabled": self.config.paper_dynamic_allocation_enabled,
                "paper_min_order_capital_pct": self.config.paper_min_order_capital_pct,
                "paper_edge_boost_bps": self.config.paper_edge_boost_bps,
                "atr_mode": self.config.atr_mode,
                "high_net_edge_bps": self.config.high_net_edge_bps,
                "paper_relaxed_min_atr_bps": self.config.paper_relaxed_min_atr_bps,
                "pair_health_guard_enabled": self.config.pair_health_guard_enabled,
                "pair_health_guard_action": self.config.pair_health_guard_action,
                "pair_health_guard_min_closed_trades": self.config.pair_health_guard_min_closed_trades,
                "pair_health_guard_early_min_closed_trades": self.config.pair_health_guard_early_min_closed_trades,
                "regime_scoring_enabled": self.regime_engine.config.enabled,
                "regime_score_weight": self.regime_engine.config.score_weight,
                "pair_health_scoring": bool(health_by_symbol is not None),
            },
            "execution_gate": self.execution_gate(paper_mode=paper_mode),
            "selected_symbols": selected_symbols,
            "opportunities": [item.to_dict() for item in ranked],
        }

    def score_instance(
        self,
        instance: Mapping[str, Any],
        *,
        total_capital: float = 0.0,
        paper_mode: bool = False,
        health_by_symbol: Optional[Mapping[str, Mapping[str, Any]]] = None,
    ) -> OpportunityResult:
        symbol = str(instance.get("symbol") or instance.get("pair") or "UNKNOWN")
        warmup = instance.get("warmup") if isinstance(instance.get("warmup"), dict) else {}
        last_decision = instance.get("last_decision") if isinstance(instance.get("last_decision"), dict) else {}
        last_signal = instance.get("last_signal") if isinstance(instance.get("last_signal"), dict) else {}
        edge = last_decision.get("edge_context") if isinstance(last_decision.get("edge_context"), dict) else {}
        gross_edge = _safe_float(last_decision.get("gross_edge_bps", edge.get("expected_move_bps")))
        cost_bps = _safe_float(last_decision.get("cost_bps", edge.get("total_cost_bps")))
        net_edge = _safe_float(last_decision.get("net_edge_bps", edge.get("net_edge_bps")))
        min_edge = _safe_float(last_decision.get("min_edge_bps", edge.get("adaptive_min_edge_bps")))
        spread_bps = _safe_float(edge.get("spread_bps"))
        atr_bps = _safe_float(last_decision.get("atr_pct")) * 10000.0

        runtime_events = instance.get("runtime_events") or []
        liquidity = 0.0
        stability = self._signal_stability(symbol, runtime_events)
        market_metrics = self._try_market_metrics(symbol)
        if market_metrics is not None:
            liquidity = self._liquidity_score(market_metrics)
            if spread_bps <= 0.0:
                spread_bps = max(0.0, _safe_float(getattr(market_metrics, "spread_avg", 0.0)) * 100.0)
            if atr_bps <= 0.0:
                atr_bps = max(0.0, _safe_float(getattr(market_metrics, "volatility_24h", 0.0)) * 100.0)

        base_score, components = self._score(
            gross_edge_bps=gross_edge,
            cost_bps=cost_bps,
            net_edge_bps=net_edge,
            atr_bps=atr_bps,
            spread_bps=spread_bps,
            liquidity_score=liquidity,
            stability=stability,
        )
        regime = self._regime_for(
            symbol,
            instance.get("price_history_tail") or instance.get("price_history") or [],
        )
        performance_context = None
        if health_by_symbol is not None:
            performance_context = health_by_symbol.get(symbol_key(symbol))
        if performance_context is None and isinstance(instance.get("pair_health"), Mapping):
            performance_context = instance.get("pair_health")
        health = self._health_for(symbol, performance_context)
        score = self._score_with_adjustments(base_score, regime.adjustment, health["adjustment"])
        blockers = list(instance.get("blocked_reasons") or [])
        if warmup.get("active"):
            blockers.append("warmup")
        if not last_signal:
            blockers.append("no_recent_signal")
        blockers.extend(self._blockers(
            score=score,
            gross_edge_bps=gross_edge,
            net_edge_bps=net_edge,
            atr_bps=atr_bps,
            spread_bps=spread_bps,
            stability=stability,
            open_positions=int(_safe_float(instance.get("open_positions"), 0.0)),
            paper_mode=paper_mode,
            health=health,
        ))
        blockers = list(dict.fromkeys(blockers))
        status = "tradable" if not blockers else "non_tradable"
        reason = "score_ok" if not blockers else blockers[0]
        allocation = self._allocation(
            score=score,
            available_capital=_safe_float(instance.get("capital"), 0.0),
            total_capital=total_capital,
            paper_mode=paper_mode,
            net_edge_bps=net_edge,
            min_edge_bps=min_edge,
        )
        return OpportunityResult(
            symbol=symbol,
            score=score,
            status=status,
            reason=reason,
            base_score=base_score,
            gross_edge_bps=gross_edge,
            cost_bps=cost_bps,
            net_edge_bps=net_edge,
            min_edge_bps=min_edge,
            atr_bps=atr_bps,
            spread_bps=spread_bps,
            volume_liquidity_score=liquidity,
            signal_stability=stability,
            allocation_eur=allocation["symbol_cap_eur"],
            recommended_order_eur=allocation["order_eur"],
            allocation_capital_pct=allocation["capital_pct"],
            allocation_reason=allocation["reason"],
            components=components,
            blockers=blockers,
            regime_score=regime.regime_score,
            regime_adjustment=regime.adjustment,
            regime_context=self._regime_context(regime),
            health_score=health["health_score"],
            health_adjustment=health["adjustment"],
            health_context=health["context"],
            source="runtime_instance_snapshot",
        )

    def _regime_for(self, symbol: str, price_history: Optional[Iterable[Any]]) -> RegimeFeatureResult:
        try:
            return self.regime_engine.analyze_symbol(symbol, price_history)
        except Exception:
            return self.regime_engine.neutral_result(symbol, 0, "regime_unavailable")

    @staticmethod
    def _score_with_adjustments(base_score: float, regime_adjustment: float, health_adjustment: float) -> float:
        return max(0.0, min(100.0, base_score + regime_adjustment + health_adjustment))

    @staticmethod
    def _regime_context(regime: RegimeFeatureResult) -> dict[str, Any]:
        return {
            "regime": regime.regime,
            "confidence": round(regime.confidence, 4),
            "entropy_norm": round(regime.entropy_norm, 4),
            "markov_state": regime.markov_state,
            "persistence_probability": round(regime.persistence_probability, 4),
            "sample_count": regime.sample_count,
            "reason": regime.reason,
            "enabled": regime.enabled,
        }

    def _health_for(self, symbol: str, context: Optional[Mapping[str, Any]]) -> dict[str, Any]:
        if not context:
            return {
                "health_score": 50.0,
                "adjustment": 0.0,
                "context": {
                    "symbol": symbol_key(symbol),
                    "status": "unknown",
                    "reason": "no_health_context",
                    "closed_trades": 0,
                    "enabled": False,
                    "guard_action": self.config.pair_health_guard_action,
                },
            }
        health_score = _safe_float(context.get("health_score"), 50.0)
        adjustment = _safe_float(context.get("adjustment"), 0.0)
        return {
            "health_score": health_score,
            "adjustment": adjustment,
            "context": {
                "symbol": symbol_key(context.get("symbol", symbol)),
                "status": context.get("status", "unknown"),
                "reason": context.get("reason", "unknown"),
                "closed_trades": int(_safe_float(context.get("closed_trades"), 0.0)),
                "net_pnl_eur": _safe_float(context.get("net_pnl_eur"), 0.0),
                "profit_factor": context.get("profit_factor"),
                "win_rate": _safe_float(context.get("win_rate"), 0.0),
                "avg_return_bps": _safe_float(context.get("avg_return_bps"), 0.0),
                "max_drawdown_eur": _safe_float(context.get("max_drawdown_eur"), 0.0),
                "enabled": bool(context.get("enabled", True)),
                "guard_action": self.config.pair_health_guard_action,
            },
        }

    def _score(
        self,
        *,
        gross_edge_bps: float,
        cost_bps: float,
        net_edge_bps: float,
        atr_bps: float,
        spread_bps: float,
        liquidity_score: float,
        stability: float,
    ) -> tuple[float, dict[str, float]]:
        cfg = self.config
        gross_n = _clamp(gross_edge_bps / max(cfg.min_gross_edge_bps * 2.0, 1.0))
        net_n = _clamp((net_edge_bps - cfg.min_net_edge_bps) / max(cfg.min_gross_edge_bps, 1.0))
        cost_n = _clamp(1.0 - cost_bps / max(cfg.max_cost_bps, 1.0))
        if atr_bps <= 0.0:
            atr_n = 0.0
        elif atr_bps < cfg.min_atr_bps:
            atr_n = _clamp(atr_bps / max(cfg.min_atr_bps, 1.0))
        elif atr_bps <= cfg.max_atr_bps:
            atr_n = 1.0
        else:
            atr_n = _clamp(1.0 - ((atr_bps - cfg.max_atr_bps) / max(cfg.max_atr_bps, 1.0)))
        spread_n = _clamp(1.0 - spread_bps / max(cfg.max_spread_bps, 0.1))
        liq_n = _clamp(liquidity_score)
        stable_n = _clamp(stability)
        components = {
            "gross_edge": gross_n * 20.0,
            "net_edge": net_n * 30.0,
            "cost": cost_n * 15.0,
            "volatility": atr_n * 15.0,
            "spread": spread_n * 10.0,
            "liquidity": liq_n * 5.0,
            "stability": stable_n * 5.0,
        }
        return max(0.0, min(100.0, sum(components.values()))), components

    def _blockers(
        self,
        *,
        score: float,
        gross_edge_bps: float,
        net_edge_bps: float,
        atr_bps: float,
        spread_bps: float,
        stability: float,
        open_positions: int,
        paper_mode: bool = False,
        health: Optional[Mapping[str, Any]] = None,
    ) -> list[str]:
        cfg = self.config
        blockers: list[str] = []
        if gross_edge_bps < cfg.min_gross_edge_bps:
            blockers.append("gross_edge_below_target")
        if net_edge_bps < cfg.min_net_edge_bps:
            blockers.append("net_edge_below_target")
        if atr_bps < cfg.min_atr_bps and not self._paper_atr_override_allowed(
            paper_mode=paper_mode,
            gross_edge_bps=gross_edge_bps,
            net_edge_bps=net_edge_bps,
            atr_bps=atr_bps,
        ):
            blockers.append("atr_below_minimum")
        if atr_bps > cfg.max_atr_bps:
            blockers.append("atr_above_maximum")
        if spread_bps > cfg.max_spread_bps:
            blockers.append("spread_too_wide")
        if stability < cfg.min_stability:
            blockers.append("signal_not_stable")
        if score < cfg.min_score:
            blockers.append("score_below_threshold")
        blockers.extend(self._health_blockers(health, paper_mode=paper_mode))
        if open_positions < 0:
            blockers.append("invalid_position_count")
        return blockers

    def _health_blockers(
        self,
        health: Optional[Mapping[str, Any]],
        *,
        paper_mode: bool,
    ) -> list[str]:
        cfg = self.config
        if not paper_mode or not cfg.pair_health_guard_enabled or not health:
            return []
        if cfg.pair_health_guard_action != "block":
            return []
        context = health.get("context") if isinstance(health.get("context"), Mapping) else {}
        status = str(context.get("status") or "").lower()
        closed = int(_safe_float(context.get("closed_trades"), 0.0))
        net_pnl = _safe_float(context.get("net_pnl_eur"), 0.0)
        health_score = _safe_float(health.get("health_score"), _safe_float(context.get("health_score"), 50.0))
        pf_raw = context.get("profit_factor")
        profit_factor = _safe_float(pf_raw, 0.0 if pf_raw is None else 1.0)

        if status == "weak" and closed >= cfg.pair_health_guard_min_closed_trades:
            return ["pair_health_weak"]
        if status == "underperforming" and closed >= cfg.pair_health_guard_min_closed_trades:
            return ["pair_health_underperforming"]
        if status == "early_weak" and closed >= cfg.pair_health_guard_early_min_closed_trades:
            return ["pair_health_early_weak"]
        if (
            status == "learning"
            and closed >= cfg.pair_health_guard_early_min_closed_trades
            and net_pnl < 0.0
            and health_score <= cfg.pair_health_guard_score_max
            and profit_factor <= cfg.pair_health_guard_pf_max
        ):
            return ["pair_health_early_weak"]
        return []

    def _paper_atr_override_allowed(
        self,
        *,
        paper_mode: bool,
        gross_edge_bps: float,
        net_edge_bps: float,
        atr_bps: float,
    ) -> bool:
        cfg = self.config
        if not paper_mode:
            return False
        if cfg.atr_mode not in {"adaptive", "opportunistic"}:
            return False
        if net_edge_bps < cfg.high_net_edge_bps:
            return False
        if gross_edge_bps < cfg.min_gross_edge_bps:
            return False
        if atr_bps < cfg.paper_relaxed_min_atr_bps:
            return False
        return True

    def _allocation(
        self,
        *,
        score: float,
        available_capital: float,
        total_capital: Optional[float],
        paper_mode: bool = False,
        net_edge_bps: float = 0.0,
        min_edge_bps: float = 0.0,
    ) -> dict[str, float]:
        cfg = self.config
        available = max(0.0, float(available_capital))
        total = max(available, float(total_capital or 0.0))
        symbol_pct = cfg.paper_max_symbol_exposure_pct if paper_mode else cfg.max_symbol_exposure_pct
        total_pct = cfg.paper_max_total_exposure_pct if paper_mode else cfg.max_total_exposure_pct
        min_order = cfg.paper_min_order_eur if paper_mode else cfg.min_order_eur
        max_order = cfg.paper_max_order_eur if paper_mode else cfg.max_order_eur
        order_capital_pct = self._order_capital_pct(
            score=score,
            paper_mode=paper_mode,
            net_edge_bps=net_edge_bps,
            min_edge_bps=min_edge_bps,
        )
        symbol_cap = total * symbol_pct / 100.0 if total > 0.0 else available
        total_cap = total * total_pct / 100.0 if total > 0.0 else available
        raw_order = available * (order_capital_pct / 100.0)
        order = min(raw_order, max_order, symbol_cap, total_cap, available)
        reason = "ok"
        if order < min_order:
            can_floor_paper_order = (
                paper_mode
                and cfg.paper_allow_min_order_floor
                and score >= cfg.min_score
                and min_order > 0.0
                and available >= min_order
                and min_order <= max_order
                and min_order <= symbol_cap
                and min_order <= total_cap
            )
            if can_floor_paper_order:
                order = min_order
                reason = "paper_min_order_floor"
            else:
                reason = (
                    "available_below_min_order"
                    if available < min_order
                    else "exposure_cap_below_min_order"
                    if min(symbol_cap, total_cap, max_order) < min_order
                    else "raw_order_below_min_order"
                )
                order = 0.0
        return {
            "symbol_cap_eur": max(0.0, min(symbol_cap, total_cap)),
            "order_eur": max(0.0, order),
            "capital_pct": max(0.0, order_capital_pct),
            "reason": reason,
        }

    def _order_capital_pct(
        self,
        *,
        score: float,
        paper_mode: bool,
        net_edge_bps: float,
        min_edge_bps: float,
    ) -> float:
        cfg = self.config
        if not paper_mode or not cfg.paper_dynamic_allocation_enabled:
            base_pct = cfg.paper_order_capital_pct if paper_mode else 15.0
            return base_pct * _clamp(score / 100.0)

        target_pct = max(cfg.paper_min_order_capital_pct, cfg.paper_order_capital_pct)
        floor_pct = min(cfg.paper_min_order_capital_pct, target_pct)
        score_floor = max(0.0, min(99.0, cfg.min_score))
        score_quality = _clamp((score - score_floor) / max(1.0, 100.0 - score_floor))
        edge_threshold = max(cfg.min_net_edge_bps, min_edge_bps)
        edge_surplus = max(0.0, float(net_edge_bps) - edge_threshold)
        edge_quality = _clamp(edge_surplus / max(1.0, cfg.paper_edge_boost_bps))
        conviction = _clamp((score_quality * 0.55) + (edge_quality * 0.45))
        return floor_pct + ((target_pct - floor_pct) * conviction)

    def _signal_stability(
        self,
        symbol: str,
        recent_events: Optional[Iterable[Mapping[str, Any]]],
    ) -> float:
        events = [
            event for event in (recent_events or [])
            if isinstance(event, Mapping)
            and str(event.get("symbol") or "").upper() == symbol.upper()
            and str(event.get("side") or event.get("signal") or "").lower() in {"buy", "sell"}
        ][-12:]
        if not events:
            return 0.5
        last_side = str(events[-1].get("side") or events[-1].get("signal") or "").lower()
        same_side = sum(1 for event in events if str(event.get("side") or event.get("signal") or "").lower() == last_side)
        rejection_penalty = sum(1 for event in events if str(event.get("event") or "").endswith("rejected"))
        stability = 0.35 + 0.55 * (same_side / max(len(events), 1)) - 0.10 * (rejection_penalty / max(len(events), 1))
        return _clamp(stability)

    def _liquidity_score(self, market_metrics: Optional[Any]) -> float:
        if market_metrics is None:
            return 0.5
        composite = _safe_float(getattr(market_metrics, "composite_score", None), -1.0)
        if composite >= 0.0:
            return _clamp(composite / 100.0)
        volume = _safe_float(getattr(market_metrics, "volume_24h", 0.0))
        return _clamp(volume / 250.0)

    def _try_market_metrics(self, symbol: str) -> Optional[Any]:
        try:
            from .market_analyzer import get_market_analyzer

            analyzer = get_market_analyzer()
            raw = str(symbol or "").upper()
            aliases = {
                "BTCEUR": ("BTCEUR", "BTC/EUR", "XBT/EUR", "XXBTZEUR"),
                "XBT/EUR": ("XBT/EUR", "BTC/EUR", "BTCEUR", "XXBTZEUR"),
                "XXBTZEUR": ("XXBTZEUR", "XBT/EUR", "BTC/EUR", "BTCEUR"),
                "ETHEUR": ("ETHEUR", "ETH/EUR", "XETHZEUR"),
                "XETHZEUR": ("XETHZEUR", "ETH/EUR", "ETHEUR"),
                "SOLEUR": ("SOLEUR", "SOL/EUR"),
                "ADAEUR": ("ADAEUR", "ADA/EUR"),
                "XXRPZEUR": ("XXRPZEUR", "XRP/EUR"),
                "XRPEUR": ("XRPEUR", "XRP/EUR", "XXRPZEUR"),
                "LINKEUR": ("LINKEUR", "LINK/EUR"),
                "DOTEUR": ("DOTEUR", "DOT/EUR"),
                "AVAXEUR": ("AVAXEUR", "AVAX/EUR"),
                "UNIEUR": ("UNIEUR", "UNI/EUR"),
                "POLEUR": ("POLEUR", "POL/EUR"),
            }
            candidates = aliases.get(raw, (raw, raw.replace("/", "")))
            for candidate in candidates:
                metrics = analyzer.analyze_market(candidate)
                if metrics is not None:
                    return metrics
        except Exception:
            return None
        return None
