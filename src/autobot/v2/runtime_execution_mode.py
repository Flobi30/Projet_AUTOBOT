"""Explicit, fail-closed execution-mode selection for the active runtime.

The research/shadow programme may consume public market data, but it must not
silently create a simulated wallet or an order-capable executor.  A future
paper activation therefore requires both an explicit override of observation
mode and every paper execution guard to be enabled deliberately.
"""

from __future__ import annotations

import os


_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_PAPER_EXECUTION_GUARDS = (
    "PAPER_EXECUTION_ADAPTER_ENABLED",
    "PAPER_EXECUTION_ROUTER_ENABLED",
    "PAPER_TEST_TRADING_ENABLED",
)


class ObservationOnlyExecutionComponentDisabled(RuntimeError):
    """Raised when legacy private-execution code is constructed in observation mode."""


def env_enabled(name: str, default: bool = False) -> bool:
    """Read one boolean environment flag without accepting ambiguous values."""

    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUE_VALUES


def paper_execution_authorized() -> bool:
    """Return true only for an intentionally enabled paper execution path."""

    return env_enabled("PAPER_TRADING") and all(env_enabled(name) for name in _PAPER_EXECUTION_GUARDS)


def observation_only_runtime() -> bool:
    """Return whether the running service must have no order-capable executor.

    ``AUTOBOT_OBSERVATION_ONLY_RUNTIME`` is an explicit deployment lock.  If
    it is true, it always wins.  A false value is not an execution
    authorization: a paper runtime still defaults to observation-only until
    all paper execution guards are explicitly enabled.
    """

    explicit = os.getenv("AUTOBOT_OBSERVATION_ONLY_RUNTIME")
    if explicit is not None and explicit.strip().lower() in _TRUE_VALUES:
        return True
    return env_enabled("PAPER_TRADING") and not paper_execution_authorized()


def reject_private_execution_component(component: str) -> None:
    """Fail before a direct Kraken executor can exist in observation mode.

    Public data collectors must use their dedicated public clients. A legacy
    executor has no legitimate purpose in the research/shadow deployment,
    even for a read request, because its construction enables a private API
    path outside the active runtime boundary.
    """

    if observation_only_runtime():
        normalized = str(component or "private execution component").strip()
        raise ObservationOnlyExecutionComponentDisabled(
            f"{normalized} is disabled in observation-only runtime"
        )
