"""
ReconciliationManager — Full Async
MIGRATION P0: Replaces reconciliation.py (threading)

Uses asyncio tasks for periodic reconciliation.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Union

from .order_executor_async import OrderExecutorAsync, OrderStatus
from .reconciliation import Divergence

logger = logging.getLogger(__name__)


class ReconciliationManagerAsync:
    """Async reconciliation manager."""

    def __init__(
        self,
        order_executor: OrderExecutorAsync,
        instances: Union[Dict[str, Any], Callable[[], Dict[str, Any]]],
        check_interval: int = 3600,
    ) -> None:
        self.order_executor = order_executor
        # ARCH-06: accept either a static dict or a callable returning current dict
        self._get_instances: Callable[[], Dict[str, Any]] = (
            instances if callable(instances) else (lambda: instances)  # type: ignore[arg-type]
        )
        self.check_interval = check_interval

        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._count = 0
        self._last: Optional[datetime] = None

        logger.info("🔄 ReconciliationManagerAsync initialisé")

    async def reconcile_all(self) -> List[Divergence]:
        all_div: List[Divergence] = []
        logger.info("🔄 Réconciliation complète (async)...")
        # ARCH-06: use callable to get the current (dynamic) instances snapshot
        for inst_id, inst in self._get_instances().items():
            try:
                divs = await self._reconcile_instance(inst)
                all_div.extend(divs)
            except Exception as exc:
                logger.exception(f"❌ Erreur réconciliation {inst_id}: {exc}")
        self._count += 1
        self._last = datetime.now()
        if all_div:
            logger.warning(f"⚠️ {len(all_div)} divergence(s) trouvée(s)")
        else:
            logger.info("✅ Aucune divergence")
        return all_div

    async def _reconcile_instance(self, instance: Any) -> List[Divergence]:
        divs: List[Divergence] = []
        instance.recalculate_allocated_capital()

        local_open = [p for p in instance.get_positions_snapshot() if p.get("status") == "open"]

        for pos in local_open:
            txid = pos.get("txid")
            pos_id = pos.get("id")
            if not txid:
                divs.append(Divergence(
                    type="orphan_local", position_id=pos_id, kraken_txid=None,
                    details={"reason": "Position sans TXID"}, severity="critical",
                ))
                await instance.close_position(pos_id, pos.get("buy_price", 0))
                continue

            status = await self.order_executor.get_order_status(txid)
            if status and status.status == "closed":
                sold = await self._check_if_sold(txid, instance.config.symbol)
                if sold:
                    divs.append(Divergence(
                        type="orphan_local", position_id=pos_id, kraken_txid=txid,
                        details={"reason": "Vendu sur Kraken"}, severity="critical",
                    ))
                    sell_price = await self._get_avg_sell_price(txid, instance.config.symbol)
                    await instance.close_position(pos_id, sell_price)

        return divs

    async def _check_if_sold(self, buy_txid: str, symbol: str) -> bool:
        try:
            status = await self.order_executor.get_order_status(buy_txid)
            if not status or status.status != "closed":
                return False
            closed = await self.order_executor.get_closed_orders(
                start_time=int(time.time()) - 86400
            )
            for _, info in closed.items():
                descr = info.get("descr", {})
                if descr.get("type") == "sell" and descr.get("pair") == symbol:
                    vol = float(info.get("vol", 0))
                    if abs(vol - status.volume_exec) < 0.0001:
                        return True
            return False
        except Exception:
            return False

    async def _get_avg_sell_price(self, buy_txid: str, symbol: str) -> float:
        try:
            closed = await self.order_executor.get_closed_orders(
                start_time=int(time.time()) - 86400
            )
            for _, info in closed.items():
                if info.get("descr", {}).get("type") == "sell":
                    avg = float(info.get("avg_price", 0))
                    if avg > 0:
                        return avg
            return 0.0
        except Exception:
            return 0.0

    async def _loop(self) -> None:
        logger.info("🔄 Boucle réconciliation démarrée (async)")
        await self.reconcile_all()
        while self._running:
            try:
                await asyncio.sleep(self.check_interval)
                if self._running:
                    await self.reconcile_all()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception(f"❌ Erreur boucle réconciliation: {exc}")
                await asyncio.sleep(60)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("✅ ReconciliationManagerAsync démarré")

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("✅ ReconciliationManagerAsync arrêté")

    def get_stats(self) -> Dict[str, Any]:
        return {
            "reconciliation_count": self._count,
            "last_reconciliation": self._last.isoformat() if self._last else None,
            "check_interval": self.check_interval,
            "is_running": self._running,
        }
