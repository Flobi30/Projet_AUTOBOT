from dataclasses import dataclass

from autobot.v2.pair_ranking_engine import PairRankingEngine
from autobot.v2.universe_manager import UniverseManager


@dataclass
class _Metrics:
    composite_score: float
    trend_strength: float
    volume_24h: float
    spread_avg: float
    volatility_24h: float
    volatility_7d: float


class _Analyzer:
    def __init__(self, mapping):
        self.mapping = mapping
        self.calls = 0

    def analyze_market(self, symbol):
        self.calls += 1
        return self.mapping.get(symbol)


def test_pair_ranking_engine_deterministic_scoring_and_order():
    manager = UniverseManager(max_supported=5, max_eligible=3, enable_forex=True)
    manager.initialize(preferred_symbols=["BTC/EUR", "ETH/EUR", "SOL/EUR"])
    manager.set_eligible_universe(["BTC/EUR", "ETH/EUR", "SOL/EUR"])

    analyzer = _Analyzer(
        {
            "BTC/EUR": _Metrics(70, 0.5, 120, 0.02, 2.0, 2.2),
            "ETH/EUR": _Metrics(70, 0.6, 80, 0.20, 2.0, 5.0),
            "SOL/EUR": _Metrics(65, 0.8, 140, 0.03, 2.1, 2.0),
        }
    )
    engine = PairRankingEngine(manager, analyzer=analyzer, update_seconds=300, min_score_activate=50)

    ranked = engine.refresh(now_ts=1000.0)

    assert [p.symbol for p in ranked] == ["BTC/EUR", "SOL/EUR", "ETH/EUR"]
    assert ranked[0].score > ranked[-1].score


def test_pair_ranking_engine_cost_and_degradation_penalties_and_explainability():
    manager = UniverseManager(max_supported=2, max_eligible=2, enable_forex=True)
    manager.initialize(preferred_symbols=["BTC/EUR", "ETH/EUR"])
    manager.set_eligible_universe(["BTC/EUR", "ETH/EUR"])

    analyzer = _Analyzer(
        {
            "BTC/EUR": _Metrics(70, 0.4, 100, 0.02, 2.0, 2.0),
            "ETH/EUR": _Metrics(70, 0.4, 100, 0.30, 1.0, 7.0),
        }
    )
    engine = PairRankingEngine(manager, analyzer=analyzer, update_seconds=300, min_score_activate=60)

    ranked = engine.refresh(now_ts=2000.0)
    by_symbol = {p.symbol: p for p in ranked}

    assert by_symbol["BTC/EUR"].score > by_symbol["ETH/EUR"].score
    explain = by_symbol["ETH/EUR"].explain
    assert set(explain.keys()) == {
        "base_composite",
        "trend_bonus",
        "liquidity_bonus",
        "spread_penalty",
        "degradation_penalty",
        "formula",
    }
    assert explain["formula"] == "base+trend+liquidity-spread-degradation"


def test_pair_ranking_engine_cached_refresh_cadence():
    manager = UniverseManager(max_supported=2, max_eligible=2, enable_forex=True)
    manager.initialize(preferred_symbols=["BTC/EUR", "ETH/EUR"])
    manager.set_eligible_universe(["BTC/EUR", "ETH/EUR"])

    analyzer = _Analyzer(
        {
            "BTC/EUR": _Metrics(70, 0.5, 100, 0.02, 2.0, 2.1),
            "ETH/EUR": _Metrics(69, 0.4, 90, 0.03, 2.2, 2.3),
        }
    )
    engine = PairRankingEngine(manager, analyzer=analyzer, update_seconds=60, min_score_activate=50)

    engine.refresh_if_due(now_ts=100.0)
    first_calls = analyzer.calls
    engine.refresh_if_due(now_ts=120.0)
    second_calls = analyzer.calls
    engine.refresh_if_due(now_ts=161.0)

    assert first_calls == 2
    assert second_calls == 2  # cached, no recompute before cadence
    assert analyzer.calls == 4  # recomputed after cadence
