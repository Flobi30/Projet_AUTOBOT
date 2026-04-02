"""Tests pour KellyCriterion.calculate_position_size_dynamic."""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.kelly_criterion import KellyCriterion
import pytest
import math


# Parametres nominaux : win_rate=0.60, avg_win=150, avg_loss=100
# f* = (0.60 * 1.5 - 0.40) / 1.5 = 0.3333
# Half-Kelly = 0.1667
# capital * 2% = 200.0 (capital=10000)
# => position = min(0.1667 * 10000, 200.0) = 200.0 (plafonnee a 2%)

CAPITAL = 10_000.0
WIN_RATE = 0.60
AVG_WIN = 150.0
AVG_LOSS = 100.0
PF_OK = 1.5


@pytest.fixture
def kelly() -> KellyCriterion:
    """Instance KellyCriterion avec cap standard."""
    return KellyCriterion(max_position_pct=0.25)


def test_calculate_position_size_dynamic_no_losses_capped_at_2pct(
    kelly: KellyCriterion,
) -> None:
    """Sans pertes consecutives, le resultat est plafonné a 2% du capital."""
    result = kelly.calculate_position_size_dynamic(
        WIN_RATE, AVG_WIN, AVG_LOSS, CAPITAL, PF_OK, consecutive_losses=0
    )
    assert result == pytest.approx(CAPITAL * 0.02, rel=1e-6)
    assert result <= CAPITAL * 0.02 + 1e-9


def test_calculate_position_size_dynamic_two_losses_no_decrement(
    kelly: KellyCriterion,
) -> None:
    """Avec 2 pertes consecutives, aucun decrement ne s'applique (seuil = 3)."""
    result_0 = kelly.calculate_position_size_dynamic(
        WIN_RATE, AVG_WIN, AVG_LOSS, CAPITAL, PF_OK, consecutive_losses=0
    )
    result_2 = kelly.calculate_position_size_dynamic(
        WIN_RATE, AVG_WIN, AVG_LOSS, CAPITAL, PF_OK, consecutive_losses=2
    )
    assert result_2 == pytest.approx(result_0, rel=1e-6)


def test_calculate_position_size_dynamic_three_losses_decrement_085(
    kelly: KellyCriterion,
) -> None:
    """Avec 3 pertes consecutives, le Kelly est multiplie par 0.85^1 = 0.85."""
    # Half-Kelly brut = 0.1667, apres decrement = 0.1667 * 0.85 = 0.14167
    # position = min(0.14167 * 10000, 200) = 141.67 (sous le plafond)
    f_star = (WIN_RATE * (AVG_WIN / AVG_LOSS) - (1 - WIN_RATE)) / (AVG_WIN / AVG_LOSS)
    half_kelly = f_star / 2.0
    expected = min(half_kelly * 0.85 * CAPITAL, CAPITAL * 0.02)

    result = kelly.calculate_position_size_dynamic(
        WIN_RATE, AVG_WIN, AVG_LOSS, CAPITAL, PF_OK, consecutive_losses=3
    )
    assert result == pytest.approx(expected, rel=1e-6)


def test_calculate_position_size_dynamic_five_losses_decrement_085_pow3(
    kelly: KellyCriterion,
) -> None:
    """Avec 5 pertes consecutives, le Kelly est multiplie par 0.85^3 = 0.614125."""
    f_star = (WIN_RATE * (AVG_WIN / AVG_LOSS) - (1 - WIN_RATE)) / (AVG_WIN / AVG_LOSS)
    half_kelly = f_star / 2.0
    factor = 0.85**3
    expected = min(half_kelly * factor * CAPITAL, CAPITAL * 0.02)

    result = kelly.calculate_position_size_dynamic(
        WIN_RATE, AVG_WIN, AVG_LOSS, CAPITAL, PF_OK, consecutive_losses=5
    )
    assert result == pytest.approx(expected, rel=1e-6)
    assert math.isclose(0.85**3, 0.614125, rel_tol=1e-5)


def test_calculate_position_size_dynamic_never_exceeds_2pct(
    kelly: KellyCriterion,
) -> None:
    """Le resultat ne depasse jamais 2% du capital, quelle que soit la configuration."""
    for losses in [0, 1, 2, 3, 5, 10]:
        result = kelly.calculate_position_size_dynamic(
            WIN_RATE, AVG_WIN, AVG_LOSS, CAPITAL, PF_OK, consecutive_losses=losses
        )
        assert result <= CAPITAL * 0.02 + 1e-9, (
            f"Position {result} depasse 2% du capital pour {losses} pertes"
        )


def test_calculate_position_size_dynamic_pf_below_one_returns_zero(
    kelly: KellyCriterion,
) -> None:
    """PF < 1.0 retourne 0.0."""
    result = kelly.calculate_position_size_dynamic(
        WIN_RATE, AVG_WIN, AVG_LOSS, CAPITAL, current_pf=0.9
    )
    assert result == 0.0


def test_calculate_position_size_dynamic_invalid_win_rate_returns_zero(
    kelly: KellyCriterion,
) -> None:
    """win_rate invalide retourne 0.0."""
    assert kelly.calculate_position_size_dynamic(0.0, AVG_WIN, AVG_LOSS, CAPITAL, PF_OK) == 0.0
    assert kelly.calculate_position_size_dynamic(1.0, AVG_WIN, AVG_LOSS, CAPITAL, PF_OK) == 0.0
    assert kelly.calculate_position_size_dynamic(-0.1, AVG_WIN, AVG_LOSS, CAPITAL, PF_OK) == 0.0


def test_calculate_position_size_dynamic_invalid_avg_win_returns_zero(
    kelly: KellyCriterion,
) -> None:
    """avg_win invalide retourne 0.0."""
    assert kelly.calculate_position_size_dynamic(WIN_RATE, 0.0, AVG_LOSS, CAPITAL, PF_OK) == 0.0
    assert kelly.calculate_position_size_dynamic(WIN_RATE, -50.0, AVG_LOSS, CAPITAL, PF_OK) == 0.0


def test_calculate_position_size_dynamic_invalid_capital_returns_zero(
    kelly: KellyCriterion,
) -> None:
    """Capital invalide retourne 0.0."""
    assert kelly.calculate_position_size_dynamic(WIN_RATE, AVG_WIN, AVG_LOSS, 0.0, PF_OK) == 0.0
    assert kelly.calculate_position_size_dynamic(WIN_RATE, AVG_WIN, AVG_LOSS, -100.0, PF_OK) == 0.0


def test_calculate_position_size_dynamic_negative_edge_returns_zero(
    kelly: KellyCriterion,
) -> None:
    """Edge Kelly negative retourne 0.0."""
    # win_rate=0.30, avg_win=100, avg_loss=100 => f* = -0.40
    result = kelly.calculate_position_size_dynamic(0.30, 100.0, 100.0, CAPITAL, PF_OK)
    assert result == 0.0


def test_calculate_position_size_dynamic_string_input_returns_zero(
    kelly: KellyCriterion,
) -> None:
    """Types non numeriques retournent 0.0."""
    result = kelly.calculate_position_size_dynamic(
        "0.6", AVG_WIN, AVG_LOSS, CAPITAL, PF_OK  # type: ignore[arg-type]
    )
    assert result == 0.0
