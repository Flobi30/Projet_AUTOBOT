"""Conservative instance split policy for AUTOBOT.

The policy is pure and disabled for execution by default. It is intended to
audit and plan paper-only spin-offs, not to create runtime children.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


EXECUTION_FLAG_NAME = "ENABLE_INSTANCE_SPLIT_EXECUTOR"
BLOCKING_FAILURE_MODES = {"weak_mfe_below_cost"}
VALIDATED_STRATEGY_STATUSES = {"paper_candidate", "paper_validated", "shadow_passed"}


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class InstanceSplitPolicyConfig:
    executor_enabled: bool = False
    paper_mode_only: bool = True
    max_splits_per_parent_lifetime: int = 1
    min_parent_capital_eur: float = 2_000.0
    child_capital_pct: float = 25.0
    min_child_capital_eur: float = 400.0
    min_net_pnl_eur: float = 0.0
    min_profit_factor: float = 1.25
    min_trade_count: int = 100
    min_validation_days: int = 7
    max_drawdown_pct: float = 12.0
    min_strategy_scorecard: float = 75.0
    required_strategy_statuses: tuple[str, ...] = tuple(sorted(VALIDATED_STRATEGY_STATUSES))
    blocked_failure_modes: tuple[str, ...] = tuple(sorted(BLOCKING_FAILURE_MODES))

    @classmethod
    def from_env(cls) -> "InstanceSplitPolicyConfig":
        return cls(executor_enabled=_env_bool(EXECUTION_FLAG_NAME, False))

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["required_strategy_statuses"] = list(self.required_strategy_statuses)
        payload["blocked_failure_modes"] = list(self.blocked_failure_modes)
        payload["feature_flag"] = EXECUTION_FLAG_NAME
        return payload


@dataclass(frozen=True)
class InstanceSplitEvidence:
    parent_instance_id: str
    parent_capital_eur: float
    parent_available_eur: float
    parent_lifetime_split_count: int = 0
    paper_mode: bool = True
    strategy_id: str = "unknown"
    strategy_status: str = "learning"
    net_pnl_eur: float = 0.0
    profit_factor: float | None = None
    trade_count: int = 0
    validation_days: int = 0
    max_drawdown_pct: float = 0.0
    strategy_scorecard: float = 0.0
    dominant_failure_mode: str | None = None
    official_paper_net_pnl_eur: float = 0.0
    live_promotion_allowed: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["metadata"] = dict(self.metadata)
        return payload


@dataclass(frozen=True)
class InstanceSplitDecision:
    allowed_to_plan: bool
    executor_enabled: bool
    executable_now: bool
    status: str
    reason: str
    blockers: tuple[str, ...]
    planned_child_capital_eur: float
    parent_capital_after_eur: float
    live_promotion_allowed: bool = False
    config: Mapping[str, Any] = field(default_factory=dict)
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed_to_plan": self.allowed_to_plan,
            "executor_enabled": self.executor_enabled,
            "executable_now": self.executable_now,
            "status": self.status,
            "reason": self.reason,
            "blockers": list(self.blockers),
            "planned_child_capital_eur": self.planned_child_capital_eur,
            "parent_capital_after_eur": self.parent_capital_after_eur,
            "live_promotion_allowed": self.live_promotion_allowed,
            "config": dict(self.config),
            "evidence": dict(self.evidence),
        }


class InstanceSplitPolicy:
    """Evaluate whether a parent instance may create one paper child."""

    def __init__(self, config: InstanceSplitPolicyConfig | None = None) -> None:
        self.config = config or InstanceSplitPolicyConfig.from_env()

    def evaluate(self, evidence: InstanceSplitEvidence | Mapping[str, Any]) -> InstanceSplitDecision:
        ev = evidence if isinstance(evidence, InstanceSplitEvidence) else _evidence_from_mapping(evidence)
        cfg = self.config
        planned_child = max(0.0, float(ev.parent_capital_eur) * cfg.child_capital_pct / 100.0)
        parent_after = float(ev.parent_capital_eur) - planned_child
        blockers: list[str] = []

        if cfg.paper_mode_only and not ev.paper_mode:
            blockers.append("paper_mode_required")
        if ev.live_promotion_allowed:
            blockers.append("live_promotion_must_remain_false")
        if ev.parent_lifetime_split_count >= cfg.max_splits_per_parent_lifetime:
            blockers.append("parent_already_split")
        if ev.parent_capital_eur < cfg.min_parent_capital_eur:
            blockers.append("parent_capital_below_threshold")
        if planned_child < cfg.min_child_capital_eur:
            blockers.append("planned_child_capital_below_minimum")
        if planned_child > ev.parent_available_eur:
            blockers.append("available_capital_below_child_capital")
        if ev.net_pnl_eur <= cfg.min_net_pnl_eur:
            blockers.append("net_pnl_not_positive_after_costs")
        if ev.official_paper_net_pnl_eur <= cfg.min_net_pnl_eur:
            blockers.append("official_paper_net_pnl_not_positive")
        if ev.profit_factor is None or ev.profit_factor < cfg.min_profit_factor:
            blockers.append("profit_factor_below_threshold")
        if ev.trade_count < cfg.min_trade_count:
            blockers.append("insufficient_trade_count")
        if ev.validation_days < cfg.min_validation_days:
            blockers.append("insufficient_validation_days")
        if ev.max_drawdown_pct > cfg.max_drawdown_pct:
            blockers.append("drawdown_above_threshold")
        if ev.strategy_scorecard < cfg.min_strategy_scorecard:
            blockers.append("strategy_scorecard_below_threshold")
        if ev.strategy_status not in set(cfg.required_strategy_statuses):
            blockers.append("strategy_status_not_validated")
        if ev.dominant_failure_mode in set(cfg.blocked_failure_modes):
            blockers.append(f"blocked_failure_mode:{ev.dominant_failure_mode}")

        allowed_to_plan = not blockers
        executable_now = allowed_to_plan and bool(cfg.executor_enabled)
        if executable_now:
            status = "executable_paper_only"
            reason = "split_policy_passed_and_executor_enabled"
        elif allowed_to_plan:
            status = "planned_only"
            reason = "split_policy_passed_but_executor_disabled"
        else:
            status = "blocked"
            reason = ",".join(blockers)
        return InstanceSplitDecision(
            allowed_to_plan=allowed_to_plan,
            executor_enabled=bool(cfg.executor_enabled),
            executable_now=executable_now,
            status=status,
            reason=reason,
            blockers=tuple(blockers),
            planned_child_capital_eur=round(planned_child, 6),
            parent_capital_after_eur=round(parent_after, 6),
            live_promotion_allowed=False,
            config=cfg.to_dict(),
            evidence=ev.to_dict(),
        )


def _evidence_from_mapping(payload: Mapping[str, Any]) -> InstanceSplitEvidence:
    return InstanceSplitEvidence(
        parent_instance_id=str(payload.get("parent_instance_id") or ""),
        parent_capital_eur=_float(payload.get("parent_capital_eur")),
        parent_available_eur=_float(payload.get("parent_available_eur")),
        parent_lifetime_split_count=int(_float(payload.get("parent_lifetime_split_count"))),
        paper_mode=bool(payload.get("paper_mode", True)),
        strategy_id=str(payload.get("strategy_id") or "unknown"),
        strategy_status=str(payload.get("strategy_status") or "learning"),
        net_pnl_eur=_float(payload.get("net_pnl_eur")),
        profit_factor=_optional_float(payload.get("profit_factor")),
        trade_count=int(_float(payload.get("trade_count"))),
        validation_days=int(_float(payload.get("validation_days"))),
        max_drawdown_pct=_float(payload.get("max_drawdown_pct")),
        strategy_scorecard=_float(payload.get("strategy_scorecard")),
        dominant_failure_mode=(
            str(payload.get("dominant_failure_mode"))
            if payload.get("dominant_failure_mode") not in (None, "")
            else None
        ),
        official_paper_net_pnl_eur=_float(payload.get("official_paper_net_pnl_eur")),
        live_promotion_allowed=bool(payload.get("live_promotion_allowed", False)),
        metadata=dict(payload.get("metadata") or {}),
    )


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _optional_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
