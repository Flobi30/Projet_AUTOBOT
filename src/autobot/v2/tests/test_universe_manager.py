from autobot.v2.markets import get_market_config, MarketType
from autobot.v2.universe_manager import UniverseManager


def test_universe_manager_initialization_caps_and_forex_filter():
    manager = UniverseManager(max_supported=4, max_eligible=2, enable_forex=False)
    manager.initialize(preferred_symbols=["EUR/USD", "BTC/EUR", "ETH/EUR", "SOL/EUR"])

    supported = manager.get_supported_universe()
    eligible = manager.get_eligible_universe()

    assert len(supported) == 4
    assert len(eligible) == 2
    assert "EUR/USD" not in supported


def test_universe_manager_tracks_ranked_websocket_and_traded_states():
    manager = UniverseManager(max_supported=5, max_eligible=3, enable_forex=True)
    manager.initialize(preferred_symbols=["BTC/EUR", "ETH/EUR", "SOL/EUR", "EUR/USD", "GBP/USD"])

    manager.set_eligible_universe(["BTC/EUR", "ETH/EUR", "EUR/USD"])
    manager.update_ranked_universe(["ETH/EUR", "EUR/USD", "BTC/EUR", "SOL/EUR"])
    manager.update_scored_universe({"ETH/EUR": {"score": 80.0}, "SOL/EUR": {"score": 90.0}})
    manager.mark_websocket_active(["ETH/EUR", "SOL/EUR"])  # SOL should be ignored (not eligible)
    manager.mark_actively_traded(["BTC/EUR", "EUR/USD", "XRP/EUR"])  # XRP ignored

    snap = manager.snapshot()

    assert snap.ranked == ("ETH/EUR", "EUR/USD", "BTC/EUR")
    assert snap.scored == {"ETH/EUR": {"score": 80.0}}
    assert snap.websocket_active == frozenset({"ETH/EUR"})
    assert snap.actively_traded == frozenset({"BTC/EUR", "EUR/USD"})
    assert get_market_config("EUR/USD").market_type == MarketType.FOREX
