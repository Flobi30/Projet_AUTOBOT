"""Evidence gate before shadow strategies can affect official paper execution.

The gate is deliberately conservative. It does not decide whether a signal is
good, and it never enables live trading. It only answers whether a shadow
engine has enough paper evidence to be treated as an official paper candidate.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping

from .strategy_runtime_policy import GRID_RUNTIME_RETIRED_REASON, is_runtime_engine_retired
from .strategy_validation_registry import EXECUTION_READY_STATUSES, PROMOTABLE_STRATEGY_IDS, WORKFLOW_STATUSES


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


def _optional_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class StrategyPromotionGateConfig:
    enabled: bool = True
    research_workflow_enabled: bool = True
    min_closed_trades: int = 30
    min_sample_count: int = 100
    min_profit_factor: float = 1.25
    min_net_pnl_eur: float = 0.0
    min_win_rate_pct: float = 45.0
    no_loss_min_closed_trades: int = 50
    max_drawdown_eur: float = 1_000_000.0

    @classmethod
    def from_env(cls) -> "StrategyPromotionGateConfig":
        return cls(
            enabled=_env_bool("STRATEGY_PROMOTION_GATE_ENABLED", True),
            research_workflow_enabled=_env_bool("STRATEGY_RESEARCH_WORKFLOW_GATE_ENABLED", True),
            min_closed_trades=_env_int("STRATEGY_PROMOTION_MIN_CLOSED_TRADES", 30, 1, 100_000),
            min_sample_count=_env_int("STRATEGY_PROMOTION_MIN_SAMPLE_COUNT", 100, 1, 1_000_000),
            min_profit_factor=_env_float("STRATEGY_PROMOTION_MIN_PROFIT_FACTOR", 1.25, 0.01, 100.0),
            min_net_pnl_eur=_env_float("STRATEGY_PROMOTION_MIN_NET_PNL_EUR", 0.0, -1_000_000.0, 1_000_000.0),
            min_win_rate_pct=_env_float("STRATEGY_PROMOTION_MIN_WIN_RATE_PCT", 45.0, 0.0, 100.0),
            no_loss_min_closed_trades=_env_int(
                "STRATEGY_PROMOTION_NO_LOSS_MIN_CLOSED_TRADES", 50, 1, 100_000
            ),
            max_drawdown_eur=_env_float("STRATEGY_PROMOTION_MAX_DRAWDOWN_EUR", 1_000_000.0, 0.0, 1_000_000_000.0),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "research_workflow_enabled": self.research_workflow_enabled,
            "min_closed_trades": self.min_closed_trades,
            "min_sample_count": self.min_sample_count,
            "min_profit_factor": self.min_profit_factor,
            "min_net_pnl_eur": self.min_net_pnl_eur,
            "min_win_rate_pct": self.min_win_rate_pct,
            "no_loss_min_closed_trades": self.no_loss_min_closed_trades,
            "max_drawdown_eur": self.max_drawdown_eur,
        }


class StrategyPromotionGate:
    """Apply paper promotion checks to one selected router candidate."""

    def __init__(self, config: StrategyPromotionGateConfig | None = None) -> None:
        self.config = config or StrategyPromotionGateConfig.from_env()

    def evaluate(
        self,
        selected: Mapping[str, Any],
        action: str,
        *,
        paper_mode: bool,
    ) -> dict[str, Any]:
        engine = str(selected.get("engine") or "no_trade")
        if not self.config.enabled:
            return self._result(True, "disabled", "promotion_gate_disabled", {})
        if not paper_mode:
            return self._result(False, "blocked", "not_paper_mode", {})
        if action != "shadow_candidate_review":
            return self._result(False, "learning", "router_not_requesting_promotion", {})
        if engine == "no_trade":
            return self._result(False, "blocked", "no_trade_selected", {})
        if is_runtime_engine_retired(engine):
            return self._result(
                False,
                "blocked",
                GRID_RUNTIME_RETIRED_REASON,
                {"engine": {"value": engine, "passed": False}},
            )
        if engine not in PROMOTABLE_STRATEGY_IDS:
            return self._result(
                False,
                "blocked",
                "unknown_strategy_engine",
                {
                    "engine": {
                        "value": engine,
                        "allowed": sorted(PROMOTABLE_STRATEGY_IDS),
                        "passed": False,
                    }
                },
            )

        closed_trades = _safe_int(selected.get("closed_trades"), 0)
        sample_count = _safe_int(selected.get("sample_count"), 0)
        net_pnl = _safe_float(selected.get("net_pnl_eur"), 0.0)
        profit_factor = _optional_float(selected.get("profit_factor"))
        win_rate = _optional_float(selected.get("win_rate"))
        drawdown = _optional_float(selected.get("max_drawdown_eur"))
        validation_status = str(selected.get("validation_status") or "learning")

        checks = {
            "closed_trades": {
                "value": closed_trades,
                "minimum": self.config.min_closed_trades,
                "passed": closed_trades >= self.config.min_closed_trades,
            },
            "sample_count": {
                "value": sample_count,
                "minimum": self.config.min_sample_count,
                "passed": sample_count >= self.config.min_sample_count,
            },
            "net_pnl_eur": {
                "value": round(net_pnl, 6),
                "minimum": self.config.min_net_pnl_eur,
                "passed": net_pnl > self.config.min_net_pnl_eur,
            },
            "profit_factor": self._profit_factor_check(profit_factor, closed_trades),
            "win_rate": {
                "value": win_rate,
                "minimum": self.config.min_win_rate_pct,
                "passed": win_rate is not None and win_rate >= self.config.min_win_rate_pct,
            },
            "max_drawdown_eur": {
                "value": drawdown,
                "maximum": self.config.max_drawdown_eur,
                "passed": drawdown is None or drawdown <= self.config.max_drawdown_eur,
            },
        }
        if self.config.research_workflow_enabled:
            checks["research_validation_status"] = {
                "value": validation_status,
                "minimum": sorted(EXECUTION_READY_STATUSES),
                "passed": validation_status in EXECUTION_READY_STATUSES,
                "valid_status": validation_status in WORKFLOW_STATUSES,
            }
        failed = [name for name, check in checks.items() if not bool(check.get("passed"))]
        if failed:
            status = "learning" if "closed_trades" in failed or "sample_count" in failed else "blocked"
            return self._result(False, status, f"promotion_gate_failed:{','.join(failed)}", checks)
        return self._result(True, "passed", "promotion_gate_passed", checks)

    def _profit_factor_check(self, profit_factor: float | None, closed_trades: int) -> dict[str, Any]:
        if profit_factor is None:
            return {
                "value": None,
                "minimum": self.config.min_profit_factor,
                "no_loss_min_closed_trades": self.config.no_loss_min_closed_trades,
                "passed": closed_trades >= self.config.no_loss_min_closed_trades,
                "reason": "no_loss_sample_requires_more_closed_trades",
            }
        return {
            "value": profit_factor,
            "minimum": self.config.min_profit_factor,
            "passed": profit_factor >= self.config.min_profit_factor,
        }

    def _result(
        self,
        passed: bool,
        status: str,
        reason: str,
        checks: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {
            "enabled": self.config.enabled,
            "passed": bool(passed),
            "status": status,
            "reason": reason,
            "config": self.config.to_dict(),
            "checks": dict(checks),
            "live_enabled": False,
        }
