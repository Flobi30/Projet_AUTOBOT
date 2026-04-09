from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass
class RegimeState:
    regime: str = "RANGE"
    confidence: float = 0.0
    stable_ticks: int = 0


class RegimeController:
    """Centralized market regime state machine with hysteresis."""

    def __init__(self, hysteresis_ticks: int = 3):
        self.hysteresis_ticks = max(1, int(hysteresis_ticks))
        self._state_by_symbol: Dict[str, RegimeState] = {}

    def classify(self, trend: str, volatility: float, drawdown: float) -> str:
        if drawdown >= 0.30:
            return "CRISIS"
        if volatility >= 0.06:
            return "HIGH_VOL"
        if trend in ("up", "down"):
            return "TREND"
        return "RANGE"

    def update(self, symbol: str, trend: str, volatility: float, drawdown: float) -> RegimeState:
        target = self.classify(trend, volatility, drawdown)
        state = self._state_by_symbol.setdefault(symbol, RegimeState())
        if state.regime == target:
            state.stable_ticks = min(state.stable_ticks + 1, 100)
            state.confidence = min(1.0, state.confidence + 0.1)
            return state

        # hysteresis before switching
        state.stable_ticks += 1
        if state.stable_ticks >= self.hysteresis_ticks:
            state.regime = target
            state.stable_ticks = 0
            state.confidence = 0.6
        else:
            state.confidence = max(0.0, state.confidence - 0.1)
        return state

    def module_policy(self, regime: str) -> Dict[str, bool]:
        if regime == "CRISIS":
            return {
                "enable_mean_reversion": False,
                "enable_ml": False,
                "enable_onchain": False,
            }
        if regime == "HIGH_VOL":
            return {
                "enable_mean_reversion": False,
                "enable_ml": True,
                "enable_onchain": True,
            }
        if regime == "TREND":
            return {
                "enable_mean_reversion": False,
                "enable_ml": True,
                "enable_onchain": True,
            }
        return {
            "enable_mean_reversion": True,
            "enable_ml": True,
            "enable_onchain": True,
        }

    def snapshot(self) -> Dict[str, Dict[str, float | str | int]]:
        return {
            sym: {
                "regime": st.regime,
                "confidence": st.confidence,
                "stable_ticks": st.stable_ticks,
            }
            for sym, st in self._state_by_symbol.items()
        }
