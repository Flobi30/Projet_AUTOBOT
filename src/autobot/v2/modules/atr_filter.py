"""
ATR Filter — Filtre de volatilité basé sur l'Average True Range.

Module Phase 1 d'AutoBot. Mesure la volatilité courante via ATR
et met la stratégie Grid en pause si la volatilité est hors plage :
  - ATR < min_volatility (défaut 2%) → marché trop calme, Grid inefficace
  - ATR > max_volatility (défaut 8%) → marché trop violent, risque de sortie de grille

Calcul incrémental O(1) par tick (Wilder's smoothing), thread-safe.

Usage:
    from autobot.v2.modules.atr_filter import ATRFilter

    atr = ATRFilter(period=14, min_volatility=2.0, max_volatility=8.0)

    # À chaque tick WebSocket
    atr.on_price(price)

    # Avant ouverture de position
    if atr.should_trade():
        ...  # ouvrir position
    else:
        ...  # pause automatique
"""

from collections import deque
import threading
import logging

logger = logging.getLogger(__name__)


class ATRFilter:
    """
    Filtre de volatilité basé sur l'Average True Range (ATR).

    L'ATR est exprimé en pourcentage du prix courant, ce qui le rend
    comparable entre instruments de prix très différents.

    Le lissage utilise la méthode de Wilder :
        ATR_new = ((ATR_prev * (period - 1)) + TR_current) / period

    Pendant la phase de warm-up (< period True Ranges collectés),
    l'ATR est calculé comme la moyenne arithmétique des TR accumulés.
    ``should_trade()`` retourne ``False`` tant que le warm-up n'est
    pas terminé.

    Args:
        period: Nombre de périodes pour le calcul ATR (défaut 14).
        min_volatility: Seuil bas en % — en dessous, trading désactivé (défaut 2.0).
        max_volatility: Seuil haut en % — au-dessus, trading désactivé (défaut 8.0).
    """

    def __init__(
        self,
        period: int = 14,
        min_volatility: float = 2.0,
        max_volatility: float = 8.0,
    ) -> None:
        if period < 1:
            raise ValueError(f"period doit être >= 1, reçu {period}")
        if min_volatility < 0:
            raise ValueError(f"min_volatility doit être >= 0, reçu {min_volatility}")
        if max_volatility <= min_volatility:
            raise ValueError(
                f"max_volatility ({max_volatility}) doit être > min_volatility ({min_volatility})"
            )

        self._period: int = period
        self._min_volatility: float = min_volatility
        self._max_volatility: float = max_volatility

        self._lock = threading.RLock()

        # État interne
        self._previous_price: float | None = None
        self._current_price: float | None = None
        self._atr: float | None = None          # ATR absolu lissé (Wilder)
        self._tr_buffer: deque = deque()         # TR collectés pendant le warm-up
        self._warmed_up: bool = False            # True dès que len(tr_buffer) == period
        self._tick_count: int = 0

        # Cache du dernier état loggé (évite de spammer les logs)
        self._last_logged_state: bool | None = None

        logger.info(
            "ATRFilter initialisé — période=%d, min=%.1f%%, max=%.1f%%",
            period, min_volatility, max_volatility,
        )

    # ------------------------------------------------------------------
    # Propriétés en lecture seule
    # ------------------------------------------------------------------

    @property
    def period(self) -> int:
        """Période de calcul ATR."""
        return self._period

    @property
    def min_volatility(self) -> float:
        """Seuil minimum de volatilité en %."""
        return self._min_volatility

    @property
    def max_volatility(self) -> float:
        """Seuil maximum de volatilité en %."""
        return self._max_volatility

    # ------------------------------------------------------------------
    # Méthodes publiques
    # ------------------------------------------------------------------

    def on_price(self, price: float) -> None:
        """
        Ingère un nouveau prix (tick WebSocket).

        Calcule le True Range par rapport au prix précédent et met à
        jour l'ATR de manière incrémentale.

        Args:
            price: Prix courant de l'instrument (doit être > 0).

        Thread-safe: Oui (utilise RLock interne).
        """
        if price is None or price <= 0:
            logger.warning("ATR Filter: prix invalide ignoré: %s", price)
            return

        with self._lock:
            self._tick_count += 1
            self._current_price = price

            # Premier tick : pas de TR possible, on stocke juste le prix
            if self._previous_price is None:
                self._previous_price = price
                return

            tr = self._calculate_tr(price, self._previous_price)
            self._update_atr(tr)
            self._previous_price = price

            # Log conditionnel (seulement sur changement d'état)
            self._log_state()

    def should_trade(self) -> bool:
        """
        Indique si la volatilité courante autorise le trading.

        Retourne ``False`` si :
        - Le warm-up n'est pas terminé (< period True Ranges collectés)
        - L'ATR% est inférieur à ``min_volatility``
        - L'ATR% est supérieur à ``max_volatility``

        Returns:
            True si le trading est autorisé, False sinon.

        Thread-safe: Oui (utilise RLock interne).
        """
        with self._lock:
            if not self._warmed_up:
                return False

            atr_pct = self._get_atr_percent()
            if atr_pct is None:
                return False

            return self._min_volatility <= atr_pct <= self._max_volatility

    def get_current_atr(self) -> float | None:
        """
        Retourne l'ATR courant exprimé en pourcentage du prix.

        Returns:
            ATR en pourcentage (ex: 3.5 pour 3.5%), ou None si pas
            encore disponible (warm-up en cours ou pas de données).

        Thread-safe: Oui (utilise RLock interne).
        """
        with self._lock:
            return self._get_atr_percent()

    def get_status(self) -> dict:
        """
        Retourne un dictionnaire complet de l'état du filtre.

        Returns:
            Dictionnaire contenant :
            - ``atr_percent``: ATR courant en % (ou None)
            - ``trading_enabled``: bool
            - ``warmed_up``: bool
            - ``tick_count``: nombre de ticks ingérés
            - ``current_price``: dernier prix reçu (ou None)
            - ``period``: période configurée
            - ``min_volatility``: seuil bas en %
            - ``max_volatility``: seuil haut en %
            - ``reason``: raison si trading désactivé (ou None)

        Thread-safe: Oui (utilise RLock interne).
        """
        with self._lock:
            atr_pct = self._get_atr_percent()
            trading = self.should_trade()
            reason = self._get_disabled_reason(atr_pct)

            return {
                "atr_percent": round(atr_pct, 4) if atr_pct is not None else None,
                "trading_enabled": trading,
                "warmed_up": self._warmed_up,
                "tick_count": self._tick_count,
                "current_price": self._current_price,
                "period": self._period,
                "min_volatility": self._min_volatility,
                "max_volatility": self._max_volatility,
                "reason": reason,
            }

    def reset(self) -> None:
        """
        Réinitialise le filtre (utile pour changement de marché ou test).

        Thread-safe: Oui (utilise RLock interne).
        """
        with self._lock:
            self._previous_price = None
            self._current_price = None
            self._atr = None
            self._tr_buffer.clear()
            self._warmed_up = False
            self._tick_count = 0
            self._last_logged_state = None
            logger.info("ATRFilter: réinitialisé")

    # ------------------------------------------------------------------
    # Méthodes privées
    # ------------------------------------------------------------------

    def _calculate_tr(self, current: float, previous: float) -> float:
        """
        Calcule le True Range entre deux prix consécutifs.

        Pour des données tick-only (pas de OHLC), le True Range se
        réduit à ``abs(current - previous)`` car on n'a ni high ni low
        distincts du close.

        Args:
            current: Prix courant.
            previous: Prix précédent.

        Returns:
            True Range absolu.
        """
        return abs(current - previous)

    def _update_atr(self, true_range: float) -> None:
        """
        Met à jour l'ATR de manière incrémentale O(1).

        Pendant le warm-up (< period valeurs), accumule les TR dans
        un buffer et calcule la moyenne simple provisoire.

        Une fois le warm-up terminé, utilise le lissage de Wilder :
            ATR = ((ATR_prev * (period - 1)) + TR) / period

        Args:
            true_range: True Range du tick courant.
        """
        if not self._warmed_up:
            # Phase de warm-up : accumulation
            self._tr_buffer.append(true_range)

            if len(self._tr_buffer) >= self._period:
                # Warm-up terminé : première ATR = moyenne simple
                self._atr = sum(self._tr_buffer) / self._period
                self._warmed_up = True
                self._tr_buffer.clear()  # Libère la mémoire
                logger.info(
                    "ATR Filter: warm-up terminé après %d ticks — ATR initiale: %.6f",
                    self._tick_count,
                    self._atr,
                )
            else:
                # ATR provisoire pendant le warm-up (moyenne partielle)
                self._atr = sum(self._tr_buffer) / len(self._tr_buffer)
        else:
            # Lissage de Wilder — O(1)
            self._atr = ((self._atr * (self._period - 1)) + true_range) / self._period

    def _get_atr_percent(self) -> float | None:
        """
        Calcule l'ATR en pourcentage du prix courant.

        Returns:
            ATR en pourcentage, ou None si pas de données.
        """
        if self._atr is None or self._current_price is None or self._current_price == 0:
            return None
        return (self._atr / self._current_price) * 100.0

    def _get_disabled_reason(self, atr_pct: float | None) -> str | None:
        """
        Détermine la raison pour laquelle le trading est désactivé.

        Args:
            atr_pct: ATR en pourcentage (peut être None).

        Returns:
            Chaîne décrivant la raison, ou None si trading actif.
        """
        if not self._warmed_up:
            remaining = self._period - len(self._tr_buffer)
            return f"warm-up en cours ({remaining} ticks restants)"

        if atr_pct is None:
            return "données insuffisantes"

        if atr_pct < self._min_volatility:
            return f"volatilité trop faible ({atr_pct:.2f}% < {self._min_volatility}%)"

        if atr_pct > self._max_volatility:
            return f"volatilité trop élevée ({atr_pct:.2f}% > {self._max_volatility}%)"

        return None

    def _log_state(self) -> None:
        """
        Logue l'état courant du filtre.

        Ne logue que lors d'un changement d'état (ENABLED <-> DISABLED)
        pour éviter le spam dans les logs haute fréquence.
        """
        trading = self.should_trade()
        atr_pct = self._get_atr_percent()

        # Ne loguer que sur changement d'état
        if trading == self._last_logged_state:
            return
        self._last_logged_state = trading

        if atr_pct is not None:
            status = "ENABLED" if trading else "DISABLED"
            reason = self._get_disabled_reason(atr_pct)
            reason_str = f" ({reason})" if reason else ""
            logger.info(
                "ATR: %.2f%% - Trading: %s%s",
                atr_pct,
                status,
                reason_str,
            )
