"""Paper-only setup shadow lab.

This module runs isolated virtual grid variants on observed market prices.  It
never sends orders, never writes to the official paper trade ledger, and never
enables live trading.  The goal is to collect comparable evidence for several
candidate setups per symbol before any setup is allowed to influence execution.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from .pair_strategy_health import symbol_key
from .setup_optimizer import DEFAULT_VARIANTS, PairSetupOptimizer, SetupVariant
from .strategies.adaptive_grid_config import get_default_registry


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
class SetupShadowLabConfig:
    enabled: bool = True
    continue_in_live: bool = True
    db_path: str = "data/setup_shadow_lab.db"
    virtual_capital_per_variant: float = 100.0
    min_tick_seconds: int = 30
    persist_interval_seconds: int = 60
    max_variants_per_symbol: int = 5
    min_order_eur: float = 5.0
    fee_bps_per_side: float = 8.0
    slippage_bps_per_side: float = 2.0
    stop_loss_multiplier: float = 3.0
    min_samples_for_signal: int = 20
    min_closed_trades_for_signal: int = 8
    candidate_score: float = 65.0
    candidate_profit_factor: float = 1.15
    weak_score: float = 40.0

    @classmethod
    def from_env(cls) -> "SetupShadowLabConfig":
        return cls(
            enabled=_env_bool("SETUP_SHADOW_LAB_ENABLED", True),
            continue_in_live=_env_bool("SETUP_SHADOW_CONTINUE_IN_LIVE", True),
            db_path=os.getenv("SETUP_SHADOW_DB_PATH", "data/setup_shadow_lab.db"),
            virtual_capital_per_variant=_env_float("SETUP_SHADOW_VIRTUAL_CAPITAL_EUR", 100.0, 10.0, 1_000_000.0),
            min_tick_seconds=_env_int("SETUP_SHADOW_MIN_TICK_SECONDS", 30, 0, 86_400),
            persist_interval_seconds=_env_int("SETUP_SHADOW_PERSIST_INTERVAL_SECONDS", 60, 1, 86_400),
            max_variants_per_symbol=_env_int("SETUP_SHADOW_MAX_VARIANTS_PER_SYMBOL", 5, 1, 20),
            min_order_eur=_env_float("SETUP_SHADOW_MIN_ORDER_EUR", 5.0, 0.0, 10_000.0),
            fee_bps_per_side=_env_float("SETUP_SHADOW_FEE_BPS_PER_SIDE", 8.0, 0.0, 500.0),
            slippage_bps_per_side=_env_float("SETUP_SHADOW_SLIPPAGE_BPS_PER_SIDE", 2.0, 0.0, 500.0),
            stop_loss_multiplier=_env_float("SETUP_SHADOW_STOP_LOSS_MULTIPLIER", 3.0, 0.1, 50.0),
            min_samples_for_signal=_env_int("SETUP_SHADOW_MIN_SAMPLES", 20, 1, 100_000),
            min_closed_trades_for_signal=_env_int("SETUP_SHADOW_MIN_CLOSED_TRADES", 8, 1, 100_000),
            candidate_score=_env_float("SETUP_SHADOW_CANDIDATE_SCORE", 65.0, 0.0, 100.0),
            candidate_profit_factor=_env_float("SETUP_SHADOW_CANDIDATE_PF", 1.15, 0.01, 100.0),
            weak_score=_env_float("SETUP_SHADOW_WEAK_SCORE", 40.0, 0.0, 100.0),
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
            "min_order_eur": self.min_order_eur,
            "fee_bps_per_side": self.fee_bps_per_side,
            "slippage_bps_per_side": self.slippage_bps_per_side,
            "stop_loss_multiplier": self.stop_loss_multiplier,
            "min_samples_for_signal": self.min_samples_for_signal,
            "min_closed_trades_for_signal": self.min_closed_trades_for_signal,
            "candidate_score": self.candidate_score,
            "candidate_profit_factor": self.candidate_profit_factor,
            "weak_score": self.weak_score,
        }


@dataclass
class ShadowPosition:
    id: str
    level_index: int
    entry_price: float
    volume: float
    notional: float
    entry_fee: float
    opened_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "level_index": self.level_index,
            "entry_price": self.entry_price,
            "volume": self.volume,
            "notional": self.notional,
            "entry_fee": self.entry_fee,
            "opened_at": self.opened_at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ShadowPosition":
        return cls(
            id=str(payload.get("id") or ""),
            level_index=int(_safe_float(payload.get("level_index"), 0.0)),
            entry_price=_safe_float(payload.get("entry_price")),
            volume=_safe_float(payload.get("volume")),
            notional=_safe_float(payload.get("notional")),
            entry_fee=_safe_float(payload.get("entry_fee")),
            opened_at=str(payload.get("opened_at") or _utc_now()),
        )


@dataclass
class ShadowVariantState:
    symbol: str
    variant: str
    signature: str
    center_price: float
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
    open_positions: list[ShadowPosition] = field(default_factory=list)


class SetupShadowLab:
    """Runs virtual setup variants on observed prices."""

    def __init__(
        self,
        config: SetupShadowLabConfig | None = None,
        variants: Iterable[SetupVariant] | None = None,
    ) -> None:
        self.config = config or SetupShadowLabConfig.from_env()
        self.variants = tuple(variants or DEFAULT_VARIANTS)
        self.registry = get_default_registry()
        self.optimizer = PairSetupOptimizer()
        self._lock = threading.RLock()
        self._states: dict[tuple[str, str], ShadowVariantState] = {}
        self._last_update_mono: dict[str, float] = {}
        self._last_persist_mono: float = 0.0
        self._loaded = False

    def on_price_tick(self, *, symbol: str, price: float, timestamp: Any = None) -> dict[str, Any]:
        symbol = symbol_key(symbol)
        price = _safe_float(price)
        if not self.config.enabled:
            return {"updated": False, "reason": "disabled"}
        if price <= 0.0 or symbol == "UNKNOWN":
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
            for variant in self.variants[: self.config.max_variants_per_symbol]:
                grid_config = self._grid_config(symbol, variant)
                state = self._state(symbol, variant.name, grid_config, price)
                self._run_variant_tick(state, variant, grid_config, price, _iso(timestamp))
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
                        "variants": [],
                        "best_variant": None,
                        "updated_at": None,
                    },
                )
                bucket["variants"].append(metrics)
                if bucket["best_variant"] is None or metrics["score"] > bucket["best_variant"]["score"]:
                    bucket["best_variant"] = metrics
                updated_at = state.updated_at
                if bucket["updated_at"] is None or str(updated_at) > str(bucket["updated_at"]):
                    bucket["updated_at"] = updated_at

            rows = []
            for row in by_symbol.values():
                row["variants"].sort(key=lambda item: item["score"], reverse=True)
                rows.append(row)
            rows.sort(key=lambda item: (-(item["best_variant"] or {}).get("score", 0.0), item["symbol"]))

            total_closed = sum(int(self._metrics(state)["closed_trades"]) for state in states)
            total_open = sum(len(state.open_positions) for state in states)
            total_pnl = sum(float(self._metrics(state)["net_pnl_eur"]) for state in states)
            candidate_count = sum(
                1
                for row in rows
                if row.get("best_variant") and row["best_variant"].get("status") == "candidate"
            )
            return {
                "timestamp": _utc_now(),
                "mode": "paper_shadow",
                "paper_only": True,
                "enabled": self.config.enabled,
                "live_promotion_allowed": False,
                "writes_official_paper_ledger": False,
                "config": self.config.to_dict(),
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
                    "Shadow lab: isolated virtual setup tests from observed prices. "
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
        state: ShadowVariantState,
        variant: SetupVariant,
        grid_config: Mapping[str, Any],
        price: float,
        timestamp: str,
    ) -> None:
        if not state.open_positions and self._outside_grid(state.center_price, grid_config, price):
            state.center_price = price

        state.last_price = price
        state.last_tick_at = timestamp
        state.sample_count += 1

        self._close_ready_positions(state, grid_config, price, timestamp)
        self._open_candidate_position(state, variant, grid_config, price, timestamp)

        equity = self._equity(state, price)
        state.peak_equity = max(state.peak_equity or self.config.virtual_capital_per_variant, equity)
        state.max_drawdown_eur = max(state.max_drawdown_eur, state.peak_equity - equity)
        state.updated_at = timestamp

    def _close_ready_positions(
        self,
        state: ShadowVariantState,
        grid_config: Mapping[str, Any],
        price: float,
        timestamp: str,
    ) -> None:
        sell_threshold_pct = max(0.01, _safe_float(grid_config.get("estimated_sell_threshold_pct"), 1.5))
        stop_loss_pct = sell_threshold_pct * self.config.stop_loss_multiplier
        remaining: list[ShadowPosition] = []
        closed_rows: list[tuple[ShadowPosition, float, str]] = []
        for pos in state.open_positions:
            target_price = pos.entry_price * (1.0 + sell_threshold_pct / 100.0)
            stop_price = pos.entry_price * (1.0 - stop_loss_pct / 100.0)
            if price >= target_price:
                closed_rows.append((pos, price, "take_profit"))
            elif price <= stop_price:
                closed_rows.append((pos, price, "stop_loss"))
            else:
                remaining.append(pos)
        state.open_positions = remaining

        for pos, exit_price, reason in closed_rows:
            exit_notional = pos.volume * exit_price
            exit_fee = self._leg_cost(exit_notional)
            gross = (exit_price - pos.entry_price) * pos.volume
            net = gross - pos.entry_fee - exit_fee
            state.cash += exit_notional - exit_fee
            state.realized_pnl += net
            state.fees += pos.entry_fee + exit_fee
            state.closed_trades += 1
            if net > 0.0:
                state.gross_profit += net
                state.wins += 1
            else:
                state.gross_loss += abs(net)
                state.losses += 1
            self._record_trade(state, pos, exit_price, exit_fee, net, reason, timestamp)

    def _open_candidate_position(
        self,
        state: ShadowVariantState,
        variant: SetupVariant,
        grid_config: Mapping[str, Any],
        price: float,
        timestamp: str,
    ) -> None:
        max_positions = int(_safe_float(grid_config.get("max_positions"), 1.0))
        if len(state.open_positions) >= max_positions:
            return
        levels = self._levels(state.center_price, grid_config)
        open_levels = {pos.level_index for pos in state.open_positions}
        touch_bps = _safe_float(grid_config.get("entry_touch_bps"), variant.entry_touch_bps)
        eligible = [
            (idx, level)
            for idx, level in enumerate(levels)
            if level <= state.center_price
            and idx not in open_levels
            and price <= level * (1.0 + touch_bps / 10000.0)
        ]
        if not eligible:
            return

        idx, level = max(eligible, key=lambda item: item[1])
        notional = min(
            _safe_float(grid_config.get("max_capital_per_level"), self.config.virtual_capital_per_variant),
            state.cash * 0.35,
        )
        if notional < self.config.min_order_eur:
            return
        entry_fee = self._leg_cost(notional)
        if state.cash < notional + entry_fee:
            return
        state.cash -= notional + entry_fee
        volume = notional / max(price, 1e-12)
        state.open_positions.append(
            ShadowPosition(
                id=self._position_id(state.symbol, state.variant, state.opened_trades + 1, timestamp),
                level_index=idx,
                entry_price=price,
                volume=volume,
                notional=notional,
                entry_fee=entry_fee,
                opened_at=timestamp,
            )
        )
        state.opened_trades += 1

    def _metrics(self, state: ShadowVariantState) -> dict[str, Any]:
        last_price = state.last_price or state.center_price
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
            "open_positions": len(state.open_positions),
            "sample_count": int(state.sample_count),
            "max_drawdown_eur": round(state.max_drawdown_eur, 4),
            "max_drawdown_pct": round((state.max_drawdown_eur / max(self.config.virtual_capital_per_variant, 1e-9)) * 100.0, 4),
            "fees_eur": round(state.fees, 4),
            "center_price": round(state.center_price, 10),
            "last_price": round(last_price, 10),
            "last_tick_at": state.last_tick_at,
            "updated_at": state.updated_at,
            "evidence_source": "setup_shadow_lab",
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
            pf_component = max(-25.0, min(25.0, (profit_factor - 1.0) * 22.0))
        win_component = (win_rate - 0.5) * 18.0 if closed_trades > 0 else 0.0
        dd_penalty = min(25.0, (max_drawdown_eur / capital) * 120.0)
        evidence = min(1.0, sample_count / max(self.config.min_samples_for_signal, 1))
        raw = 50.0 + (net_return_pct * 4.0) + (realized_return_pct * 2.0) + pf_component + win_component - dd_penalty
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

    def _grid_config(self, symbol: str, variant: SetupVariant) -> dict[str, Any]:
        profile = self.registry.get(symbol)
        grid_config, _edge = self.optimizer._grid_config_for_variant(profile, variant)
        return grid_config

    def _state(
        self,
        symbol: str,
        variant: str,
        grid_config: Mapping[str, Any],
        price: float,
    ) -> ShadowVariantState:
        key = (symbol, variant)
        signature = self._signature(grid_config)
        state = self._states.get(key)
        if state is None:
            state = ShadowVariantState(
                symbol=symbol,
                variant=variant,
                signature=signature,
                center_price=price,
                cash=self.config.virtual_capital_per_variant,
                created_at=_utc_now(),
                peak_equity=self.config.virtual_capital_per_variant,
                last_price=price,
            )
            self._states[key] = state
            return state
        if state.signature != signature and not state.open_positions:
            state.signature = signature
            state.center_price = price
        return state

    def _levels(self, center_price: float, grid_config: Mapping[str, Any]) -> list[float]:
        num_levels = max(2, int(_safe_float(grid_config.get("num_levels"), 15.0)))
        range_percent = max(0.01, _safe_float(grid_config.get("range_percent"), 3.0))
        half_range = range_percent / 2.0 / 100.0
        lower = center_price * (1.0 - half_range)
        upper = center_price * (1.0 + half_range)
        step = (upper - lower) / (num_levels - 1)
        return [lower + (idx * step) for idx in range(num_levels)]

    def _outside_grid(self, center_price: float, grid_config: Mapping[str, Any], price: float) -> bool:
        levels = self._levels(center_price, grid_config)
        return bool(levels and (price < levels[0] or price > levels[-1]))

    def _leg_cost(self, notional: float) -> float:
        return max(0.0, float(notional) * ((self.config.fee_bps_per_side + self.config.slippage_bps_per_side) / 10000.0))

    def _unrealized_pnl(self, state: ShadowVariantState, price: float) -> float:
        total = 0.0
        for pos in state.open_positions:
            exit_notional = pos.volume * price
            exit_fee = self._leg_cost(exit_notional)
            total += ((price - pos.entry_price) * pos.volume) - pos.entry_fee - exit_fee
        return total

    def _equity(self, state: ShadowVariantState, price: float) -> float:
        open_value = sum(pos.volume * price - self._leg_cost(pos.volume * price) for pos in state.open_positions)
        return state.cash + open_value

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

    @staticmethod
    def _signature(grid_config: Mapping[str, Any]) -> str:
        raw = json.dumps(dict(grid_config), sort_keys=True, separators=(",", ":"))
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]

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
                CREATE TABLE IF NOT EXISTS setup_shadow_state (
                    symbol TEXT NOT NULL,
                    variant TEXT NOT NULL,
                    signature TEXT NOT NULL,
                    center_price REAL NOT NULL,
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
                    open_positions_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (symbol, variant)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS setup_shadow_trades (
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
                    created_at TEXT NOT NULL
                )
                """
            )

    def _load_states(self) -> None:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM setup_shadow_state").fetchall()
        for row in rows:
            try:
                positions_raw = json.loads(row["open_positions_json"] or "[]")
            except json.JSONDecodeError:
                positions_raw = []
            state = ShadowVariantState(
                symbol=str(row["symbol"]),
                variant=str(row["variant"]),
                signature=str(row["signature"]),
                center_price=float(row["center_price"]),
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
                open_positions=[
                    ShadowPosition.from_dict(item)
                    for item in positions_raw
                    if isinstance(item, Mapping)
                ],
            )
            self._states[(state.symbol, state.variant)] = state

    def _persist_all(self) -> None:
        if not self.config.enabled:
            return
        with self._connect() as conn:
            for state in self._states.values():
                conn.execute(
                    """
                    INSERT OR REPLACE INTO setup_shadow_state (
                        symbol, variant, signature, center_price, cash, realized_pnl,
                        gross_profit, gross_loss, fees, wins, losses, opened_trades,
                        closed_trades, sample_count, peak_equity, max_drawdown_eur,
                        last_price, last_tick_at, open_positions_json, created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        state.symbol,
                        state.variant,
                        state.signature,
                        state.center_price,
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
                        json.dumps([pos.to_dict() for pos in state.open_positions], separators=(",", ":")),
                        state.created_at,
                        state.updated_at,
                    ),
                )

    def _record_trade(
        self,
        state: ShadowVariantState,
        position: ShadowPosition,
        exit_price: float,
        exit_fee: float,
        realized_pnl: float,
        reason: str,
        timestamp: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO setup_shadow_trades (
                    symbol, variant, position_id, entry_price, exit_price, volume,
                    notional, fees, realized_pnl, reason, opened_at, closed_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                ),
            )
