"""
Signal Handler — Full Async
MIGRATION P0: Replaces signal_handler.py

Connects strategy signals to async order execution.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Optional

from .strategies import TradingSignal, SignalType
from .order_executor_async import OrderExecutorAsync, OrderSide
from .validator import ValidatorEngine, ValidationStatus, create_default_validator_engine

logger = logging.getLogger(__name__)


class SignalHandlerAsync:
    """Async signal handler — receives signals, validates, executes orders."""

    def __init__(
        self,
        instance: Any,
        order_executor: Optional[OrderExecutorAsync] = None,
    ) -> None:
        self.instance = instance
        self.order_executor = order_executor
        self.validator = create_default_validator_engine()
        self._last_signal_time: Optional[datetime] = None
        self._cooldown_seconds = 5
        self._setup_signal_callback()
        logger.info(f"📡 SignalHandlerAsync initialisé pour {instance.id}")

    def _setup_signal_callback(self) -> None:
        if self.instance._strategy:
            self.instance._strategy.set_signal_callback(self._on_signal_sync)

    def _on_signal_sync(self, signal: TradingSignal) -> None:
        """Sync bridge: strategies emit signals synchronously, we schedule async work."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._on_signal(signal))
        except RuntimeError:
            logger.error("❌ Pas de loop asyncio — signal perdu")

    async def _on_signal(self, signal: TradingSignal) -> None:
        """Async signal handler."""
        logger.info(f"📡 Signal: {signal.type.value.upper()} {signal.symbol} @ {signal.price:.2f}")

        if self._last_signal_time:
            elapsed = (datetime.now() - self._last_signal_time).total_seconds()
            if elapsed < self._cooldown_seconds:
                logger.warning(f"⏱️ Signal ignoré (cooldown): {elapsed:.1f}s")
                return

        try:
            if signal.type == SignalType.BUY:
                await self._execute_buy(signal)
            elif signal.type in (SignalType.SELL, SignalType.CLOSE):
                await self._execute_sell(signal)
            self._last_signal_time = datetime.now()
        except Exception as exc:
            logger.exception(f"❌ Erreur exécution signal: {exc}")

    async def _execute_buy(self, signal: TradingSignal) -> None:
        logger.info(f"🛒 Exécution ACHAT {signal.symbol}")

        available = self.instance.get_available_capital()
        context = {
            "available_capital": available,
            "signal_price": signal.price,
            "instance_status": self.instance.status.value,
            "open_positions_count": len([
                p for p in self.instance.get_positions_snapshot() if p.get("status") == "open"
            ]),
            "max_positions": getattr(self.instance.config, "max_positions", 10),
        }

        validation = self.validator.validate("open_position", context)
        if validation.status == ValidationStatus.RED:
            logger.error(f"❌ Signal BUY rejeté: {validation.message}")
            return

        if self.order_executor is None:
            logger.error("❌ OrderExecutor non configuré")
            return

        volume = signal.volume if signal.volume > 0 else (available * 0.10) / signal.price
        volume = round(volume, 6)
        if volume <= 0:
            return

        symbol = self._convert_symbol(signal.symbol)
        result = await self.order_executor.execute_market_order(symbol, OrderSide.BUY, volume)

        if not result.success:
            logger.error(f"❌ Échec ordre Kraken: {result.error}")
            return

        executed_price = result.executed_price or signal.price
        executed_volume = result.executed_volume or volume

        # Stop-loss
        stop_price = executed_price * 0.95
        sl_result = await self.order_executor.execute_stop_loss_order(
            symbol, OrderSide.SELL, executed_volume, stop_price
        )
        sl_txid = sl_result.txid if sl_result.success else None

        position = await self.instance.open_position(
            price=executed_price,
            volume=executed_volume,
            stop_loss=stop_price,
            stop_loss_txid=sl_txid,
            buy_txid=result.txid,
        )

        if position:
            logger.info(f"✅ Position créée: {position.id}")

    async def _execute_sell(self, signal: TradingSignal) -> None:
        logger.info(f"💰 Exécution VENTE {signal.symbol}")

        if self.order_executor is None:
            logger.error("❌ OrderExecutor non configuré")
            return

        positions = self.instance.get_positions_snapshot()
        open_positions = [p for p in positions if p.get("status") == "open"]
        if not open_positions:
            return

        close_all = signal.volume == -1 or signal.metadata.get("close_all", False)
        to_close = open_positions if close_all else [open_positions[-1]]

        symbol = self._convert_symbol(signal.symbol)
        for pos in to_close:
            pos_id = pos.get("id")
            vol = pos.get("volume", 0)
            if not pos_id or vol <= 0:
                continue

            sl_txid = pos.get("stop_loss_txid")
            if sl_txid:
                await self.order_executor.cancel_order(sl_txid)

            result = await self.order_executor.execute_market_order(symbol, OrderSide.SELL, vol)
            if result.success:
                price = result.executed_price or signal.price
                await self.instance.close_position(pos_id, price, sell_txid=result.txid)
            else:
                logger.error(f"❌ Échec vente: {result.error}")

    @staticmethod
    def _convert_symbol(symbol: str) -> str:
        mapping = {
            "BTC/EUR": "XXBTZEUR",
            "ETH/EUR": "XETHZEUR",
            "BTC/USD": "XXBTZUSD",
            "ETH/USD": "XETHZUSD",
        }
        return mapping.get(symbol, symbol.replace("/", ""))
