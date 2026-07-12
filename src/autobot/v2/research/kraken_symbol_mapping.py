"""Central Kraken public-symbol mapping for AUTOBOT research.

This module resolves AUTOBOT research symbols to Kraken public REST asset-pair
identifiers for OHLCV and depth collection. It uses public endpoints only,
never reads private credentials, and is intentionally isolated from paper/live
order execution.
"""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Callable, Mapping, Sequence

from .symbol_normalization import expand_research_symbol_aliases, normalize_research_symbol


KRAKEN_PUBLIC_ASSET_PAIRS_URL = "https://api.kraken.com/0/public/AssetPairs"

# These are explicit Kraken asset identifiers, not string heuristics.  Kraken's
# public AssetPairs response identifies both legs of a market, but uses a small
# set of venue-specific aliases (for example XBT and ZEUR).  Unknown values are
# deliberately left unmapped rather than stripped or guessed.
KRAKEN_EXPLICIT_ASSET_ALIASES = {
    "XBT": "BTC",
    "XXBT": "BTC",
    "BTC": "BTC",
    "XETH": "ETH",
    "ETH": "ETH",
    "XLTC": "LTC",
    "LTC": "LTC",
    "XXLM": "XLM",
    "XLM": "XLM",
    "XXRP": "XRP",
    "XRP": "XRP",
    "SOL": "SOL",
    "TRX": "TRX",
    "ADA": "ADA",
    "LINK": "LINK",
    "DOT": "DOT",
    "BCH": "BCH",
    "ATOM": "ATOM",
    "AVAX": "AVAX",
    "AAVE": "AAVE",
    "ZEUR": "EUR",
    "EUR": "EUR",
}

# Central AUTOBOT research universe fallback. Runtime-configured TRADING_PAIRS
# still takes precedence when present.
AUTOBOT_DEFAULT_ACTIVE_SYMBOLS = (
    "BTCZEUR",
    "ETHZEUR",
    "SOLEUR",
    "LTCZEUR",
    "XLMZEUR",
    "XRPZEUR",
    "TRXEUR",
    "ADAEUR",
    "LINKEUR",
    "DOTEUR",
    "BCHEUR",
    "ATOMEUR",
    "AVAXEUR",
    "AAVEEUR",
)


AssetPairsFetcher = Callable[[], Mapping[str, Mapping[str, Any]]]


@dataclass(frozen=True)
class KrakenPublicPairMapping:
    autobot_symbol: str
    kraken_ohlcv_symbol: str
    runtime_symbol: str
    aliases: tuple[str, ...]
    altname: str | None = None
    wsname: str | None = None
    base_asset: str | None = None
    quote_asset: str | None = None
    market_mapping_status: str = "MAPPING_UNVERIFIED"

    def explicit_market_mapping(self) -> dict[str, str] | None:
        """Return the exchange-declared base/quote mapping, never a guess."""

        if self.market_mapping_status != "EXPLICIT" or not self.base_asset or not self.quote_asset:
            return None
        return {"base_asset": self.base_asset, "quote_asset": self.quote_asset}

    def to_dict(self) -> dict[str, Any]:
        return {
            "autobot_symbol": self.autobot_symbol,
            "kraken_ohlcv_symbol": self.kraken_ohlcv_symbol,
            "runtime_symbol": self.runtime_symbol,
            "aliases": list(self.aliases),
            "altname": self.altname,
            "wsname": self.wsname,
            "base_asset": self.base_asset,
            "quote_asset": self.quote_asset,
            "market_mapping_status": self.market_mapping_status,
        }


@dataclass(frozen=True)
class KrakenPublicSymbolRegistry:
    mappings: Mapping[str, KrakenPublicPairMapping]
    alias_to_symbol: Mapping[str, str]
    source: str = "kraken_public_asset_pairs"

    def resolve(self, symbol: str | None) -> KrakenPublicPairMapping | None:
        for candidate in _symbol_candidates(symbol):
            canonical = self.alias_to_symbol.get(candidate)
            if canonical:
                return self.mappings.get(canonical)
        return None

    def explicit_market_mappings(self) -> dict[str, dict[str, str]]:
        """Build canonical mappings suitable for point-in-time OHLCV storage.

        Only mappings declared by Kraken's public AssetPairs response are
        returned.  A missing asset alias is a data-quality condition, not an
        invitation to infer a quote currency from a compact symbol.
        """

        result: dict[str, dict[str, str]] = {}
        for symbol, mapping in self.mappings.items():
            explicit = mapping.explicit_market_mapping()
            if explicit is not None:
                result[symbol] = explicit
        return result


