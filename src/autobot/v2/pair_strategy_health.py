"""Pair/strategy health scoring from traceable realized trades.

The goal is not to predict prices.  This module turns the realized paper
ledger into a bounded score that can gently steer paper opportunity selection
away from setups that are currently destroying net PnL.
"""

from __future__ import annotations

import os
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional


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


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, float(value)))


def symbol_key(symbol: Any) -> str:
    return str(symbol or "UNKNOWN").upper().replace("/", "").strip()


@dataclass(frozen=True)
class PairStrategyHealthConfig:
    enabled: bool = True
    live_enabled: bool = False
    min_closed_trades: int = 20
    early_weak_min_closed_trades: int = 8
    early_weak_score_max: float = 35.0
    early_weak_pf_max: float = 0.80
    early_weak_penalty_multiplier: float = 0.75
    lookback_closed_trades: int = 80
    max_bonus: float = 8.0
    max_penalty: float = 28.0
    cache_seconds: int = 30
    pf_floor: float = 0.75
    pf_target: float = 1.35
    active_pf_floor: float = 1.0
    avg_return_target_bps: float = 35.0

    @classmethod
    def from_env(cls) -> "PairStrategyHealthConfig":
        return cls(
            enabled=_env_bool("PAIR_HEALTH_SCORING_ENABLED", True),
            live_enabled=_env_bool("PAIR_HEALTH_LIVE_ENABLED", False),
            min_closed_trades=_env_int("PAIR_HEALTH_MIN_CLOSED_TRADES", 20, 1, 10_000),
            early_weak_min_closed_trades=_env_int("PAIR_HEALTH_EARLY_WEAK_MIN_CLOSED_TRADES", 8, 1, 10_000),
            early_weak_score_max=_env_float("PAIR_HEALTH_EARLY_WEAK_SCORE_MAX", 35.0, 0.0, 100.0),
            early_weak_pf_max=_env_float("PAIR_HEALTH_EARLY_WEAK_PF_MAX", 0.80, 0.0, 10.0),
            early_weak_penalty_multiplier=_env_float("PAIR_HEALTH_EARLY_WEAK_PENALTY_MULTIPLIER", 0.75, 0.0, 1.0),
            lookback_closed_trades=_env_int("PAIR_HEALTH_LOOKBACK_CLOSED_TRADES", 80, 1, 10_000),
            max_bonus=_env_float("PAIR_HEALTH_MAX_BONUS", 8.0, 0.0, 50.0),
            max_penalty=_env_float("PAIR_HEALTH_MAX_PENALTY", 28.0, 0.0, 80.0),
            cache_seconds=_env_int("PAIR_HEALTH_CACHE_SECONDS", 30, 0, 86_400),
            pf_floor=_env_float("PAIR_HEALTH_PF_FLOOR", 0.75, 0.0, 10.0),
            pf_target=_env_float("PAIR_HEALTH_PF_TARGET", 1.35, 0.01, 100.0),
            active_pf_floor=_env_float("PAIR_HEALTH_ACTIVE_PF_FLOOR", 1.0, 0.0, 10.0),
            avg_return_target_bps=_env_float("PAIR_HEALTH_AVG_RETURN_TARGET_BPS", 35.0, 1.0, 10_000.0),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "live_enabled": self.live_enabled,
            "min_closed_trades": self.min_closed_trades,
            "early_weak_min_closed_trades": self.early_weak_min_closed_trades,
            "early_weak_score_max": self.early_weak_score_max,
            "early_weak_pf_max": self.early_weak_pf_max,
            "early_weak_penalty_multiplier": self.early_weak_penalty_multiplier,
            "lookback_closed_trades": self.lookback_closed_trades,
            "max_bonus": self.max_bonus,
            "max_penalty": self.max_penalty,
            "cache_seconds": self.cache_seconds,
            "pf_floor": self.pf_floor,
            "pf_target": self.pf_target,
            "active_pf_floor": self.active_pf_floor,
            "avg_return_target_bps": self.avg_return_target_bps,
        }


