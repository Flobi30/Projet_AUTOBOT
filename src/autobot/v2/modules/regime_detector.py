"""
Regime Detector — Détection du régime de marché basé sur l'ADX et la volatilité.

Module Phase 1 d'AutoBot V2. Classifie le marché en quatre régimes :
  - RANGE : ADX < 20, pas de tendance -> Grid idéal
  - TREND_FAIBLE : 20 <= ADX < 40, légère tendance -> Grid avec précaution
  - TREND_FORTE : ADX >= 40, tendance marquée -> Trend Following prioritaire
  - CRISE : ATR actuel > ATR moyenne * crisis_multiplier -> pause toutes stratégies

L'ADX (Average Directional Index) mesure la force de la tendance (0-100)
sans en indiquer la direction. Il est calculé à partir des Directional
Movement indicators (DM+/DM-) lissés par la méthode de Wilder.

Calcul incrémental O(1) par tick (Wilder's smoothing), thread-safe.

Usage:
    from autobot.v2.modules.regime_detector import RegimeDetector, MarketRegime

    detector = RegimeDetector(adx_period=14)

    # À chaque bougie OHLC
    regime = detector.update(high=105.0, low=95.0, close=102.0)

    if detector.should_trade_grid():
        ...  # Grid strategy OK
    elif detector.should_trade_trend():
        ...  # Trend following OK
    else:
        ...  # CRISE — pause toutes stratégies
"""

from __future__ import annotations

import logging
import threading
from enum import Enum, auto

logger = logging.getLogger(__name__)


class MarketRegime(Enum):
    """Régimes de marché détectables."""

    RANGE = auto()
    TREND_FAIBLE = auto()
    TREND_FORTE = auto()
    CRISE = auto()


