"""Paper-first execution governance for strategy selection.

This module turns router/reconciliation evidence into an execution policy.
It remains paper-only: the result may block or reroute official paper entries,
but it never enables live trading.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Optional

from .pair_strategy_health import symbol_key


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
class StrategyGovernanceConfig:
    enabled: bool = True
    apply_to_execution: bool = True
    block_on_no_trade: bool = True
    block_on_divergence: bool = True
    allow_non_grid_shadow_mirror: bool = True
    candidate_score_min: float = 70.0

    @classmethod
    def from_env(cls) -> "StrategyGovernanceConfig":
        return cls(
            enabled=_env_bool("STRATEGY_GOVERNANCE_ENABLED", True),
            apply_to_execution=_env_bool("STRATEGY_GOVERNANCE_APPLY_TO_EXECUTION", True),
            block_on_no_trade=_env_bool("STRATEGY_GOVERNANCE_BLOCK_ON_NO_TRADE", True),
            block_on_divergence=_env_bool("STRATEGY_GOVERNANCE_BLOCK_ON_DIVERGENCE", True),
            allow_non_grid_shadow_mirror=_env_bool("STRATEGY_GOVERNANCE_ALLOW_NON_GRID_MIRROR", True),
            candidate_score_min=_env_float("STRATEGY_GOVERNANCE_CANDIDATE_SCORE_MIN", 70.0, 0.0, 100.0),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "apply_to_execution": self.apply_to_execution,
            "block_on_no_trade": self.block_on_no_trade,
            "block_on_divergence": self.block_on_divergence,
            "allow_non_grid_shadow_mirror": self.allow_non_grid_shadow_mirror,
            "candidate_score_min": self.candidate_score_min,
        }


class StrategyGovernanceEngine:
    """Convert strategy evidence into a paper execution policy."""

    def __init__(self, config: Optional[StrategyGovernanceConfig] = None) -> None:
        self.config = config or StrategyGovernanceConfig.from_env()

    def build_snapshot(
        self,
        *,
        router_snapshot: Mapping[str, Any] | None,
        reconciliation_snapshot: Mapping[str, Any] | None,
        paper_mode: bool,
        instance_state_by_symbol: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        router_snapshot = router_snapshot if isinstance(router_snapshot, Mapping) else {}
        reconciliation_snapshot = reconciliation_snapshot if isinstance(reconciliation_snapshot, Mapping) else {}
        instance_state_by_symbol = instance_state_by_symbol if isinstance(instance_state_by_symbol, Mapping) else {}

        routes = list(router_snapshot.get("routes", []) or [])
        reconciliation_by_symbol = self._reconciliation_by_symbol(reconciliation_snapshot.get("symbols", []))

        rows = []
        for route in routes:
            if not isinstance(route, Mapping):
                continue
            symbol = symbol_key(route.get("symbol"))
            if symbol == "UNKNOWN":
                continue
            row = self._govern_symbol(
                symbol=symbol,
                route=route,
                reconciliation=reconciliation_by_symbol.get(symbol, {}),
                instance_state=instance_state_by_symbol.get(symbol, {}),
                paper_mode=paper_mode,
            )
            rows.append(row)

        priority = {
            "blocked": 0,
            "review": 1,
            "pending_flat": 2,
            "eligible": 3,
            "learning": 4,
            "observe": 5,
        }
        rows.sort(key=lambda item: (priority.get(str(item.get("governance_status")), 99), item["symbol"]))

        return {
            "timestamp": _utc_now(),
            "mode": "paper" if paper_mode else "live_observation",
            "paper_mode": paper_mode,
            "paper_only": True,
            "live_promotion_allowed": False,
            "enabled": self.config.enabled,
            "apply_to_execution": self.config.apply_to_execution,
            "config": self.config.to_dict(),
            "summary": {
                "symbols": len(rows),
                "eligible_symbols": sum(1 for row in rows if row.get("governance_status") == "eligible"),
                "blocked_symbols": sum(1 for row in rows if row.get("block_new_entries")),
                "mirror_symbols": sum(1 for row in rows if row.get("execution_mode") == "shadow_signal_mirror"),
                "pending_flat_symbols": sum(1 for row in rows if row.get("execution_mode") == "shadow_signal_mirror_pending_flat"),
            },
            "symbols": rows,
            "by_symbol": {row["symbol"]: row for row in rows},
            "message": (
                "Strategy governance converts router plus reconciliation evidence into a paper execution policy. "
                "It can block weak official entries, keep learning in shadow, or allow a controlled non-grid mirror in paper."
            ),
        }

    def _reconciliation_by_symbol(self, rows: Iterable[Any]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for row in rows or []:
            if not isinstance(row, Mapping):
                continue
            symbol = symbol_key(row.get("symbol"))
            if symbol == "UNKNOWN":
                continue
            result[symbol] = dict(row)
        return result

    def _govern_symbol(
        self,
        *,
        symbol: str,
        route: Mapping[str, Any],
        reconciliation: Mapping[str, Any],
        instance_state: Mapping[str, Any],
        paper_mode: bool,
    ) -> dict[str, Any]:
        selected_engine = str(route.get("selected_engine") or "no_trade")
        selected_variant = route.get("selected_variant")
        router_score = _safe_float(route.get("router_score"))
        router_action = str(route.get("recommended_action") or "continue_shadow_learning")
        router_reason = str(route.get("reason") or "unknown")
        paper_policy = route.get("paper_execution_policy") if isinstance(route.get("paper_execution_policy"), Mapping) else {}
        recon_verdict = str(reconciliation.get("verdict") or "none")
        recon_action = str(reconciliation.get("recommended_action") or "continue_observation")
        open_positions = _safe_int(instance_state.get("open_positions"))

        reasons: list[str] = []
        decision = "observe"
        governance_status = "observe"
        execution_mode = "observe_only"
        allow_grid_entries = True
        allow_shadow_signal_mirror = False
        block_new_entries = False
        official_execution_engine = "dynamic_grid"

        if not self.config.enabled or not paper_mode:
            reasons.append("governance_disabled_or_not_paper")
        elif selected_engine == "no_trade":
            reasons.append("router_selected_no_trade")
            decision = "abstain"
            governance_status = "blocked" if self.config.block_on_no_trade else "observe"
            execution_mode = "observe_only"
            allow_grid_entries = not self.config.block_on_no_trade
            block_new_entries = self.config.block_on_no_trade
            official_execution_engine = "none"
        elif selected_engine in {"trend_momentum", "mean_reversion"}:
            support = str(paper_policy.get("support") or "shadow_only")
            if (
                self.config.allow_non_grid_shadow_mirror
                and support == "paper_official_candidate"
                and router_action == "shadow_candidate_review"
                and router_score >= self.config.candidate_score_min
            ):
                if recon_verdict == "shadow_sample_not_robust":
                    reasons.append("shadow_candidate_not_robust_yet")
                    decision = "keep_learning"
                    governance_status = "learning"
                    execution_mode = "observe_only"
                elif open_positions > 0:
                    reasons.extend(["grid_positions_still_open", "wait_until_flat_before_non_grid_mirror"])
                    decision = "wait_until_flat_then_mirror"
                    governance_status = "pending_flat"
                    execution_mode = "shadow_signal_mirror_pending_flat"
                    allow_grid_entries = False
                    block_new_entries = True
                    official_execution_engine = selected_engine
                else:
                    reasons.append("non_grid_shadow_candidate_eligible_for_paper_mirror")
                    decision = "mirror_non_grid_candidate"
                    governance_status = "eligible"
                    execution_mode = "shadow_signal_mirror"
                    allow_grid_entries = False
                    allow_shadow_signal_mirror = True
                    block_new_entries = True
                    official_execution_engine = selected_engine
            else:
                reasons.append(str(paper_policy.get("reason") or "non_grid_candidate_not_ready"))
                decision = "keep_shadow_learning"
                governance_status = "learning" if router_action == "continue_shadow_learning" else "review"
                execution_mode = "grid_runtime"
        else:
            decision = "run_grid"
            governance_status = "eligible"
            execution_mode = "grid_runtime"

        if (
            self.config.block_on_divergence
            and selected_engine == "dynamic_grid"
            and recon_verdict in {"official_underperforming", "shadow_official_divergence"}
        ):
            reasons.append(recon_verdict)
            reasons.append(recon_action)
            decision = "pause_grid_review_divergence"
            governance_status = "review"
            execution_mode = "grid_runtime"
            allow_grid_entries = False
            block_new_entries = True
            official_execution_engine = "dynamic_grid"

        if selected_engine == "dynamic_grid" and execution_mode == "grid_runtime" and governance_status == "eligible":
            reasons.append("grid_remains_official_paper_engine")
            decision = "run_grid"

        if not reasons:
            reasons.append(router_reason)

        return {
            "symbol": symbol,
            "selected_engine": selected_engine,
            "selected_variant": selected_variant,
            "router_score": round(router_score, 2),
            "router_action": router_action,
            "router_reason": router_reason,
            "reconciliation_verdict": recon_verdict,
            "reconciliation_action": recon_action,
            "open_positions": open_positions,
            "governance_status": governance_status,
            "decision": decision,
            "execution_mode": execution_mode,
            "official_execution_engine": official_execution_engine,
            "allow_grid_entries": allow_grid_entries,
            "allow_shadow_signal_mirror": allow_shadow_signal_mirror,
            "block_new_entries": block_new_entries,
            "paper_only": True,
            "live_promotion_allowed": False,
            "reason": sorted(set(str(reason) for reason in reasons if reason))[0] if reasons else router_reason,
            "reasons": sorted(set(str(reason) for reason in reasons if reason)),
            "paper_execution_policy": dict(paper_policy) if paper_policy else {},
        }
