"""
VWAP/TWAP Execution — Exécution intelligente d'ordres volumineux.

Découpe un gros ordre en tranches temporelles (TWAP) ou pondérées
par volume (VWAP) pour minimiser l'impact marché.

- TWAP : divise l'ordre en N tranches régulières sur la durée
- VWAP : pondère chaque tranche selon le profil de volume historique

Thread-safe (RLock), O(1) par tick, sans numpy/pandas.

Usage:
    from autobot.v2.modules.vwap_twap import VWAPTWAPEngine

    engine = VWAPTWAPEngine()
    engine.on_trade(price=50000, volume=0.5)
    schedule = engine.create_twap_schedule(total_volume=10.0, duration_minutes=60, slices=12)
    schedule = engine.create_vwap_schedule(total_volume=10.0, duration_minutes=60, slices=12)
"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class VWAPTWAPEngine:
    """
    Moteur d'exécution VWAP/TWAP.

    Collecte le profil de volume intraday pour pondérer les tranches VWAP.
    Gère l'exécution séquentielle des tranches avec suivi.

    Args:
        volume_buckets: Nombre de buckets horaires pour le profil de volume (défaut 24).
        max_history: Nombre max de trades stockés pour le calcul VWAP (défaut 10000).
    """

    def __init__(self, volume_buckets: int = 24, max_history: int = 10000) -> None:
        self._lock = threading.RLock()
        self._volume_buckets = volume_buckets
        self._max_history = max_history

        # Profil de volume par heure (0-23)
        self._volume_profile: List[float] = [0.0] * volume_buckets
        self._trade_counts: List[int] = [0] * volume_buckets

        # Historique des trades (price, volume, timestamp)
        self._trades: deque = deque(maxlen=max_history)

        # VWAP courant (running)
        self._cumulative_pv: float = 0.0  # sum(price * volume)
        self._cumulative_vol: float = 0.0  # sum(volume)

        # Ordres en cours
        self._active_schedules: Dict[str, Dict[str, Any]] = {}
        self._schedule_counter: int = 0

        logger.info(
            "VWAPTWAPEngine initialisé — %d buckets, max %d trades",
            volume_buckets, max_history,
        )

    # ------------------------------------------------------------------
    # Feed de données
    # ------------------------------------------------------------------

    def on_trade(self, price: float, volume: float, timestamp: Optional[datetime] = None) -> None:
        """
        Ingère un trade exécuté pour mettre à jour le VWAP et le profil de volume.

        O(1) — mise à jour incrémentale.
        """
        if price <= 0 or volume <= 0:
            return

        ts = timestamp or datetime.now(timezone.utc)

        with self._lock:
            # VWAP running
            self._cumulative_pv += price * volume
            self._cumulative_vol += volume

            # Profil de volume horaire
            hour = ts.hour % self._volume_buckets
            self._volume_profile[hour] += volume
            self._trade_counts[hour] += 1

            self._trades.append((price, volume, ts))

    def get_vwap(self) -> Optional[float]:
        """Retourne le VWAP courant. O(1)."""
        with self._lock:
            if self._cumulative_vol == 0:
                return None
            return self._cumulative_pv / self._cumulative_vol

    def get_volume_profile(self) -> List[float]:
        """Retourne le profil de volume normalisé (somme = 1.0)."""
        with self._lock:
            total = sum(self._volume_profile)
            if total == 0:
                return [1.0 / self._volume_buckets] * self._volume_buckets
            return [v / total for v in self._volume_profile]

    # ------------------------------------------------------------------
    # Création de schedules
    # ------------------------------------------------------------------

    def create_twap_schedule(
        self,
        total_volume: float,
        duration_minutes: int,
        slices: int = 10,
        side: str = "buy",
    ) -> Dict[str, Any]:
        """
        Crée un schedule TWAP : volume réparti uniformément.

        Args:
            total_volume: Volume total à exécuter.
            duration_minutes: Durée totale en minutes.
            slices: Nombre de tranches.
            side: "buy" ou "sell".

        Returns:
            Schedule dict avec id, tranches, timing.
        """
        if slices < 1:
            slices = 1
        if total_volume <= 0 or duration_minutes <= 0:
            raise ValueError("Volume et durée doivent être > 0")

        interval_sec = (duration_minutes * 60) / slices
        volume_per_slice = total_volume / slices

        with self._lock:
            self._schedule_counter += 1
            schedule_id = f"TWAP-{self._schedule_counter:04d}"

        tranches = []
        for i in range(slices):
            tranches.append({
                "slice_index": i,
                "volume": round(volume_per_slice, 8),
                "delay_seconds": round(interval_sec * i, 1),
                "status": "pending",
                "executed_price": None,
                "executed_at": None,
            })

        schedule = {
            "id": schedule_id,
            "type": "TWAP",
            "side": side,
            "total_volume": total_volume,
            "duration_minutes": duration_minutes,
            "slices": slices,
            "interval_seconds": round(interval_sec, 1),
            "tranches": tranches,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "created",
            "executed_volume": 0.0,
            "avg_price": None,
        }

        with self._lock:
            self._active_schedules[schedule_id] = schedule

        logger.info(
            "📊 TWAP créé: %s — %s %.6f en %d tranches sur %dm",
            schedule_id, side, total_volume, slices, duration_minutes,
        )
        return schedule

    def create_vwap_schedule(
        self,
        total_volume: float,
        duration_minutes: int,
        slices: int = 10,
        side: str = "buy",
        start_hour: int = 0,
    ) -> Dict[str, Any]:
        """
        Crée un schedule VWAP : volume pondéré par le profil horaire.

        Les tranches sont plus grosses aux heures de fort volume.

        Args:
            total_volume: Volume total à exécuter.
            duration_minutes: Durée totale en minutes.
            slices: Nombre de tranches.
            side: "buy" ou "sell".
            start_hour: Heure de début UTC (pour lookup profil).

        Returns:
            Schedule dict.
        """
        if slices < 1:
            slices = 1
        if total_volume <= 0 or duration_minutes <= 0:
            raise ValueError("Volume et durée doivent être > 0")

        interval_sec = (duration_minutes * 60) / slices
        profile = self.get_volume_profile()

        # Calcule les poids pour les heures couvertes par les tranches
        weights = []
        for i in range(slices):
            elapsed_minutes = (duration_minutes / slices) * i
            hour_idx = (start_hour + int(elapsed_minutes / 60)) % self._volume_buckets
            weights.append(profile[hour_idx])

        # Normalise les poids
        total_weight = sum(weights) or 1.0
        weights = [w / total_weight for w in weights]

        with self._lock:
            self._schedule_counter += 1
            schedule_id = f"VWAP-{self._schedule_counter:04d}"

        tranches = []
        for i in range(slices):
            vol = total_volume * weights[i]
            tranches.append({
                "slice_index": i,
                "volume": round(vol, 8),
                "weight": round(weights[i], 4),
                "delay_seconds": round(interval_sec * i, 1),
                "status": "pending",
                "executed_price": None,
                "executed_at": None,
            })

        schedule = {
            "id": schedule_id,
            "type": "VWAP",
            "side": side,
            "total_volume": total_volume,
            "duration_minutes": duration_minutes,
            "slices": slices,
            "interval_seconds": round(interval_sec, 1),
            "tranches": tranches,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "created",
            "executed_volume": 0.0,
            "avg_price": None,
        }

        with self._lock:
            self._active_schedules[schedule_id] = schedule

        logger.info(
            "📊 VWAP créé: %s — %s %.6f en %d tranches sur %dm",
            schedule_id, side, total_volume, slices, duration_minutes,
        )
        return schedule

    def mark_slice_executed(
        self, schedule_id: str, slice_index: int, price: float
    ) -> bool:
        """Marque une tranche comme exécutée."""
        with self._lock:
            sched = self._active_schedules.get(schedule_id)
            if not sched:
                return False

            if slice_index >= len(sched["tranches"]):
                return False

            tranche = sched["tranches"][slice_index]
            tranche["status"] = "executed"
            tranche["executed_price"] = price
            tranche["executed_at"] = datetime.now(timezone.utc).isoformat()

            sched["executed_volume"] += tranche["volume"]

            # Recalcul avg_price
            total_pv = sum(
                t["executed_price"] * t["volume"]
                for t in sched["tranches"]
                if t["status"] == "executed" and t["executed_price"]
            )
            total_v = sched["executed_volume"]
            sched["avg_price"] = round(total_pv / total_v, 2) if total_v > 0 else None

            # Vérifie si terminé
            all_done = all(t["status"] == "executed" for t in sched["tranches"])
            if all_done:
                sched["status"] = "completed"
                logger.info(
                    "✅ %s terminé — avg price: %.2f",
                    schedule_id, sched["avg_price"],
                )

            return True

    def get_schedule(self, schedule_id: str) -> Optional[Dict]:
        """Retourne un schedule par ID."""
        with self._lock:
            return self._active_schedules.get(schedule_id)

    def get_status(self) -> Dict[str, Any]:
        """Retourne l'état du moteur."""
        with self._lock:
            return {
                "vwap": round(self.get_vwap(), 2) if self.get_vwap() else None,
                "trades_ingested": len(self._trades),
                "active_schedules": len(self._active_schedules),
                "cumulative_volume": round(self._cumulative_vol, 6),
            }

    def reset(self) -> None:
        """Réinitialise le moteur."""
        with self._lock:
            self._volume_profile = [0.0] * self._volume_buckets
            self._trade_counts = [0] * self._volume_buckets
            self._trades.clear()
            self._cumulative_pv = 0.0
            self._cumulative_vol = 0.0
            self._active_schedules.clear()
            logger.info("VWAPTWAPEngine: réinitialisé")


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

    print("\n🧪 Tests VWAPTWAPEngine")
    print("=" * 50)

    engine = VWAPTWAPEngine()

    # Test 1: VWAP initial = None
    assert_test("VWAP initial = None", engine.get_vwap() is None)

    # Test 2: Feed trades
    engine.on_trade(100.0, 10.0)
    engine.on_trade(110.0, 20.0)
    engine.on_trade(105.0, 15.0)
    vwap = engine.get_vwap()
    expected_vwap = (100*10 + 110*20 + 105*15) / (10+20+15)
    assert_test(f"VWAP = {expected_vwap:.2f}", abs(vwap - expected_vwap) < 0.01)

    # Test 3: TWAP schedule
    sched = engine.create_twap_schedule(total_volume=10.0, duration_minutes=60, slices=5)
    assert_test("TWAP créé", sched["type"] == "TWAP")
    assert_test("TWAP 5 tranches", len(sched["tranches"]) == 5)
    assert_test("TWAP volume/tranche = 2.0", abs(sched["tranches"][0]["volume"] - 2.0) < 0.001)
    assert_test("TWAP interval = 720s", abs(sched["interval_seconds"] - 720.0) < 0.1)

    # Test 4: VWAP schedule
    sched_v = engine.create_vwap_schedule(total_volume=10.0, duration_minutes=60, slices=5)
    assert_test("VWAP créé", sched_v["type"] == "VWAP")
    total_vol = sum(t["volume"] for t in sched_v["tranches"])
    assert_test(f"VWAP volume total = 10.0 (got {total_vol:.4f})", abs(total_vol - 10.0) < 0.01)

    # Test 5: Mark slice executed
    ok = engine.mark_slice_executed(sched["id"], 0, 100.0)
    assert_test("Slice 0 marquée exécutée", ok)
    s = engine.get_schedule(sched["id"])
    assert_test("Executed volume = 2.0", abs(s["executed_volume"] - 2.0) < 0.01)

    # Test 6: Complete all slices
    for i in range(1, 5):
        engine.mark_slice_executed(sched["id"], i, 100.0 + i)
    s = engine.get_schedule(sched["id"])
    assert_test("Schedule completed", s["status"] == "completed")
    assert_test("Avg price calculé", s["avg_price"] is not None)

    # Test 7: Volume profile
    profile = engine.get_volume_profile()
    assert_test("Profile normalisé (somme≈1)", abs(sum(profile) - 1.0) < 0.01)

    # Test 8: Status
    status = engine.get_status()
    assert_test("Status has vwap", "vwap" in status)
    assert_test("Status has active_schedules", status["active_schedules"] >= 1)

    # Test 9: Invalid inputs
    engine.on_trade(-1, 10)  # ignored
    engine.on_trade(100, 0)  # ignored
    assert_test("Invalid trades ignored", len(engine._trades) == 3)

    # Test 10: Reset
    engine.reset()
    assert_test("Reset: VWAP = None", engine.get_vwap() is None)
    assert_test("Reset: 0 schedules", len(engine._active_schedules) == 0)

    # Test 11: Thread safety
    import concurrent.futures
    ts_engine = VWAPTWAPEngine()

    def feed_trades(n):
        for i in range(n):
            ts_engine.on_trade(100.0 + i * 0.01, 1.0)
        return n

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(feed_trades, 250) for _ in range(4)]
        [f.result() for f in futures]
    assert_test("Thread safety: 1000 trades", len(ts_engine._trades) == 1000)

    print(f"\n{'=' * 50}")
    print(f"Résultat: {passed}/{passed + failed} tests passés")
    sys.exit(0 if failed == 0 else 1)