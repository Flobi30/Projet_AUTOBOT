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
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Optional

from .strategies import TradingSignal, SignalType
from .order_executor_async import OrderExecutorAsync, OrderSide
from .validator import ValidatorEngine, ValidationStatus, create_default_validator_engine
from .order_state_machine import PersistedOrderStateMachine
from .kill_switch import KillSwitch
from .reconciliation_strict import StrictReconciliation
from .modules.fee_optimizer import FeeOptimizer
from .market_analyzer import get_market_analyzer
from .opportunity_scoring import OpportunityScorer

logger = logging.getLogger(__name__)


DEFAULT_COST_EDGE_PROFILES: dict[str, dict[str, dict[str, float]]] = {
    "conservative": {
        "RANGE": {"atr_sl_mult": 1.35, "tp_rr": 1.85, "min_edge_bps": 16.0, "cost_buffer_mult": 1.00, "volatility_edge_weight": 0.35},
        "TREND": {"atr_sl_mult": 1.70, "tp_rr": 2.10, "min_edge_bps": 18.0, "cost_buffer_mult": 1.00, "volatility_edge_weight": 0.35},
    },
    "balanced": {
        "RANGE": {"atr_sl_mult": 1.55, "tp_rr": 1.55, "min_edge_bps": 12.0, "cost_buffer_mult": 1.00, "volatility_edge_weight": 0.25},
        "TREND": {"atr_sl_mult": 1.95, "tp_rr": 1.75, "min_edge_bps": 14.0, "cost_buffer_mult": 1.00, "volatility_edge_weight": 0.25},
    },
    "exploratory_paper": {
        "RANGE": {"atr_sl_mult": 1.55, "tp_rr": 1.75, "min_edge_bps": 6.0, "cost_buffer_mult": 0.25, "volatility_edge_weight": 0.10},
        "TREND": {"atr_sl_mult": 1.95, "tp_rr": 1.95, "min_edge_bps": 8.0, "cost_buffer_mult": 0.25, "volatility_edge_weight": 0.10},
    },
    # Backward-compatible aliases for existing configs.
    "defensive": {
        "RANGE": {"atr_sl_mult": 1.35, "tp_rr": 1.85, "min_edge_bps": 16.0, "cost_buffer_mult": 1.00, "volatility_edge_weight": 0.35},
        "TREND": {"atr_sl_mult": 1.70, "tp_rr": 2.10, "min_edge_bps": 18.0, "cost_buffer_mult": 1.00, "volatility_edge_weight": 0.35},
    },
    "offensive": {
        "RANGE": {"atr_sl_mult": 1.75, "tp_rr": 1.35, "min_edge_bps": 10.0, "cost_buffer_mult": 1.00, "volatility_edge_weight": 0.25},
        "TREND": {"atr_sl_mult": 2.20, "tp_rr": 1.55, "min_edge_bps": 12.0, "cost_buffer_mult": 1.00, "volatility_edge_weight": 0.25},
    },
}
RISK_REGIME_PRESETS = DEFAULT_COST_EDGE_PROFILES


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
        self._base_atr_sl_mult = self._atr_sl_mult
        self._base_tp_rr = self._tp_rr
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
        self._max_signal_latency_ms = self._load_positive_float(
            "max_signal_latency_ms",
            "MAX_SIGNAL_LATENCY_MS",
            2500.0,
        )
        self._max_expected_slippage_bps = self._load_positive_float(
            "max_expected_slippage_bps",
            "MAX_EXPECTED_SLIPPAGE_BPS",
            22.0,
        )
        self._min_edge_bps = self._load_positive_float("min_edge_bps", "MIN_EDGE_BPS", 12.0)
        self._base_min_edge_bps = self._min_edge_bps
        self._edge_percentile_target = self._load_float_in_range(
            "edge_percentile_target",
            "EDGE_PERCENTILE_TARGET",
            0.75,
            minimum=0.50,
            maximum=0.99,
        )
        self._edge_fallback_fee_bps = self._load_float_in_range(
            "edge_fallback_fee_bps",
            "EDGE_FALLBACK_FEE_BPS",
            40.0,
            minimum=0.0,
            maximum=250.0,
        )
        self._edge_fallback_slippage_bps = self._load_float_in_range(
            "edge_fallback_slippage_bps",
            "EDGE_FALLBACK_SLIPPAGE_BPS",
            6.0,
            minimum=0.0,
            maximum=250.0,
        )
        self._edge_slippage_spread_fraction = self._load_float_in_range(
            "edge_slippage_spread_fraction",
            "EDGE_SLIPPAGE_SPREAD_FRACTION",
            0.35,
            minimum=0.0,
            maximum=2.0,
        )
        self._volatility_edge_weight = self._load_float_in_range(
            "volatility_edge_weight",
            "VOLATILITY_EDGE_WEIGHT",
            0.25,
            minimum=0.0,
            maximum=5.0,
        )
        self._edge_cost_buffer_mult = self._load_float_in_range(
            "edge_cost_buffer_mult",
            "EDGE_COST_BUFFER_MULT",
            1.0,
            minimum=0.0,
            maximum=3.0,
        )
        self._risk_regime_preset = str(
            getattr(
                getattr(self.instance, "config", None),
                "cost_edge_profile",
                os.getenv("COST_EDGE_PROFILE", os.getenv("RISK_REGIME_PRESET", "balanced")),
            )
        ).strip().lower()
        self._cost_edge_profiles = self._load_cost_edge_profiles()
        self._validate_risk_parameters()
        self._osm = PersistedOrderStateMachine()
        self._kill_switch = KillSwitch(on_trigger=self._on_kill_switch_triggered)
        self._reconciler = StrictReconciliation()
        self._setup_signal_callback()
        self._fee_optimizer: Optional[FeeOptimizer] = getattr(self.instance, "_fee_optimizer", None)
        self._execution_cost_samples: dict[str, list[dict[str, float]]] = {}
        history_size = self._load_positive_int("cost_edge_audit_history_size", "COST_EDGE_AUDIT_HISTORY_SIZE", 50)
        self._runtime_event_history: deque[dict[str, Any]] = deque(maxlen=min(500, max(10, history_size)))
        self._opportunity_scorer = OpportunityScorer()
        logger.info(f"📡 SignalHandlerAsync initialisé pour {instance.id}")

    def _record_runtime_event(self, attr_name: str, **payload: Any) -> dict[str, Any]:
        """Expose non-sensitive runtime trace events for the dashboard."""
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "instance_id": getattr(self.instance, "id", None),
            **payload,
        }
        history = getattr(self, "_runtime_event_history", None)
        if history is not None:
            history.append(event)
            setattr(self.instance, "_runtime_events", list(history))
        setattr(self, attr_name, event)
        setattr(self.instance, attr_name, event)
        return event

    @staticmethod
    def _serialize_risk_params(params: dict[str, Any]) -> dict[str, Any]:
        serialized: dict[str, Any] = {}
        for key, value in params.items():
            if isinstance(value, (int, float)):
                serialized[key] = round(float(value), 6)
            else:
                serialized[key] = value
        return serialized

    def _estimate_total_runtime_capital(self) -> float:
        orchestrator = getattr(self.instance, "orchestrator", None)
        instances = getattr(orchestrator, "_instances", None)
        if isinstance(instances, dict):
            total = 0.0
            for inst in instances.values():
                try:
                    total += max(0.0, float(inst.get_current_capital()))
                except Exception:
                    continue
            if total > 0.0:
                return total
        try:
            return max(0.0, float(self.instance.get_current_capital()))
        except Exception:
            return 0.0

    def _build_opportunity_result(
        self,
        signal: TradingSignal,
        edge_ctx: dict[str, float],
        atr_pct: float,
        available_capital: float,
        open_positions: int,
    ) -> Any:
        return self._opportunity_scorer.score_signal(
            symbol=signal.symbol,
            edge_context=edge_ctx,
            atr_pct=atr_pct,
            available_capital=available_capital,
            open_positions=open_positions,
            recent_events=list(getattr(self, "_runtime_event_history", [])),
            market_metrics=self._get_market_metrics(signal.symbol),
            total_capital=self._estimate_total_runtime_capital(),
            paper_mode=self._is_paper_mode(),
            price_history=list(getattr(self.instance, "_price_history", [])),
        )

    def _opportunity_gate_applies(self) -> dict[str, Any]:
        return self._opportunity_scorer.execution_gate(paper_mode=self._is_paper_mode())

    @staticmethod
    async def _maybe_await(value: Any) -> Any:
        if asyncio.iscoroutine(value) or isinstance(value, asyncio.Future):
            return await value
        return value

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

    def _load_positive_int(self, config_key: str, env_key: str, default: int) -> int:
        """Read a positive integer from config/env."""
        candidate = getattr(getattr(self.instance, "config", None), config_key, default)
        env_value = os.getenv(env_key)
        if env_value is not None and str(env_value).strip() != "":
            candidate = env_value
        try:
            value = int(candidate)
        except (TypeError, ValueError):
            logger.warning("Paramètre invalide %s=%r, default=%d", env_key, candidate, default)
            return default
        if value <= 0:
            logger.warning("Paramètre hors bornes %s=%d (doit être > 0), default=%d", env_key, value, default)
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

    def _load_cost_edge_profiles(self) -> dict[str, dict[str, dict[str, float]]]:
        """Load cost/edge profile defaults, then apply env overrides."""
        profiles = deepcopy(DEFAULT_COST_EDGE_PROFILES)
        field_env = {
            "atr_sl_mult": "ATR_SL_MULT",
            "tp_rr": "TP_RR",
            "min_edge_bps": "MIN_EDGE_BPS",
            "cost_buffer_mult": "COST_BUFFER_MULT",
            "volatility_edge_weight": "VOLATILITY_EDGE_WEIGHT",
        }
        for profile_name, regimes in profiles.items():
            for regime_name, params in regimes.items():
                for field, suffix in field_env.items():
                    env_key = f"COST_EDGE_{profile_name.upper()}_{regime_name}_{suffix}"
                    raw = os.getenv(env_key)
                    if raw is None or raw.strip() == "":
                        continue
                    try:
                        params[field] = float(raw)
                    except ValueError:
                        logger.warning("Paramètre cost/edge invalide %s=%r ignoré", env_key, raw)
        return profiles

    def _is_paper_mode(self) -> bool:
        orchestrator = getattr(self.instance, "orchestrator", None)
        if getattr(orchestrator, "paper_mode", False):
            return True
        return os.getenv("PAPER_TRADING", "false").lower() in {"1", "true", "yes", "on"}

    def _validate_risk_parameters(self) -> None:
        """Normalize parameters to safe bounds for risk/cost guards."""
        # Safety ranges
        self._fallback_atr_pct = min(0.25, max(0.001, self._fallback_atr_pct))
        self._tp_rr = min(8.0, max(0.5, self._tp_rr))
        self._atr_sl_mult = min(6.0, max(0.5, self._atr_sl_mult))
        self._max_spread_bps = min(1000.0, max(1.0, self._max_spread_bps))
        self._max_signal_latency_ms = min(60_000.0, max(5.0, self._max_signal_latency_ms))
        self._max_expected_slippage_bps = min(1000.0, max(1.0, self._max_expected_slippage_bps))
        self._min_edge_bps = min(1000.0, max(1.0, self._min_edge_bps))
        self._risk_per_trade_pct = min(10.0, max(0.05, self._risk_per_trade_pct))
        self._max_position_capital_pct = min(100.0, max(1.0, self._max_position_capital_pct))
        self._base_tp_rr = self._tp_rr
        self._base_atr_sl_mult = self._atr_sl_mult
        self._base_min_edge_bps = self._min_edge_bps
        if self._risk_regime_preset not in self._cost_edge_profiles:
            logger.warning(
                "Profil cost/edge inconnu '%s' (disponibles=%s), fallback=balanced",
                self._risk_regime_preset,
                ",".join(sorted(self._cost_edge_profiles.keys())),
            )
            self._risk_regime_preset = "balanced"
        if self._risk_regime_preset == "exploratory_paper" and not self._is_paper_mode():
            logger.warning("Profil exploratory_paper interdit hors paper trading, fallback=balanced")
            self._risk_regime_preset = "balanced"

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
            self._record_runtime_event(
                "_last_decision_event",
                event="signal_ignored",
                reason="kill_switch_active",
                symbol=signal.symbol,
                side=signal.type.value,
                price=float(signal.price),
            )
            logger.error("🛑 Kill switch actif — signal ignoré")
            return
        logger.info(f"📡 Signal: {signal.type.value.upper()} {signal.symbol} @ {signal.price:.2f}")
        self._record_runtime_event(
            "_last_signal_event",
            event="signal_received",
            symbol=signal.symbol,
            side=signal.type.value,
            price=float(signal.price),
            volume=float(signal.volume),
            reason=getattr(signal, "reason", None),
        )

        if self._last_signal_time:
            elapsed = (datetime.now(timezone.utc) - self._last_signal_time).total_seconds()
            if elapsed < self._cooldown_seconds:
                self._record_runtime_event(
                    "_last_decision_event",
                    event="signal_ignored",
                    reason="cooldown",
                    symbol=signal.symbol,
                    side=signal.type.value,
                    elapsed_seconds=round(elapsed, 3),
                )
                logger.warning(f"⏱️ Signal ignoré (cooldown): {elapsed:.1f}s")
                return

        try:
            if signal.type == SignalType.BUY:
                if not self._passes_microstructure_hard_filter(signal):
                    details = getattr(self, "_last_microstructure_reject_context", None)
                    self._record_runtime_event(
                        "_last_decision_event",
                        event="signal_rejected",
                        reason="microstructure_filter",
                        symbol=signal.symbol,
                        side=signal.type.value,
                        details=details if isinstance(details, dict) else None,
                    )
                    return
                await self._execute_buy(signal)
            elif signal.type in (SignalType.SELL, SignalType.CLOSE):
                await self._execute_sell(signal)
            self._last_signal_time = datetime.now(timezone.utc)
        except Exception as exc:
            self._record_runtime_event(
                "_last_error_event",
                event="signal_execution_error",
                symbol=signal.symbol,
                side=signal.type.value,
                error=str(exc)[:240],
            )
            logger.exception(f"❌ Erreur exécution signal: {exc}")


    async def recover(self) -> None:
        """ROB-01: Check for in-flight orders and reconcile with exchange."""
        pending = await self._osm.recover_non_terminal()
        if not pending:
            return
        
        logger.info(f"🔄 [WAL] Récupération de {len(pending)} ordres non terminés...")
        for row in pending:
            client_order_id = row["client_order_id"]
            userref = row.get("userref")
            txid = row.get("exchange_order_id")
            symbol = row["symbol"]
            
            logger.info(f"🔎 [WAL] Vérification ordre {client_order_id} (userref={userref}, txid={txid})")
            
            found_txid = None
            order_info = None
            
            if txid:
                # We have a TXID, query directly
                status = await self.order_executor.get_order_status(txid)
                if status:
                    found_txid = txid
                    # Update info from status if possible
            elif userref:
                # No TXID, search by userref
                found = await self.order_executor.find_order_by_userref(userref)
                if found:
                    found_txid, order_info = found
            
            if found_txid:
                logger.info(f"✅ [WAL] Ordre trouvé sur l'échange: {found_txid}")
                # Transition based on exchange state
                # For now, mark as ACK to trigger reconciliation
                await self._osm.transition(client_order_id, "ACK", "recovered_from_exchange", exchange_order_id=found_txid)
            else:
                logger.warning(f"❌ [WAL] Ordre {client_order_id} introuvable sur l'échange -- marquage REJECTED")
                await self._osm.transition(client_order_id, "REJECTED", "not_found_on_exchange_after_crash")

    async def _execute_buy(self, signal: TradingSignal) -> None:
        logger.info(f"🛒 Exécution ACHAT {signal.symbol}")
        if await self._maybe_await(self._osm.is_duplicate_active(self._convert_symbol(signal.symbol), "buy")):
            self._record_runtime_event(
                "_last_decision_event",
                event="buy_rejected",
                reason="duplicate_active_order",
                symbol=signal.symbol,
                side="buy",
            )
            logger.warning("🔁 Ordre BUY dupliqué bloqué (idempotency)")
            return

        available = self.instance.get_available_capital()
        order_value = signal.volume * signal.price if signal.volume > 0 else (available * 0.10)
        open_positions_count = len([
            p for p in self.instance.get_positions_snapshot() if p.get("status") == "open"
        ])
        context = {
            # Align with open_position_validator contract
            "balance": available,
            "order_value": order_value,
            "open_positions": open_positions_count,
            "price": signal.price,
            "instance_status": self.instance.status.value,
            "max_positions": getattr(self.instance.config, "max_positions", 10),
        }

        validation = self.validator.validate("open_position", context)
        if validation.status == ValidationStatus.RED:
            self._record_runtime_event(
                "_last_decision_event",
                event="buy_rejected",
                reason="open_position_validator",
                symbol=signal.symbol,
                message=validation.message,
            )
            logger.error(f"❌ Signal BUY rejeté: {validation.message}")
            return

        if self.order_executor is None:
            self._record_runtime_event(
                "_last_error_event",
                event="buy_rejected",
                reason="order_executor_missing",
                symbol=signal.symbol,
            )
            logger.error("❌ OrderExecutor non configuré")
            return

        atr_pct = self._estimate_atr_pct(signal.price)
        risk_params = self._resolve_dynamic_risk_params(signal, atr_pct)
        stop_distance = max(signal.price * atr_pct * risk_params["atr_sl_mult"], signal.price * 0.002)
        risk_budget = max(0.0, available * (self._risk_per_trade_pct / 100.0))
        max_order_value = available * (self._max_position_capital_pct / 100.0)
        volume_risk = (risk_budget / stop_distance) if stop_distance > 0 else 0.0
        volume_cap = (max_order_value / signal.price) if signal.price > 0 else 0.0
        volume_default = (available * 0.10) / signal.price if signal.price > 0 else 0.0
        volume = signal.volume if signal.volume > 0 else min(volume_default, volume_risk or volume_default, volume_cap or volume_default)
        volume = round(volume, 6)
        if volume <= 0:
            self._record_runtime_event(
                "_last_decision_event",
                event="buy_rejected",
                reason="zero_or_negative_volume",
                symbol=signal.symbol,
                side="buy",
                available_capital=float(available),
                order_value=float(order_value),
            )
            return

        edge_ctx = self._estimate_edge_context(signal, atr_pct, risk_params)
        if not self._passes_cost_guard(edge_ctx):
            cost_details = {
                key: round(float(value), 6)
                for key, value in edge_ctx.items()
                if isinstance(value, (int, float))
            }
            self._record_runtime_event(
                "_last_decision_event",
                event="buy_rejected",
                reason="cost_guard",
                symbol=signal.symbol,
                side="buy",
                net_edge_bps=round(float(edge_ctx.get("net_edge_bps", 0.0)), 3),
                min_edge_bps=round(float(edge_ctx.get("adaptive_min_edge_bps", self._min_edge_bps)), 3),
                gross_edge_bps=round(float(edge_ctx.get("expected_move_bps", 0.0)), 3),
                cost_bps=round(float(edge_ctx.get("total_cost_bps", 0.0)), 3),
                gross_required_bps=round(float(edge_ctx.get("gross_required_bps", 0.0)), 3),
                edge_shortfall_bps=round(float(edge_ctx.get("edge_shortfall_bps", 0.0)), 3),
                blocking_condition=(
                    "net_edge_bps < adaptive_min_edge_bps"
                    if float(edge_ctx.get("net_edge_bps", 0.0)) < float(edge_ctx.get("adaptive_min_edge_bps", self._min_edge_bps))
                    else "spread_bps > max_spread_bps"
                ),
                atr_pct=round(float(atr_pct), 8),
                volume=float(volume),
                order_value=round(float(volume * signal.price), 8),
                available_capital=round(float(available), 8),
                signal_price=float(signal.price),
                signal_reason=getattr(signal, "reason", None),
                risk_params=self._serialize_risk_params(risk_params),
                edge_context=cost_details,
            )
            logger.info("⛔ Signal BUY ignoré: edge net insuffisant vs coûts")
            return

        opportunity = self._build_opportunity_result(
            signal,
            edge_ctx,
            atr_pct,
            available,
            open_positions_count,
        )
        opportunity_payload = opportunity.to_dict()
        opportunity_gate = self._opportunity_gate_applies()
        if opportunity_gate.get("selection_applies_to_execution"):
            if opportunity.status != "tradable" or opportunity.recommended_order_eur <= 0.0:
                self._record_runtime_event(
                    "_last_decision_event",
                    event="buy_rejected",
                    reason="opportunity_score",
                    symbol=signal.symbol,
                    side="buy",
                    net_edge_bps=round(float(edge_ctx.get("net_edge_bps", 0.0)), 3),
                    min_edge_bps=round(float(edge_ctx.get("adaptive_min_edge_bps", self._min_edge_bps)), 3),
                    gross_edge_bps=round(float(edge_ctx.get("expected_move_bps", 0.0)), 3),
                    cost_bps=round(float(edge_ctx.get("total_cost_bps", 0.0)), 3),
                    blocking_condition=opportunity.reason,
                    atr_pct=round(float(atr_pct), 8),
                    volume=float(volume),
                    order_value=round(float(volume * signal.price), 8),
                    available_capital=round(float(available), 8),
                    signal_price=float(signal.price),
                    signal_reason=getattr(signal, "reason", None),
                    risk_params=self._serialize_risk_params(risk_params),
                    edge_context={
                        key: round(float(value), 6)
                        for key, value in edge_ctx.items()
                        if isinstance(value, (int, float))
                    },
                    opportunity=opportunity_payload,
                    opportunity_gate=opportunity_gate,
                )
                logger.info(
                    "⛔ Signal BUY ignoré: opportunité insuffisante (%s, score %.1f)",
                    opportunity.reason,
                    opportunity.score,
                )
                return

            capped_volume = round(opportunity.recommended_order_eur / signal.price, 6)
            if capped_volume <= 0.0:
                self._record_runtime_event(
                    "_last_decision_event",
                    event="buy_rejected",
                    reason="opportunity_allocation_zero",
                    symbol=signal.symbol,
                    side="buy",
                    opportunity=opportunity_payload,
                    opportunity_gate=opportunity_gate,
                )
                return
            volume = min(volume, capped_volume)

        symbol = self._convert_symbol(signal.symbol)
        volume_before_min_adjustment = volume
        normalized_volume = self._normalize_buy_volume_for_minimum(
            symbol=symbol,
            volume=volume,
            price=signal.price,
            available_capital=available,
            max_order_value=max_order_value,
            signal_reason=getattr(signal, "reason", None),
            opportunity=opportunity_payload,
        )
        if normalized_volume is None:
            return
        volume = normalized_volume
        order_size_adjustment = None
        if volume > volume_before_min_adjustment:
            order_size_adjustment = {
                "reason": "rounded_to_min_order_volume",
                "original_volume": round(float(volume_before_min_adjustment), 12),
                "adjusted_volume": round(float(volume), 12),
                "original_order_value": round(float(volume_before_min_adjustment * signal.price), 8),
                "adjusted_order_value": round(float(volume * signal.price), 8),
            }
        accepted_edge_details = {
            key: round(float(value), 6)
            for key, value in edge_ctx.items()
            if isinstance(value, (int, float))
        }
        self._record_runtime_event(
            "_last_decision_event",
            event="buy_accepted",
            reason="all_guards_passed",
            symbol=signal.symbol,
            side="buy",
            net_edge_bps=round(float(edge_ctx.get("net_edge_bps", 0.0)), 3),
            min_edge_bps=round(float(edge_ctx.get("adaptive_min_edge_bps", self._min_edge_bps)), 3),
            gross_edge_bps=round(float(edge_ctx.get("expected_move_bps", 0.0)), 3),
            cost_bps=round(float(edge_ctx.get("total_cost_bps", 0.0)), 3),
            gross_required_bps=round(float(edge_ctx.get("gross_required_bps", 0.0)), 3),
            edge_shortfall_bps=round(float(edge_ctx.get("edge_shortfall_bps", 0.0)), 3),
            atr_pct=round(float(atr_pct), 8),
            volume=float(volume),
            order_value=round(float(volume * signal.price), 8),
            available_capital=round(float(available), 8),
            signal_price=float(signal.price),
            signal_reason=getattr(signal, "reason", None),
            risk_params=self._serialize_risk_params(risk_params),
            edge_context=accepted_edge_details,
            opportunity=opportunity_payload,
            opportunity_gate=opportunity_gate,
            order_size_adjustment=order_size_adjustment,
        )
        execution_plan = self._build_execution_plan(signal, volume, edge_ctx=edge_ctx)
        decision_id = f"dec_{uuid.uuid4().hex}"
        signal_id = f"sig_{uuid.uuid4().hex}"
        rec = await self._maybe_await(self._osm.new_order(
            instance_id=self.instance.id,
            symbol=symbol,
            side="buy",
            order_type=execution_plan["order_type"],
            requested_qty=volume,
            decision_id=decision_id,
            signal_id=signal_id,
        ))
        await self._maybe_await(self._osm.transition(rec.client_order_id, "SENT", "submitted_to_exchange"))
        if execution_plan["order_type"] == "limit":
            result = await self.order_executor.execute_limit_order(
                symbol=symbol,
                side=OrderSide.BUY,
                volume=volume,
                limit_price=execution_plan["price"],
                post_only=bool(execution_plan.get("post_only", False)),
                userref=getattr(rec, "userref", None),
            )
        else:
            result = await self.order_executor.execute_market_order(
                symbol,
                OrderSide.BUY,
                volume,
                userref=getattr(rec, "userref", None),
            )

        if not result.success:
            local_validation_error = self._is_local_order_validation_error(result.error)
            self._record_runtime_event(
                "_last_order_event",
                event="order_rejected",
                symbol=symbol,
                side="buy",
                order_type=execution_plan["order_type"],
                volume=float(volume),
                error=(result.error or "unknown")[:240],
            )
            logger.error(f"❌ Échec ordre Kraken: {result.error}")
            await self._maybe_await(self._osm.transition(
                rec.client_order_id,
                "REJECTED",
                "local_order_validation" if local_validation_error else "exchange_error",
                retries_delta=1,
                last_error_message=result.error,
            ))
            if not local_validation_error:
                await self._kill_switch.record_api_failure(result.error or "unknown")
            return
        self._kill_switch.record_api_success()
        await self._maybe_await(self._osm.transition(
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
        ))
        if result.executed_volume and result.executed_volume < volume:
            await self._maybe_await(self._osm.transition(
                rec.client_order_id,
                "PARTIAL",
                "partial_fill",
                exchange_order_id=result.txid,
                filled_qty=result.executed_volume,
                avg_fill_price=result.executed_price,
            ))
            self._kill_switch.mark_partial(rec.client_order_id, time.time())
        else:
            await self._maybe_await(self._osm.transition(
                rec.client_order_id,
                "FILLED",
                "full_fill",
                exchange_order_id=result.txid,
                filled_qty=result.executed_volume or volume,
                avg_fill_price=result.executed_price,
            ))
            self._kill_switch.clear_partial(rec.client_order_id)

        executed_price = result.executed_price or signal.price
        executed_volume = result.executed_volume or volume
        actual_liquidity = self._normalize_liquidity(result.liquidity)
        self._record_runtime_event(
            "_last_order_event",
            event="order_filled",
            symbol=symbol,
            side="buy",
            order_type=execution_plan["order_type"],
            txid=result.txid,
            requested_volume=float(volume),
            executed_volume=float(executed_volume),
            executed_price=float(executed_price),
            fees=float(result.fees or 0.0),
            paper_mode=bool(getattr(getattr(self.instance, "orchestrator", None), "paper_mode", False)),
        )
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
        notional = max(executed_price * executed_volume, 1e-8)
        fee_bps = (float(result.fees or 0.0) / notional) * 10000.0
        self._record_execution_cost_sample(
            symbol,
            fee_bps=fee_bps,
            slippage_bps=abs(self._slippage_bps(signal.price, executed_price, "buy")),
        )

        stop_price, take_profit, trailing_activation, trailing_gap = self._compute_exit_levels(
            executed_price,
            signal=signal,
        )
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
            persistence = getattr(self.instance, "_persistence", None)
            if persistence is not None and hasattr(persistence, "append_trade_ledger"):
                await self._maybe_await(persistence.append_trade_ledger(
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
                ))
            logger.info(f"✅ Position créée: {position.id}")
            # Immutable audit event
            config_hash = hashlib.sha256(
                str(vars(self.instance.config)).encode("utf-8")
            ).hexdigest()
            if persistence is not None and hasattr(persistence, "append_audit_event"):
                await self._maybe_await(persistence.append_audit_event(
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
                ))
            await self._post_trade_reconcile()

    async def _execute_sell(self, signal: TradingSignal) -> None:
        logger.info(f"💰 Exécution VENTE {signal.symbol}")

        if self.order_executor is None:
            self._record_runtime_event(
                "_last_error_event",
                event="sell_rejected",
                reason="order_executor_missing",
                symbol=signal.symbol,
            )
            logger.error("❌ OrderExecutor non configuré")
            return

        positions = self.instance.get_positions_snapshot()
        open_positions = [p for p in positions if p.get("status") == "open"]
        if not open_positions:
            self._record_runtime_event(
                "_last_decision_event",
                event="sell_ignored",
                reason="no_open_position",
                symbol=signal.symbol,
            )
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
            if not self._passes_order_size_guard(
                symbol=symbol,
                side="sell",
                volume=float(vol),
                price=float(signal.price),
                available_capital=0.0,
                signal_reason=getattr(signal, "reason", None),
            ):
                continue

            # ROB-01: WAL + Idempotency
            if await self._osm.is_duplicate_active(symbol, "sell"):
                logger.warning(f"🔁 Ordre SELL dupliqué bloqué (idempotency): {symbol}")
                continue

            rec = await self._osm.new_order(
                instance_id=self.instance.id,
                symbol=symbol,
                side="sell",
                order_type="market",
                requested_qty=vol,
                signal_id=f"sig_sell_{uuid.uuid4().hex}"
            )
            await self._osm.transition(rec.client_order_id, "SENT", "submitted_to_exchange")

            sl_txid = pos.get("stop_loss_txid")
            result = await self.order_executor.execute_market_order(symbol, OrderSide.SELL, vol, userref=rec.userref)
            if result.success:
                price = result.executed_price or signal.price
                await self.instance.close_position(pos_id, price, sell_txid=result.txid)
                await self._osm.transition(rec.client_order_id, "FILLED", "execution_success", 
                                   exchange_order_id=result.txid, filled_qty=vol, avg_fill_price=price)

            if result.success:
                price = result.executed_price or signal.price
                await self.instance.close_position(pos_id, price, sell_txid=result.txid)
                actual_liquidity = self._normalize_liquidity(result.liquidity)
                self._record_runtime_event(
                    "_last_order_event",
                    event="order_filled",
                    symbol=symbol,
                    side="sell",
                    order_type="market",
                    txid=result.txid,
                    executed_volume=float(vol),
                    executed_price=float(price),
                    fees=float(result.fees or 0.0),
                    paper_mode=bool(getattr(getattr(self.instance, "orchestrator", None), "paper_mode", False)),
                )
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
                await self.instance._persistence.append_trade_ledger(
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
                self._record_runtime_event(
                    "_last_order_event",
                    event="order_rejected",
                    symbol=symbol,
                    side="sell",
                    order_type="market",
                    volume=float(vol),
                    error=(result.error or "unknown")[:240],
                )
                logger.error(f"❌ Échec vente: {result.error}")
                if not self._is_local_order_validation_error(result.error):
                    await self._kill_switch.record_api_failure(result.error or "sell failed")

    async def _post_trade_reconcile(self) -> None:
        """Compare local vs exchange balance snapshots and trigger kill switch on critical drift."""
        if self.order_executor is None:
            return
        exchange_balance = await self.order_executor.get_balance()
        if exchange_balance:
            self._kill_switch.record_balance_freshness(time.time())
        local_total = self.instance.get_current_capital()
        tb = await self.order_executor.get_trade_balance("EUR")
        if isinstance(tb, dict) and "equivalent_balance" in tb:
            exchange_total = float(tb.get("equivalent_balance") or 0.0)
        else:
            exchange_total = float(exchange_balance.get("ZEUR", exchange_balance.get("EUR", 0.0)))
        divergences = self._reconciler.compare_balances(local_total, exchange_total)
        # Deeper parity: fees / realized / unrealized PnL aggregates
        exchange_realized = self._to_optional_float(tb.get("n") if isinstance(tb, dict) else None)
        exchange_unrealized = self._to_optional_float(tb.get("u") if isinstance(tb, dict) else None)
        exchange_fees = self._to_optional_float(tb.get("c") if isinstance(tb, dict) else None)
        local_unrealized = self._compute_unrealized_pnl()
        local_fees = await self._compute_local_fees_aggregate()
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

    def _min_order_volume(self, symbol: str) -> float:
        """Minimum executable volume used by the local executor contract."""
        normalized = self._convert_symbol(symbol).upper().replace("/", "").replace("-", "_")
        raw = os.getenv(f"MIN_ORDER_VOLUME_{normalized}", os.getenv("MIN_ORDER_VOLUME", "0.0001"))
        try:
            value = float(raw)
        except (TypeError, ValueError):
            logger.warning("MIN_ORDER_VOLUME invalide (%r), fallback=0.0001", raw)
            return 0.0001
        return max(0.0, value)

    @staticmethod
    def _is_local_order_validation_error(error: Optional[str]) -> bool:
        text = str(error or "").lower()
        return "volume" in text and ("minimum" in text or "min" in text)

    def _passes_order_size_guard(
        self,
        *,
        symbol: str,
        side: str,
        volume: float,
        price: float,
        available_capital: float,
        signal_reason: Optional[str] = None,
        opportunity: Optional[dict[str, Any]] = None,
    ) -> bool:
        min_volume = self._min_order_volume(symbol)
        if min_volume <= 0.0 or volume >= min_volume:
            return True

        min_notional = min_volume * max(0.0, float(price))
        actual_notional = max(0.0, float(volume)) * max(0.0, float(price))
        self._record_runtime_event(
            "_last_decision_event",
            event=f"{side}_rejected",
            reason="order_size_below_minimum",
            symbol=symbol,
            side=side,
            volume=round(float(volume), 12),
            min_volume=round(float(min_volume), 12),
            order_value=round(float(actual_notional), 8),
            min_order_value=round(float(min_notional), 8),
            available_capital=round(float(available_capital), 8),
            signal_price=float(price),
            signal_reason=signal_reason,
            opportunity=opportunity,
            blocking_condition="volume < min_order_volume",
        )
        logger.info(
            "Signal %s ignore: volume %.12f < minimum %.12f pour %s",
            side.upper(),
            volume,
            min_volume,
            symbol,
        )
        return False

    def _normalize_buy_volume_for_minimum(
        self,
        *,
        symbol: str,
        volume: float,
        price: float,
        available_capital: float,
        max_order_value: float,
        signal_reason: Optional[str] = None,
        opportunity: Optional[dict[str, Any]] = None,
    ) -> Optional[float]:
        min_volume = self._min_order_volume(symbol)
        if min_volume <= 0.0 or volume >= min_volume:
            return volume

        min_notional = min_volume * max(0.0, float(price))
        actual_notional = max(0.0, float(volume)) * max(0.0, float(price))
        fee_buffer = self._load_float_in_range(
            "min_order_fee_buffer_mult",
            "MIN_ORDER_FEE_BUFFER_MULT",
            1.01,
            minimum=1.0,
            maximum=1.10,
        )
        required_cash = min_notional * fee_buffer
        recommended_order = 0.0
        opportunity_status = None
        if isinstance(opportunity, dict):
            opportunity_status = opportunity.get("status")
            try:
                recommended_order = float(opportunity.get("recommended_order_eur") or 0.0)
            except (TypeError, ValueError):
                recommended_order = 0.0

        can_round_up = (
            min_notional > 0.0
            and required_cash <= max(0.0, float(available_capital))
            and min_notional <= max(0.0, float(max_order_value))
            and opportunity_status == "tradable"
            and recommended_order >= min_notional
        )
        if can_round_up:
            self._record_runtime_event(
                "_last_decision_event",
                event="buy_size_adjusted",
                reason="rounded_to_min_order_volume",
                symbol=symbol,
                side="buy",
                original_volume=round(float(volume), 12),
                adjusted_volume=round(float(min_volume), 12),
                original_order_value=round(float(actual_notional), 8),
                adjusted_order_value=round(float(min_notional), 8),
                min_volume=round(float(min_volume), 12),
                available_capital=round(float(available_capital), 8),
                max_order_value=round(float(max_order_value), 8),
                recommended_order_eur=round(float(recommended_order), 8),
                signal_price=float(price),
                signal_reason=signal_reason,
                opportunity=opportunity,
            )
            logger.info(
                "Signal BUY ajuste au minimum executable: %.12f -> %.12f pour %s",
                volume,
                min_volume,
                symbol,
            )
            return min_volume

        self._passes_order_size_guard(
            symbol=symbol,
            side="buy",
            volume=volume,
            price=price,
            available_capital=available_capital,
            signal_reason=signal_reason,
            opportunity=opportunity,
        )
        return None

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

    async def _compute_local_fees_aggregate(self) -> Optional[float]:
        persistence = getattr(self.instance, "_persistence", None)
        if persistence is None or not hasattr(persistence, "get_trade_ledger_metrics"):
            return None
        try:
            metrics = await self._maybe_await(persistence.get_trade_ledger_metrics(self.instance.id))
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

    def _compute_exit_levels(
        self,
        entry_price: float,
        signal: Optional[TradingSignal] = None,
    ) -> tuple[float, float, float, float]:
        atr_pct = self._estimate_atr_pct(entry_price)
        risk_params = self._resolve_dynamic_risk_params(signal, atr_pct) if signal else {
            "atr_sl_mult": self._base_atr_sl_mult,
            "tp_rr": self._base_tp_rr,
            "min_edge_bps": self._base_min_edge_bps,
        }
        sl_pct = max(0.004, atr_pct * risk_params["atr_sl_mult"])
        stop_price = entry_price * (1.0 - sl_pct)
        tp_pct = max(sl_pct * risk_params["tp_rr"], sl_pct * 1.2)
        take_profit = entry_price * (1.0 + tp_pct)
        trailing_activation = entry_price * (1.0 + sl_pct * 0.8)
        trailing_gap = sl_pct * 0.7
        return stop_price, take_profit, trailing_activation, trailing_gap

    def _slippage_bps(self, expected_price: float, executed_price: float, side: str) -> float:
        if expected_price <= 0:
            return 0.0
        raw = ((executed_price - expected_price) / expected_price) * 10000
        return float(raw if side == "buy" else -raw)

    @staticmethod
    def _percentile(values: list[float], percentile: float) -> float:
        if not values:
            return 0.0
        ordered = sorted(float(v) for v in values)
        idx = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * percentile))))
        return ordered[idx]

    def _load_recent_execution_costs(self, symbol: str) -> list[dict[str, float]]:
        return list(self._execution_cost_samples.get(symbol, []))

    def _record_execution_cost_sample(self, symbol: str, fee_bps: float, slippage_bps: float) -> None:
        samples = self._execution_cost_samples.setdefault(symbol, [])
        total_cost_bps = max(0.0, float(fee_bps)) + max(0.0, float(slippage_bps))
        samples.append({
            "fee_bps": max(0.0, float(fee_bps)),
            "slippage_bps": max(0.0, float(slippage_bps)),
            "total_cost_bps": total_cost_bps,
        })
        del samples[:-100]

    def _estimate_edge_context(
        self,
        signal: TradingSignal,
        atr_pct: float,
        risk_params: Optional[dict[str, float]] = None,
    ) -> dict[str, float]:
        metadata = signal.metadata or {}
        symbol = self._convert_symbol(signal.symbol)
        spread_bps = float(metadata.get("spread_bps", 0.0))
        params = risk_params or self._resolve_dynamic_risk_params(signal, atr_pct)
        observed = self._load_recent_execution_costs(symbol)
        fee_samples = [s["fee_bps"] for s in observed]
        slip_samples = [s["slippage_bps"] for s in observed]
        cost_samples = [s["total_cost_bps"] for s in observed]
        fallback_fee_bps = float(metadata.get("fee_bps", self._edge_fallback_fee_bps))
        fallback_slippage_bps = float(
            metadata.get(
                "slippage_bps",
                max(self._edge_fallback_slippage_bps, spread_bps * self._edge_slippage_spread_fraction),
            )
        )
        estimated_fee_bps = self._percentile(fee_samples, self._edge_percentile_target) if fee_samples else fallback_fee_bps
        estimated_slippage_bps = self._percentile(slip_samples, self._edge_percentile_target) if slip_samples else fallback_slippage_bps
        observed_cost_pctl = self._percentile(cost_samples, self._edge_percentile_target) if cost_samples else (estimated_fee_bps + estimated_slippage_bps)
        expected_move_bps = float(metadata.get("expected_move_bps", atr_pct * 10000 * params["tp_rr"]))
        total_cost_bps = spread_bps + estimated_fee_bps + estimated_slippage_bps
        net_edge_bps = expected_move_bps - total_cost_bps
        volatility_edge_weight = float(params.get("volatility_edge_weight", self._volatility_edge_weight))
        cost_buffer_mult = float(params.get("cost_buffer_mult", self._edge_cost_buffer_mult))
        volatility_component_bps = atr_pct * 10000 * volatility_edge_weight
        observed_cost_buffer_bps = observed_cost_pctl * cost_buffer_mult
        adaptive_min_edge_bps = max(params["min_edge_bps"], observed_cost_buffer_bps + volatility_component_bps)
        gross_required_bps = total_cost_bps + adaptive_min_edge_bps
        return {
            "spread_bps": spread_bps,
            "expected_move_bps": expected_move_bps,
            "estimated_fee_bps": estimated_fee_bps,
            "estimated_slippage_bps": estimated_slippage_bps,
            "total_cost_bps": total_cost_bps,
            "net_edge_bps": net_edge_bps,
            "adaptive_min_edge_bps": adaptive_min_edge_bps,
            "volatility_component_bps": volatility_component_bps,
            "observed_cost_buffer_bps": observed_cost_buffer_bps,
            "cost_buffer_multiplier": cost_buffer_mult,
            "gross_required_bps": gross_required_bps,
            "edge_shortfall_bps": max(0.0, gross_required_bps - expected_move_bps),
            "observed_samples": float(len(observed)),
        }

    def _passes_cost_guard(
        self,
        signal_or_edge_ctx: TradingSignal | dict[str, float],
        atr_pct: Optional[float] = None,
        risk_params: Optional[dict[str, float]] = None,
    ) -> bool:
        if isinstance(signal_or_edge_ctx, dict):
            edge_ctx = signal_or_edge_ctx
        else:
            if atr_pct is None:
                raise TypeError("atr_pct is required when passing a TradingSignal")
            edge_ctx = self._estimate_edge_context(signal_or_edge_ctx, atr_pct, risk_params)

        spread_bps = float(edge_ctx.get("spread_bps", 0.0))
        if spread_bps > self._max_spread_bps:
            logger.info("Spread %.1f bps > max %.1f bps", spread_bps, self._max_spread_bps)
            return False
        net_edge_bps = float(edge_ctx.get("net_edge_bps", 0.0))
        min_edge_bps = float(edge_ctx.get("adaptive_min_edge_bps", self._min_edge_bps))
        if net_edge_bps < min_edge_bps:
            logger.info("Edge net %.1f bps < minimum %.1f bps", net_edge_bps, min_edge_bps)
            return False
        return True

    def _resolve_dynamic_risk_params(self, signal: Optional[TradingSignal], atr_pct: float) -> dict[str, float]:
        metadata = (signal.metadata if signal else None) or {}
        regime = str(metadata.get("regime", "RANGE")).upper()
        regime_key = "TREND" if "TREND" in regime else "RANGE"
        preset = self._cost_edge_profiles.get(self._risk_regime_preset, self._cost_edge_profiles["balanced"])
        base = preset[regime_key]

        spread_bps = max(0.0, float(metadata.get("spread_bps", 0.0)))
        vol_ratio = self._compute_recent_volatility_ratio(atr_pct)

        atr_sl_mult = float(base["atr_sl_mult"])
        tp_rr = float(base["tp_rr"])
        min_edge_bps = float(base["min_edge_bps"])
        cost_buffer_mult = float(base.get("cost_buffer_mult", self._edge_cost_buffer_mult))
        volatility_edge_weight = float(base.get("volatility_edge_weight", self._volatility_edge_weight))

        if vol_ratio >= 1.35:
            atr_sl_mult *= 1.12
            tp_rr += 0.22
            min_edge_bps += min(8.0, (vol_ratio - 1.35) * 12.0)
        elif vol_ratio <= 0.75:
            atr_sl_mult *= 0.94
            tp_rr = max(1.1, tp_rr - 0.10)

        spread_rr_floor = 1.20 + min(1.0, spread_bps / 120.0)
        tp_rr = max(tp_rr, spread_rr_floor)
        min_edge_bps += min(12.0, spread_bps * 0.12)

        return {
            "atr_sl_mult": min(6.0, max(0.5, atr_sl_mult)),
            "tp_rr": min(8.0, max(0.5, tp_rr)),
            "min_edge_bps": min(1000.0, max(1.0, min_edge_bps)),
            "cost_buffer_mult": min(3.0, max(0.0, cost_buffer_mult)),
            "volatility_edge_weight": min(5.0, max(0.0, volatility_edge_weight)),
            "cost_edge_profile": self._risk_regime_preset,
        }

    def _compute_recent_volatility_ratio(self, atr_pct: float) -> float:
        baseline = max(self._fallback_atr_pct, 1e-4)
        history = list(getattr(self.instance, "_price_history", []))
        if len(history) >= 10:
            closes = [float(x[1]) for x in history[-min(len(history), 60):]]
            moves = [abs(closes[i] - closes[i - 1]) / max(closes[i - 1], 1e-8) for i in range(1, len(closes))]
            if moves:
                baseline = max(baseline, sum(moves) / len(moves))
        return max(0.25, min(4.0, atr_pct / max(baseline, 1e-8)))

    def _passes_microstructure_hard_filter(self, signal: TradingSignal) -> bool:
        """Hard gate before _execute_buy to reject poor microstructure setups."""
        metadata = signal.metadata or {}
        market_metrics = self._get_market_metrics(signal.symbol)

        spread_bps = self._resolve_spread_bps(metadata, market_metrics)
        latency_ms = self._resolve_signal_latency_ms(signal, metadata)
        expected_slippage_bps = self._resolve_expected_slippage_bps(metadata, spread_bps, market_metrics)

        rejection_reasons: list[str] = []
        if spread_bps > self._max_spread_bps:
            rejection_reasons.append(
                f"spread_bps={spread_bps:.2f} > max_spread_bps={self._max_spread_bps:.2f}"
            )
        if latency_ms > self._max_signal_latency_ms:
            rejection_reasons.append(
                f"signal_latency_ms={latency_ms:.1f} > max_signal_latency_ms={self._max_signal_latency_ms:.1f}"
            )
        # P1: Order Flow Imbalance (OFI) Filter
        try:
            if hasattr(self.instance, "orchestrator") and hasattr(self.instance.orchestrator, "ofi"):
                ofi = self.instance.orchestrator.ofi
                if ofi:
                    side = "buy" if signal.type == SignalType.BUY else "sell"
                    if ofi.is_unbalanced_against(signal.symbol, side):
                        score = ofi.get_ofi_score(signal.symbol)
                        rejection_reasons.append(
                            f"OFI_BLOCK: pressure against {side} (score={score:.2f})"
                        )
        except Exception as exc:
            logger.warning(f"⚠️ Erreur OFI filter: {exc}")

        if expected_slippage_bps > self._max_expected_slippage_bps:
            rejection_reasons.append(
                "expected_slippage_bps="
                f"{expected_slippage_bps:.2f} > max_expected_slippage_bps={self._max_expected_slippage_bps:.2f}"
            )

        if not rejection_reasons:
            return True

        context = {
            "symbol": signal.symbol,
            "reason": signal.reason,
            "price": float(signal.price),
            "spread_bps": spread_bps,
            "signal_latency_ms": latency_ms,
            "expected_slippage_bps": expected_slippage_bps,
            "thresholds": {
                "max_spread_bps": self._max_spread_bps,
                "max_signal_latency_ms": self._max_signal_latency_ms,
                "max_expected_slippage_bps": self._max_expected_slippage_bps,
            },
        }
        if market_metrics is not None:
            context["market_analyzer"] = {
                "spread_avg_pct": market_metrics.spread_avg,
                "volatility_24h_pct": market_metrics.volatility_24h,
                "market_quality": market_metrics.market_quality.name,
                "composite_score": market_metrics.composite_score,
            }

        logger.info("⛔ Hard microstructure reject %s: %s", signal.symbol, "; ".join(rejection_reasons))
        self._last_microstructure_reject_context = {
            **context,
            "rejection_reasons": rejection_reasons,
        }
        self._journal_rejected_microstructure(signal.symbol, rejection_reasons, context)
        return False

    def _get_market_metrics(self, symbol: str) -> Optional[Any]:
        try:
            analyzer = get_market_analyzer()
            return analyzer.analyze_market(symbol)
        except Exception:
            logger.debug("Market analyzer indisponible pour %s", symbol, exc_info=True)
            return None

    @staticmethod
    def _safe_float(value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _resolve_spread_bps(self, metadata: dict[str, Any], market_metrics: Optional[Any]) -> float:
        spread_bps = self._safe_float(metadata.get("spread_bps"), -1.0)
        if spread_bps >= 0:
            return spread_bps
        if market_metrics is not None:
            return max(0.0, float(market_metrics.spread_avg) * 100.0)
        return 0.0

    def _resolve_signal_latency_ms(self, signal: TradingSignal, metadata: dict[str, Any]) -> float:
        candidate_keys = (
            "signal_latency_ms",
            "latency_ms",
            "ws_latency_ms",
            "tick_age_ms",
        )
        for key in candidate_keys:
            parsed = self._safe_float(metadata.get(key), -1.0)
            if parsed >= 0:
                return parsed
        signal_ts = signal.timestamp
        if signal_ts.tzinfo is None:
            signal_ts = signal_ts.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - signal_ts).total_seconds() * 1000.0)

    def _resolve_expected_slippage_bps(
        self,
        metadata: dict[str, Any],
        spread_bps: float,
        market_metrics: Optional[Any],
    ) -> float:
        expected_slippage = self._safe_float(metadata.get("expected_slippage_bps"), -1.0)
        if expected_slippage >= 0:
            return expected_slippage
        explicit_slippage = self._safe_float(metadata.get("slippage_bps"), -1.0)
        if explicit_slippage >= 0:
            return explicit_slippage
        if market_metrics is not None:
            return max(4.0, spread_bps * 0.45, float(market_metrics.spread_avg) * 60.0)
        return max(4.0, spread_bps * 0.35)

    def _journal_rejected_microstructure(
        self,
        symbol: str,
        reasons: list[str],
        context: dict[str, Any],
    ) -> None:
        service = getattr(self.instance, "decision_journal_service", None)
        if service is None or not hasattr(service, "rejected_opportunity"):
            return
        try:
            service.rejected_opportunity(
                reason="microstructure_hard_filter",
                source="signal_handler_async",
                symbol=symbol,
                context={**context, "reasons": reasons},
            )
        except Exception:
            logger.debug("Decision journal indisponible pour rejet microstructure", exc_info=True)

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
        # Phase 5: Force Maker Only (Ultra Optimization)
        force_maker = getattr(self.instance.config, "force_maker_only", os.getenv("FORCE_MAKER_ONLY", "false").lower() == "true")
        
        prefer_limit = (low_urgency and has_edge and rec.get("order_type") == "limit") or force_maker
        if prefer_limit:
            # Use provided limit price or current signal price
            price = float(metadata.get("limit_price") or signal.price)
            reason = "force_maker_only_enabled" if force_maker else rec.get("reason", "low_urgency_edge")
            return {"order_type": "limit", "post_only": True, "price": price, "reason": reason}
            
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
