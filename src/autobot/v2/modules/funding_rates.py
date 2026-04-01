"""
Funding Rates Monitor — Surveillance temps réel des funding rates Kraken.

Module AutoBot V2. Surveille les funding rates des contrats perpétuels
et déclenche une pause automatique si le taux dépasse un seuil extrême :
  - |rate| >= extreme_threshold (défaut ±0.1%) → PAUSE automatique
  - |rate| < extreme_threshold → OK, trading autorisé

Les funding rates sur Kraken sont typiquement entre -0.01% et +0.01%
(8h). Un taux > 0.1% signale un déséquilibre extrême du marché
(sur-levier massif), dangereux pour le Grid trading.

Calcul O(1) par update, thread-safe (RLock).

Usage:
    from autobot.v2.modules.funding_rates import FundingRatesMonitor

    monitor = FundingRatesMonitor(extreme_threshold=0.1)

    # À chaque réception du funding rate (WebSocket ou polling)
    should_continue = monitor.update(rate=0.05)  # True = OK

    if monitor.is_extreme():
        ...  # pause le Grid

    status = monitor.get_status()
"""

from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)


class FundingRatesMonitor:
    """
    Moniteur de funding rates pour contrats perpétuels Kraken.

    Déclenche une pause automatique du trading lorsque le funding rate
    dépasse le seuil extrême configuré (en valeur absolue).

    Le seuil est exprimé en pourcentage (ex: 0.1 = 0.1%).
    Le rate reçu dans update() est aussi en pourcentage.

    Args:
        extreme_threshold: Seuil en % au-delà duquel le rate est
            considéré extrême (défaut 0.1 = ±0.1%).
        cooldown_updates: Nombre d'updates consécutifs sous le seuil
            nécessaires pour sortir de l'état PAUSE (défaut 3).
            Évite les oscillations rapides PAUSE/OK.

    Thread-safe: Oui (RLock interne).
    Complexité: O(1) par appel à update().
    """

    def __init__(
        self,
        extreme_threshold: float = 0.1,
        cooldown_updates: int = 3,
    ) -> None:
        if not isinstance(extreme_threshold, (int, float)) or extreme_threshold <= 0:
            raise ValueError(
                f"extreme_threshold doit être un nombre > 0, reçu {extreme_threshold}"
            )
        if not isinstance(cooldown_updates, int) or cooldown_updates < 1:
            raise ValueError(
                f"cooldown_updates doit être un entier >= 1, reçu {cooldown_updates}"
            )

        self._threshold: float = float(extreme_threshold)
        self._cooldown_updates: int = cooldown_updates
        self._lock: threading.RLock = threading.RLock()

        # État courant
        self._current_rate: float | None = None
        self._is_extreme: bool = False
        self._consecutive_ok: int = 0
        self._update_count: int = 0
        self._last_update_ts: float | None = None

        # Historique simplifié (pas de buffer, O(1))
        self._max_rate: float | None = None
        self._min_rate: float | None = None
        self._extreme_count: int = 0  # Nombre total de passages en zone extrême

        # Cache pour log conditionnel
        self._last_logged_state: bool | None = None

        logger.info(
            "FundingRatesMonitor initialisé — seuil=±%.4f%%, cooldown=%d updates",
            extreme_threshold, cooldown_updates,
        )

    # ------------------------------------------------------------------
    # Propriétés
    # ------------------------------------------------------------------

    @property
    def extreme_threshold(self) -> float:
        """Seuil extrême en % (valeur absolue)."""
        return self._threshold

    @property
    def cooldown_updates(self) -> int:
        """Nombre d'updates OK consécutifs pour sortir de PAUSE."""
        return self._cooldown_updates

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def update(self, rate: float) -> bool:
        """
        Met à jour avec un nouveau funding rate.

        Args:
            rate: Funding rate en pourcentage (ex: 0.05 pour 0.05%,
                  -0.02 pour -0.02%).

        Returns:
            True si le trading est autorisé (rate non extrême),
            False si le rate est extrême (trading doit être pausé).

        Thread-safe: Oui (RLock interne).
        Complexité: O(1).
        """
        if not isinstance(rate, (int, float)):
            raise ValueError(f"rate doit être numérique, reçu {type(rate).__name__}")

        with self._lock:
            self._current_rate = float(rate)
            self._update_count += 1
            self._last_update_ts = time.time()

            # Mise à jour min/max — O(1)
            if self._max_rate is None or rate > self._max_rate:
                self._max_rate = rate
            if self._min_rate is None or rate < self._min_rate:
                self._min_rate = rate

            # Évaluation du seuil
            rate_abs = abs(rate)
            is_currently_extreme = rate_abs >= self._threshold

            if is_currently_extreme:
                # Rate extrême → PAUSE immédiate
                if not self._is_extreme:
                    self._extreme_count += 1
                self._is_extreme = True
                self._consecutive_ok = 0
            else:
                # Rate normal
                if self._is_extreme:
                    # En état PAUSE → incrémenter le compteur cooldown
                    self._consecutive_ok += 1
                    if self._consecutive_ok >= self._cooldown_updates:
                        # Cooldown écoulé → sortir de PAUSE
                        self._is_extreme = False
                        self._consecutive_ok = 0
                # else: déjà OK, rien à faire

            self._log_state()

            return not self._is_extreme

    def is_extreme(self) -> bool:
        """
        Indique si le funding rate actuel est en zone extrême.

        Returns:
            True si extrême (trading doit être en pause),
            False sinon.

        Thread-safe: Oui (RLock interne).
        """
        with self._lock:
            return self._is_extreme

    def get_status(self) -> dict:
        """
        Retourne l'état complet du moniteur pour le dashboard.

        Returns:
            Dictionnaire contenant :
            - ``current_rate``: Dernier funding rate reçu (ou None)
            - ``is_extreme``: bool, True si en zone extrême
            - ``trading_allowed``: bool, inverse de is_extreme
            - ``threshold``: Seuil configuré en %
            - ``update_count``: Nombre total d'updates reçus
            - ``max_rate``: Rate max observé (ou None)
            - ``min_rate``: Rate min observé (ou None)
            - ``extreme_count``: Nombre de passages en zone extrême
            - ``consecutive_ok``: Updates OK consécutifs (pendant cooldown)
            - ``cooldown_updates``: Seuil de cooldown configuré
            - ``cooldown_remaining``: Updates restants avant sortie de PAUSE
            - ``last_update_ts``: Timestamp du dernier update (ou None)

        Thread-safe: Oui (RLock interne).
        """
        with self._lock:
            cooldown_remaining = 0
            if self._is_extreme:
                cooldown_remaining = max(
                    0, self._cooldown_updates - self._consecutive_ok
                )

            return {
                "current_rate": (
                    round(self._current_rate, 6)
                    if self._current_rate is not None
                    else None
                ),
                "is_extreme": self._is_extreme,
                "trading_allowed": not self._is_extreme,
                "threshold": self._threshold,
                "update_count": self._update_count,
                "max_rate": (
                    round(self._max_rate, 6)
                    if self._max_rate is not None
                    else None
                ),
                "min_rate": (
                    round(self._min_rate, 6)
                    if self._min_rate is not None
                    else None
                ),
                "extreme_count": self._extreme_count,
                "consecutive_ok": self._consecutive_ok,
                "cooldown_updates": self._cooldown_updates,
                "cooldown_remaining": cooldown_remaining,
                "last_update_ts": self._last_update_ts,
            }

    def reset(self) -> None:
        """
        Réinitialise le moniteur (utile pour changement de marché ou test).

        Thread-safe: Oui (RLock interne).
        """
        with self._lock:
            self._current_rate = None
            self._is_extreme = False
            self._consecutive_ok = 0
            self._update_count = 0
            self._last_update_ts = None
            self._max_rate = None
            self._min_rate = None
            self._extreme_count = 0
            self._last_logged_state = None
            logger.info("FundingRatesMonitor: réinitialisé")

    # ------------------------------------------------------------------
    # Méthodes privées
    # ------------------------------------------------------------------

    def _log_state(self) -> None:
        """
        Logue l'état courant du moniteur.

        Format: "Funding: X.XX% → PAUSE/OK"
        Ne logue que lors d'un changement d'état pour éviter le spam.
        """
        current_state = self._is_extreme

        if current_state == self._last_logged_state:
            return
        self._last_logged_state = current_state

        rate_str = (
            f"{self._current_rate:+.4f}%"
            if self._current_rate is not None
            else "N/A"
        )
        action = "PAUSE" if current_state else "OK"

        logger.info("Funding: %s → %s", rate_str, action)


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
    assert_raises("threshold=0", ValueError, FundingRatesMonitor, extreme_threshold=0)
    assert_raises("threshold=-1", ValueError, FundingRatesMonitor, extreme_threshold=-1)
    assert_raises("threshold='a'", ValueError, FundingRatesMonitor, extreme_threshold="a")
    assert_raises("cooldown=0", ValueError, FundingRatesMonitor, cooldown_updates=0)
    assert_raises("cooldown=-1", ValueError, FundingRatesMonitor, cooldown_updates=-1)
    assert_raises("cooldown=1.5", ValueError, FundingRatesMonitor, cooldown_updates=1.5)

    m = FundingRatesMonitor(extreme_threshold=0.15, cooldown_updates=5)
    assert_eq("threshold", m.extreme_threshold, 0.15)
    assert_eq("cooldown", m.cooldown_updates, 5)

    m_def = FundingRatesMonitor()
    assert_eq("default threshold", m_def.extreme_threshold, 0.1)
    assert_eq("default cooldown", m_def.cooldown_updates, 3)

    # =================================================================
    # Test 2 : Rate normal → True (trading OK)
    # =================================================================
    print("\n=== Test 2 : Rate normal → True ===")
    m2 = FundingRatesMonitor(extreme_threshold=0.1)

    assert_eq("0.01% → True", m2.update(0.01), True)
    assert_eq("is_extreme False", m2.is_extreme(), False)
    assert_eq("-0.05% → True", m2.update(-0.05), True)
    assert_eq("0.0% → True", m2.update(0.0), True)
    assert_eq("0.099% → True", m2.update(0.099), True)

    # =================================================================
    # Test 3 : Rate extrême → False (PAUSE)
    # =================================================================
    print("\n=== Test 3 : Rate extrême → False ===")
    m3 = FundingRatesMonitor(extreme_threshold=0.1)
    assert_eq("0.1% (= seuil) → False", m3.update(0.1), False)
    assert_eq("is_extreme True", m3.is_extreme(), True)

    m3b = FundingRatesMonitor(extreme_threshold=0.1)
    assert_eq("0.15% → False", m3b.update(0.15), False)

    m3c = FundingRatesMonitor(extreme_threshold=0.1)
    assert_eq("-0.12% → False", m3c.update(-0.12), False)
    assert_eq("is_extreme True (négatif)", m3c.is_extreme(), True)

    # =================================================================
    # Test 4 : Cooldown — ne sort pas de PAUSE immédiatement
    # =================================================================
    print("\n=== Test 4 : Cooldown ===")
    m4 = FundingRatesMonitor(extreme_threshold=0.1, cooldown_updates=3)

    m4.update(0.2)  # → PAUSE
    assert_eq("en PAUSE", m4.is_extreme(), True)

    # 1er update normal — toujours en PAUSE (cooldown = 3)
    assert_eq("cooldown 1/3 → False", m4.update(0.01), False)
    assert_eq("still extreme", m4.is_extreme(), True)
    s = m4.get_status()
    assert_eq("consecutive_ok=1", s["consecutive_ok"], 1)
    assert_eq("cooldown_remaining=2", s["cooldown_remaining"], 2)

    # 2e update normal
    assert_eq("cooldown 2/3 → False", m4.update(0.01), False)
    assert_eq("still extreme", m4.is_extreme(), True)

    # 3e update normal — cooldown atteint → sortie de PAUSE
    assert_eq("cooldown 3/3 → True", m4.update(0.01), True)
    assert_eq("not extreme anymore", m4.is_extreme(), False)

    # =================================================================
    # Test 5 : Cooldown reset si nouveau spike
    # =================================================================
    print("\n=== Test 5 : Cooldown reset par spike ===")
    m5 = FundingRatesMonitor(extreme_threshold=0.1, cooldown_updates=3)

    m5.update(0.2)   # → PAUSE
    m5.update(0.01)  # cooldown 1/3
    m5.update(0.01)  # cooldown 2/3
    # Nouveau spike au lieu du 3e OK
    assert_eq("re-spike → False", m5.update(0.15), False)
    s = m5.get_status()
    assert_eq("consecutive_ok reset", s["consecutive_ok"], 0)
    assert_eq("cooldown_remaining=3", s["cooldown_remaining"], 3)

    # =================================================================
    # Test 6 : get_status — structure complète
    # =================================================================
    print("\n=== Test 6 : get_status — structure ===")
    m6 = FundingRatesMonitor(extreme_threshold=0.05, cooldown_updates=2)
    m6.update(0.01)
    m6.update(-0.03)
    s = m6.get_status()

    required_keys = [
        "current_rate", "is_extreme", "trading_allowed", "threshold",
        "update_count", "max_rate", "min_rate", "extreme_count",
        "consecutive_ok", "cooldown_updates", "cooldown_remaining",
        "last_update_ts",
    ]
    for key in required_keys:
        assert_true(f"clé '{key}' présente", key in s)

    assert_eq("current_rate", s["current_rate"], -0.03, 0.001)
    assert_eq("is_extreme", s["is_extreme"], False)
    assert_eq("trading_allowed", s["trading_allowed"], True)
    assert_eq("threshold", s["threshold"], 0.05)
    assert_eq("update_count", s["update_count"], 2)
    assert_eq("max_rate", s["max_rate"], 0.01, 0.001)
    assert_eq("min_rate", s["min_rate"], -0.03, 0.001)
    assert_eq("extreme_count", s["extreme_count"], 0)
    assert_true("last_update_ts not None", s["last_update_ts"] is not None)

    # =================================================================
    # Test 7 : extreme_count — comptage correct
    # =================================================================
    print("\n=== Test 7 : extreme_count ===")
    m7 = FundingRatesMonitor(extreme_threshold=0.1, cooldown_updates=1)

    m7.update(0.01)   # OK
    m7.update(0.2)    # → PAUSE (extreme_count=1)
    m7.update(0.01)   # cooldown 1/1 → OK
    m7.update(0.3)    # → PAUSE (extreme_count=2)
    m7.update(0.5)    # encore extrême, mais déjà en PAUSE (pas de ré-incrémentation)
    m7.update(0.01)   # cooldown 1/1 → OK
    m7.update(-0.15)  # → PAUSE (extreme_count=3)

    s = m7.get_status()
    assert_eq("extreme_count=3", s["extreme_count"], 3)

    # =================================================================
    # Test 8 : reset
    # =================================================================
    print("\n=== Test 8 : reset ===")
    m8 = FundingRatesMonitor(extreme_threshold=0.1)
    m8.update(0.2)
    m8.update(0.01)

    m8.reset()
    s = m8.get_status()
    assert_eq("reset current_rate", s["current_rate"], None)
    assert_eq("reset is_extreme", s["is_extreme"], False)
    assert_eq("reset update_count", s["update_count"], 0)
    assert_eq("reset max_rate", s["max_rate"], None)
    assert_eq("reset min_rate", s["min_rate"], None)
    assert_eq("reset extreme_count", s["extreme_count"], 0)
    assert_eq("reset consecutive_ok", s["consecutive_ok"], 0)

    # =================================================================
    # Test 9 : Validation entrées update()
    # =================================================================
    print("\n=== Test 9 : Validation entrées ===")
    m9 = FundingRatesMonitor()
    assert_raises("rate='abc'", ValueError, m9.update, "abc")
    assert_raises("rate=None", ValueError, m9.update, None)
    assert_raises("rate=[1]", ValueError, m9.update, [1])

    # int accepté (converti en float)
    assert_eq("rate=0 (int) → True", m9.update(0), True)

    # =================================================================
    # Test 10 : Thread-safety — 200 appels concurrents
    # =================================================================
    print("\n=== Test 10 : Thread-safety ===")
    m_mt = FundingRatesMonitor(extreme_threshold=0.1, cooldown_updates=2)
    errors = []

    def thread_task(i):
        try:
            rate = 0.01 * (i % 20) - 0.1  # range -0.1 à +0.09
            m_mt.update(rate)
            m_mt.is_extreme()
            m_mt.get_status()
            return True
        except Exception as exc:
            errors.append(str(exc))
            return False

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(thread_task, i) for i in range(200)]
        results = [f.result() for f in futures]

    assert_true(
        f"200 appels concurrents sans erreur (errors={len(errors)})",
        len(errors) == 0 and all(results),
    )

    # =================================================================
    # Test 11 : Cooldown avec cooldown_updates=1 (sortie rapide)
    # =================================================================
    print("\n=== Test 11 : Cooldown rapide (cooldown=1) ===")
    m11 = FundingRatesMonitor(extreme_threshold=0.1, cooldown_updates=1)

    m11.update(0.2)  # → PAUSE
    assert_eq("PAUSE", m11.is_extreme(), True)
    # Un seul update OK suffit
    assert_eq("1 OK → sortie", m11.update(0.01), True)
    assert_eq("not extreme", m11.is_extreme(), False)

    # =================================================================
    # Test 12 : Min/max tracking
    # =================================================================
    print("\n=== Test 12 : Min/max tracking ===")
    m12 = FundingRatesMonitor(extreme_threshold=1.0)  # seuil haut pour pas trigger

    m12.update(0.05)
    m12.update(-0.03)
    m12.update(0.08)
    m12.update(-0.01)
    m12.update(0.02)

    s = m12.get_status()
    assert_eq("max_rate=0.08", s["max_rate"], 0.08, 0.001)
    assert_eq("min_rate=-0.03", s["min_rate"], -0.03, 0.001)

    # =================================================================
    # Test 13 : Scénario réaliste — séquence de funding rates
    # =================================================================
    print("\n=== Test 13 : Scénario réaliste ===")
    m13 = FundingRatesMonitor(extreme_threshold=0.1, cooldown_updates=3)

    # Rates normaux (toutes les 8h sur Kraken)
    rates_normaux = [0.01, 0.015, -0.005, 0.02, 0.008, -0.01]
    for r in rates_normaux:
        assert_eq(f"normal {r}% → True", m13.update(r), True)

    # Spike extrême
    assert_eq("spike 0.25% → False", m13.update(0.25), False)
    assert_eq("is_extreme", m13.is_extreme(), True)

    # Cooldown progressif
    assert_eq("cool 1/3", m13.update(0.05), False)
    assert_eq("cool 2/3", m13.update(0.03), False)
    assert_eq("cool 3/3 → OK", m13.update(0.01), True)

    # Retour à la normale
    assert_eq("retour normal", m13.update(0.008), True)
    assert_eq("pas extreme", m13.is_extreme(), False)

    s = m13.get_status()
    assert_eq("total updates", s["update_count"], 11)
    assert_eq("extreme_count=1", s["extreme_count"], 1)

    # =================================================================
    # Test 14 : Log format — vérification via handler capturant
    # =================================================================
    print("\n=== Test 14 : Log format ===")

    class LogCapture(logging.Handler):
        def __init__(self):
            super().__init__()
            self.records = []
        def emit(self, record):
            self.records.append(self.format(record))

    cap = LogCapture()
    cap.setFormatter(logging.Formatter("%(message)s"))
    test_logger = logging.getLogger("autobot.v2.modules.funding_rates")
    test_logger.addHandler(cap)

    m14 = FundingRatesMonitor(extreme_threshold=0.1)
    cap.records.clear()  # Clear init log

    m14.update(0.15)  # → PAUSE — should log
    found_pause = any("PAUSE" in r and "Funding:" in r for r in cap.records)
    assert_true("log contient 'Funding: ... → PAUSE'", found_pause)

    cap.records.clear()
    m14.update(0.2)  # encore extrême — NE devrait PAS re-loguer (même état)
    assert_eq("pas de re-log si même état", len(cap.records), 0)

    test_logger.removeHandler(cap)

    # =================================================================
    # Test 15 : État initial avant tout update
    # =================================================================
    print("\n=== Test 15 : État initial ===")
    m15 = FundingRatesMonitor()
    s = m15.get_status()
    assert_eq("initial current_rate", s["current_rate"], None)
    assert_eq("initial is_extreme", s["is_extreme"], False)
    assert_eq("initial trading_allowed", s["trading_allowed"], True)
    assert_eq("initial update_count", s["update_count"], 0)
    assert_eq("initial max_rate", s["max_rate"], None)
    assert_eq("initial min_rate", s["min_rate"], None)
    assert_eq("initial extreme_count", s["extreme_count"], 0)
    assert_eq("initial cooldown_remaining", s["cooldown_remaining"], 0)
    assert_eq("initial last_update_ts", s["last_update_ts"], None)

    # ----- Résumé -----
    print(f"\n{'='*60}")
    print(f"RÉSULTATS : {passed}/{total} passés, {failed} échecs")
    print(f"{'='*60}")

    sys.exit(0 if failed == 0 else 1)
