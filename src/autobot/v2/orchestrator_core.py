from __future__ import annotations

from typing import Optional

from .instance_async import TradingInstanceAsync
from .orchestrator import InstanceConfig


class OrchestratorCore:
    """Core instance lifecycle facade."""

    def __init__(self, orchestrator: object) -> None:
        self._o = orchestrator

    async def create_instance(self, config: InstanceConfig) -> Optional[TradingInstanceAsync]:
        return await self._o._create_instance_impl(config)

    async def remove_instance(self, instance_id: str) -> bool:
        return await self._o._remove_instance_impl(instance_id)

    async def create_instance_auto(
        self,
        parent_instance_id: Optional[str] = None,
        initial_capital: float = 0.0,
    ) -> Optional[TradingInstanceAsync]:
        return await self._o._create_instance_auto_impl(
            parent_instance_id=parent_instance_id,
            initial_capital=initial_capital,
        )

    async def check_spin_off(self, parent: TradingInstanceAsync) -> Optional[TradingInstanceAsync]:
        return await self._o._check_spin_off_impl(parent)
