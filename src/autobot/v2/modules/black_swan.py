"""
Black Swan Catcher — Détecte les événements extrêmes de marché.

Surveille les anomalies statistiques sévères :
  - Flash crash (chute brutale > N écarts-types)
  - Flash pump (hausse brutale > N écarts-types)
  - Pic de volume anormal
  - Divergence prix / volume

Déclenche des actions défensives (pause trading, close positions)
ou opportunistes (catch the knife) selon la configuration.

Thread-safe (RLock), O(1) par tick, sans numpy/pandas.

Usage:
    from autobot.v2.modules.black_swan import BlackSwanCatcher

    catcher = BlackSwanCatcher(lookback=200, sigma_threshold=4.0)
    event = catcher.on_price(price, volume=100)
    if event:
        print(f"🦢 Black Swan détecté: {event['type']}")
"""

from __future__ import annotations

import logging
import math
import threading
from collections import deque
from datetime import datetime, timezone, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class BlackSwanCatcher:
    """
    Détecteur d'événements Black Swan.

    Maintient des statistiques glissantes (moyenne, écart-type) pour
    détecter les mouvements de prix anormaux en temps réel.

    Args:
        lookback: Fenêtre de lookback pour les stats (en ticks). Défaut 200.
        sigma_threshold: Seuil en écarts-types pour un événement. Défaut 4.0.
        volume_spike_ratio: Ratio volume/moyenne pour un spike de volume. Défaut 5.0.
        cooldown_ticks: Nombre de ticks avant de pouvoir re-détecter. Défaut 10.
    """

    def __init__(
        self,
        lookback: int = 200,
        sigma_threshold: float = 4.0,
        volume_spike_ratio: float = 5.0,
        cooldown_ticks: int = 10,
    ) -> None:
        self._lock = threading.RLock()
        self._lookback = lookback
        self._sigma_threshold = sigma_threshold
        self._volume_spike_ratio = volume_spike_ratio
        self._cooldown_ticks = cooldown_ticks

        # Statistiques glissantes des rendements (incrémental)
        self._returns: deque = deque(maxlen=lookback)
        self._volumes: deque = deque(maxlen=lookback)
        self._prev_price: Optional[float] = None
        self._current_price: Optional[float] = None

        # Running stats (Welford's algorithm pour O(1))
        self._n: int = 0
        self._mean: float = 0.0
        self._m2: float = 0.0  # somme des carrés des écarts

        # Volume stats
        self._vol_sum: float = 0.0

        # Événements détectés
        self._events: deque = deque(maxlen=100)
        self._cooldown_counter: int = 0
        self._tick_count: int = 0

        logger.info(
            "BlackSwanCatcher initialisé — lookback=%d, sigma=%.1f, vol_spike=%.1fx",
            lookback, sigma_threshold, volume_spike_ratio,
        )

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def on_price(self, price: float, volume: float = 0.0) -> Optional[Dict[str, Any]]:
        """
        Ingère un nouveau tick prix + volume.

        Retourne un événement Black Swan si détecté, None sinon.

        O(1) par appel grâce à Welford's algorithm.
        """
        if price <= 0:
            return None

        with self._lock:
            self._tick_count += 1

            # Décrémente cooldown
            if self._cooldown_counter > 0:
                self._cooldown_counter -= 1

            # Premier tick
            if self._prev_price is None:
                self._prev_price = price
                self._current_price = price
                if volume > 0:
                    self._volumes.append(volume)
                    self._vol_sum += volume
                return None

            self._current_price = price

            # Calcul du rendement
            ret = (price - self._prev_price) / self._prev_price
            self._prev_price = price

            # Ajout au buffer et mise à jour stats Welford
            old_ret = None
            if len(self._returns) == self._lookback:
                old_ret = self._returns[0]

            self._returns.append(ret)

            # Welford incrémental avec fenêtre glissante
            if old_ret is not None:
                # Supprime l'ancien point
                self._n -= 1
                if self._n > 0:
                    old_mean = self._mean
                    self._mean = (old_mean * (self._n + 1) - old_ret) / self._n
                    self._m2 -= (old_ret - old_mean) * (old_ret - self._mean)
                else:
                    self._mean = 0.0
                    self._m2 = 0.0

            # Ajoute le nouveau point
            self._n += 1
            delta = ret - self._mean
            self._mean += delta / self._n
            delta2 = ret - self._mean
            self._m2 += delta * delta2

            # Volume tracking
            old_vol = None
            if len(self._volumes) == self._lookback:
                old_vol = self._volumes[0]
                self._vol_sum -= old_vol
            if volume > 0:
                self._volumes.append(volume)
                self._vol_sum += volume

            # Pas assez de données
            if self._n < 20:
                return None

            # Calcul écart-type
            variance = self._m2 / self._n if self._n > 0 else 0.0
            if variance < 0:
                variance = 0.0  # Protection contre dérive numérique
            std = math.sqrt(variance)

            # Détection événement
            if std == 0:
                return None

            z_score = (ret - self._mean) / std

            event = None

            # Black Swan : z-score extrême
            if abs(z_score) >= self._sigma_threshold and self._cooldown_counter == 0:
                if z_score < 0:
                    event_type = "flash_crash"
                    severity = "CRITICAL" if abs(z_score) >= 6 else "HIGH"
                else:
                    event_type = "flash_pump"
                    severity = "CRITICAL" if abs(z_score) >= 6 else "HIGH"

                event = {
                    "type": event_type,
                    "severity": severity,
                    "z_score": round(z_score, 2),
                    "return_pct": round(ret * 100, 4),
                    "price": price,
                    "mean_return": round(self._mean * 100, 6),
                    "std_return": round(std * 100, 6),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "tick": self._tick_count,
                }

                self._events.append(event)
                self._cooldown_counter = self._cooldown_ticks

                logger.warning(
                    "🦢 BLACK SWAN: %s — z=%.2f, ret=%.4f%%, price=%.2f",
                    event_type.upper(), z_score, ret * 100, price,
                )

            # Volume spike
            if volume > 0 and not event:
                avg_vol = self._vol_sum / len(self._volumes) if self._volumes else 0
                if avg_vol > 0 and volume / avg_vol >= self._volume_spike_ratio and self._cooldown_counter == 0:
                    event = {
                        "type": "volume_spike",
                        "severity": "MEDIUM",
                        "volume": volume,
                        "avg_volume": round(avg_vol, 2),
                        "spike_ratio": round(volume / avg_vol, 2),
                        "price": price,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "tick": self._tick_count,
                    }
                    self._events.append(event)
                    self._cooldown_counter = self._cooldown_ticks

                    logger.warning(
                        "🦢 VOLUME SPIKE: %.2fx avg — vol=%.2f, price=%.2f",
                        volume / avg_vol, volume, price,
                    )

            return event

    def get_recent_events(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Retourne les derniers événements détectés."""
        with self._lock:
            return list(self._events)[-limit:]

    def get_z_score(self) -> Optional[float]:
        """Retourne le z-score du dernier rendement."""
        with self._lock:
            if self._n < 2 or not self._returns:
                return None
            variance = self._m2 / self._n if self._n > 0 else 0.0
            if variance <= 0:
                return None
            std = math.sqrt(variance)
            if std == 0:
                return None
            return (self._returns[-1] - self._mean) / std

    def get_status(self) -> Dict[str, Any]:
        """Retourne l'état du détecteur."""
        with self._lock:
            z = self.get_z_score()
            return {
                "tick_count": self._tick_count,
                "data_points": self._n,
                "current_z_score": round(z, 2) if z is not None else None,
                "events_detected": len(self._events),
                "cooldown_remaining": self._cooldown_counter,
                "sigma_threshold": self._sigma_threshold,
                "current_price": self._current_price,
            }

    def reset(self) -> None:
        """Réinitialise le détecteur."""
        with self._lock:
            self._returns.clear()
            self._volumes.clear()
            self._prev_price = None
            self._current_price = None
            self._n = 0
            self._mean = 0.0
            self._m2 = 0.0
            self._vol_sum = 0.0
            self._events.clear()
            self._cooldown_counter = 0
            self._tick_count = 0
            logger.info("BlackSwanCatcher: réinitialisé")


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

    print("\n🧪 Tests BlackSwanCatcher")
    print("=" * 50)

    catcher = BlackSwanCatcher(lookback=50, sigma_threshold=3.0, cooldown_ticks=5)

    # Test 1: Init
    assert_test("Init OK", catcher._tick_count == 0)

    # Test 2: Feed prix normaux (petite volatilité)
    import random
    random.seed(42)
    base_price = 50000.0
    for i in range(100):
        noise = random.gauss(0, 0.001)  # 0.1% std dev
        base_price *= (1 + noise)
        catcher.on_price(base_price, volume=10.0)

    assert_test("100 ticks normaux ingérés", catcher._tick_count == 100)
    assert_test("Pas d'événement sur prix normaux", len(catcher._events) == 0)

    # Test 3: Flash crash (chute de 5%)
    crash_price = base_price * 0.95
    event = catcher.on_price(crash_price, volume=10.0)
    assert_test("Flash crash détecté", event is not None)
    if event:
        assert_test("Type = flash_crash", event["type"] == "flash_crash")
        assert_test("z_score négatif", event["z_score"] < 0)

    # Test 4: Cooldown actif
    event2 = catcher.on_price(crash_price * 0.95, volume=10.0)
    assert_test("Cooldown: pas de double détection", event2 is None)

    # Test 5: Attendre fin cooldown
    for i in range(10):
        catcher.on_price(crash_price * (1 + 0.001 * i), volume=10.0)

    # Test 6: Flash pump
    pump_price = catcher._current_price * 1.06
    event3 = catcher.on_price(pump_price, volume=10.0)
    assert_test("Flash pump détecté", event3 is not None and event3["type"] == "flash_pump")

    # Test 7: Volume spike
    catcher2 = BlackSwanCatcher(lookback=50, sigma_threshold=10.0, volume_spike_ratio=5.0, cooldown_ticks=0)
    for i in range(60):
        catcher2.on_price(50000 + i, volume=10.0)
    spike_event = catcher2.on_price(50060, volume=100.0)  # 10x le volume moyen
    assert_test("Volume spike détecté", spike_event is not None and spike_event["type"] == "volume_spike")

    # Test 8: Recent events
    events = catcher.get_recent_events()
    assert_test("Events historique non vide", len(events) > 0)

    # Test 9: Status
    status = catcher.get_status()
    assert_test("Status has tick_count", status["tick_count"] > 100)
    assert_test("Status has events_detected", status["events_detected"] > 0)

    # Test 10: Reset
    catcher.reset()
    assert_test("Reset: 0 events", len(catcher._events) == 0)
    assert_test("Reset: 0 ticks", catcher._tick_count == 0)

    # Test 11: Thread safety
    import concurrent.futures
    ts_catcher = BlackSwanCatcher(lookback=200, sigma_threshold=5.0)

    def feed_prices(n):
        random.seed()
        p = 50000
        for _ in range(n):
            p *= (1 + random.gauss(0, 0.001))
            ts_catcher.on_price(p, volume=10)
        return n

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(feed_prices, 250) for _ in range(4)]
        [f.result() for f in futures]
    assert_test("Thread safety: 1000 ticks", ts_catcher._tick_count == 1000)

    print(f"\n{'=' * 50}")
    print(f"Résultat: {passed}/{passed + failed} tests passés")
    sys.exit(0 if failed == 0 else 1)