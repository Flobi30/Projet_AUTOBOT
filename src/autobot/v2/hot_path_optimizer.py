"""
HotPathOptimizer — GC management and latency telemetry for the hot path.
P4: Hot/Cold Path Separation.

Purpose:
    Eliminate GC pauses and track per-tick latency on the critical path:
    WebSocket recv → parse → ring.write() → queue.put() → on_price_update()

GC strategy:
    CPython's GC runs automatically when the allocation threshold is exceeded.
    At high tick rates (10+ ticks/s × 2000 instances) a GC cycle can inject
    1–50 ms of latency without warning.  ``enter_hot_path()`` disables the
    collector for the lifetime of the hot-path component; ``force_gc()`` must
    be called periodically from the cold path (e.g. every 30 s) so memory is
    still reclaimed.

Latency tracking:
    Samples are stored in a pre-allocated ``array.array("q")`` circular buffer
    (signed 64-bit integers, nanoseconds).  No heap allocation occurs during
    ``start_tick()`` / ``record_tick()``.  ``stats`` sorts a copy of the
    sample array (cold path — allocation allowed).

Usage::

    optimizer = HotPathOptimizer()
    optimizer.enter_hot_path()          # disable GC globally

    # Per tick (hot path — zero allocation):
    t0 = optimizer.start_tick()
    process(data)
    optimizer.record_tick(t0)

    # From cold path (periodic):
    optimizer.force_gc()                # collect without re-enabling auto-GC

    optimizer.exit_hot_path()           # re-enable GC on shutdown

Module-level singleton::

    from .hot_path_optimizer import get_hot_path_optimizer
    opt = get_hot_path_optimizer()
"""

from __future__ import annotations

import array
import gc
import time
from typing import Dict

__all__ = ["HotPathOptimizer", "get_hot_path_optimizer"]

_DEFAULT_SAMPLES: int = 4096  # Must be power of 2


class HotPathOptimizer:
    """
    GC controller and nanosecond-resolution latency recorder for the hot path.

    All state is stored in ``__slots__`` for minimal attribute-lookup overhead.
    The latency sample buffer is a pre-allocated C array — no object creation
    inside ``start_tick()`` / ``record_tick()``.

    Thread safety:
        Designed for single-threaded asyncio.  ``start_tick`` / ``record_tick``
        must only be called from the event-loop thread.
    """

    __slots__ = (
        "_max_samples",
        "_mask",
        "_samples",
        "_write_idx",
        "_count",
        "_gc_was_enabled",
        "_active",
        "_tick_count",
        "_total_ns",
        "_max_ns",
    )

    def __init__(self, max_samples: int = _DEFAULT_SAMPLES) -> None:
        """
        Args:
            max_samples: Circular buffer size for latency samples.
                         Must be a power of 2.  Default: 4 096.
        """
        if max_samples & (max_samples - 1):
            raise ValueError(
                f"max_samples must be a power of 2, got {max_samples}"
            )
        self._max_samples: int = max_samples
        self._mask: int = max_samples - 1
        # Pre-allocate: signed 64-bit C array — zero heap pressure on hot path
        self._samples: array.array = array.array(
            "q", (0 for _ in range(max_samples))
        )
        self._write_idx: int = 0
        self._count: int = 0
        self._gc_was_enabled: bool = False
        self._active: bool = False
        self._tick_count: int = 0
        self._total_ns: int = 0
        self._max_ns: int = 0

    # ------------------------------------------------------------------
    # GC control
    # ------------------------------------------------------------------

    def enter_hot_path(self) -> None:
        """
        Disable CPython garbage collector.

        Call once at startup (e.g. from ``OrchestratorAsync.start()``).
        Subsequent calls are idempotent.
        """
        if not self._active:
            self._gc_was_enabled = gc.isenabled()
            gc.disable()
            self._active = True

    def exit_hot_path(self) -> None:
        """
        Run a final collection then restore the GC to its prior state.

        Call on shutdown (e.g. from ``OrchestratorAsync.stop()``).
        Idempotent.
        """
        if self._active:
            gc.collect()
            if self._gc_was_enabled:
                gc.enable()
            self._active = False

    def force_gc(self) -> int:
        """
        Trigger a GC collection *without* re-enabling automatic GC.

        Must be called periodically from the cold path so objects accumulated
        during GC-disabled operation are eventually reclaimed.

        Returns:
            Number of unreachable objects collected.
        """
        return gc.collect()

    # ------------------------------------------------------------------
    # Latency measurement — hot path (zero allocation)
    # ------------------------------------------------------------------

    @staticmethod
    def start_tick() -> int:
        """
        Return current time in nanoseconds.

        Uses ``time.perf_counter_ns()`` which has sub-microsecond resolution
        on Linux and macOS.  Call at the very start of each tick.
        """
        return time.perf_counter_ns()

    def record_tick(self, start_ns: int) -> int:
        """
        Compute elapsed time since *start_ns* and store the sample.

        O(1) — writes to pre-allocated C array, no heap allocation.

        Args:
            start_ns: Value returned by a prior :meth:`start_tick` call.

        Returns:
            Elapsed nanoseconds.
        """
        elapsed: int = time.perf_counter_ns() - start_ns
        self._samples[self._write_idx & self._mask] = elapsed
        self._write_idx += 1
        if self._count < self._max_samples:
            self._count += 1
        self._tick_count += 1
        self._total_ns += elapsed
        if elapsed > self._max_ns:
            self._max_ns = elapsed
        return elapsed

    # ------------------------------------------------------------------
    # Statistics — cold path (may allocate)
    # ------------------------------------------------------------------

    @property
    def stats(self) -> Dict[str, object]:
        """
        Return latency percentiles and GC state.

        Sorts a snapshot of the sample buffer — call from the cold path only.
        """
        n = self._count
        if n == 0:
            return {
                "tick_count": 0,
                "avg_ns": 0,
                "max_ns": 0,
                "p50_ns": 0,
                "p95_ns": 0,
                "p99_ns": 0,
                "gc_disabled": self._active,
            }
        # Cold path: copy + sort is fine here
        samples = sorted(self._samples[:n])
        avg = self._total_ns // self._tick_count if self._tick_count else 0
        return {
            "tick_count": self._tick_count,
            "avg_ns": avg,
            "max_ns": self._max_ns,
            "p50_ns": samples[int(n * 0.50)],
            "p95_ns": samples[int(n * 0.95)],
            "p99_ns": samples[int(n * 0.99)],
            "gc_disabled": self._active,
        }

    def reset_stats(self) -> None:
        """Reset all accumulated statistics.  Call from the cold path."""
        self._write_idx = 0
        self._count = 0
        self._tick_count = 0
        self._total_ns = 0
        self._max_ns = 0

    # ------------------------------------------------------------------
    # Repr
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"HotPathOptimizer("
            f"active={self._active}, "
            f"ticks={self._tick_count}, "
            f"max_ns={self._max_ns})"
        )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_singleton: HotPathOptimizer | None = None


def get_hot_path_optimizer(max_samples: int = _DEFAULT_SAMPLES) -> HotPathOptimizer:
    """
    Return the process-wide :class:`HotPathOptimizer` singleton.

    The first call creates the instance; subsequent calls return it unchanged
    (the *max_samples* argument is ignored after first call).
    """
    global _singleton
    if _singleton is None:
        _singleton = HotPathOptimizer(max_samples)
    return _singleton
