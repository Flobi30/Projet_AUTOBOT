from __future__ import annotations

import asyncio
import logging
from time import perf_counter
from typing import Any, Dict

logger = logging.getLogger(__name__)


class SafetyGuard:
    def __init__(
        self,
        emergency_cycle_ms: float = 100.0,
        emergency_consecutive: int = 3,
        blocked_cooldown_s: float = 60.0,
    ) -> None:
        self.execution_times: Dict[str, float] = {}
        self.blocked_features: set[str] = set()
        self.emergency_mode = False
        self._blocked_until: Dict[str, float] = {}
        self._slow_cycles = 0
        self._emergency_cycle_ms = float(emergency_cycle_ms)
        self._emergency_consecutive = max(1, int(emergency_consecutive))
        self._blocked_cooldown_s = max(1.0, float(blocked_cooldown_s))

    def can_run(self, feature_name: str) -> bool:
        now = perf_counter()
        ts = self._blocked_until.get(feature_name, 0.0)
        if ts and now < ts:
            return False
        if feature_name in self.blocked_features and now >= ts:
            self.blocked_features.discard(feature_name)
            self._blocked_until.pop(feature_name, None)
        return True

    async def execute_with_timeout(
        self,
        feature_name: str,
        coro,
        timeout_ms: float,
        fallback_value: Any,
    ) -> Any:
        if not self.can_run(feature_name):
            return fallback_value
        t0 = perf_counter()
        try:
            value = await asyncio.wait_for(coro, timeout=max(0.001, timeout_ms / 1000.0))
            self.execution_times[feature_name] = (perf_counter() - t0) * 1000.0
            return value
        except Exception:
            self.execution_times[feature_name] = (perf_counter() - t0) * 1000.0
            self.blocked_features.add(feature_name)
            self._blocked_until[feature_name] = perf_counter() + self._blocked_cooldown_s
            logger.warning("SafetyGuard: feature '%s' timed out/failed, fallback applied", feature_name)
            return fallback_value

    def check_performance_budget(self, total_cycle_ms: float) -> bool:
        if float(total_cycle_ms) > self._emergency_cycle_ms:
            self._slow_cycles += 1
        else:
            self._slow_cycles = 0
        if self._slow_cycles >= self._emergency_consecutive:
            self.emergency_mode = True
            return False
        return True

    def reset_emergency(self) -> None:
        self.emergency_mode = False
        self._slow_cycles = 0

    def get_emergency_status(self) -> Dict[str, Any]:
        return {
            "emergency_mode": self.emergency_mode,
            "blocked_features": sorted(self.blocked_features),
            "execution_times_ms": dict(self.execution_times),
        }
