"""
Signal Handler — Full Async
MIGRATION P0: Replaces signal_handler.py

Connects strategy signals to async order execution.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
import hashlib
from datetime import datetime, timezone
from typing import Any, Optional

from .strategies import TradingSignal, SignalType
from .order_executor_async import OrderExecutorAsync, OrderSide
from .validator import ValidatorEngine, ValidationStatus, create_default_validator_engine
from .order_state_machine import PersistedOrderStateMachine
from .kill_switch import KillSwitch
from .reconciliation_strict import StrictReconciliation

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
        self._osm = PersistedOrderStateMachine()
        self._kill_switch = KillSwitch(on_trigger=self._on_kill_switch_triggered)
        self._reconciler = StrictReconciliation()
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
        if self._kill_switch.tripped or self._kill_switch.is_globally_tripped():
            logger.error("🛑 Kill switch actif — signal ignoré")
            return
        logger.info(f"📡 Signal: {signal.type.value.upper()} {signal.symbol} @ {signal.price:.2f}")

        if self._last_signal_time:
            elapsed = (datetime.now(timezone.utc) - self._last_signal_time).total_seconds()
            if elapsed < self._cooldown_seconds:
                logger.warning(f"⏱️ Signal ignoré (cooldown): {elapsed:.1f}s")
                return

        try:
            if signal.type == SignalType.BUY:
                await self._execute_buy(signal)
            elif signal.type in (SignalType.SELL, SignalType.CLOSE):
                await self._execute_sell(signal)
            self._last_signal_time = datetime.now(timezone.utc)
        except Exception as exc:
            logger.exception(f"❌ Erreur exécution signal: {exc}")

    async def _execute_buy(self, signal: TradingSignal) -> None:
        logger.info(f"🛒 Exécution ACHAT {signal.symbol}")
        if self._osm.is_duplicate_active(self._convert_symbol(signal.symbol), "buy"):
            logger.warning("🔁 Ordre BUY dupliqué bloqué (idempotency)")
            return

        available = self.instance.get_available_capital()
        order_value = signal.volume * signal.price if signal.volume > 0 else (available * 0.10)
        context = {
            # Align with open_position_validator contract
            "balance": available,
            "order_value": order_value,
            "open_positions": len([
                p for p in self.instance.get_positions_snapshot() if p.get("status") == "open"
            ]),
            "price": signal.price,
            "instance_status": self.instance.status.value,
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
        decision_id = f"dec_{uuid.uuid4().hex}"
        signal_id = f"sig_{uuid.uuid4().hex}"
        rec = self._osm.new_order(
            instance_id=self.instance.id,
            symbol=symbol,
            side="buy",
            order_type="market",
            requested_qty=volume,
            decision_id=decision_id,
            signal_id=signal_id,
        )
        self._osm.transition(rec.client_order_id, "SENT", "submitted_to_exchange")
        result = await self.order_executor.execute_market_order(symbol, OrderSide.BUY, volume)

        if not result.success:
            logger.error(f"❌ Échec ordre Kraken: {result.error}")
            self._osm.transition(
                rec.client_order_id,
                "REJECTED",
                "exchange_error",
                retries_delta=1,
                last_error_message=result.error,
            )
            await self._kill_switch.record_api_failure(result.error or "unknown")
            return
        self._kill_switch.record_api_success()
        self._osm.transition(
            rec.client_order_id,
            "ACK",
            "exchange_ack",
            exchange_order_id=result.txid,
            payload=result.raw_response or {},
        )
        if result.executed_volume and result.executed_volume < volume:
            self._osm.transition(
                rec.client_order_id,
                "PARTIAL",
                "partial_fill",
                exchange_order_id=result.txid,
                filled_qty=result.executed_volume,
                avg_fill_price=result.executed_price,
            )
            self._kill_switch.mark_partial(rec.client_order_id, time.time())
        else:
            self._osm.transition(
                rec.client_order_id,
                "FILLED",
                "full_fill",
                exchange_order_id=result.txid,
                filled_qty=result.executed_volume or volume,
                avg_fill_price=result.executed_price,
            )
            self._kill_switch.clear_partial(rec.client_order_id)

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
            # Immutable audit event
            config_hash = hashlib.sha256(
                str(vars(self.instance.config)).encode("utf-8")
            ).hexdigest()
            self.instance._persistence.append_audit_event(
                event_id=f"evt_{uuid.uuid4().hex}",
                event_type="ORDER_BUY_FILLED",
                decision_id=decision_id,
                signal_id=signal_id,
                client_order_id=rec.client_order_id,
                exchange_order_id=result.txid,
                instance_id=self.instance.id,
                config_hash=config_hash,
                risk_snapshot={
                    "available_capital": available,
                    "max_positions": getattr(self.instance.config, "max_positions", 10),
                },
                fees=result.fees,
                order_from_status="SENT",
                order_to_status="FILLED",
                exchange_raw_normalized=result.raw_response or {},
            )
            await self._post_trade_reconcile()

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
            result = await self.order_executor.execute_market_order(symbol, OrderSide.SELL, vol)
            if result.success:
                price = result.executed_price or signal.price
                await self.instance.close_position(pos_id, price, sell_txid=result.txid)
                if sl_txid:
                    await self.order_executor.cancel_order(sl_txid)
                await self._post_trade_reconcile()
            else:
                logger.error(f"❌ Échec vente: {result.error}")
                await self._kill_switch.record_api_failure(result.error or "sell failed")

    async def _post_trade_reconcile(self) -> None:
        """Compare local vs exchange balance snapshots and trigger kill switch on critical drift."""
        if self.order_executor is None:
            return
        exchange_balance = await self.order_executor.get_balance()
        if exchange_balance:
            self._kill_switch.record_balance_freshness(time.time())
        local_total = self.instance.get_current_capital()
        exchange_total = float(exchange_balance.get("ZEUR", 0.0))
        divergences = self._reconciler.compare_balances(local_total, exchange_total)
        # Deeper parity: fees / realized / unrealized PnL aggregates
        tb = await self.order_executor.get_trade_balance("EUR")
        exchange_metrics = {
            "realized_pnl": float(tb.get("n", 0.0) if isinstance(tb.get("n"), (int, float)) else 0.0),
            "unrealized_pnl": float(tb.get("u", 0.0) if isinstance(tb.get("u"), (int, float)) else 0.0),
            "fees": float(tb.get("c", 0.0) if isinstance(tb.get("c"), (int, float)) else 0.0),
        }
        local_metrics = {
            "realized_pnl": float(self.instance.get_profit()),
            "unrealized_pnl": 0.0,  # TODO: derive mark-to-market from open positions
            "fees": 0.0,  # TODO: persist/aggregate actual exchange fees in dedicated table
        }
        divergences.extend(self._reconciler.compare_fills_fees_pnl(local_metrics, exchange_metrics))
        if self._reconciler.should_kill_switch(divergences):
            await self._kill_switch.trigger("reconciliation_mismatch", divergences[0].message)

    async def _on_kill_switch_triggered(self, event) -> None:
        """Automatic hard stop when safety rules are violated."""
        logger.critical("Kill switch callback: %s", event.reason)
        await self.instance.emergency_stop()

    @staticmethod
    def _convert_symbol(symbol: str) -> str:
        mapping = {
            "BTC/EUR": "XXBTZEUR",
            "ETH/EUR": "XETHZEUR",
            "BTC/USD": "XXBTZUSD",
            "ETH/USD": "XETHZUSD",
        }
        return mapping.get(symbol, symbol.replace("/", ""))
