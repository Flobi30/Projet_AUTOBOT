"""
Pyramiding Manager — Ajout contrôlé à une position gagnante.

Ce module expose PyramidingManager, qui gère l'accumulation progressive
(pyramiding) d'une position rentable avec trailing stop serré sur chaque
ajout.
"""

from __future__ import annotations

import logging
import threading

__all__ = ["PyramidingManager"]

logger = logging.getLogger(__name__)


class PyramidingManager:
    """Gestionnaire de pyramiding thread-safe.

    Gère jusqu'à max_adds ajouts successifs à une position ouverte,
    déclenchés dès que le profit dépasse profit_threshold_pct.
    Chaque ajout est accompagné d'un trailing stop serré.

    Attributes:
        MAX_ADDS: Nombre maximum d'ajouts autorisés (défaut de classe).
        SCALE_INCREMENTS: Multiplicateurs de taille par niveau.
        PROFIT_THRESHOLD_PCT: Seuil de profit (%) pour déclencher un ajout.
        TRAILING_STOP_PCT: Distance du trailing stop (%) sur les ajouts.
    """

    MAX_ADDS: int = 3
    SCALE_INCREMENTS: list[float] = [1.0, 1.3, 1.5]
    PROFIT_THRESHOLD_PCT: float = 2.0
    TRAILING_STOP_PCT: float = 1.0

    def __init__(
        self,
        max_adds: int = 3,
        profit_threshold_pct: float = 2.0,
    ) -> None:
        """Initialise le gestionnaire de pyramiding.

        Args:
            max_adds: Nombre maximum d'ajouts autorisés (1-3).
            profit_threshold_pct: Seuil de profit (%) pour un ajout (> 0).

        Raises:
            ValueError: Si max_adds ou profit_threshold_pct est invalide.
        """
        max_scale_len = len(self.SCALE_INCREMENTS)
        if not (1 <= max_adds <= max_scale_len):
            raise ValueError(
                f"max_adds doit être entre 1 et {max_scale_len}, reçu : {max_adds}"
            )
        if profit_threshold_pct <= 0.0:
            raise ValueError(
                f"profit_threshold_pct doit être > 0, reçu : {profit_threshold_pct}"
            )

        self._max_adds = max_adds
        self._profit_threshold_pct = profit_threshold_pct
        self._lock = threading.RLock()

        # État de la position
        self._current_level: int = 0
        self._entry_price: float | None = None
        self._base_size: float | None = None
        self._adds: list[dict[str, float]] = []

    # ------------------------------------------------------------------
    # Interface publique
    # ------------------------------------------------------------------

    def open_position(self, entry_price: float, base_size: float) -> None:
        """Ouvre une nouvelle position et réinitialise l'état.

        Args:
            entry_price: Prix d'entrée de la position (> 0).
            base_size: Taille de base de la position (> 0).

        Raises:
            ValueError: Si les paramètres sont invalides.
        """
        if entry_price <= 0.0:
            raise ValueError(f"entry_price doit être > 0, reçu : {entry_price}")
        if base_size <= 0.0:
            raise ValueError(f"base_size doit être > 0, reçu : {base_size}")

        with self._lock:
            self._entry_price = entry_price
            self._base_size = base_size
            self._current_level = 0
            self._adds = []
            logger.debug(
                "Position ouverte — prix=%.6f taille=%.6f", entry_price, base_size
            )

    def should_add(self, current_price: float) -> bool:
        """Vérifie si un ajout à la position est déclenché.

        Conditions :
        - Une position doit être ouverte.
        - Le niveau courant doit être inférieur à max_adds.
        - Le profit (depuis entry_price) doit dépasser profit_threshold_pct.

        Args:
            current_price: Prix de marché actuel.

        Returns:
            True si toutes les conditions sont réunies, False sinon.
        """
        with self._lock:
            if self._entry_price is None:
                return False
            if self._current_level >= self._max_adds:
                return False
            profit_pct = (current_price - self._entry_price) / self._entry_price * 100.0
            return profit_pct >= self._profit_threshold_pct

    def add_to_position(self, current_price: float) -> dict[str, float] | None:
        """Tente d'ajouter à la position si les conditions sont réunies.

        Args:
            current_price: Prix de marché actuel.

        Returns:
            Dictionnaire {"size_multiplier": float, "trailing_stop": float}
            si l'ajout est effectué, None sinon.
        """
        with self._lock:
            if not self.should_add(current_price):
                return None

            scale = self.SCALE_INCREMENTS[self._current_level]
            trailing_stop = current_price * (1.0 - self.TRAILING_STOP_PCT / 100.0)
            add_info: dict[str, float] = {
                "size_multiplier": scale,
                "trailing_stop": trailing_stop,
                "price": current_price,
                "level": float(self._current_level + 1),
            }
            self._adds.append(add_info)
            self._current_level += 1
            logger.debug(
                "Ajout niveau %d — scale=%.2f trailing_stop=%.6f",
                self._current_level,
                scale,
                trailing_stop,
            )
            return {"size_multiplier": scale, "trailing_stop": trailing_stop}

    def close_position(self) -> None:
        """Ferme la position et réinitialise tout l'état."""
        with self._lock:
            self._entry_price = None
            self._base_size = None
            self._current_level = 0
            self._adds = []
            logger.debug("Position fermée — état réinitialisé.")

    def get_status(self) -> dict[str, object]:
        """Retourne l'état courant du gestionnaire.

        Returns:
            Dictionnaire avec current_level, max_adds, entry_price,
            adds et is_open.
        """
        with self._lock:
            return {
                "current_level": self._current_level,
                "max_adds": self._max_adds,
                "entry_price": self._entry_price,
                "adds": list(self._adds),
                "is_open": self._entry_price is not None,
            }
