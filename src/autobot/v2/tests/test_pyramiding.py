"""Tests pour PyramidingManager."""

from __future__ import annotations

import sys

sys.path.insert(0, "/home/node/.openclaw/workspace/src")

import pytest

from autobot.v2.modules.pyramiding_manager import PyramidingManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def manager() -> PyramidingManager:
    """Instance fraiche de PyramidingManager avec paramètres par défaut."""
    return PyramidingManager(max_adds=3, profit_threshold_pct=2.0)


# ---------------------------------------------------------------------------
# 1. should_add retourne False avant open_position
# ---------------------------------------------------------------------------


def test_should_add_returns_false_before_open(manager: PyramidingManager) -> None:
    """should_add doit retourner False si aucune position n'est ouverte."""
    assert manager.should_add(105.0) is False


# ---------------------------------------------------------------------------
# 2. Après open à 100, au prix 100 (0 % profit) : should_add=False
# ---------------------------------------------------------------------------


def test_should_add_returns_false_at_entry_price(manager: PyramidingManager) -> None:
    """Aucun profit à l'entrée, should_add doit retourner False."""
    manager.open_position(entry_price=100.0, base_size=1.0)
    assert manager.should_add(100.0) is False


# ---------------------------------------------------------------------------
# 3. Au prix 102 (2 % profit) : should_add=True
# ---------------------------------------------------------------------------


def test_should_add_returns_true_at_threshold_profit(
    manager: PyramidingManager,
) -> None:
    """2 % de profit atteint le seuil, should_add doit retourner True."""
    manager.open_position(entry_price=100.0, base_size=1.0)
    assert manager.should_add(102.0) is True


# ---------------------------------------------------------------------------
# 4. add_to_position retourne size_multiplier=1.0 (niveau 0→1)
# ---------------------------------------------------------------------------


def test_add_to_position_first_add_returns_scale_1_0(
    manager: PyramidingManager,
) -> None:
    """Premier ajout : size_multiplier doit valoir 1.0 (SCALE_INCREMENTS[0])."""
    manager.open_position(entry_price=100.0, base_size=1.0)
    result = manager.add_to_position(102.0)

    assert result is not None
    assert result["size_multiplier"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 5. Après MAX_ADDS ajouts : should_add=False
# ---------------------------------------------------------------------------


def test_should_add_false_after_max_adds(manager: PyramidingManager) -> None:
    """should_add doit retourner False une fois le nombre max d'ajouts atteint."""
    manager.open_position(entry_price=100.0, base_size=1.0)
    current_price = 102.0

    for _ in range(PyramidingManager.MAX_ADDS):
        manager.add_to_position(current_price)
        current_price += 2.0  # on monte le prix pour rester au-dessus du seuil

    assert manager.should_add(current_price) is False


# ---------------------------------------------------------------------------
# 6. close_position réinitialise l'état : should_add=False
# ---------------------------------------------------------------------------


def test_close_position_resets_state(manager: PyramidingManager) -> None:
    """Après close_position, should_add doit retourner False."""
    manager.open_position(entry_price=100.0, base_size=1.0)
    manager.close_position()
    assert manager.should_add(110.0) is False

    status = manager.get_status()
    assert status["is_open"] is False
    assert status["current_level"] == 0
    assert status["entry_price"] is None


# ---------------------------------------------------------------------------
# 7. trailing_stop dans l'ajout = price * (1 - 1.0/100)
# ---------------------------------------------------------------------------


def test_add_to_position_trailing_stop_formula(manager: PyramidingManager) -> None:
    """Le trailing stop doit être price * (1 - TRAILING_STOP_PCT / 100)."""
    manager.open_position(entry_price=100.0, base_size=1.0)
    price = 102.0
    result = manager.add_to_position(price)

    assert result is not None
    expected_trailing_stop = price * (1.0 - PyramidingManager.TRAILING_STOP_PCT / 100.0)
    assert result["trailing_stop"] == pytest.approx(expected_trailing_stop, rel=1e-9)


# ---------------------------------------------------------------------------
# Cas limites supplémentaires
# ---------------------------------------------------------------------------


def test_add_to_position_returns_none_when_no_position(
    manager: PyramidingManager,
) -> None:
    """Sans position ouverte, add_to_position doit retourner None."""
    assert manager.add_to_position(105.0) is None


def test_open_position_invalid_entry_price_raises(manager: PyramidingManager) -> None:
    """entry_price <= 0 doit lever ValueError."""
    with pytest.raises(ValueError, match="entry_price"):
        manager.open_position(entry_price=0.0, base_size=1.0)


def test_init_invalid_max_adds_raises() -> None:
    """max_adds hors [1, 10] doit lever ValueError."""
    with pytest.raises(ValueError, match="max_adds"):
        PyramidingManager(max_adds=0)


def test_get_status_returns_all_keys(manager: PyramidingManager) -> None:
    """get_status doit contenir toutes les clés attendues."""
    manager.open_position(entry_price=50.0, base_size=2.0)
    status = manager.get_status()

    assert "current_level" in status
    assert "max_adds" in status
    assert "entry_price" in status
    assert "adds" in status
    assert "is_open" in status
    assert status["is_open"] is True
    assert status["entry_price"] == pytest.approx(50.0)
