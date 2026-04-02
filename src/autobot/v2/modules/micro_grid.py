"""
Micro-Grid Scalping — Grille ultra-serrée pour scalping haute fréquence.

Place une grille très dense (step < 0.5%) autour du prix courant pour
capturer les micro-mouvements. Conçu pour les marchés latéraux à
faible spread.

Différences avec le Grid classique :
  - Niveaux très proches (0.05% - 0.3% de step)
  - Cycle rapide : repositionnement automatique toutes les N secondes
  - Profit cible très faible (quelques centimes par fill)
  - Volume élevé pour compenser -> nécessite des frais maker

Gestion intégrée :
  - Anti-drift : recentrage automatique si prix sort de la grille
  - Kill-switch si le spread > seuil (marché illiquide)
  - Suivi P&L tick-by-tick

Thread-safe (RLock), O(N) par tick où N = nombre de niveaux (petit).

Usage:
    from autobot.v2.modules.micro_grid import MicroGridScalper

    scalper = MicroGridScalper(
        grid_step_pct=0.1,
        num_levels=5,
        amount_per_level=10.0,
        max_spread_pct=0.15,
    )

    action = scalper.on_tick(bid=50000.0, ask=50010.0)
    status = scalper.get_status()
"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class MicroGridScalper:
    """
    Scalper micro-grille.

    Place des ordres limite très proches du mid-price et capture les
    rebonds de 0.05-0.3%. Recentre automatiquement la grille si le
    prix dérive au-delà d'un seuil.

    Args:
        grid_step_pct: Écart entre niveaux en %. Défaut 0.6 (minimum pour couvrir
            les frais maker aller-retour de 0.5%).
        num_levels: Nombre de niveaux de chaque côté (buy + sell). Défaut 5.
        amount_per_level: Montant par niveau en devise quote. Défaut 10.0.
        max_spread_pct: Spread max toléré. Au-delà, kill-switch. Défaut 0.15.
        recenter_threshold_pct: Seuil de drift pour recentrer. Défaut 0.3.
        min_profit_pct: Profit minimum par roundtrip (frais maker×2 = 0.50%).
            Défaut 0.50. Le step doit être > min_profit_pct pour être rentable.
        cooldown_seconds: Cooldown entre deux recentrages. Défaut 5.
    """

    # Frais maker Kraken aller-retour : 0.25% × 2 = 0.50%
    # Le step minimum doit couvrir ces frais pour être rentable.
    MIN_ROUNDTRIP_FEE_PCT: float = 0.50
    MIN_STEP_PCT: float = 0.6  # step minimum (> frais maker×2)

    def __init__(
        self,
        grid_step_pct: float = 0.6,
        num_levels: int = 5,
        amount_per_level: float = 10.0,
        max_spread_pct: float = 0.15,
        recenter_threshold_pct: float = 0.3,
        min_profit_pct: float = 0.50,
        cooldown_seconds: float = 5.0,
    ) -> None:
        if grid_step_pct <= 0:
            raise ValueError(f"grid_step_pct doit être > 0, reçu {grid_step_pct}")
        if grid_step_pct < self.MIN_STEP_PCT:
            raise ValueError(
                f"grid_step_pct doit être >= {self.MIN_STEP_PCT}% pour couvrir "
                f"les frais maker aller-retour ({self.MIN_ROUNDTRIP_FEE_PCT}%), "
                f"reçu {grid_step_pct}%"
            )
        if min_profit_pct < self.MIN_ROUNDTRIP_FEE_PCT:
            raise ValueError(
                f"min_profit_pct doit être >= {self.MIN_ROUNDTRIP_FEE_PCT}% "
                f"(frais maker×2), reçu {min_profit_pct}%"
            )
        if num_levels < 1:
            raise ValueError(f"num_levels doit être >= 1, reçu {num_levels}")
        if amount_per_level <= 0:
            raise ValueError(f"amount_per_level doit être > 0, reçu {amount_per_level}")

        self._lock = threading.RLock()

        # Configuration
        self._step_pct = grid_step_pct
        self._num_levels = num_levels
        self._amount_per_level = amount_per_level
        self._max_spread_pct = max_spread_pct
        self._recenter_threshold_pct = recenter_threshold_pct
        self._min_profit_pct = min_profit_pct
        self._cooldown = cooldown_seconds

        # État de la grille
        self._center_price: Optional[float] = None
        self._buy_levels: List[Dict[str, Any]] = []
        self._sell_levels: List[Dict[str, Any]] = []
        self._active: bool = True
        self._kill_switch: bool = False

        # Timing
        self._last_recenter: float = 0.0
        self._created_at: float = time.time()

        # Stats
        self._total_fills: int = 0
        self._buy_fills: int = 0
        self._sell_fills: int = 0
        self._total_profit: float = 0.0
        self._total_volume: float = 0.0
        self._recenters: int = 0
        self._kill_switch_triggers: int = 0
        self._ticks_processed: int = 0

        # Historique P&L pour tracking
        self._pnl_history: deque = deque(maxlen=1000)

        logger.info(
            f"MicroGridScalper initialisé: step={grid_step_pct}%, "
            f"levels={num_levels}×2, amount={amount_per_level}€/level, "
            f"max_spread={max_spread_pct}%"
        )

    # ------------------------------------------------------------------
    # Grid construction
    # ------------------------------------------------------------------

    def _build_grid(self, mid_price: float) -> None:
        """Construit la grille autour du mid-price."""
        self._center_price = mid_price
        self._buy_levels = []
        self._sell_levels = []

        step_factor = self._step_pct / 100.0

        for i in range(1, self._num_levels + 1):
            # Niveaux d'achat (sous le mid)
            buy_price = mid_price * (1.0 - i * step_factor)
            self._buy_levels.append({
                "level": i,
                "price": round(buy_price, 6),
                "amount": self._amount_per_level,
                "filled": False,
                "fill_time": None,
            })

            # Niveaux de vente (au-dessus du mid)
            sell_price = mid_price * (1.0 + i * step_factor)
            self._sell_levels.append({
                "level": i,
                "price": round(sell_price, 6),
                "amount": self._amount_per_level,
                "filled": False,
                "fill_time": None,
            })

    def _needs_recenter(self, mid_price: float) -> bool:
        """Vérifie si la grille doit être recentrée."""
        if self._center_price is None:
            return True

        drift_pct = abs(mid_price - self._center_price) / self._center_price * 100
        if drift_pct >= self._recenter_threshold_pct:
            now = time.time()
            if (now - self._last_recenter) >= self._cooldown:
                return True
        return False

    # ------------------------------------------------------------------
    # Tick processing
    # ------------------------------------------------------------------

    def on_tick(self, bid: float, ask: float) -> Dict[str, Any]:
        """
        Traite un tick bid/ask.

        Args:
            bid: Prix bid courant.
            ask: Prix ask courant.

        Returns:
            Dict avec les actions et l'état courant.
        """
        if bid <= 0 or ask <= 0 or ask < bid:
            raise ValueError(f"Prix invalides: bid={bid}, ask={ask}")

        with self._lock:
            self._ticks_processed += 1
            mid_price = (bid + ask) / 2.0
            spread_pct = (ask - bid) / mid_price * 100.0

            # Kill-switch si spread trop large
            if spread_pct > self._max_spread_pct:
                if not self._kill_switch:
                    self._kill_switch = True
                    self._kill_switch_triggers += 1
                    logger.warning(
                        f"MicroGrid KILL-SWITCH: spread={spread_pct:.3f}% > "
                        f"max={self._max_spread_pct}%"
                    )
                return {
                    "action": "kill_switch",
                    "reason": f"spread {spread_pct:.3f}% > {self._max_spread_pct}%",
                    "mid_price": mid_price,
                    "spread_pct": round(spread_pct, 4),
                    "orders": [],
                }

            # Réactivation si spread revient
            if self._kill_switch:
                self._kill_switch = False
                logger.info(f"MicroGrid réactivé: spread={spread_pct:.3f}%")

            # Construction / recentrage de la grille
            if self._needs_recenter(mid_price):
                self._build_grid(mid_price)
                self._last_recenter = time.time()
                self._recenters += 1

            # Vérifier les fills
            new_orders = []
            fills_this_tick = 0

            for level in self._buy_levels:
                if not level["filled"] and bid <= level["price"]:
                    level["filled"] = True
                    level["fill_time"] = time.time()
                    self._buy_fills += 1
                    self._total_fills += 1
                    self._total_volume += level["amount"]
                    fills_this_tick += 1

                    # L'achat est fill → on place un sell correspondant
                    tp_price = level["price"] * (1.0 + self._step_pct / 100.0)
                    new_orders.append({
                        "side": "sell",
                        "price": round(tp_price, 6),
                        "amount": level["amount"],
                        "reason": f"TP buy level {level['level']}",
                    })

            for level in self._sell_levels:
                if not level["filled"] and ask >= level["price"]:
                    level["filled"] = True
                    level["fill_time"] = time.time()
                    self._sell_fills += 1
                    self._total_fills += 1
                    self._total_volume += level["amount"]
                    fills_this_tick += 1

                    # La vente est fill → on place un buy correspondant
                    tp_price = level["price"] * (1.0 - self._step_pct / 100.0)
                    new_orders.append({
                        "side": "buy",
                        "price": round(tp_price, 6),
                        "amount": level["amount"],
                        "reason": f"TP sell level {level['level']}",
                    })

            # Estimation profit par fill :
            # profit = montant × (step% − frais maker aller-retour%) / 100
            # min_profit_pct = frais maker×2 = 0.50%, step doit être > min_profit_pct
            if fills_this_tick > 0:
                net_margin_pct = self._step_pct - self._min_profit_pct
                profit_per_fill = self._amount_per_level * net_margin_pct / 100.0
                tick_profit = profit_per_fill * fills_this_tick
                self._total_profit += tick_profit
                self._pnl_history.append({
                    "time": time.time(),
                    "profit": tick_profit,
                    "fills": fills_this_tick,
                })

            return {
                "action": "active",
                "mid_price": round(mid_price, 6),
                "spread_pct": round(spread_pct, 4),
                "center_price": round(self._center_price, 6) if self._center_price else None,
                "fills_this_tick": fills_this_tick,
                "new_orders": new_orders,
                "total_fills": self._total_fills,
                "buy_levels_active": sum(1 for l in self._buy_levels if not l["filled"]),
                "sell_levels_active": sum(1 for l in self._sell_levels if not l["filled"]),
            }

    def record_fill(self, side: str, price: float, amount: float, profit: float) -> None:
        """Enregistre un fill externe (callback de l'exchange)."""
        with self._lock:
            self._total_fills += 1
            self._total_volume += amount
            self._total_profit += profit
            if side == "buy":
                self._buy_fills += 1
            else:
                self._sell_fills += 1

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    def pause(self) -> None:
        """Met en pause le scalper."""
        with self._lock:
            self._active = False
            logger.info("MicroGrid mis en pause")

    def resume(self) -> None:
        """Reprend le scalper."""
        with self._lock:
            self._active = True
            self._kill_switch = False
            logger.info("MicroGrid repris")

    def force_recenter(self, price: float) -> None:
        """Force un recentrage de la grille."""
        with self._lock:
            self._build_grid(price)
            self._last_recenter = time.time()
            self._recenters += 1
            logger.info(f"MicroGrid recentré sur {price}")

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        """Retourne l'état complet du module."""
        with self._lock:
            uptime = time.time() - self._created_at
            fills_per_hour = (self._total_fills / uptime * 3600) if uptime > 0 else 0

            return {
                "module": "micro_grid_scalper",
                "active": self._active,
                "kill_switch": self._kill_switch,
                "center_price": self._center_price,
                "config": {
                    "grid_step_pct": self._step_pct,
                    "num_levels": self._num_levels,
                    "amount_per_level": self._amount_per_level,
                    "max_spread_pct": self._max_spread_pct,
                    "recenter_threshold_pct": self._recenter_threshold_pct,
                },
                "stats": {
                    "total_fills": self._total_fills,
                    "buy_fills": self._buy_fills,
                    "sell_fills": self._sell_fills,
                    "total_profit": round(self._total_profit, 6),
                    "total_volume": round(self._total_volume, 2),
                    "recenters": self._recenters,
                    "kill_switch_triggers": self._kill_switch_triggers,
                    "ticks_processed": self._ticks_processed,
                    "fills_per_hour": round(fills_per_hour, 1),
                    "uptime_seconds": round(uptime, 0),
                },
                "grid": {
                    "buy_levels": len(self._buy_levels),
                    "sell_levels": len(self._sell_levels),
                    "buy_active": sum(1 for l in self._buy_levels if not l["filled"]),
                    "sell_active": sum(1 for l in self._sell_levels if not l["filled"]),
                },
            }

    def reset(self) -> None:
        """Réinitialise le scalper."""
        with self._lock:
            self._center_price = None
            self._buy_levels = []
            self._sell_levels = []
            self._active = True
            self._kill_switch = False
            self._total_fills = 0
            self._buy_fills = 0
            self._sell_fills = 0
            self._total_profit = 0.0
            self._total_volume = 0.0
            self._recenters = 0
            self._kill_switch_triggers = 0
            self._ticks_processed = 0
            self._pnl_history.clear()
            self._created_at = time.time()
            logger.info("MicroGridScalper réinitialisé")
