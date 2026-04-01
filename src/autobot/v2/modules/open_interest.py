"""
Open Interest Monitor — Détection de squeeze potentiel via OI et prix.

Module Phase 1 d'AutoBot V2. Surveille l'Open Interest et le prix pour
détecter une surchauffe du marché pouvant mener à un squeeze :
  - OI spike > 50% par rapport à la moyenne + prix flat (< 2% change)
    → SQUEEZE RISK détecté, trading dangereux

Un squeeze se produit typiquement quand l'OI grimpe brutalement
(accumulation massive de positions) pendant que le prix stagne
(compression). La résolution violente (liquidations en cascade)
crée un mouvement de prix extrême dans une direction.

Historique maintenu dans une deque à maxlen 100 pour calcul
des moyennes glissantes. Opérations O(1) par update.

Usage:
    from autobot.v2.modules.open_interest import OpenInterestMonitor

    monitor = OpenInterestMonitor()

    # À chaque réception de données OI + prix
    should_continue = monitor.update(oi=150_000_000, price=65000.0)

    if monitor.is_squeeze_risk():
        ...  # pause ou réduction de l'exposition

    status = monitor.get_status()
"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections import deque

logger = logging.getLogger("autobot.v2.modules.open_interest")


class OpenInterestMonitor:
    """
    Moniteur d'Open Interest pour détection de squeeze potentiel.

    Détecte les situations à risque de squeeze en comparant l'OI courant
    à la moyenne glissante et en vérifiant que le prix reste flat.

    Conditions de squeeze risk :
      1. OI spike > oi_spike_threshold (défaut 50%) au-dessus de la moyenne
      2. Prix flat : variation < price_flat_threshold (défaut 2%) par
         rapport à la moyenne

    L'historique est borné à ``window_size`` entrées (défaut 100) via
    une deque, garantissant O(1) pour append et len.

    Args:
        oi_spike_threshold: Seuil de spike OI en ratio (0.5 = 50%).
        price_flat_threshold: Seuil de prix flat en ratio (0.02 = 2%).
        window_size: Taille de la fenêtre glissante (défaut 100).
        cooldown_updates: Updates OK consécutifs pour sortir de SQUEEZE (défaut 3).
        min_updates: Updates minimum avant activation de la détection (défaut 5).

    Thread-safe: Oui (RLock interne).
    Complexité: O(1) par appel à update().
    """

    def __init__(
        self,
        oi_spike_threshold: float = 0.5,
        price_flat_threshold: float = 0.02,
        window_size: int = 100,
        cooldown_updates: int = 3,
        min_updates: int = 5,
    ) -> None:
        if not isinstance(oi_spike_threshold, (int, float)) or oi_spike_threshold <= 0:
            raise ValueError(f"oi_spike_threshold doit être un nombre > 0, reçu {oi_spike_threshold}")
        if not isinstance(price_flat_threshold, (int, float)) or price_flat_threshold <= 0:
            raise ValueError(f"price_flat_threshold doit être un nombre > 0, reçu {price_flat_threshold}")
        if not isinstance(window_size, int) or window_size < 2:
            raise ValueError(f"window_size doit être un entier >= 2, reçu {window_size}")
        if not isinstance(cooldown_updates, int) or cooldown_updates < 1:
            raise ValueError(f"cooldown_updates doit être un entier >= 1, reçu {cooldown_updates}")
        if not isinstance(min_updates, int) or min_updates < 1:
            raise ValueError(f"min_updates doit être un entier >= 1, reçu {min_updates}")

        self._oi_spike_threshold: float = float(oi_spike_threshold)
        self._price_flat_threshold: float = float(price_flat_threshold)
        self._window_size: int = window_size
        self._cooldown_updates: int = cooldown_updates
        self._min_updates: int = min_updates
        self._lock: threading.RLock = threading.RLock()

        # Historique borné — deque avec maxlen pour O(1) amortized append
        self._oi_history: deque[float] = deque(maxlen=window_size)
        self._price_history: deque[float] = deque(maxlen=window_size)

        # Sommes glissantes pour calcul O(1) des moyennes
        self._oi_sum: float = 0.0
        self._price_sum: float = 0.0

        # État courant
        self._current_oi: float | None = None
        self._current_price: float | None = None
        self._is_squeeze_risk: bool = False
        self._consecutive_ok: int = 0
        self._update_count: int = 0
        self._last_update_ts: float | None = None

        # Statistiques
        self._squeeze_count: int = 0
        self._max_oi_spike_pct: float | None = None
        self._last_oi_spike_pct: float | None = None
        self._last_price_change_pct: float | None = None

        # Cache pour log conditionnel
        self._last_logged_state: bool | None = None

        logger.info(
            "OpenInterestMonitor initialisé — oi_spike=%.0f%%, price_flat=%.1f%%, "
            "window=%d, cooldown=%d, min_updates=%d",
            oi_spike_threshold * 100, price_flat_threshold * 100,
            window_size, cooldown_updates, min_updates,
        )

    # ------------------------------------------------------------------
    # Propriétés
    # ------------------------------------------------------------------

    @property
    def oi_spike_threshold(self) -> float:
        return self._oi_spike_threshold

    @property
    def price_flat_threshold(self) -> float:
        return self._price_flat_threshold

    @property
    def window_size(self) -> int:
        return self._window_size

    @property
    def cooldown_updates(self) -> int:
        return self._cooldown_updates

    @property
    def min_updates(self) -> int:
        return self._min_updates

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def update(self, oi: float, price: float) -> bool:
        """
        Met à jour avec un nouveau couple (Open Interest, prix).

        Args:
            oi: Open Interest courant (doit être > 0, fini).
            price: Prix courant (doit être > 0, fini).

        Returns:
            True si le trading est sûr (pas de squeeze risk),
            False si un risque de squeeze est détecté.

        Raises:
            ValueError: Si oi ou price invalide (<=0, NaN, inf, non-numérique).

        Thread-safe: Oui (RLock interne).
        Complexité: O(1).
        """
        self._validate_input(oi, "oi")
        self._validate_input(price, "price")

        oi = float(oi)
        price = float(price)

        with self._lock:
            now = time.monotonic()
            self._current_oi = oi
            self._current_price = price
            self._update_count += 1
            self._last_update_ts = now

            # Mise à jour des sommes glissantes — O(1)
            # Si la deque est pleine, l'élément éjecté doit être soustrait
            if len(self._oi_history) == self._oi_history.maxlen:
                self._oi_sum -= self._oi_history[0]
            if len(self._price_history) == self._price_history.maxlen:
                self._price_sum -= self._price_history[0]

            self._oi_history.append(oi)
            self._price_history.append(price)
            self._oi_sum += oi
            self._price_sum += price

            # Pas assez de données pour détecter
            if self._update_count < self._min_updates:
                return True

            # Calcul des moyennes — O(1) grâce aux sommes glissantes
            n = len(self._oi_history)
            oi_avg = self._oi_sum / n
            price_avg = self._price_sum / n

            # Calcul du spike OI (en ratio)
            oi_spike_pct = (oi - oi_avg) / oi_avg if oi_avg > 0 else 0.0

            # Calcul du changement de prix (en ratio, valeur absolue)
            price_change_pct = abs(price - price_avg) / price_avg if price_avg > 0 else 0.0

            self._last_oi_spike_pct = oi_spike_pct
            self._last_price_change_pct = price_change_pct

            # Mise à jour du max spike
            if self._max_oi_spike_pct is None or oi_spike_pct > self._max_oi_spike_pct:
                self._max_oi_spike_pct = oi_spike_pct

            # Détection squeeze : OI spike ET prix flat
            is_currently_squeeze = (
                oi_spike_pct > self._oi_spike_threshold
                and price_change_pct < self._price_flat_threshold
            )

            if is_currently_squeeze:
                if not self._is_squeeze_risk:
                    self._squeeze_count += 1
                self._is_squeeze_risk = True
                self._consecutive_ok = 0
            else:
                if self._is_squeeze_risk:
                    self._consecutive_ok += 1
                    if self._consecutive_ok >= self._cooldown_updates:
                        self._is_squeeze_risk = False
                        self._consecutive_ok = 0

            self._log_state(oi_spike_pct, price_change_pct)

            return not self._is_squeeze_risk

    def is_squeeze_risk(self) -> bool:
        """
        Indique si un risque de squeeze est actuellement détecté.

        Returns:
            True si squeeze risk actif, False sinon.
        Thread-safe: Oui (RLock interne).
        """
        with self._lock:
            return self._is_squeeze_risk

    def get_status(self) -> dict:
        """
        Retourne l'état complet du moniteur pour le dashboard.
        Thread-safe: Oui (RLock interne).
        """
        with self._lock:
            cooldown_remaining = 0
            if self._is_squeeze_risk:
                cooldown_remaining = max(0, self._cooldown_updates - self._consecutive_ok)

            n = len(self._oi_history)
            oi_avg = round(self._oi_sum / n, 6) if n > 0 else None
            price_avg = round(self._price_sum / n, 6) if n > 0 else None

            return {
                "current_oi": self._current_oi,
                "current_price": self._current_price,
                "is_squeeze_risk": self._is_squeeze_risk,
                "trading_allowed": not self._is_squeeze_risk,
                "oi_spike_threshold": self._oi_spike_threshold,
                "price_flat_threshold": self._price_flat_threshold,
                "update_count": self._update_count,
                "window_size": self._window_size,
                "history_length": n,
                "squeeze_count": self._squeeze_count,
                "consecutive_ok": self._consecutive_ok,
                "cooldown_updates": self._cooldown_updates,
                "cooldown_remaining": cooldown_remaining,
                "last_oi_spike_pct": (
                    round(self._last_oi_spike_pct, 6)
                    if self._last_oi_spike_pct is not None else None
                ),
                "last_price_change_pct": (
                    round(self._last_price_change_pct, 6)
                    if self._last_price_change_pct is not None else None
                ),
                "max_oi_spike_pct": (
                    round(self._max_oi_spike_pct, 6)
                    if self._max_oi_spike_pct is not None else None
                ),
                "oi_avg": oi_avg,
                "price_avg": price_avg,
                "last_update_ts": self._last_update_ts,
                "min_updates": self._min_updates,
            }

    def reset(self) -> None:
        """Réinitialise le moniteur. Thread-safe: Oui (RLock interne)."""
        with self._lock:
            self._oi_history.clear()
            self._price_history.clear()
            self._oi_sum = 0.0
            self._price_sum = 0.0
            self._current_oi = None
            self._current_price = None
            self._is_squeeze_risk = False
            self._consecutive_ok = 0
            self._update_count = 0
            self._last_update_ts = None
            self._squeeze_count = 0
            self._max_oi_spike_pct = None
            self._last_oi_spike_pct = None
            self._last_price_change_pct = None
            self._last_logged_state = None
            logger.info("OpenInterestMonitor: réinitialisé")

    # ------------------------------------------------------------------
    # Méthodes privées
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_input(value: float, name: str) -> None:
        """Valide qu'une entrée est un nombre > 0, fini, pas NaN."""
        if not isinstance(value, (int, float)):
            raise ValueError(
                f"{name} doit être numérique, reçu {type(value).__name__}: {value}"
            )
        if math.isnan(value) or math.isinf(value):
            raise ValueError(f"{name} invalide (NaN ou inf): {value}")
        if value <= 0:
            raise ValueError(f"{name} doit être > 0, reçu {value}")

    def _log_state(self, oi_spike_pct: float, price_change_pct: float) -> None:
        """
        Logue l'état courant du moniteur.
        Format: "OI: spike X% + prix flat → SQUEEZE RISK" ou "OI: OK"
        Ne logue que lors d'un changement d'état pour éviter le spam.
        """
        current_state = self._is_squeeze_risk

        if current_state == self._last_logged_state:
            return
        self._last_logged_state = current_state

        if current_state:
            logger.info(
                "OI: spike %.1f%% + prix flat → SQUEEZE RISK",
                oi_spike_pct * 100,
            )
        else:
            logger.info("OI: OK — squeeze risk dissipé")