@dataclass(frozen=True)
class RealizedLedgerTrade:
    symbol: str
    realized_pnl: float
    notional: float
    fees: float
    timestamp: str


@dataclass
class PairStrategyHealth:
    symbol: str
    status: str
    reason: str
    health_score: float = 50.0
    adjustment: float = 0.0
    closed_trades: int = 0
    net_pnl_eur: float = 0.0
    gross_profit_eur: float = 0.0
    gross_loss_eur: float = 0.0
    profit_factor: Optional[float] = None
    win_rate: float = 0.0
    avg_pnl_eur: float = 0.0
    avg_return_bps: float = 0.0
    max_drawdown_eur: float = 0.0
    total_fees_eur: float = 0.0
    components: dict[str, float] = field(default_factory=dict)
    enabled: bool = True
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "status": self.status,
            "reason": self.reason,
            "health_score": round(self.health_score, 2),
            "adjustment": round(self.adjustment, 3),
            "closed_trades": int(self.closed_trades),
            "net_pnl_eur": round(self.net_pnl_eur, 4),
            "gross_profit_eur": round(self.gross_profit_eur, 4),
            "gross_loss_eur": round(self.gross_loss_eur, 4),
            "profit_factor": round(self.profit_factor, 4) if self.profit_factor is not None else None,
            "win_rate": round(self.win_rate, 4),
            "avg_pnl_eur": round(self.avg_pnl_eur, 4),
            "avg_return_bps": round(self.avg_return_bps, 3),
            "max_drawdown_eur": round(self.max_drawdown_eur, 4),
            "total_fees_eur": round(self.total_fees_eur, 4),
            "components": {key: round(value, 4) for key, value in self.components.items()},
            "enabled": self.enabled,
            "timestamp": self.timestamp,
        }