@dataclass(frozen=True)
class KrakenSymbolPreflight:
    requested_symbols: tuple[str, ...]
    resolved_symbols: tuple[str, ...]
    mappings: tuple[KrakenPublicPairMapping, ...]
    source: str = "kraken_public_asset_pairs"

    def mapping_by_symbol(self) -> dict[str, KrakenPublicPairMapping]:
        return {item.autobot_symbol: item for item in self.mappings}

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested_symbols": list(self.requested_symbols),
            "resolved_symbols": list(self.resolved_symbols),
            "mappings": [item.to_dict() for item in self.mappings],
            "source": self.source,
        }


def detect_active_autobot_symbols(
    *,
    env: Mapping[str, str] | None = None,
    extra_symbols: Sequence[str] = (),
    fallback_to_default_universe: bool = True,
) -> tuple[str, ...]:
    """Return the current AUTOBOT active-symbol set for research workflows.

    Order of precedence:
    1. runtime ``TRADING_PAIRS`` when configured;
    2. runtime ``TRADING_SYMBOL`` fallback;
    3. optional ``extra_symbols`` supplied by the caller;
    4. central AUTOBOT default active universe when requested.
    """

    env_values = env or os.environ
    discovered: list[str] = []
    pairs_text = str(env_values.get("TRADING_PAIRS") or "").strip()
    if pairs_text:
        discovered.extend(item.strip() for item in pairs_text.split(",") if item.strip())
    else:
        single = str(env_values.get("TRADING_SYMBOL") or "").strip()
        if single:
            discovered.append(single)
    discovered.extend(extra_symbols)
    if not discovered and fallback_to_default_universe:
        discovered.extend(AUTOBOT_DEFAULT_ACTIVE_SYMBOLS)
    return _dedupe_preserve_order(normalize_research_symbol(item) for item in discovered)


@lru_cache(maxsize=1)
def fetch_kraken_public_asset_pairs() -> dict[str, Mapping[str, Any]]:
    """Fetch public Kraken asset pairs from the official REST API."""

    with urllib.request.urlopen(KRAKEN_PUBLIC_ASSET_PAIRS_URL, timeout=20) as response:  # nosec B310 - public fixed HTTPS endpoint.
        payload = json.loads(response.read().decode("utf-8"))
    errors = payload.get("error") or []
    if errors:
        raise ValueError(f"Kraken AssetPairs error: {errors}")
    result = payload.get("result")
    if not isinstance(result, Mapping):
        raise ValueError("Kraken AssetPairs payload is missing a result mapping")
    return {str(key): value for key, value in result.items() if isinstance(value, Mapping)}


def build_kraken_public_symbol_registry(
    *,
    asset_pairs: Mapping[str, Mapping[str, Any]] | None = None,
    asset_pairs_fetcher: AssetPairsFetcher | None = None,
) -> KrakenPublicSymbolRegistry:
    pairs = asset_pairs or (asset_pairs_fetcher or fetch_kraken_public_asset_pairs)()
    chosen: dict[str, KrakenPublicPairMapping] = {}
    ranks: dict[str, tuple[int, str]] = {}

    for pair_key, metadata in pairs.items():
        pair_name = str(pair_key).strip().upper()
        altname = _optional_text(metadata.get("altname"))
        wsname = _optional_text(metadata.get("wsname"))
        canonical = normalize_research_symbol(wsname or altname or pair_name)
        if not canonical:
            continue
        aliases = _pair_aliases(canonical, pair_name=pair_name, altname=altname, wsname=wsname)
        base_asset = _canonical_kraken_asset(metadata.get("base"))
        quote_asset = _canonical_kraken_asset(metadata.get("quote"))
        mapping_status = "EXPLICIT" if base_asset and quote_asset else "MAPPING_UNVERIFIED"
        mapping = KrakenPublicPairMapping(
            autobot_symbol=canonical,
            kraken_ohlcv_symbol=pair_name,
            runtime_symbol=pair_name,
            aliases=aliases,
            altname=altname,
            wsname=wsname,
            base_asset=base_asset,
            quote_asset=quote_asset,
            market_mapping_status=mapping_status,
        )
        rank = _pair_rank(pair_name, altname=altname, wsname=wsname)
        current_rank = ranks.get(canonical)
        if current_rank is None or rank < current_rank:
            chosen[canonical] = mapping
            ranks[canonical] = rank

    alias_to_symbol: dict[str, str] = {}
    for canonical, mapping in chosen.items():
        alias_to_symbol[canonical] = canonical
        for alias in mapping.aliases:
            alias_to_symbol[alias] = canonical
    return KrakenPublicSymbolRegistry(mappings=chosen, alias_to_symbol=alias_to_symbol)


