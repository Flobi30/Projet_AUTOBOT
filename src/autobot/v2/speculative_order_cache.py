"""
Speculative Order Cache — P6: Pre-computed order templates for zero-latency execution.

Architecture:
    Pre-compute order templates at each grid level so that when a signal fires,
    the order params are already built — only the volume (price-dependent) needs
    a single integer division at signal time.

    For market SELL orders with a known position volume, templates are fully
    pre-computed (zero compute on signal).

    Template storage:
        Key: (symbol, side, level_index)
        Value: OrderTemplate with pre-built bytes prefix + capital metadata

Usage:
    cache = SpeculativeOrderCache()
    cache.precompute_grid_levels("XXBTZEUR", grid_levels, capital_per_level=50.0)

    # Hot path — O(1) lookup
    template = cache.get("XXBTZEUR", "buy", level_index=3)
    if template is not None:
        # cache hit — build order
        ...
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

__all__ = [
    "OrderTemplate",
    "SpeculativeOrderCache",
]

# ---------------------------------------------------------------------------
# Cache key type
# ---------------------------------------------------------------------------

CacheKey = Tuple[str, str, int]  # (symbol, side, level_index)

# ---------------------------------------------------------------------------
# OrderTemplate
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OrderTemplate:
    """
    Immutable pre-computed order template.

    Stores the static URL-encoded body prefix for a Kraken AddOrder request
    (everything up to and including ``volume=``).  The caller patches the
    volume value inline into a pre-allocated bytearray — no dict allocation,
    no string formatting during the hot path.

    Fields
    ------
    key
        Cache key ``(symbol, side, level_index)``.
    symbol
        Kraken pair (e.g. ``"XXBTZEUR"``).
    side
        ``"buy"`` or ``"sell"``.
    level_index
        Index into the grid levels list.
    level_price
        Pre-computed grid level price (used to approximate volume for buys).
    capital_per_level
        EUR capital allocated per grid level (>0 for BUY, 0.0 for SELL).
    fixed_volume
        Pre-computed volume for SELL orders (from open position). ``-1.0``
        means "compute from live price" (BUY path).
    body_prefix
        URL-encoded bytes ending with ``b"volume="``.
        e.g. ``b"pair=XXBTZEUR&type=buy&ordertype=market&volume="``.
    vol_field_width
        Reserved bytes for the volume value in a pre-allocated buffer.
        Must accommodate the widest possible decimal string (16 bytes).
    """

    key: CacheKey
    symbol: str
    side: str
    level_index: int
    level_price: float
    capital_per_level: float
    fixed_volume: float       # -1.0 = compute at signal time (BUY)
    body_prefix: bytes        # URL-encoded static prefix
    vol_field_width: int = 16 # chars reserved for volume in output buffer

    @property
    def has_fixed_volume(self) -> bool:
        """True for SELL templates where volume is fully pre-computed."""
        return self.fixed_volume >= 0.0


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


class SpeculativeOrderCache:
    """
    Cache of pre-computed OrderTemplates keyed by (symbol, side, level_index).

    Thread-safety
    -------------
    Templates are inserted once (at strategy init) and then only read.
    Reads are O(1) dict lookups — safe in CPython's GIL / asyncio single thread.

    Stats
    -----
    ``hits`` / ``misses`` counters for monitoring cache effectiveness.
    """

    def __init__(self) -> None:
        self._store: Dict[CacheKey, OrderTemplate] = {}
        self._hits: int = 0
        self._misses: int = 0

    # ------------------------------------------------------------------
    # Write API (called at init / grid recenter)
    # ------------------------------------------------------------------

    def store(self, template: OrderTemplate) -> None:
        """Insert or replace a template in the cache."""
        self._store[template.key] = template

    def precompute_grid_levels(
        self,
        symbol: str,
        grid_levels: List[float],
        capital_per_level: float,
    ) -> None:
        """
        Pre-compute BUY templates for every grid level.

        Called once when the grid is initialised (or after a recenter).
        Each BUY template stores ``capital_per_level`` so that volume is
        computed as ``capital / live_price`` with a single division at
        signal time.

        SELL templates are created later via ``store_sell_template()``
        once a position is opened and its volume is known.
        """
        if capital_per_level <= 0:
            raise ValueError(f"capital_per_level must be > 0, got {capital_per_level}")

        for idx, price in enumerate(grid_levels):
            prefix = _build_body_prefix(symbol, "buy")
            t = OrderTemplate(
                key=(symbol, "buy", idx),
                symbol=symbol,
                side="buy",
                level_index=idx,
                level_price=price,
                capital_per_level=capital_per_level,
                fixed_volume=-1.0,
                body_prefix=prefix,
            )
            self._store[t.key] = t

        logger.debug(
            "🗃️ SpecCache: %d BUY templates pré-calculés pour %s "
            "(capital/level=%.2f€)",
            len(grid_levels),
            symbol,
            capital_per_level,
        )

    def store_sell_template(
        self,
        symbol: str,
        level_index: int,
        level_price: float,
        volume: float,
    ) -> None:
        """
        Pre-compute a SELL template for an open position.

        Called by the strategy when a position is opened.  The volume is
        fully known so the template is completely pre-computed.
        """
        prefix = _build_body_prefix(symbol, "sell")
        t = OrderTemplate(
            key=(symbol, "sell", level_index),
            symbol=symbol,
            side="sell",
            level_index=level_index,
            level_price=level_price,
            capital_per_level=0.0,
            fixed_volume=volume,
            body_prefix=prefix,
        )
        self._store[t.key] = t

    def invalidate(self, symbol: str, side: str, level_index: int) -> None:
        """Remove a single template from the cache."""
        self._store.pop((symbol, side, level_index), None)

    def invalidate_symbol(self, symbol: str) -> None:
        """Remove all templates for a symbol (e.g. after grid recenter)."""
        keys = [k for k in self._store if k[0] == symbol]
        for k in keys:
            del self._store[k]

    # ------------------------------------------------------------------
    # Read API (hot path)
    # ------------------------------------------------------------------

    def get(
        self,
        symbol: str,
        side: str,
        level_index: int,
    ) -> Optional[OrderTemplate]:
        """
        O(1) template lookup — hot path.

        Returns ``None`` on cache miss so the caller can fall back to
        normal order construction.
        """
        t = self._store.get((symbol, side, level_index))
        if t is not None:
            self._hits += 1
        else:
            self._misses += 1
        return t

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    @property
    def hits(self) -> int:
        return self._hits

    @property
    def misses(self) -> int:
        return self._misses

    @property
    def size(self) -> int:
        return len(self._store)

    def hit_rate(self) -> float:
        """Fraction of lookups that were cache hits (0.0–1.0)."""
        total = self._hits + self._misses
        return self._hits / total if total else 0.0

    def reset_stats(self) -> None:
        self._hits = 0
        self._misses = 0

    def get_stats(self) -> Dict[str, object]:
        return {
            "size": self.size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self.hit_rate(), 4),
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_body_prefix(symbol: str, side: str) -> bytes:
    """
    Build the static URL-encoded body prefix for a Kraken market order.

    Result ends with ``b"volume="`` so the caller can append the volume
    value directly.

    Example::

        _build_body_prefix("XXBTZEUR", "buy")
        # b"pair=XXBTZEUR&type=buy&ordertype=market&volume="
    """
    return (
        f"pair={symbol}&type={side}&ordertype=market&volume="
    ).encode("ascii")
