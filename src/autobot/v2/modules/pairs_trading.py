"""
Pairs Trading — Trading de paires corrélées.

Détecte les divergences entre deux actifs historiquement corrélés et
trade le retour à la moyenne du spread.

Calcul incrémental du z-score du spread, entrée/sortie automatique.

Thread-safe (RLock), O(1) par tick, sans numpy/pandas.

Usage:
    from autobot.v2.modules.pairs_trading import PairsTrader

    trader = PairsTrader(pair_a="BTC/USD", pair_b="ETH/USD", lookback=100)
    signal = trader.on_prices(price_a=50000, price_b=3000)
"""

from __future__ import annotations

import logging
import math
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class PairsTrader:
    """
    Module de pairs trading avec spread z-score.

    ⚠️ WARNING: Le hedge ratio utilisé ici est un ratio moyen simplifié
    (price_a / price_b) sur la fenêtre glissante. Ce n'est PAS une régression
    OLS ni une cointégration de Johansen. Pour un usage en production avec des
    paires faiblement corrélées, envisager un hedge ratio basé sur une méthode
    statistiquement robuste.

    Args:
        pair_a: Symbole du premier actif.
        pair_b: Symbole du deuxième actif.
        lookback: Fenêtre pour la moyenne et l'écart-type du spread. Défaut 100.
        entry_z: Z-score d'entrée. Défaut 2.0.
        exit_z: Z-score de sortie. Défaut 0.5.
        hedge_ratio_lookback: Fenêtre pour le ratio de hedge. Défaut 50.
    """

    def __init__(
        self,
        pair_a: str = "BTC/USD",
        pair_b: str = "ETH/USD",
        lookback: int = 100,
        entry_z: float = 2.0,
        exit_z: float = 0.5,
        hedge_ratio_lookback: int = 50,
    ) -> None:
        self._lock = threading.RLock()
        self.pair_a = pair_a
        self.pair_b = pair_b
        self._lookback = lookback
        self._entry_z = entry_z
        self._exit_z = exit_z

        # Prix historiques
        self._prices_a: deque = deque(maxlen=lookback)
        self._prices_b: deque = deque(maxlen=lookback)

        # Spread : A - hedge_ratio * B
        self._spreads: deque = deque(maxlen=lookback)
        self._hedge_ratio: float = 1.0
        self._hr_lookback = hedge_ratio_lookback

        # Stats glissantes du spread (Welford)
        self._spread_n: int = 0
        self._spread_mean: float = 0.0
        self._spread_m2: float = 0.0

        # État de position
        self._position: Optional[str] = None  # "long_spread" ou "short_spread"
        self._entry_spread: float = 0.0
        self._entry_z_actual: float = 0.0

        # Métriques
        self._tick_count: int = 0
        self._signals: List[Dict[str, Any]] = []
        self._trades_count: int = 0
        self._total_pnl: float = 0.0

        logger.info(
            "PairsTrader initialisé — %s/%s, lookback=%d, entry_z=%.1f, exit_z=%.1f",
            pair_a, pair_b, lookback, entry_z, exit_z,
        )

    def on_prices(self, price_a: float, price_b: float) -> Optional[Dict[str, Any]]:
        """
        Ingère un nouveau couple de prix.

        Retourne un signal si entrée ou sortie détectée.

        O(1) par appel.
        """
        if price_a <= 0 or price_b <= 0:
            return None

        with self._lock:
            self._tick_count += 1

            self._prices_a.append(price_a)
            self._prices_b.append(price_b)

            # Mise à jour hedge ratio périodique (simplifié : ratio moyen)
            if len(self._prices_a) >= self._hr_lookback:
                n = min(self._hr_lookback, len(self._prices_a))
                ratios = []
                for i in range(1, n + 1):
                    if self._prices_b[-i] != 0:
                        ratios.append(self._prices_a[-i] / self._prices_b[-i])
                if ratios:
                    self._hedge_ratio = sum(ratios) / len(ratios)

            # Calcul du spread
            spread = price_a - self._hedge_ratio * price_b

            # Gestion fenêtre glissante
            old_spread = None
            if len(self._spreads) == self._lookback:
                old_spread = self._spreads[0]

            self._spreads.append(spread)

            # Welford incrémental
            if old_spread is not None:
                self._spread_n -= 1
                if self._spread_n > 0:
                    old_mean = self._spread_mean
                    self._spread_mean = (old_mean * (self._spread_n + 1) - old_spread) / self._spread_n
                    self._spread_m2 -= (old_spread - old_mean) * (old_spread - self._spread_mean)
                else:
                    self._spread_mean = 0.0
                    self._spread_m2 = 0.0

            self._spread_n += 1
            delta = spread - self._spread_mean
            self._spread_mean += delta / self._spread_n
            delta2 = spread - self._spread_mean
            self._spread_m2 += delta * delta2

            # Z-score
            if self._spread_n < 20:
                return None

            variance = self._spread_m2 / self._spread_n if self._spread_n > 0 else 0
            if variance <= 0:
                return None
            std = math.sqrt(variance)
            if std == 0:
                return None

            z_score = (spread - self._spread_mean) / std

            # Logique de trading
            signal = None

            if self._position is None:
                # Entrée
                if z_score >= self._entry_z:
                    self._position = "short_spread"
                    self._entry_spread = spread
                    self._entry_z_actual = z_score
                    signal = {
                        "action": "OPEN",
                        "direction": "short_spread",
                        "detail": f"Short {self.pair_a}, Long {self.pair_b}",
                        "z_score": round(z_score, 2),
                        "spread": round(spread, 4),
                        "hedge_ratio": round(self._hedge_ratio, 4),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                elif z_score <= -self._entry_z:
                    self._position = "long_spread"
                    self._entry_spread = spread
                    self._entry_z_actual = z_score
                    signal = {
                        "action": "OPEN",
                        "direction": "long_spread",
                        "detail": f"Long {self.pair_a}, Short {self.pair_b}",
                        "z_score": round(z_score, 2),
                        "spread": round(spread, 4),
                        "hedge_ratio": round(self._hedge_ratio, 4),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
            else:
                # Sortie (retour vers la moyenne)
                should_exit = False
                if self._position == "short_spread" and z_score <= self._exit_z:
                    should_exit = True
                elif self._position == "long_spread" and z_score >= -self._exit_z:
                    should_exit = True

                if should_exit:
                    pnl = 0.0
                    if self._position == "short_spread":
                        pnl = self._entry_spread - spread
                    else:
                        pnl = spread - self._entry_spread

                    self._total_pnl += pnl
                    self._trades_count += 1

                    signal = {
                        "action": "CLOSE",
                        "direction": self._position,
                        "pnl": round(pnl, 4),
                        "z_score": round(z_score, 2),
                        "spread": round(spread, 4),
                        "entry_z": round(self._entry_z_actual, 2),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    self._position = None

            if signal:
                self._signals.append(signal)
                action = signal["action"]
                direction = signal.get("direction", "")
                logger.info(
                    "📊 PairsTrading %s: %s z=%.2f spread=%.4f",
                    action, direction, z_score, spread,
                )

            return signal

    def get_z_score(self) -> Optional[float]:
        """Retourne le z-score courant du spread."""
        with self._lock:
            if self._spread_n < 2 or not self._spreads:
                return None
            variance = self._spread_m2 / self._spread_n if self._spread_n > 0 else 0
            if variance <= 0:
                return None
            std = math.sqrt(variance)
            if std == 0:
                return None
            return (self._spreads[-1] - self._spread_mean) / std

    def get_status(self) -> Dict[str, Any]:
        """Retourne l'état du module."""
        with self._lock:
            z = self.get_z_score()
            return {
                "pair_a": self.pair_a,
                "pair_b": self.pair_b,
                "position": self._position,
                "z_score": round(z, 2) if z is not None else None,
                "hedge_ratio": round(self._hedge_ratio, 4),
                "tick_count": self._tick_count,
                "trades_count": self._trades_count,
                "total_pnl": round(self._total_pnl, 4),
                "data_points": self._spread_n,
            }

    def reset(self) -> None:
        """Réinitialise."""
        with self._lock:
            self._prices_a.clear()
            self._prices_b.clear()
            self._spreads.clear()
            self._spread_n = 0
            self._spread_mean = 0.0
            self._spread_m2 = 0.0
            self._position = None
            self._tick_count = 0
            self._signals.clear()
            self._trades_count = 0
            self._total_pnl = 0.0
            logger.info("PairsTrader: réinitialisé")


# ======================================================================
# Tests intégrés
# ======================================================================
if __name__ == "__main__":
    import sys
    import random

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

    print("\n🧪 Tests PairsTrader")
    print("=" * 50)

    trader = PairsTrader(pair_a="BTC", pair_b="ETH", lookback=50, entry_z=2.0, exit_z=0.3)

    # Test 1: Init
    assert_test("Init OK", trader._tick_count == 0)

    # Test 2: Feed correlated prices (warmup)
    random.seed(42)
    for i in range(60):
        noise = random.gauss(0, 0.002)
        pa = 50000 * (1 + noise)
        pb = 3000 * (1 + noise * 0.9)  # corrélé
        trader.on_prices(pa, pb)

    assert_test("60 ticks ingérés", trader._tick_count == 60)
    z = trader.get_z_score()
    assert_test("Z-score calculable", z is not None)

    # Test 3: Force divergence (spread s'élargit)
    signals = []
    for i in range(30):
        pa = 55000 + i * 200  # A monte fort
        pb = 3000 - i * 5    # B baisse
        sig = trader.on_prices(pa, pb)
        if sig:
            signals.append(sig)

    assert_test("Signal de divergence détecté", len(signals) > 0)
    if signals:
        assert_test("Signal OPEN", signals[0]["action"] == "OPEN")

    # Test 4: Retour à la moyenne → CLOSE
    close_signals = []
    for i in range(50):
        pa = 55000 - i * 100
        pb = 3000 + i * 10
        sig = trader.on_prices(pa, pb)
        if sig and sig["action"] == "CLOSE":
            close_signals.append(sig)

    assert_test("Signal CLOSE détecté", len(close_signals) > 0)

    # Test 5: Status
    status = trader.get_status()
    assert_test("Status has pair_a", status["pair_a"] == "BTC")
    assert_test("Status has trades_count", "trades_count" in status)
    assert_test("Status has z_score", "z_score" in status)

    # Test 6: Reset
    trader.reset()
    assert_test("Reset: tick_count=0", trader._tick_count == 0)
    assert_test("Reset: no position", trader._position is None)

    # Test 7: Thread safety
    import concurrent.futures
    ts_trader = PairsTrader(lookback=50)

    def feed_pair(n):
        r = random.Random()
        for i in range(n):
            ts_trader.on_prices(50000 + r.gauss(0, 100), 3000 + r.gauss(0, 10))
        return n

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(feed_pair, 100) for _ in range(4)]
        [f.result() for f in futures]
    assert_test("Thread safety: 400 ticks", ts_trader._tick_count == 400)

    print(f"\n{'=' * 50}")
    print(f"Résultat: {passed}/{passed + failed} tests passés")
    sys.exit(0 if failed == 0 else 1)
