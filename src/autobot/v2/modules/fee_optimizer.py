"""
Fee Optimizer — Optimisation des frais de trading Kraken.

Analyse les frais (maker/taker) et recommande le type d'ordre optimal
pour minimiser les coûts sur chaque trade.

Fonctionnalités :
  - Suivi du volume 30j pour le calcul du tier de frais Kraken
  - Recommandation maker vs taker selon l'urgence du signal
  - Estimation du slippage pour comparer limit vs market
  - Calcul du breakeven minimum après frais
  - Post-only mode pour forcer les frais maker

Thread-safe (RLock), O(1) par appel.

Usage:
    from autobot.v2.modules.fee_optimizer import FeeOptimizer

    optimizer = FeeOptimizer()
    rec = optimizer.recommend(
        side="buy",
        price=50000.0,
        amount=100.0,
        urgency=0.3,       # 0=pas urgent, 1=très urgent
    )
    # rec: {"order_type": "limit", "post_only": True, "estimated_fee": 0.16, ...}

    optimizer.record_trade(volume=100.0, fee=0.16, was_maker=True)
    status = optimizer.get_status()
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from datetime import datetime, timezone, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Kraken fee tiers (spot) — volume 30j en USD
# https://www.kraken.com/features/fee-schedule
KRAKEN_FEE_TIERS: List[Tuple[float, float, float]] = [
    # (max_volume, maker_fee_pct, taker_fee_pct)
    (50_000,        0.25,  0.40),
    (100_000,       0.20,  0.35),
    (250_000,       0.14,  0.24),
    (500_000,       0.12,  0.22),
    (1_000_000,     0.10,  0.20),
    (2_500_000,     0.08,  0.18),
    (5_000_000,     0.06,  0.16),
    (10_000_000,    0.04,  0.14),
    (100_000_000,   0.02,  0.12),
    (float('inf'),  0.00,  0.10),
]


class FeeOptimizer:
    """
    Optimiseur de frais pour Kraken.

    Suit le volume de trading sur 30 jours glissants et détermine le
    tier de frais applicable. Recommande ensuite le type d'ordre
    (limit/market, post_only) en fonction de l'urgence du signal et
    du spread estimé.

    Args:
        default_maker_pct: Frais maker par défaut en %. Défaut 0.25.
        default_taker_pct: Frais taker par défaut en %. Défaut 0.40.
        urgency_threshold: Seuil d'urgence au-dessus duquel on recommande market. Défaut 0.7.
        volume_30d_initial: Volume 30j initial connu (USD). Défaut 0.
    """

    def __init__(
        self,
        default_maker_pct: float = 0.25,
        default_taker_pct: float = 0.40,
        urgency_threshold: float = 0.7,
        volume_30d_initial: float = 0.0,
    ) -> None:
        self._lock = threading.RLock()

        self._default_maker = default_maker_pct
        self._default_taker = default_taker_pct
        self._urgency_threshold = urgency_threshold

        # Volume tracking (30 jours glissants)
        self._trade_log: deque = deque()  # (timestamp, volume_usd)
        self._volume_30d: float = volume_30d_initial

        # Frais courants
        self._current_maker_pct: float = default_maker_pct
        self._current_taker_pct: float = default_taker_pct
        self._update_fee_tier()

        # Statistiques
        self._total_fees_paid: float = 0.0
        self._total_fees_saved: float = 0.0  # économie vs taker systématique
        self._maker_count: int = 0
        self._taker_count: int = 0
        self._total_volume: float = 0.0

        logger.info(
            f"FeeOptimizer initialisé: maker={self._current_maker_pct}%, "
            f"taker={self._current_taker_pct}%, "
            f"volume_30d={volume_30d_initial:.0f}$"
        )

    # ------------------------------------------------------------------
    # Fee tier management
    # ------------------------------------------------------------------

    # Complexité : O(N) pire cas (si tous les éléments sont expirés d'un coup),
    # mais O(1) amorti — chaque élément n'est purgé qu'une seule fois sur toute
    # sa durée de vie dans la deque.
    def _purge_old_trades(self) -> None:
        """Supprime les trades de plus de 30 jours du log."""
        cutoff = time.time() - (30 * 24 * 3600)
        while self._trade_log and self._trade_log[0][0] < cutoff:
            _, old_vol = self._trade_log.popleft()
            self._volume_30d -= old_vol

        # Protection contre les flottants négatifs
        if self._volume_30d < 0:
            self._volume_30d = 0.0

    def _update_fee_tier(self) -> None:
        """Met à jour le tier de frais selon le volume 30j."""
        for max_vol, maker, taker in KRAKEN_FEE_TIERS:
            if self._volume_30d <= max_vol:
                self._current_maker_pct = maker
                self._current_taker_pct = taker
                return

    def get_fees(self) -> Tuple[float, float]:
        """Retourne (maker_pct, taker_pct) courants."""
        with self._lock:
            return self._current_maker_pct, self._current_taker_pct

    # ------------------------------------------------------------------
    # Recommendation engine
    # ------------------------------------------------------------------

    def recommend(
        self,
        side: str,
        price: float,
        amount: float,
        urgency: float = 0.0,
        spread_pct: float = 0.1,
    ) -> Dict[str, Any]:
        """
        Recommande le type d'ordre optimal.

        Args:
            side: "buy" ou "sell".
            price: Prix courant.
            amount: Montant en devise quote (USD/EUR).
            urgency: Score d'urgence 0.0 (calme) à 1.0 (très urgent).
            spread_pct: Spread bid-ask estimé en %.

        Returns:
            Dict avec la recommandation complète.
        """
        with self._lock:
            self._purge_old_trades()

            # Coûts estimés
            maker_fee = amount * self._current_maker_pct / 100.0
            taker_fee = amount * self._current_taker_pct / 100.0
            fee_saving = taker_fee - maker_fee

            # Slippage estimé pour un market order
            slippage_cost = amount * spread_pct / 200.0  # moitié du spread

            # Coût total estimé
            cost_limit = maker_fee  # limit = maker, pas de slippage
            cost_market = taker_fee + slippage_cost  # market = taker + slippage

            # Décision
            if urgency >= self._urgency_threshold:
                # Signal urgent → market order
                order_type = "market"
                post_only = False
                estimated_fee = taker_fee
                reason = f"urgence haute ({urgency:.1f} >= {self._urgency_threshold})"
            elif cost_market < cost_limit * 1.1:
                # Market presque aussi cheap que limit → market
                order_type = "market"
                post_only = False
                estimated_fee = taker_fee
                reason = "coût market ≈ limit"
            else:
                # Pas urgent → limit post-only pour frais maker
                order_type = "limit"
                post_only = True
                estimated_fee = maker_fee
                reason = f"économie de {fee_saving:.4f} vs market"

            # Breakeven minimum (frais aller-retour)
            round_trip_pct = (self._current_maker_pct + self._current_taker_pct) / 100.0
            if order_type == "limit":
                round_trip_pct = (self._current_maker_pct * 2) / 100.0
            breakeven_pct = round_trip_pct * 100.0

            return {
                "order_type": order_type,
                "post_only": post_only,
                "estimated_fee": round(estimated_fee, 6),
                "estimated_fee_pct": round(
                    self._current_maker_pct if order_type == "limit" else self._current_taker_pct, 4
                ),
                "breakeven_pct": round(breakeven_pct, 4),
                "fee_saving_vs_market": round(fee_saving, 6),
                "reason": reason,
                "side": side,
                "amount": amount,
                "current_tier": {
                    "maker_pct": self._current_maker_pct,
                    "taker_pct": self._current_taker_pct,
                    "volume_30d": round(self._volume_30d, 2),
                },
            }

    # ------------------------------------------------------------------
    # Trade recording
    # ------------------------------------------------------------------

    def record_trade(
        self,
        volume: float,
        fee: float,
        was_maker: bool,
    ) -> None:
        """
        Enregistre un trade exécuté pour le suivi de volume et stats.

        Args:
            volume: Volume du trade en USD.
            fee: Frais payés.
            was_maker: True si exécuté comme maker (limit fill).
        """
        with self._lock:
            now = time.time()
            self._trade_log.append((now, volume))
            self._volume_30d += volume
            self._total_fees_paid += fee
            self._total_volume += volume

            if was_maker:
                self._maker_count += 1
                # Économie vs taker
                would_be_taker = volume * self._current_taker_pct / 100.0
                self._total_fees_saved += (would_be_taker - fee)
            else:
                self._taker_count += 1

            # Mise à jour du tier
            self._update_fee_tier()

    # ------------------------------------------------------------------
    # Breakeven calculator
    # ------------------------------------------------------------------

    def compute_breakeven(
        self,
        entry_price: float,
        side: str = "buy",
        use_maker: bool = True,
    ) -> Dict[str, float]:
        """
        Calcule le prix de breakeven après frais aller-retour.

        Args:
            entry_price: Prix d'entrée.
            side: "buy" ou "sell".
            use_maker: True si on espère être maker au close.

        Returns:
            Dict avec breakeven_price et minimum_move_pct.
        """
        with self._lock:
            entry_fee_pct = self._current_maker_pct if use_maker else self._current_taker_pct
            exit_fee_pct = self._current_maker_pct if use_maker else self._current_taker_pct
            total_fee_pct = (entry_fee_pct + exit_fee_pct) / 100.0

            if side == "buy":
                breakeven = entry_price * (1.0 + total_fee_pct)
            else:
                breakeven = entry_price * (1.0 - total_fee_pct)

            return {
                "entry_price": entry_price,
                "breakeven_price": round(breakeven, 6),
                "minimum_move_pct": round(total_fee_pct * 100, 4),
                "entry_fee_pct": entry_fee_pct,
                "exit_fee_pct": exit_fee_pct,
            }

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        """Retourne l'état complet du module."""
        with self._lock:
            self._purge_old_trades()
            total_trades = self._maker_count + self._taker_count
            maker_ratio = (self._maker_count / total_trades * 100) if total_trades > 0 else 0.0

            return {
                "module": "fee_optimizer",
                "current_tier": {
                    "maker_pct": self._current_maker_pct,
                    "taker_pct": self._current_taker_pct,
                    "volume_30d": round(self._volume_30d, 2),
                },
                "stats": {
                    "total_fees_paid": round(self._total_fees_paid, 6),
                    "total_fees_saved": round(self._total_fees_saved, 6),
                    "total_volume": round(self._total_volume, 2),
                    "maker_count": self._maker_count,
                    "taker_count": self._taker_count,
                    "maker_ratio_pct": round(maker_ratio, 1),
                },
                "config": {
                    "urgency_threshold": self._urgency_threshold,
                },
            }

    def reset(self) -> None:
        """Réinitialise les statistiques (garde le tier)."""
        with self._lock:
            self._trade_log.clear()
            self._volume_30d = 0.0
            self._total_fees_paid = 0.0
            self._total_fees_saved = 0.0
            self._maker_count = 0
            self._taker_count = 0
            self._total_volume = 0.0
            self._update_fee_tier()
            logger.info("FeeOptimizer réinitialisé")
