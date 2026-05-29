"""Paper-only multi-engine strategy router.

The router compares isolated shadow evidence from Grid, Trend/Momentum and
Mean-Reversion labs. It never enables live trading. A separate paper-only
adapter may let a validated Grid candidate replace the official paper setup.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Optional

from .pair_strategy_health import symbol_key
from .strategy_promotion_gate import StrategyPromotionGate, StrategyPromotionGateConfig


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


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class StrategyRouterConfig:
    enabled: bool = True
    live_enabled: bool = False
    min_shadow_closed_trades: int = 5
    candidate_score: float = 70.0
    watch_score: float = 55.0
    weak_score: float = 40.0
    no_trade_score: float = 50.0
    evidence_cap_learning_score: float = 62.0

    @classmethod
    def from_env(cls) -> "StrategyRouterConfig":
        return cls(
            enabled=_env_bool("STRATEGY_ROUTER_ENABLED", True),
            live_enabled=_env_bool("STRATEGY_ROUTER_LIVE_ENABLED", False),
            min_shadow_closed_trades=_env_int("STRATEGY_ROUTER_MIN_SHADOW_CLOSED_TRADES", 5, 1, 100_000),
            candidate_score=_env_float("STRATEGY_ROUTER_CANDIDATE_SCORE", 70.0, 0.0, 100.0),
            watch_score=_env_float("STRATEGY_ROUTER_WATCH_SCORE", 55.0, 0.0, 100.0),
            weak_score=_env_float("STRATEGY_ROUTER_WEAK_SCORE", 40.0, 0.0, 100.0),
            no_trade_score=_env_float("STRATEGY_ROUTER_NO_TRADE_SCORE", 50.0, 0.0, 100.0),
            evidence_cap_learning_score=_env_float("STRATEGY_ROUTER_LEARNING_SCORE_CAP", 62.0, 0.0, 100.0),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "live_enabled": self.live_enabled,
            "min_shadow_closed_trades": self.min_shadow_closed_trades,
            "candidate_score": self.candidate_score,
            "watch_score": self.watch_score,
            "weak_score": self.weak_score,
            "no_trade_score": self.no_trade_score,
            "evidence_cap_learning_score": self.evidence_cap_learning_score,
        }


class StrategyRouter:
    """Rank candidate engines per symbol from shadow evidence."""

    def __init__(
        self,
        config: Optional[StrategyRouterConfig] = None,
        promotion_gate_config: Optional[StrategyPromotionGateConfig] = None,
    ) -> None:
        self.config = config or StrategyRouterConfig.from_env()
        self.promotion_gate = StrategyPromotionGate(promotion_gate_config)

    def build_snapshot(
        self,
        *,
        instances: Iterable[Mapping[str, Any]],
        paper_mode: bool,
        setup_shadow_by_symbol: Mapping[str, Mapping[str, Any]] | None = None,
        trend_shadow_by_symbol: Mapping[str, Mapping[str, Any]] | None = None,
        mean_reversion_shadow_by_symbol: Mapping[str, Mapping[str, Any]] | None = None,
        opportunities: Iterable[Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        setup_shadow_by_symbol = setup_shadow_by_symbol or {}
        trend_shadow_by_symbol = trend_shadow_by_symbol or {}
        mean_reversion_shadow_by_symbol = mean_reversion_shadow_by_symbol or {}
        opp_by_symbol = {
            symbol_key(item.get("symbol")): item
            for item in opportunities or []
            if isinstance(item, Mapping) and symbol_key(item.get("symbol")) != "UNKNOWN"
        }

        symbols = self._symbols(
            instances,
            setup_shadow_by_symbol,
            trend_shadow_by_symbol,
            mean_reversion_shadow_by_symbol,
            opp_by_symbol,
        )
        rows = []
        for symbol in sorted(symbols):
            engines = [
                self._engine_candidate("dynamic_grid", "setup_shadow_lab", setup_shadow_by_symbol.get(symbol)),
                self._engine_candidate("trend_momentum", "trend_shadow_lab", trend_shadow_by_symbol.get(symbol)),
                self._engine_candidate("mean_reversion", "mean_reversion_shadow_lab", mean_reversion_shadow_by_symbol.get(symbol)),
            ]
            engines = [engine for engine in engines if engine is not None]
            no_trade = self._no_trade_candidate(engines)
            ranked = sorted([*engines, no_trade], key=lambda item: item["router_score"], reverse=True)
            selected = ranked[0]
            action, reason = self._recommendation(selected, ranked)
            promotion_gate = self.promotion_gate.evaluate(selected, action, paper_mode=paper_mode)
            paper_execution_policy = self._paper_execution_policy(
                selected,
                action,
                paper_mode=paper_mode,
                promotion_gate=promotion_gate,
            )
            opp = opp_by_symbol.get(symbol, {})
            rows.append(
                {
                    "symbol": symbol,
                    "selected_engine": selected["engine"],
                    "selected_variant": selected.get("variant"),
                    "router_score": round(float(selected["router_score"]), 2),
                    "status": selected["status"],
                    "validation_status": selected.get("validation_status"),
                    "recommended_action": action,
                    "reason": reason,
                    "paper_only": True,
                    "live_promotion_allowed": False,
                    "official_execution_enabled": paper_execution_policy.get("support") == "paper_official_candidate",
                    "paper_official_execution_enabled": paper_execution_policy.get("support") == "paper_official_candidate",
                    "opportunity_score": opp.get("score") if isinstance(opp, Mapping) else None,
                    "opportunity_status": opp.get("status") if isinstance(opp, Mapping) else None,
                    "opportunity_reason": opp.get("reason") if isinstance(opp, Mapping) else None,
                    "promotion_gate": promotion_gate,
                    "paper_execution_policy": paper_execution_policy,
                    "engines": ranked,
                }
            )

        candidate_count = sum(1 for row in rows if row["recommended_action"] == "shadow_candidate_review")
        official_candidate_count = sum(1 for row in rows if row["paper_execution_policy"].get("support") == "paper_official_candidate")
        promotion_blocked_count = sum(
            1
            for row in rows
            if row["recommended_action"] == "shadow_candidate_review"
            and row["paper_execution_policy"].get("support") != "paper_official_candidate"
        )
        no_trade_count = sum(1 for row in rows if row["selected_engine"] == "no_trade")
        learning_count = sum(1 for row in rows if row["recommended_action"] == "continue_shadow_learning")
        paper_official_execution_enabled = paper_mode and _env_bool("PAPER_EXECUTION_ROUTER_ENABLED", True)
        return {
            "timestamp": _utc_now(),
            "mode": "paper" if paper_mode else "live_shadow_observation",
            "paper_mode": paper_mode,
            "enabled": self.config.enabled,
            "paper_only": True,
            "live_promotion_allowed": False,
            "official_execution_enabled": paper_official_execution_enabled,
            "paper_official_execution_enabled": paper_official_execution_enabled,
            "config": self.config.to_dict(),
            "promotion_gate": {
                "enabled": self.promotion_gate.config.enabled,
                "config": self.promotion_gate.config.to_dict(),
                "passed_symbols": official_candidate_count,
                "blocked_symbols": promotion_blocked_count,
            },
            "summary": {
                "symbols": len(rows),
                "candidate_symbols": candidate_count,
                "paper_official_candidate_symbols": official_candidate_count,
                "promotion_blocked_symbols": promotion_blocked_count,
                "learning_symbols": learning_count,
                "no_trade_symbols": no_trade_count,
            },
            "routes": rows,
            "by_symbol": {row["symbol"]: row for row in rows},
            "message": (
                "Strategy router ranks grid, trend, mean-reversion and no-trade from shadow evidence. "
                "Validated candidates can graduate to controlled paper execution while live stays blocked."
            ),
        }

    def _symbols(
        self,
        instances: Iterable[Mapping[str, Any]],
        *groups: Mapping[str, Any],
    ) -> set[str]:
        symbols: set[str] = set()
        for inst in instances or []:
            if not isinstance(inst, Mapping):
                continue
            symbol = symbol_key(inst.get("symbol") or inst.get("pair"))
            if symbol != "UNKNOWN":
                symbols.add(symbol)
        for group in groups:
            for raw_symbol in group.keys():
                symbol = symbol_key(raw_symbol)
                if symbol != "UNKNOWN":
                    symbols.add(symbol)
        return symbols

    def _engine_candidate(
        self,
        engine: str,
        source: str,
        symbol_payload: Optional[Mapping[str, Any]],
    ) -> Optional[dict[str, Any]]:
        if not isinstance(symbol_payload, Mapping):
            return None
        best = symbol_payload.get("best_variant")
        if not isinstance(best, Mapping):
            return None
        raw_score = _safe_float(best.get("score"), 0.0)
        closed = _safe_int(best.get("closed_trades"), 0)
        sample_count = _safe_int(best.get("sample_count"), 0)
        net_pnl = _safe_float(best.get("net_pnl_eur"), 0.0)
        status = str(best.get("status") or "learning")
        validation_status = str(best.get("validation_status") or best.get("research_status") or "learning")
        score = self._router_score(raw_score, status, closed, net_pnl)
        return {
            "engine": engine,
            "variant": best.get("variant") or best.get("name"),
            "source": source,
            "status": status,
            "validation_status": validation_status,
            "router_score": round(score, 2),
            "raw_score": round(raw_score, 2),
            "net_pnl_eur": round(net_pnl, 4),
            "realized_pnl_eur": best.get("realized_pnl_eur"),
            "profit_factor": best.get("profit_factor"),
            "win_rate": best.get("win_rate"),
            "max_drawdown_eur": best.get("max_drawdown_eur"),
            "closed_trades": closed,
            "open_positions": _safe_int(best.get("open_positions"), 0),
            "sample_count": sample_count,
            "last_decision": best.get("last_decision") if isinstance(best.get("last_decision"), Mapping) else {},
        }

    def _router_score(self, raw_score: float, status: str, closed: int, net_pnl: float) -> float:
        score = raw_score
        if closed < self.config.min_shadow_closed_trades:
            score = min(score, self.config.evidence_cap_learning_score)
        if status == "candidate":
            score += 6.0
        elif status == "watch":
            score += 2.0
        elif status == "weak":
            score -= 12.0
        elif status == "learning":
            score -= 2.0
        if net_pnl < 0.0:
            score -= min(15.0, abs(net_pnl) * 1.5)
        elif net_pnl > 0.0:
            score += min(8.0, net_pnl * 1.5)
        return max(0.0, min(100.0, score))

    def _no_trade_candidate(self, engines: list[dict[str, Any]]) -> dict[str, Any]:
        if not engines:
            score = self.config.no_trade_score + 10.0
            reason = "no_engine_evidence"
        elif all(engine["status"] == "weak" for engine in engines):
            score = self.config.no_trade_score + 18.0
            reason = "all_engines_weak"
        elif all(_safe_int(engine.get("closed_trades")) < self.config.min_shadow_closed_trades for engine in engines):
            score = self.config.no_trade_score + 6.0
            reason = "insufficient_shadow_evidence"
        elif max(float(engine["router_score"]) for engine in engines) < self.config.watch_score:
            score = self.config.no_trade_score + 10.0
            reason = "no_engine_above_watch_score"
        else:
            score = self.config.no_trade_score
            reason = "available_as_safety_choice"
        return {
            "engine": "no_trade",
            "variant": "abstain",
            "source": "router_safety",
            "status": "available",
            "router_score": round(min(100.0, score), 2),
            "raw_score": round(self.config.no_trade_score, 2),
            "net_pnl_eur": 0.0,
            "profit_factor": None,
            "win_rate": None,
            "max_drawdown_eur": None,
            "closed_trades": 0,
            "open_positions": 0,
            "sample_count": 0,
            "last_decision": {"status": "router_choice", "reason": reason},
        }

    def _recommendation(self, selected: Mapping[str, Any], ranked: list[Mapping[str, Any]]) -> tuple[str, str]:
        engine = str(selected.get("engine") or "no_trade")
        if engine == "no_trade":
            return "no_trade", str((selected.get("last_decision") or {}).get("reason") or "router_safety")
        closed = _safe_int(selected.get("closed_trades"), 0)
        score = _safe_float(selected.get("router_score"), 0.0)
        status = str(selected.get("status") or "learning")
        if closed < self.config.min_shadow_closed_trades:
            return "continue_shadow_learning", "insufficient_shadow_closed_trades"
        if status == "candidate" and score >= self.config.candidate_score:
            return "shadow_candidate_review", "best_engine_has_candidate_evidence"
        if score >= self.config.watch_score and status in {"watch", "candidate"}:
            return "watch_best_engine", "best_engine_positive_but_not_promoted"
        runner_up = ranked[1] if len(ranked) > 1 else {}
        if runner_up and runner_up.get("engine") == "no_trade":
            return "continue_shadow_learning", "no_trade_close_second"
        return "continue_shadow_learning", "no_engine_validated_yet"

    def _paper_execution_policy(
        self,
        selected: Mapping[str, Any],
        action: str,
        *,
        paper_mode: bool,
        promotion_gate: Mapping[str, Any],
    ) -> dict[str, Any]:
        paper_router_enabled = paper_mode and _env_bool("PAPER_EXECUTION_ROUTER_ENABLED", True)
        engine = str(selected.get("engine") or "no_trade")
        gate_passed = bool(promotion_gate.get("passed"))
        gate_reason = str(promotion_gate.get("reason") or "promotion_gate_unknown")
        if engine == "dynamic_grid":
            if action == "shadow_candidate_review" and paper_router_enabled and gate_passed:
                return {
                    "support": "paper_official_candidate",
                    "reason": "dynamic_grid_adapter_available",
                    "paper_execution_enabled": True,
                    "live_enabled": False,
                    "promotion_gate": promotion_gate,
                }
            if action == "shadow_candidate_review" and paper_router_enabled and not gate_passed:
                return {
                    "support": "paper_observation",
                    "reason": gate_reason,
                    "paper_execution_enabled": paper_router_enabled,
                    "live_enabled": False,
                    "promotion_gate": promotion_gate,
                }
            return {
                "support": "paper_observation",
                "reason": "dynamic_grid_waiting_for_candidate_evidence" if paper_router_enabled else "paper_execution_router_disabled",
                "paper_execution_enabled": paper_router_enabled,
                "live_enabled": False,
                "promotion_gate": promotion_gate,
            }
        if engine in {"trend_momentum", "mean_reversion"}:
            adapter_enabled = paper_mode and _env_bool("PAPER_EXECUTION_ADAPTER_ENABLED", True)
            trend_enabled = _env_bool("PAPER_EXECUTION_ADAPTER_TREND_ENABLED", True)
            mean_reversion_enabled = _env_bool("PAPER_EXECUTION_ADAPTER_MEAN_REVERSION_ENABLED", True)
            engine_enabled = (
                trend_enabled if engine == "trend_momentum" else mean_reversion_enabled
            )
            if action == "shadow_candidate_review" and paper_router_enabled and adapter_enabled and engine_enabled and gate_passed:
                return {
                    "support": "paper_official_candidate",
                    "reason": "shadow_paper_execution_adapter_available",
                    "paper_execution_enabled": True,
                    "live_enabled": False,
                    "promotion_gate": promotion_gate,
                }
            return {
                "support": "shadow_only",
                "reason": (
                    gate_reason
                    if action == "shadow_candidate_review" and not gate_passed
                    else
                    "paper_execution_adapter_disabled"
                    if not adapter_enabled or not engine_enabled
                    else "shadow_candidate_waiting_for_review"
                ),
                "paper_execution_enabled": False,
                "live_enabled": False,
                "promotion_gate": promotion_gate,
            }
        return {
            "support": "abstain",
            "reason": "router_selected_no_trade",
            "paper_execution_enabled": False,
            "live_enabled": False,
            "promotion_gate": promotion_gate,
        }
