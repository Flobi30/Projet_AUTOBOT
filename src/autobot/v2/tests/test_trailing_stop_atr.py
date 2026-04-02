"""
Tests unitaires pour le module TrailingStopATR.

Couvre :
1. SL initial avant activation du trailing
2. Trailing NON activé si profit < activation_profit * atr
3. Trailing ACTIVÉ si profit >= activation_profit * atr
4. Une fois actif, stop ne descend jamais (trailing à la hausse uniquement)
5. reset() efface l'état
6. Entrées invalides lèvent ValueError
7. get_status() retourne le dictionnaire correct

À exécuter avec : python3 -m pytest test_trailing_stop_atr.py -v
"""

from __future__ import annotations

import sys
import os
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from modules.trailing_stop_atr import TrailingStopATR

import pytest


# ---------------------------------------------------------------------------
# Constantes de test
# ---------------------------------------------------------------------------

ENTRY = 50_000.0
ATR = 200.0
MULTIPLIER = 2.5
ACTIVATION = 1.5

# SL initial attendu = entry - multiplier * atr = 50_000 - 500 = 49_500
INITIAL_SL = ENTRY - MULTIPLIER * ATR

# Seuil d'activation = entry + activation * atr = 50_000 + 300 = 50_300
ACTIVATION_THRESHOLD = ENTRY + ACTIVATION * ATR


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_ts(**kwargs: float) -> TrailingStopATR:
    """Instancie un TrailingStopATR avec des valeurs par défaut."""
    defaults: dict[str, float] = {
        "atr_multiplier": MULTIPLIER,
        "activation_profit": ACTIVATION,
    }
    defaults.update(kwargs)
    return TrailingStopATR(**defaults)


# ---------------------------------------------------------------------------
# 1. SL initial avant activation du trailing
# ---------------------------------------------------------------------------


class TestInitialStopLoss:
    def test_initial_sl_equals_entry_minus_multiplier_times_atr(self) -> None:
        """SL initial = entry_price - (atr_multiplier * atr)."""
        ts = make_ts()
        stop = ts.update(price=ENTRY, atr=ATR, entry_price=ENTRY)
        assert stop == pytest.approx(INITIAL_SL)

    def test_initial_sl_returned_before_activation(self) -> None:
        """Chaque appel avant activation retourne le SL initial recalculé."""
        ts = make_ts()
        # Prix en-dessous du seuil d'activation
        price_below = ACTIVATION_THRESHOLD - 1
        stop = ts.update(price=price_below, atr=ATR, entry_price=ENTRY)
        expected = ENTRY - MULTIPLIER * ATR
        assert stop == pytest.approx(expected)

    def test_initial_sl_uses_current_atr(self) -> None:
        """Le SL initial s'adapte si l'ATR change entre deux appels."""
        ts = make_ts()
        atr_small = 100.0
        stop = ts.update(price=ENTRY, atr=atr_small, entry_price=ENTRY)
        assert stop == pytest.approx(ENTRY - MULTIPLIER * atr_small)

    def test_update_returns_float_not_none(self) -> None:
        """update() retourne toujours un float, jamais None."""
        ts = make_ts()
        result = ts.update(price=ENTRY, atr=ATR, entry_price=ENTRY)
        assert isinstance(result, float)


# ---------------------------------------------------------------------------
# 2. Trailing NON activé si profit insuffisant
# ---------------------------------------------------------------------------


class TestTrailingNotActivated:
    def test_trailing_inactive_when_profit_below_threshold(self) -> None:
        """Trailing non activé si price < entry + activation_profit * atr."""
        ts = make_ts()
        price_below = ACTIVATION_THRESHOLD - 0.01
        ts.update(price=price_below, atr=ATR, entry_price=ENTRY)
        assert not ts.get_status()["trailing_active"]

    def test_trailing_inactive_at_entry_price(self) -> None:
        """Trailing non activé quand le prix est exactement au prix d'entrée."""
        ts = make_ts()
        ts.update(price=ENTRY, atr=ATR, entry_price=ENTRY)
        assert not ts.get_status()["trailing_active"]

    def test_trailing_inactive_just_below_threshold(self) -> None:
        """Trailing non activé à 1 unité en-dessous du seuil."""
        ts = make_ts()
        ts.update(price=ACTIVATION_THRESHOLD - 1.0, atr=ATR, entry_price=ENTRY)
        assert not ts.get_status()["trailing_active"]

    def test_stop_is_initial_sl_when_inactive(self) -> None:
        """current_stop = SL initial si trailing non activé."""
        ts = make_ts()
        ts.update(price=ENTRY + 50, atr=ATR, entry_price=ENTRY)  # sous le seuil
        status = ts.get_status()
        assert not status["trailing_active"]
        assert status["current_stop"] == pytest.approx(INITIAL_SL)


