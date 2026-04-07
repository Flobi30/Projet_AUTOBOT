"""
Adaptive Grid Configuration — PairProfileRegistry + DynamicGridAllocator

Provides per-pair profiles (range, levels, capital allocation) and a registry
to look them up at runtime.  Falls back to a sensible default so existing
behaviour is 100 % preserved when no pair-specific config exists.

O(1) lookup via dict, no I/O, fully sync (CPU-only), thread-safe for reads
(immutable after init).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

__all__ = [
    "PairProfile",
    "PairProfileRegistry",
    "DynamicGridAllocator",
    "get_default_registry",
]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PairProfile — immutable config for a single pair
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class PairProfile:
    """Per-pair trading profile for the adaptive grid.

    Attributes:
        symbol:                 Canonical symbol (e.g. "XXBTZEUR").
        base_range_pct:         Default range +/-% when volatility data is unavailable.
        min_range_pct:          Hard floor for adaptive range (prevents ultra-tight grids).
        max_range_pct:          Hard ceiling for adaptive range (prevents ultra-wide grids).
        base_num_levels:        Default grid level count.
        min_levels:             Minimum levels (low-vol environment).
        max_levels:             Maximum levels (high-vol environment).
        max_capital_per_level:  Max EUR per level (absolute cap).
        capital_weight:         Relative weight for cross-pair capital allocation.
        atr_multiplier:         Scales ATR -> range.  range_pct = ATR% * atr_multiplier.
        hv_ratio_band:          (low, high) — HV24/HV7d ratio thresholds for regime switch.
        enable_multi_grid:      Allow short-term + long-term grids for this pair.
        tags:                   Free-form tags (e.g. "major", "altcoin", "forex").
    """

    symbol: str
    base_range_pct: float = 7.0
    min_range_pct: float = 2.0
    max_range_pct: float = 15.0
    base_num_levels: int = 15
    min_levels: int = 5
    max_levels: int = 30
    max_capital_per_level: float = 50.0
    capital_weight: float = 1.0
    atr_multiplier: float = 2.5
    hv_ratio_band: Tuple[float, float] = (0.7, 1.3)
    enable_multi_grid: bool = False
    tags: Tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Default profiles for well-known pairs
# ---------------------------------------------------------------------------

_DEFAULT_PROFILES: Dict[str, PairProfile] = {
    # --- BTC ---
    "XXBTZEUR": PairProfile(
        symbol="XXBTZEUR",
        base_range_pct=2.0,
        min_range_pct=0.8,
        max_range_pct=5.0,
        base_num_levels=15,
        min_levels=8,
        max_levels=25,
        max_capital_per_level=100.0,
        capital_weight=1.5,
        atr_multiplier=1.5,
        hv_ratio_band=(0.7, 1.3),
        enable_multi_grid=True,
        tags=("major", "btc"),
    ),
    "XXBTZUSD": PairProfile(
        symbol="XXBTZUSD",
        base_range_pct=2.0,
        min_range_pct=0.8,
        max_range_pct=5.0,
        base_num_levels=15,
        min_levels=8,
        max_levels=25,
        max_capital_per_level=100.0,
        capital_weight=1.5,
        atr_multiplier=1.5,
        hv_ratio_band=(0.7, 1.3),
        enable_multi_grid=True,
        tags=("major", "btc"),
    ),
    # --- ETH ---
    "XETHZEUR": PairProfile(
        symbol="XETHZEUR",
        base_range_pct=3.0,
        min_range_pct=1.2,
        max_range_pct=6.0,
        base_num_levels=15,
        min_levels=8,
        max_levels=25,
        max_capital_per_level=80.0,
        capital_weight=1.3,
        atr_multiplier=1.8,
        hv_ratio_band=(0.65, 1.35),
        enable_multi_grid=True,
        tags=("major", "eth"),
    ),
    "XETHZUSD": PairProfile(
        symbol="XETHZUSD",
        base_range_pct=3.0,
        min_range_pct=1.2,
        max_range_pct=6.0,
        base_num_levels=15,
        min_levels=8,
        max_levels=25,
        max_capital_per_level=80.0,
        capital_weight=1.3,
        atr_multiplier=1.8,
        hv_ratio_band=(0.65, 1.35),
        enable_multi_grid=True,
        tags=("major", "eth"),
    ),
    # --- XRP ---
    "XXRPZEUR": PairProfile(
        symbol="XXRPZEUR",
        base_range_pct=4.0,
        min_range_pct=1.5,
        max_range_pct=8.0,
        base_num_levels=15,
        min_levels=8,
        max_levels=25,
        max_capital_per_level=40.0,
        capital_weight=0.8,
        atr_multiplier=2.0,
        hv_ratio_band=(0.6, 1.4),
        tags=("altcoin", "xrp"),
    ),
    # --- SOL ---
    "SOLEUR": PairProfile(
        symbol="SOLEUR",
        base_range_pct=4.0,
        min_range_pct=1.5,
        max_range_pct=8.0,
        base_num_levels=15,
        min_levels=8,
        max_levels=25,
        max_capital_per_level=40.0,
        capital_weight=0.9,
        atr_multiplier=2.0,
        hv_ratio_band=(0.6, 1.4),
        tags=("altcoin", "sol"),
    ),
    "SOLUSD": PairProfile(
        symbol="SOLUSD",
        base_range_pct=4.0,
        min_range_pct=1.5,
        max_range_pct=8.0,
        base_num_levels=15,
        min_levels=8,
        max_levels=25,
        max_capital_per_level=40.0,
        capital_weight=0.9,
        atr_multiplier=2.0,
        hv_ratio_band=(0.6, 1.4),
        tags=("altcoin", "sol"),
    ),
    # --- ADA ---
    "ADAEUR": PairProfile(
        symbol="ADAEUR",
        base_range_pct=4.0,
        min_range_pct=2.0,
        max_range_pct=8.0,
        base_num_levels=15,
        min_levels=8,
        max_levels=25,
        max_capital_per_level=30.0,
        capital_weight=0.6,
        atr_multiplier=2.0,
        hv_ratio_band=(0.55, 1.45),
        tags=("altcoin", "ada"),
    ),
    # --- LINK ---
    "LINKEUR": PairProfile(
        symbol="LINKEUR",
        base_range_pct=4.0,
        min_range_pct=1.5,
        max_range_pct=8.0,
        base_num_levels=15,
        min_levels=8,
        max_levels=25,
        max_capital_per_level=30.0,
        capital_weight=0.7,
        atr_multiplier=2.0,
        hv_ratio_band=(0.55, 1.45),
        tags=("altcoin", "link"),
    ),
    # --- MATIC ---
    "POLEUR": PairProfile(
        symbol="POLEUR",
        base_range_pct=4.5,
        min_range_pct=1.5,
        max_range_pct=8.0,
        base_num_levels=15,
        min_levels=8,
        max_levels=25,
        max_capital_per_level=25.0,
        capital_weight=0.5,
        atr_multiplier=2.0,
        hv_ratio_band=(0.55, 1.45),
        tags=("altcoin", "pol"),
    ),
    # --- AVAX ---
    "AVAXEUR": PairProfile(
        symbol="AVAXEUR",
        base_range_pct=4.5,
        min_range_pct=1.5,
        max_range_pct=8.0,
        base_num_levels=15,
        min_levels=8,
        max_levels=25,
        max_capital_per_level=30.0,
        capital_weight=0.6,
        atr_multiplier=2.0,
        hv_ratio_band=(0.55, 1.45),
        tags=("altcoin", "avax"),
    ),
    # --- UNI ---
    "UNIEUR": PairProfile(
        symbol="UNIEUR",
        base_range_pct=4.5,
        min_range_pct=1.5,
        max_range_pct=8.0,
        base_num_levels=15,
        min_levels=8,
        max_levels=25,
        max_capital_per_level=25.0,
        capital_weight=0.5,
        atr_multiplier=2.0,
        hv_ratio_band=(0.55, 1.45),
        tags=("altcoin", "uni"),
    ),
    # --- DOT ---
    "DOTEUR": PairProfile(
        symbol="DOTEUR",
        base_range_pct=4.0,
        min_range_pct=2.0,
        max_range_pct=8.0,
        base_num_levels=15,
        min_levels=8,
        max_levels=25,
        max_capital_per_level=30.0,
        capital_weight=0.6,
        atr_multiplier=2.0,
        hv_ratio_band=(0.55, 1.45),
        tags=("altcoin", "dot"),
    ),
}

# Fallback profile used when no pair-specific config exists
_FALLBACK_PROFILE = PairProfile(
    symbol="__fallback__",
    base_range_pct=3.0,
    min_range_pct=1.2,
    max_range_pct=8.0,
    base_num_levels=15,
    min_levels=8,
    max_levels=25,
    max_capital_per_level=50.0,
    capital_weight=1.0,
    atr_multiplier=2.0,
    hv_ratio_band=(0.7, 1.3),
    tags=("unknown",),
)


# ---------------------------------------------------------------------------
# PairProfileRegistry — O(1) lookup, immutable after construction
# ---------------------------------------------------------------------------

class PairProfileRegistry:
    """Registry of per-pair profiles for adaptive grid trading.

    The registry is populated at construction time and is read-only afterwards.
    ``get()`` is O(1) dict lookup — safe for the hot path.

    If no profile exists for a given symbol, a sensible fallback is returned
    that preserves the legacy 7% / 15-level behaviour.
    """

    def __init__(
        self,
        profiles: Optional[Dict[str, PairProfile]] = None,
        *,
        use_defaults: bool = True,
    ) -> None:
        self._profiles: Dict[str, PairProfile] = {}
        if use_defaults:
            self._profiles.update(_DEFAULT_PROFILES)
        if profiles:
            self._profiles.update(profiles)

        logger.info(
            "PairProfileRegistry: %d profils charges (%d defauts, %d custom)",
            len(self._profiles),
            len(_DEFAULT_PROFILES) if use_defaults else 0,
            len(profiles) if profiles else 0,
        )

    # O(1) hot-path lookup
    def get(self, symbol: str) -> PairProfile:
        """Return the profile for *symbol*, or the fallback profile."""
        return self._profiles.get(symbol, _FALLBACK_PROFILE)

    def has(self, symbol: str) -> bool:
        """Check whether an explicit profile exists for *symbol*."""
        return symbol in self._profiles

    def register(self, profile: PairProfile) -> None:
        """Register (or override) a profile at runtime."""
        self._profiles[profile.symbol] = profile
        logger.info("PairProfileRegistry: profil enregistre pour %s", profile.symbol)

    @property
    def symbols(self) -> List[str]:
        return list(self._profiles.keys())

    @property
    def fallback(self) -> PairProfile:
        return _FALLBACK_PROFILE

    def get_all(self) -> Dict[str, PairProfile]:
        return dict(self._profiles)


# ---------------------------------------------------------------------------
# DynamicGridAllocator — compute levels + capital per level
# ---------------------------------------------------------------------------

class DynamicGridAllocator:
    """Compute the number of grid levels and capital per level dynamically.

    Uses the pair profile + current volatility data to decide:
    - How many levels (more levels in high-vol, fewer in calm markets)
    - How much capital per level (inverse-vol weighting)

    All methods are pure functions (no I/O, no state mutation), O(1).
    """

    @staticmethod
    def compute_num_levels(
        profile: PairProfile,
        atr_pct: Optional[float] = None,
    ) -> int:
        """Determine the number of grid levels for current conditions.

        High ATR -> more levels (wider grid needs more granularity).
        No ATR data -> fall back to ``profile.base_num_levels``.

        Returns:
            Integer in [profile.min_levels, profile.max_levels].
        """
        if atr_pct is None or atr_pct <= 0:
            return profile.base_num_levels

        # Linear interpolation: ATR% 1->min_levels, ATR% 10->max_levels
        t = max(0.0, min(1.0, (atr_pct - 1.0) / 9.0))
        raw = profile.min_levels + t * (profile.max_levels - profile.min_levels)
        return max(profile.min_levels, min(profile.max_levels, int(round(raw))))

    @staticmethod
    def compute_capital_per_level(
        profile: PairProfile,
        available_capital: float,
        num_levels: int,
        max_positions: int = 10,
        atr_pct: Optional[float] = None,
    ) -> float:
        """Determine the EUR amount to deploy per grid level.

        Applies inverse-volatility scaling: higher ATR -> smaller per-level
        allocation (risk reduction).

        Returns:
            Capital per level in EUR, clamped to [5.0, profile.max_capital_per_level].
        """
        if available_capital <= 0 or num_levels <= 0:
            return 5.0

        usable = available_capital * 0.90
        max_buys = max(1, max_positions)
        base_cpl = usable / max_buys

        # Inverse-vol scaling: if ATR is high, reduce allocation
        if atr_pct is not None and atr_pct > 0:
            vol_scale = max(0.4, min(1.0, 1.0 - (atr_pct - 2.0) * 0.1))
            base_cpl *= vol_scale

        return max(5.0, min(base_cpl, profile.max_capital_per_level))

    @staticmethod
    def compute_grid_config(
        profile: PairProfile,
        available_capital: float,
        atr_pct: Optional[float] = None,
        max_positions: int = 10,
    ) -> Dict[str, float]:
        """One-shot helper: compute all grid parameters at once.

        Returns:
            Dict with keys: num_levels, capital_per_level, range_pct.
        """
        num_levels = DynamicGridAllocator.compute_num_levels(profile, atr_pct)
        cpl = DynamicGridAllocator.compute_capital_per_level(
            profile, available_capital, num_levels, max_positions, atr_pct,
        )
        # Range: use ATR if available, else base
        if atr_pct is not None and atr_pct > 0:
            range_pct = max(
                profile.min_range_pct,
                min(profile.max_range_pct, atr_pct * profile.atr_multiplier),
            )
        else:
            range_pct = profile.base_range_pct

        return {
            "num_levels": num_levels,
            "capital_per_level": cpl,
            "range_pct": range_pct,
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_registry: Optional[PairProfileRegistry] = None


def get_default_registry() -> PairProfileRegistry:
    """Return the module-level singleton registry (lazy init)."""
    global _registry
    if _registry is None:
        _registry = PairProfileRegistry()
    return _registry