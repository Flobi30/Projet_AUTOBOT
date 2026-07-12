import pytest

from autobot.v2.research.kraken_symbol_mapping import (
    AUTOBOT_DEFAULT_ACTIVE_SYMBOLS,
    build_kraken_public_symbol_registry,
    detect_active_autobot_symbols,
    preflight_kraken_public_symbols,
)


pytestmark = pytest.mark.unit


def _asset_pairs_fixture():
    return {
        "XXBTZEUR": {"altname": "XBTEUR", "wsname": "XBT/EUR", "base": "XXBT", "quote": "ZEUR"},
        "XETHZEUR": {"altname": "ETHEUR", "wsname": "ETH/EUR", "base": "XETH", "quote": "ZEUR"},
        "SOLEUR": {"altname": "SOLEUR", "wsname": "SOL/EUR", "base": "SOL", "quote": "ZEUR"},
        "XLTCZEUR": {"altname": "LTCEUR", "wsname": "LTC/EUR", "base": "XLTC", "quote": "ZEUR"},
        "XXLMZEUR": {"altname": "XLMEUR", "wsname": "XLM/EUR", "base": "XXLM", "quote": "ZEUR"},
        "XXRPZEUR": {"altname": "XRPEUR", "wsname": "XRP/EUR", "base": "XXRP", "quote": "ZEUR"},
        "TRXEUR": {"altname": "TRXEUR", "wsname": "TRX/EUR", "base": "TRX", "quote": "ZEUR"},
        "ADAEUR": {"altname": "ADAEUR", "wsname": "ADA/EUR", "base": "ADA", "quote": "ZEUR"},
        "LINKEUR": {"altname": "LINKEUR", "wsname": "LINK/EUR", "base": "LINK", "quote": "ZEUR"},
        "DOTEUR": {"altname": "DOTEUR", "wsname": "DOT/EUR", "base": "DOT", "quote": "ZEUR"},
        "BCHEUR": {"altname": "BCHEUR", "wsname": "BCH/EUR", "base": "BCH", "quote": "ZEUR"},
        "ATOMEUR": {"altname": "ATOMEUR", "wsname": "ATOM/EUR", "base": "ATOM", "quote": "ZEUR"},
        "AVAXEUR": {"altname": "AVAXEUR", "wsname": "AVAX/EUR", "base": "AVAX", "quote": "ZEUR"},
        "AAVEEUR": {"altname": "AAVEEUR", "wsname": "AAVE/EUR", "base": "AAVE", "quote": "ZEUR"},
    }


def test_detect_active_autobot_symbols_prefers_runtime_pairs(monkeypatch):
    monkeypatch.setenv("TRADING_PAIRS", "XXBTZEUR,XETHZEUR,ADAEUR")
    monkeypatch.delenv("TRADING_SYMBOL", raising=False)

    assert detect_active_autobot_symbols() == ("BTCZEUR", "ETHZEUR", "ADAEUR")


def test_detect_active_autobot_symbols_falls_back_to_default_universe(monkeypatch):
    monkeypatch.delenv("TRADING_PAIRS", raising=False)
    monkeypatch.delenv("TRADING_SYMBOL", raising=False)

    assert detect_active_autobot_symbols() == AUTOBOT_DEFAULT_ACTIVE_SYMBOLS


def test_build_registry_resolves_special_kraken_prefixed_pairs():
    registry = build_kraken_public_symbol_registry(asset_pairs=_asset_pairs_fixture())

    assert registry.resolve("BTCZEUR").kraken_ohlcv_symbol == "XXBTZEUR"
    assert registry.resolve("ETHZEUR").kraken_ohlcv_symbol == "XETHZEUR"
    assert registry.resolve("XLMZEUR").kraken_ohlcv_symbol == "XXLMZEUR"
    assert registry.resolve("XRPZEUR").kraken_ohlcv_symbol == "XXRPZEUR"
    assert registry.resolve("LTCZEUR").kraken_ohlcv_symbol == "XLTCZEUR"


def test_registry_exposes_only_explicit_exchange_market_mappings():
    registry = build_kraken_public_symbol_registry(asset_pairs=_asset_pairs_fixture())

    assert registry.resolve("BTCZEUR").explicit_market_mapping() == {"base_asset": "BTC", "quote_asset": "EUR"}
    assert registry.explicit_market_mappings()["ETHZEUR"] == {"base_asset": "ETH", "quote_asset": "EUR"}
    assert set(AUTOBOT_DEFAULT_ACTIVE_SYMBOLS).issubset(registry.explicit_market_mappings())

    unverified = build_kraken_public_symbol_registry(
        asset_pairs={"MYSTERY": {"altname": "MYSTERYEUR", "wsname": "MYSTERY/EUR", "base": "UNKNOWN", "quote": "ZEUR"}}
    ).resolve("MYSTERYEUR")
    assert unverified is not None
    assert unverified.explicit_market_mapping() is None
    assert unverified.market_mapping_status == "MAPPING_UNVERIFIED"


def test_preflight_passes_all_default_active_symbols():
    preflight = preflight_kraken_public_symbols(
        AUTOBOT_DEFAULT_ACTIVE_SYMBOLS,
        asset_pairs_fetcher=_asset_pairs_fixture,
    )

    assert preflight.resolved_symbols == AUTOBOT_DEFAULT_ACTIVE_SYMBOLS
    assert {item.autobot_symbol for item in preflight.mappings} == set(AUTOBOT_DEFAULT_ACTIVE_SYMBOLS)


def test_preflight_fails_fast_for_unknown_symbol():
    with pytest.raises(ValueError, match="Kraken public symbol mapping missing"):
        preflight_kraken_public_symbols(("TRXEUR", "BADPAIR"), asset_pairs_fetcher=_asset_pairs_fixture)