# ---------------------------------------------------------------------------
# 3. Trailing ACTIVÉ quand profit >= activation_profit * atr
# ---------------------------------------------------------------------------


class TestTrailingActivation:
    def test_trailing_activates_at_threshold(self) -> None:
        """Trailing activé quand price == activation_threshold."""
        ts = make_ts()
        ts.update(price=ACTIVATION_THRESHOLD, atr=ATR, entry_price=ENTRY)
        assert ts.get_status()["trailing_active"]

    def test_trailing_activates_above_threshold(self) -> None:
        """Trailing activé quand price > activation_threshold."""
        ts = make_ts()
        ts.update(price=ACTIVATION_THRESHOLD + 100, atr=ATR, entry_price=ENTRY)
        assert ts.get_status()["trailing_active"]

    def test_stop_after_activation_equals_price_minus_distance(self) -> None:
        """Stop après activation = price - atr_multiplier * atr."""
        ts = make_ts()
        activation_price = ACTIVATION_THRESHOLD
        stop = ts.update(price=activation_price, atr=ATR, entry_price=ENTRY)
        expected = activation_price - MULTIPLIER * ATR
        assert stop == pytest.approx(expected)

    def test_trailing_remains_active_after_price_drop(self) -> None:
        """Une fois activé, trailing reste actif même si le prix baisse."""
        ts = make_ts()
        ts.update(price=ACTIVATION_THRESHOLD + 200, atr=ATR, entry_price=ENTRY)
        # Prix qui redescend en-dessous du seuil d'activation
        ts.update(price=ACTIVATION_THRESHOLD - 100, atr=ATR, entry_price=ENTRY)
        assert ts.get_status()["trailing_active"]


# ---------------------------------------------------------------------------
# 4. Stop ne descend jamais une fois activé
# ---------------------------------------------------------------------------


class TestStopNeverDecreases:
    def test_stop_follows_price_up(self) -> None:
        """Le stop monte quand le prix monte."""
        ts = make_ts()
        ts.update(price=ACTIVATION_THRESHOLD, atr=ATR, entry_price=ENTRY)
        stop1 = ts.update(price=ACTIVATION_THRESHOLD + 100, atr=ATR, entry_price=ENTRY)
        stop2 = ts.update(price=ACTIVATION_THRESHOLD + 200, atr=ATR, entry_price=ENTRY)
        assert stop2 > stop1

    def test_stop_does_not_decrease_on_price_drop(self) -> None:
        """Le stop ne descend pas quand le prix baisse après activation."""
        ts = make_ts()
        high_price = ACTIVATION_THRESHOLD + 500
        ts.update(price=high_price, atr=ATR, entry_price=ENTRY)
        stop_at_high = ts.get_status()["current_stop"]

        # Prix qui redescend
        lower_price = ACTIVATION_THRESHOLD + 50
        stop_after_drop = ts.update(price=lower_price, atr=ATR, entry_price=ENTRY)

        assert stop_after_drop == pytest.approx(stop_at_high)

    def test_stop_monotonic_across_sequence(self) -> None:
        """Stop strictement croissant ou stable sur une séquence de prix."""
        ts = make_ts()
        prices = [
            ACTIVATION_THRESHOLD,
            ACTIVATION_THRESHOLD + 100,
            ACTIVATION_THRESHOLD + 300,
            ACTIVATION_THRESHOLD + 200,  # recul
            ACTIVATION_THRESHOLD + 400,
            ACTIVATION_THRESHOLD + 100,  # recul fort
            ACTIVATION_THRESHOLD + 500,
        ]
        stops = []
        for p in prices:
            s = ts.update(price=p, atr=ATR, entry_price=ENTRY)
            stops.append(s)

        for i in range(1, len(stops)):
            assert stops[i] >= stops[i - 1], (
                f"Stop a baissé à l'indice {i}: {stops[i - 1]:.2f} → {stops[i]:.2f}"
            )

    def test_highest_price_tracked(self) -> None:
        """highest_price est le maximum des prix observés."""
        ts = make_ts()
        ts.update(price=ACTIVATION_THRESHOLD, atr=ATR, entry_price=ENTRY)
        ts.update(price=ACTIVATION_THRESHOLD + 300, atr=ATR, entry_price=ENTRY)
        ts.update(price=ACTIVATION_THRESHOLD + 100, atr=ATR, entry_price=ENTRY)
        status = ts.get_status()
        assert status["highest_price"] == pytest.approx(ACTIVATION_THRESHOLD + 300)


