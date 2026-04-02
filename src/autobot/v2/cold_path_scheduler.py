"""
ColdPathScheduler — Fire-and-forget async task runner for cold-path work.
P4: Hot/Cold Path Separation.

Purpose:
    Ensure that non-latency-critical operations (SQLite persistence, verbose
    logging, periodic risk checks, GC triggers, analytics) are never awaited
    on the hot path.

    All cold-path calls go through ``schedule()`` which wraps the coroutine in
    ``asyncio.create_task()``.  The hot path returns immediately; the task is
    executed on the next event-loop iteration.

Design invariants:
    - ``schedule(coro)`` is O(1) and never awaits — safe to call from hot path.
    - Errors in cold-path tasks are caught and counted; they must NOT propagate
      back to the hot path.
    - ``stop()`` cancels all pending periodic tasks and drains active one-shots.
    - One-shot task list is pruned periodically to avoid unbounded growth.

Usage::

    scheduler = ColdPathScheduler()
    await scheduler.start()

    # Fire-and-forget from hot path (non-blocking):
    scheduler.schedule(instance.save_state())

    # Periodic GC every 30 s:
    scheduler.schedule_periodic(hot_optimizer.force_gc, interval=30.0,
                                 name="gc-collect")

    await scheduler.stop()

Module-level singleton::

    from .cold_path_scheduler import get_cold_path_scheduler
    scheduler = get_cold_path_scheduler()
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional

__all__ = ["ColdPathScheduler", "get_cold_path_scheduler"]

logger = logging.getLogger(__name__)

# Prune the one-shot list when it exceeds this size (keeps only active tasks).
_ONESHOT_PRUNE_THRESHOLD: int = 256


class ColdPathScheduler:
    """
    Async scheduler for cold-path (non-latency-critical) work.

    One-shot tasks:
        ``schedule(coro)`` wraps *coro* in ``asyncio.create_task()`` and
        returns immediately.  The task runs asynchronously; errors are caught
        and logged.

    Periodic tasks:
        ``schedule_periodic(fn, interval, name)`` spawns a background task
        that calls *fn()* every *interval* seconds.  *fn* may be synchronous
        or async.

    Thread safety:
        Single-threaded asyncio.  All public methods must be called from the
        same event loop.
    """

    def __init__(self) -> None:
        # Periodic task registry: name → Task
        self._periodic_tasks: Dict[str, asyncio.Task] = {}  # type: ignore[type-arg]
        # Live one-shot tasks (kept so stop() can cancel stragglers)
        self._oneshot_tasks: List[asyncio.Task] = []  # type: ignore[type-arg]
        self._running: bool = False
        # Approximate counters — no lock needed (single-threaded asyncio)
        self._scheduled: int = 0
        self._errors: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Mark the scheduler as running.  Idempotent."""
        self._running = True
        logger.debug("❄️ ColdPathScheduler démarré")

    async def stop(self) -> None:
        """
        Cancel all periodic tasks and wait for active one-shot tasks.

        One-shot tasks that are still running are cancelled; callers should
        flush any critical state (e.g. ``save_state``) before calling ``stop``.
        """
        self._running = False

        # Cancel periodic tasks
        for name, task in list(self._periodic_tasks.items()):
            if not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
        self._periodic_tasks.clear()

        # Cancel still-running one-shot tasks
        active = [t for t in self._oneshot_tasks if not t.done()]
        for task in active:
            task.cancel()
        if active:
            await asyncio.gather(*active, return_exceptions=True)
        self._oneshot_tasks.clear()

        logger.debug(
            f"❄️ ColdPathScheduler arrêté "
            f"(total_scheduled={self._scheduled}, errors={self._errors})"
        )

    # ------------------------------------------------------------------
    # One-shot fire-and-forget
    # ------------------------------------------------------------------

    def schedule(
        self,
        coro: Awaitable[Any],
        name: Optional[str] = None,
    ) -> "asyncio.Task[None]":
        """
        Schedule *coro* as a fire-and-forget ``asyncio.Task``.

        Returns immediately — the coroutine runs on the next event-loop
        iteration.  Any exception is caught, logged, and counted; it does
        **not** propagate.

        Args:
            coro:  Coroutine / awaitable to schedule.
            name:  Optional task name (visible in asyncio debug output).

        Returns:
            The created :class:`asyncio.Task`.
        """
        task: asyncio.Task[None] = asyncio.create_task(
            self._run_oneshot(coro),
            name=name or "cold-oneshot",
        )
        self._oneshot_tasks.append(task)
        # Prune completed tasks to bound list growth
        if len(self._oneshot_tasks) > _ONESHOT_PRUNE_THRESHOLD:
            self._oneshot_tasks = [t for t in self._oneshot_tasks if not t.done()]
        self._scheduled += 1
        return task

    async def _run_oneshot(self, coro: Awaitable[Any]) -> None:
        """Run *coro*, catch and log any exception."""
        try:
            await coro
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._errors += 1
            logger.error("❄️ Cold-path task error: %s", exc, exc_info=True)

    # ------------------------------------------------------------------
    # Periodic tasks
    # ------------------------------------------------------------------

    def schedule_periodic(
        self,
        fn: Callable[[], Any],
        interval: float,
        name: str,
    ) -> "asyncio.Task[None]":
        """
        Run ``fn()`` every *interval* seconds as a background task.

        *fn* may be a plain function (sync) or an async function; both are
        handled.  If a periodic task with *name* is already running it is
        first cancelled and replaced.

        The first invocation of *fn* is delayed by *interval* seconds so that
        the hot path is not affected at startup.

        Args:
            fn:       Callable invoked every *interval* seconds.
            interval: Seconds between invocations (wall-clock delay).
            name:     Unique human-readable identifier for this task.

        Returns:
            The created :class:`asyncio.Task`.
        """
        # Replace existing task with same name
        existing = self._periodic_tasks.pop(name, None)
        if existing and not existing.done():
            existing.cancel()

        task: asyncio.Task[None] = asyncio.create_task(
            self._periodic_loop(fn, interval, name),
            name=f"cold-periodic-{name}",
        )
        self._periodic_tasks[name] = task
        logger.debug(
            "❄️ Tâche périodique enregistrée: %s (interval=%.1fs)", name, interval
        )
        return task

    async def _periodic_loop(
        self,
        fn: Callable[[], Any],
        interval: float,
        name: str,
    ) -> None:
        """Core loop: sleep *interval* seconds then call *fn()*."""
        logger.debug("❄️ Démarrage tâche périodique: %s", name)
        try:
            while self._running:
                await asyncio.sleep(interval)
                if not self._running:
                    break
                try:
                    result = fn()
                    # Support both sync and async callables
                    if asyncio.iscoroutine(result):
                        await result
                    self._scheduled += 1
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self._errors += 1
                    logger.error(
                        "❄️ Erreur tâche périodique '%s': %s", name, exc,
                        exc_info=True,
                    )
        except asyncio.CancelledError:
            logger.debug("❄️ Tâche périodique annulée: %s", name)
            raise

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def schedule_gc(
        self,
        optimizer: Any,
        interval: float = 30.0,
    ) -> "asyncio.Task[None]":
        """
        Register a periodic GC collection via *optimizer.force_gc*.

        This is the recommended way to reclaim memory while the hot path
        keeps auto-GC disabled.

        Args:
            optimizer: :class:`~hot_path_optimizer.HotPathOptimizer` instance.
            interval:  Seconds between GC cycles.  Default: 30 s.

        Returns:
            The periodic :class:`asyncio.Task`.
        """
        return self.schedule_periodic(optimizer.force_gc, interval, "gc-collect")

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    @property
    def stats(self) -> Dict[str, object]:
        """Return a diagnostic snapshot (safe to call from any context)."""
        active_oneshots = sum(1 for t in self._oneshot_tasks if not t.done())
        return {
            "running": self._running,
            "periodic_tasks": len(self._periodic_tasks),
            "periodic_names": sorted(self._periodic_tasks.keys()),
            "oneshot_active": active_oneshots,
            "total_scheduled": self._scheduled,
            "total_errors": self._errors,
        }

    def __repr__(self) -> str:
        return (
            f"ColdPathScheduler("
            f"running={self._running}, "
            f"periodic={list(self._periodic_tasks)}, "
            f"scheduled={self._scheduled})"
        )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_singleton: ColdPathScheduler | None = None


def get_cold_path_scheduler() -> ColdPathScheduler:
    """
    Return the process-wide :class:`ColdPathScheduler` singleton.

    The first call creates the instance; subsequent calls return it unchanged.
    """
    global _singleton
    if _singleton is None:
        _singleton = ColdPathScheduler()
    return _singleton
