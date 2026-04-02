"""
OS-level tuning for AUTOBOT V2 Async — P5.

Implements four layers of optimisation:

1. **TCP socket options** — applied per WebSocket connection:
   - ``TCP_NODELAY``: disable Nagle's algorithm (reduces RTT by up to 40 ms on LAN).
   - ``SO_BUSY_POLL``: kernel busy-poll on socket receive (Linux ≥ 4.5, ~50 µs window).
   - ``TCP_QUICKACK``: immediate ACK transmission (Linux-only).

2. **CPU affinity pinning** — via ``os.sched_setaffinity()``:
   Binds the process to a dedicated set of cores so the hot path is never
   pre-empted by unrelated tasks.  Degrades gracefully if the OS or permissions
   do not support it.

3. **Real-time scheduling** — via ``SCHED_FIFO``:
   Opt-in; raises process priority above normal interactive workloads.
   Requires ``root`` or ``CAP_SYS_NICE``.  Silently skipped otherwise.

4. **Auto-detection** — all optimisations are best-effort:
   - Root status detected via ``os.getuid()``.
   - Syscall availability detected via ``hasattr`` / ``getattr``.
   - Failures are logged at WARNING/DEBUG; the process never crashes.

Usage::

    tuner = OSTuner()

    # At startup (CPU + scheduling):
    result = tuner.apply_all(cpu_cores={0, 1})
    print(result.summary())

    # Per WebSocket connection (TCP options):
    ws = await websockets.connect(url, ...)
    tuner.tune_websocket(ws)
"""

from __future__ import annotations

import logging
import os
import socket
import sys
from dataclasses import dataclass, field
from typing import Any, Set

logger = logging.getLogger(__name__)

# Linux-specific SO_BUSY_POLL numeric value (fallback when not in socket module)
_SO_BUSY_POLL_LINUX = 46

# Default busy-poll window in microseconds
_BUSY_POLL_US = 50


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


@dataclass
class TuningResult:
    """Captures which OS tuning options were applied, skipped, or failed."""

    applied: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)

    def summary(self) -> str:
        parts: list[str] = []
        if self.applied:
            parts.append(f"applied=[{', '.join(self.applied)}]")
        if self.skipped:
            parts.append(f"skipped=[{', '.join(self.skipped)}]")
        if self.failed:
            parts.append(f"failed=[{', '.join(self.failed)}]")
        return "  ".join(parts) if parts else "nothing changed"


# ---------------------------------------------------------------------------
# Main tuner
# ---------------------------------------------------------------------------


