"""
Momentum Scoring — Score de momentum multi-timeframe.

Calcule un score de momentum composite (0-100) basé sur :
  - Rate of Change (ROC) sur plusieurs fenêtres
  - Force relative (RSI simplifié)
  - Accélération du momentum (dérivée seconde)

Le score guide les décisions de trading :
  - > 70 : Fort momentum haussier → favoriser longs
  - 30-70 : Neutre → attendre
  - < 30 : Fort momentum baissier → favoriser shorts

Thread-safe (RLock), O(1) par tick, sans numpy/pandas.

Usage:
    from autobot.v2.modules.momentum_scoring import MomentumScorer

    scorer = MomentumScorer()
    scorer.on_price(50000)
    score = scorer.get_score()
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from datetime import datetime, timezone, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class MomentumScorer:
    """
    Calculateur de score de momentum multi-fenêtre.

    Combine plusieurs indicateurs de momentum pour produire un score
    normalisé entre 0 et 100.

    Args:
        roc_periods: Liste des périodes pour le Rate of Change. Défaut [10, 20, 50].
        rsi_period: Période pour le RSI simplifié. Défaut 14.
        max_history: Taille max du buffer de prix. Défaut 200.
    """

    def __init__(
        self,
        roc_periods: Optional[List[int]] = None,
        rsi_period: int = 14,
        max_history: int = 200,
    ) -> None:
        self._lock = threading.RLock()
        self._roc_periods = roc_periods or [10, 20, 50]
        self._rsi_period = rsi_period
        self._max_history = max(max_history, max(self._roc_periods) + 10)

        # Buffer de prix
        self._prices: deque = deque(maxlen=self._max_history)

        # RSI incrémental (Wilder's smoothing)
        self._avg_gain: float = 0.0
        self._avg_loss: float = 0.0
        self._rsi_ready: bool = False
        self._rsi_count: int = 0
        self._gains_buffer: deque = deque(maxlen=rsi_period)

        # Cache du score
        self._last_score: float = 50.0
        self._tick_count: int = 0

        logger.info(
            "MomentumScorer initialisé — ROC periods=%s, RSI period=%d",
            self._roc_periods, rsi_period,
        )

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def on_price(self, price: float) -> float:
        """
        Ingère un nouveau prix et retourne le score de momentum.

        O(1) — tous les calculs sont incrémentaux.

        Returns:
            Score de momentum (0-100).
        """
        if price <= 0:
            return self._last_score

        with self._lock:
            self._tick_count += 1

            # RSI incrémental
            if len(self._prices) > 0:
                change = price - self._prices[-1]
                gain = max(change, 0.0)
                loss = max(-change, 0.0)

                self._rsi_count += 1

                if not self._rsi_ready:
                    self._gains_buffer.append((gain, loss))
                    if self._rsi_count >= self._rsi_period:
                        # Première valeur RSI = moyenne simple
                        self._avg_gain = sum(g for g, _ in self._gains_buffer) / self._rsi_period
                        self._avg_loss = sum(l for _, l in self._gains_buffer) / self._rsi_period
                        self._rsi_ready = True
                else:
                    # Wilder's smoothing O(1)
                    self._avg_gain = (self._avg_gain * (self._rsi_period - 1) + gain) / self._rsi_period
                    self._avg_loss = (self._avg_loss * (self._rsi_period - 1) + loss) / self._rsi_period

            self._prices.append(price)

            # Calcul du score composite
            self._last_score = self._compute_score()
            return self._last_score

    def get_score(self) -> float:
        """Retourne le dernier score de momentum (0-100). O(1)."""
        with self._lock:
            return self._last_score

    def get_rsi(self) -> Optional[float]:
        """Retourne le RSI courant (0-100), ou None si pas prêt."""
        with self._lock:
            if not self._rsi_ready:
                return None
            if self._avg_loss == 0:
                return 100.0
            rs = self._avg_gain / self._avg_loss
            return 100.0 - (100.0 / (1.0 + rs))

    def get_roc(self, period: int) -> Optional[float]:
        """Retourne le Rate of Change sur N périodes (en %)."""
        with self._lock:
            if len(self._prices) <= period:
                return None
            old_price = self._prices[-1 - period]
            if old_price == 0:
                return None
            return ((self._prices[-1] - old_price) / old_price) * 100.0

    def get_signal(self) -> str:
        """
        Retourne un signal basé sur le score.

        Returns:
            "bullish" si score > 70, "bearish" si < 30, "neutral" sinon.
        """
        score = self.get_score()
        if score > 70:
            return "bullish"
        elif score < 30:
            return "bearish"
        return "neutral"

    def get_status(self) -> Dict[str, Any]:
        """Retourne l'état du scorer."""
        with self._lock:
            rsi = self.get_rsi()
            rocs = {}
            for p in self._roc_periods:
                r = self.get_roc(p)
                rocs[f"roc_{p}"] = round(r, 4) if r is not None else None

            return {
                "score": round(self._last_score, 2),
                "signal": self.get_signal(),
                "rsi": round(rsi, 2) if rsi is not None else None,
                "rocs": rocs,
                "tick_count": self._tick_count,
                "data_points": len(self._prices),
                "warmed_up": self._rsi_ready and len(self._prices) >= max(self._roc_periods),
            }

    def reset(self) -> None:
        """Réinitialise le scorer."""
        with self._lock:
            self._prices.clear()
            self._avg_gain = 0.0
            self._avg_loss = 0.0
            self._rsi_ready = False
            self._rsi_count = 0
            self._gains_buffer.clear()
            self._last_score = 50.0
            self._tick_count = 0
            logger.info("MomentumScorer: réinitialisé")

    # ------------------------------------------------------------------
    # Méthodes privées
    # ------------------------------------------------------------------

    def _compute_score(self) -> float:
        """
        Calcule le score composite de momentum.

        Combine :
        - RSI normalisé (poids 0.4)
        - ROC multi-fenêtre normalisé (poids 0.4)
        - Accélération du momentum (poids 0.2)

        Returns:
            Score entre 0 et 100.
        """
        components = []
        weights = []

        # Composant RSI (0-100 directement)
        rsi = self.get_rsi()
        if rsi is not None:
            components.append(rsi)
            weights.append(0.4)

        # Composant ROC (moyenne des ROC normalisés)
        # CORRECTION Review: Pour les cryptos volatiles, un ROC de ±10% est
        # courant et saturerait le score. On utilise un facteur adaptatif :
        # - Fenêtres courtes (5-10) → ROC souvent élevé → facteur faible (2.0)
        # - Fenêtres longues (50+)  → ROC plus modéré  → facteur plus élevé (5.0)
        # Cela évite la saturation à 0/100 sur les cryptos tout en restant
        # sensible aux mouvements sur les fenêtres longues.
        roc_scores = []
        for period in self._roc_periods:
            roc = self.get_roc(period)
            if roc is not None:
                # Facteur adaptatif : fenêtres courtes → plage plus large (±25%)
                # fenêtres longues → plage standard (±10%)
                if period <= 10:
                    norm_factor = 2.0   # ±25% → [0, 100]
                elif period <= 30:
                    norm_factor = 3.0   # ±16.7% → [0, 100]
                else:
                    norm_factor = 5.0   # ±10% → [0, 100]
                normalized = max(0.0, min(100.0, 50.0 + roc * norm_factor))
                roc_scores.append(normalized)

        if roc_scores:
            avg_roc = sum(roc_scores) / len(roc_scores)
            components.append(avg_roc)
            weights.append(0.4)

        # Composant accélération (dérivée seconde du prix)
        if len(self._prices) >= 3:
            p = self._prices
            ret_now = (p[-1] - p[-2]) / p[-2] if p[-2] != 0 else 0
            ret_prev = (p[-2] - p[-3]) / p[-3] if p[-3] != 0 else 0
            accel = ret_now - ret_prev
            # Normalise: -0.02 → 0, 0 → 50, +0.02 → 100
            accel_score = max(0.0, min(100.0, 50.0 + accel * 2500.0))
            components.append(accel_score)
            weights.append(0.2)

        if not components:
            return 50.0

        # Moyenne pondérée
        total_weight = sum(weights)
        if total_weight == 0:
            return 50.0

        score = sum(c * w for c, w in zip(components, weights)) / total_weight
        return max(0.0, min(100.0, score))


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

    print("\n🧪 Tests MomentumScorer")
    print("=" * 50)

    scorer = MomentumScorer(roc_periods=[5, 10, 20], rsi_period=14)

    # Test 1: Initial score = 50
    assert_test("Score initial = 50", scorer.get_score() == 50.0)

    # Test 2: Feed prix en hausse
    for i in range(60):
        scorer.on_price(50000 + i * 100)  # hausse continue
    score_up = scorer.get_score()
    assert_test(f"Score haussier > 60 (got {score_up:.1f})", score_up > 60)

    # Test 3: RSI disponible après warmup
    rsi = scorer.get_rsi()
    assert_test("RSI disponible après warmup", rsi is not None)
    assert_test(f"RSI > 50 en hausse (got {rsi:.1f})", rsi > 50)

    # Test 4: ROC positif
    roc = scorer.get_roc(10)
    assert_test("ROC(10) disponible", roc is not None)
    assert_test(f"ROC(10) > 0 en hausse (got {roc:.4f}%)", roc > 0)

    # Test 5: Signal bullish
    signal = scorer.get_signal()
    assert_test(f"Signal en hausse (got {signal})", signal in ("bullish", "neutral"))

    # Test 6: Feed prix en baisse
    scorer2 = MomentumScorer(roc_periods=[5, 10, 20], rsi_period=14)
    for i in range(60):
        scorer2.on_price(50000 - i * 100)  # baisse continue
    score_down = scorer2.get_score()
    assert_test(f"Score baissier < 40 (got {score_down:.1f})", score_down < 40)

    # Test 7: Signal bearish
    signal_down = scorer2.get_signal()
    assert_test(f"Signal en baisse (got {signal_down})", signal_down in ("bearish", "neutral"))

    # Test 8: Status complet
    status = scorer.get_status()
    assert_test("Status has score", "score" in status)
    assert_test("Status has rsi", "rsi" in status)
    assert_test("Status has rocs", "rocs" in status)
    assert_test("Status warmed_up", status["warmed_up"])

    # Test 9: Reset
    scorer.reset()
    assert_test("Reset: score = 50", scorer.get_score() == 50.0)
    assert_test("Reset: tick_count = 0", scorer._tick_count == 0)

    # Test 10: Thread safety
    import concurrent.futures
    ts_scorer = MomentumScorer()

    def feed_prices(n):
        random.seed()
        for _ in range(n):
            ts_scorer.on_price(50000 + random.gauss(0, 100))
        return n

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(feed_prices, 250) for _ in range(4)]
        [f.result() for f in futures]
    assert_test("Thread safety: 1000 ticks", ts_scorer._tick_count == 1000)

    print(f"\n{'=' * 50}")
    print(f"Résultat: {passed}/{passed + failed} tests passés")
    sys.exit(0 if failed == 0 else 1)