# ---------------------------------------------------------------------------
# 5. reset() efface l'état
# ---------------------------------------------------------------------------


class TestReset:
    def test_reset_clears_trailing_active(self) -> None:
        """Après reset, trailing_active == False."""
        ts = make_ts()
        ts.update(price=ACTIVATION_THRESHOLD, atr=ATR, entry_price=ENTRY)
        assert ts.get_status()["trailing_active"]
        ts.reset()
        assert not ts.get_status()["trailing_active"]

    def test_reset_clears_current_stop(self) -> None:
        """Après reset, current_stop == None."""
        ts = make_ts()
        ts.update(price=ENTRY, atr=ATR, entry_price=ENTRY)
        ts.reset()
        assert ts.get_status()["current_stop"] is None

    def test_reset_clears_highest_price(self) -> None:
        """Après reset, highest_price == None."""
        ts = make_ts()
        ts.update(price=ACTIVATION_THRESHOLD + 100, atr=ATR, entry_price=ENTRY)
        ts.reset()
        assert ts.get_status()["highest_price"] is None

    def test_reset_allows_reuse(self) -> None:
        """Après reset, un nouvel update repart de zéro (SL initial)."""
        ts = make_ts()
        ts.update(price=ACTIVATION_THRESHOLD + 200, atr=ATR, entry_price=ENTRY)
        ts.reset()
        # Nouvelle position à un prix d'entrée différent
        new_entry = 60_000.0
        stop = ts.update(price=new_entry, atr=ATR, entry_price=new_entry)
        assert stop == pytest.approx(new_entry - MULTIPLIER * ATR)
        assert not ts.get_status()["trailing_active"]

    def test_reset_then_reactivate(self) -> None:
        """Après reset, le trailing peut se réactiver normalement."""
        ts = make_ts()
        ts.update(price=ACTIVATION_THRESHOLD + 100, atr=ATR, entry_price=ENTRY)
        ts.reset()
        ts.update(price=ENTRY, atr=ATR, entry_price=ENTRY)
        assert not ts.get_status()["trailing_active"]
        ts.update(price=ACTIVATION_THRESHOLD, atr=ATR, entry_price=ENTRY)
        assert ts.get_status()["trailing_active"]


# ---------------------------------------------------------------------------
# 6. Entrées invalides lèvent ValueError
# ---------------------------------------------------------------------------


class TestInputValidation:
    def test_price_zero_raises(self) -> None:
        """price=0 lève ValueError."""
        ts = make_ts()
        with pytest.raises(ValueError, match="price"):
            ts.update(price=0.0, atr=ATR, entry_price=ENTRY)

    def test_price_negative_raises(self) -> None:
        """price < 0 lève ValueError."""
        ts = make_ts()
        with pytest.raises(ValueError, match="price"):
            ts.update(price=-1.0, atr=ATR, entry_price=ENTRY)

    def test_atr_zero_raises(self) -> None:
        """atr=0 lève ValueError."""
        ts = make_ts()
        with pytest.raises(ValueError, match="atr"):
            ts.update(price=ENTRY, atr=0.0, entry_price=ENTRY)

    def test_atr_negative_raises(self) -> None:
        """atr=-1 lève ValueError."""
        ts = make_ts()
        with pytest.raises(ValueError, match="atr"):
            ts.update(price=ENTRY, atr=-1.0, entry_price=ENTRY)

    def test_entry_price_zero_raises(self) -> None:
        """entry_price=0 lève ValueError."""
        ts = make_ts()
        with pytest.raises(ValueError, match="entry_price"):
            ts.update(price=ENTRY, atr=ATR, entry_price=0.0)

    def test_entry_price_negative_raises(self) -> None:
        """entry_price < 0 lève ValueError."""
        ts = make_ts()
        with pytest.raises(ValueError, match="entry_price"):
            ts.update(price=ENTRY, atr=ATR, entry_price=-500.0)

    def test_constructor_invalid_atr_multiplier_raises(self) -> None:
        """atr_multiplier <= 0 dans le constructeur lève ValueError."""
        with pytest.raises(ValueError, match="atr_multiplier"):
            TrailingStopATR(atr_multiplier=0.0)
        with pytest.raises(ValueError, match="atr_multiplier"):
            TrailingStopATR(atr_multiplier=-1.0)

    def test_constructor_invalid_activation_profit_raises(self) -> None:
        """activation_profit <= 0 dans le constructeur lève ValueError."""
        with pytest.raises(ValueError, match="activation_profit"):
            TrailingStopATR(activation_profit=0.0)
        with pytest.raises(ValueError, match="activation_profit"):
            TrailingStopATR(activation_profit=-0.5)