class OSTuner:
    """
    Best-effort OS-level tuner.

    All public methods are idempotent and never raise — failures are logged.
    """

    # ------------------------------------------------------------------
    # Capability detection
    # ------------------------------------------------------------------

    @staticmethod
    def is_root() -> bool:
        """Return True if the process is running as root (UID 0)."""
        try:
            return os.getuid() == 0
        except AttributeError:
            # Windows — os.getuid() not available
            return False

    @staticmethod
    def is_linux() -> bool:
        return sys.platform.startswith("linux")

    @staticmethod
    def has_sched_setaffinity() -> bool:
        return hasattr(os, "sched_setaffinity")

    @staticmethod
    def has_sched_fifo() -> bool:
        return hasattr(os, "SCHED_FIFO") and hasattr(os, "sched_setscheduler")

    # ------------------------------------------------------------------
    # TCP socket tuning
    # ------------------------------------------------------------------

    def apply_tcp_socket_options(self, sock: socket.socket) -> list[str]:
        """
        Apply low-latency TCP options to *sock*.

        Returns the list of option names that were successfully applied.

        Options applied:
        - ``TCP_NODELAY`` — disable Nagle (always attempted on TCP sockets)
        - ``SO_BUSY_POLL`` — kernel busy-poll window of 50 µs (Linux ≥ 4.5)
        - ``TCP_QUICKACK`` — immediate ACK (Linux-only)
        """
        applied: list[str] = []

        # TCP_NODELAY — universally available on TCP sockets
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            applied.append("TCP_NODELAY")
            logger.debug("TCP_NODELAY enabled on socket fd=%d", sock.fileno())
        except OSError as exc:
            logger.warning("TCP_NODELAY failed (fd=%d): %s", sock.fileno(), exc)

        # SO_BUSY_POLL — Linux 4.5+ only
        if self.is_linux():
            busy_poll_opt = getattr(socket, "SO_BUSY_POLL", _SO_BUSY_POLL_LINUX)
            try:
                sock.setsockopt(socket.SOL_SOCKET, busy_poll_opt, _BUSY_POLL_US)
                applied.append(f"SO_BUSY_POLL({_BUSY_POLL_US}µs)")
                logger.debug(
                    "SO_BUSY_POLL=%dµs enabled on socket fd=%d",
                    _BUSY_POLL_US,
                    sock.fileno(),
                )
            except OSError as exc:
                logger.debug(
                    "SO_BUSY_POLL not available (fd=%d, kernel <4.5?): %s",
                    sock.fileno(),
                    exc,
                )

        # TCP_QUICKACK — Linux-only
        quickack = getattr(socket, "TCP_QUICKACK", None)
        if quickack is not None and self.is_linux():
            try:
                sock.setsockopt(socket.IPPROTO_TCP, quickack, 1)
                applied.append("TCP_QUICKACK")
                logger.debug("TCP_QUICKACK enabled on socket fd=%d", sock.fileno())
            except OSError as exc:
                logger.debug(
                    "TCP_QUICKACK failed (fd=%d): %s", sock.fileno(), exc
                )

        return applied

    def tune_websocket(self, ws: Any) -> list[str]:
        """
        Extract the underlying TCP socket from a *websockets* connection and tune it.

        Works with ``websockets.WebSocketClientProtocol`` (v10+) which exposes
        ``ws.transport`` — an asyncio ``Transport``.

        Returns the list of option names applied, or an empty list on failure.
        """
        try:
            transport = getattr(ws, "transport", None)
            if transport is None:
                logger.debug(
                    "tune_websocket: ws.transport is None — skipping TCP tuning"
                )
                return []

            sock: socket.socket | None = transport.get_extra_info("socket")
            if sock is None:
                logger.debug(
                    "tune_websocket: transport has no 'socket' info — skipping"
                )
                return []

            applied = self.apply_tcp_socket_options(sock)
            if applied:
                logger.info(
                    "WebSocket TCP options applied: %s", ", ".join(applied)
                )
            return applied
        except Exception as exc:
            logger.warning("tune_websocket: unexpected error: %s", exc)
            return []

    # ------------------------------------------------------------------
    # CPU affinity
    # ------------------------------------------------------------------

    def apply_cpu_pinning(self, cores: Set[int]) -> bool:
        """
        Pin the current process to *cores* via ``os.sched_setaffinity()``.

        Returns True on success.
        """
        if not self.has_sched_setaffinity():
            logger.info(
                "CPU pinning: os.sched_setaffinity not available (non-Linux?)"
            )
            return False

        if not cores:
            logger.warning("CPU pinning: empty core set — skipped")
            return False

        try:
            os.sched_setaffinity(0, cores)
            logger.info(
                "CPU pinning: process bound to cores %s", sorted(cores)
            )
            return True
        except PermissionError:
            logger.warning(
                "CPU pinning: insufficient permissions (need root or CAP_SYS_NICE)"
            )
            return False
        except OSError as exc:
            logger.warning("CPU pinning failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Real-time scheduling
    # ------------------------------------------------------------------

    def apply_rt_scheduling(self, priority: int = 10) -> bool:
        """
        Apply ``SCHED_FIFO`` real-time scheduling with *priority*.

        Priority range: 1 (lowest RT) – 99 (highest RT).
        Requires root or ``CAP_SYS_NICE``.

        Returns True on success.
        """
        if not self.has_sched_fifo():
            logger.info(
                "RT scheduling: SCHED_FIFO not available (non-Linux?)"
            )
            return False

        if not 1 <= priority <= 99:
            logger.warning(
                "RT scheduling: priority %d out of range [1,99] — skipped", priority
            )
            return False

        try:
            param = os.sched_param(priority)
            os.sched_setscheduler(0, os.SCHED_FIFO, param)
            logger.info(
                "RT scheduling: SCHED_FIFO priority=%d applied", priority
            )
            return True
        except PermissionError:
            logger.warning(
                "RT scheduling: insufficient permissions (need root or CAP_SYS_NICE)"
            )
            return False
        except OSError as exc:
            logger.warning("RT scheduling failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # apply_all — startup-time optimisations
    # ------------------------------------------------------------------

    def apply_all(
        self,
        cpu_cores: Set[int] | None = None,
        rt_priority: int = 10,
        enable_rt_scheduling: bool = False,
    ) -> TuningResult:
        """
        Apply all startup-time OS optimisations and return a :class:`TuningResult`.

        TCP socket options are **not** applied here — call :meth:`tune_websocket`
        on each connection after ``await websockets.connect(...)``.

        Args:
            cpu_cores: Set of CPU core indices to pin the process to.
                       ``None`` or empty set → CPU pinning skipped.
            rt_priority: ``SCHED_FIFO`` priority (1–99, default 10).
            enable_rt_scheduling: If True, attempt ``SCHED_FIFO``.
                                   Default is False (requires root / CAP_SYS_NICE).
        """
        result = TuningResult()
        root = self.is_root()

        logger.info(
            "OS Tuning starting — platform=%s  root=%s",
            sys.platform,
            root,
        )

        # -- CPU pinning -------------------------------------------------------
        if cpu_cores:
            if self.apply_cpu_pinning(cpu_cores):
                result.applied.append(f"cpu_pinning(cores={sorted(cpu_cores)})")
            else:
                result.skipped.append("cpu_pinning")
        else:
            result.skipped.append("cpu_pinning(no cores specified)")

        # -- Real-time scheduling ----------------------------------------------
        if enable_rt_scheduling:
            if self.apply_rt_scheduling(rt_priority):
                result.applied.append(f"sched_fifo(priority={rt_priority})")
            else:
                result.skipped.append(f"sched_fifo(priority={rt_priority})")
        else:
            result.skipped.append("sched_fifo(disabled by caller)")

        logger.info("OS Tuning complete: %s", result.summary())
        return result


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_tuner: OSTuner | None = None


def get_os_tuner() -> OSTuner:
    """Return the global :class:`OSTuner` singleton."""
    global _tuner
    if _tuner is None:
        _tuner = OSTuner()
    return _tuner
