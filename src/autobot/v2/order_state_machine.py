from __future__ import annotations

import uuid
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from .persistence import StatePersistence, get_persistence
from .strategy_runtime_policy import canonical_order_append_block_reason
from .order_lifecycle import TERMINAL_ORDER_STATUSES, normalize_order_status


TERMINAL_STATES = TERMINAL_ORDER_STATUSES


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
        strategy_id: str,
        decision_id: Optional[str] = None,
        signal_id: Optional[str] = None,
        client_order_id: Optional[str] = None,
        userref: Optional[int] = None,
    ) -> OrderLifecycleRecord:
        block_reason = canonical_order_append_block_reason(
            strategy_id,
            decision_id=decision_id,
            signal_id=signal_id,
        )
        if block_reason is not None:
            raise ValueError(f"{block_reason} for a persisted order")
        normalized_strategy_id = str(strategy_id).strip()
        oid = client_order_id or f"ord_{uuid.uuid4().hex}"
        uref = userref or (time.time_ns() % 2147483647)
        persisted = await self._persistence.upsert_order(
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
            strategy_id=normalized_strategy_id,
        )
        if not persisted:
            raise RuntimeError("persisted order creation was rejected")
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

    async def recover_to_terminal(
        self,
        client_order_id: str,
        terminal_status: str,
        reason: str,
        **kwargs: Any,
    ) -> bool:
        """Replay the minimum safe lifecycle before a recovered terminal state.

        Recovery can discover a fill after the runtime crashed while the local
        order was still `NEW`, `SENT` or `UNKNOWN`. It must not skip the
        canonical state graph merely because the exchange is ahead of the
        local ledger.
        """

        target = normalize_order_status(terminal_status)
        if target not in TERMINAL_STATES:
            return False
        row = await self.get(client_order_id)
        current = normalize_order_status((row or {}).get("status"))
        if current is None:
            return False
        if current in TERMINAL_STATES:
            return current == target

        if current == "NEW" and target == "EXPIRED":
            if not await self.transition(client_order_id, "SENT", "recovery_submission_inferred", **kwargs):
                return False
            current = "SENT"
        elif target == "FILLED":
            if current == "NEW":
                if not await self.transition(client_order_id, "SENT", "recovery_submission_inferred", **kwargs):
                    return False
                current = "SENT"
            if current in {"SENT", "UNKNOWN"}:
                if not await self.transition(client_order_id, "ACK", "recovered_exchange_ack", **kwargs):
                    return False
                current = "ACK"
        elif current == "PARTIAL" and target in {"REJECTED", "EXPIRED"}:
            if not await self.transition(client_order_id, "UNKNOWN", "recovery_terminal_state_ambiguous", **kwargs):
                return False

        return await self.transition(client_order_id, target, reason, **kwargs)

    async def recover_non_terminal(self) -> list[Dict[str, Any]]:
        return await self._persistence.get_non_terminal_orders()

    async def is_duplicate_active(self, symbol: str, side: str) -> bool:
        for row in await self.recover_non_terminal():
            if row.get("symbol") == symbol and row.get("side") == side:
                return True
        return False
