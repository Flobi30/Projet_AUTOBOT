"""Controlled paper-only execution adapter for non-grid shadow engines.

This adapter never enables live trading. It can mirror a validated trend or
mean-reversion shadow candidate into the official paper execution pipeline,
while leaving the live path untouched.
"""

from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from .strategies import SignalType, TradingSignal


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


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_ts(value: Any) -> float:
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    if not value:
        return 0.0
    raw = str(value)
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return 0.0


@dataclass(frozen=True)
class ShadowPaperAdapterConfig:
    enabled: bool = True
    max_event_age_seconds: float = 180.0
    dedupe_ttl_seconds: float = 3600.0
    trend_enabled: bool = True
    mean_reversion_enabled: bool = True

    @classmethod
    def from_env(cls) -> "ShadowPaperAdapterConfig":
        return cls(
            enabled=_env_bool("PAPER_EXECUTION_ADAPTER_ENABLED", True),
            max_event_age_seconds=_env_float("PAPER_EXECUTION_ADAPTER_MAX_EVENT_AGE_SECONDS", 180.0, 5.0, 86_400.0),
            dedupe_ttl_seconds=_env_float("PAPER_EXECUTION_ADAPTER_DEDUPE_TTL_SECONDS", 3600.0, 30.0, 604_800.0),
            trend_enabled=_env_bool("PAPER_EXECUTION_ADAPTER_TREND_ENABLED", True),
            mean_reversion_enabled=_env_bool("PAPER_EXECUTION_ADAPTER_MEAN_REVERSION_ENABLED", True),
        )


