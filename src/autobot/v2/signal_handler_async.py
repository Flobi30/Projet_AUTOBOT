"""
Signal Handler — Full Async
MIGRATION P0: Replaces signal_handler.py

Connects strategy signals to async order execution.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
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
from .modules.fee_optimizer import FeeOptimizer

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
        self._atr_period = 14
        self._risk_per_trade_pct = self._load_positive_float(
            "risk_per_trade_pct",
            "RISK_PER_TRADE_PCT",
            1.0,
        )
        self._max_position_capital_pct = self._load_positive_float(
            "max_position_capital_pct",
            "MAX_POSITION_CAPITAL_PCT",
            15.0,
        )
        self._atr_sl_mult = self._load_positive_float("atr_sl_mult", "ATR_SL_MULT", 1.8)
        self._tp_rr = self._load_positive_float("tp_rr", "TP_RR", 1.6)
        self._fallback_atr_pct = self._load_positive_float(
            "fallback_atr_pct",
            "FALLBACK_ATR_PCT",
            0.012,
        )
        self._max_spread_bps = self._load_positive_float(
            "max_spread_bps",
            "MAX_SPREAD_BPS",
            35.0,
        )
        self._min_edge_bps = self._load_positive_float("min_edge_bps", "MIN_EDGE_BPS", 12.0)
        self._edge_percentile_target = self._load_float_in_range(
            "edge_percentile_target",
            "EDGE_PERCENTILE_TARGET",
            0.70,
            minimum=0.50,
            maximum=0.99,
        )
        self._cost_obs_window = int(self._load_positive_float("cost_observation_window", "COST_OBSERVATION_WINDOW", 60.0))
        self._volatility_edge_weight = self._load_positive_float(
            "volatility_edge_weight",
            "VOLATILITY_EDGE_WEIGHT",
            0.20,
        )
        self._validate_risk_parameters()
        self._osm = PersistedOrderStateMachine()
        self._kill_switch = KillSwitch(on_trigger=self._on_kill_switch_triggered)
        self._reconciler = StrictReconciliation()
        self._setup_signal_callback()
        self._fee_optimizer: Optional[FeeOptimizer] = getattr(self.instance, "_fee_optimizer", None)
        logger.info(f"📡 SignalHandlerAsync initialisé pour {instance.id}")

    def _load_positive_float(self, config_key: str, env_key: str, default: float) -> float:
        """Read config then env value and fallback to default on invalid input."""
        candidate = getattr(getattr(self.instance, "config", None), config_key, default)
        env_value = os.getenv(env_key)
        if env_value is not None and str(env_value).strip() != "":
            candidate = env_value
        try:
            value = float(candidate)
        except (TypeError, ValueError):
            logger.warning("Paramètre invalide %s=%r, default=%.6f", env_key, candidate, default)
            return default
        if value <= 0:
            logger.warning("Paramètre hors bornes %s=%.6f (doit être > 0), default=%.6f", env_key, value, default)
            return default
        return value


    def _load_float_in_range(
        self,
        config_key: str,
        env_key: str,
        default: float,
        *,
        minimum: float,
        maximum: float,
    ) -> float:
        """Read config/env and clamp to [minimum, maximum]."""
        value = self._load_positive_float(config_key, env_key, default)
        return min(maximum, max(minimum, value))

    def _validate_risk_parameters(self) -> None:
        """Normalize parameters to safe bounds for risk/cost guards."""
        # Safety ranges
        self._fallback_atr_pct = min(0.25, max(0.001, self._fallback_atr_pct))
        self._tp_rr = min(8.0, max(0.5, self._tp_rr))
        self._atr_sl_mult = min(6.0, max(0.5, self._atr_sl_mult))
        self._max_spread_bps = min(1000.0, max(1.0, self._max_spread_bps))
        self._min_edge_bps = min(1000.0, max(1.0, self._min_edge_bps))
        self._risk_per_trade_pct = min(10.0, max(0.05, self._risk_per_trade_pct))
        self._max_position_capital_pct = min(100.0, max(1.0, self._max_position_capital_pct))
        self._edge_percentile_target = min(0.99, max(0.50, self._edge_percentile_target))
        self._cost_obs_window = int(min(500, max(10, self._cost_obs_window)))
        self._volatility_edge_weight = min(2.0, max(0.05, self._volatility_edge_weight))

    def _setup_signal_callback(self) -> None:
        strategy = getattr(self.instance, "_strategy", None)
        if strategy:
            strategy.set_signal_callback(self._on_signal_sync)

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

        atr_pct = self._estimate_atr_pct(signal.price)
        stop_distance = max(signal.price * atr_pct * self._atr_sl_mult, signal.price * 0.002)
        risk_budget = max(0.0, available * (self._risk_per_trade_pct / 100.0))
        max_order_value = available * (self._max_position_capital_pct / 100.0)
        volume_risk = (risk_budget / stop_distance) if stop_distance > 0 else 0.0
        volume_cap = (max_order_value / signal.price) if signal.price > 0 else 0.0
        volume_default = (available * 0.10) / signal.price if signal.price > 0 else 0.0
        volume = signal.volume if signal.volume > 0 else min(volume_default, volume_risk or volume_default, volume_cap or volume_default)
        volume = round(volume, 6)
        if volume <= 0:
            return

        edge_ctx = self._estimate_edge_context(signal, atr_pct)
        if not self._passes_cost_guard(edge_ctx):
            logger.info("⛔ Signal BUY ignoré: edge net insuffisant vs coûts")
            return

        symbol = self._convert_symbol(signal.symbol)
        execution_plan = self._build_execution_plan(signal, volume, edge_ctx=edge_ctx)
        decision_id = f"dec_{uuid.uuid4().hex}"
        signal_id = f"sig_{uuid.uuid4().hex}"
        rec = self._osm.new_order(
            instance_id=self.instance.id,
            symbol=symbol,
            side="buy",
            order_type=execution_plan["order_type"],
            requested_qty=volume,
            decision_id=decision_id,
            signal_id=signal_id,
        )
        self._osm.transition(rec.client_order_id, "SENT", "submitted_to_exchange")
        if execution_plan["order_type"] == "limit":
            result = await self.order_executor.execute_limit_order(
                symbol=symbol,
                side=OrderSide.BUY,
                volume=volume,
                limit_price=execution_plan["price"],
                post_only=bool(execution_plan.get("post_only", False)),
            )
        else:
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
            payload={
                **(result.raw_response or {}),
                "liquidity": result.liquidity,
                "order_type": execution_plan["order_type"],
                "post_only": bool(execution_plan.get("post_only", False)),
            },
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
        actual_liquidity = self._normalize_liquidity(result.liquidity)
        logger.info(
            "💸 Exécution BUY %s: type=%s post_only=%s liquidity=%s reason=%s",
            symbol,
            execution_plan["order_type"],
            bool(execution_plan.get("post_only", False)),
            actual_liquidity,
            execution_plan["reason"],
        )
        self._record_fee_optimizer_trade(
            amount=executed_price * executed_volume,
            fees=result.fees,
            liquidity=actual_liquidity,
        )

        stop_price, take_profit, trailing_activation, trailing_gap = self._compute_exit_levels(executed_price)
        sl_result = await self.order_executor.execute_stop_loss_order(
            symbol, OrderSide.SELL, executed_volume, stop_price
        )
        sl_txid = sl_result.txid if sl_result.success else None

        position = await self.instance.open_position(
            price=executed_price,
            volume=executed_volume,
            stop_loss=stop_price,
            take_profit=take_profit,
            stop_loss_txid=sl_txid,
            buy_txid=result.txid,
            buy_fee=result.fees,
            buy_fee_source="order_result" if result.fees is not None else None,
        )

        if position:
            self.instance._persistence.append_trade_ledger(
                trade_id=f"trd_{uuid.uuid4().hex}",
                position_id=position.id,
                instance_id=self.instance.id,
                symbol=symbol,
                side="buy",
                expected_price=signal.price,
                executed_price=executed_price,
                volume=executed_volume,
                fees=result.fees,
                slippage_bps=self._slippage_bps(signal.price, executed_price, "buy"),
                realized_pnl=None,
                exchange_order_id=result.txid,
                decision_id=decision_id,
                signal_id=signal_id,
                is_opening_leg=True,
                is_closing_leg=False,
                execution_liquidity=actual_liquidity,
            )
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
                slippage_bps=self._slippage_bps(signal.price, executed_price, "buy"),
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

        metadata = signal.metadata or {}
        close_all = signal.volume == -1 or metadata.get("close_all", False)
        to_close = open_positions if close_all else [open_positions[-1]]

        for pos in to_close:
            pos_id = pos.get("id")
            vol = pos.get("volume", 0)
            if not pos_id or vol <= 0:
                continue
            symbol = self._convert_symbol(pos.get("symbol") or signal.symbol)

            sl_txid = pos.get("stop_loss_txid")
            result = await self.order_executor.execute_market_order(symbol, OrderSide.SELL, vol)
            if result.success:
                price = result.executed_price or signal.price
                await self.instance.close_position(pos_id, price, sell_txid=result.txid)
                actual_liquidity = self._normalize_liquidity(result.liquidity)
                logger.info(
                    "💸 Exécution SELL %s: type=market post_only=False liquidity=%s",
                    symbol,
                    actual_liquidity,
                )
                self._record_fee_optimizer_trade(
                    amount=price * vol,
                    fees=result.fees,
                    liquidity=actual_liquidity,
                )
                self.instance._persistence.append_trade_ledger(
                    trade_id=f"trd_{uuid.uuid4().hex}",
                    position_id=pos_id,
                    instance_id=self.instance.id,
                    symbol=symbol,
                    side="sell",
                    expected_price=signal.price,
                    executed_price=price,
                    volume=vol,
                    fees=result.fees,
                    slippage_bps=self._slippage_bps(signal.price, price, "sell"),
                    realized_pnl=pos.get("profit"),
                    exchange_order_id=result.txid,
                    decision_id=None,
                    signal_id=None,
                    is_opening_leg=False,
                    is_closing_leg=True,
                    execution_liquidity=actual_liquidity,
                )
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
        exchange_realized = self._to_optional_float(tb.get("n") if isinstance(tb, dict) else None)
        exchange_unrealized = self._to_optional_float(tb.get("u") if isinstance(tb, dict) else None)
        exchange_fees = self._to_optional_float(tb.get("c") if isinstance(tb, dict) else None)
        local_unrealized = self._compute_unrealized_pnl()
        local_fees = self._compute_local_fees_aggregate()
        local_realized = self._to_optional_float(self.instance.get_profit())

        exchange_metrics = {
            "realized_pnl": exchange_realized,
            "unrealized_pnl": exchange_unrealized,
            "fees": exchange_fees,
        }
        local_metrics = {
            "realized_pnl": local_realized,
            "unrealized_pnl": local_unrealized,
            "fees": local_fees,
        }
        quality_flags = {
            "local_realized_available": local_realized is not None,
            "local_unrealized_quality": getattr(self, "_last_unrealized_pnl_quality", "incomplete"),
            "local_fees_available": local_fees is not None,
            "exchange_realized_available": exchange_realized is not None,
            "exchange_unrealized_available": exchange_unrealized is not None,
            "exchange_fees_available": exchange_fees is not None,
        }
        metrics_quality = self._derive_metrics_quality(quality_flags)
        logger.info(
            "📊 Réconciliation métriques qualité=%s (flags=%s)",
            metrics_quality,
            quality_flags,
        )
        divergences.extend(
            self._reconciler.compare_fills_fees_pnl(
                self._normalize_metrics_for_reconciliation(local_metrics),
                self._normalize_metrics_for_reconciliation(exchange_metrics),
            )
        )
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
            "XBT/EUR": "XXBTZEUR",
            "ETH/EUR": "XETHZEUR",
            "BTC/USD": "XXBTZUSD",
            "ETH/USD": "XETHZUSD",
        }
        return mapping.get(symbol, symbol.replace("/", ""))

    def _estimate_atr_pct(self, fallback_price: float) -> float:
        """Lightweight ATR proxy from recent close-to-close moves."""
        history = list(getattr(self.instance, "_price_history", []))
        if len(history) < 3:
            return max(0.001, min(0.08, self._fallback_atr_pct))
        prices = [float(x[1]) for x in history[-(self._atr_period + 1):]]
        moves = [abs(prices[i] - prices[i - 1]) for i in range(1, len(prices))]
        atr_abs = sum(moves) / len(moves) if moves else max(fallback_price * 0.01, 1e-8)
        ref = prices[-1] if prices else fallback_price
        return max(0.001, min(0.08, atr_abs / max(ref, 1e-8)))

    async def _estimate_exchange_fees_24h(self) -> float:
        """Best-effort fee estimate from closed orders in last 24h."""
        if self.order_executor is None:
            return 0.0
        try:
            now = int(time.time())
            closed = await self.order_executor.get_closed_orders(start_time=now - 86400, end_time=now)
            total = 0.0
            for order in closed.values():
                fee = order.get("fee", 0.0)
                try:
                    total += float(fee)
                except (TypeError, ValueError):
                    continue
            return total
        except Exception:
            return 0.0

    def _compute_local_fees_aggregate(self) -> Optional[float]:
        persistence = getattr(self.instance, "_persistence", None)
        if persistence is None or not hasattr(persistence, "get_trade_ledger_metrics"):
            return None
        try:
            metrics = persistence.get_trade_ledger_metrics(self.instance.id)
            return self._to_optional_float(metrics.get("total_fees"))
        except Exception:
            logger.exception("❌ Impossible d'agréger les frais locaux (persistence/audit)")
            return None

    @staticmethod
    def _normalize_metrics_for_reconciliation(metrics: dict[str, Optional[float]]) -> dict[str, float]:
        return {
            "realized_pnl": float(metrics.get("realized_pnl") or 0.0),
            "unrealized_pnl": float(metrics.get("unrealized_pnl") or 0.0),
            "fees": float(metrics.get("fees") or 0.0),
        }

    @staticmethod
    def _to_optional_float(value: Any) -> Optional[float]:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _derive_metrics_quality(flags: dict[str, Any]) -> str:
        required_available = (
            flags.get("local_realized_available")
            and flags.get("local_fees_available")
            and flags.get("exchange_realized_available")
            and flags.get("exchange_unrealized_available")
            and flags.get("exchange_fees_available")
        )
        unrealized_quality = flags.get("local_unrealized_quality", "incomplete")
        if not required_available or unrealized_quality == "incomplete":
            return "incomplet"
        if unrealized_quality == "estimated":
            return "estimé"
        return "complet"

    def _compute_exit_levels(self, entry_price: float) -> tuple[float, float, float, float]:
        atr_pct = self._estimate_atr_pct(entry_price)
        sl_pct = max(0.004, atr_pct * self._atr_sl_mult)
        stop_price = entry_price * (1.0 - sl_pct)
        tp_pct = max(sl_pct * self._tp_rr, sl_pct * 1.2)
        take_profit = entry_price * (1.0 + tp_pct)
        trailing_activation = entry_price * (1.0 + sl_pct * 0.8)
        trailing_gap = sl_pct * 0.7
        return stop_price, take_profit, trailing_activation, trailing_gap

    def _slippage_bps(self, expected_price: float, executed_price: float, side: str) -> float:
        if expected_price <= 0:
            return 0.0
        raw = ((executed_price - expected_price) / expected_price) * 10000
        return float(raw if side == "buy" else -raw)

    def _percentile(self, values: list[float], q: float) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        if len(ordered) == 1:
            return ordered[0]
        clamped_q = min(1.0, max(0.0, float(q)))
        idx = (len(ordered) - 1) * clamped_q
        lo = int(idx)
        hi = min(lo + 1, len(ordered) - 1)
        if lo == hi:
            return ordered[lo]
        frac = idx - lo
        return ordered[lo] + (ordered[hi] - ordered[lo]) * frac

    def _load_recent_execution_costs(self, symbol: str) -> list[dict[str, float]]:
        persistence = getattr(self.instance, "_persistence", None)
        if persistence is None or not hasattr(persistence, "_get_conn"):
            return []
        try:
            with persistence._lock:
                conn = persistence._get_conn()
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """
                    SELECT executed_price, volume, fees, slippage_bps
                    FROM trade_ledger
                    WHERE instance_id = ?
                      AND symbol = ?
                      AND executed_price IS NOT NULL
                      AND volume IS NOT NULL
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (self.instance.id, symbol, int(self._cost_obs_window)),
                ).fetchall()
            samples: list[dict[str, float]] = []
            for row in rows:
                px = self._to_optional_float(row["executed_price"])
                vol = self._to_optional_float(row["volume"])
                if px is None or vol is None or px <= 0 or vol <= 0:
                    continue
                amount = px * vol
                fee = max(0.0, self._to_optional_float(row["fees"]) or 0.0)
                fee_bps = (fee / amount) * 10000 if amount > 0 else 0.0
                slip = abs(self._to_optional_float(row["slippage_bps"]) or 0.0)
                samples.append({"fee_bps": fee_bps, "slippage_bps": slip, "total_cost_bps": fee_bps + slip})
            return samples
        except Exception:
            logger.exception("❌ Impossible de charger les coûts observés pour %s", symbol)
            return []

    def _estimate_edge_context(self, signal: TradingSignal, atr_pct: float) -> dict[str, float]:
        metadata = signal.metadata or {}
        symbol = self._convert_symbol(signal.symbol)
        spread_bps = float(metadata.get("spread_bps", 0.0))
        observed = self._load_recent_execution_costs(symbol)
        fee_samples = [s["fee_bps"] for s in observed]
        slip_samples = [s["slippage_bps"] for s in observed]
        cost_samples = [s["total_cost_bps"] for s in observed]
        fallback_fee_bps = float(metadata.get("fee_bps", 40.0))
        fallback_slippage_bps = float(metadata.get("slippage_bps", max(6.0, spread_bps * 0.35)))
        estimated_fee_bps = self._percentile(fee_samples, self._edge_percentile_target) if fee_samples else fallback_fee_bps
        estimated_slippage_bps = self._percentile(slip_samples, self._edge_percentile_target) if slip_samples else fallback_slippage_bps
        observed_cost_pctl = self._percentile(cost_samples, self._edge_percentile_target) if cost_samples else (estimated_fee_bps + estimated_slippage_bps)
        expected_move_bps = float(metadata.get("expected_move_bps", atr_pct * 10000 * self._tp_rr))
        total_cost_bps = spread_bps + estimated_fee_bps + estimated_slippage_bps
        net_edge_bps = expected_move_bps - total_cost_bps
        volatility_component_bps = atr_pct * 10000 * self._volatility_edge_weight
        adaptive_min_edge_bps = max(self._min_edge_bps, observed_cost_pctl + volatility_component_bps)
        return {
            "spread_bps": spread_bps,
            "expected_move_bps": expected_move_bps,
            "estimated_fee_bps": estimated_fee_bps,
            "estimated_slippage_bps": estimated_slippage_bps,
            "total_cost_bps": total_cost_bps,
            "net_edge_bps": net_edge_bps,
            "adaptive_min_edge_bps": adaptive_min_edge_bps,
            "volatility_component_bps": volatility_component_bps,
            "observed_samples": float(len(observed)),
        }

    def _passes_cost_guard(self, edge_ctx: dict[str, float]) -> bool:
        spread_bps = float(edge_ctx.get("spread_bps", 0.0))
        if spread_bps > self._max_spread_bps:
            logger.info("Spread %.1f bps > max %.1f bps", spread_bps, self._max_spread_bps)
            return False
        net_edge_bps = float(edge_ctx.get("net_edge_bps", 0.0))
        adaptive_min_edge_bps = float(edge_ctx.get("adaptive_min_edge_bps", self._min_edge_bps))
        if net_edge_bps < adaptive_min_edge_bps:
            logger.info(
                "Edge net %.2f bps < seuil adaptatif %.2f bps (pctl=%.2f, n=%d, coûts=%.2f)",
                net_edge_bps,
                adaptive_min_edge_bps,
                self._edge_percentile_target,
                int(edge_ctx.get("observed_samples", 0.0)),
                float(edge_ctx.get("total_cost_bps", 0.0)),
            )
            return False
        return True

    def _build_execution_plan(self, signal: TradingSignal, volume: float, edge_ctx: Optional[dict[str, float]] = None) -> dict[str, Any]:
        metadata = signal.metadata or {}
        edge = edge_ctx or self._estimate_edge_context(signal, self._estimate_atr_pct(signal.price))
        edge_bps = float(edge.get("net_edge_bps", 0.0))
        adaptive_min_edge = float(edge.get("adaptive_min_edge_bps", self._min_edge_bps))
        spread_bps = float(edge.get("spread_bps", metadata.get("spread_bps", 0.0)))
        urgency = max(0.0, min(1.0, float(metadata.get("urgency", 0.0))))
        low_urgency = urgency <= 0.35
        has_edge = edge_bps >= adaptive_min_edge

        amount = max(signal.price * volume, 0.0)
        rec = (
            self._fee_optimizer.recommend(
                side="buy",
                price=signal.price,
                amount=amount,
                urgency=urgency,
                spread_pct=(spread_bps / 100.0),
            )
            if self._fee_optimizer is not None
            else {"order_type": "market", "post_only": False, "reason": "fee_optimizer_unavailable"}
        )
        prefer_limit = low_urgency and has_edge and rec.get("order_type") == "limit"
        if prefer_limit:
            price = float(metadata.get("limit_price") or signal.price)
            return {"order_type": "limit", "post_only": True, "price": price, "reason": rec.get("reason", "low_urgency_edge")}
        return {"order_type": "market", "post_only": False, "price": signal.price, "reason": rec.get("reason", "market_fallback")}

    @staticmethod
    def _normalize_liquidity(liquidity: Optional[str]) -> str:
        normalized = str(liquidity or "unknown").lower()
        if normalized not in {"maker", "taker"}:
            return "unknown"
        return normalized

    def _record_fee_optimizer_trade(self, amount: float, fees: float, liquidity: str) -> None:
        if self._fee_optimizer is None or amount <= 0:
            return
        self._fee_optimizer.record_trade(
            volume=amount,
            fee=max(0.0, float(fees or 0.0)),
            was_maker=(liquidity == "maker"),
        )

    def _compute_unrealized_pnl(self) -> Optional[float]:
        last_price = getattr(self.instance, "_last_price", None)
        if last_price is None:
            self._last_unrealized_pnl_quality = "incomplete"
            return None
        unrealized = 0.0
        has_open_position = False
        has_partial_data = False
        for pos in self.instance.get_positions_snapshot():
            if pos.get("status") != "open":
                continue
            has_open_position = True
            buy_price = self._to_optional_float(pos.get("buy_price"))
            volume = self._to_optional_float(pos.get("volume"))
            if buy_price is None or volume is None:
                has_partial_data = True
                continue
            if buy_price > 0 and volume > 0:
                unrealized += (float(last_price) - buy_price) * volume
            else:
                has_partial_data = True
        if has_open_position and has_partial_data and unrealized == 0.0:
            self._last_unrealized_pnl_quality = "incomplete"
            return None
        self._last_unrealized_pnl_quality = "estimated" if has_partial_data else "complete"
        return unrealized
