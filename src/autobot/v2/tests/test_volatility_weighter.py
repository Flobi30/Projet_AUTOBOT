"""Tests pour VolatilityWeighter."""

from __future__ import annotations

import sys
import os


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.volatility_weighter import VolatilityWeighter
import pytest
pytestmark = pytest.mark.unit



@pytest.fixture
def weighter() -> VolatilityWeighter:
    """Instance VolatilityWeighter fraiche."""
    return VolatilityWeighter()


def test_calculate_weights_two_pairs_inverse_atr(weighter: VolatilityWeighter) -> None:
    """BTC ATR=200, ETH ATR=100 => BTC=1/3, ETH=2/3."""
    # inv(200) = 0.005, inv(100) = 0.010, sum = 0.015
    # BTC = 0.005/0.015 = 1/3, ETH = 0.010/0.015 = 2/3
    atr = {"BTC/USD": 200.0, "ETH/USD": 100.0}
    weights = weighter.calculate_weights(atr)

    assert weights["BTC/USD"] == pytest.approx(1 / 3, rel=1e-6)
    assert weights["ETH/USD"] == pytest.approx(2 / 3, rel=1e-6)


def test_calculate_weights_three_equal_atrs(weighter: VolatilityWeighter) -> None:
    """Trois paires avec ATR identiques => poids egaux (~0.333 chacun)."""
    atr = {"A": 150.0, "B": 150.0, "C": 150.0}
    weights = weighter.calculate_weights(atr)

    for symbol in atr:
        assert weights[symbol] == pytest.approx(1 / 3, rel=1e-6)


def test_calculate_weights_one_zero_atr_excluded(weighter: VolatilityWeighter) -> None:
    """La paire avec ATR=0 est exclue, les autres sont renormalisees."""
    atr = {"BTC/USD": 200.0, "ETH/USD": 100.0, "DOGE/USD": 0.0}
    weights = weighter.calculate_weights(atr)

    assert weights["DOGE/USD"] == 0.0
    assert weights["BTC/USD"] == pytest.approx(1 / 3, rel=1e-6)
    assert weights["ETH/USD"] == pytest.approx(2 / 3, rel=1e-6)
    assert sum(weights.values()) == pytest.approx(1.0, rel=1e-6)


def test_calculate_weights_all_zero_atr_equal_weights(
    weighter: VolatilityWeighter,
) -> None:
    """Toutes les ATR = 0 => poids egaux entre toutes les paires."""
    atr = {"X": 0.0, "Y": 0.0, "Z": 0.0}
    weights = weighter.calculate_weights(atr)

    for symbol in atr:
        assert weights[symbol] == pytest.approx(1 / 3, rel=1e-6)
    assert sum(weights.values()) == pytest.approx(1.0, rel=1e-6)


def test_calculate_weights_empty_raises_value_error(
    weighter: VolatilityWeighter,
) -> None:
    """Un dictionnaire vide leve ValueError."""
    with pytest.raises(ValueError, match="vide"):
        weighter.calculate_weights({})


def test_allocate_capital_distributes_correctly(
    weighter: VolatilityWeighter,
) -> None:
    """capital=10000, BTC ATR=200, ETH ATR=100 => BTC=3333.33, ETH=6666.67."""
    atr = {"BTC/USD": 200.0, "ETH/USD": 100.0}
    allocation = weighter.allocate_capital(10_000.0, atr)

    assert allocation["BTC/USD"] == pytest.approx(10_000 / 3, rel=1e-6)
    assert allocation["ETH/USD"] == pytest.approx(20_000 / 3, rel=1e-6)


def test_allocate_capital_invalid_capital_raises(
    weighter: VolatilityWeighter,
) -> None:
    """capital <= 0 leve ValueError."""
    atr = {"BTC/USD": 200.0}
    with pytest.raises(ValueError, match="> 0"):
        weighter.allocate_capital(0.0, atr)
    with pytest.raises(ValueError, match="> 0"):
        weighter.allocate_capital(-5000.0, atr)


def test_calculate_weights_sum_to_one(weighter: VolatilityWeighter) -> None:
    """Les poids somment toujours a 1.0, quelle que soit la configuration."""
    atr = {
        "BTC/USD": 300.0,
        "ETH/USD": 120.0,
        "SOL/USD": 45.0,
        "ADA/USD": 0.0,
    }
    weights = weighter.calculate_weights(atr)
    assert sum(weights.values()) == pytest.approx(1.0, rel=1e-6)


def test_get_status_returns_last_weights(weighter: VolatilityWeighter) -> None:
    """get_status retourne les derniers poids calcules."""
    assert weighter.get_status() == {}

    atr = {"BTC/USD": 200.0, "ETH/USD": 100.0}
    weights = weighter.calculate_weights(atr)
    status = weighter.get_status()

    assert status == pytest.approx(weights, rel=1e-6)


def test_allocate_capital_total_equals_input(weighter: VolatilityWeighter) -> None:
    """La somme des allocations egale le capital total."""
    atr = {"A": 100.0, "B": 200.0, "C": 300.0}
    total = 50_000.0
    allocation = weighter.allocate_capital(total, atr)
    assert sum(allocation.values()) == pytest.approx(total, rel=1e-6)
