import pytest

import importlib
from dataclasses import dataclass

from autobot.v2.market_analyzer import MarketQualityScore
from autobot.v2.markets import MarketType


pytestmark = pytest.mark.unit

@dataclass
class _Metric:
    symbol: str
    market_type: MarketType
    market_quality: MarketQualityScore
    composite_score: float
    recommended_strategy: str = "grid"
    recommended_allocation: float = 0.2
    volatility_24h: float = 1.0
    trend_strength: float = 0.5


class _DummyOrchestrator:
    def __init__(self):
        self._instances = {}


def _reload_selector(monkeypatch, *, enabled: bool, max_supported: int = 10, max_eligible: int = 5, enable_forex: bool = False, enable_pair_ranking: bool = False, ranking_min_score_activate: float = 55.0):
    monkeypatch.setenv("ENABLE_UNIVERSE_MANAGER", "true" if enabled else "false")
    monkeypatch.setenv("UNIVERSE_MAX_SUPPORTED", str(max_supported))
    monkeypatch.setenv("UNIVERSE_MAX_ELIGIBLE", str(max_eligible))
    monkeypatch.setenv("UNIVERSE_ENABLE_FOREX", "true" if enable_forex else "false")
    monkeypatch.setenv("ENABLE_PAIR_RANKING_ENGINE", "true" if enable_pair_ranking else "false")
    monkeypatch.setenv("RANKING_MIN_SCORE_ACTIVATE", str(ranking_min_score_activate))

    import autobot.v2.config as config
    import autobot.v2.market_selector as market_selector

    importlib.reload(config)
    return importlib.reload(market_selector)


def test_market_selector_flag_off_keeps_legacy_behavior(monkeypatch):
    market_selector = _reload_selector(monkeypatch, enabled=False)
    selector = market_selector.MarketSelector(_DummyOrchestrator())

    assert selector.use_universe_manager is False
    assert selector.universe_manager is None


def test_market_selector_flag_on_uses_universe_manager_and_eligible_filter(monkeypatch):
    market_selector = _reload_selector(
        monkeypatch,
        enabled=True,
        max_supported=4,
        max_eligible=1,
        enable_forex=False,
    )
    selector = market_selector.MarketSelector(_DummyOrchestrator())

    assert selector.use_universe_manager is True
    assert selector.universe_manager is not None
    assert len(selector.universe_manager.get_supported_universe()) <= 4
    selector.universe_manager.set_eligible_universe(["BTC/EUR"])

    markets = [
        _Metric("BTC/EUR", MarketType.CRYPTO, MarketQualityScore.GOOD, 80),
        _Metric("ETH/EUR", MarketType.CRYPTO, MarketQualityScore.GOOD, 90),
    ]
    candidates = selector._filter_candidates(markets, current_markets={})

    assert [m.symbol for m in candidates] == ["BTC/EUR"]


def test_market_selector_pair_ranking_flag_gated_fallback(monkeypatch):
    # Flag off => legacy composite ordering
    market_selector = _reload_selector(monkeypatch, enabled=True, enable_pair_ranking=False)
    selector = market_selector.MarketSelector(_DummyOrchestrator())
    selector.universe_manager.set_eligible_universe(["BTC/EUR", "ETH/EUR"])
    legacy_markets = [
        _Metric("BTC/EUR", MarketType.CRYPTO, MarketQualityScore.GOOD, 80),
        _Metric("ETH/EUR", MarketType.CRYPTO, MarketQualityScore.GOOD, 90),
    ]
    legacy = selector._filter_candidates(legacy_markets, current_markets={})
    assert [m.symbol for m in legacy] == ["ETH/EUR", "BTC/EUR"]

    # Flag on => uses ranked+scored universe from manager
    market_selector = _reload_selector(
        monkeypatch,
        enabled=True,
        enable_pair_ranking=True,
        ranking_min_score_activate=60,
    )
    selector = market_selector.MarketSelector(_DummyOrchestrator())
    selector.universe_manager.set_eligible_universe(["BTC/EUR", "ETH/EUR"])
    selector.universe_manager.update_ranked_universe(["BTC/EUR", "ETH/EUR"])
    selector.universe_manager.update_scored_universe({
        "BTC/EUR": {"score": 75.0},
        "ETH/EUR": {"score": 50.0},
    })
    ranked_markets = [
        _Metric("BTC/EUR", MarketType.CRYPTO, MarketQualityScore.GOOD, 70),
        _Metric("ETH/EUR", MarketType.CRYPTO, MarketQualityScore.GOOD, 99),
    ]
    ranked = selector._filter_candidates(ranked_markets, current_markets={})
    assert [m.symbol for m in ranked] == ["BTC/EUR"]
