import math

import pytest

from autobot.v2.opportunity_scoring import OpportunityConfig, OpportunityScorer
from autobot.v2.regime_features import RegimeFeatureConfig, RegimeFeatureEngine


pytestmark = pytest.mark.unit


def _prices_from_returns(start: float, returns_bps: list[float]) -> list[float]:
    prices = [start]
    price = start
    for ret in returns_bps:
        price *= math.exp(ret / 10000.0)
        prices.append(price)
    return prices


def _engine() -> RegimeFeatureEngine:
    return RegimeFeatureEngine(
        RegimeFeatureConfig(
            entropy_window=32,
            markov_window=48,
            min_samples=8,
            score_weight=8.0,
            flat_return_bps=3.0,
            volatile_return_bps=30.0,
        )
    )


def test_entropy_is_low_on_stable_price_series():
    engine = _engine()
    result = engine.analyze_symbol("ETHEUR", [100.0] * 40)

    assert result.entropy_norm == 0.0
    assert result.regime in {"low_activity", "range"}
    assert result.adjustment <= 0.0


def test_entropy_is_high_on_chaotic_state_series():
    engine = _engine()
    returns = [35.0, -6.0, 1.0, 8.0, -36.0, 6.0, -1.0, -8.0] * 8
    result = engine.analyze_symbol("BTCEUR", _prices_from_returns(100.0, returns))

    assert result.entropy_norm >= engine.config.high_entropy_threshold
    assert result.regime == "chaos"
    assert result.adjustment < 0.0


def test_markov_transition_matrix_matches_known_sequence():
    engine = _engine()
    matrix = engine._transition_matrix(["UP", "UP", "DOWN", "FLAT", "UP", "DOWN"])

    assert matrix["UP"]["UP"] == pytest.approx(1 / 3)
    assert matrix["UP"]["DOWN"] == pytest.approx(2 / 3)
    assert matrix["DOWN"]["FLAT"] == 1.0
    assert matrix["FLAT"]["UP"] == 1.0


def test_insufficient_history_returns_unknown_without_penalty():
    engine = _engine()
    result = engine.analyze_symbol("SOLEUR", [100.0, 100.4])

    assert result.regime == "unknown"
    assert result.regime_score == 50.0
    assert result.adjustment == 0.0


def test_range_regime_improves_score_without_new_blocker():
    engine = _engine()
    scorer = OpportunityScorer(
        OpportunityConfig(min_score=0.0, min_gross_edge_bps=35.0, min_net_edge_bps=12.0),
        regime_engine=engine,
    )
    returns = ([2.0] * 5 + [8.0, -8.0]) * 8

    result = scorer.score_signal(
        symbol="ETHEUR",
        edge_context={
            "expected_move_bps": 70.0,
            "total_cost_bps": 18.0,
            "net_edge_bps": 52.0,
            "adaptive_min_edge_bps": 12.0,
            "spread_bps": 1.0,
        },
        atr_pct=0.002,
        available_capital=500.0,
        paper_mode=True,
        price_history=_prices_from_returns(100.0, returns),
    )

    assert result.regime_context["regime"] == "range"
    assert result.regime_adjustment > 0.0
    assert result.score > result.base_score
    assert not any(blocker.startswith("regime_") for blocker in result.blockers)


def test_chaos_regime_reduces_score_without_new_blocker():
    engine = _engine()
    scorer = OpportunityScorer(
        OpportunityConfig(min_score=0.0, min_gross_edge_bps=35.0, min_net_edge_bps=12.0),
        regime_engine=engine,
    )
    returns = [35.0, -6.0, 1.0, 8.0, -36.0, 6.0, -1.0, -8.0] * 8

    result = scorer.score_signal(
        symbol="BTCEUR",
        edge_context={
            "expected_move_bps": 70.0,
            "total_cost_bps": 18.0,
            "net_edge_bps": 52.0,
            "adaptive_min_edge_bps": 12.0,
            "spread_bps": 1.0,
        },
        atr_pct=0.002,
        available_capital=500.0,
        paper_mode=True,
        price_history=_prices_from_returns(100.0, returns),
    )

    assert result.regime_context["regime"] == "chaos"
    assert result.regime_adjustment < 0.0
    assert result.score < result.base_score
    assert not any(blocker.startswith("regime_") for blocker in result.blockers)
