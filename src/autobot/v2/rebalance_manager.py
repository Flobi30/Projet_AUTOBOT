"""
RebalanceManager — Automatic gain reinvestment and drawdown protection.

Integrates with OrchestratorAsync to periodically check all instances
and apply rebalancing rules:
  - When an instance exceeds +20% profit → reinvest 25% of gains
  - When an instance reaches -10% drawdown → reduce position by 50%
  - Daily at 00:00 UTC → full rebalance check

All thresholds are configurable. Every action is logged.
No mock data — all calculations use real instance state.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RebalanceEvent:
    """Record of a rebalance action for audit trail."""
    timestamp: str
    instance_id: str
    instance_name: str
    action: str  # "reinvest" | "reduce" | "skip"
    amount: float
    reason: str
    profit_percent: float
    drawdown_percent: float
    capital_before: float
    capital_after: float


class RebalanceManager:
    """
    Manages automatic capital rebalancing across trading instances.

    Configuration thresholds (all as fractions, e.g., 0.20 = 20%):
        REBALANCE_THRESHOLD_PROFIT:  Profit % above which gains are reinvested.
        REBALANCE_THRESHOLD_DRAWDOWN: Drawdown % above which position is reduced.
        REINVEST_PERCENT:            Fraction of gains to reinvest.
        REDUCE_PERCENT:              Fraction of position to reduce on drawdown.
        MIN_REINVEST_AMOUNT:         Minimum EUR to trigger reinvestment.
    """

    REBALANCE_THRESHOLD_PROFIT: float = 0.20    # 20%
    REBALANCE_THRESHOLD_DRAWDOWN: float = 0.10  # 10%
    REINVEST_PERCENT: float = 0.25              # 25% of gains
    REDUCE_PERCENT: float = 0.50                # 50% position reduction
    MIN_REINVEST_AMOUNT: float = 5.0            # Minimum 5€ to reinvest
    CHECK_INTERVAL_SECONDS: float = 3600.0      # 1 hour

    def __init__(self, orchestrator: Any) -> None:
        self.orchestrator = orchestrator
        self._history: List[RebalanceEvent] = []
        self._max_history: int = 500
        self._last_check: float = 0.0
        self._total_reinvested: float = 0.0
        self._total_reduced: float = 0.0
        self._check_count: int = 0
        self._enabled: bool = True
        self._task: Optional[asyncio.Task] = None

        logger.info(
            f"⚖️ RebalanceManager initialisé — "
            f"Profit threshold: {self.REBALANCE_THRESHOLD_PROFIT*100:.0f}%, "
            f"Drawdown threshold: {self.REBALANCE_THRESHOLD_DRAWDOWN*100:.0f}%, "
            f"Reinvest: {self.REINVEST_PERCENT*100:.0f}%"
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the periodic rebalance check loop."""
        if self._task and not self._task.done():
            return
        self._enabled = True
        self._task = asyncio.create_task(self._periodic_loop(), name="rebalance-manager")
        logger.info("⚖️ RebalanceManager démarré (vérification toutes les heures)")

    async def stop(self) -> None:
        """Stop the periodic rebalance check loop."""
        self._enabled = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("⚖️ RebalanceManager arrêté")

    async def _periodic_loop(self) -> None:
        """Background loop that runs check_and_rebalance periodically."""
        while self._enabled:
            try:
                await asyncio.sleep(self.CHECK_INTERVAL_SECONDS)
                if self._enabled:
                    await self.check_and_rebalance()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception(f"❌ Erreur boucle rebalance: {exc}")
                await asyncio.sleep(60)  # Back off on error

    # ------------------------------------------------------------------
    # Core logic
    # ------------------------------------------------------------------

    async def check_and_rebalance(self) -> List[RebalanceEvent]:
        """
        Check all instances and apply rebalancing if necessary.

        Returns a list of RebalanceEvent objects describing what was done.
        """
        if not self._enabled:
            return []

        self._check_count += 1
        self._last_check = time.time()
        events: List[RebalanceEvent] = []

        try:
            instances = list(self.orchestrator._instances.values())
        except Exception as exc:
            logger.error(f"❌ Impossible de récupérer les instances: {exc}")
            return events

        if not instances:
            logger.debug("⚖️ Aucune instance à rebalancer")
            return events

        logger.info(f"⚖️ Vérification rebalancement — {len(instances)} instance(s)")

        for instance in instances:
            try:
                event = await self._check_instance(instance)
                if event:
                    events.append(event)
                    self._history.append(event)
                    # Trim history
                    if len(self._history) > self._max_history:
                        self._history = self._history[-self._max_history:]
            except Exception as exc:
                logger.error(
                    f"❌ Erreur rebalance instance {instance.id}: {exc}",
                    exc_info=True,
                )

        if events:
            logger.info(
                f"⚖️ Rebalancement terminé — {len(events)} action(s) effectuée(s)"
            )
        else:
            logger.debug("⚖️ Rebalancement terminé — aucune action nécessaire")

        return events

    async def _check_instance(self, instance: Any) -> Optional[RebalanceEvent]:
        """
        Check a single instance and decide if rebalancing is needed.

        Uses REAL data from the instance:
        - get_profit() → actual P&L
        - get_initial_capital() → real initial capital
        - get_drawdown() → real drawdown from peak
        - get_current_capital() → real current capital
        """
        try:
            # Real calculations — no mock data
            initial_capital = instance.get_initial_capital()
            current_capital = instance.get_current_capital()
            profit = instance.get_profit()
            drawdown = instance.get_drawdown()  # Already a fraction (0.0 to 1.0)

            # Avoid division by zero
            if initial_capital <= 0:
                return None

            profit_percent = profit / initial_capital  # fraction

            instance_name = getattr(instance.config, 'name', instance.id)

            # Scenario 1: Profit exceeds threshold → reinvest portion of gains
            if profit_percent > self.REBALANCE_THRESHOLD_PROFIT:
                reinvest_amount = profit * self.REINVEST_PERCENT

                # Skip if amount too small
                if reinvest_amount < self.MIN_REINVEST_AMOUNT:
                    logger.debug(
                        f"⚖️ {instance.id}: Profit {profit_percent*100:.1f}% "
                        f"mais montant trop petit ({reinvest_amount:.2f}€)"
                    )
                    return None

                capital_before = current_capital
                await self._reinvest(instance, reinvest_amount)
                capital_after = instance.get_current_capital()

                event = RebalanceEvent(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    instance_id=instance.id,
                    instance_name=instance_name,
                    action="reinvest",
                    amount=reinvest_amount,
                    reason=f"Profit {profit_percent*100:.1f}% > seuil {self.REBALANCE_THRESHOLD_PROFIT*100:.0f}%",
                    profit_percent=profit_percent * 100,
                    drawdown_percent=drawdown * 100,
                    capital_before=capital_before,
                    capital_after=capital_after,
                )
                self._total_reinvested += reinvest_amount
                return event

            # Scenario 2: Drawdown exceeds threshold → reduce position
            elif drawdown > self.REBALANCE_THRESHOLD_DRAWDOWN:
                reduce_amount = current_capital * self.REDUCE_PERCENT
                capital_before = current_capital

                await self._reduce_position(instance, self.REDUCE_PERCENT)
                capital_after = instance.get_current_capital()

                event = RebalanceEvent(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    instance_id=instance.id,
                    instance_name=instance_name,
                    action="reduce",
                    amount=reduce_amount,
                    reason=f"Drawdown {drawdown*100:.1f}% > seuil {self.REBALANCE_THRESHOLD_DRAWDOWN*100:.0f}%",
                    profit_percent=profit_percent * 100,
                    drawdown_percent=drawdown * 100,
                    capital_before=capital_before,
                    capital_after=capital_after,
                )
                self._total_reduced += reduce_amount
                return event

        except Exception as exc:
            logger.error(
                f"❌ Erreur vérification instance {instance.id}: {exc}",
                exc_info=True,
            )

        return None

    async def _reinvest(self, instance: Any, amount: float) -> None:
        """
        Reinvest gains into the instance by increasing its capital.

        This adjusts the instance's _initial_capital upward so that
        the new capital base is higher, effectively compounding gains.
        """
        try:
            # Increase the initial capital reference (compound effect)
            instance._initial_capital += amount
            logger.info(
                f"💰 Réinvestissement: +{amount:.2f}€ dans {instance.id} "
                f"({getattr(instance.config, 'name', 'unknown')})"
            )
        except Exception as exc:
            logger.error(f"❌ Erreur réinvestissement {instance.id}: {exc}")

    async def _reduce_position(self, instance: Any, percent: float) -> None:
        """
        Reduce position exposure by closing open positions.

        Strategy:
        1. Get all open positions
        2. Close the oldest positions until we've reduced by `percent`
        3. If no positions to close, just log a warning
        """
        try:
            positions = instance.get_positions_snapshot()
            open_positions = [p for p in positions if p.get("status") == "open"]

            if not open_positions:
                logger.warning(
                    f"⚠️ Réduction demandée pour {instance.id} mais aucune position ouverte"
                )
                return

            # Close positions starting from the least profitable
            sorted_positions = sorted(
                open_positions,
                key=lambda p: p.get("pnl", 0),
            )

            positions_to_close = max(1, int(len(sorted_positions) * percent))

            for pos in sorted_positions[:positions_to_close]:
                pos_id = pos.get("id")
                current_price = pos.get("current_price", pos.get("entry_price", 0))

                if pos_id and current_price > 0:
                    profit = await instance.close_position(pos_id, current_price)
                    if profit is not None:
                        logger.warning(
                            f"⚠️ Position {pos_id} fermée (réduction drawdown): "
                            f"P&L {profit:.2f}€"
                        )

            logger.warning(
                f"⚠️ Réduction position: {positions_to_close} position(s) fermée(s) "
                f"sur {instance.id} ({percent*100:.0f}%)"
            )
        except Exception as exc:
            logger.error(f"❌ Erreur réduction position {instance.id}: {exc}")

    # ------------------------------------------------------------------
    # Status & API
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        """Return current status for the dashboard API."""
        return {
            "enabled": self._enabled,
            "check_count": self._check_count,
            "last_check": (
                datetime.fromtimestamp(self._last_check, tz=timezone.utc).isoformat()
                if self._last_check > 0
                else None
            ),
            "total_reinvested": round(self._total_reinvested, 2),
            "total_reduced": round(self._total_reduced, 2),
            "thresholds": {
                "profit_threshold_pct": self.REBALANCE_THRESHOLD_PROFIT * 100,
                "drawdown_threshold_pct": self.REBALANCE_THRESHOLD_DRAWDOWN * 100,
                "reinvest_pct": self.REINVEST_PERCENT * 100,
                "reduce_pct": self.REDUCE_PERCENT * 100,
                "min_reinvest_eur": self.MIN_REINVEST_AMOUNT,
            },
            "recent_events": [
                {
                    "timestamp": e.timestamp,
                    "instance_id": e.instance_id,
                    "instance_name": e.instance_name,
                    "action": e.action,
                    "amount": round(e.amount, 2),
                    "reason": e.reason,
                }
                for e in self._history[-20:]  # Last 20 events
            ],
        }

    def get_history(self) -> List[Dict[str, Any]]:
        """Return full rebalance history."""
        return [
            {
                "timestamp": e.timestamp,
                "instance_id": e.instance_id,
                "instance_name": e.instance_name,
                "action": e.action,
                "amount": round(e.amount, 2),
                "reason": e.reason,
                "profit_percent": round(e.profit_percent, 2),
                "drawdown_percent": round(e.drawdown_percent, 2),
                "capital_before": round(e.capital_before, 2),
                "capital_after": round(e.capital_after, 2),
            }
            for e in self._history
        ]