"""Paper-first colony planning for AUTOBOT Grid children.

The colony manager is intentionally a control-plane component.  It does not
place orders and it does not promote anything to live by itself.  Its job is to
make the future multi-bot behaviour explicit: capital envelopes, child roles,
promotion gates, split gates, and paper-only guardrails.
"""

from __future__ import annotations

import os
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence


_TRUE_VALUES = {"1", "true", "yes", "on"}


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUE_VALUES


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


def _csv(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    return [part.strip() for part in raw.split(",") if part.strip()]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _symbol_key(value: Any) -> str:
    return str(value or "").replace("/", "").upper()


@dataclass(frozen=True)
class ColonyConfig:
    enabled: bool = True
    target_live_capital_eur: float = 500.0
    child_behaviors: tuple[str, ...] = ("core", "momentum", "volatility", "mean_reversion")
    max_paper_children: int = 4
    max_live_children: int = 0
    parent_reserve_pct: float = 35.0
    max_total_active_pct: float = 40.0
    min_child_capital_eur: float = 75.0
    max_child_symbols: int = 6
    min_validation_trades: int = 50
    min_validation_days: int = 7
    min_profit_factor: float = 1.25
    min_net_pnl_pct: float = 1.0
    max_child_drawdown_pct: float = 8.0
    daily_loss_limit_pct: float = 2.0
    min_split_parent_capital_eur: float = 2000.0
    split_child_capital_pct: float = 25.0
    max_splits_per_bot: int = 1
    auto_live_promotion: bool = False
    max_auto_live_capital_eur: float = 0.0
    leverage_enabled: bool = False
    max_leverage: float = 1.0

    @classmethod
    def from_env(cls) -> "ColonyConfig":
        target_default = _env_float("LIVE_CAPITAL_TARGET_EUR", 500.0, 0.0, 10_000_000.0)
        target = _env_float("COLONY_TARGET_LIVE_CAPITAL_EUR", target_default, 0.0, 10_000_000.0)
        behaviors = tuple(_csv("COLONY_CHILD_BEHAVIORS", "core,momentum,volatility,mean_reversion"))
        return cls(
            enabled=_env_bool("COLONY_MANAGER_ENABLED", True),
            target_live_capital_eur=target,
            child_behaviors=behaviors or cls.child_behaviors,
            max_paper_children=_env_int("COLONY_MAX_PAPER_CHILDREN", 4, 1, 100),
            max_live_children=_env_int("COLONY_MAX_LIVE_CHILDREN", 0, 0, 100),
            parent_reserve_pct=_env_float("COLONY_PARENT_RESERVE_PCT", 35.0, 0.0, 95.0),
            max_total_active_pct=_env_float("COLONY_MAX_TOTAL_ACTIVE_PCT", 40.0, 1.0, 100.0),
            min_child_capital_eur=_env_float("COLONY_MIN_CHILD_CAPITAL_EUR", 75.0, 1.0, 1_000_000.0),
            max_child_symbols=_env_int("COLONY_MAX_CHILD_SYMBOLS", 6, 1, 100),
            min_validation_trades=_env_int("COLONY_MIN_VALIDATION_TRADES", 50, 1, 100_000),
            min_validation_days=_env_int("COLONY_MIN_VALIDATION_DAYS", 7, 1, 3650),
            min_profit_factor=_env_float("COLONY_MIN_PROFIT_FACTOR", 1.25, 0.01, 100.0),
            min_net_pnl_pct=_env_float("COLONY_MIN_NET_PNL_PCT", 1.0, -100.0, 10_000.0),
            max_child_drawdown_pct=_env_float("COLONY_MAX_CHILD_DRAWDOWN_PCT", 8.0, 0.1, 100.0),
            daily_loss_limit_pct=_env_float("COLONY_DAILY_LOSS_LIMIT_PCT", 2.0, 0.1, 100.0),
            min_split_parent_capital_eur=_env_float("COLONY_MIN_SPLIT_PARENT_CAPITAL_EUR", 2000.0, 1.0, 100_000_000.0),
            split_child_capital_pct=_env_float("COLONY_SPLIT_CHILD_CAPITAL_PCT", 25.0, 1.0, 95.0),
            max_splits_per_bot=_env_int("COLONY_MAX_SPLITS_PER_BOT", 1, 0, 100),
            auto_live_promotion=_env_bool("COLONY_AUTO_LIVE_PROMOTION", False),
            max_auto_live_capital_eur=_env_float("COLONY_MAX_AUTO_LIVE_CAPITAL_EUR", 0.0, 0.0, 100_000_000.0),
            leverage_enabled=_env_bool("COLONY_LEVERAGE_ENABLED", False),
            max_leverage=_env_float("COLONY_MAX_LEVERAGE", 1.0, 1.0, 10.0),
        )


@dataclass(frozen=True)
class BehaviorProfile:
    name: str
    description: str
    risk_profile: str
    preferred_symbols: tuple[str, ...] = ()
    min_score_bias: float = 0.0


@dataclass
class ColonyChildPlan:
    id: str
    behavior: str
    lifecycle: str
    paper_only: bool
    budget_eur: float
    max_order_eur: float
    candidate_symbols: list[str]
    primary_symbol: str | None
    score: float
    promotion: dict[str, Any] = field(default_factory=dict)
    split: dict[str, Any] = field(default_factory=dict)
    safeguards: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "behavior": self.behavior,
            "lifecycle": self.lifecycle,
            "paper_only": self.paper_only,
            "budget_eur": round(self.budget_eur, 2),
            "max_order_eur": round(self.max_order_eur, 2),
            "candidate_symbols": list(self.candidate_symbols),
            "primary_symbol": self.primary_symbol,
            "score": round(self.score, 2),
            "promotion": self.promotion,
            "split": self.split,
            "safeguards": self.safeguards,
        }


