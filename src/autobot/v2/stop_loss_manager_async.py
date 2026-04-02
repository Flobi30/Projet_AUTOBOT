"""
StopLossManager — Full Async
MIGRATION P0: Replaces stop_loss_manager.py (threading)

Uses asyncio tasks instead of threads for periodic monitoring.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple

from .order_executor_async import OrderExecutorAsync, OrderStatus

logger = logging.getLogger(__name__)


class StopLossManagerAsync:
    """Async stop-loss manager with periodic monitoring task."""

    def __init__(
        self,
        order_executor: OrderExecutorAsync,
        check_interval: int = 30,
    ) -> None:
        self.order_executor = order_executor
        self.check_interval = check_interval

        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None

        # {txid: position_id}
        self._monitored: Dict[str, str] = {}
        self._on_stop_loss_triggered: Optional[
            Callable[[str, OrderStatus], Coroutine[Any, Any, None]]
        ] = None

        logger.info("🛡️ StopLossManagerAsync initialisé")

    def register_stop_loss(self, txid: str, position_id: str) -> bool:
        self._monitored[txid] = position_id
        logger.info(f"🛡️ Stop-loss enregistré: {txid[:8]}... → {position_id}")
        return True

    def unregister_stop_loss(self, txid: str) -> bool:
        if txid in self._monitored:
            del self._monitored[txid]
            return True
        return False

    async def check_stop_loss(self, txid: str) -> Tuple[bool, Optional[OrderStatus]]:
        status = await self.order_executor.get_order_status(txid)
        if status is None:
            return False, None
        if status.status == "closed":
            logger.info(f"🚨 Stop-loss déclenché: {txid[:8]}...")
            return True, status
        return False, status

    async def reconcile_positions(self, positions: List[Any]) -> List[Tuple[str, OrderStatus]]:
        triggered = []
        for pos in positions:
            txid = pos.get("stop_loss_txid") if isinstance(pos, dict) else getattr(pos, "stop_loss_txid", None)
            pos_id = pos.get("id") if isinstance(pos, dict) else getattr(pos, "id", None)
            if not txid or not pos_id:
                continue
            was_triggered, status = await self.check_stop_loss(txid)
            if was_triggered and status:
                triggered.append((pos_id, status))
            else:
                self.register_stop_loss(txid, pos_id)
        return triggered

    async def _monitor_loop(self) -> None:
        logger.info("🛡️ Surveillance stop-loss démarrée (async)")
        while self._running:
            try:
                for txid, position_id in list(self._monitored.items()):
                    if not self._running:
                        break
                    try:
                        triggered, status = await self.check_stop_loss(txid)
                        if triggered and self._on_stop_loss_triggered and status:
                            await self._on_stop_loss_triggered(position_id, status)
                            self.unregister_stop_loss(txid)
                    except Exception as exc:
                        logger.exception(f"❌ Erreur check SL {txid[:8]}...: {exc}")
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception(f"❌ Erreur boucle SL: {exc}")
                await asyncio.sleep(5)
        logger.info("🛡️ Surveillance stop-loss arrêtée (async)")

    async def start(
        self,
        on_stop_loss_triggered: Optional[
            Callable[[str, OrderStatus], Coroutine[Any, Any, None]]
        ] = None,
    ) -> None:
        if self._running:
            return
        self._running = True
        self._on_stop_loss_triggered = on_stop_loss_triggered
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("✅ StopLossManagerAsync démarré")

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("✅ StopLossManagerAsync arrêté")

    def get_monitored_count(self) -> int:
        return len(self._monitored)