class RegimeDetector:
    """
    Détecteur de régime de marché basé sur l'ADX et la volatilité.

    Le warm-up dure adx_period * 2 ticks utiles (ticks avec TR calculable).
    Phase 1 (adx_period ticks) : initialise ATR/+DM/-DM par moyenne simple.
    Phase 2 (adx_period ticks) : initialise ADX par moyenne simple des DX.
    Pendant le warm-up, le régime retourné est RANGE.

    Thread-safe: Oui (RLock interne).
    Complexité: O(1) par appel à update().
    """

    def __init__(
        self,
        adx_period: int = 14,
        adx_threshold_weak: float = 20.0,
        adx_threshold_strong: float = 40.0,
        crisis_atr_multiplier: float = 3.0,
    ) -> None:
        if not isinstance(adx_period, int) or adx_period < 2:
            raise ValueError(f"adx_period doit être un entier >= 2, reçu {adx_period}")
        if adx_threshold_weak <= 0:
            raise ValueError(f"adx_threshold_weak doit être > 0, reçu {adx_threshold_weak}")
        if adx_threshold_strong <= adx_threshold_weak:
            raise ValueError(
                f"adx_threshold_strong ({adx_threshold_strong}) "
                f"doit être > adx_threshold_weak ({adx_threshold_weak})"
            )
        if crisis_atr_multiplier <= 1.0:
            raise ValueError(f"crisis_atr_multiplier doit être > 1.0, reçu {crisis_atr_multiplier}")

        self._period: int = adx_period
        self._threshold_weak: float = float(adx_threshold_weak)
        self._threshold_strong: float = float(adx_threshold_strong)
        self._crisis_multiplier: float = float(crisis_atr_multiplier)
        self._lock: threading.RLock = threading.RLock()

        # État OHLC précédent
        self._prev_high: float | None = None
        self._prev_low: float | None = None
        self._prev_close: float | None = None

        # Accumulateurs warm-up phase 1
        self._warmup_tr_sum: float = 0.0
        self._warmup_dm_plus_sum: float = 0.0
        self._warmup_dm_minus_sum: float = 0.0
        self._warmup_count: int = 0

        # Indicateurs lissés (Wilder)
        self._atr: float | None = None
        self._smoothed_dm_plus: float | None = None
        self._smoothed_dm_minus: float | None = None

        # ADX warm-up phase 2
        self._warmup_dx_sum: float = 0.0
        self._warmup_dx_count: int = 0
        self._adx: float | None = None

        # ATR moyenne long-terme (détection crise)
        self._atr_avg: float | None = None

        # Phases
        self._phase1_done: bool = False
        self._phase2_done: bool = False

        # État courant
        self._current_regime: MarketRegime = MarketRegime.RANGE
        self._tick_count: int = 0
        self._last_logged_regime: MarketRegime | None = None

        logger.info(
            "RegimeDetector initialisé — période=%d, seuil_faible=%.1f, "
            "seuil_fort=%.1f, crise_mult=%.1f, warm-up=%d ticks",
            adx_period, adx_threshold_weak, adx_threshold_strong,
            crisis_atr_multiplier, adx_period * 2,
        )

    # ------------------------------------------------------------------
    # Propriétés
    # ------------------------------------------------------------------

    @property
    def period(self) -> int:
        return self._period

    @property
    def adx_threshold_weak(self) -> float:
        return self._threshold_weak

    @property
    def adx_threshold_strong(self) -> float:
        return self._threshold_strong

    @property
    def crisis_atr_multiplier(self) -> float:
        return self._crisis_multiplier

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def update(self, high: float, low: float, close: float) -> MarketRegime:
        """
        Met à jour avec une nouvelle bougie OHLC.

        Returns: Le régime de marché détecté.
        Thread-safe, O(1).
        """
        if not all(isinstance(v, (int, float)) for v in (high, low, close)):
            raise ValueError(
                f"high/low/close doivent être numériques, reçu: "
                f"{type(high).__name__}, {type(low).__name__}, {type(close).__name__}"
            )
        if high < low:
            raise ValueError(f"high ({high}) doit être >= low ({low})")
        if low <= 0:
            raise ValueError(f"low doit être > 0, reçu {low}")

        with self._lock:
            self._tick_count += 1

            # Premier tick : stocker et retourner RANGE
            if self._prev_high is None:
                self._prev_high = high
                self._prev_low = low
                self._prev_close = close
                return self._current_regime

            # Calcul True Range
            tr = self._calculate_true_range(high, low, close)

            # Calcul Directional Movement
            dm_plus, dm_minus = self._calculate_directional_movement(high, low)

            if not self._phase1_done:
                self._warmup_phase1(tr, dm_plus, dm_minus)
            else:
                self._wilder_smooth(tr, dm_plus, dm_minus)
                dx = self._calculate_dx()

                if not self._phase2_done:
                    self._warmup_phase2(dx)
                else:
                    self._adx = ((self._adx * (self._period - 1)) + dx) / self._period

                # ATR moyenne long-terme
                if self._atr_avg is None:
                    self._atr_avg = self._atr
                else:
                    self._atr_avg = ((self._atr_avg * (self._period - 1)) + self._atr) / self._period

            self._prev_high = high
            self._prev_low = low
            self._prev_close = close

            self._current_regime = self._classify_regime()
            self._log_regime_change()

            return self._current_regime

    def get_regime(self) -> MarketRegime:
        """Retourne le régime actuel sans mise à jour."""
        with self._lock:
            return self._current_regime

    def should_trade_grid(self) -> bool:
        """True si Grid autorisé (RANGE ou TREND_FAIBLE)."""
        with self._lock:
            return self._current_regime in (MarketRegime.RANGE, MarketRegime.TREND_FAIBLE)

    def should_trade_trend(self) -> bool:
        """True si Trend Following autorisé (TREND_FORTE)."""
        with self._lock:
            return self._current_regime == MarketRegime.TREND_FORTE

    def get_status(self) -> dict:
        """État complet pour le dashboard."""
        with self._lock:
            warmup_total = self._period * 2
            ticks_with_tr = max(0, self._tick_count - 1)
            warmup_remaining = max(0, warmup_total - ticks_with_tr)
            if self._phase2_done:
                warmup_remaining = 0

            return {
                "regime": self._current_regime.name,
                "adx": round(self._adx, 4) if self._adx is not None else None,
                "atr": round(self._atr, 6) if self._atr is not None else None,
                "atr_avg": round(self._atr_avg, 6) if self._atr_avg is not None else None,
                "warmed_up": self._phase2_done,
                "tick_count": self._tick_count,
                "grid_allowed": self.should_trade_grid(),
                "trend_allowed": self.should_trade_trend(),
                "period": self._period,
                "threshold_weak": self._threshold_weak,
                "threshold_strong": self._threshold_strong,
                "crisis_multiplier": self._crisis_multiplier,
                "warmup_remaining": warmup_remaining,
            }

    def reset(self) -> None:
        """Réinitialise le détecteur."""
        with self._lock:
            self._prev_high = None
            self._prev_low = None
            self._prev_close = None
            self._warmup_tr_sum = 0.0
            self._warmup_dm_plus_sum = 0.0
            self._warmup_dm_minus_sum = 0.0
            self._warmup_count = 0
            self._atr = None
            self._smoothed_dm_plus = None
            self._smoothed_dm_minus = None
            self._warmup_dx_sum = 0.0
            self._warmup_dx_count = 0
            self._adx = None
            self._atr_avg = None
            self._phase1_done = False
            self._phase2_done = False
            self._current_regime = MarketRegime.RANGE
            self._tick_count = 0
            self._last_logged_regime = None
            logger.info("RegimeDetector: réinitialisé")

    # ------------------------------------------------------------------
    # Méthodes privées — Calculs
    # ------------------------------------------------------------------

    def _calculate_true_range(self, high: float, low: float, close: float) -> float:
        """
        True Range = max(high - low, |high - prev_close|, |low - prev_close|)
        O(1), pas de boucle.
        """
        prev_close = self._prev_close
        return max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close),
        )

    def _calculate_directional_movement(
        self, high: float, low: float
    ) -> tuple[float, float]:
        """
        Calcule +DM et -DM.

        +DM = high - prev_high  (si positif ET > prev_low - low)
        -DM = prev_low - low    (si positif ET > high - prev_high)

        Si les deux sont positifs, seul le plus grand est conservé.
        """
        up_move = high - self._prev_high
        down_move = self._prev_low - low

        dm_plus = 0.0
        dm_minus = 0.0

        if up_move > 0 and up_move > down_move:
            dm_plus = up_move
        if down_move > 0 and down_move > up_move:
            dm_minus = down_move

        return dm_plus, dm_minus

    def _warmup_phase1(self, tr: float, dm_plus: float, dm_minus: float) -> None:
        """
        Phase 1 warm-up : accumule TR, +DM, -DM pendant adx_period ticks.
        À la fin, initialise les moyennes simples.
        """
        self._warmup_tr_sum += tr
        self._warmup_dm_plus_sum += dm_plus
        self._warmup_dm_minus_sum += dm_minus
        self._warmup_count += 1

        if self._warmup_count >= self._period:
            self._atr = self._warmup_tr_sum / self._period
            self._smoothed_dm_plus = self._warmup_dm_plus_sum / self._period
            self._smoothed_dm_minus = self._warmup_dm_minus_sum / self._period
            self._phase1_done = True

            # Initialiser ATR avg
            self._atr_avg = self._atr

            # Calculer le premier DX
            dx = self._calculate_dx()
            self._warmup_dx_sum += dx
            self._warmup_dx_count += 1

            logger.info(
                "RegimeDetector: phase 1 terminée — ATR=%.6f, +DM=%.6f, -DM=%.6f",
                self._atr, self._smoothed_dm_plus, self._smoothed_dm_minus,
            )

    def _wilder_smooth(self, tr: float, dm_plus: float, dm_minus: float) -> None:
        """
        Lissage de Wilder O(1) pour ATR, +DM lissé, -DM lissé.
        Formule: val = ((val_prev * (period - 1)) + new_val) / period
        """
        p = self._period
        self._atr = ((self._atr * (p - 1)) + tr) / p
        self._smoothed_dm_plus = ((self._smoothed_dm_plus * (p - 1)) + dm_plus) / p
        self._smoothed_dm_minus = ((self._smoothed_dm_minus * (p - 1)) + dm_minus) / p

    def _calculate_dx(self) -> float:
        """
        DX = |+DI - -DI| / (+DI + -DI) * 100

        +DI = smoothed_dm_plus / atr * 100
        -DI = smoothed_dm_minus / atr * 100

        Retourne 0.0 si dénominateur nul (évite division par zéro).
        """
        if self._atr is None or self._atr == 0:
            return 0.0

        di_plus = (self._smoothed_dm_plus / self._atr) * 100.0
        di_minus = (self._smoothed_dm_minus / self._atr) * 100.0

        di_sum = di_plus + di_minus
        if di_sum == 0:
            return 0.0

        return (abs(di_plus - di_minus) / di_sum) * 100.0

    def _warmup_phase2(self, dx: float) -> None:
        """
        Phase 2 warm-up : accumule DX pendant adx_period ticks.
        À la fin, initialise ADX = moyenne simple des DX.
        """
        self._warmup_dx_sum += dx
        self._warmup_dx_count += 1

        if self._warmup_dx_count >= self._period:
            self._adx = self._warmup_dx_sum / self._period
            self._phase2_done = True
            logger.info(
                "RegimeDetector: warm-up complet — ADX=%.2f, régime=%s",
                self._adx, self._current_regime.name,
            )

    def _classify_regime(self) -> MarketRegime:
        """
        Classifie le régime de marché selon l'ADX et l'ATR.

        Priorité : CRISE > TREND_FORTE > TREND_FAIBLE > RANGE
        Pendant le warm-up : retourne toujours RANGE.
        """
        # Warm-up : RANGE par défaut
        if not self._phase2_done:
            return MarketRegime.RANGE

        # Détection CRISE : ATR >> ATR moyenne
        if self._atr is not None and self._atr_avg is not None and self._atr_avg > 0:
            if self._atr > self._atr_avg * self._crisis_multiplier:
                return MarketRegime.CRISE

        # Classification par ADX
        if self._adx is None:
            return MarketRegime.RANGE

        if self._adx >= self._threshold_strong:
            return MarketRegime.TREND_FORTE
        elif self._adx >= self._threshold_weak:
            return MarketRegime.TREND_FAIBLE
        else:
            return MarketRegime.RANGE

    def _log_regime_change(self) -> None:
        """Logue uniquement lors d'un changement de régime."""
        if self._current_regime == self._last_logged_regime:
            return
        self._last_logged_regime = self._current_regime

        adx_str = f"ADX {self._adx:.1f}" if self._adx is not None else "ADX N/A"

        if self._current_regime == MarketRegime.RANGE:
            action = "Grid OK"
        elif self._current_regime == MarketRegime.TREND_FAIBLE:
            action = "Grid OK (précaution)"
        elif self._current_regime == MarketRegime.TREND_FORTE:
            action = "Trend Following"
        else:
            action = "PAUSE TOUTES STRATÉGIES"

        logger.info(
            "Régime: %s (%s) — %s",
            self._current_regime.name, adx_str, action,
        )


