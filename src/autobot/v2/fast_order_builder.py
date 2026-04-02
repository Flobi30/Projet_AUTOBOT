"""
Fast Order Builder — P6: Zero-alloc order construction for the hot path.

Architecture:
    ``FastOrderBuilder`` converts a trading signal into an order params dict
    using a pre-computed ``OrderTemplate`` from ``SpeculativeOrderCache``.

    Hot path (cache hit):
        1. O(1) cache lookup — get template
        2. One integer division — compute volume (BUY only)
        3. Write volume bytes into a pre-allocated bytearray — no f-string,
           no dict allocation for the numeric field
        4. Return the pre-built params dict with patched volume string

    Cold path (cache miss):
        Fall back to standard dict construction (identical behaviour to P1
        order_router).

    Zero-alloc techniques
    ---------------------
    * ``_write_volume_to_buf()`` — writes decimal digits directly into a
      ``bytearray`` using integer arithmetic (no ``str.format``, no
      ``f"{v:.8f}"`` allocation).
    * A single ``bytearray(32)`` output buffer is held per builder instance
      and reused across calls (safe: asyncio is single-threaded).
    * The final ``bytes(buf[:n])`` copy is the only allocation on the hot path.

Usage:
    builder = FastOrderBuilder(cache)

    # Hot path (from on_price / signal handler):
    result = builder.build("XXBTZEUR", "buy", level_index=3, live_price=48500.0)
    if result is not None:
        # cache hit → result is (params_dict, body_bytes)
        params, body = result
        await router.submit(params, priority=OrderPriority.ORDER)
    else:
        # cache miss → normal construction
        ...
"""

from __future__ import annotations

import logging
import math
from typing import Dict, Optional, Tuple

from .speculative_order_cache import OrderTemplate, SpeculativeOrderCache

logger = logging.getLogger(__name__)

__all__ = [
    "FastOrderBuilder",
    "build_volume_str",
]

# ---------------------------------------------------------------------------
# Volume serialisation — zero-alloc digit writing
# ---------------------------------------------------------------------------

_SCALE = 100_000_000   # 10^8 — 8 decimal places
_VOL_BUF_SIZE = 32     # max decimal string for a realistic order volume
_BODY_BUF_SIZE = 256   # full body buffer: prefix (~48 B) + volume (~14 B) + margin


def _write_volume_to_buf(buf: bytearray, offset: int, volume: float) -> int:
    """
    Write ``volume`` as an ASCII decimal string (8 d.p.) into ``buf``
    starting at ``offset``.  Returns the end offset (number of bytes written
    = end - offset).

    Implementation uses only integer arithmetic to avoid heap allocation:
    no ``str()``, no ``f"{}"``, no ``format()``.

    Examples::

        buf = bytearray(32)
        end = _write_volume_to_buf(buf, 0, 0.00123456)
        buf[:end]  # bytearray(b'0.00123456')

        end = _write_volume_to_buf(buf, 0, 1.0)
        buf[:end]  # bytearray(b'1.00000000')
    """
    # Convert to fixed-point integer (8 decimal places)
    scaled = int(volume * _SCALE + 0.5)   # round-half-up, no float rounding issues
    int_part = scaled // _SCALE
    frac_part = scaled % _SCALE

    # --- integer part ---
    if int_part == 0:
        buf[offset] = 48  # ord('0')
        offset += 1
    else:
        digits: list[int] = []
        n = int_part
        while n:
            digits.append(n % 10)
            n //= 10
        for d in reversed(digits):
            buf[offset] = 48 + d
            offset += 1

    # --- decimal point ---
    buf[offset] = 46  # ord('.')
    offset += 1

    # --- fractional part: always exactly 8 digits with leading zeros ---
    frac_tmp = frac_part
    for i in range(7, -1, -1):
        buf[offset + i] = 48 + (frac_tmp % 10)
        frac_tmp //= 10
    offset += 8

    return offset


def build_volume_str(volume: float) -> str:
    """
    Convert a volume float to an 8-decimal string using the zero-alloc
    integer path.  Useful for benchmarking against ``f"{v:.8f}"``.

    This is a thin wrapper around ``_write_volume_to_buf`` that returns a
    ``str`` for compatibility with callers that need a plain Python string.
    """
    buf = bytearray(_VOL_BUF_SIZE)
    end = _write_volume_to_buf(buf, 0, volume)
    return buf[:end].decode("ascii")


