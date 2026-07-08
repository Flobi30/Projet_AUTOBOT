"""Paper-only mean-reversion shadow lab.

This module evaluates lightweight Bollinger/z-score mean-reversion variants on
observed prices.  It never places orders, never writes to the official paper
ledger, and never enables live trading.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from .pair_strategy_health import symbol_key
from .shadow_cost_bridge import conservative_shadow_cost_defaults


_SHADOW_COST_DEFAULTS = conservative_shadow_cost_defaults()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.getenv(name)
    try:
        value = float(raw) if raw not in (None, "") else default
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    try:
        value = int(float(raw)) if raw not in (None, "") else default
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _optional_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return max(minimum, min(maximum, float(value)))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if value:
        return str(value)
    return _utc_now()


@dataclass(frozen=True)
class MeanReversionShadowConfig:
    enabled: bool = True
    continue_in_live: bool = True
    db_path: str = "data/mean_reversion_shadow_lab.db"
    virtual_capital_per_variant: float = 100.0
    min_tick_seconds: int = 10
    persist_interval_seconds: int = 60
    max_variants_per_symbol: int = 4
    max_price_samples: int = 512
    min_order_eur: float = 5.0
    fee_bps_per_side: float = _SHADOW_COST_DEFAULTS.fee_bps_per_side
    slippage_bps_per_side: float = _SHADOW_COST_DEFAULTS.slippage_bps_per_side
    min_samples_for_signal: int = 24
    min_closed_trades_for_signal: int = 5
    candidate_score: float = 70.0
    candidate_profit_factor: float = 1.25
    weak_score: float = 40.0

    @classmethod
    def from_env(cls) -> "MeanReversionShadowConfig":
        cost_defaults = conservative_shadow_cost_defaults()
        return cls(
            enabled=_env_bool("MEAN_REVERSION_SHADOW_LAB_ENABLED", True),
            continue_in_live=_env_bool("MEAN_REVERSION_SHADOW_CONTINUE_IN_LIVE", True),
            db_path=os.getenv("MEAN_REVERSION_SHADOW_DB_PATH", "data/mean_reversion_shadow_lab.db"),
            virtual_capital_per_variant=_env_float("MEAN_REVERSION_SHADOW_VIRTUAL_CAPITAL_EUR", 100.0, 10.0, 1_000_000.0),
            min_tick_seconds=_env_int("MEAN_REVERSION_SHADOW_MIN_TICK_SECONDS", 10, 0, 86_400),
            persist_interval_seconds=_env_int("MEAN_REVERSION_SHADOW_PERSIST_INTERVAL_SECONDS", 60, 1, 86_400),
            max_variants_per_symbol=_env_int("MEAN_REVERSION_SHADOW_MAX_VARIANTS_PER_SYMBOL", 4, 1, 20),
            max_price_samples=_env_int("MEAN_REVERSION_SHADOW_MAX_PRICE_SAMPLES", 512, 64, 10_000),
            min_order_eur=_env_float("MEAN_REVERSION_SHADOW_MIN_ORDER_EUR", 5.0, 0.0, 10_000.0),
            fee_bps_per_side=_env_float(
                "MEAN_REVERSION_SHADOW_FEE_BPS_PER_SIDE",
                cost_defaults.fee_bps_per_side,
                0.0,
                500.0,
            ),
            slippage_bps_per_side=_env_float(
                "MEAN_REVERSION_SHADOW_SLIPPAGE_BPS_PER_SIDE",
                cost_defaults.slippage_bps_per_side,
                0.0,
                500.0,
            ),
            min_samples_for_signal=_env_int("MEAN_REVERSION_SHADOW_MIN_SAMPLES", 24, 1, 100_000),
            min_closed_trades_for_signal=_env_int("MEAN_REVERSION_SHADOW_MIN_CLOSED_TRADES", 5, 1, 100_000),
            candidate_score=_env_float("MEAN_REVERSION_SHADOW_CANDIDATE_SCORE", 70.0, 0.0, 100.0),
            candidate_profit_factor=_env_float("MEAN_REVERSION_SHADOW_CANDIDATE_PF", 1.25, 0.01, 100.0),
            weak_score=_env_float("MEAN_REVERSION_SHADOW_WEAK_SCORE", 40.0, 0.0, 100.0),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "continue_in_live": self.continue_in_live,
            "db_path": self.db_path,
            "virtual_capital_per_variant": self.virtual_capital_per_variant,
            "min_tick_seconds": self.min_tick_seconds,
            "persist_interval_seconds": self.persist_interval_seconds,
            "max_variants_per_symbol": self.max_variants_per_symbol,
            "max_price_samples": self.max_price_samples,
            "min_order_eur": self.min_order_eur,
            "fee_bps_per_side": self.fee_bps_per_side,
            "slippage_bps_per_side": self.slippage_bps_per_side,
            "effective_cost_bps_per_side": self.fee_bps_per_side + self.slippage_bps_per_side,
            "cost_model_source": _SHADOW_COST_DEFAULTS.source,
            "min_samples_for_signal": self.min_samples_for_signal,
            "min_closed_trades_for_signal": self.min_closed_trades_for_signal,
            "candidate_score": self.candidate_score,
            "candidate_profit_factor": self.candidate_profit_factor,
            "weak_score": self.weak_score,
        }


@dataclass(frozen=True)
class MeanReversionVariant:
    name: str
    description: str
    window: int = 32
    entry_z: float = 2.0
    exit_z: float = 0.15
    stop_z: float = 3.5
    atr_window: int = 16
    min_bandwidth_bps: float = 8.0
    max_bandwidth_bps: float = 250.0
    max_abs_trend_bps: float = 120.0
    min_atr_bps: float = 3.0
    max_atr_bps: float = 220.0
    min_expected_net_edge_bps: float = 6.0
    position_pct: float = 0.35
    cooldown_ticks: int = 3

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "window": self.window,
            "entry_z": self.entry_z,
            "exit_z": self.exit_z,
            "stop_z": self.stop_z,
            "atr_window": self.atr_window,
            "min_bandwidth_bps": self.min_bandwidth_bps,
            "max_bandwidth_bps": self.max_bandwidth_bps,
            "max_abs_trend_bps": self.max_abs_trend_bps,
            "min_atr_bps": self.min_atr_bps,
            "max_atr_bps": self.max_atr_bps,
            "min_expected_net_edge_bps": self.min_expected_net_edge_bps,
            "position_pct": self.position_pct,
            "cooldown_ticks": self.cooldown_ticks,
        }


DEFAULT_MEAN_REVERSION_VARIANTS: tuple[MeanReversionVariant, ...] = (
    MeanReversionVariant(
        name="mr_bollinger_balanced",
        description="Balanced Bollinger/z-score snapback in range-like markets.",
        window=32,
        entry_z=2.0,
        exit_z=0.10,
        stop_z=3.6,
        max_abs_trend_bps=120.0,
        position_pct=0.35,
    ),
    MeanReversionVariant(
        name="mr_deep_snapback",
        description="Waits for deeper deviation before entering.",
        window=48,
        entry_z=2.5,
        exit_z=0.05,
        stop_z=4.0,
        min_bandwidth_bps=10.0,
        max_abs_trend_bps=150.0,
        min_expected_net_edge_bps=10.0,
        position_pct=0.30,
    ),
    MeanReversionVariant(
        name="mr_fast_probe",
        description="Paper-only faster snapback probe; smaller allocation, still cost-aware.",
        window=20,
        entry_z=1.25,
        exit_z=0.20,
        stop_z=3.2,
        max_abs_trend_bps=95.0,
        min_expected_net_edge_bps=4.0,
        position_pct=0.18,
    ),
    MeanReversionVariant(
        name="mr_range_probe",
        description="Paper-only range probe for mild deviations after cost filter.",
        window=28,
        entry_z=1.15,
        exit_z=0.15,
        stop_z=3.0,
        min_bandwidth_bps=4.0,
        max_bandwidth_bps=150.0,
        max_abs_trend_bps=70.0,
        min_atr_bps=1.0,
        min_expected_net_edge_bps=3.0,
        position_pct=0.15,
    ),
)


@dataclass
class MeanReversionPosition:
    id: str
    entry_price: float
    volume: float
    notional: float
    entry_fee: float
    opened_at: str
    entry_z: float
    mean_at_entry: float
    std_at_entry: float
    opportunity: dict[str, Any] = field(default_factory=dict)
    entry_features: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "entry_price": self.entry_price,
            "volume": self.volume,
            "notional": self.notional,
            "entry_fee": self.entry_fee,
            "opened_at": self.opened_at,
            "entry_z": self.entry_z,
            "mean_at_entry": self.mean_at_entry,
            "std_at_entry": self.std_at_entry,
            "opportunity": dict(self.opportunity),
            "entry_features": dict(self.entry_features),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MeanReversionPosition":
        return cls(
            id=str(payload.get("id") or ""),
            entry_price=_safe_float(payload.get("entry_price")),
            volume=_safe_float(payload.get("volume")),
            notional=_safe_float(payload.get("notional")),
            entry_fee=_safe_float(payload.get("entry_fee")),
            opened_at=str(payload.get("opened_at") or _utc_now()),
            entry_z=_safe_float(payload.get("entry_z")),
            mean_at_entry=_safe_float(payload.get("mean_at_entry")),
            std_at_entry=_safe_float(payload.get("std_at_entry")),
            opportunity=dict(payload.get("opportunity") or {}) if isinstance(payload.get("opportunity"), Mapping) else {},
            entry_features=dict(payload.get("entry_features") or {}) if isinstance(payload.get("entry_features"), Mapping) else {},
        )


@dataclass
class MeanReversionState:
    symbol: str
    variant: str
    cash: float
    created_at: str
    realized_pnl: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    fees: float = 0.0
    wins: int = 0
    losses: int = 0
    opened_trades: int = 0
    closed_trades: int = 0
    sample_count: int = 0
    peak_equity: float = 0.0
    max_drawdown_eur: float = 0.0
    last_price: Optional[float] = None
    last_tick_at: Optional[str] = None
    updated_at: str = field(default_factory=_utc_now)
    prices: list[float] = field(default_factory=list)
    open_position: Optional[MeanReversionPosition] = None
    last_signal: dict[str, Any] = field(default_factory=dict)
    last_decision: dict[str, Any] = field(default_factory=dict)
    cooldown_until_sample: int = 0


class MeanReversionShadowLab:
    """Runs virtual mean-reversion variants on observed prices."""

    def __init__(
        self,
        config: MeanReversionShadowConfig | None = None,
        variants: Iterable[MeanReversionVariant] | None = None,
    ) -> None:
        self.config = config or MeanReversionShadowConfig.from_env()
        self.variants = tuple(variants or DEFAULT_MEAN_REVERSION_VARIANTS)
        self._lock = threading.RLock()
        self._states: dict[tuple[str, str], MeanReversionState] = {}
        self._last_update_mono: dict[str, float] = {}
        self._last_persist_mono: float = 0.0
        self._loaded = False

    def on_price_tick(
        self,
        *,
        symbol: str,
        price: float,
        timestamp: Any = None,
        opportunity_context: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        symbol = symbol_key(symbol)
        price = _safe_float(price)
        if not self.config.enabled:
            return {"updated": False, "reason": "disabled"}
        if price <= 0.0 or symbol == "UNKNOWN" or not math.isfinite(price):
            return {"updated": False, "reason": "invalid_tick"}

        now = time.monotonic()
        with self._lock:
            self._ensure_loaded()
            existing = any(key[0] == symbol for key in self._states)
            last = self._last_update_mono.get(symbol)
            if existing and last is not None and now - last < self.config.min_tick_seconds:
                self._mark_last_price(symbol, price, timestamp)
                return {"updated": False, "reason": "throttled"}
            self._last_update_mono[symbol] = now

            updated = 0
            opportunity = _opportunity_context(opportunity_context)
            for variant in self.variants[: self.config.max_variants_per_symbol]:
                state = self._state(symbol, variant.name, price)
                self._run_variant_tick(state, variant, price, _iso(timestamp), opportunity)
                updated += 1

            if now - self._last_persist_mono >= self.config.persist_interval_seconds:
                self._persist_all()
                self._last_persist_mono = now

        return {"updated": True, "symbol": symbol, "variants": updated}

    def build_snapshot(self, *, symbols: Optional[Iterable[Any]] = None) -> dict[str, Any]:
        with self._lock:
            self._ensure_loaded()
            allowed = {symbol_key(sym) for sym in symbols or [] if symbol_key(sym) != "UNKNOWN"}
            states = list(self._states.values())
            if allowed:
                states = [state for state in states if state.symbol in allowed]

            by_symbol: dict[str, dict[str, Any]] = {}
            for state in states:
                metrics = self._metrics(state)
                bucket = by_symbol.setdefault(
                    state.symbol,
                    {
                        "symbol": state.symbol,
                        "engine": "mean_reversion",
                        "variants": [],
                        "best_variant": None,
                        "updated_at": None,
                    },
                )
                bucket["variants"].append(metrics)
                if bucket["best_variant"] is None or metrics["score"] > bucket["best_variant"]["score"]:
                    bucket["best_variant"] = metrics
                if bucket["updated_at"] is None or str(state.updated_at) > str(bucket["updated_at"]):
                    bucket["updated_at"] = state.updated_at

            rows = []
            for row in by_symbol.values():
                row["variants"].sort(key=lambda item: item["score"], reverse=True)
                rows.append(row)
            rows.sort(key=lambda item: (-(item["best_variant"] or {}).get("score", 0.0), item["symbol"]))

            total_closed = sum(int(self._metrics(state)["closed_trades"]) for state in states)
            total_open = sum(1 for state in states if state.open_position is not None)
            total_pnl = sum(float(self._metrics(state)["net_pnl_eur"]) for state in states)
            candidate_count = sum(
                1
                for row in rows
                if row.get("best_variant") and row["best_variant"].get("status") == "candidate"
            )
            return {
                "timestamp": _utc_now(),
                "mode": "paper_shadow",
                "engine": "mean_reversion",
                "paper_only": True,
                "enabled": self.config.enabled,
                "live_promotion_allowed": False,
                "writes_official_paper_ledger": False,
                "config": self.config.to_dict(),
                "variants": [variant.to_dict() for variant in self.variants[: self.config.max_variants_per_symbol]],
                "summary": {
                    "symbols": len(rows),
                    "variant_states": len(states),
                    "open_shadow_positions": total_open,
                    "closed_shadow_trades": total_closed,
                    "net_shadow_pnl_eur": round(total_pnl, 4),
                    "candidate_symbols": candidate_count,
                },
                "symbols": rows,
                "by_symbol": {row["symbol"]: row for row in rows},
                "message": (
                    "Mean-reversion shadow lab: isolated virtual Bollinger/z-score tests from observed prices. "
                    "These results do not place orders and do not change official paper PnL."
                ),
            }

    def evidence_by_symbol(self) -> dict[str, Any]:
        snapshot = self.build_snapshot()
        return snapshot.get("by_symbol", {})

    def flush(self) -> None:
        with self._lock:
            self._ensure_loaded()
            self._persist_all()
            self._last_persist_mono = time.monotonic()

    def _run_variant_tick(
        self,
        state: MeanReversionState,
        variant: MeanReversionVariant,
        price: float,
        timestamp: str,
        opportunity: Mapping[str, Any],
    ) -> None:
        state.last_price = price
        state.last_tick_at = timestamp
        state.sample_count += 1
        state.prices.append(price)
        if len(state.prices) > self.config.max_price_samples:
            del state.prices[: len(state.prices) - self.config.max_price_samples]

        features = self._features(state.prices, variant)
        if state.open_position is not None:
            self._maybe_close_position(state, variant, features, price, timestamp)
        if state.open_position is None:
            self._maybe_open_position(state, variant, features, price, timestamp, opportunity)

        equity = self._equity(state, price)
        state.peak_equity = max(state.peak_equity or self.config.virtual_capital_per_variant, equity)
        state.max_drawdown_eur = max(state.max_drawdown_eur, state.peak_equity - equity)
        state.updated_at = timestamp

    def _maybe_open_position(
        self,
        state: MeanReversionState,
        variant: MeanReversionVariant,
        features: Mapping[str, Any],
        price: float,
        timestamp: str,
        opportunity: Mapping[str, Any],
    ) -> None:
        if state.sample_count < state.cooldown_until_sample:
            self._set_rejected(state, variant, features, price, timestamp, "cooldown")
            return
        should_buy, reason = self._entry_decision(variant, features, state.sample_count)
        state.last_signal = {
            "timestamp": timestamp,
            "symbol": state.symbol,
            "variant": variant.name,
            "side": "buy" if should_buy else "hold",
            "price": price,
            "reason": reason,
            "features": dict(features),
        }
        if not should_buy:
            self._set_rejected(state, variant, features, price, timestamp, reason)
            return

        notional = min(
            state.cash * _clamp(variant.position_pct, 0.01, 0.95),
            self.config.virtual_capital_per_variant * _clamp(variant.position_pct, 0.01, 0.95),
        )
        if notional < self.config.min_order_eur:
            self._set_rejected(state, variant, features, price, timestamp, "notional_below_min_order")
            return
        entry_fee = self._leg_cost(notional)
        if state.cash < notional + entry_fee:
            self._set_rejected(state, variant, features, price, timestamp, "insufficient_shadow_cash")
            return
        mean = _safe_float(features.get("mean"), price)
        std = max(_safe_float(features.get("std")), 1e-12)
        state.cash -= notional + entry_fee
        state.opened_trades += 1
        state.open_position = MeanReversionPosition(
            id=self._position_id(state.symbol, state.variant, state.opened_trades, timestamp),
            entry_price=price,
            volume=notional / max(price, 1e-12),
            notional=notional,
            entry_fee=entry_fee,
            opened_at=timestamp,
            entry_z=_safe_float(features.get("z_score")),
            mean_at_entry=mean,
            std_at_entry=std,
            opportunity=dict(opportunity),
            entry_features=dict(features),
        )
        state.last_decision = {
            "timestamp": timestamp,
            "status": "opened",
            "reason": reason,
            "notional_eur": round(notional, 4),
            "features": dict(features),
        }

    def _set_rejected(
        self,
        state: MeanReversionState,
        variant: MeanReversionVariant,
        features: Mapping[str, Any],
        price: float,
        timestamp: str,
        reason: str,
    ) -> None:
        state.last_signal = {
            "timestamp": timestamp,
            "symbol": state.symbol,
            "variant": variant.name,
            "side": "hold",
            "price": price,
            "reason": reason,
            "features": dict(features),
        }
        state.last_decision = {
            "timestamp": timestamp,
            "status": "rejected",
            "reason": reason,
            "features": dict(features),
        }

    def _maybe_close_position(
        self,
        state: MeanReversionState,
        variant: MeanReversionVariant,
        features: Mapping[str, Any],
        price: float,
        timestamp: str,
    ) -> None:
        pos = state.open_position
        if pos is None:
            return
        should_close, reason = self._exit_decision(pos, variant, features, price)
        if should_close:
            self._close_position(state, pos, price, reason, timestamp)
            state.cooldown_until_sample = state.sample_count + max(0, variant.cooldown_ticks)
            state.last_decision = {
                "timestamp": timestamp,
                "status": "closed",
                "reason": reason,
                "features": dict(features),
            }
        else:
            state.last_decision = {
                "timestamp": timestamp,
                "status": "holding",
                "reason": reason,
                "features": dict(features),
            }

    def _entry_decision(
        self,
        variant: MeanReversionVariant,
        features: Mapping[str, Any],
        sample_count: int,
    ) -> tuple[bool, str]:
        if sample_count < self.config.min_samples_for_signal:
            return False, "warmup"
        if sample_count < int(features.get("required_samples") or 0):
            return False, "indicator_warmup"
        if not features.get("ready"):
            return False, str(features.get("reason") or "not_ready")
        atr_bps = _safe_float(features.get("atr_bps"))
        if atr_bps < variant.min_atr_bps:
            return False, "atr_below_min"
        if atr_bps > variant.max_atr_bps:
            return False, "atr_above_max"
        bandwidth_bps = _safe_float(features.get("bandwidth_bps"))
        if bandwidth_bps < variant.min_bandwidth_bps:
            return False, "bandwidth_below_min"
        if bandwidth_bps > variant.max_bandwidth_bps:
            return False, "bandwidth_above_max"
        z_score = _safe_float(features.get("z_score"))
        if z_score > -abs(variant.entry_z):
            return False, "zscore_not_extreme"
        expected_net_bps = _safe_float(features.get("expected_net_edge_bps"))
        if expected_net_bps < variant.min_expected_net_edge_bps:
            return False, "expected_edge_below_cost"
        trend_bps = abs(_safe_float(features.get("trend_bps")))
        if trend_bps > variant.max_abs_trend_bps:
            return False, "trend_too_strong_for_mean_reversion"
        return True, "lower_band_snapback_cost_aware"

    def _exit_decision(
        self,
        pos: MeanReversionPosition,
        variant: MeanReversionVariant,
        features: Mapping[str, Any],
        price: float,
    ) -> tuple[bool, str]:
        z_score = _safe_float(features.get("z_score"))
        if z_score >= -abs(variant.exit_z):
            return True, "mean_reversion_exit"
        stop_price = pos.entry_price - (abs(variant.stop_z) * max(pos.std_at_entry, 1e-12))
        if price <= stop_price:
            return True, "zscore_stop"
        mean = _safe_float(features.get("mean"))
        if mean > 0.0 and price >= mean:
            return True, "mean_touch_exit"
        return False, "waiting_snapback"

    def _features(self, prices: list[float], variant: MeanReversionVariant) -> dict[str, Any]:
        required = max(variant.window + 1, variant.atr_window + 1)
        if len(prices) < required:
            return {
                "ready": False,
                "reason": "indicator_warmup",
                "samples": len(prices),
                "required_samples": required,
            }
        current_price = prices[-1]
        window_prices = prices[-variant.window - 1 : -1]
        mean = sum(window_prices) / len(window_prices)
        variance = sum((price - mean) ** 2 for price in window_prices) / max(len(window_prices), 1)
        std = math.sqrt(max(variance, 0.0))
        if mean <= 0.0 or std <= 0.0:
            return {
                "ready": False,
                "reason": "flat_or_invalid_std",
                "samples": len(prices),
                "required_samples": required,
                "mean": mean,
                "std": std,
            }
        returns_bps = [
            ((prices[idx] / max(prices[idx - 1], 1e-12)) - 1.0) * 10000.0
            for idx in range(1, len(prices))
        ]
        atr_values = returns_bps[-variant.atr_window :]
        atr_bps = sum(abs(value) for value in atr_values) / max(len(atr_values), 1)
        trend_base = window_prices[0]
        trend_bps = ((current_price / max(trend_base, 1e-12)) - 1.0) * 10000.0
        z_score = (current_price - mean) / max(std, 1e-12)
        expected_gross_bps = max(0.0, ((mean / max(current_price, 1e-12)) - 1.0) * 10000.0)
        estimated_round_trip_cost_bps = (self.config.fee_bps_per_side + self.config.slippage_bps_per_side) * 2.0
        expected_net_edge_bps = expected_gross_bps - estimated_round_trip_cost_bps
        return {
            "ready": True,
            "samples": len(prices),
            "required_samples": required,
            "mean": mean,
            "std": std,
            "z_score": round(z_score, 4),
            "lower_band": mean - (abs(variant.entry_z) * std),
            "upper_band": mean + (abs(variant.entry_z) * std),
            "bandwidth_bps": round((std / mean) * 10000.0, 4),
            "trend_bps": round(trend_bps, 4),
            "atr_bps": round(atr_bps, 4),
            "expected_gross_edge_bps": round(expected_gross_bps, 4),
            "estimated_round_trip_cost_bps": round(estimated_round_trip_cost_bps, 4),
            "expected_net_edge_bps": round(expected_net_edge_bps, 4),
        }

    def _close_position(
        self,
        state: MeanReversionState,
        position: MeanReversionPosition,
        exit_price: float,
        reason: str,
        timestamp: str,
    ) -> None:
        exit_notional = position.volume * exit_price
        exit_fee = self._leg_cost(exit_notional)
        gross = (exit_price - position.entry_price) * position.volume
        net = gross - position.entry_fee - exit_fee
        state.cash += exit_notional - exit_fee
        state.realized_pnl += net
        state.fees += position.entry_fee + exit_fee
        state.closed_trades += 1
        if net > 0.0:
            state.gross_profit += net
            state.wins += 1
        else:
            state.gross_loss += abs(net)
            state.losses += 1
        state.open_position = None
        self._record_trade(state, position, exit_price, exit_fee, net, reason, timestamp)

    def _metrics(self, state: MeanReversionState) -> dict[str, Any]:
        last_price = state.last_price or (state.prices[-1] if state.prices else 0.0)
        unrealized = self._unrealized_pnl(state, last_price)
        equity = self._equity(state, last_price)
        net_pnl = equity - self.config.virtual_capital_per_variant
        profit_factor = None
        if state.gross_loss > 0.0:
            profit_factor = state.gross_profit / state.gross_loss
        elif state.gross_profit > 0.0:
            profit_factor = None
        win_rate = state.wins / state.closed_trades if state.closed_trades else 0.0
        score = self._score(
            net_pnl=net_pnl,
            realized_pnl=state.realized_pnl,
            profit_factor=profit_factor,
            win_rate=win_rate,
            max_drawdown_eur=state.max_drawdown_eur,
            closed_trades=state.closed_trades,
            sample_count=state.sample_count,
        )
        status = self._status(score, net_pnl, profit_factor, state.closed_trades, state.sample_count)
        return {
            "symbol": state.symbol,
            "engine": "mean_reversion",
            "variant": state.variant,
            "status": status,
            "score": round(score, 2),
            "virtual_capital_eur": round(self.config.virtual_capital_per_variant, 2),
            "cash_eur": round(state.cash, 4),
            "equity_eur": round(equity, 4),
            "net_pnl_eur": round(net_pnl, 4),
            "realized_pnl_eur": round(state.realized_pnl, 4),
            "unrealized_pnl_eur": round(unrealized, 4),
            "gross_profit_eur": round(state.gross_profit, 4),
            "gross_loss_eur": round(state.gross_loss, 4),
            "profit_factor": round(profit_factor, 4) if profit_factor is not None else None,
            "win_rate": round(win_rate * 100.0, 2),
            "opened_trades": int(state.opened_trades),
            "closed_trades": int(state.closed_trades),
            "open_positions": 1 if state.open_position else 0,
            "sample_count": int(state.sample_count),
            "max_drawdown_eur": round(state.max_drawdown_eur, 4),
            "max_drawdown_pct": round((state.max_drawdown_eur / max(self.config.virtual_capital_per_variant, 1e-9)) * 100.0, 4),
            "fees_eur": round(state.fees, 4),
            "last_price": round(last_price, 10) if last_price else None,
            "last_tick_at": state.last_tick_at,
            "updated_at": state.updated_at,
            "last_signal": dict(state.last_signal),
            "last_decision": dict(state.last_decision),
            "evidence_source": "mean_reversion_shadow_lab",
        }

    def _score(
        self,
        *,
        net_pnl: float,
        realized_pnl: float,
        profit_factor: Optional[float],
        win_rate: float,
        max_drawdown_eur: float,
        closed_trades: int,
        sample_count: int,
    ) -> float:
        capital = max(self.config.virtual_capital_per_variant, 1e-9)
        net_return_pct = (net_pnl / capital) * 100.0
        realized_return_pct = (realized_pnl / capital) * 100.0
        pf_component = 0.0
        if profit_factor is not None:
            pf_component = max(-30.0, min(30.0, (profit_factor - 1.0) * 20.0))
        win_component = (win_rate - 0.50) * 18.0 if closed_trades > 0 else 0.0
        dd_penalty = min(30.0, (max_drawdown_eur / capital) * 130.0)
        evidence = min(1.0, sample_count / max(self.config.min_samples_for_signal, 1))
        raw = 50.0 + (net_return_pct * 5.0) + (realized_return_pct * 2.0) + pf_component + win_component - dd_penalty
        return _clamp((50.0 * (1.0 - evidence)) + (raw * evidence))

    def _status(
        self,
        score: float,
        net_pnl: float,
        profit_factor: Optional[float],
        closed_trades: int,
        sample_count: int,
    ) -> str:
        if sample_count < self.config.min_samples_for_signal or closed_trades < self.config.min_closed_trades_for_signal:
            return "learning"
        if (
            score >= self.config.candidate_score
            and net_pnl > 0.0
            and (profit_factor is None or profit_factor >= self.config.candidate_profit_factor)
        ):
            return "candidate"
        if score <= self.config.weak_score or net_pnl < 0.0:
            return "weak"
        return "watch"

    def _state(self, symbol: str, variant: str, price: float) -> MeanReversionState:
        key = (symbol, variant)
        state = self._states.get(key)
        if state is None:
            state = MeanReversionState(
                symbol=symbol,
                variant=variant,
                cash=self.config.virtual_capital_per_variant,
                created_at=_utc_now(),
                peak_equity=self.config.virtual_capital_per_variant,
                last_price=price,
            )
            self._states[key] = state
        return state

    def _leg_cost(self, notional: float) -> float:
        return max(0.0, float(notional) * ((self.config.fee_bps_per_side + self.config.slippage_bps_per_side) / 10000.0))

    def _unrealized_pnl(self, state: MeanReversionState, price: float) -> float:
        pos = state.open_position
        if pos is None:
            return 0.0
        exit_notional = pos.volume * price
        exit_fee = self._leg_cost(exit_notional)
        return ((price - pos.entry_price) * pos.volume) - pos.entry_fee - exit_fee

    def _equity(self, state: MeanReversionState, price: float) -> float:
        pos = state.open_position
        if pos is None:
            return state.cash
        exit_notional = pos.volume * price
        return state.cash + exit_notional - self._leg_cost(exit_notional)

    def _mark_last_price(self, symbol: str, price: float, timestamp: Any) -> None:
        tick_at = _iso(timestamp)
        for (state_symbol, _variant), state in self._states.items():
            if state_symbol == symbol:
                state.last_price = price
                state.last_tick_at = tick_at
                state.updated_at = tick_at

    @staticmethod
    def _position_id(symbol: str, variant: str, sequence: int, timestamp: str) -> str:
        raw = f"{symbol}|{variant}|{sequence}|{timestamp}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._init_db()
        self._load_states()
        self._loaded = True

    def _connect(self) -> sqlite3.Connection:
        path = Path(self.config.db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS mean_reversion_shadow_state (
                    symbol TEXT NOT NULL,
                    variant TEXT NOT NULL,
                    cash REAL NOT NULL,
                    realized_pnl REAL NOT NULL,
                    gross_profit REAL NOT NULL,
                    gross_loss REAL NOT NULL,
                    fees REAL NOT NULL,
                    wins INTEGER NOT NULL,
                    losses INTEGER NOT NULL,
                    opened_trades INTEGER NOT NULL,
                    closed_trades INTEGER NOT NULL,
                    sample_count INTEGER NOT NULL,
                    peak_equity REAL NOT NULL,
                    max_drawdown_eur REAL NOT NULL,
                    last_price REAL,
                    last_tick_at TEXT,
                    prices_json TEXT NOT NULL,
                    open_position_json TEXT NOT NULL,
                    last_signal_json TEXT NOT NULL,
                    last_decision_json TEXT NOT NULL,
                    cooldown_until_sample INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (symbol, variant)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS mean_reversion_shadow_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    variant TEXT NOT NULL,
                    position_id TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    exit_price REAL NOT NULL,
                    volume REAL NOT NULL,
                    notional REAL NOT NULL,
                    fees REAL NOT NULL,
                    realized_pnl REAL NOT NULL,
                    reason TEXT NOT NULL,
                    opened_at TEXT NOT NULL,
                    closed_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    opportunity_score REAL,
                    opportunity_status TEXT,
                    opportunity_reason TEXT,
                    opportunity_components TEXT
                )
                """
            )
            _ensure_trade_metadata_columns(conn, "mean_reversion_shadow_trades")

    def _load_states(self) -> None:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM mean_reversion_shadow_state").fetchall()
        for row in rows:
            try:
                prices_raw = json.loads(row["prices_json"] or "[]")
            except json.JSONDecodeError:
                prices_raw = []
            try:
                position_raw = json.loads(row["open_position_json"] or "null")
            except json.JSONDecodeError:
                position_raw = None
            try:
                last_signal = json.loads(row["last_signal_json"] or "{}")
            except json.JSONDecodeError:
                last_signal = {}
            try:
                last_decision = json.loads(row["last_decision_json"] or "{}")
            except json.JSONDecodeError:
                last_decision = {}
            position = MeanReversionPosition.from_dict(position_raw) if isinstance(position_raw, Mapping) else None
            state = MeanReversionState(
                symbol=str(row["symbol"]),
                variant=str(row["variant"]),
                cash=float(row["cash"]),
                realized_pnl=float(row["realized_pnl"]),
                gross_profit=float(row["gross_profit"]),
                gross_loss=float(row["gross_loss"]),
                fees=float(row["fees"]),
                wins=int(row["wins"]),
                losses=int(row["losses"]),
                opened_trades=int(row["opened_trades"]),
                closed_trades=int(row["closed_trades"]),
                sample_count=int(row["sample_count"]),
                peak_equity=float(row["peak_equity"]),
                max_drawdown_eur=float(row["max_drawdown_eur"]),
                last_price=_safe_float(row["last_price"], 0.0) or None,
                last_tick_at=row["last_tick_at"],
                created_at=str(row["created_at"]),
                updated_at=str(row["updated_at"]),
                prices=[_safe_float(item) for item in prices_raw if _safe_float(item) > 0.0],
                open_position=position,
                last_signal=last_signal if isinstance(last_signal, dict) else {},
                last_decision=last_decision if isinstance(last_decision, dict) else {},
                cooldown_until_sample=int(row["cooldown_until_sample"]),
            )
            self._states[(state.symbol, state.variant)] = state

    def _persist_all(self) -> None:
        if not self.config.enabled:
            return
        with self._connect() as conn:
            for state in self._states.values():
                conn.execute(
                    """
                    INSERT OR REPLACE INTO mean_reversion_shadow_state (
                        symbol, variant, cash, realized_pnl, gross_profit,
                        gross_loss, fees, wins, losses, opened_trades,
                        closed_trades, sample_count, peak_equity,
                        max_drawdown_eur, last_price, last_tick_at,
                        prices_json, open_position_json, last_signal_json,
                        last_decision_json, cooldown_until_sample, created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        state.symbol,
                        state.variant,
                        state.cash,
                        state.realized_pnl,
                        state.gross_profit,
                        state.gross_loss,
                        state.fees,
                        state.wins,
                        state.losses,
                        state.opened_trades,
                        state.closed_trades,
                        state.sample_count,
                        state.peak_equity,
                        state.max_drawdown_eur,
                        state.last_price,
                        state.last_tick_at,
                        json.dumps(state.prices[-self.config.max_price_samples :], separators=(",", ":")),
                        json.dumps(state.open_position.to_dict() if state.open_position else None, separators=(",", ":")),
                        json.dumps(state.last_signal, separators=(",", ":")),
                        json.dumps(state.last_decision, separators=(",", ":")),
                        state.cooldown_until_sample,
                        state.created_at,
                        state.updated_at,
                    ),
                )

    def _record_trade(
        self,
        state: MeanReversionState,
        position: MeanReversionPosition,
        exit_price: float,
        exit_fee: float,
        realized_pnl: float,
        reason: str,
        timestamp: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO mean_reversion_shadow_trades (
                    symbol, variant, position_id, entry_price, exit_price,
                    volume, notional, fees, realized_pnl, reason, opened_at,
                    closed_at, created_at, opportunity_score, opportunity_status,
                    opportunity_reason, opportunity_components, entry_features_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    state.symbol,
                    state.variant,
                    position.id,
                    position.entry_price,
                    exit_price,
                    position.volume,
                    position.notional,
                    position.entry_fee + exit_fee,
                    realized_pnl,
                    reason,
                    position.opened_at,
                    timestamp,
                    _utc_now(),
                    _optional_float(position.opportunity.get("opportunity_score")),
                    str(position.opportunity.get("opportunity_status") or "") or None,
                    str(position.opportunity.get("opportunity_reason") or "") or None,
                    json.dumps(position.opportunity.get("opportunity_components") or {}, separators=(",", ":")),
                    json.dumps(position.entry_features or {}, separators=(",", ":")),
                ),
            )


def _opportunity_context(raw: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        return {}
    score = _optional_float(raw.get("opportunity_score", raw.get("score")))
    result: dict[str, Any] = {}
    if score is not None:
        result["opportunity_score"] = score
    status = raw.get("opportunity_status", raw.get("status"))
    reason = raw.get("opportunity_reason", raw.get("reason"))
    components = raw.get("opportunity_components", raw.get("components"))
    if status not in (None, ""):
        result["opportunity_status"] = str(status)
    if reason not in (None, ""):
        result["opportunity_reason"] = str(reason)
    if isinstance(components, Mapping):
        result["opportunity_components"] = dict(components)
    return result


def _ensure_trade_metadata_columns(conn: sqlite3.Connection, table: str) -> None:
    existing = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, ddl_type in {
        "opportunity_score": "REAL",
        "opportunity_status": "TEXT",
        "opportunity_reason": "TEXT",
        "opportunity_components": "TEXT",
        "entry_features_json": "TEXT",
    }.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl_type}")
