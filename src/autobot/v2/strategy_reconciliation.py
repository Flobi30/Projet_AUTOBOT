"""Read-only reconciliation between shadow engines and official paper ledger.

The goal is to expose when a shadow lab looks profitable while the official
paper ledger loses money.  This module never places orders and never enables
live trading; it only produces an audit snapshot that can guide safer changes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from .pair_strategy_health import symbol_key


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    try:
        value = int(float(raw)) if raw not in (None, "") else default
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.getenv(name)
    try:
        value = float(raw) if raw not in (None, "") else default
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


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _round_optional(value: Any, digits: int = 4) -> float | None:
    if value is None:
        return None
    return round(_safe_float(value), digits)


@dataclass(frozen=True)
class StrategyReconciliationConfig:
    min_official_closed_trades: int = 20
    min_shadow_closed_trades: int = 30
    no_loss_shadow_min_closed_trades: int = 50
    min_positive_shadow_pnl_eur: float = 0.0
    fee_drag_warning_pct: float = 35.0

    @classmethod
    def from_env(cls) -> "StrategyReconciliationConfig":
        return cls(
            min_official_closed_trades=_env_int(
                "STRATEGY_RECONCILIATION_MIN_OFFICIAL_CLOSED_TRADES", 20, 1, 100_000
            ),
            min_shadow_closed_trades=_env_int(
                "STRATEGY_RECONCILIATION_MIN_SHADOW_CLOSED_TRADES", 30, 1, 100_000
            ),
            no_loss_shadow_min_closed_trades=_env_int(
                "STRATEGY_RECONCILIATION_NO_LOSS_SHADOW_MIN_CLOSED_TRADES", 50, 1, 100_000
            ),
            min_positive_shadow_pnl_eur=_env_float(
                "STRATEGY_RECONCILIATION_MIN_POSITIVE_SHADOW_PNL_EUR", 0.0, -1_000_000.0, 1_000_000.0
            ),
            fee_drag_warning_pct=_env_float("STRATEGY_RECONCILIATION_FEE_DRAG_WARNING_PCT", 35.0, 0.0, 10_000.0),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "min_official_closed_trades": self.min_official_closed_trades,
            "min_shadow_closed_trades": self.min_shadow_closed_trades,
            "no_loss_shadow_min_closed_trades": self.no_loss_shadow_min_closed_trades,
            "min_positive_shadow_pnl_eur": self.min_positive_shadow_pnl_eur,
            "fee_drag_warning_pct": self.fee_drag_warning_pct,
        }


class StrategyReconciliationEngine:
    """Compare official realized paper PnL against isolated shadow evidence."""

    def __init__(self, config: StrategyReconciliationConfig | None = None) -> None:
        self.config = config or StrategyReconciliationConfig.from_env()

    def build_snapshot(
        self,
        *,
        official_performance: Mapping[str, Any] | None,
        shadow_snapshots: Mapping[str, Mapping[str, Any]] | None,
        paper_mode: bool,
    ) -> dict[str, Any]:
        official_performance = official_performance if isinstance(official_performance, Mapping) else {}
        shadow_snapshots = shadow_snapshots if isinstance(shadow_snapshots, Mapping) else {}
        official_by_symbol = {
            symbol_key(symbol): self._official_stats(symbol_key(symbol), payload)
            for symbol, payload in (official_performance.get("by_symbol", {}) or {}).items()
            if isinstance(payload, Mapping)
        }
        shadow_by_symbol = self._shadow_by_symbol(shadow_snapshots)
        symbols = sorted(set(official_by_symbol) | set(shadow_by_symbol))

        rows = []
        for symbol in symbols:
            official = official_by_symbol.get(symbol, self._empty_official(symbol))
            shadows = shadow_by_symbol.get(symbol, {})
            best_shadow = self._best_shadow(shadows)
            verdict, action, causes = self._verdict(official, best_shadow, shadows)
            rows.append(
                {
                    "symbol": symbol,
                    "verdict": verdict,
                    "recommended_action": action,
                    "root_causes": causes,
                    "official": official,
                    "best_shadow": best_shadow,
                    "shadows": shadows,
                }
            )

        priority = {
            "shadow_official_divergence": 0,
            "official_underperforming": 1,
            "shadow_sample_not_robust": 2,
            "learning": 3,
            "aligned_positive": 4,
            "aligned_negative": 5,
            "neutral": 6,
        }
        rows.sort(key=lambda row: (priority.get(str(row["verdict"]), 99), row["symbol"]))

        summary = self._summary(rows, official_performance, shadow_snapshots)
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": "paper" if paper_mode else "live_observation",
            "paper_mode": paper_mode,
            "paper_only": True,
            "live_promotion_allowed": False,
            "config": self.config.to_dict(),
            "summary": summary,
            "symbols": rows,
            "message": (
                "Reconciliation compares official paper ledger with isolated shadow labs. "
                "A positive shadow result is not accepted as real performance unless official paper evidence agrees."
            ),
        }

    def _official_stats(self, symbol: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        closed = _safe_int(payload.get("closed_trades"))
        net = _safe_float(payload.get("net_pnl"))
        gross_profit = _safe_float(payload.get("gross_profit"))
        gross_loss = _safe_float(payload.get("gross_loss"))
        fees = _safe_float(payload.get("fees"))
        profit_factor = payload.get("profit_factor")
        fee_drag_pct = (fees / gross_profit * 100.0) if gross_profit > 0.0 else None
        return {
            "symbol": symbol,
            "closed_trades": closed,
            "net_pnl_eur": round(net, 4),
            "gross_profit_eur": round(gross_profit, 4),
            "gross_loss_eur": round(gross_loss, 4),
            "fees_eur": round(fees, 4),
            "profit_factor": _round_optional(profit_factor),
            "profit_factor_status": payload.get("profit_factor_status"),
            "win_rate": round(_safe_float(payload.get("win_rate")), 2),
            "fee_drag_pct": round(fee_drag_pct, 2) if fee_drag_pct is not None else None,
            "source": payload.get("source", "trade_ledger"),
            "first_close": payload.get("first_close"),
            "last_close": payload.get("last_close"),
        }

    @staticmethod
    def _empty_official(symbol: str) -> dict[str, Any]:
        return {
            "symbol": symbol,
            "closed_trades": 0,
            "net_pnl_eur": 0.0,
            "gross_profit_eur": 0.0,
            "gross_loss_eur": 0.0,
            "fees_eur": 0.0,
            "profit_factor": None,
            "profit_factor_status": "no_closed_trades",
            "win_rate": 0.0,
            "fee_drag_pct": None,
            "source": "none",
            "first_close": None,
            "last_close": None,
        }

    def _shadow_by_symbol(self, snapshots: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for engine, snapshot in snapshots.items():
            if not isinstance(snapshot, Mapping):
                continue
            by_symbol = snapshot.get("by_symbol", {})
            if not isinstance(by_symbol, Mapping):
                continue
            for raw_symbol, row in by_symbol.items():
                if not isinstance(row, Mapping):
                    continue
                symbol = symbol_key(raw_symbol)
                best = row.get("best_variant")
                if not isinstance(best, Mapping):
                    continue
                result.setdefault(symbol, {})[str(engine)] = self._shadow_stats(str(engine), symbol, best)
        return result

    def _shadow_stats(self, engine: str, symbol: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        closed = _safe_int(payload.get("closed_trades"))
        gross_loss = _safe_float(payload.get("gross_loss_eur", payload.get("gross_loss")))
        profit_factor = payload.get("profit_factor")
        no_loss = closed > 0 and gross_loss <= 0.0 and profit_factor is None
        robust_sample = closed >= self.config.min_shadow_closed_trades
        no_loss_robust = not no_loss or closed >= self.config.no_loss_shadow_min_closed_trades
        return {
            "engine": engine,
            "symbol": symbol,
            "variant": payload.get("variant") or payload.get("name"),
            "status": payload.get("status"),
            "score": round(_safe_float(payload.get("score")), 2),
            "closed_trades": closed,
            "net_pnl_eur": round(_safe_float(payload.get("net_pnl_eur")), 4),
            "realized_pnl_eur": round(_safe_float(payload.get("realized_pnl_eur", payload.get("net_pnl_eur"))), 4),
            "gross_profit_eur": round(_safe_float(payload.get("gross_profit_eur", payload.get("gross_profit"))), 4),
            "gross_loss_eur": round(gross_loss, 4),
            "fees_eur": round(_safe_float(payload.get("fees_eur", payload.get("fees"))), 4),
            "profit_factor": _round_optional(profit_factor),
            "win_rate": round(_safe_float(payload.get("win_rate")), 2),
            "sample_count": _safe_int(payload.get("sample_count")),
            "open_positions": _safe_int(payload.get("open_positions")),
            "no_loss_sample": no_loss,
            "robust_sample": robust_sample,
            "no_loss_robust": no_loss_robust,
            "evidence_source": payload.get("evidence_source"),
        }

    @staticmethod
    def _best_shadow(shadows: Mapping[str, Mapping[str, Any]]) -> dict[str, Any] | None:
        candidates = [value for value in shadows.values() if isinstance(value, Mapping)]
        if not candidates:
            return None
        return dict(
            sorted(
                candidates,
                key=lambda item: (
                    _safe_float(item.get("net_pnl_eur")),
                    _safe_float(item.get("score")),
                    _safe_int(item.get("closed_trades")),
                ),
                reverse=True,
            )[0]
        )

    def _verdict(
        self,
        official: Mapping[str, Any],
        best_shadow: Mapping[str, Any] | None,
        shadows: Mapping[str, Mapping[str, Any]],
    ) -> tuple[str, str, list[str]]:
        official_closed = _safe_int(official.get("closed_trades"))
        official_net = _safe_float(official.get("net_pnl_eur"))
        official_pf = official.get("profit_factor")
        fee_drag = official.get("fee_drag_pct")
        causes: list[str] = []

        if official_closed < self.config.min_official_closed_trades:
            causes.append("official_sample_too_small")

        if fee_drag is not None and _safe_float(fee_drag) >= self.config.fee_drag_warning_pct:
            causes.append("official_fee_drag_high")

        if best_shadow is None:
            if official_closed <= 0:
                return "learning", "collect_shadow_and_official_data", causes or ["no_shadow_or_official_evidence"]
            if official_net < 0.0:
                causes.append("official_negative_without_shadow_alternative")
                return "official_underperforming", "pause_scaling_and_review_setup", sorted(set(causes))
            return "neutral", "continue_observation", sorted(set(causes))

        shadow_closed = _safe_int(best_shadow.get("closed_trades"))
        shadow_net = _safe_float(best_shadow.get("net_pnl_eur"))
        shadow_positive = shadow_net > self.config.min_positive_shadow_pnl_eur
        shadow_robust = bool(best_shadow.get("robust_sample")) and bool(best_shadow.get("no_loss_robust"))

        if shadow_positive and not shadow_robust:
            causes.append("shadow_positive_but_sample_not_robust")
            if bool(best_shadow.get("no_loss_sample")):
                causes.append("shadow_has_no_losses_yet")
            if shadow_closed < self.config.min_shadow_closed_trades:
                causes.append("shadow_closed_trades_below_reconciliation_min")

        if shadow_positive and official_closed >= self.config.min_official_closed_trades and official_net < 0.0:
            causes.append("shadow_positive_official_negative")
            if not shadow_robust:
                return "shadow_official_divergence", "do_not_promote_shadow_review_costs_and_execution", sorted(set(causes))
            return "shadow_official_divergence", "reconcile_trade_by_trade_before_any_promotion", sorted(set(causes))

        if official_closed >= self.config.min_official_closed_trades and official_net < 0.0:
            causes.append("official_negative_expectancy")
            if official_pf is None or _safe_float(official_pf) < 1.0:
                causes.append("official_profit_factor_below_one")
            return "official_underperforming", "pause_scaling_and_review_setup", sorted(set(causes))

        if shadow_positive and not shadow_robust:
            return "shadow_sample_not_robust", "keep_shadow_learning_before_paper_promotion", sorted(set(causes))

        if official_closed > 0 and official_net > 0.0 and shadow_positive:
            return "aligned_positive", "continue_paper_observation_no_live_auto_promotion", sorted(set(causes)) or ["official_and_shadow_positive"]

        if official_closed > 0 and official_net <= 0.0 and shadow_net <= 0.0:
            return "aligned_negative", "avoid_scaling_this_setup", sorted(set(causes)) or ["official_and_shadow_not_positive"]

        return "learning", "collect_more_comparable_data", sorted(set(causes)) or ["insufficient_comparable_evidence"]

    def _summary(
        self,
        rows: list[Mapping[str, Any]],
        official_performance: Mapping[str, Any],
        shadow_snapshots: Mapping[str, Mapping[str, Any]],
    ) -> dict[str, Any]:
        verdict_counts: dict[str, int] = {}
        for row in rows:
            verdict = str(row.get("verdict") or "unknown")
            verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1

        official_global = official_performance.get("global", {}) if isinstance(official_performance, Mapping) else {}
        shadow_summary = {}
        for engine, snapshot in shadow_snapshots.items():
            summary = snapshot.get("summary", {}) if isinstance(snapshot, Mapping) else {}
            if isinstance(summary, Mapping):
                shadow_summary[engine] = {
                    "closed_shadow_trades": _safe_int(summary.get("closed_shadow_trades")),
                    "net_shadow_pnl_eur": round(_safe_float(summary.get("net_shadow_pnl_eur")), 4),
                    "candidate_symbols": _safe_int(summary.get("candidate_symbols")),
                }

        return {
            "symbols": len(rows),
            "verdict_counts": verdict_counts,
            "requires_attention": sum(1 for row in rows if row.get("verdict") in {"shadow_official_divergence", "official_underperforming"}),
            "official": {
                "closed_trades": _safe_int(official_global.get("closed_trades")),
                "net_pnl_eur": round(_safe_float(official_global.get("net_pnl")), 4),
                "profit_factor": _round_optional(official_global.get("profit_factor")),
                "win_rate": round(_safe_float(official_global.get("win_rate")), 2),
                "source": official_performance.get("source", "none") if isinstance(official_performance, Mapping) else "none",
            },
            "shadow": shadow_summary,
        }