class PairStrategyHealthEngine:
    """Build health scores from `trade_ledger` closing legs."""

    def __init__(self, config: PairStrategyHealthConfig | None = None) -> None:
        self.config = config or PairStrategyHealthConfig.from_env()
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}

    def neutral(self, symbol: Any, reason: str = "no_health_context") -> PairStrategyHealth:
        return PairStrategyHealth(
            symbol=symbol_key(symbol),
            status="unknown",
            reason=reason,
            enabled=self.config.enabled,
        )

    def build_snapshot_from_state_db(self, db_path: Any, *, paper_mode: bool) -> dict[str, Any]:
        cache_key = f"{Path(str(db_path)).resolve() if db_path else 'data/autobot_state.db'}|{paper_mode}"
        now = time.monotonic()
        ttl = max(0, int(self.config.cache_seconds))
        cached = self._cache.get(cache_key)
        if cached and ttl > 0 and now - cached[0] <= ttl:
            return cached[1]

        trades = load_realized_ledger_trades(db_path)
        snapshot = self.build_snapshot(trades, paper_mode=paper_mode)
        self._cache[cache_key] = (now, snapshot)
        return snapshot

    def build_snapshot(
        self,
        trades: Iterable[RealizedLedgerTrade],
        *,
        paper_mode: bool,
    ) -> dict[str, Any]:
        applies = self.config.enabled and (paper_mode or self.config.live_enabled)
        grouped: dict[str, list[RealizedLedgerTrade]] = {}
        for trade in trades:
            grouped.setdefault(symbol_key(trade.symbol), []).append(trade)

        by_symbol = {
            symbol: self.analyze_symbol(symbol, rows, applies=applies).to_dict()
            for symbol, rows in grouped.items()
        }
        ranked = sorted(by_symbol.values(), key=lambda item: item["health_score"], reverse=True)
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": "paper" if paper_mode else "live",
            "paper_mode": paper_mode,
            "enabled": self.config.enabled,
            "applies_to_scoring": applies,
            "config": self.config.to_dict(),
            "by_symbol": by_symbol,
            "ranked": ranked,
        }

    def analyze_symbol(
        self,
        symbol: str,
        trades: Iterable[RealizedLedgerTrade],
        *,
        applies: bool = True,
    ) -> PairStrategyHealth:
        rows = sorted(list(trades), key=lambda trade: str(trade.timestamp))
        if self.config.lookback_closed_trades > 0:
            rows = rows[-self.config.lookback_closed_trades :]
        closed = len(rows)
        if not self.config.enabled:
            return PairStrategyHealth(symbol=symbol_key(symbol), status="disabled", reason="disabled", enabled=False)
        if not applies:
            return PairStrategyHealth(symbol=symbol_key(symbol), status="neutral", reason="not_applied_in_live", enabled=True)
        if closed <= 0:
            return self.neutral(symbol, "no_closed_trades")

        pnls = [float(row.realized_pnl) for row in rows]
        notionals = [max(1e-9, float(row.notional)) for row in rows]
        returns_bps = [(pnl / notional) * 10000.0 for pnl, notional in zip(pnls, notionals)]
        wins = [pnl for pnl in pnls if pnl > 0.0]
        losses = [pnl for pnl in pnls if pnl < 0.0]
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        net_pnl = sum(pnls)
        profit_factor = None
        if gross_loss > 0.0:
            profit_factor = gross_profit / gross_loss
        elif gross_profit > 0.0:
            profit_factor = None

        cumulative = 0.0
        peak = 0.0
        max_drawdown = 0.0
        for pnl in pnls:
            cumulative += pnl
            peak = max(peak, cumulative)
            max_drawdown = max(max_drawdown, peak - cumulative)

        avg_return_bps = sum(returns_bps) / closed
        avg_pnl = net_pnl / closed
        win_rate = len(wins) / closed
        pf_component = self._profit_factor_component(profit_factor, gross_profit, gross_loss)
        net_component = self._net_component(gross_profit, gross_loss)
        return_component = _clamp(
            0.5 + (avg_return_bps / max(self.config.avg_return_target_bps * 2.0, 1.0))
        )
        win_component = _clamp(win_rate)
        dd_component = self._drawdown_component(max_drawdown, gross_profit, gross_loss)
        score = 100.0 * (
            (pf_component * 0.35)
            + (net_component * 0.25)
            + (return_component * 0.20)
            + (win_component * 0.10)
            + (dd_component * 0.10)
        )
        early_weak = self._is_early_weak(
            closed=closed,
            score=score,
            net_pnl=net_pnl,
            profit_factor=profit_factor,
        )
        if closed < self.config.min_closed_trades:
            evidence_quality = closed / max(self.config.min_closed_trades, 1)
            score = (50.0 * (1.0 - evidence_quality)) + (score * evidence_quality)
            if early_weak:
                reason = "early_negative_evidence"
                status = "early_weak"
            else:
                reason = "insufficient_closed_trades"
                status = "learning"
        else:
            reason = "realized_health"
            status = self._status(score, net_pnl, profit_factor)
            if self._is_confirmed_underperforming(net_pnl, profit_factor):
                status = "underperforming"
                reason = "realized_underperforming"

        adjustment = self._adjustment(score, closed, early_weak=early_weak)
        if self._is_confirmed_underperforming(net_pnl, profit_factor) and adjustment > 0.0:
            adjustment = -min(
                self.config.max_penalty,
                self.config.max_penalty
                * _clamp((self.config.active_pf_floor - float(profit_factor or 0.0)) / max(self.config.active_pf_floor, 1e-9))
                * 0.35,
            )
        return PairStrategyHealth(
            symbol=symbol_key(symbol),
            status=status,
            reason=reason,
            health_score=score,
            adjustment=adjustment,
            closed_trades=closed,
            net_pnl_eur=net_pnl,
            gross_profit_eur=gross_profit,
            gross_loss_eur=gross_loss,
            profit_factor=profit_factor,
            win_rate=win_rate,
            avg_pnl_eur=avg_pnl,
            avg_return_bps=avg_return_bps,
            max_drawdown_eur=max_drawdown,
            total_fees_eur=sum(float(row.fees) for row in rows),
            components={
                "profit_factor": pf_component,
                "net": net_component,
                "avg_return": return_component,
                "win_rate": win_component,
                "drawdown": dd_component,
            },
            enabled=True,
        )

    def _profit_factor_component(
        self,
        profit_factor: Optional[float],
        gross_profit: float,
        gross_loss: float,
    ) -> float:
        if profit_factor is None:
            if gross_profit > 0.0 and gross_loss <= 0.0:
                return 0.85
            return 0.50
        return _clamp((profit_factor - self.config.pf_floor) / max(self.config.pf_target - self.config.pf_floor, 1e-9))

    @staticmethod
    def _net_component(gross_profit: float, gross_loss: float) -> float:
        total = gross_profit + gross_loss
        if total <= 0.0:
            return 0.50
        return _clamp(gross_profit / total)

    @staticmethod
    def _drawdown_component(max_drawdown: float, gross_profit: float, gross_loss: float) -> float:
        scale = max(gross_profit + gross_loss, 1e-9)
        return _clamp(1.0 - (max_drawdown / scale))

    def _is_early_weak(
        self,
        *,
        closed: int,
        score: float,
        net_pnl: float,
        profit_factor: Optional[float],
    ) -> bool:
        if closed < self.config.early_weak_min_closed_trades:
            return False
        if net_pnl >= 0.0:
            return False
        pf = profit_factor if profit_factor is not None else 0.0
        return score <= self.config.early_weak_score_max and pf <= self.config.early_weak_pf_max

    def _is_confirmed_underperforming(
        self,
        net_pnl: float,
        profit_factor: Optional[float],
    ) -> bool:
        pf = profit_factor if profit_factor is not None else (0.0 if net_pnl < 0.0 else self.config.active_pf_floor)
        return net_pnl < 0.0 and pf < self.config.active_pf_floor

    def _adjustment(self, score: float, closed_trades: int, *, early_weak: bool = False) -> float:
        if closed_trades < self.config.min_closed_trades:
            if early_weak:
                centered = max(0.0, (50.0 - float(score)) / 50.0)
                evidence = _clamp(closed_trades / max(self.config.min_closed_trades, 1))
                return -min(
                    self.config.max_penalty,
                    self.config.max_penalty
                    * centered
                    * evidence
                    * self.config.early_weak_penalty_multiplier,
                )
            return 0.0
        centered = (float(score) - 50.0) / 50.0
        if centered >= 0.0:
            return min(self.config.max_bonus, self.config.max_bonus * centered)
        return -min(self.config.max_penalty, self.config.max_penalty * abs(centered))

    @staticmethod
    def _status(score: float, net_pnl: float, profit_factor: Optional[float]) -> str:
        pf = profit_factor if profit_factor is not None else (2.0 if net_pnl > 0.0 else 1.0)
        if score >= 70.0 and net_pnl > 0.0 and pf >= 1.20:
            return "healthy"
        if score >= 55.0 and net_pnl >= 0.0:
            return "neutral_positive"
        if score < 35.0 or (net_pnl < 0.0 and pf < 0.90):
            return "weak"
        return "neutral"


def load_realized_ledger_trades(db_path: Any) -> list[RealizedLedgerTrade]:
    path = Path(str(db_path)) if db_path else Path("data/autobot_state.db")
    if not path.exists():
        return []
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            table = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='trade_ledger'"
            ).fetchone()
            if not table:
                return []
            rows = conn.execute(
                """
                SELECT symbol, executed_price, volume, fees, realized_pnl, created_at
                FROM trade_ledger
                WHERE is_closing_leg = 1
                  AND realized_pnl IS NOT NULL
                  AND volume > 0
                  AND executed_price > 0
                ORDER BY created_at ASC
                """
            ).fetchall()
        finally:
            conn.close()
    except Exception:
        return []

    trades: list[RealizedLedgerTrade] = []
    for row in rows:
        price = _safe_float(row["executed_price"])
        volume = _safe_float(row["volume"])
        if price <= 0.0 or volume <= 0.0:
            continue
        trades.append(
            RealizedLedgerTrade(
                symbol=symbol_key(row["symbol"]),
                realized_pnl=_safe_float(row["realized_pnl"]),
                notional=price * volume,
                fees=_safe_float(row["fees"]),
                timestamp=str(row["created_at"] or ""),
            )
        )
    return trades
