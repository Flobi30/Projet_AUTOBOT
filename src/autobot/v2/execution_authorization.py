"""Shared fail-closed authorization for real exchange order mutations."""

from __future__ import annotations

import os


MUTATING_PRIVATE_METHODS = frozenset({"AddOrder", "CancelOrder"})
REAL_ORDER_MUTATION_BLOCKED = "REAL_ORDER_MUTATION_BLOCKED"
REAL_ORDER_MUTATION_BLOCKED_MESSAGE = (
    "Real order mutations require PAPER_TRADING=false, "
    "LIVE_TRADING_CONFIRMATION=true, "
    "STRATEGY_ROUTER_LIVE_ENABLED=true, "
    "AUTOBOT_REAL_ORDER_EXECUTION_ENABLED=true, and "
    "PREFLIGHT_ONLY=false"
)


def _env_true(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def real_order_mutation_authorized() -> bool:
    """Return whether a real exchange mutation has every explicit approval.

    This is the final executor-boundary defence for direct ``AddOrder`` and
    ``CancelOrder`` calls. It defaults to false and is intentionally stricter
    than startup attestation.
    """
    return (
        not _env_true("PAPER_TRADING")
        and _env_true("LIVE_TRADING_CONFIRMATION")
        and _env_true("STRATEGY_ROUTER_LIVE_ENABLED")
        and _env_true("AUTOBOT_REAL_ORDER_EXECUTION_ENABLED")
        and not _env_true("PREFLIGHT_ONLY")
    )


def real_order_mutation_blocked_response() -> dict:
    """Return a protocol-neutral blocked response without a network call."""
    return {
        "error": [f"{REAL_ORDER_MUTATION_BLOCKED}:{REAL_ORDER_MUTATION_BLOCKED_MESSAGE}"],
        "error_code": REAL_ORDER_MUTATION_BLOCKED,
    }
