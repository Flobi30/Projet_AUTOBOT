"""
Order Queue — Full Async (asyncio.PriorityQueue)
MIGRATION P0: Replaces order_queue.py (threading.Queue + TokenBucket)

Uses asyncio.PriorityQueue for priority ordering.
Token bucket reimplemented without threading.Lock.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, IntEnum
from typing import Any, Callable, Coroutine, Dict, Optional

from .order_executor_async import OrderExecutorAsync, OrderSide

logger = logging.getLogger(__name__)


class OrderPriority(IntEnum):
    """Priority levels (lower = higher priority)."""
    EMERGENCY = 0
    ORDER = 1
    INFO = 2


class QueueOrderType(Enum):
    BUY = "buy"
    SELL = "sell"
    STOP_LOSS = "stop_loss"
    CANCEL = "cancel"


@dataclass(order=True)
class PrioritizedOrder:
    """Order with priority for PriorityQueue."""
    priority: int
    timestamp: float = field(compare=True, default_factory=time.monotonic)
    order_type: QueueOrderType = field(compare=False, default=QueueOrderType.BUY)
    symbol: str = field(compare=False, default="")
    volume: float = field(compare=False, default=0.0)
    price: Optional[float] = field(compare=False, default=None)
    stop_price: Optional[float] = field(compare=False, default=None)
    callback: Optional[Callable] = field(compare=False, default=None)


class AsyncTokenBucket:
    """Token bucket for rate limiting (no locks needed in async)."""

    def __init__(self, tokens_per_second: float, max_tokens: float) -> None:
        self.tokens_per_second = tokens_per_second
        self.max_tokens = max_tokens
        self.tokens = max_tokens
        self.last_update = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_update
        self.tokens = min(self.max_tokens, self.tokens + elapsed * self.tokens_per_second)
        self.last_update = now

    def consume(self, n: float = 1.0) -> bool:
        self._refill()
        if self.tokens >= n:
            self.tokens -= n
            return True
        return False

    async def wait_and_consume(self, n: float = 1.0) -> None:
        """Wait until enough tokens, then consume."""
        while True:
            self._refill()
            if self.tokens >= n:
                self.tokens -= n
                return
            needed = n - self.tokens
            wait = needed / self.tokens_per_second
            await asyncio.sleep(wait)


class OrderQueueAsync:
    """Async order queue with priority and rate limiting."""

    def __init__(
        self,
        order_executor: OrderExecutorAsync,
        max_rate: float = 1.0,
        max_burst: float = 3.0,
    ) -> None:
        self.order_executor = order_executor
        self.token_bucket = AsyncTokenBucket(max_rate, max_burst)
        self._queue: asyncio.PriorityQueue[PrioritizedOrder] = asyncio.PriorityQueue()
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._stats = {"processed": 0, "failed": 0}

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._process_loop())
        logger.info("✅ OrderQueueAsync démarrée")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("🛑 OrderQueueAsync arrêtée")

    async def submit(
        self,
        order_type: QueueOrderType,
        symbol: str,
        volume: float,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        priority: OrderPriority = OrderPriority.ORDER,
        callback: Optional[Callable] = None,
    ) -> None:
        order = PrioritizedOrder(
            priority=priority.value,
            order_type=order_type,
            symbol=symbol,
            volume=volume,
            price=price,
            stop_price=stop_price,
            callback=callback,
        )
        await self._queue.put(order)

    async def _process_loop(self) -> None:
        while self._running:
            try:
                order = await asyncio.wait_for(self._queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            await self.token_bucket.wait_and_consume(1.0)
            await self._execute_order(order)

    async def _execute_order(self, order: PrioritizedOrder) -> None:
        try:
            result = None
            if order.order_type == QueueOrderType.BUY:
                result = await self.order_executor.execute_market_order(
                    order.symbol, OrderSide.BUY, order.volume
                )
            elif order.order_type == QueueOrderType.SELL:
                result = await self.order_executor.execute_market_order(
                    order.symbol, OrderSide.SELL, order.volume
                )
            elif order.order_type == QueueOrderType.STOP_LOSS:
                result = await self.order_executor.execute_stop_loss_order(
                    order.symbol, OrderSide.SELL, order.volume, order.stop_price or 0
                )
            elif order.order_type == QueueOrderType.CANCEL:
                result = await self.order_executor.cancel_order(order.symbol)

            if result and getattr(result, "success", False):
                self._stats["processed"] += 1
            else:
                self._stats["failed"] += 1

            if order.callback:
                try:
                    if asyncio.iscoroutinefunction(order.callback):
                        await order.callback(result)
                    else:
                        order.callback(result)
                except Exception as exc:
                    logger.exception(f"❌ Erreur callback ordre: {exc}")
        except Exception as exc:
            logger.exception(f"❌ Erreur exécution ordre: {exc}")
            self._stats["failed"] += 1

    def get_stats(self) -> Dict[str, Any]:
        return {
            "processed": self._stats["processed"],
            "failed": self._stats["failed"],
            "queued": self._queue.qsize(),
        }
