"""Canonical persisted order statuses and fail-closed transition rules."""

from __future__ import annotations

from typing import Optional


TERMINAL_ORDER_STATUSES = frozenset({"FILLED", "CANCELED", "REJECTED", "EXPIRED"})

# ``CANCELLED`` occurs in external APIs and older AUTOBOT records. New
# persisted runtime states use the single canonical ``CANCELED`` spelling.
_STATUS_ALIASES = {
    "CANCELLED": "CANCELED",
}

_ALLOWED_TRANSITIONS = {
    "NEW": frozenset({"SENT", "CANCELED", "REJECTED"}),
    "SENT": frozenset({"ACK", "CANCELED", "REJECTED", "EXPIRED", "UNKNOWN"}),
    "ACK": frozenset({"PARTIAL", "FILLED", "CANCELED", "REJECTED", "EXPIRED", "UNKNOWN"}),
    "PARTIAL": frozenset({"PARTIAL", "FILLED", "CANCELED", "UNKNOWN"}),
    "UNKNOWN": frozenset({"ACK", "PARTIAL", "FILLED", "CANCELED", "REJECTED", "EXPIRED"}),
}


def normalize_order_status(value: object) -> Optional[str]:
    """Return a canonical status or ``None`` for an unsupported value."""

    if not isinstance(value, str):
        return None
    status = value.strip().upper()
    if not status:
        return None
    status = _STATUS_ALIASES.get(status, status)
    if status in TERMINAL_ORDER_STATUSES or status in _ALLOWED_TRANSITIONS:
        return status
    return None


def is_allowed_order_transition(from_status: object, to_status: object) -> bool:
    """Return whether a canonical state transition is safe to persist.

    Retrying an already-persisted state is idempotent. The only deliberate
    non-terminal self-transition is ``PARTIAL -> PARTIAL`` to retain a later
    fill update while the order remains open.
    """

    normalized_from = normalize_order_status(from_status)
    normalized_to = normalize_order_status(to_status)
    if normalized_from is None or normalized_to is None:
        return False
    if normalized_from == normalized_to:
        return normalized_from in TERMINAL_ORDER_STATUSES or normalized_from == "PARTIAL"
    if normalized_from in TERMINAL_ORDER_STATUSES:
        return False
    return normalized_to in _ALLOWED_TRANSITIONS[normalized_from]