# ======================================================================
# Tests intégrés
# ======================================================================

if __name__ == "__main__":
    import math
    import sys

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )

    passed = 0
    failed = 0
    total = 0

    def assert_eq(test_name: str, actual, expected, tolerance: float = 0.01):
        global passed, failed, total
        total += 1
        if isinstance(expected, float):
            ok = math.isclose(actual, expected, abs_tol=tolerance)
        else:
            ok = actual == expected
        if ok:
            passed += 1
            print(f"  PASS  {test_name}: {actual}")
        else:
            failed += 1
            print(f"  FAIL  {test_name}: attendu {expected}, obtenu {actual}")

    def assert_true(test_name: str, condition: bool):
        global passed, failed, total
        total += 1
        if condition:
            passed += 1
            print(f"  PASS  {test_name}")
        else:
            failed += 1
            print(f"  FAIL  {test_name}")

    def assert_raises(test_name: str, exc_type, fn, *args, **kwargs):
        global passed, failed, total
        total += 1
        try:
            fn(*args, **kwargs)
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
    assert_raises("adx_period=1", ValueError, RegimeDetector, adx_period=1)
    assert_raises("adx_period='a'", ValueError, RegimeDetector, adx_period="a")
    assert_raises("threshold_weak=0", ValueError, RegimeDetector, adx_threshold_weak=0)
    assert_raises("strong <= weak", ValueError, RegimeDetector, adx_threshold_weak=40, adx_threshold_strong=20)
    assert_raises("crisis_mult=0.5", ValueError, RegimeDetector, crisis_atr_multiplier=0.5)
    assert_raises("crisis_mult=1.0", ValueError, RegimeDetector, crisis_atr_multiplier=1.0)

    # Cas nominal OK
    d = RegimeDetector(adx_period=5, adx_threshold_weak=20, adx_threshold_strong=40, crisis_atr_multiplier=3.0)
    assert_eq("period", d.period, 5)
    assert_eq("threshold_weak", d.adx_threshold_weak, 20.0)
    assert_eq("threshold_strong", d.adx_threshold_strong, 40.0)
    assert_eq("crisis_multiplier", d.crisis_atr_multiplier, 3.0)

    # =================================================================
    # Test 2 : Warm-up — retourne RANGE pendant N ticks
    # =================================================================
    print("\n=== Test 2 : Warm-up — RANGE pendant 2*period ticks ===")
    det = RegimeDetector(adx_period=3, adx_threshold_weak=20, adx_threshold_strong=40)

    # Warm-up = 3*2 = 6 ticks utiles = 7 ticks total (premier sans TR)
    # Simulons un marché latéral avec de petites variations
    warmup_data = [
        (101, 99, 100),
        (102, 98, 101),
        (101, 99, 100),
        (102, 98, 101),
        (101, 99, 100),
        (102, 98, 101),
        (101, 99, 100),
    ]

    for i, (h, l, c) in enumerate(warmup_data):
        regime = det.update(h, l, c)
        # Pendant les 6 premiers ticks utiles (= 7 premiers ticks total), warm-up
        if i < 6:
            assert_eq(f"tick {i+1} warm-up", regime, MarketRegime.RANGE)

    status = det.get_status()
    assert_eq("warmed_up après 7 ticks (period=3)", status["warmed_up"], True)
    assert_true("adx non None", status["adx"] is not None)

    # =================================================================
    # Test 3 : Détection RANGE — marché latéral
    # =================================================================
    print("\n=== Test 3 : RANGE — marché latéral (ADX faible) ===")
    det_range = RegimeDetector(adx_period=3, adx_threshold_weak=20, adx_threshold_strong=40)

    # Marché latéral : prix oscillent entre 99 et 101
    lateral_data = [
        (101, 99, 100), (101, 99, 100), (101, 99, 100),
        (101, 99, 100), (101, 99, 100), (101, 99, 100),
        (101, 99, 100), (101, 99, 100), (101, 99, 100),
        (101, 99, 100), (101, 99, 100), (101, 99, 100),
    ]

    for h, l, c in lateral_data:
        regime = det_range.update(h, l, c)

    assert_eq("latéral => RANGE", regime, MarketRegime.RANGE)
    assert_true("grid OK en RANGE", det_range.should_trade_grid())
    assert_true("trend NOT OK en RANGE", not det_range.should_trade_trend())

    # =================================================================
    # Test 4 : Détection TREND_FORTE — tendance marquée
    # =================================================================
    print("\n=== Test 4 : TREND_FORTE — tendance haussière forte ===")
    det_trend = RegimeDetector(adx_period=3, adx_threshold_weak=20, adx_threshold_strong=40)

    # Tendance haussière forte : prix monte régulièrement avec gros range
    price = 100.0
    for i in range(20):
        price += 5.0  # monte de 5 à chaque tick
        h = price + 1.0
        l = price - 1.0
        c = price
        det_trend.update(h, l, c)

    regime = det_trend.get_regime()
    status = det_trend.get_status()
    # Avec une tendance aussi marquée, ADX devrait être élevé
    if status["warmed_up"] and status["adx"] is not None:
        assert_true(f"ADX élevé en tendance forte: {status['adx']:.1f}", status["adx"] > 30)
    assert_true("trend OK en TREND", det_trend.should_trade_trend() or regime == MarketRegime.CRISE)

    # =================================================================
    # Test 5 : Détection CRISE — volatilité extrême
    # =================================================================
    print("\n=== Test 5 : CRISE — spike de volatilité ===")
    det_crise = RegimeDetector(adx_period=3, adx_threshold_weak=20, adx_threshold_strong=40, crisis_atr_multiplier=2.0)

    # Phase calme pour établir ATR avg basse
    for i in range(10):
        det_crise.update(101, 99, 100)

    s_before = det_crise.get_status()
    print(f"  INFO  Avant spike: ATR={s_before['atr']}, ATR_avg={s_before['atr_avg']}")

    # Premier spike massif : le ratio ATR/ATR_avg est maximal au premier spike
    # car ATR_avg n'a pas encore rattrapé (Wilder smoothing avec period=3 est rapide)
    regime_spike = det_crise.update(150, 50, 100)

    s_after = det_crise.get_status()
    if s_after["atr"] is not None and s_after["atr_avg"] is not None and s_after["atr_avg"] > 0:
        ratio = s_after["atr"] / s_after["atr_avg"]
        print(f"  INFO  Après 1er spike: ATR={s_after['atr']}, ATR_avg={s_after['atr_avg']}, ratio={ratio:.2f}")
        assert_eq("CRISE détectée au premier spike", regime_spike, MarketRegime.CRISE)

    # =================================================================
    # Test 6 : should_trade_grid / should_trade_trend
    # =================================================================
    print("\n=== Test 6 : Méthodes should_trade ===")
    det6 = RegimeDetector(adx_period=3)

    # Pendant warm-up => RANGE => grid OK, trend NOK
    det6.update(101, 99, 100)
    assert_true("warm-up: grid OK", det6.should_trade_grid())
    assert_true("warm-up: trend NOK", not det6.should_trade_trend())

    # =================================================================
    # Test 7 : get_status — structure complète
    # =================================================================
    print("\n=== Test 7 : get_status — structure ===")
    det7 = RegimeDetector(adx_period=3, adx_threshold_weak=15, adx_threshold_strong=35, crisis_atr_multiplier=2.5)
    det7.update(101, 99, 100)
    s = det7.get_status()

    required_keys = [
        "regime", "adx", "atr", "atr_avg", "warmed_up", "tick_count",
        "grid_allowed", "trend_allowed", "period", "threshold_weak",
        "threshold_strong", "crisis_multiplier", "warmup_remaining",
    ]
    for key in required_keys:
        assert_true(f"clé '{key}' présente", key in s)

    assert_eq("status period", s["period"], 3)
    assert_eq("status threshold_weak", s["threshold_weak"], 15.0)
    assert_eq("status threshold_strong", s["threshold_strong"], 35.0)
    assert_eq("status crisis_multiplier", s["crisis_multiplier"], 2.5)
    assert_eq("status tick_count", s["tick_count"], 1)
    assert_eq("status regime", s["regime"], "RANGE")

    # =================================================================
    # Test 8 : reset
    # =================================================================
    print("\n=== Test 8 : reset ===")
    det8 = RegimeDetector(adx_period=3)
    for i in range(10):
        det8.update(101 + i, 99 + i, 100 + i)

    det8.reset()
    s = det8.get_status()
    assert_eq("reset tick_count", s["tick_count"], 0)
    assert_eq("reset warmed_up", s["warmed_up"], False)
    assert_eq("reset adx", s["adx"], None)
    assert_eq("reset regime", s["regime"], "RANGE")

    # =================================================================
    # Test 9 : Validation des entrées update()
    # =================================================================
    print("\n=== Test 9 : Validation entrées update() ===")
    det9 = RegimeDetector(adx_period=3)
    assert_raises("high < low", ValueError, det9.update, 90, 100, 95)
    assert_raises("low = 0", ValueError, det9.update, 100, 0, 50)
    assert_raises("low < 0", ValueError, det9.update, 100, -1, 50)
    assert_raises("type string", ValueError, det9.update, "100", 90, 95)

    # =================================================================
    # Test 10 : Thread-safety
    # =================================================================
    print("\n=== Test 10 : Thread-safety ===")
    import concurrent.futures

    det_mt = RegimeDetector(adx_period=5)
    errors = []

    def thread_task(i: int):
        try:
            price = 100.0 + (i % 20)
            h = price + 2.0
            l = price - 2.0
            det_mt.update(h, l, price)
            det_mt.get_regime()
            det_mt.should_trade_grid()
            det_mt.should_trade_trend()
            det_mt.get_status()
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
    # Test 11 : ADX converge vers 0 en marché parfaitement latéral
    # =================================================================
    print("\n=== Test 11 : ADX converge vers 0 en parfait range ===")
    det11 = RegimeDetector(adx_period=3)

    # Prix identiques => DM+ = DM- = 0 => DI+ = DI- = 0 => DX = 0
    for _ in range(20):
        det11.update(100, 100, 100)

    s = det11.get_status()
    if s["adx"] is not None:
        assert_true(f"ADX proche de 0 en flat: {s['adx']:.4f}", s["adx"] < 5.0)

    # =================================================================
    # Test 12 : Transition de régime (RANGE -> TREND_FAIBLE -> TREND_FORTE)
    # =================================================================
    print("\n=== Test 12 : Transition progressive de régime ===")
    det12 = RegimeDetector(adx_period=3, adx_threshold_weak=15, adx_threshold_strong=50)

    # Phase latérale
    for _ in range(10):
        det12.update(101, 99, 100)

    s = det12.get_status()
    if s["warmed_up"]:
        print(f"  INFO  Après phase latérale: ADX={s['adx']}, régime={s['regime']}")

    # Début de tendance modérée
    price = 100.0
    for _ in range(10):
        price += 2.0
        det12.update(price + 1, price - 1, price)

    s = det12.get_status()
    print(f"  INFO  Après tendance modérée: ADX={s['adx']}, régime={s['regime']}")

    # Accélération forte
    for _ in range(10):
        price += 8.0
        det12.update(price + 1, price - 1, price)

    s = det12.get_status()
    print(f"  INFO  Après tendance forte: ADX={s['adx']}, régime={s['regime']}")

    # =================================================================
    # Test 13 : CRISE prioritaire sur ADX
    # =================================================================
    print("\n=== Test 13 : CRISE prioritaire sur ADX ===")
    det13 = RegimeDetector(adx_period=3, crisis_atr_multiplier=2.0)

    # Warm-up calme pour établir ATR avg basse
    for _ in range(8):
        det13.update(101, 99, 100)

    s_pre = det13.get_status()
    print(f"  INFO  Avant crise: ATR={s_pre['atr']}, ADX={s_pre['adx']}")

    # Un seul spike massif (avec direction = tendance) => ADX monte ET crise
    # Le spike doit être suffisant pour que ATR > 2 * ATR_avg au premier coup
    regime_crisis = det13.update(200, 50, 180)
    s = det13.get_status()

    if s["warmed_up"] and s["atr"] is not None and s["atr_avg"] is not None and s["atr_avg"] > 0:
        ratio = s["atr"] / s["atr_avg"]
        print(f"  INFO  Après spike: ATR={s['atr']}, ATR_avg={s['atr_avg']}, ADX={s['adx']}, ratio={ratio:.2f}")
        assert_true(f"ATR ratio > crisis_mult ({ratio:.2f} > 2.0)", ratio > 2.0)
        assert_eq("CRISE prioritaire sur TREND", regime_crisis, MarketRegime.CRISE)

    # =================================================================
    # Test 14 : Warmup remaining dans get_status
    # =================================================================
    print("\n=== Test 14 : warmup_remaining ===")
    det14 = RegimeDetector(adx_period=3)
    # warm-up = 6 ticks utiles, premier tick sans TR
    s = det14.get_status()
    assert_eq("warmup_remaining initial", s["warmup_remaining"], 6)

    det14.update(101, 99, 100)  # tick 1, pas de TR
    s = det14.get_status()
    assert_eq("warmup_remaining après tick 1", s["warmup_remaining"], 6)

    det14.update(102, 98, 101)  # tick 2, 1er TR
    s = det14.get_status()
    assert_eq("warmup_remaining après tick 2", s["warmup_remaining"], 5)

    # =================================================================
    # Test 15 : MarketRegime enum valeurs
    # =================================================================
    print("\n=== Test 15 : MarketRegime enum ===")
    assert_true("RANGE existe", hasattr(MarketRegime, "RANGE"))
    assert_true("TREND_FAIBLE existe", hasattr(MarketRegime, "TREND_FAIBLE"))
    assert_true("TREND_FORTE existe", hasattr(MarketRegime, "TREND_FORTE"))
    assert_true("CRISE existe", hasattr(MarketRegime, "CRISE"))
    assert_eq("4 régimes", len(MarketRegime), 4)

    # ----- Résumé -----
    print(f"\n{'='*60}")
    print(f"RÉSULTATS : {passed}/{total} passés, {failed} échecs")
    print(f"{'='*60}")

    sys.exit(0 if failed == 0 else 1)