class ColonyManager:
    """Build a transparent, paper-first plan for a Grid bot colony."""

    BEHAVIORS: dict[str, BehaviorProfile] = {
        "core": BehaviorProfile(
            name="core",
            description="liquid large-cap grid with conservative exposure",
            risk_profile="conservative",
            preferred_symbols=("XXBTZEUR", "BTCEUR", "XBT/EUR", "XETHZEUR", "ETHEUR", "ETH/EUR", "SOLEUR", "SOL/EUR"),
            min_score_bias=4.0,
        ),
        "momentum": BehaviorProfile(
            name="momentum",
            description="grid entries only when gross/net edge is strong",
            risk_profile="balanced",
            min_score_bias=2.0,
        ),
        "volatility": BehaviorProfile(
            name="volatility",
            description="grid spacing adapts to higher ATR regimes",
            risk_profile="balanced",
            min_score_bias=1.0,
        ),
        "mean_reversion": BehaviorProfile(
            name="mean_reversion",
            description="range-focused grid with spread and stability priority",
            risk_profile="conservative",
            min_score_bias=0.0,
        ),
    }

    def __init__(self, config: ColonyConfig | None = None) -> None:
        self.config = config or ColonyConfig.from_env()

    def build_snapshot(
        self,
        *,
        opportunities: Sequence[Mapping[str, Any]],
        instances: Iterable[Mapping[str, Any]],
        capital: Mapping[str, Any] | None,
        paper_mode: bool,
    ) -> dict[str, Any]:
        cfg = self.config
        capital = dict(capital or {})
        instances_list = list(instances or [])
        opps = [dict(opp) for opp in opportunities if isinstance(opp, Mapping)]
        runtime_capital = _safe_float(
            capital.get("total_capital", capital.get("total_balance")),
            sum(_safe_float(inst.get("capital")) for inst in instances_list),
        )
        target_capital = cfg.target_live_capital_eur or runtime_capital
        planning_capital = target_capital if target_capital > 0.0 else runtime_capital
        reserve_eur = planning_capital * cfg.parent_reserve_pct / 100.0
        active_budget = max(0.0, planning_capital - reserve_eur)

        behaviors = [b for b in cfg.child_behaviors if b in self.BEHAVIORS]
        if not behaviors:
            behaviors = list(self.BEHAVIORS.keys())
        behaviors = behaviors[: cfg.max_paper_children]
        max_children_by_capital = int(active_budget // max(cfg.min_child_capital_eur, 1.0))
        desired_children = max(1, min(len(behaviors), cfg.max_paper_children, max_children_by_capital or 1))
        behaviors = behaviors[:desired_children]
        child_budget = active_budget / max(len(behaviors), 1)
        symbols_per_child = max(1, min(cfg.max_child_symbols, math.ceil(len(opps) / max(len(behaviors), 1))))

        assigned: set[str] = set()
        children: list[ColonyChildPlan] = []
        for behavior in behaviors:
            profile = self.BEHAVIORS[behavior]
            ranked = self._rank_for_behavior(profile, opps)
            candidates: list[str] = []
            score_sum = 0.0
            for opp in ranked:
                symbol = str(opp.get("symbol") or opp.get("pair") or "")
                if not symbol:
                    continue
                key = _symbol_key(symbol)
                if key in assigned:
                    continue
                candidates.append(symbol)
                assigned.add(key)
                score_sum += _safe_float(opp.get("score"))
                if len(candidates) >= symbols_per_child:
                    break

            if not candidates and ranked:
                symbol = str(ranked[0].get("symbol") or ranked[0].get("pair") or "")
                candidates = [symbol] if symbol else []
                score_sum = _safe_float(ranked[0].get("score"))

            avg_score = score_sum / max(len(candidates), 1)
            lifecycle = "paper_training" if paper_mode else "live_blocked"
            child = ColonyChildPlan(
                id=f"grid_{behavior}",
                behavior=behavior,
                lifecycle=lifecycle,
                paper_only=paper_mode or not cfg.auto_live_promotion or cfg.max_auto_live_capital_eur <= 0.0,
                budget_eur=child_budget,
                max_order_eur=min(child_budget * 0.20, planning_capital * cfg.max_total_active_pct / 100.0),
                candidate_symbols=candidates,
                primary_symbol=candidates[0] if candidates else None,
                score=avg_score,
                promotion=self._promotion_state(behavior, instances_list, paper_mode),
                split=self._split_state(child_budget),
                safeguards=self._safeguards(profile),
            )
            children.append(child)

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "enabled": cfg.enabled,
            "mode": "paper" if paper_mode else "live",
            "paper_mode": paper_mode,
            "implementation_stage": "paper_control_plane",
            "execution": {
                "auto_live_promotion": cfg.auto_live_promotion,
                "max_auto_live_capital_eur": round(cfg.max_auto_live_capital_eur, 2),
                "live_children_allowed": cfg.max_live_children,
                "live_activation_blocked": (not cfg.auto_live_promotion or cfg.max_auto_live_capital_eur <= 0.0),
                "leverage_enabled": cfg.leverage_enabled,
                "max_leverage": cfg.max_leverage if cfg.leverage_enabled else 1.0,
            },
            "capital_model": {
                "runtime_capital_eur": round(runtime_capital, 2),
                "target_live_capital_eur": round(target_capital, 2),
                "planning_capital_eur": round(planning_capital, 2),
                "reserve_eur": round(reserve_eur, 2),
                "active_budget_eur": round(active_budget, 2),
                "min_child_capital_eur": round(cfg.min_child_capital_eur, 2),
            },
            "risk_limits": {
                "parent_reserve_pct": cfg.parent_reserve_pct,
                "max_total_active_pct": cfg.max_total_active_pct,
                "daily_loss_limit_pct": cfg.daily_loss_limit_pct,
                "max_child_drawdown_pct": cfg.max_child_drawdown_pct,
                "max_splits_per_bot": cfg.max_splits_per_bot,
                "split_child_capital_pct": cfg.split_child_capital_pct,
                "min_split_parent_capital_eur": cfg.min_split_parent_capital_eur,
            },
            "children": [child.to_dict() for child in children],
            "runtime": {
                "instance_count": len(instances_list),
                "opportunity_count": len(opps),
                "watchlist_symbols": sorted({_symbol_key(opp.get("symbol") or opp.get("pair")) for opp in opps if (opp.get("symbol") or opp.get("pair"))}),
            },
        }

    def _rank_for_behavior(
        self,
        profile: BehaviorProfile,
        opportunities: Sequence[Mapping[str, Any]],
    ) -> list[Mapping[str, Any]]:
        return sorted(
            opportunities,
            key=lambda opp: self._behavior_score(profile, opp),
            reverse=True,
        )

    def _behavior_score(self, profile: BehaviorProfile, opp: Mapping[str, Any]) -> float:
        score = _safe_float(opp.get("score"))
        symbol = _symbol_key(opp.get("symbol") or opp.get("pair"))
        gross = _safe_float(opp.get("gross_edge_bps"))
        net = _safe_float(opp.get("net_edge_bps"))
        atr = _safe_float(opp.get("atr_bps"))
        spread = _safe_float(opp.get("spread_bps"))
        stability = _safe_float(opp.get("signal_stability"), 0.5)
        if profile.name == "core":
            score += profile.min_score_bias
            if symbol in {_symbol_key(s) for s in profile.preferred_symbols}:
                score += 10.0
            score -= min(12.0, spread * 0.8)
        elif profile.name == "momentum":
            score += min(20.0, gross / 8.0) + min(20.0, net / 8.0)
        elif profile.name == "volatility":
            score += min(25.0, atr / 4.0)
        elif profile.name == "mean_reversion":
            score += stability * 12.0
            score -= min(10.0, spread)
            if 8.0 <= atr <= 120.0:
                score += 8.0
        return score

    def _promotion_state(
        self,
        behavior: str,
        instances: Sequence[Mapping[str, Any]],
        paper_mode: bool,
    ) -> dict[str, Any]:
        cfg = self.config
        trade_count = 0
        max_drawdown_pct = 0.0
        pnl_pct_values: list[float] = []
        for inst in instances:
            status = inst.get("strategy_status") if isinstance(inst.get("strategy_status"), Mapping) else {}
            trade_count += int(_safe_float(status.get("trade_count", inst.get("trade_count")), 0.0))
            max_drawdown_pct = max(max_drawdown_pct, _safe_float(inst.get("max_drawdown")) * 100.0)
            if "profit_pct" in inst:
                pnl_pct_values.append(_safe_float(inst.get("profit_pct")))
        net_pnl_pct = sum(pnl_pct_values) / max(len(pnl_pct_values), 1)
        blockers: list[str] = []
        if not paper_mode:
            blockers.append("not_in_paper_training")
        if trade_count < cfg.min_validation_trades:
            blockers.append("insufficient_trade_history")
        if max_drawdown_pct > cfg.max_child_drawdown_pct:
            blockers.append("drawdown_above_limit")
        if net_pnl_pct < cfg.min_net_pnl_pct:
            blockers.append("net_pnl_below_validation_target")
        if not cfg.auto_live_promotion or cfg.max_auto_live_capital_eur <= 0.0:
            blockers.append("auto_live_promotion_disabled")
        return {
            "eligible": not blockers,
            "target_state": "paper_validated" if not blockers else "paper_training",
            "blocked_reasons": blockers,
            "evidence": {
                "behavior": behavior,
                "trade_count": trade_count,
                "min_validation_trades": cfg.min_validation_trades,
                "net_pnl_pct": round(net_pnl_pct, 3),
                "min_net_pnl_pct": cfg.min_net_pnl_pct,
                "max_drawdown_pct": round(max_drawdown_pct, 3),
                "max_child_drawdown_pct": cfg.max_child_drawdown_pct,
            },
        }

    def _split_state(self, child_budget: float) -> dict[str, Any]:
        cfg = self.config
        child_capital = child_budget * cfg.split_child_capital_pct / 100.0
        blockers: list[str] = []
        if child_budget < cfg.min_split_parent_capital_eur:
            blockers.append("capital_below_split_threshold")
        if cfg.max_splits_per_bot <= 0:
            blockers.append("splits_disabled")
        if child_capital < cfg.min_child_capital_eur:
            blockers.append("child_capital_below_minimum")
        return {
            "eligible": not blockers,
            "blocked_reasons": blockers,
            "planned_child_capital_eur": round(child_capital, 2),
            "max_splits_per_bot": cfg.max_splits_per_bot,
        }

    def _safeguards(self, profile: BehaviorProfile) -> dict[str, Any]:
        cfg = self.config
        return {
            "risk_profile": profile.risk_profile,
            "daily_loss_limit_pct": cfg.daily_loss_limit_pct,
            "max_drawdown_pct": cfg.max_child_drawdown_pct,
            "leverage": 1.0 if not cfg.leverage_enabled else cfg.max_leverage,
            "requires_central_order_router": True,
            "requires_global_risk_manager": True,
            "requires_human_live_unlock": not cfg.auto_live_promotion,
        }
