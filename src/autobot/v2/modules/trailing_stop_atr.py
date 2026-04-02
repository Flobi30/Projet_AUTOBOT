"""
Trailing Stop basé sur l'ATR (Average True Range).

Implémente un stop-loss dynamique qui suit le prix à la hausse
(trailing) une fois qu'un seuil de profit initial est atteint.

Logique :
    1. SL initial = entry_price - (atr_multiplier * atr)
    2. Activation du trailing si price >= entry_price + (activation_profit * atr)
    3. Une fois actif : stop = max(stop, price - atr_multiplier * atr)
       — le stop ne descend jamais une fois activé.
    4. Retourne toujours un stop non-None (SL initial avant activation,
       trailing stop après activation).

Usage :
    from autobot.v2.modules.trailing_stop_atr import TrailingStopATR

    ts = TrailingStopATR(atr_multiplier=2.5, activation_profit=1.5)
    stop = ts.update(price=50_000.0, atr=200.0, entry_price=49_500.0)
    if stop and price < stop:
        # clôturer la position
        ...
"""

from __future__ import annotations

import logging
import threading

__all__ = ["TrailingStopATR"]

logger = logging.getLogger(__name__)


class TrailingStopATR:
    """
    Stop-loss dynamique basé sur l'ATR avec activation par seuil de profit.

    Le trailing stop commence en mode « SL initial fixe » et bascule
    automatiquement en mode trailing une fois que le profit dépasse
    ``activation_profit * atr``.  Une fois activé, le stop ne peut
    que monter — jamais descendre.

    Args:
        atr_multiplier: Distance stop = price - (atr_multiplier * atr).
            Doit être > 0. Défaut : 2.5.
        activation_profit: Fraction d'ATR de profit requis pour activer
            le trailing. Doit être > 0. Défaut : 1.5.
    """

    def __init__(
        self,
        atr_multiplier: float = 2.5,
        activation_profit: float = 1.5,
    ) -> None:
        if atr_multiplier <= 0:
            raise ValueError(
                f"atr_multiplier doit être > 0, reçu {atr_multiplier}"
            )
        if activation_profit <= 0:
            raise ValueError(
                f"activation_profit doit être > 0, reçu {activation_profit}"
            )

        self._atr_multiplier: float = atr_multiplier
        self._activation_profit: float = activation_profit
        self._lock = threading.RLock()

        # État interne — réinitialisé par reset()
        self._trailing_active: bool = False
        self._current_stop: float | None = None
        self._highest_price: float | None = None

        logger.info(
            "TrailingStopATR initialisé — atr_multiplier=%.2f, activation_profit=%.2f",
            atr_multiplier,
            activation_profit,
        )

    # ------------------------------------------------------------------
    # Propriétés en lecture seule
    # ------------------------------------------------------------------

    @property
    def atr_multiplier(self) -> float:
        """Multiplicateur ATR pour le calcul de la distance du stop."""
        return self._atr_multiplier

    @property
    def activation_profit(self) -> float:
        """Fraction d'ATR de profit nécessaire pour activer le trailing."""
        return self._activation_profit

    # ------------------------------------------------------------------
    # Méthodes publiques
    # ------------------------------------------------------------------

    def update(self, price: float, atr: float, entry_price: float) -> float:
        """
        Met à jour le trailing stop avec le prix courant.

        Calcule et retourne le stop-loss courant.  Avant l'activation
        du trailing, retourne le SL initial fixe.  Après activation,
        retourne le trailing stop (qui ne peut que monter).

        Args:
            price: Prix courant de l'instrument. Doit être > 0.
            atr: ATR courant. Doit être > 0.
            entry_price: Prix d'entrée de la position. Doit être > 0.

        Returns:
            Prix du stop courant (toujours non-None après un appel valide).

        Raises:
            ValueError: Si price, atr ou entry_price est invalide (<= 0).

        Thread-safe : Oui (utilise RLock interne).
        """
        self._validate_inputs(price, atr, entry_price)

        with self._lock:
            initial_sl = entry_price - self._atr_multiplier * atr
            activation_threshold = entry_price + self._activation_profit * atr

            # Mise à jour du plus haut prix observé
            if self._highest_price is None or price > self._highest_price:
                self._highest_price = price

            # Vérification de l'activation du trailing
            if not self._trailing_active and price >= activation_threshold:
                self._trailing_active = True
                # Initialisation du stop trailing au niveau courant
                self._current_stop = price - self._atr_multiplier * atr
                logger.info(
                    "TrailingStop activé — price=%.4f, stop=%.4f, entry=%.4f",
                    price,
                    self._current_stop,
                    entry_price,
                )

            if self._trailing_active:
                # Le stop trailing suit le prix à la hausse — jamais en baisse
                new_stop = price - self._atr_multiplier * atr
                assert self._current_stop is not None
                self._current_stop = max(self._current_stop, new_stop)
                return self._current_stop

            # Trailing non encore activé → SL initial fixe
            self._current_stop = initial_sl
            return initial_sl

    def reset(self) -> None:
        """
        Réinitialise l'état pour une nouvelle position.

        Après appel, trailing_active=False, current_stop=None,
        highest_price=None.

        Thread-safe : Oui (utilise RLock interne).
        """
        with self._lock:
            self._trailing_active = False
            self._current_stop = None
            self._highest_price = None
            logger.info("TrailingStopATR réinitialisé")

    def get_status(self) -> dict[str, object]:
        """
        Retourne l'état courant du trailing stop.

        Returns:
            Dictionnaire contenant :
            - ``trailing_active`` : bool — trailing activé ou non
            - ``current_stop`` : float | None — stop courant
            - ``highest_price`` : float | None — plus haut prix observé
            - ``atr_multiplier`` : float — multiplicateur ATR configuré
            - ``activation_profit`` : float — seuil d'activation configuré

        Thread-safe : Oui (utilise RLock interne).
        """
        with self._lock:
            return {
                "trailing_active": self._trailing_active,
                "current_stop": self._current_stop,
                "highest_price": self._highest_price,
                "atr_multiplier": self._atr_multiplier,
                "activation_profit": self._activation_profit,
            }

    # ------------------------------------------------------------------
    # Méthodes privées
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_inputs(price: float, atr: float, entry_price: float) -> None:
        """
        Valide les paramètres d'entrée de update().

        Args:
            price: Prix courant.
            atr: ATR courant.
            entry_price: Prix d'entrée.

        Raises:
            ValueError: Si l'un des paramètres est <= 0.
        """
        if price <= 0:
            raise ValueError(f"price doit être > 0, reçu {price}")
        if atr <= 0:
            raise ValueError(f"atr doit être > 0, reçu {atr}")
        if entry_price <= 0:
            raise ValueError(f"entry_price doit être > 0, reçu {entry_price}")
