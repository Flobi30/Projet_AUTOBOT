"""
DCA Hybride Grid — Stratégie combinant DCA (Dollar Cost Averaging) et Grid Trading.

Combine deux approches complémentaires :
  1. DCA : accumulation progressive d'un actif à intervalles réguliers
     ou sur replis de prix (dip-buying)
  2. Grid : grille d'ordres limites pour capturer la volatilité intraday

Le module calcule dynamiquement :
  - Le montant DCA ajusté selon le z-score du prix (achète plus en dip)
  - Les niveaux de grille autour du prix moyen d'achat DCA
  - Le ratio DCA/Grid selon le régime de marché détecté

Thread-safe (RLock), O(1) par tick, sans numpy/pandas.

Usage:
    from autobot.v2.modules.dca_hybrid import DCAHybridGrid

    dca = DCAHybridGrid(
        base_amount=50.0,        # montant DCA de base en €
        grid_levels=10,          # nombre de niveaux Grid
        grid_range_pct=5.0,      # range total de la grille en %
        dip_multiplier=2.0,      # multiplieur en cas de dip
    )

    # À chaque tick
    action = dca.on_price(price=50000.0)
    # action: {"dca_buy": True, "dca_amount": 75.0, "grid_orders": [...]}

    status = dca.get_status()
"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections import deque
from datetime import datetime, timezone, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class DCAHybridGrid:
    """
    Module DCA Hybride combinant Dollar Cost Averaging et Grid Trading.

    Le DCA de base est modulé par un z-score du prix : quand le prix
    est significativement en dessous de sa moyenne mobile, le montant
    d'achat est multiplié (dip-buying). Quand le prix est au-dessus,
    le montant est réduit.

    La grille est centrée sur le prix moyen pondéré d'achat (VWAP DCA)
    et ajustée dynamiquement.

    Args:
        base_amount: Montant DCA de base par intervalle (en devise quote). Défaut 50.0.
        grid_levels: Nombre de niveaux de la grille. Défaut 10.
        grid_range_pct: Range total de la grille en %. Défaut 5.0.
        dip_multiplier: Multiplieur max du montant en cas de dip. Défaut 2.0.
        lookback: Fenêtre pour le calcul de la moyenne et l'écart-type. Défaut 100.
        dca_interval_seconds: Intervalle minimum entre deux achats DCA. Défaut 3600 (1h).
        grid_take_profit_pct: Prise de profit par niveau grid en %. Défaut 1.0.
        min_amount: Montant minimum d'achat (Kraken). Défaut 5.0.
    """

    def __init__(
        self,
        base_amount: float = 50.0,
        grid_levels: int = 10,
        grid_range_pct: float = 5.0,
        dip_multiplier: float = 2.0,
        lookback: int = 100,
        dca_interval_seconds: int = 3600,
        grid_take_profit_pct: float = 1.0,
        min_amount: float = 5.0,
    ) -> None:
        if base_amount <= 0:
            raise ValueError(f"base_amount doit être > 0, reçu {base_amount}")
        if grid_levels < 2:
            raise ValueError(f"grid_levels doit être >= 2, reçu {grid_levels}")
        if grid_range_pct <= 0:
            raise ValueError(f"grid_range_pct doit être > 0, reçu {grid_range_pct}")
        if dip_multiplier < 1.0:
            raise ValueError(f"dip_multiplier doit être >= 1.0, reçu {dip_multiplier}")

        self._lock = threading.RLock()

        # Configuration
        self._base_amount = base_amount
        self._grid_levels = grid_levels
        self._grid_range_pct = grid_range_pct
        self._dip_multiplier = dip_multiplier
        self._lookback = lookback
        self._dca_interval = dca_interval_seconds
        self._grid_tp_pct = grid_take_profit_pct
        self._min_amount = min_amount

        # Historique de prix pour z-score
        self._prices: deque = deque(maxlen=lookback)
        self._price_sum: float = 0.0
        self._price_sq_sum: float = 0.0

        # État DCA
        self._total_invested: float = 0.0
        self._total_quantity: float = 0.0
        self._dca_count: int = 0
        self._last_dca_time: float = 0.0
        self._avg_price: float = 0.0  # VWAP des achats DCA

        # État Grid
        self._grid_orders: List[Dict[str, Any]] = []
        self._grid_fills: int = 0
        self._grid_profit: float = 0.0

        # État courant
        self._current_price: Optional[float] = None
        self._last_z_score: float = 0.0

        logger.info(
            f"DCAHybridGrid initialisé: base={base_amount}€, "
            f"grid={grid_levels} niveaux, range={grid_range_pct}%, "
            f"dip_mult={dip_multiplier}x"
        )

    # ------------------------------------------------------------------
    # Z-Score incrémental
    # ------------------------------------------------------------------

    def _update_stats(self, price: float) -> None:
        """Met à jour les statistiques incrémentales pour le z-score."""
        # Si le buffer est plein, retirer l'ancien
        if len(self._prices) == self._lookback:
            old = self._prices[0]
            self._price_sum -= old
            self._price_sq_sum -= old * old

        self._prices.append(price)
        self._price_sum += price
        self._price_sq_sum += price * price

    def _compute_z_score(self, price: float) -> float:
        """Calcule le z-score du prix courant par rapport à la fenêtre."""
        n = len(self._prices)
        if n < 2:
            return 0.0

        mean = self._price_sum / n
        variance = (self._price_sq_sum / n) - (mean * mean)
        if variance <= 0:
            return 0.0

        std = math.sqrt(variance)
        if std < 1e-10:
            return 0.0

        return (price - mean) / std

    # ------------------------------------------------------------------
    # DCA Logic
    # ------------------------------------------------------------------

    def _compute_dca_amount(self, z_score: float) -> float:
        """
        Calcule le montant DCA ajusté selon le z-score.

        - z < -2 : montant × dip_multiplier (max)
        - z = 0  : montant × 1.0 (base)
        - z > +2 : montant × 0.25 (réduction forte, on n'achète presque pas)

        Interpolation linéaire entre les niveaux.
        """
        if z_score <= -2.0:
            multiplier = self._dip_multiplier
        elif z_score <= 0.0:
            # Interpolation linéaire [-2, 0] → [dip_mult, 1.0]
            t = (z_score + 2.0) / 2.0  # 0 → 1
            multiplier = self._dip_multiplier + t * (1.0 - self._dip_multiplier)
        elif z_score <= 2.0:
            # Interpolation linéaire [0, 2] → [1.0, 0.25]
            t = z_score / 2.0  # 0 → 1
            multiplier = 1.0 + t * (0.25 - 1.0)
        else:
            multiplier = 0.25

        amount = self._base_amount * multiplier
        return max(amount, self._min_amount)

    def _should_dca(self) -> bool:
        """Vérifie si on peut lancer un achat DCA (intervalle respecté)."""
        now = time.time()
        return (now - self._last_dca_time) >= self._dca_interval

    def _record_dca_buy(self, price: float, amount: float) -> None:
        """Enregistre un achat DCA."""
        quantity = amount / price
        self._total_invested += amount
        self._total_quantity += quantity
        self._dca_count += 1
        self._last_dca_time = time.time()
        self._avg_price = self._total_invested / self._total_quantity if self._total_quantity > 0 else price

    # ------------------------------------------------------------------
    # Grid Logic
    # ------------------------------------------------------------------

    def _compute_grid_levels(self, center_price: float) -> List[Dict[str, Any]]:
        """
        Calcule les niveaux de la grille autour du prix central.

        Returns:
            Liste de dict avec {level, price, side, take_profit_price}
        """
        levels = []
        half_range = self._grid_range_pct / 100.0 / 2.0
        step = (2 * half_range) / (self._grid_levels - 1) if self._grid_levels > 1 else 0

        for i in range(self._grid_levels):
            offset = -half_range + i * step
            level_price = center_price * (1.0 + offset)

            if level_price < center_price:
                # Niveau bas → ordre d'achat
                side = "buy"
                tp_price = level_price * (1.0 + self._grid_tp_pct / 100.0)
            else:
                # Niveau haut → ordre de vente
                side = "sell"
                tp_price = level_price * (1.0 - self._grid_tp_pct / 100.0)

            levels.append({
                "level": i,
                "price": round(level_price, 2),
                "side": side,
                "take_profit_price": round(tp_price, 2),
                "filled": False,
            })

        return levels

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def on_price(self, price: float, available_capital: Optional[float] = None) -> Dict[str, Any]:
        """
        Traite un nouveau tick de prix.

        Args:
            price: Prix courant de l'actif.
            available_capital: Capital disponible pour trader (optionnel).
                Si fourni, le montant DCA sera plafonné à ce montant et
                aucun achat ne sera recommandé si le capital est insuffisant
                (< min_amount).

        Returns:
            Dict avec les actions recommandées:
            - dca_buy: bool, si un achat DCA est recommandé
            - dca_amount: float, montant recommandé
            - grid_orders: list, niveaux de grille actuels
            - z_score: float, z-score courant
            - skipped_reason: str ou None, raison si DCA ignoré
        """
        if price <= 0:
            raise ValueError(f"Prix doit être > 0, reçu {price}")

        with self._lock:
            self._current_price = price
            self._update_stats(price)
            z_score = self._compute_z_score(price)
            self._last_z_score = z_score

            # DCA
            dca_buy = False
            dca_amount = 0.0
            skipped_reason = None
            if self._should_dca():
                dca_amount = self._compute_dca_amount(z_score)

                # Vérification capital disponible
                if available_capital is not None:
                    if available_capital < self._min_amount:
                        skipped_reason = (
                            f"capital insuffisant ({available_capital:.2f}€ "
                            f"< min {self._min_amount:.2f}€)"
                        )
                        dca_amount = 0.0
                        logger.warning(f"DCA SKIP: {skipped_reason}")
                    elif dca_amount > available_capital:
                        old_amount = dca_amount
                        dca_amount = max(self._min_amount, available_capital)
                        logger.info(
                            f"DCA CAPPED: {old_amount:.2f}€ → {dca_amount:.2f}€ "
                            f"(capital dispo={available_capital:.2f}€)"
                        )

                if dca_amount >= self._min_amount and skipped_reason is None:
                    dca_buy = True
                    self._record_dca_buy(price, dca_amount)
                    logger.info(
                        f"DCA BUY: {dca_amount:.2f}€ @ {price:.2f} "
                        f"(z={z_score:.2f}, count={self._dca_count})"
                    )

            # Grid — centre sur le VWAP DCA ou le prix courant
            center = self._avg_price if self._avg_price > 0 else price
            self._grid_orders = self._compute_grid_levels(center)

            # Vérifier les fills de la grille
            filled_count = 0
            for order in self._grid_orders:
                if order["side"] == "buy" and price <= order["price"]:
                    if not order["filled"]:
                        order["filled"] = True
                        filled_count += 1
                elif order["side"] == "sell" and price >= order["price"]:
                    if not order["filled"]:
                        order["filled"] = True
                        filled_count += 1

            if filled_count > 0:
                self._grid_fills += filled_count
                profit_per_fill = center * (self._grid_tp_pct / 100.0) * (self._base_amount / center)
                self._grid_profit += profit_per_fill * filled_count

            return {
                "dca_buy": dca_buy,
                "dca_amount": round(dca_amount, 2),
                "dca_avg_price": round(self._avg_price, 2),
                "grid_orders": self._grid_orders,
                "grid_center": round(center, 2),
                "z_score": round(z_score, 4),
                "price": price,
                "skipped_reason": skipped_reason,
            }

    def record_grid_fill(self, level: int, profit: float) -> None:
        """Enregistre le fill d'un niveau grid (appelé par l'exécuteur d'ordres)."""
        with self._lock:
            self._grid_fills += 1
            self._grid_profit += profit

    def get_status(self) -> Dict[str, Any]:
        """Retourne l'état complet du module."""
        with self._lock:
            return {
                "module": "dca_hybrid_grid",
                "current_price": self._current_price,
                "z_score": round(self._last_z_score, 4),
                "dca": {
                    "total_invested": round(self._total_invested, 2),
                    "total_quantity": round(self._total_quantity, 8),
                    "avg_price": round(self._avg_price, 2),
                    "buy_count": self._dca_count,
                    "base_amount": self._base_amount,
                    "interval_seconds": self._dca_interval,
                },
                "grid": {
                    "levels": self._grid_levels,
                    "range_pct": self._grid_range_pct,
                    "take_profit_pct": self._grid_tp_pct,
                    "total_fills": self._grid_fills,
                    "total_profit": round(self._grid_profit, 2),
                    "active_orders": len(self._grid_orders),
                },
                "config": {
                    "dip_multiplier": self._dip_multiplier,
                    "lookback": self._lookback,
                    "min_amount": self._min_amount,
                },
                "prices_collected": len(self._prices),
                "warmed_up": len(self._prices) >= self._lookback,
            }

    def reset(self) -> None:
        """Réinitialise complètement le module."""
        with self._lock:
            self._prices.clear()
            self._price_sum = 0.0
            self._price_sq_sum = 0.0
            self._total_invested = 0.0
            self._total_quantity = 0.0
            self._dca_count = 0
            self._last_dca_time = 0.0
            self._avg_price = 0.0
            self._grid_orders = []
            self._grid_fills = 0
            self._grid_profit = 0.0
            self._current_price = None
            self._last_z_score = 0.0
            logger.info("DCAHybridGrid réinitialisé")