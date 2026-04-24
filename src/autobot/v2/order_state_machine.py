from __future__ import annotations

import uuid
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from .persistence import StatePersistence, get_persistence


TERMINAL_STATES = {"FILLED", "CANCELED", "REJECTED", "EXPIRED"}


@dataclass
class OrderLifecycleRecord:
    client_order_id: str
    status: str
    userref: int
    exchange_order_id: Optional[str] = None


class PersistedOrderStateMachine:
    """Persisted order lifecycle with idempotency + crash recovery support."""

    def __init__(self, persistence: Optional[StatePersistence] = None):
        self._persistence = persistence or get_persistence()

    async def new_order(
        self,
        instance_id: str,
        symbol: str,
        side: str,
        order_type: str,
        requested_qty: float,
        decision_id: Optional[str] = None,
        signal_id: Optional[str] = None,
        client_order_id: Optional[str] = None,
        userref: Optional[int] = None,
    ) -> OrderLifecycleRecord:
        oid = client_order_id or f"ord_{uuid.uuid4().hex}"
        uref = userref or (time.time_ns() % 2147483647)
        await self._persistence.upsert_order(
            client_order_id=oid,
            instance_id=instance_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            requested_qty=requested_qty,
            status="NEW",
            userref=uref,
            decision_id=decision_id,
            signal_id=signal_id,
        )
        return OrderLifecycleRecord(client_order_id=oid, status="NEW", userref=uref)

    async def transition(self, client_order_id: str, to_status: str, reason: str, source: str = "runtime", **kwargs: Any) -> bool:
        return await self._persistence.transition_order_state(
            client_order_id=client_order_id,
            to_status=to_status,
            reason=reason,
            source=source,
            **kwargs,
        )

    async def get(self, client_order_id: str) -> Optional[Dict[str, Any]]:
        return await self._persistence.get_order(client_order_id)

    async def recover_non_terminal(self) -> list[Dict[str, Any]]:
        return await self._persistence.get_non_terminal_orders()

    async def is_duplicate_active(self, symbol: str, side: str) -> bool:
        for row in await self.recover_non_terminal():
            if row.get("symbol") == symbol and row.get("side") == side:
                return True
        return False
