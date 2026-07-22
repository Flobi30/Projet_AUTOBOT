"""Fail-closed retirement boundary for the synchronous AUTOBOT runtime.

``main_async.py`` and ``OrchestratorAsync`` are the only supported runtime
entrypoints.  The threaded ``Orchestrator`` / ``TradingInstance`` pair remains
importable because legacy type annotations and historical tooling still refer
to it, but it must never initialise a websocket, persistence store or Kraken
execution component.
"""

from __future__ import annotations


class LegacySynchronousRuntimeRetired(RuntimeError):
    """Raised before the archived synchronous runtime can perform I/O."""


def reject_legacy_synchronous_runtime(component: str) -> None:
    """Fail closed before a legacy synchronous component initialises.

    There is deliberately no environment override.  Historical replays belong
    in the isolated research adapters, while production observation runtime is
    exclusively asynchronous and already protected by the current safety
    gates.
    """

    normalized_component = str(component or "legacy synchronous runtime").strip()
    raise LegacySynchronousRuntimeRetired(
        f"{normalized_component} is retired_from_execution; "
        "use autobot.v2.main_async / OrchestratorAsync instead"
    )
