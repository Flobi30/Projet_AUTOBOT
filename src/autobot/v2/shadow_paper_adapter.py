"""Retired bridge from shadow candidates to legacy paper signals.

The previous bridge converted shadow observations into legacy runtime signals,
skipping the canonical portfolio, risk and OMS contracts.  During the
research/shadow programme it is deliberately fail-closed: no caller or
environment variable can make it create a paper/runtime signal.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from typing import Any, Mapping, Optional

from .shadow_cost_bridge import conservative_shadow_cost_defaults


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


@dataclass(frozen=True)
class ShadowPaperAdapterConfig:
    enabled: bool = False
    max_event_age_seconds: float = 180.0
    dedupe_ttl_seconds: float = 3600.0
    trend_enabled: bool = True
    mean_reversion_enabled: bool = True

    @classmethod
    def from_env(cls) -> "ShadowPaperAdapterConfig":
        # Ignore the legacy enable switch.  A future migration must introduce a
        # separate contract-backed adapter rather than revive this bypass.
        return cls(
            enabled=False,
            max_event_age_seconds=_env_float("PAPER_EXECUTION_ADAPTER_MAX_EVENT_AGE_SECONDS", 180.0, 5.0, 86_400.0),
            dedupe_ttl_seconds=_env_float("PAPER_EXECUTION_ADAPTER_DEDUPE_TTL_SECONDS", 3600.0, 30.0, 604_800.0),
            trend_enabled=_env_bool("PAPER_EXECUTION_ADAPTER_TREND_ENABLED", True),
            mean_reversion_enabled=_env_bool("PAPER_EXECUTION_ADAPTER_MEAN_REVERSION_ENABLED", True),
        )


class ShadowPaperExecutionAdapter:
    """Quarantined legacy bridge; it can never create an official signal."""

    def __init__(self, config: Optional[ShadowPaperAdapterConfig] = None) -> None:
        self.config = replace(config or ShadowPaperAdapterConfig.from_env(), enabled=False)

    async def mirror_if_needed(
        self,
        *,
        instance: Any,
        governance_row: Mapping[str, Any] | None,
        shadow_symbol_row: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        # This must remain before every handler or position lookup.  Even a
        # populated legacy candidate must not reach ``_on_signal``.
        return {
            "handled": False,
            "reason": "legacy_shadow_paper_bridge_retired",
            "research_only": True,
            "paper_capital_allowed": False,
            "live_allowed": False,
        }

    def _entry_metadata(
        self,
        *,
        engine: str,
        best: Mapping[str, Any],
        last_signal: Mapping[str, Any],
        last_decision: Mapping[str, Any],
    ) -> dict[str, Any]:
        features = last_signal.get("features") if isinstance(last_signal.get("features"), Mapping) else {}
        cost_defaults = conservative_shadow_cost_defaults()
        fee_per_side = cost_defaults.fee_bps_per_side
        slippage_per_side = cost_defaults.slippage_bps_per_side
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
            "effective_cost_bps_per_side": cost_defaults.effective_cost_bps_per_side,
            "cost_model_source": cost_defaults.source,
            "regime": regime,
        }
