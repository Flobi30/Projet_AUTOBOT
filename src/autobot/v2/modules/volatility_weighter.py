"""
Inverse Volatility Weighting — Alloue plus de capital aux paires moins volatiles.

Formule :
    Weight_i = (1 / ATR_i) / sum(1 / ATR_j)

Les paires avec ATR = 0 sont exclues (poids = 0).
Si toutes les paires ont ATR = 0, les poids sont egaux.
"""

from __future__ import annotations

import logging
import threading

__all__ = ["VolatilityWeighter"]

logger = logging.getLogger(__name__)


class VolatilityWeighter:
    """
    Ponderation inverse par la volatilite (ATR).

    Calcule des poids normalises pour un portefeuille de paires,
    favorisant les instruments les moins volatils.
    Thread-safe via RLock.
    """

    def __init__(self) -> None:
        """Initialise le pondérateur de volatilite."""
        self._lock: threading.RLock = threading.RLock()
        self._last_weights: dict[str, float] = {}

        logger.info("VolatilityWeighter initialise")

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def calculate_weights(self, atr_values: dict[str, float]) -> dict[str, float]:
        """
        Calcule les poids inverses de volatilite normalises.

        Weight_i = (1 / ATR_i) / sum(1 / ATR_j)

        Les paires avec ATR <= 0 sont exclues (poids = 0).
        Si toutes les ATR sont nulles, retourne des poids egaux.

        Args:
            atr_values: Dictionnaire {symbole: ATR}. Exemple :
                {"BTC/USD": 250.0, "ETH/USD": 120.0}.

        Returns:
            Dictionnaire {symbole: poids} avec sum(poids) == 1.0.
            Les paires exclues ont un poids de 0.0.

        Raises:
            ValueError: Si atr_values est vide.
        """
        if not atr_values:
            raise ValueError("atr_values ne peut pas etre vide")

        with self._lock:
            symbols = list(atr_values.keys())
            weights: dict[str, float] = {s: 0.0 for s in symbols}

            valid = {s: v for s, v in atr_values.items() if v > 0.0}

            if not valid:
                # Cas degenere : toutes ATR = 0 => poids egaux
                equal_weight = 1.0 / len(symbols)
                weights = {s: equal_weight for s in symbols}
                logger.warning(
                    "VolatilityWeighter: toutes ATR = 0 — poids egaux (%.4f)",
                    equal_weight,
                )
            else:
                inverse_sum = sum(1.0 / v for v in valid.values())
                for symbol, atr in valid.items():
                    weights[symbol] = (1.0 / atr) / inverse_sum

            self._last_weights = dict(weights)

            logger.info(
                "VolatilityWeighter: poids calcules pour %d paires (%d valides)",
                len(symbols),
                len(valid) if valid else len(symbols),
            )
            return weights

    def allocate_capital(
        self, total_capital: float, atr_values: dict[str, float]
    ) -> dict[str, float]:
        """
        Repartit le capital selon les poids inverses de volatilite.

        Args:
            total_capital: Capital total a repartir (> 0).
            atr_values: Dictionnaire {symbole: ATR}.

        Returns:
            Dictionnaire {symbole: capital_alloue} ou
            capital_alloue_i = weight_i * total_capital.

        Raises:
            ValueError: Si total_capital <= 0 ou atr_values est vide.
        """
        if total_capital <= 0.0:
            raise ValueError(
                f"total_capital doit etre > 0, recu {total_capital}"
            )

        weights = self.calculate_weights(atr_values)
        allocation = {symbol: weight * total_capital for symbol, weight in weights.items()}

        logger.info(
            "VolatilityWeighter: capital %.2f distribue sur %d paires",
            total_capital,
            len(allocation),
        )
        return allocation

    def get_status(self) -> dict[str, float]:
        """
        Retourne les derniers poids calcules.

        Returns:
            Copie du dictionnaire {symbole: poids} du dernier appel
            a calculate_weights. Vide si aucun calcul n'a ete effectue.
        """
        with self._lock:
            return dict(self._last_weights)
