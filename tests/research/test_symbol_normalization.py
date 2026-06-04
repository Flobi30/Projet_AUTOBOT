import pytest

from autobot.v2.research.symbol_normalization import (
    expand_research_symbol_aliases,
    normalize_research_symbol,
)


pytestmark = pytest.mark.unit


def test_normalize_research_symbol_maps_kraken_aliases_to_compact_research_symbols():
    assert normalize_research_symbol("XXBTZEUR") == "BTCZEUR"
    assert normalize_research_symbol("XBT/EUR") == "BTCZEUR"
    assert normalize_research_symbol("BTC/EUR") == "BTCZEUR"
    assert normalize_research_symbol("XETHZEUR") == "ETHZEUR"
    assert normalize_research_symbol("XXLMZEUR") == "XLMZEUR"
    assert normalize_research_symbol("XXRPZEUR") == "XRPZEUR"
    assert normalize_research_symbol("XLTCZEUR") == "LTCZEUR"


def test_expand_research_symbol_aliases_includes_known_kraken_forms():
    aliases = set(expand_research_symbol_aliases(["BTCZEUR", "ETHZEUR"]))

    assert {"BTCZEUR", "BTCEUR", "XBT/EUR", "XBTZEUR", "XXBTZEUR"}.issubset(aliases)
    assert {"ETHZEUR", "ETHEUR", "ETH/EUR", "XETHZEUR"}.issubset(aliases)