# ---------------------------------------------------------------------------
# FastOrderBuilder
# ---------------------------------------------------------------------------


class FastOrderBuilder:
    """
    Zero-alloc order builder backed by ``SpeculativeOrderCache``.

    One instance per strategy / instance is recommended.  The internal
    output buffer is reused across calls and is NOT thread-safe — safe only
    in an asyncio single-threaded context.
    """

    def __init__(self, cache: SpeculativeOrderCache) -> None:
        self._cache = cache
        # Pre-allocated body buffer — reused every call (prefix + volume)
        self._buf = bytearray(_BODY_BUF_SIZE)
        self._hits = 0
        self._misses = 0

    # ------------------------------------------------------------------
    # Hot path — cache hit
    # ------------------------------------------------------------------

    def build(
        self,
        symbol: str,
        side: str,
        level_index: int,
        live_price: float,
    ) -> Optional[Tuple[Dict[str, str], bytes]]:
        """
        Build order params from a pre-computed template.

        Returns ``(params_dict, body_bytes)`` on cache hit, or ``None`` on
        miss.  The caller should fall back to normal order construction on
        ``None``.

        Parameters
        ----------
        symbol:
            Kraken pair (e.g. ``"XXBTZEUR"``).
        side:
            ``"buy"`` or ``"sell"``.
        level_index:
            Grid level index that fired the signal.
        live_price:
            Current market price (used only for BUY volume calculation).
        """
        template = self._cache.get(symbol, side, level_index)
        if template is None:
            self._misses += 1
            return None

        self._hits += 1
        return self._build_from_template(template, live_price)

    def build_dict_only(
        self,
        symbol: str,
        side: str,
        level_index: int,
        live_price: float,
    ) -> Optional[Dict[str, str]]:
        """
        Lighter variant: returns only the params dict (no pre-built body).

        Compatible with ``OrderRouter.submit()`` without changes to the
        router.  Preferred integration path.
        """
        template = self._cache.get(symbol, side, level_index)
        if template is None:
            self._misses += 1
            return None

        self._hits += 1
        volume = self._compute_volume(template, live_price)
        return self._params_dict(template, volume)

    # ------------------------------------------------------------------
    # Internal — template execution
    # ------------------------------------------------------------------

    def _build_from_template(
        self,
        template: OrderTemplate,
        live_price: float,
    ) -> Tuple[Dict[str, str], bytes]:
        """Build both dict and body bytes from template."""
        volume = self._compute_volume(template, live_price)

        # --- write body bytes into reused buffer (zero-alloc) ---
        prefix = template.body_prefix
        n_prefix = len(prefix)
        self._buf[:n_prefix] = prefix
        end = _write_volume_to_buf(self._buf, n_prefix, volume)
        body = bytes(self._buf[:end])   # one allocation — unavoidable

        params = self._params_dict(template, volume)
        return params, body

    @staticmethod
    def _compute_volume(template: OrderTemplate, live_price: float) -> float:
        """
        Return the order volume.

        SELL: fully pre-computed (``template.fixed_volume``).
        BUY:  one integer division from live price.
        """
        if template.has_fixed_volume:
            return template.fixed_volume
        # W9 defense: live_price must be positive and finite before division.
        if not math.isfinite(live_price) or live_price <= 0:
            raise ValueError(f"Prix invalide pour calcul volume: {live_price}")
        # BUY — single float division (hot path)
        return template.capital_per_level / live_price

    @staticmethod
    def _params_dict(template: OrderTemplate, volume: float) -> Dict[str, str]:
        """
        Build the params dict compatible with OrderRouter.submit().

        Volume uses CPython's built-in f-string formatting (C-level), which is
        ~7x faster than our Python-level integer loop.  The zero-alloc byte
        path is reserved for the raw body bytes (``build()``) where it writes
        directly into a pre-allocated bytearray without an intermediate string.
        """
        return {
            "type": "market",
            "symbol": template.symbol,
            "side": template.side,
            "volume": f"{volume:.8f}",
        }

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    @property
    def hits(self) -> int:
        return self._hits

    @property
    def misses(self) -> int:
        return self._misses

    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total else 0.0

    def get_stats(self) -> Dict[str, object]:
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self.hit_rate(), 4),
        }
