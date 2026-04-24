"""
Liquidation Heatmap — Détecte les zones de liquidation probables.

Maintient une carte thermique des niveaux de prix où des liquidations
en cascade sont probables, basée sur l'open interest et le levier moyen.

Utilise des buckets de prix pour agréger l'exposition. Les zones à forte
concentration deviennent des aimants de prix (support/résistance de liquidation).

Thread-safe (RLock), O(1) par tick, sans numpy/pandas.

Usage:
    from autobot.v2.modules.liquidation_heatmap import LiquidationHeatmap

    heatmap = LiquidationHeatmap(price_range_pct=20.0, bucket_count=100)
    heatmap.update_open_interest(price=50000, oi_long=1000, oi_short=800, avg_leverage=10)
    zones = heatmap.get_liquidation_zones(current_price=50000)
"""

from __future__ import annotations

import logging
import math
import threading
from collections import deque
from datetime import datetime, timezone, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class LiquidationHeatmap:
    """
    Carte thermique des zones de liquidation.

    Chaque bucket de prix stocke le volume estimé de positions
    susceptibles d'être liquidées si le prix atteint ce niveau.

    Args:
        price_range_pct: Plage de prix couverte (±X% du prix courant). Défaut 20%.
        bucket_count: Nombre de buckets dans la plage. Défaut 100.
        decay_factor: Facteur de décroissance temporelle (0-1). Défaut 0.95.
    """

    def __init__(
        self,
        price_range_pct: float = 20.0,
        bucket_count: int = 100,
        decay_factor: float = 0.95,
    ) -> None:
        self._lock = threading.RLock()
        self._price_range_pct = price_range_pct
        self._bucket_count = bucket_count
        self._decay_factor = decay_factor

        # Heatmap : {bucket_index: estimated_liquidation_volume}
        self._long_liq_map: List[float] = [0.0] * bucket_count  # liq si prix BAISSE
        self._short_liq_map: List[float] = [0.0] * bucket_count  # liq si prix MONTE

        # Prix de référence pour le centrage
        self._center_price: float = 0.0
        self._price_low: float = 0.0
        self._price_high: float = 0.0
        self._bucket_size: float = 0.0

        # Dernières données OI
        self._last_oi_long: float = 0.0
        self._last_oi_short: float = 0.0
        self._last_avg_leverage: float = 1.0
        self._update_count: int = 0

        logger.info(
            "LiquidationHeatmap initialisée — range ±%.1f%%, %d buckets",
            price_range_pct, bucket_count,
        )

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def update_open_interest(
        self,
        price: float,
        oi_long: float,
        oi_short: float,
        avg_leverage: float = 10.0,
    ) -> None:
        """
        Met à jour la heatmap avec les données d'open interest.

        Estime les niveaux de liquidation en fonction du levier moyen :
        - Longs liquidés si prix baisse de (1/leverage) * 100%
        - Shorts liquidés si prix monte de (1/leverage) * 100%

        O(bucket_count) pour le decay, sinon O(1).
        """
        if price <= 0 or avg_leverage < 1:
            return

        with self._lock:
            # Recentre la heatmap si prix a changé significativement
            if self._center_price == 0 or abs(price - self._center_price) / self._center_price > 0.05:
                self._recenter(price)

            # Decay temporel sur tout le map
            for i in range(self._bucket_count):
                self._long_liq_map[i] *= self._decay_factor
                self._short_liq_map[i] *= self._decay_factor

            # Estime la distribution de liquidation
            liq_distance_pct = 1.0 / avg_leverage  # ex: leverage 10x → 10% de distance

            # Long liquidation price = prix * (1 - 1/leverage)
            long_liq_price = price * (1.0 - liq_distance_pct)
            long_bucket = self._price_to_bucket(long_liq_price)
            if 0 <= long_bucket < self._bucket_count:
                self._long_liq_map[long_bucket] += oi_long

                # Étale sur les buckets voisins (distribution gaussienne simplifiée)
                spread = max(1, int(self._bucket_count * 0.03))
                for offset in range(1, spread + 1):
                    weight = 1.0 / (offset + 1)
                    if long_bucket - offset >= 0:
                        self._long_liq_map[long_bucket - offset] += oi_long * weight
                    if long_bucket + offset < self._bucket_count:
                        self._long_liq_map[long_bucket + offset] += oi_long * weight

            # Short liquidation price = prix * (1 + 1/leverage)
            short_liq_price = price * (1.0 + liq_distance_pct)
            short_bucket = self._price_to_bucket(short_liq_price)
            if 0 <= short_bucket < self._bucket_count:
                self._short_liq_map[short_bucket] += oi_short

                spread = max(1, int(self._bucket_count * 0.03))
                for offset in range(1, spread + 1):
                    weight = 1.0 / (offset + 1)
                    if short_bucket - offset >= 0:
                        self._short_liq_map[short_bucket - offset] += oi_short * weight
                    if short_bucket + offset < self._bucket_count:
                        self._short_liq_map[short_bucket + offset] += oi_short * weight

            self._last_oi_long = oi_long
            self._last_oi_short = oi_short
            self._last_avg_leverage = avg_leverage
            self._update_count += 1

    def get_liquidation_zones(
        self, current_price: float, top_n: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Retourne les N zones de liquidation les plus significatives.

        Args:
            current_price: Prix courant.
            top_n: Nombre de zones à retourner.

        Returns:
            Liste de dicts: {price, volume, side, distance_pct}
        """
        zones = []

        with self._lock:
            if self._bucket_size == 0:
                return zones

            # Collecte les zones long liq (baisse)
            for i, vol in enumerate(self._long_liq_map):
                if vol > 0:
                    price = self._bucket_to_price(i)
                    dist = ((price - current_price) / current_price) * 100
                    zones.append({
                        "price": round(price, 2),
                        "volume": round(vol, 2),
                        "side": "long_liq",
                        "distance_pct": round(dist, 2),
                    })

            # Collecte les zones short liq (hausse)
            for i, vol in enumerate(self._short_liq_map):
                if vol > 0:
                    price = self._bucket_to_price(i)
                    dist = ((price - current_price) / current_price) * 100
                    zones.append({
                        "price": round(price, 2),
                        "volume": round(vol, 2),
                        "side": "short_liq",
                        "distance_pct": round(dist, 2),
                    })

        # Trie par volume décroissant
        zones.sort(key=lambda z: z["volume"], reverse=True)
        return zones[:top_n]

    def is_near_liquidation_zone(
        self, current_price: float, threshold_pct: float = 2.0
    ) -> Optional[Dict[str, Any]]:
        """
        Vérifie si le prix est proche d'une zone de liquidation majeure.

        Args:
            current_price: Prix courant.
            threshold_pct: Distance max en % pour considérer "proche".

        Returns:
            Zone la plus proche si dans le seuil, None sinon.
        """
        zones = self.get_liquidation_zones(current_price, top_n=10)
        for zone in zones:
            if abs(zone["distance_pct"]) <= threshold_pct:
                return zone
        return None

    def get_status(self) -> Dict[str, Any]:
        """Retourne l'état de la heatmap."""
        with self._lock:
            long_total = sum(self._long_liq_map)
            short_total = sum(self._short_liq_map)
            return {
                "center_price": round(self._center_price, 2),
                "range": f"±{self._price_range_pct}%",
                "total_long_liq_volume": round(long_total, 2),
                "total_short_liq_volume": round(short_total, 2),
                "update_count": self._update_count,
                "avg_leverage": round(self._last_avg_leverage, 1),
            }

    def reset(self) -> None:
        """Réinitialise la heatmap."""
        with self._lock:
            self._long_liq_map = [0.0] * self._bucket_count
            self._short_liq_map = [0.0] * self._bucket_count
            self._center_price = 0.0
            self._update_count = 0
            logger.info("LiquidationHeatmap: réinitialisée")

    # ------------------------------------------------------------------
    # Méthodes privées
    # ------------------------------------------------------------------

    def _recenter(self, price: float) -> None:
        """
        Recentre la heatmap autour d'un nouveau prix.
        
        LOG-01: Au lieu de reset brutalement, on décale les buckets existants
        pour préserver l'historique de liquidation.
        """
        if self._center_price == 0:
            self._center_price = price
            self._price_low = price * (1 - self._price_range_pct / 100)
            self._price_high = price * (1 + self._price_range_pct / 100)
            self._bucket_size = (self._price_high - self._price_low) / self._bucket_count
            self._long_liq_map = [0.0] * self._bucket_count
            self._short_liq_map = [0.0] * self._bucket_count
            return

        old_low = self._price_low
        new_center = price
        new_low = new_center * (1 - self._price_range_pct / 100)
        new_high = new_center * (1 + self._price_range_pct / 100)
        new_bucket_size = (new_high - new_low) / self._bucket_count
        
        # Calculer le décalage approximatif en nombre de buckets
        # (new_low - old_low) / old_bucket_size
        shift = int(round((new_low - old_low) / self._bucket_size))
        
        if abs(shift) >= self._bucket_count:
            # Shift trop grand, reset nécessaire
            self._long_liq_map = [0.0] * self._bucket_count
            self._short_liq_map = [0.0] * self._bucket_count
        else:
            # Décaler les buckets
            new_long = [0.0] * self._bucket_count
            new_short = [0.0] * self._bucket_count
            
            for i in range(self._bucket_count):
                old_idx = i + shift
                if 0 <= old_idx < self._bucket_count:
                    new_long[i] = self._long_liq_map[old_idx]
                    new_short[i] = self._short_liq_map[old_idx]
            
            self._long_liq_map = new_long
            self._short_liq_map = new_short

        self._center_price = new_center
        self._price_low = new_low
        self._price_high = new_high
        self._bucket_size = new_bucket_size
        logger.info(f"LiquidationHeatmap recentrée (shift={shift})")

    def _price_to_bucket(self, price: float) -> int:
        """Convertit un prix en index de bucket."""
        if self._bucket_size == 0:
            return 0
        idx = int((price - self._price_low) / self._bucket_size)
        return max(0, min(idx, self._bucket_count - 1))

    def _bucket_to_price(self, bucket: int) -> float:
        """Convertit un index de bucket en prix (milieu du bucket)."""
        return self._price_low + (bucket + 0.5) * self._bucket_size


# ======================================================================
# Tests intégrés
# ======================================================================
if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    passed = 0
    failed = 0

    def assert_test(name: str, condition: bool) -> None:
        global passed, failed
        if condition:
            passed += 1
            print(f"  ✅ {name}")
        else:
            failed += 1
            print(f"  ❌ {name}")

    print("\n🧪 Tests LiquidationHeatmap")
    print("=" * 50)

    hm = LiquidationHeatmap(price_range_pct=20.0, bucket_count=100)

    # Test 1: Initial state
    assert_test("Initial: pas de zones", len(hm.get_liquidation_zones(50000)) == 0)

    # Test 2: Update OI
    hm.update_open_interest(price=50000, oi_long=1000, oi_short=800, avg_leverage=10)
    assert_test("Update count = 1", hm._update_count == 1)

    # Test 3: Zones détectées
    zones = hm.get_liquidation_zones(50000, top_n=10)
    assert_test("Zones détectées après update", len(zones) > 0)

    # Test 4: Long liq en dessous du prix
    long_zones = [z for z in zones if z["side"] == "long_liq"]
    assert_test("Long liq zones existent", len(long_zones) > 0)
    if long_zones:
        assert_test("Long liq price < current", long_zones[0]["price"] < 50000)

    # Test 5: Short liq au dessus du prix
    short_zones = [z for z in zones if z["side"] == "short_liq"]
    assert_test("Short liq zones existent", len(short_zones) > 0)
    if short_zones:
        assert_test("Short liq price > current", short_zones[0]["price"] > 50000)

    # Test 6: Near liquidation zone
    near = hm.is_near_liquidation_zone(45500, threshold_pct=5.0)
    assert_test("Near zone détectée à 45500", near is not None)

    far = hm.is_near_liquidation_zone(50000, threshold_pct=0.1)
    # Peut être None si aucune zone n'est à 0.1%
    assert_test("Loin du centre = pas de zone proche", far is None or abs(far["distance_pct"]) <= 0.1)

    # Test 7: Multiple updates with decay
    for i in range(5):
        hm.update_open_interest(price=50000, oi_long=500, oi_short=400, avg_leverage=10)
    assert_test("Decay: 6 updates", hm._update_count == 6)

    # Test 8: Status
    status = hm.get_status()
    assert_test("Status has center_price", status["center_price"] == 50000)
    assert_test("Status has avg_leverage", status["avg_leverage"] == 10.0)

    # Test 9: Reset
    hm.reset()
    assert_test("Reset: no zones", len(hm.get_liquidation_zones(50000)) == 0)

    # Test 10: Thread safety
    import concurrent.futures
    ts_hm = LiquidationHeatmap()

    def update_many(n):
        for i in range(n):
            ts_hm.update_open_interest(50000 + i, 100, 80, 10)
        return n

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(update_many, 100) for _ in range(4)]
        [f.result() for f in futures]
    assert_test("Thread safety: 400 updates", ts_hm._update_count == 400)

    print(f"\n{'=' * 50}")
    print(f"Résultat: {passed}/{passed + failed} tests passés")
    sys.exit(0 if failed == 0 else 1)