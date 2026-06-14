"""Canonical execution-cost profiles shared across AUTOBOT.

The module contains assumptions only. It does not submit orders and does not
change runtime trading flags. Research code may use explicit overrides, but
the selected profile remains visible in every serialized cost configuration.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class CostProfile:
    name: str
    maker_fee_bps: float
    taker_fee_bps: float
    fallback_spread_bps: float
    slippage_bps_per_leg: float
    latency_buffer_bps_per_leg: float
    entry_liquidity: str
    exit_liquidity: str
    spread_model: str
    slippage_model: str
    spread_charge_fraction: float
    legacy: bool = False
    runtime_comparable: bool = True
    description: str = ""

    def fee_bps(self, liquidity: str) -> float:
        if liquidity == "maker":
            return self.maker_fee_bps
        if liquidity == "taker":
            return self.taker_fee_bps
        raise ValueError(f"unsupported liquidity type: {liquidity}")

    @property
    def round_trip_cost_estimate_bps(self) -> float:
        return (
            self.fee_bps(self.entry_liquidity)
            + self.fee_bps(self.exit_liquidity)
            + (self.fallback_spread_bps * self.spread_charge_fraction)
            + (2.0 * self.slippage_bps_per_leg)
            + (2.0 * self.latency_buffer_bps_per_leg)
        )

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["round_trip_cost_estimate_bps"] = self.round_trip_cost_estimate_bps
        return payload


_PROFILES = {
    "paper_current_taker": CostProfile(
        name="paper_current_taker",
        maker_fee_bps=25.0,
        taker_fee_bps=40.0,
        fallback_spread_bps=8.0,
        slippage_bps_per_leg=3.0,
        latency_buffer_bps_per_leg=0.0,
        entry_liquidity="taker",
        exit_liquidity="taker",
        spread_model="observed_top_of_book_or_8bps_fallback",
        slippage_model="runtime_guard_6bps_round_trip",
        spread_charge_fraction=1.0,
        description="Current paper taker/taker assumptions and runtime guard fallback.",
    ),
    "paper_current_maker": CostProfile(
        name="paper_current_maker",
        maker_fee_bps=25.0,
        taker_fee_bps=40.0,
        fallback_spread_bps=8.0,
        slippage_bps_per_leg=0.0,
        latency_buffer_bps_per_leg=0.0,
        entry_liquidity="maker",
        exit_liquidity="maker",
        spread_model="post_only_no_cross",
        slippage_model="post_only_fill_no_extra_slippage",
        spread_charge_fraction=0.0,
        description="Maker/maker only when realistic post-only fill rules are used.",
    ),
    "research_stress": CostProfile(
        name="research_stress",
        maker_fee_bps=25.0,
        taker_fee_bps=40.0,
        fallback_spread_bps=8.0,
        slippage_bps_per_leg=4.0,
        latency_buffer_bps_per_leg=1.0,
        entry_liquidity="taker",
        exit_liquidity="taker",
        spread_model="observed_top_of_book_or_8bps_fallback",
        slippage_model="fixed_4bps_per_leg_plus_1bps_latency",
        spread_charge_fraction=1.0,
        description="Conservative research profile aligned with current paper fees.",
    ),
    "research_legacy": CostProfile(
        name="research_legacy",
        maker_fee_bps=10.0,
        taker_fee_bps=16.0,
        fallback_spread_bps=8.0,
        slippage_bps_per_leg=4.0,
        latency_buffer_bps_per_leg=1.0,
        entry_liquidity="taker",
        exit_liquidity="taker",
        spread_model="fixed_or_observed_8bps_fallback",
        slippage_model="fixed_4bps_per_leg_plus_1bps_latency",
        spread_charge_fraction=1.0,
        legacy=True,
        runtime_comparable=False,
        description="Historical 16bps research profile; not comparable to current paper runtime.",
    ),
}

COST_PROFILE_NAMES = tuple(_PROFILES)
DEFAULT_RESEARCH_COST_PROFILE = "research_stress"
DEFAULT_PAPER_COST_PROFILE = "paper_current_taker"


def get_cost_profile(name: str) -> CostProfile:
    try:
        return _PROFILES[name]
    except KeyError as exc:
        choices = ", ".join(COST_PROFILE_NAMES)
        raise ValueError(f"unknown cost profile {name!r}; expected one of: {choices}") from exc