def preflight_kraken_public_symbols(
    symbols: Sequence[str],
    *,
    asset_pairs: Mapping[str, Mapping[str, Any]] | None = None,
    asset_pairs_fetcher: AssetPairsFetcher | None = None,
) -> KrakenSymbolPreflight:
    registry = build_kraken_public_symbol_registry(
        asset_pairs=asset_pairs,
        asset_pairs_fetcher=asset_pairs_fetcher,
    )
    resolved: list[KrakenPublicPairMapping] = []
    requested = _dedupe_preserve_order(normalize_research_symbol(symbol) for symbol in symbols)
    missing: list[str] = []
    for symbol in requested:
        mapping = registry.resolve(symbol)
        if mapping is None:
            missing.append(symbol)
            continue
        if mapping.autobot_symbol not in {item.autobot_symbol for item in resolved}:
            resolved.append(mapping)
    if missing:
        raise ValueError(
            "Kraken public symbol mapping missing for active symbols: "
            f"{', '.join(missing)}. Update the AUTOBOT/Kraken symbol mapping before running research collection."
        )
    return KrakenSymbolPreflight(
        requested_symbols=requested,
        resolved_symbols=tuple(item.autobot_symbol for item in resolved),
        mappings=tuple(resolved),
    )


def resolve_kraken_public_pair(
    symbol: str,
    *,
    asset_pairs: Mapping[str, Mapping[str, Any]] | None = None,
    asset_pairs_fetcher: AssetPairsFetcher | None = None,
) -> KrakenPublicPairMapping:
    preflight = preflight_kraken_public_symbols(
        (symbol,),
        asset_pairs=asset_pairs,
        asset_pairs_fetcher=asset_pairs_fetcher,
    )
    return preflight.mappings[0]


def _pair_aliases(
    canonical: str,
    *,
    pair_name: str,
    altname: str | None,
    wsname: str | None,
) -> tuple[str, ...]:
    aliases = set(expand_research_symbol_aliases((canonical,)))
    aliases.update(_symbol_candidates(canonical))
    aliases.update(_symbol_candidates(pair_name))
    aliases.update(_symbol_candidates(altname))
    aliases.update(_symbol_candidates(wsname))
    return tuple(sorted(alias for alias in aliases if alias))


def _pair_rank(pair_name: str, *, altname: str | None, wsname: str | None) -> tuple[int, str]:
    penalty = 0
    if "." in pair_name:
        penalty += 100
    if not wsname:
        penalty += 5
    if not altname:
        penalty += 2
    return (penalty, pair_name)


def _symbol_candidates(symbol: str | None) -> tuple[str, ...]:
    raw = str(symbol or "").strip().upper()
    if not raw:
        return ()
    compact = raw.replace("/", "").replace("-", "").replace("_", "")
    normalized = normalize_research_symbol(raw)
    candidates = [raw, compact, normalized]
    if normalized:
        candidates.extend(expand_research_symbol_aliases((normalized,)))
        if normalized.endswith("ZEUR"):
            candidates.append(normalized.replace("ZEUR", "EUR"))
    return _dedupe_preserve_order(candidate for candidate in candidates if candidate)


def _dedupe_preserve_order(values: Sequence[str] | Any) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return tuple(ordered)


def _optional_text(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _canonical_kraken_asset(value: Any) -> str | None:
    """Normalize only documented Kraken asset aliases from AssetPairs."""

    raw = _optional_text(value)
    if raw is None:
        return None
    return KRAKEN_EXPLICIT_ASSET_ALIASES.get(raw.upper())
