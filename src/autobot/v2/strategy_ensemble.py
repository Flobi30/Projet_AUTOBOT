"""
Strategy Ensemble — Combinaison de stratégies avec pondération dynamique par régime.

Ce module expose :
- MarketRegime : énumération des régimes de marché
- EnsembleSignal : signal combiné avec score de confiance 0.0-1.0
- StrategyEnsemble : agrégateur thread-safe de signaux multi-stratégies
"""

from __future__ import annotations

import logging
import threading
from enum import Enum, auto

__all__ = ["MarketRegime", "EnsembleSignal", "StrategyEnsemble", "REGIME_WEIGHTS"]

logger = logging.getLogger(__name__)

VALID_STRATEGIES: frozenset[str] = frozenset({"grid", "trend", "mean_reversion"})
VALID_DIRECTIONS: frozenset[str] = frozenset({"BUY", "SELL", "HOLD"})
SIGNAL_THRESHOLD = 0.3


class MarketRegime(Enum):
    """Régime de marché détecté par l'analyseur."""

    RANGE = auto()
    TREND_FAIBLE = auto()
    TREND_FORTE = auto()


REGIME_WEIGHTS: dict[MarketRegime, dict[str, float]] = {
    MarketRegime.RANGE: {"grid": 0.70, "trend": 0.00, "mean_reversion": 0.30},
    MarketRegime.TREND_FAIBLE: {"grid": 0.40, "trend": 0.40, "mean_reversion": 0.20},
    MarketRegime.TREND_FORTE: {"grid": 0.20, "trend": 0.80, "mean_reversion": 0.00},
}


class EnsembleSignal:
    """Signal combiné avec score de confiance 0.0-1.0.

    Attributes:
        direction: Direction du signal — "BUY", "SELL" ou "HOLD".
        score: Confiance pondérée dans l'intervalle [0.0, 1.0].
        weights_used: Pondérations appliquées par stratégie
            (ex. {"grid": 0.7, "trend": 0.0, "mean_reversion": 0.3}).
    """

    def __init__(
        self,
        direction: str,
        score: float,
        weights_used: dict[str, float],
    ) -> None:
        """Initialise un signal d'ensemble.

        Args:
            direction: "BUY", "SELL" ou "HOLD".
            score: Confiance pondérée [0.0, 1.0].
            weights_used: Pondérations par stratégie.
        """
        self.direction = direction
        self.score = score
        self.weights_used = weights_used

    def __repr__(self) -> str:
        return (
            f"EnsembleSignal(direction={self.direction!r}, "
            f"score={self.score:.3f}, weights={self.weights_used})"
        )


class StrategyEnsemble:
    """Agrégateur thread-safe de signaux multi-stratégies.

    Combine les signaux de Grid, Trend et MeanReversion avec des
    pondérations dynamiques selon le régime de marché courant.

    Thread-safety : toutes les lectures/écritures sont protégées par un
    threading.RLock.
    """

    def __init__(self) -> None:
        """Initialise l'ensemble avec des signaux vides."""
        self._lock = threading.RLock()
        # Dernier signal connu par stratégie : {"direction": str, "score": float}
        self._last_signals: dict[str, dict[str, str | float]] = {}
        self._call_count = 0

    # ------------------------------------------------------------------
    # Interface publique
    # ------------------------------------------------------------------

    def update_signal(self, strategy: str, direction: str, score: float) -> None:
        """Enregistre le dernier signal d'une stratégie.

        Args:
            strategy: Identifiant de la stratégie — "grid", "trend" ou
                "mean_reversion".
            direction: Direction du signal — "BUY", "SELL" ou "HOLD".
            score: Confiance [0.0, 1.0].

        Raises:
            ValueError: Si strategy, direction ou score est invalide.
        """
        if strategy not in VALID_STRATEGIES:
            raise ValueError(
                f"Stratégie inconnue : {strategy!r}. "
                f"Valeurs acceptées : {sorted(VALID_STRATEGIES)}"
            )
        if direction not in VALID_DIRECTIONS:
            raise ValueError(
                f"Direction invalide : {direction!r}. "
                f"Valeurs acceptées : {sorted(VALID_DIRECTIONS)}"
            )
        if not (0.0 <= score <= 1.0):
            raise ValueError(f"Le score doit être dans [0.0, 1.0], reçu : {score}")

        with self._lock:
            self._last_signals[strategy] = {"direction": direction, "score": score}
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "Signal mis à jour — stratégie=%s dir=%s score=%.3f",
                    strategy,
                    direction,
                    score,
                )

    def get_signal(self, regime: MarketRegime) -> EnsembleSignal:
        """Calcule le signal combiné pour le régime donné.

        Algorithme :
        - Pour chaque stratégie dont le signal est disponible, on cumule
          les scores pondérés côté BUY et côté SELL séparément.
        - Si buy_score > sell_score et buy_score > SIGNAL_THRESHOLD → BUY.
        - Si sell_score > buy_score et sell_score > SIGNAL_THRESHOLD → SELL.
        - Sinon → HOLD.

        Args:
            regime: Régime de marché courant.

        Returns:
            EnsembleSignal avec la direction gagnante, le score et les
            pondérations utilisées.
        """
        with self._lock:
            self._call_count += 1
            weights = REGIME_WEIGHTS[regime]
            # Pas de copie — on itère directement sous le lock
            # Évite 600K allocs/sec à haute fréquence

            buy_score = 0.0
            sell_score = 0.0

            for strategy, weight in weights.items():
                if weight == 0.0:
                    continue
                signal = self._last_signals.get(strategy)
                if signal is None:
                    continue
                direction = signal["direction"]
                score = float(signal["score"])  # type: ignore[arg-type]
                if direction == "BUY":
                    buy_score += weight * score
                elif direction == "SELL":
                    sell_score += weight * score

        if buy_score > sell_score and buy_score > SIGNAL_THRESHOLD:
            direction = "BUY"
            winning_score = buy_score
        elif sell_score > buy_score and sell_score > SIGNAL_THRESHOLD:
            direction = "SELL"
            winning_score = sell_score
        else:
            direction = "HOLD"
            winning_score = max(buy_score, sell_score)

        # Logging conditionnel pour éviter overhead en hot path
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "get_signal régime=%s buy=%.3f sell=%.3f → %s",
                regime.name,
                buy_score,
                sell_score,
                direction,
            )
        return EnsembleSignal(
            direction=direction, score=winning_score, weights_used=dict(weights)
        )

    def get_weights(self, regime: MarketRegime) -> dict[str, float]:
        """Retourne les pondérations pour un régime donné.

        Args:
            regime: Régime de marché.

        Returns:
            Dictionnaire {stratégie: poids}.
        """
        return dict(REGIME_WEIGHTS[regime])

    def get_status(self) -> dict[str, object]:
        """Retourne l'état courant de l'ensemble.

        Returns:
            Dictionnaire contenant last_signals et call_count.
        """
        with self._lock:
            return {
                "last_signals": dict(self._last_signals),
                "call_count": self._call_count,
            }
