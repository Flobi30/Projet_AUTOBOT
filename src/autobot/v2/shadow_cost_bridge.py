"""Cost bridge for legacy shadow simulators.

Shadow labs still use a legacy per-side cost shape:

``fee_bps_per_side + slippage_bps_per_side``

The research replay engine uses a richer model:

``fee + half spread + slippage + latency``

This module converts the richer research default into the legacy shape so
shadow results are not easier than replay/backtest results.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .research.execution_cost_model import ExecutionCostConfig


@dataclass(frozen=True)
class LegacyShadowCostDefaults:
    fee_bps_per_side: float
    slippage_bps_per_side: float
    effective_cost_bps_per_side: float
    source: str = "research_execution_cost_model_legacy_shadow_bridge"

    def to_dict(self) -> dict[str, float | str]:
        return asdict(self)


def conservative_shadow_cost_defaults(config: ExecutionCostConfig | None = None) -> LegacyShadowCostDefaults:
    """Return conservative legacy shadow costs derived from research costs.

    The legacy ``slippage`` bucket includes actual slippage, latency and half
    the fallback spread because the old shadow labs do not model spread
    separately.
    """

    cfg = config or ExecutionCostConfig()
    cfg.validate()
    fee_bps = float(cfg.taker_fee_bps)
    legacy_slippage_bps = float(cfg.slippage_bps) + float(cfg.latency_buffer_bps) + (float(cfg.fallback_spread_bps) / 2.0)
    return LegacyShadowCostDefaults(
        fee_bps_per_side=fee_bps,
        slippage_bps_per_side=legacy_slippage_bps,
        effective_cost_bps_per_side=fee_bps + legacy_slippage_bps,
    )
