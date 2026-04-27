"""Tests pour StrategyEnsemble."""

from __future__ import annotations

import sys

import pytest

pytestmark = pytest.mark.unit

sys.path.insert(0, "/home/node/.openclaw/workspace/src")

from autobot.v2.strategy_ensemble import MarketRegime, StrategyEnsemble


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def ensemble() -> StrategyEnsemble:
    """Instance fraiche de StrategyEnsemble."""
    return StrategyEnsemble()


# ---------------------------------------------------------------------------
# 1. Pondérations par régime
# ---------------------------------------------------------------------------


def test_get_weights_range_returns_expected(ensemble: StrategyEnsemble) -> None:
    """RANGE : grid=0.70, trend=0.00, mean_reversion=0.30."""
    weights = ensemble.get_weights(MarketRegime.RANGE)
    assert weights == {"grid": 0.70, "trend": 0.00, "mean_reversion": 0.30}


def test_get_weights_trend_forte_returns_expected(ensemble: StrategyEnsemble) -> None:
    """TREND_FORTE : grid=0.20, trend=0.80, mean_reversion=0.00."""
    weights = ensemble.get_weights(MarketRegime.TREND_FORTE)
    assert weights == {"grid": 0.20, "trend": 0.80, "mean_reversion": 0.00}


# ---------------------------------------------------------------------------
# 3. Signal BUY unique depuis grid en régime RANGE
# ---------------------------------------------------------------------------


def test_get_signal_single_buy_grid_range_returns_buy(
    ensemble: StrategyEnsemble,
) -> None:
    """Un seul signal BUY de grid en RANGE donne direction=BUY avec score=0.70*score_i."""
    signal_score = 0.9
    ensemble.update_signal("grid", "BUY", signal_score)

    result = ensemble.get_signal(MarketRegime.RANGE)

    assert result.direction == "BUY"
    # buy_score = 0.70 * 0.9 = 0.63
    assert result.score == pytest.approx(0.70 * signal_score, rel=1e-6)


# ---------------------------------------------------------------------------
# 4. Signaux conflictuels — sell_score > buy_score → SELL
# ---------------------------------------------------------------------------


def test_get_signal_conflicting_signals_sell_wins(ensemble: StrategyEnsemble) -> None:
    """Si sell_score > buy_score, direction=SELL."""
    # TREND_FORTE : trend pèse 0.80
    ensemble.update_signal("trend", "SELL", 1.0)  # sell_score = 0.80
    ensemble.update_signal("grid", "BUY", 1.0)  # buy_score = 0.20

    result = ensemble.get_signal(MarketRegime.TREND_FORTE)

    assert result.direction == "SELL"
    assert result.score == pytest.approx(0.80, rel=1e-6)


# ---------------------------------------------------------------------------
# 5. Scores trop faibles → HOLD
# ---------------------------------------------------------------------------


def test_get_signal_low_scores_returns_hold(ensemble: StrategyEnsemble) -> None:
    """Des scores en dessous du seuil produisent HOLD."""
    ensemble.update_signal("grid", "BUY", 0.1)
    # 0.70 * 0.1 = 0.07 < SIGNAL_THRESHOLD (0.3)

    result = ensemble.get_signal(MarketRegime.RANGE)

    assert result.direction == "HOLD"


# ---------------------------------------------------------------------------
# 6. update_signal avec stratégie invalide lève ValueError
# ---------------------------------------------------------------------------


def test_update_signal_invalid_strategy_raises_value_error(
    ensemble: StrategyEnsemble,
) -> None:
    """Une stratégie inconnue doit lever ValueError."""
    with pytest.raises(ValueError, match="Stratégie inconnue"):
        ensemble.update_signal("unknown_strat", "BUY", 0.5)


def test_update_signal_invalid_direction_raises_value_error(
    ensemble: StrategyEnsemble,
) -> None:
    """Une direction invalide doit lever ValueError."""
    with pytest.raises(ValueError, match="Direction invalide"):
        ensemble.update_signal("grid", "MAYBE", 0.5)


def test_update_signal_invalid_score_raises_value_error(
    ensemble: StrategyEnsemble,
) -> None:
    """Un score hors [0,1] doit lever ValueError."""
    with pytest.raises(ValueError, match="score"):
        ensemble.update_signal("grid", "BUY", 1.5)


# ---------------------------------------------------------------------------
# 7. get_status retourne call_count croissant
# ---------------------------------------------------------------------------


def test_get_status_call_count_increments(ensemble: StrategyEnsemble) -> None:
    """call_count doit s'incrémenter à chaque appel à get_signal."""
    assert ensemble.get_status()["call_count"] == 0

    ensemble.get_signal(MarketRegime.RANGE)
    assert ensemble.get_status()["call_count"] == 1

    ensemble.get_signal(MarketRegime.TREND_FORTE)
    assert ensemble.get_status()["call_count"] == 2


def test_get_status_contains_last_signals(ensemble: StrategyEnsemble) -> None:
    """get_status doit exposer les derniers signaux enregistrés."""
    ensemble.update_signal("grid", "BUY", 0.8)

    status = ensemble.get_status()

    assert "last_signals" in status
    assert "grid" in status["last_signals"]  # type: ignore[operator]
    assert status["last_signals"]["grid"]["direction"] == "BUY"  # type: ignore[index]
