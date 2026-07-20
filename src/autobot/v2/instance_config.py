"""Side-effect-free configuration contract for AUTOBOT instances."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(slots=True)
class InstanceConfig:
    name: str
    symbol: str
    strategy: str
    initial_capital: float
    leverage: int = 1
    tp_sl_config: dict[str, Any] = field(default_factory=dict)
    grid_config: Optional[dict[str, Any]] = None