class ShadowPaperExecutionAdapter:
    """Mirror validated non-grid shadow decisions into official paper signals."""

    def __init__(self, config: Optional[ShadowPaperAdapterConfig] = None) -> None:
        self.config = config or ShadowPaperAdapterConfig.from_env()
        self._seen_events: dict[str, float] = {}

    def _supported(self, engine: str) -> bool:
        if engine == "trend_momentum":
            return self.config.trend_enabled
        if engine == "mean_reversion":
            return self.config.mean_reversion_enabled
        return False

    def _prune_seen(self) -> None:
        now = time.monotonic()
        ttl = self.config.dedupe_ttl_seconds
        self._seen_events = {
            key: seen_at
            for key, seen_at in self._seen_events.items()
            if now - seen_at <= ttl
        }

    def _event_key(
        self,
        *,
        symbol: str,
        engine: str,
        variant: str,
        status: str,
        timestamp: Any,
        reason: str,
    ) -> str:
        raw = f"{symbol}|{engine}|{variant}|{status}|{timestamp}|{reason}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    async def mirror_if_needed(
        self,
        *,
        instance: Any,
        governance_row: Mapping[str, Any] | None,
        shadow_symbol_row: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        if not self.config.enabled:
            return {"handled": False, "reason": "adapter_disabled"}
        if not isinstance(governance_row, Mapping):
            return {"handled": False, "reason": "governance_missing"}
        if str(governance_row.get("execution_mode") or "") != "shadow_signal_mirror":
            return {"handled": False, "reason": str(governance_row.get("execution_mode") or "governance_not_mirroring")}
        engine = str(governance_row.get("selected_engine") or "")
        if not self._supported(engine):
            return {"handled": False, "reason": "engine_not_supported"}
        if not isinstance(shadow_symbol_row, Mapping):
            return {"handled": False, "reason": "shadow_symbol_missing"}

        best = shadow_symbol_row.get("best_variant")
        if not isinstance(best, Mapping):
            return {"handled": False, "reason": "best_variant_missing"}

        last_signal = best.get("last_signal") if isinstance(best.get("last_signal"), Mapping) else {}
        last_decision = best.get("last_decision") if isinstance(best.get("last_decision"), Mapping) else {}
        status = str(last_decision.get("status") or "")
        if status not in {"opened", "closed"}:
            return {"handled": False, "reason": f"shadow_status_{status or 'unknown'}"}

        timestamp = last_decision.get("timestamp") or last_signal.get("timestamp")
        age_seconds = max(0.0, time.time() - _parse_ts(timestamp))
        if age_seconds > self.config.max_event_age_seconds:
            return {"handled": False, "reason": "shadow_event_stale", "age_seconds": round(age_seconds, 3)}

        symbol = str(governance_row.get("symbol") or shadow_symbol_row.get("symbol") or "")
        variant = str(best.get("variant") or best.get("name") or "unknown_variant")
        reason = str(last_decision.get("reason") or last_signal.get("reason") or "shadow_signal")
        event_key = self._event_key(
            symbol=symbol,
            engine=engine,
            variant=variant,
            status=status,
            timestamp=timestamp,
            reason=reason,
        )
        self._prune_seen()
        if event_key in self._seen_events:
            return {"handled": False, "reason": "already_mirrored_recently"}

        handler = getattr(instance, "_signal_handler", None)
        if handler is None or not hasattr(handler, "_on_signal"):
            return {"handled": False, "reason": "signal_handler_unavailable"}

        open_positions = [
            pos for pos in instance.get_positions_snapshot()
            if str(pos.get("status") or "").lower() == "open"
        ]
        if status == "opened" and open_positions:
            return {
                "handled": False,
                "reason": "instance_not_flat",
                "open_positions": len(open_positions),
            }
        if status == "closed" and not open_positions:
            self._seen_events[event_key] = time.monotonic()
            return {"handled": False, "reason": "no_official_position_to_close"}

        signal = self._build_signal(
            symbol=symbol,
            engine=engine,
            best=best,
            last_signal=last_signal,
            last_decision=last_decision,
        )
        if signal is None:
            return {"handled": False, "reason": "unable_to_build_signal"}

        before_open = len(open_positions)
        await handler._on_signal(signal)
        after_open = len([
            pos for pos in instance.get_positions_snapshot()
            if str(pos.get("status") or "").lower() == "open"
        ])
        self._seen_events[event_key] = time.monotonic()
        return {
            "handled": True,
            "engine": engine,
            "variant": variant,
            "status": status,
            "signal": signal.to_dict(),
            "open_positions_before": before_open,
            "open_positions_after": after_open,
            "reason": reason,
        }

    def _build_signal(
        self,
        *,
        symbol: str,
        engine: str,
        best: Mapping[str, Any],
        last_signal: Mapping[str, Any],
        last_decision: Mapping[str, Any],
    ) -> Optional[TradingSignal]:
        status = str(last_decision.get("status") or "")
        if status == "opened":
            price = _safe_float(last_signal.get("price") or best.get("last_price"))
            if price <= 0.0:
                return None
            notional = _safe_float(last_decision.get("notional_eur"))
            volume = round((notional / price), 8) if notional > 0.0 else 0.0
            metadata = self._entry_metadata(
                engine=engine,
                best=best,
                last_signal=last_signal,
                last_decision=last_decision,
            )
            return TradingSignal(
                type=SignalType.BUY,
                symbol=symbol,
                price=price,
                volume=volume,
                reason=f"shadow_mirror:{engine}:{last_decision.get('reason') or last_signal.get('reason') or 'candidate'}",
                timestamp=datetime.now(timezone.utc),
                metadata=metadata,
            )
        if status == "closed":
            price = _safe_float(last_signal.get("price") or best.get("last_price"))
            if price <= 0.0:
                return None
            return TradingSignal(
                type=SignalType.SELL,
                symbol=symbol,
                price=price,
                volume=-1.0,
                reason=f"shadow_mirror_close:{engine}:{last_decision.get('reason') or 'exit'}",
                timestamp=datetime.now(timezone.utc),
                metadata={
                    "close_all": True,
                    "execution_engine": engine,
                    "execution_source": "shadow_signal_mirror",
                    "shadow_variant": best.get("variant") or best.get("name"),
                    "shadow_reason": last_decision.get("reason"),
                },
            )
        return None

    def _entry_metadata(
        self,
        *,
        engine: str,
        best: Mapping[str, Any],
        last_signal: Mapping[str, Any],
        last_decision: Mapping[str, Any],
    ) -> dict[str, Any]:
        features = last_signal.get("features") if isinstance(last_signal.get("features"), Mapping) else {}
        fee_per_side = 12.0
        slippage_per_side = 3.0
        if engine == "mean_reversion":
            expected_move_bps = max(
                _safe_float(features.get("expected_gross_edge_bps")),
                _safe_float(features.get("expected_net_edge_bps")) + 18.0,
                _safe_float(features.get("bandwidth_bps")) * 0.75,
                _safe_float(features.get("atr_bps")) * 1.4,
            )
            regime = "RANGE"
        else:
            expected_move_bps = max(
                _safe_float(features.get("breakout_bps")) + (_safe_float(features.get("atr_bps")) * 0.60),
                _safe_float(features.get("momentum_bps")) * 1.25,
                _safe_float(features.get("ema_spread_bps")) * 2.0,
                _safe_float(features.get("atr_bps")) * 1.50,
            )
            regime = "TREND"
        return {
            "strategy": "shadow_paper_adapter",
            "execution_source": "shadow_signal_mirror",
            "execution_engine": engine,
            "shadow_candidate": True,
            "shadow_variant": best.get("variant") or best.get("name"),
            "shadow_reason": last_decision.get("reason") or last_signal.get("reason"),
            "shadow_features": dict(features),
            "expected_move_bps": round(max(0.0, expected_move_bps), 4),
            "fee_bps": fee_per_side,
            "exit_fee_bps": fee_per_side,
            "slippage_bps": slippage_per_side,
            "regime": regime,
        }
