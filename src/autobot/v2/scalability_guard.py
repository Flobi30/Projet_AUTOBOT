"""Scalability guard state machine (Lot 3).

Additive scaling gate only:
- ALLOW_SCALE_UP
- FREEZE
- FORCE_REDUCE
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List


class ScalingState(str, Enum):
    ALLOW_SCALE_UP = "ALLOW_SCALE_UP"
    FREEZE = "FREEZE"
    FORCE_REDUCE = "FORCE_REDUCE"


@dataclass(frozen=True)
class GuardInput:
    cpu_pct: float = 0.0
    memory_pct: float = 0.0
    ws_connected: bool = True
    ws_stale_seconds: float = 0.0
    ws_total_lag: int = 0
    execution_failure_rate: float = 0.0
    reconciliation_mismatch_ratio: float = 0.0
    kill_switch_tripped: bool = False
    pf_degraded: bool = False
    validation_degraded: bool = False


@dataclass(frozen=True)
class GuardThresholds:
    cpu_pct_max: float = 85.0
    memory_pct_max: float = 85.0
    ws_stale_seconds_max: float = 45.0
    ws_lag_max: int = 5000
    execution_failure_rate_max: float = 0.25
    reconciliation_mismatch_max: float = 0.05


@dataclass
class GuardDecision:
    state: ScalingState
    reasons: List[str] = field(default_factory=list)
    signals: Dict[str, float | bool] = field(default_factory=dict)


class ScalabilityGuard:
    def __init__(self, thresholds: GuardThresholds) -> None:
        self.thresholds = thresholds
        self._state = ScalingState.ALLOW_SCALE_UP
        self._last_decision = GuardDecision(state=self._state)

    @property
    def state(self) -> ScalingState:
        return self._state

    @property
    def last_decision(self) -> GuardDecision:
        return self._last_decision

    def evaluate(self, signal: GuardInput) -> GuardDecision:
        reasons: List[str] = []

        # hard vetoes
        if signal.kill_switch_tripped:
            reasons.append("kill_switch_tripped")
        if signal.reconciliation_mismatch_ratio >= self.thresholds.reconciliation_mismatch_max:
            reasons.append("reconciliation_mismatch")

        if reasons:
            state = ScalingState.FORCE_REDUCE
        else:
            freeze_signals = [
                (signal.cpu_pct >= self.thresholds.cpu_pct_max, "cpu_pressure"),
                (signal.memory_pct >= self.thresholds.memory_pct_max, "memory_pressure"),
                (not signal.ws_connected, "websocket_disconnected"),
                (signal.ws_stale_seconds >= self.thresholds.ws_stale_seconds_max, "websocket_stale"),
                (signal.ws_total_lag >= self.thresholds.ws_lag_max, "websocket_lag"),
                (
                    signal.execution_failure_rate >= self.thresholds.execution_failure_rate_max,
                    "execution_failure_rate",
                ),
                (signal.pf_degraded, "pf_degraded"),
                (signal.validation_degraded, "validation_degraded"),
            ]
            reasons = [name for active, name in freeze_signals if active]
            state = ScalingState.FREEZE if reasons else ScalingState.ALLOW_SCALE_UP

        self._state = state
        self._last_decision = GuardDecision(
            state=state,
            reasons=reasons,
            signals={
                "cpu_pct": signal.cpu_pct,
                "memory_pct": signal.memory_pct,
                "ws_connected": signal.ws_connected,
                "ws_stale_seconds": signal.ws_stale_seconds,
                "ws_total_lag": signal.ws_total_lag,
                "execution_failure_rate": signal.execution_failure_rate,
                "reconciliation_mismatch_ratio": signal.reconciliation_mismatch_ratio,
                "kill_switch_tripped": signal.kill_switch_tripped,
                "pf_degraded": signal.pf_degraded,
                "validation_degraded": signal.validation_degraded,
            },
        )
        return self._last_decision

    def allow_scale_up(self) -> bool:
        return self._state == ScalingState.ALLOW_SCALE_UP
