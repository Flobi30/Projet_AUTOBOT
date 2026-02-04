"""
Heartbeat Monitor for connection health monitoring.

Provides continuous monitoring of connection health with
automatic detection of connection loss and notification.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Callable, Optional, Awaitable
import logging

from .exceptions import HeartbeatTimeout
from .base import setup_json_logger


@dataclass
class HeartbeatConfig:
    """Configuration for heartbeat monitor."""
    interval: float = 10.0  # seconds between heartbeats
    timeout: float = 30.0  # seconds before considering connection lost
    max_missed: int = 3  # maximum missed heartbeats before alert


class HeartbeatMonitor:
    """
    Heartbeat monitor for tracking connection health.
    
    Monitors connection health by periodically checking a health function
    and tracking response times. Triggers callbacks when connection
    issues are detected.
    
    Features:
    - Configurable heartbeat interval and timeout
    - Async health check function support
    - Automatic reconnection triggering
    - Latency tracking
    - Connection loss detection
    
    Example:
        async def check_health():
            return await connector.health_check()
        
        monitor = HeartbeatMonitor(
            health_check=check_health,
            on_connection_lost=handle_disconnect,
            interval=10.0
        )
        
        await monitor.start()
    """
    
    def __init__(
        self,
        health_check: Callable[[], Awaitable[bool]],
        on_connection_lost: Optional[Callable[[], Awaitable[None]]] = None,
        on_connection_restored: Optional[Callable[[], Awaitable[None]]] = None,
        interval: float = 10.0,
        timeout: float = 30.0,
        max_missed: int = 3,
        config: Optional[HeartbeatConfig] = None
    ):
        """
        Initialize heartbeat monitor.
        
        Args:
            health_check: Async function that returns True if healthy
            on_connection_lost: Callback when connection is lost
            on_connection_restored: Callback when connection is restored
            interval: Seconds between heartbeat checks
            timeout: Seconds to wait for health check response
            max_missed: Maximum missed heartbeats before triggering lost
            config: Optional configuration object
        """
        if config:
            self._interval = config.interval
            self._timeout = config.timeout
            self._max_missed = config.max_missed
        else:
            self._interval = interval
            self._timeout = timeout
            self._max_missed = max_missed
        
        self._health_check = health_check
        self._on_connection_lost = on_connection_lost
        self._on_connection_restored = on_connection_restored
        
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_heartbeat: Optional[float] = None
        self._missed_count = 0
        self._is_healthy = True
        self._logger = setup_json_logger("HeartbeatMonitor")
        
        # Metrics
        self._total_checks = 0
        self._successful_checks = 0
        self._failed_checks = 0
        self._latencies: list[float] = []
    
    @property
    def is_running(self) -> bool:
        """Check if monitor is running."""
        return self._running
    
    @property
    def is_healthy(self) -> bool:
        """Check if connection is considered healthy."""
        return self._is_healthy
    
    @property
    def last_heartbeat(self) -> Optional[float]:
        """Get timestamp of last successful heartbeat."""
        return self._last_heartbeat
    
    @property
    def missed_count(self) -> int:
        """Get count of consecutive missed heartbeats."""
        return self._missed_count
    
    @property
    def time_since_heartbeat(self) -> Optional[float]:
        """Get seconds since last successful heartbeat."""
        if self._last_heartbeat is None:
            return None
        return time.monotonic() - self._last_heartbeat
    
    async def start(self) -> None:
        """Start the heartbeat monitor."""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        self._logger.info("Heartbeat monitor started", extra={
            "extra_data": {
                "interval": self._interval,
                "timeout": self._timeout,
                "max_missed": self._max_missed
            }
        })
    
    async def stop(self) -> None:
        """Stop the heartbeat monitor."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._logger.info("Heartbeat monitor stopped")
    
    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                await self._check_heartbeat()
                await asyncio.sleep(self._interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"Heartbeat monitor error: {e}")
                await asyncio.sleep(self._interval)
    
    async def _check_heartbeat(self) -> None:
        """Perform a single heartbeat check."""
        self._total_checks += 1
        start_time = time.monotonic()
        
        try:
            # Run health check with timeout
            is_healthy = await asyncio.wait_for(
                self._health_check(),
                timeout=self._timeout
            )
            
            latency_ms = (time.monotonic() - start_time) * 1000
            self._latencies.append(latency_ms)
            if len(self._latencies) > 100:
                self._latencies = self._latencies[-100:]
            
            if is_healthy:
                self._successful_checks += 1
                self._last_heartbeat = time.monotonic()
                self._missed_count = 0
                
                # Check if we're recovering from unhealthy state
                if not self._is_healthy:
                    self._is_healthy = True
                    self._logger.info("Connection restored", extra={
                        "extra_data": {"latency_ms": latency_ms}
                    })
                    if self._on_connection_restored:
                        await self._on_connection_restored()
                
                self._logger.debug("Heartbeat OK", extra={
                    "extra_data": {"latency_ms": latency_ms}
                })
            else:
                await self._handle_missed_heartbeat("Health check returned False")
                
        except asyncio.TimeoutError:
            await self._handle_missed_heartbeat("Health check timed out")
        except Exception as e:
            await self._handle_missed_heartbeat(f"Health check error: {e}")
    
    async def _handle_missed_heartbeat(self, reason: str) -> None:
        """Handle a missed heartbeat."""
        self._failed_checks += 1
        self._missed_count += 1
        
        self._logger.warning(f"Missed heartbeat: {reason}", extra={
            "extra_data": {
                "missed_count": self._missed_count,
                "max_missed": self._max_missed
            }
        })
        
        if self._missed_count >= self._max_missed and self._is_healthy:
            self._is_healthy = False
            self._logger.error("Connection lost - max missed heartbeats exceeded", extra={
                "extra_data": {
                    "missed_count": self._missed_count,
                    "last_heartbeat": self._last_heartbeat
                }
            })
            
            if self._on_connection_lost:
                await self._on_connection_lost()
    
    def record_activity(self) -> None:
        """
        Record activity to reset heartbeat timer.
        
        Call this when any successful communication occurs
        to prevent false connection loss detection.
        """
        self._last_heartbeat = time.monotonic()
        self._missed_count = 0
    
    def get_metrics(self) -> dict:
        """Get heartbeat monitor metrics."""
        avg_latency = sum(self._latencies) / len(self._latencies) if self._latencies else 0
        p95_latency = 0.0
        if self._latencies:
            sorted_latencies = sorted(self._latencies)
            idx = int(len(sorted_latencies) * 0.95)
            p95_latency = sorted_latencies[min(idx, len(sorted_latencies) - 1)]
        
        return {
            "is_running": self._running,
            "is_healthy": self._is_healthy,
            "missed_count": self._missed_count,
            "total_checks": self._total_checks,
            "successful_checks": self._successful_checks,
            "failed_checks": self._failed_checks,
            "avg_latency_ms": avg_latency,
            "p95_latency_ms": p95_latency,
            "time_since_heartbeat": self.time_since_heartbeat,
        }
    
    async def __aenter__(self) -> "HeartbeatMonitor":
        """Async context manager entry."""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.stop()
