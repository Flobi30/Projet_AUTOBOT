"""Bounded persistence for strategy-governance abstentions.

This module records decisions that happen before SignalHandlerAsync without
changing the decision itself. It never creates orders or grants live access.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class GovernanceDecisionEvent:
    symbol: str
    instance_id: str | None
    strategy: str | None
    engine: str
    event_type: str
    event_status: str
    reason: str
    payload: dict[str, Any]


class GovernanceDecisionObserver:
    """Emit only changed decisions or periodic bounded reminders."""

    def __init__(self, *, reminder_interval_seconds: float = 300.0) -> None:
        self.reminder_interval_seconds = max(30.0, float(reminder_interval_seconds))
        self._last_emitted: dict[str, tuple[tuple[Any, ...], float]] = {}

    def collect(
        self,
        snapshot: Mapping[str, Any],
        *,
        instance_by_symbol: Mapping[str, Mapping[str, Any]],
        now: float | None = None,
    ) -> tuple[GovernanceDecisionEvent, ...]:
        current_time = time.monotonic() if now is None else float(now)
        rows = snapshot.get("symbols") if isinstance(snapshot, Mapping) else None
        if not isinstance(rows, list):
            return ()

        events: list[GovernanceDecisionEvent] = []
        for raw_row in rows:
            if not isinstance(raw_row, Mapping):
                continue
            row = dict(raw_row)
            event = self._build_event(row, instance_by_symbol=instance_by_symbol)
            if event is None:
                continue
            fingerprint = (
                event.event_type,
                event.event_status,
                event.reason,
                event.engine,
                event.payload.get("execution_mode"),
                event.payload.get("router_score"),
            )
            previous = self._last_emitted.get(event.symbol)
            if previous is not None:
                previous_fingerprint, previous_time = previous
                if fingerprint == previous_fingerprint and current_time - previous_time < self.reminder_interval_seconds:
                    continue
            self._last_emitted[event.symbol] = (fingerprint, current_time)
            events.append(event)
        return tuple(events)

    @staticmethod
    def event_kwargs(event: GovernanceDecisionEvent) -> dict[str, Any]:
        return {
            "event_id": f"govobs_{uuid.uuid4().hex}",
            "instance_id": event.instance_id,
            "symbol": event.symbol,
            "strategy": event.strategy,
            "engine": event.engine,
            "event_type": event.event_type,
            "event_status": event.event_status,
            "reason": event.reason,
            "source": "strategy_governance_observer",
            "payload": event.payload,
        }

    @staticmethod
    def _build_event(
        row: Mapping[str, Any],
        *,
        instance_by_symbol: Mapping[str, Mapping[str, Any]],
    ) -> GovernanceDecisionEvent | None:
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol:
            return None
        decision = str(row.get("decision") or "observe")
        governance_status = str(row.get("governance_status") or "observe")
        selected_engine = str(row.get("selected_engine") or "no_trade")
        execution_mode = str(row.get("execution_mode") or "observe_only")
        reasons = row.get("reasons") if isinstance(row.get("reasons"), list) else []
        reason = str(row.get("reason") or (reasons[0] if reasons else "governance_observe"))
        blocked = bool(row.get("block_new_entries")) or governance_status == "blocked"
        no_trade = selected_engine == "no_trade" or decision in {"no_trade", "abstain"}
        if not blocked and not no_trade:
            return None

        event_type = "no_trade" if no_trade else "governance_block"
        event_status = "abstain" if no_trade else "blocked"
        instance = instance_by_symbol.get(symbol, {})
        payload = {
            "decision": decision,
            "execution_mode": execution_mode,
            "selected_engine": selected_engine,
            "selected_variant": row.get("selected_variant"),
            "router_score": row.get("router_score"),
            "opportunity_score": row.get("opportunity_score"),
            "opportunity_status": row.get("opportunity_status"),
            "opportunity_reason": row.get("opportunity_reason"),
            "router_action": row.get("router_action"),
            "router_reason": row.get("router_reason"),
            "governance_status": governance_status,
            "block_new_entries": bool(row.get("block_new_entries")),
            "official_execution_engine": row.get("official_execution_engine"),
            "reconciliation_verdict": row.get("reconciliation_verdict"),
            "live_promotion_allowed": False,
        }
        return GovernanceDecisionEvent(
            symbol=symbol,
            instance_id=str(instance.get("id") or instance.get("instance_id") or "") or None,
            strategy=str(instance.get("strategy") or "") or None,
            engine=selected_engine,
            event_type=event_type,
            event_status=event_status,
            reason=reason,
            payload=payload,
        )
