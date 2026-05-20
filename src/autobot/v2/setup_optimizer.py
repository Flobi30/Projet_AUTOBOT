"""Paper-only adaptive setup optimizer.

This module compares candidate Grid setups per symbol and market regime.  It
does not place orders, does not promote live trading, and does not mutate the
running strategy.  Its purpose is to turn realized paper evidence plus current
opportunity/regime context into a clear list of variants worth testing in
paper/shadow mode.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Optional

from .pair_strategy_health import symbol_key
from .strategies.adaptive_grid_config import PairProfile, get_default_registry


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
        value = int(float(raw)) if raw not in (None, "") else default
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return max(minimum, min(maximum, float(value)))


@dataclass(frozen=True)
class SetupOptimizerConfig:
    enabled: bool = True
    live_enabled: bool = False
    apply_to_execution: bool = True
    min_closed_trades: int = 30
    candidate_profit_factor: float = 1.25
    strong_profit_factor: float = 1.60
    min_net_pnl_eur: float = 0.0
    max_variants_per_symbol: int = 5
    weak_setup_score: float = 45.0
    candidate_score: float = 70.0
    max_range_multiplier: float = 2.20
    min_range_multiplier: float = 0.55

    @classmethod
    def from_env(cls) -> "SetupOptimizerConfig":
        return cls(
            enabled=_env_bool("SETUP_OPTIMIZER_ENABLED", True),
            live_enabled=_env_bool("SETUP_OPTIMIZER_LIVE_ENABLED", False),
            apply_to_execution=_env_bool("SETUP_OPTIMIZER_APPLY_TO_EXECUTION", True),
            min_closed_trades=_env_int("SETUP_OPTIMIZER_MIN_CLOSED_TRADES", 30, 1, 100_000),
            candidate_profit_factor=_env_float("SETUP_OPTIMIZER_CANDIDATE_PF", 1.25, 0.01, 100.0),
            strong_profit_factor=_env_float("SETUP_OPTIMIZER_STRONG_PF", 1.60, 0.01, 100.0),
            min_net_pnl_eur=_env_float("SETUP_OPTIMIZER_MIN_NET_PNL_EUR", 0.0, -1_000_000.0, 1_000_000.0),
            max_variants_per_symbol=_env_int("SETUP_OPTIMIZER_MAX_VARIANTS_PER_SYMBOL", 5, 1, 20),
            weak_setup_score=_env_float("SETUP_OPTIMIZER_WEAK_SCORE", 45.0, 0.0, 100.0),
            candidate_score=_env_float("SETUP_OPTIMIZER_CANDIDATE_SCORE", 70.0, 0.0, 100.0),
            max_range_multiplier=_env_float("SETUP_OPTIMIZER_MAX_RANGE_MULT", 2.20, 0.1, 10.0),
            min_range_multiplier=_env_float("SETUP_OPTIMIZER_MIN_RANGE_MULT", 0.55, 0.1, 10.0),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "live_enabled": self.live_enabled,
            "apply_to_execution": self.apply_to_execution,
            "min_closed_trades": self.min_closed_trades,
            "candidate_profit_factor": self.candidate_profit_factor,
            "strong_profit_factor": self.strong_profit_factor,
            "min_net_pnl_eur": self.min_net_pnl_eur,
            "max_variants_per_symbol": self.max_variants_per_symbol,
            "weak_setup_score": self.weak_setup_score,
            "candidate_score": self.candidate_score,
            "max_range_multiplier": self.max_range_multiplier,
            "min_range_multiplier": self.min_range_multiplier,
        }


@dataclass(frozen=True)
class SetupVariant:
    name: str
    description: str
    range_multiplier: float
    level_delta: int
    capital_multiplier: float
    entry_touch_bps: float
    max_positions_delta: int = 0


DEFAULT_VARIANTS: tuple[SetupVariant, ...] = (
    SetupVariant(
        name="grid_balanced",
        description="Current-style adaptive grid; default comparison point.",
        range_multiplier=1.0,
        level_delta=0,
        capital_multiplier=1.0,
        entry_touch_bps=15.0,
    ),
    SetupVariant(
        name="grid_wide",
        description="Wider grid for stronger moves; trades less often but seeks better gross edge.",
        range_multiplier=1.45,
        level_delta=-2,
        capital_multiplier=0.85,
        entry_touch_bps=12.0,
        max_positions_delta=-1,
    ),
    SetupVariant(
        name="grid_tight_range",
        description="Tighter range grid for stable ranging markets; lower allocation until proven.",
        range_multiplier=0.75,
        level_delta=4,
        capital_multiplier=0.65,
        entry_touch_bps=8.0,
    ),
    SetupVariant(
        name="grid_volatility",
        description="High-volatility grid with wider range and smaller capital per level.",
        range_multiplier=1.90,
        level_delta=2,
        capital_multiplier=0.55,
        entry_touch_bps=10.0,
        max_positions_delta=-2,
    ),
    SetupVariant(
        name="grid_defensive_observe",
        description="Paper observation mode for weak or chaotic setups; keeps learning without scaling.",
        range_multiplier=1.20,
        level_delta=-4,
        capital_multiplier=0.35,
        entry_touch_bps=6.0,
        max_positions_delta=-4,
    ),
)


@dataclass
class VariantScore:
    name: str
    score: float
    status: str
    reason: str
    description: str
    grid_config: dict[str, Any]
    estimated_grid_gross_edge_bps: float
    estimated_net_after_cost_bps: Optional[float]
    components: dict[str, float] = field(default_factory=dict)
    shadow_metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "score": round(self.score, 2),
            "status": self.status,
            "reason": self.reason,
            "description": self.description,
            "grid_config": dict(self.grid_config),
            "estimated_grid_gross_edge_bps": round(self.estimated_grid_gross_edge_bps, 3),
            "estimated_net_after_cost_bps": (
                round(self.estimated_net_after_cost_bps, 3)
                if self.estimated_net_after_cost_bps is not None
                else None
            ),
            "components": {key: round(value, 3) for key, value in self.components.items()},
            "shadow_metrics": dict(self.shadow_metrics),
        }


@dataclass
class SymbolSetupPlan:
    symbol: str
    strategy: str
    status: str
    recommended_action: str
    selected_variant: Optional[VariantScore]
    variants: list[VariantScore]
    evidence: dict[str, Any]
    current_context: dict[str, Any]
    execution_policy: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "strategy": self.strategy,
            "status": self.status,
            "recommended_action": self.recommended_action,
            "selected_variant": self.selected_variant.to_dict() if self.selected_variant else None,
            "variants": [variant.to_dict() for variant in self.variants],
            "evidence": dict(self.evidence),
            "current_context": dict(self.current_context),
            "execution_policy": dict(self.execution_policy),
        }


class PairSetupOptimizer:
    """Compare paper-only setup variants for each watched pair."""

    def __init__(
        self,
        config: SetupOptimizerConfig | None = None,
        variants: Iterable[SetupVariant] | None = None,
    ) -> None:
        self.config = config or SetupOptimizerConfig.from_env()
        self.variants = tuple(variants or DEFAULT_VARIANTS)
        self.registry = get_default_registry()

    def build_snapshot(
        self,
        *,
        instances: Iterable[Mapping[str, Any]],
        opportunities: Iterable[Mapping[str, Any]],
        health_by_symbol: Mapping[str, Mapping[str, Any]] | None = None,
        shadow_by_symbol: Mapping[str, Mapping[str, Any]] | None = None,
        paper_mode: bool,
        total_capital: float = 0.0,
    ) -> dict[str, Any]:
        instance_groups: dict[str, list[Mapping[str, Any]]] = {}
        for inst in instances or []:
            if not isinstance(inst, Mapping):
                continue
            symbol = symbol_key(inst.get("symbol") or inst.get("pair"))
            if not symbol or symbol == "UNKNOWN":
                continue
            instance_groups.setdefault(symbol, []).append(inst)

        opp_by_symbol = {
            symbol_key(opp.get("symbol") or opp.get("pair")): opp
            for opp in opportunities or []
            if isinstance(opp, Mapping)
        }
        health_by_symbol = health_by_symbol or {}
        shadow_by_symbol = shadow_by_symbol or {}

        plans = [
            self.analyze_symbol(
                symbol=symbol,
                instances=group,
                opportunity=opp_by_symbol.get(symbol, {}),
                health=health_by_symbol.get(symbol, {}),
                shadow=shadow_by_symbol.get(symbol, {}),
                paper_mode=paper_mode,
            )
            for symbol, group in sorted(instance_groups.items())
        ]
        rows = [plan.to_dict() for plan in plans]
        candidate_count = sum(1 for plan in plans if plan.status == "candidate")
        weak_count = sum(1 for plan in plans if plan.status in {"adjust", "pause_current"})
        learning_count = sum(1 for plan in plans if plan.status == "learning")
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": "paper" if paper_mode else "live",
            "paper_mode": paper_mode,
            "enabled": self.config.enabled,
            "live_promotion_allowed": False,
            "applies_to_execution": bool(self.config.apply_to_execution and paper_mode),
            "config": self.config.to_dict(),
            "summary": {
                "symbols": len(rows),
                "candidate_setups": candidate_count,
                "learning_setups": learning_count,
                "weak_or_adjust_setups": weak_count,
                "total_capital": round(float(total_capital or 0.0), 2),
            },
            "setups": sorted(
                rows,
                key=lambda row: (
                    row["status"] != "candidate",
                    -float((row.get("selected_variant") or {}).get("score") or 0.0),
                    row["symbol"],
                ),
            ),
            "message": (
                "Paper-only optimizer: compare setup variants by pair and regime. "
                "When enabled it can gate paper entries, but it never activates live trading."
            ),
        }

    def analyze_symbol(
        self,
        *,
        symbol: str,
        instances: Iterable[Mapping[str, Any]],
        opportunity: Mapping[str, Any],
        health: Mapping[str, Any],
        shadow: Mapping[str, Any] | None = None,
        paper_mode: bool,
    ) -> SymbolSetupPlan:
        symbol = symbol_key(symbol)
        group = list(instances or [])
        profile = self.registry.get(symbol)
        strategy = ",".join(sorted({str(inst.get("strategy", "grid")) for inst in group})) or "grid"
        regime_ctx = opportunity.get("regime_context") if isinstance(opportunity.get("regime_context"), Mapping) else {}
        regime = str(regime_ctx.get("regime") or "unknown").lower()
        opp_score = _safe_float(opportunity.get("score"), 50.0)
        cost_bps = _safe_float(opportunity.get("cost_bps"), 0.0)
        cost_for_estimate = cost_bps if cost_bps > 0.0 else None
        closed = _safe_int(health.get("closed_trades"), 0)
        pf = health.get("profit_factor")
        pf_value = _safe_float(pf, 0.0) if pf is not None else None
        net_pnl = _safe_float(health.get("net_pnl_eur"), 0.0)
        health_status = str(health.get("status") or "unknown").lower()
        shadow = shadow if isinstance(shadow, Mapping) else {}
        shadow_variants = {
            str(item.get("variant") or item.get("name") or ""): item
            for item in shadow.get("variants", [])
            if isinstance(item, Mapping)
        }
        shadow_best = shadow.get("best_variant") if isinstance(shadow.get("best_variant"), Mapping) else {}

        variant_scores = [
            self._score_variant(
                variant,
                profile=profile,
                regime=regime,
                opportunity_score=opp_score,
                cost_bps=cost_for_estimate,
                closed_trades=closed,
                profit_factor=pf_value,
                net_pnl_eur=net_pnl,
                health_status=health_status,
                shadow_metrics=shadow_variants.get(variant.name, {}),
            )
            for variant in self.variants[: self.config.max_variants_per_symbol]
        ]
        variant_scores.sort(key=lambda item: item.score, reverse=True)
        selected = variant_scores[0] if variant_scores else None
        status, action = self._status_and_action(
            selected=selected,
            paper_mode=paper_mode,
            closed_trades=closed,
            profit_factor=pf_value,
            net_pnl_eur=net_pnl,
            health_status=health_status,
        )

        evidence = {
            "closed_trades": closed,
            "net_pnl_eur": round(net_pnl, 4),
            "profit_factor": round(pf_value, 4) if pf_value is not None else None,
            "win_rate": _safe_float(health.get("win_rate"), 0.0),
            "health_status": health_status,
            "opportunity_score": round(opp_score, 2),
            "opportunity_reason": opportunity.get("reason"),
            "opportunity_status": opportunity.get("status"),
            "shadow_best_variant": shadow_best.get("variant"),
            "shadow_best_score": shadow_best.get("score"),
            "shadow_closed_trades": shadow_best.get("closed_trades"),
            "shadow_net_pnl_eur": shadow_best.get("net_pnl_eur"),
        }
        current_context = {
            "profile_source": "explicit_registry" if self.registry.has(symbol) else "fallback_profile",
            "base_range_pct": profile.base_range_pct,
            "base_num_levels": profile.base_num_levels,
            "max_capital_per_level": profile.max_capital_per_level,
            "regime": regime,
            "regime_confidence": regime_ctx.get("confidence"),
            "cost_bps": cost_for_estimate,
        }
        execution_policy = {
            "paper_only": True,
            "live_enabled": bool(self.config.live_enabled),
            "live_promotion_allowed": False,
            "apply_to_execution": bool(self.config.apply_to_execution and paper_mode),
            "reason": "paper_mode_optimizer" if paper_mode else "live_observation_only",
        }
        return SymbolSetupPlan(
            symbol=symbol,
            strategy=strategy,
            status=status,
            recommended_action=action,
            selected_variant=selected,
            variants=variant_scores,
            evidence=evidence,
            current_context=current_context,
            execution_policy=execution_policy,
        )

    def _score_variant(
        self,
        variant: SetupVariant,
        *,
        profile: PairProfile,
        regime: str,
        opportunity_score: float,
        cost_bps: Optional[float],
        closed_trades: int,
        profit_factor: Optional[float],
        net_pnl_eur: float,
        health_status: str,
        shadow_metrics: Mapping[str, Any] | None = None,
    ) -> VariantScore:
        grid_config, grid_edge = self._grid_config_for_variant(profile, variant)
        estimated_net = grid_edge - cost_bps if cost_bps is not None else None
        regime_fit = self._regime_fit(variant.name, regime)
        health_fit = self._health_fit(variant.name, health_status, closed_trades, profit_factor, net_pnl_eur)
        shadow_metrics = shadow_metrics if isinstance(shadow_metrics, Mapping) else {}
        shadow_fit = self._shadow_fit(shadow_metrics)
        opportunity_fit = (opportunity_score - 50.0) * 0.22
        edge_fit = 0.0
        if estimated_net is not None:
            edge_fit = _clamp((estimated_net - 20.0) / 120.0 * 18.0, -18.0, 18.0)

        evidence_fit = 0.0
        if closed_trades < self.config.min_closed_trades:
            evidence_fit = -4.0
        elif profit_factor is not None and profit_factor >= self.config.strong_profit_factor and net_pnl_eur > 0.0:
            evidence_fit = 8.0
        elif profit_factor is not None and profit_factor >= self.config.candidate_profit_factor and net_pnl_eur >= self.config.min_net_pnl_eur:
            evidence_fit = 5.0
        elif profit_factor is not None and profit_factor < 1.0:
            evidence_fit = -8.0

        raw_score = 50.0 + regime_fit + health_fit + shadow_fit + opportunity_fit + edge_fit + evidence_fit
        score = _clamp(raw_score)
        shadow_closed = _safe_int(shadow_metrics.get("closed_trades"), 0)
        shadow_status = str(shadow_metrics.get("status") or "").lower()
        shadow_pf_raw = shadow_metrics.get("profit_factor")
        shadow_pf = _safe_float(shadow_pf_raw, 0.0) if shadow_pf_raw is not None else None
        shadow_net = _safe_float(shadow_metrics.get("net_pnl_eur"), 0.0)
        if (
            shadow_status == "candidate"
            and shadow_closed >= max(1, min(self.config.min_closed_trades, 12))
            and shadow_net > 0.0
            and (shadow_pf is None or shadow_pf >= max(1.0, self.config.candidate_profit_factor * 0.90))
        ):
            status = "candidate"
            reason = "shadow_variant_positive"
        elif closed_trades < self.config.min_closed_trades:
            status = "learning"
            reason = "not_enough_closed_trades"
        elif score >= self.config.candidate_score and (profit_factor or 0.0) >= self.config.candidate_profit_factor and net_pnl_eur >= self.config.min_net_pnl_eur:
            status = "candidate"
            reason = "paper_evidence_positive"
        elif health_status in {"weak", "underperforming", "early_weak"}:
            status = "adjust"
            reason = "current_setup_underperforming"
        elif score <= self.config.weak_setup_score:
            status = "weak"
            reason = "variant_score_low"
        else:
            status = "watch"
            reason = "paper_observation"

        return VariantScore(
            name=variant.name,
            score=score,
            status=status,
            reason=reason,
            description=variant.description,
            grid_config=grid_config,
            estimated_grid_gross_edge_bps=grid_edge,
            estimated_net_after_cost_bps=estimated_net,
            components={
                "regime_fit": regime_fit,
                "health_fit": health_fit,
                "opportunity_fit": opportunity_fit,
                "edge_fit": edge_fit,
                "evidence_fit": evidence_fit,
                "shadow_fit": shadow_fit,
            },
            shadow_metrics=dict(shadow_metrics),
        )

    @staticmethod
    def _shadow_fit(shadow_metrics: Mapping[str, Any]) -> float:
        if not shadow_metrics:
            return 0.0
        closed = _safe_int(shadow_metrics.get("closed_trades"), 0)
        samples = _safe_int(shadow_metrics.get("sample_count"), 0)
        if closed <= 0 and samples < 20:
            return 0.0
        score = _safe_float(shadow_metrics.get("score"), 50.0)
        net_pnl = _safe_float(shadow_metrics.get("net_pnl_eur"), 0.0)
        status = str(shadow_metrics.get("status") or "").lower()
        fit = (score - 50.0) * 0.30
        if status == "candidate" and net_pnl > 0.0:
            fit += 8.0
        elif status == "weak":
            fit -= 8.0
        elif net_pnl < 0.0 and closed >= 3:
            fit -= 4.0
        return _clamp(fit, -18.0, 18.0)

    def _grid_config_for_variant(self, profile: PairProfile, variant: SetupVariant) -> tuple[dict[str, Any], float]:
        range_mult = _clamp(
            variant.range_multiplier,
            self.config.min_range_multiplier,
            self.config.max_range_multiplier,
        )
        range_pct = max(profile.min_range_pct, min(profile.max_range_pct, profile.base_range_pct * range_mult))
        num_levels = max(profile.min_levels, min(profile.max_levels, profile.base_num_levels + variant.level_delta))
        max_capital = max(5.0, round(profile.max_capital_per_level * variant.capital_multiplier, 2))
        max_positions = max(1, 10 + variant.max_positions_delta)
        grid_step_pct = range_pct / max(num_levels - 1, 1)
        sell_threshold_pct = max(1.5, grid_step_pct * 0.8)
        grid_config = {
            "range_percent": round(range_pct, 4),
            "num_levels": int(num_levels),
            "max_capital_per_level": max_capital,
            "entry_touch_bps": round(variant.entry_touch_bps, 2),
            "max_positions": int(max_positions),
            "estimated_sell_threshold_pct": round(sell_threshold_pct, 4),
        }
        return grid_config, sell_threshold_pct * 100.0

    @staticmethod
    def _regime_fit(variant_name: str, regime: str) -> float:
        table = {
            "range": {
                "grid_tight_range": 12.0,
                "grid_balanced": 7.0,
                "grid_wide": 1.0,
                "grid_volatility": -3.0,
                "grid_defensive_observe": 2.0,
            },
            "trend": {
                "grid_wide": 8.0,
                "grid_balanced": 2.0,
                "grid_volatility": 4.0,
                "grid_tight_range": -8.0,
                "grid_defensive_observe": 1.0,
            },
            "high_vol": {
                "grid_volatility": 12.0,
                "grid_wide": 8.0,
                "grid_balanced": -1.0,
                "grid_tight_range": -12.0,
                "grid_defensive_observe": 4.0,
            },
            "chaos": {
                "grid_defensive_observe": 10.0,
                "grid_volatility": -2.0,
                "grid_wide": -4.0,
                "grid_balanced": -6.0,
                "grid_tight_range": -10.0,
            },
            "low_activity": {
                "grid_defensive_observe": 8.0,
                "grid_wide": 2.0,
                "grid_balanced": -3.0,
                "grid_tight_range": -6.0,
                "grid_volatility": -8.0,
            },
            "unknown": {
                "grid_balanced": 3.0,
                "grid_defensive_observe": 2.0,
            },
        }
        return table.get(regime, table["unknown"]).get(variant_name, 0.0)

    @staticmethod
    def _health_fit(
        variant_name: str,
        health_status: str,
        closed_trades: int,
        profit_factor: Optional[float],
        net_pnl_eur: float,
    ) -> float:
        if closed_trades <= 0:
            return 0.0
        if health_status in {"healthy", "strong"}:
            base = 8.0
        elif health_status == "watch":
            base = 2.0
        elif health_status == "early_weak":
            base = -8.0
        elif health_status in {"weak", "underperforming"}:
            base = -15.0
        else:
            base = -1.0

        if profit_factor is not None:
            if profit_factor >= 1.6 and net_pnl_eur > 0.0:
                base += 5.0
            elif profit_factor >= 1.25 and net_pnl_eur >= 0.0:
                base += 3.0
            elif profit_factor < 1.0:
                base -= 4.0

        if health_status in {"weak", "underperforming", "early_weak"}:
            if variant_name == "grid_defensive_observe":
                base += 8.0
            elif variant_name in {"grid_wide", "grid_volatility"}:
                base += 3.0
            elif variant_name == "grid_tight_range":
                base -= 3.0
        elif health_status in {"healthy", "strong"} and variant_name == "grid_balanced":
            base += 2.0
        return base

    def _status_and_action(
        self,
        *,
        selected: Optional[VariantScore],
        paper_mode: bool,
        closed_trades: int,
        profit_factor: Optional[float],
        net_pnl_eur: float,
        health_status: str,
    ) -> tuple[str, str]:
        if not self.config.enabled:
            return "disabled", "optimizer_disabled"
        if not paper_mode and not self.config.live_enabled:
            return "observe_only", "live_mode_no_optimizer_action"
        if selected is None:
            return "unknown", "no_variant_available"
        shadow = selected.shadow_metrics if isinstance(selected.shadow_metrics, Mapping) else {}
        shadow_candidate = (
            str(shadow.get("status") or "").lower() == "candidate"
            and _safe_int(shadow.get("closed_trades"), 0) >= max(1, min(self.config.min_closed_trades, 12))
            and _safe_float(shadow.get("net_pnl_eur"), 0.0) > 0.0
        )
        if shadow_candidate and health_status in {"weak", "underperforming", "early_weak"}:
            return "adjust", "paper_shadow_variant_outperforms_current_setup"
        if shadow_candidate:
            return "candidate", "paper_shadow_candidate_review"
        if closed_trades < self.config.min_closed_trades:
            return "learning", "continue_paper_shadow_until_min_sample"
        if health_status in {"weak", "underperforming"} and (profit_factor or 0.0) < 1.0:
            return "pause_current", "pause_current_setup_and_test_selected_variant_in_paper"
        if selected.status == "candidate" and net_pnl_eur >= self.config.min_net_pnl_eur:
            return "candidate", "paper_review_selected_variant"
        if selected.status == "adjust":
            return "adjust", "test_selected_variant_in_paper_shadow"
        return "watch", "continue_paper_observation"
