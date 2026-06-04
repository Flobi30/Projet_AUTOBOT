"""Research-only symbol normalization helpers.

AUTOBOT runtime data can contain Kraken exchange symbols (``XXBTZEUR``),
websocket names (``XBT/EUR``) and human-friendly aliases (``BTCZEUR``) in the
same research sample. This module canonicalizes those aliases for validation
datasets without changing runtime trading symbols.
"""

from __future__ import annotations

from typing import Iterable


_ALIAS_TO_CANONICAL = {
    "AAVE/EUR": "AAVEEUR",
    "AAVEZEUR": "AAVEEUR",
    "ADA/EUR": "ADAEUR",
    "ADAZEUR": "ADAEUR",
    "ATOM/EUR": "ATOMEUR",
    "ATOMZEUR": "ATOMEUR",
    "AVAX/EUR": "AVAXEUR",
    "AVAXZEUR": "AVAXEUR",
    "BCH/EUR": "BCHEUR",
    "BCHZEUR": "BCHEUR",
    "BTC/EUR": "BTCZEUR",
    "BTCEUR": "BTCZEUR",
    "BTCZEUR": "BTCZEUR",
    "DASH/EUR": "DASHEUR",
    "DASHZEUR": "DASHEUR",
    "DOGE/EUR": "DOGEEUR",
    "DOGEZEUR": "DOGEEUR",
    "DOT/EUR": "DOTEUR",
    "DOTZEUR": "DOTEUR",
    "ETH/EUR": "ETHZEUR",
    "ETHEUR": "ETHZEUR",
    "ETHZEUR": "ETHZEUR",
    "LINK/EUR": "LINKEUR",
    "LINKZEUR": "LINKEUR",
    "LTC/EUR": "LTCZEUR",
    "LTCEUR": "LTCZEUR",
    "LTCZEUR": "LTCZEUR",
    "SOL/EUR": "SOLEUR",
    "SOLZEUR": "SOLEUR",
    "TRX/EUR": "TRXEUR",
    "TRXZEUR": "TRXEUR",
    "UNI/EUR": "UNIEUR",
    "UNIZEUR": "UNIEUR",
    "XBT/EUR": "BTCZEUR",
    "XBTZEUR": "BTCZEUR",
    "XETHZEUR": "ETHZEUR",
    "XLTCZEUR": "LTCZEUR",
    "XLM/EUR": "XLMZEUR",
    "XLMEUR": "XLMZEUR",
    "XLMZEUR": "XLMZEUR",
    "XMR/EUR": "XMREUR",
    "XMRZEUR": "XMREUR",
    "XRP/EUR": "XRPZEUR",
    "XRPEUR": "XRPZEUR",
    "XRPZEUR": "XRPZEUR",
    "XXBTZEUR": "BTCZEUR",
    "XXLMZEUR": "XLMZEUR",
    "XXMRZEUR": "XMREUR",
    "XXRPZEUR": "XRPZEUR",
    "ZEC/EUR": "ZECEUR",
    "ZECZEUR": "ZECEUR",
}

_CANONICAL_TO_ALIASES: dict[str, tuple[str, ...]] = {}
for alias, canonical in _ALIAS_TO_CANONICAL.items():
    _CANONICAL_TO_ALIASES.setdefault(canonical, tuple())
for canonical in tuple(_CANONICAL_TO_ALIASES):
    aliases = sorted(alias for alias, value in _ALIAS_TO_CANONICAL.items() if value == canonical)
    _CANONICAL_TO_ALIASES[canonical] = tuple(aliases)


def normalize_research_symbol(symbol: str | None) -> str:
    """Return the canonical compact research symbol.

    Unknown symbols are upper-cased with separators removed. Known Kraken
    aliases are mapped to one stable representation such as ``BTCZEUR``.
    """

    raw = str(symbol or "").strip().upper()
    if not raw:
        return ""
    compact = raw.replace("/", "").replace("-", "").replace("_", "")
    return _ALIAS_TO_CANONICAL.get(raw) or _ALIAS_TO_CANONICAL.get(compact) or compact


def expand_research_symbol_aliases(symbols: Iterable[str]) -> tuple[str, ...]:
    """Expand canonical symbols to known aliases for SQLite filtering."""

    expanded: set[str] = set()
    for symbol in symbols:
        canonical = normalize_research_symbol(symbol)
        if not canonical:
            continue
        expanded.add(canonical)
        expanded.add(canonical.replace("ZEUR", "EUR") if canonical.endswith("ZEUR") else canonical)
        expanded.update(_CANONICAL_TO_ALIASES.get(canonical, ()))
    return tuple(sorted(expanded))


def symbol_alias_map() -> dict[str, str]:
    return dict(_ALIAS_TO_CANONICAL)
