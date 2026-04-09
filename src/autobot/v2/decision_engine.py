from __future__ import annotations

from typing import Any, Dict, List, Optional


class DecisionEngine:
    """Facade extracting decision-related flows from OrchestratorAsync."""

    def __init__(self, orchestrator: object) -> None:
        self._o = orchestrator

    async def evaluate_signal(self, instance: object) -> bool:
        return await self._o._evaluate_signal(instance)

    def select_instances_for_cycle(self) -> List[object]:
        return self._o._select_instances_for_cycle()

    def resolve_conflict(self, actions: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not actions:
            return None
        return max(actions, key=lambda item: int(self._o.decision_policy.get(item.get("action", ""), 0)))

    def get_consensus(self, trend: str) -> Dict[str, Any]:
        regime = self._o._map_regime(trend)
        ensemble = self._o.strategy_ensemble.get_signal(regime)
        return {
            "direction": ensemble.direction,
            "score": float(ensemble.score),
            "regime": str(regime),
        }
