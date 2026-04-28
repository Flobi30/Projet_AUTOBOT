from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable, Dict, Optional

from .global_kill_switch import GlobalKillSwitchStore

logger = logging.getLogger(__name__)


@dataclass
class KillSwitchEvent:
    rule: str
    reason: str
    timestamp: str


class KillSwitch:
    """Centralized kill-switch with deterministic trigger rules."""

    def __init__(
        self,
        on_trigger: Optional[Callable[[KillSwitchEvent], Awaitable[None]]] = None,
        max_api_failures: int = 10,
        max_nonce_errors: int = 3,
        global_store: Optional[GlobalKillSwitchStore] = None,
    ) -> None:
        self._on_trigger = on_trigger
        self._tripped = False
        self._api_failures = 0
        self._nonce_errors = 0
        self._last_balance_ts: Optional[float] = None
        self._partial_started_at: Dict[str, float] = {}
        self._max_api_failures = max_api_failures
        self._max_nonce_errors = max_nonce_errors
        self._last_event: Optional[KillSwitchEvent] = None
        self._global_store = global_store or GlobalKillSwitchStore()

    @property
    def tripped(self) -> bool:
        return self._tripped

    @property
    def last_event(self) -> Optional[KillSwitchEvent]:
        return self._last_event

    async def trigger(self, rule: str, reason: str) -> None:
        if self._tripped:
            return
        self._tripped = True
        event = KillSwitchEvent(rule=rule, reason=reason, timestamp=datetime.now(timezone.utc).isoformat())
        self._last_event = event
        self._global_store.trip(rule, reason)
        logger.critical("🛑 KILL SWITCH TRIGGERED [%s] %s", rule, reason)
        if self._on_trigger:
            await self._on_trigger(event)

    def is_globally_tripped(self) -> bool:
        return self._global_store.get().tripped

    def acknowledge_recovery(self, operator_id: str) -> None:
        """Clear local and persisted kill-switch state after operator review."""
        self._tripped = False
        self._api_failures = 0
        self._nonce_errors = 0
        self._partial_started_at.clear()
        self._last_event = None
        self._global_store.acknowledge_recovery(operator_id)

    async def record_api_failure(self, error_message: str) -> None:
        if self._tripped:
            return
        self._api_failures += 1
        if "nonce" in error_message.lower():
            self._nonce_errors += 1
        if self._api_failures >= self._max_api_failures:
            await self.trigger("api_failures", f"{self._api_failures} consecutive API failures")
        if self._nonce_errors >= self._max_nonce_errors:
            await self.trigger("invalid_nonce_storm", f"{self._nonce_errors} nonce errors")

    def record_api_success(self) -> None:
        self._api_failures = 0

    def record_balance_freshness(self, now_ts: float) -> None:
        self._last_balance_ts = now_ts

    async def check_balance_staleness(self, now_ts: float, max_stale_s: float = 30.0) -> None:
        if self._tripped:
            return
        if self._last_balance_ts is None:
            return
        if now_ts - self._last_balance_ts > max_stale_s:
            await self.trigger("stale_balance", f"balance stale for {now_ts - self._last_balance_ts:.1f}s")

    def mark_partial(self, client_order_id: str, now_ts: float) -> None:
        self._partial_started_at.setdefault(client_order_id, now_ts)

    def clear_partial(self, client_order_id: str) -> None:
        self._partial_started_at.pop(client_order_id, None)

    async def check_partial_stuck(self, now_ts: float, max_partial_age_s: float = 180.0) -> None:
        if self._tripped:
            return
        for oid, ts in list(self._partial_started_at.items()):
            if now_ts - ts > max_partial_age_s:
                await self.trigger("partial_fill_stuck", f"order {oid} stuck partial for {now_ts - ts:.1f}s")
                return