# ---------------------------------------------------------------------------
# 7. get_status() retourne le dictionnaire correct
# ---------------------------------------------------------------------------


class TestGetStatus:
    def test_initial_status_keys(self) -> None:
        """get_status() retourne les cinq clés attendues."""
        ts = make_ts()
        status = ts.get_status()
        expected_keys = {
            "trailing_active",
            "current_stop",
            "highest_price",
            "atr_multiplier",
            "activation_profit",
        }
        assert set(status.keys()) == expected_keys

    def test_initial_status_values(self) -> None:
        """get_status() avant tout update retourne les valeurs initiales."""
        ts = make_ts()
        status = ts.get_status()
        assert status["trailing_active"] is False
        assert status["current_stop"] is None
        assert status["highest_price"] is None
        assert status["atr_multiplier"] == pytest.approx(MULTIPLIER)
        assert status["activation_profit"] == pytest.approx(ACTIVATION)

    def test_status_after_inactive_update(self) -> None:
        """get_status() après un update non-activateur."""
        ts = make_ts()
        ts.update(price=ENTRY, atr=ATR, entry_price=ENTRY)
        status = ts.get_status()
        assert status["trailing_active"] is False
        assert status["current_stop"] == pytest.approx(INITIAL_SL)
        assert status["highest_price"] == pytest.approx(ENTRY)

    def test_status_after_activation(self) -> None:
        """get_status() après activation du trailing."""
        ts = make_ts()
        ts.update(price=ACTIVATION_THRESHOLD, atr=ATR, entry_price=ENTRY)
        status = ts.get_status()
        assert status["trailing_active"] is True
        expected_stop = ACTIVATION_THRESHOLD - MULTIPLIER * ATR
        assert status["current_stop"] == pytest.approx(expected_stop)
        assert status["highest_price"] == pytest.approx(ACTIVATION_THRESHOLD)

    def test_status_after_reset(self) -> None:
        """get_status() après reset retourne l'état vierge."""
        ts = make_ts()
        ts.update(price=ACTIVATION_THRESHOLD + 100, atr=ATR, entry_price=ENTRY)
        ts.reset()
        status = ts.get_status()
        assert status["trailing_active"] is False
        assert status["current_stop"] is None
        assert status["highest_price"] is None


# ---------------------------------------------------------------------------
# Thread-safety
# ---------------------------------------------------------------------------


class TestThreadSafety:
    def test_concurrent_updates_no_exception(self) -> None:
        """Aucune exception sur 200 appels update() concurrents."""
        ts = make_ts()
        errors: list[Exception] = []
        results: list[float] = []
        lock = threading.Lock()

        def worker(i: int) -> None:
            try:
                price = ENTRY + i * 10.0
                stop = ts.update(price=price, atr=ATR, entry_price=ENTRY)
                with lock:
                    results.append(stop)
            except Exception as exc:
                with lock:
                    errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(200)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Exceptions détectées : {errors}"
        assert len(results) == 200

    def test_concurrent_reset_and_update_no_exception(self) -> None:
        """reset() et update() concurrents ne lèvent pas d'exception."""
        ts = make_ts()
        errors: list[Exception] = []
        lock = threading.Lock()

        def updater(i: int) -> None:
            try:
                ts.update(price=ENTRY + i, atr=ATR, entry_price=ENTRY)
            except Exception as exc:
                with lock:
                    errors.append(exc)

        def resetter() -> None:
            try:
                ts.reset()
            except Exception as exc:
                with lock:
                    errors.append(exc)

        threads = []
        for i in range(50):
            threads.append(threading.Thread(target=updater, args=(i,)))
        for _ in range(10):
            threads.append(threading.Thread(target=resetter))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Exceptions détectées : {errors}"