# ======================================================================
# Tests intégrés
# ======================================================================

if __name__ == "__main__":
    import math
    import sys
    import concurrent.futures

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )

    passed = 0
    failed = 0
    total = 0

    def assert_eq(test_name, actual, expected, tolerance=1e-9):
        global passed, failed, total
        total += 1
        if isinstance(expected, float) and isinstance(actual, (int, float)):
            ok = math.isclose(actual, expected, abs_tol=tolerance)
        else:
            ok = actual == expected
        if ok:
            passed += 1
            print(f"  PASS  {test_name}: {actual}")
        else:
            failed += 1
            print(f"  FAIL  {test_name}: attendu {expected}, obtenu {actual}")

    def assert_true(test_name, condition):
        global passed, failed, total
        total += 1
        if condition:
            passed += 1
            print(f"  PASS  {test_name}")
        else:
            failed += 1
            print(f"  FAIL  {test_name}")

    def assert_raises(test_name, exc_type, fn, *a, **kw):
        global passed, failed, total
        total += 1
        try:
            fn(*a, **kw)
            failed += 1
            print(f"  FAIL  {test_name}: pas de {exc_type.__name__}")
        except exc_type:
            passed += 1
            print(f"  PASS  {test_name}: {exc_type.__name__} levée")
        except Exception as e:
            failed += 1
            print(f"  FAIL  {test_name}: attendu {exc_type.__name__}, obtenu {type(e).__name__}: {e}")

    # =================================================================
    # Test 1 : Constructeur — validation des paramètres
    # =================================================================
    print("\n=== Test 1 : Constructeur — validation ===")
    assert_raises("oi_spike=0", ValueError, OpenInterestMonitor, oi_spike_threshold=0)
    assert_raises("oi_spike=-1", ValueError, OpenInterestMonitor, oi_spike_threshold=-1)
    assert_raises("oi_spike='a'", ValueError, OpenInterestMonitor, oi_spike_threshold="a")
    assert_raises("price_flat=0", ValueError, OpenInterestMonitor, price_flat_threshold=0)
    assert_raises("price_flat=-0.5", ValueError, OpenInterestMonitor, price_flat_threshold=-0.5)
    assert_raises("window=1", ValueError, OpenInterestMonitor, window_size=1)
    assert_raises("window=1.5", ValueError, OpenInterestMonitor, window_size=1.5)
    assert_raises("cooldown=0", ValueError, OpenInterestMonitor, cooldown_updates=0)
    assert_raises("min_updates=0", ValueError, OpenInterestMonitor, min_updates=0)

    m = OpenInterestMonitor(oi_spike_threshold=0.6, price_flat_threshold=0.03, window_size=50)
    assert_eq("oi_spike_threshold", m.oi_spike_threshold, 0.6)
    assert_eq("price_flat_threshold", m.price_flat_threshold, 0.03)
    assert_eq("window_size", m.window_size, 50)

    m_def = OpenInterestMonitor()
    assert_eq("default oi_spike", m_def.oi_spike_threshold, 0.5)
    assert_eq("default price_flat", m_def.price_flat_threshold, 0.02)
    assert_eq("default window", m_def.window_size, 100)
    assert_eq("default cooldown", m_def.cooldown_updates, 3)
    assert_eq("default min_updates", m_def.min_updates, 5)

    # =================================================================
    # Test 2 : Données normales → True (trading OK)
    # =================================================================
    print("\n=== Test 2 : Données normales → True ===")
    m2 = OpenInterestMonitor(min_updates=3)

    # Données stables — OI et prix constants
    for i in range(10):
        result = m2.update(100_000.0, 65000.0)
    assert_eq("stable data → True", result, True)
    assert_eq("is_squeeze_risk False", m2.is_squeeze_risk(), False)

    # =================================================================
    # Test 3 : Validation entrées update()
    # =================================================================
    print("\n=== Test 3 : Validation entrées ===")
    m3 = OpenInterestMonitor()
    assert_raises("oi=0", ValueError, m3.update, 0, 100.0)
    assert_raises("oi=-1", ValueError, m3.update, -1, 100.0)
    assert_raises("oi=NaN", ValueError, m3.update, float("nan"), 100.0)
    assert_raises("oi=inf", ValueError, m3.update, float("inf"), 100.0)
    assert_raises("oi='abc'", ValueError, m3.update, "abc", 100.0)
    assert_raises("oi=None", ValueError, m3.update, None, 100.0)
    assert_raises("price=0", ValueError, m3.update, 100.0, 0)
    assert_raises("price=-1", ValueError, m3.update, 100.0, -1)
    assert_raises("price=NaN", ValueError, m3.update, 100.0, float("nan"))
    assert_raises("price=inf", ValueError, m3.update, 100.0, float("inf"))
    assert_raises("price='abc'", ValueError, m3.update, 100.0, "abc")

    # int accepté (converti en float)
    assert_eq("int values OK", m3.update(100, 50), True)

    # =================================================================
    # Test 4 : Détection squeeze — OI spike + prix flat
    # =================================================================
    print("\n=== Test 4 : Détection squeeze ===")
    m4 = OpenInterestMonitor(
        oi_spike_threshold=0.5,
        price_flat_threshold=0.02,
        min_updates=5,
        cooldown_updates=3,
    )

    # 5 updates stables pour atteindre min_updates
    for _ in range(5):
        m4.update(100_000.0, 65000.0)
    assert_eq("avant spike → True", m4.is_squeeze_risk(), False)

    # OI spike massif (+100% au-dessus de la moyenne) + prix flat
    # Avec 5 entrées à 100k, moyenne = 100k. On injecte 200k.
    # Mais la moyenne inclut la nouvelle valeur, donc:
    # Après 6 updates: moyenne = (5*100k + 200k) / 6 = 133.3k
    # spike = (200k - 133.3k) / 133.3k = 50% — pile sur le seuil (>0.5 pas atteint)
    # On doit pousser plus fort
    result = m4.update(300_000.0, 65000.0)  # spike = (300k - 133.3k) / 133.3k = ~80%
    # Avec 6 entrées: moyenne = (5*100k + 300k) / 6 = 133.3k
    # Spike = (300k - 133.3k) / 133.3k = 125% > 50% ✓
    # Prix change = |65000 - 65000| / 65000 = 0% < 2% ✓
    assert_eq("OI spike + prix flat → False (squeeze)", result, False)
    assert_eq("is_squeeze_risk True", m4.is_squeeze_risk(), True)

    # =================================================================
    # Test 5 : Pas de squeeze si prix bouge
    # =================================================================
    print("\n=== Test 5 : OI spike mais prix bouge → pas de squeeze ===")
    m5 = OpenInterestMonitor(
        oi_spike_threshold=0.5,
        price_flat_threshold=0.02,
        min_updates=5,
        cooldown_updates=1,
    )

    for _ in range(5):
        m5.update(100_000.0, 65000.0)

    # OI spike + prix qui bouge beaucoup (> 2%)
    # OI spike = (300k - avg) / avg, suffisant
    # Prix change = |70000 - avg_price| / avg_price
    # avg_price = (5*65000 + 70000) / 6 = 65833
    # change = |70000 - 65833| / 65833 = 6.3% > 2% → pas de squeeze
    result = m5.update(300_000.0, 70000.0)
    assert_eq("OI spike + prix bouge → True (pas squeeze)", result, True)
    assert_eq("pas de squeeze risk", m5.is_squeeze_risk(), False)

    # =================================================================
    # Test 6 : Pas de squeeze si OI pas assez haut
    # =================================================================
    print("\n=== Test 6 : OI pas assez haut → pas de squeeze ===")
    m6 = OpenInterestMonitor(
        oi_spike_threshold=0.5,
        price_flat_threshold=0.02,
        min_updates=5,
        cooldown_updates=1,
    )

    for _ in range(5):
        m6.update(100_000.0, 65000.0)

    # OI légèrement au-dessus (110k) — pas assez pour spike
    # avg_oi = (5*100k + 110k) / 6 = 101.67k
    # spike = (110k - 101.67k) / 101.67k = 8.2% < 50%
    result = m6.update(110_000.0, 65000.0)
    assert_eq("OI petit spike → True", result, True)
    assert_eq("pas de squeeze risk", m6.is_squeeze_risk(), False)

    # =================================================================
    # Test 7 : Cooldown — ne sort pas de SQUEEZE immédiatement
    # =================================================================
    print("\n=== Test 7 : Cooldown ===")
    m7 = OpenInterestMonitor(
        oi_spike_threshold=0.5,
        price_flat_threshold=0.02,
        min_updates=3,
        cooldown_updates=3,
    )

    # 3 updates stables
    for _ in range(3):
        m7.update(100_000.0, 65000.0)

    # Déclencher squeeze
    m7.update(500_000.0, 65000.0)
    assert_eq("squeeze déclenché", m7.is_squeeze_risk(), True)

    # 1er update normal — toujours en squeeze (cooldown = 3)
    m7.update(100_000.0, 65000.0)
    assert_eq("cooldown 1/3 → still risk", m7.is_squeeze_risk(), True)
    s = m7.get_status()
    assert_eq("consecutive_ok=1", s["consecutive_ok"], 1)
    assert_eq("cooldown_remaining=2", s["cooldown_remaining"], 2)

    # 2e update normal
    m7.update(100_000.0, 65000.0)
    assert_eq("cooldown 2/3 → still risk", m7.is_squeeze_risk(), True)

    # 3e update normal → sortie
    result = m7.update(100_000.0, 65000.0)
    assert_eq("cooldown 3/3 → True (sortie)", result, True)
    assert_eq("not squeeze_risk anymore", m7.is_squeeze_risk(), False)

    # =================================================================
    # Test 8 : Cooldown reset si nouveau squeeze
    # =================================================================
    print("\n=== Test 8 : Cooldown reset par squeeze ===")
    m8 = OpenInterestMonitor(
        oi_spike_threshold=0.3,
        price_flat_threshold=0.05,
        min_updates=3,
        cooldown_updates=3,
        window_size=5,
    )

    for _ in range(3):
        m8.update(100_000.0, 65000.0)

    # Déclencher squeeze
    m8.update(500_000.0, 65000.0)
    assert_eq("squeeze déclenché", m8.is_squeeze_risk(), True)

    # 2 updates normaux (cooldown 2/3)
    m8.update(100_000.0, 65000.0)
    m8.update(100_000.0, 65000.0)
    s = m8.get_status()
    assert_eq("consecutive_ok=2", s["consecutive_ok"], 2)

    # Nouveau spike au lieu du 3e OK
    m8.update(900_000.0, 65000.0)
    s = m8.get_status()
    assert_eq("consecutive_ok reset", s["consecutive_ok"], 0)
    assert_eq("cooldown_remaining=3", s["cooldown_remaining"], 3)
    assert_eq("still squeeze", m8.is_squeeze_risk(), True)

    # =================================================================
    # Test 9 : min_updates — pas de détection avant seuil
    # =================================================================
    print("\n=== Test 9 : min_updates ===")
    m9 = OpenInterestMonitor(
        oi_spike_threshold=0.5,
        price_flat_threshold=0.02,
        min_updates=5,
    )

    # Même avec des données extrêmes, pas de squeeze avant min_updates
    for i in range(4):
        result = m9.update(100_000.0 * (i + 1), 65000.0)
        assert_eq(f"update {i+1}/4 avant min → True", result, True)
    assert_eq("pas de squeeze avant min_updates", m9.is_squeeze_risk(), False)

    # =================================================================
    # Test 10 : get_status — structure complète
    # =================================================================
    print("\n=== Test 10 : get_status — structure ===")
    m10 = OpenInterestMonitor(
        oi_spike_threshold=0.5,
        price_flat_threshold=0.02,
        window_size=50,
        cooldown_updates=2,
        min_updates=3,
    )
    m10.update(100_000.0, 65000.0)
    m10.update(105_000.0, 65100.0)
    s = m10.get_status()

    required_keys = [
        "current_oi", "current_price", "is_squeeze_risk", "trading_allowed",
        "oi_spike_threshold", "price_flat_threshold", "update_count",
        "window_size", "history_length", "squeeze_count", "consecutive_ok",
        "cooldown_updates", "cooldown_remaining", "last_oi_spike_pct",
        "last_price_change_pct", "max_oi_spike_pct", "oi_avg", "price_avg",
        "last_update_ts", "min_updates",
    ]
    for key in required_keys:
        assert_true(f"clé '{key}' présente", key in s)

    assert_eq("current_oi", s["current_oi"], 105_000.0)
    assert_eq("current_price", s["current_price"], 65100.0)
    assert_eq("update_count=2", s["update_count"], 2)
    assert_eq("history_length=2", s["history_length"], 2)
    assert_eq("is_squeeze_risk=False", s["is_squeeze_risk"], False)
    assert_eq("trading_allowed=True", s["trading_allowed"], True)
    assert_eq("squeeze_count=0", s["squeeze_count"], 0)
    assert_true("oi_avg not None", s["oi_avg"] is not None)
    assert_true("price_avg not None", s["price_avg"] is not None)
    assert_true("last_update_ts not None", s["last_update_ts"] is not None)

    # =================================================================
    # Test 11 : reset() remet tout à zéro
    # =================================================================
    print("\n=== Test 11 : reset() ===")
    m11 = OpenInterestMonitor(min_updates=3, cooldown_updates=1)
    for _ in range(5):
        m11.update(100_000.0, 65000.0)
    m11.update(500_000.0, 65000.0)
    assert_eq("avant reset → squeeze", m11.is_squeeze_risk(), True)

    m11.reset()
    s = m11.get_status()
    assert_eq("après reset → no squeeze", m11.is_squeeze_risk(), False)
    assert_eq("update_count=0", s["update_count"], 0)
    assert_eq("current_oi=None", s["current_oi"], None)
    assert_eq("current_price=None", s["current_price"], None)
    assert_eq("squeeze_count=0", s["squeeze_count"], 0)
    assert_eq("history_length=0", s["history_length"], 0)

    # =================================================================
    # Test 12 : Fenêtre glissante — window overflow
    # =================================================================
    print("\n=== Test 12 : Window overflow ===")
    m12 = OpenInterestMonitor(
        oi_spike_threshold=0.5,
        price_flat_threshold=0.02,
        min_updates=3,
        window_size=5,
        cooldown_updates=1,
    )

    # Remplir la fenêtre avec 5 updates
    for _ in range(5):
        m12.update(100_000.0, 65000.0)

    # 6e update : le 1er est éjecté, fenêtre reste à 5
    m12.update(100_000.0, 65000.0)
    s = m12.get_status()
    assert_eq("history_length=5 (maxlen)", s["history_length"], 5)
    assert_eq("update_count=6", s["update_count"], 6)

    # =================================================================
    # Test 13 : Thread safety — concurrent updates
    # =================================================================
    print("\n=== Test 13 : Thread safety ===")
    m13 = OpenInterestMonitor(min_updates=3, cooldown_updates=1)
    errors = []

    def worker(monitor, n):
        try:
            for i in range(n):
                monitor.update(100_000.0 + i, 65000.0)
                monitor.is_squeeze_risk()
                monitor.get_status()
        except Exception as e:
            errors.append(e)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(worker, m13, 50) for _ in range(4)]
        concurrent.futures.wait(futures)

    assert_eq("no thread errors", len(errors), 0)
    assert_eq("total updates=200", m13.get_status()["update_count"], 200)

    # =================================================================
    # Test 14 : squeeze_count incrémenté correctement
    # =================================================================
    print("\n=== Test 14 : squeeze_count ===")
    m14 = OpenInterestMonitor(
        oi_spike_threshold=0.5,
        price_flat_threshold=0.02,
        min_updates=3,
        cooldown_updates=1,
        window_size=10,
    )

    for _ in range(3):
        m14.update(100_000.0, 65000.0)

    # Premier squeeze
    m14.update(500_000.0, 65000.0)
    assert_eq("squeeze_count=1", m14.get_status()["squeeze_count"], 1)

    # Sortir du squeeze (cooldown=1)
    m14.update(100_000.0, 65000.0)
    assert_eq("sorti du squeeze", m14.is_squeeze_risk(), False)

    # Deuxième squeeze
    m14.update(900_000.0, 65000.0)
    assert_eq("squeeze_count=2", m14.get_status()["squeeze_count"], 2)

    # =================================================================
    # Résumé
    # =================================================================
    print(f"\n{'=' * 50}")
    print(f"RÉSULTAT: {passed}/{total} tests passés, {failed} échoués")
    print(f"{'=' * 50}")

    sys.exit(0 if failed == 0 else 1)