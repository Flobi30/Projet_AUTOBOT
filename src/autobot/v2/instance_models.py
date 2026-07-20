"""Shared instance-domain models with no execution or persistence side effects."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class InstanceStatus(Enum):
    """Lifecycle state shared by synchronous legacy and async instances."""

    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class LeverageLevel(Enum):
    """Legacy leverage enum retained as a passive compatibility model."""

    X1 = 1
    X2 = 2
    X3 = 3


@dataclass(slots=True)
class Trade:
    id: str
    side: str
    price: float
    volume: float
    timestamp: datetime
    profit: Optional[float] = None


@dataclass(slots=True)
class Position:
    id: str
    buy_price: float
    volume: float
    sell_price: Optional[float] = None
    status: str = "open"
    open_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    close_time: Optional[datetime] = None
    profit: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    stop_loss_txid: Optional[str] = None
    stop_loss_triggered: bool = False
    buy_txid: Optional[str] = None
    sell_txid: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None

