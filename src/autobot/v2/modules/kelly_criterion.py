"""
Kelly Criterion Sizing — Taille de position optimale selon performance historique.

Module Phase 1 d'AutoBot V2. Calcule la fraction optimale de capital a risquer
par position en utilisant le critere de Kelly, ajuste en Half-Kelly pour
reduire la variance, avec un plafond de securite configurable (defaut 25%).

Formule de Kelly :
    f* = (p * b - q) / b

    ou :
        p = win rate (taux de trades gagnants)
        q = 1 - p (taux de trades perdants)
        b = avg_win / avg_loss (ratio gain moyen / perte moyenne)

Implementation :
    - Half-Kelly (f* / 2) pour reduire la variance de ~50%
    - Cap a max_position_pct (defaut 25%) du capital par position
    - Plancher a 0 : ne jamais risquer sur un edge negatif
    - Filtre Profit Factor : position = 0 si PF < 1.0

Proprietes :
    - Thread-safe (RLock)
    - O(1) — aucun calcul lourd
    - Validation complete des entrees
    - Aucune dependance externe

Usage:
    from autobot.v2.modules.kelly_criterion import KellyCriterion

    kelly = KellyCriterion(max_position_pct=0.25)

    fraction = kelly.calculate_kelly_fraction(
        win_rate=0.60, avg_win=150.0, avg_loss=100.0,
    )

    position = kelly.calculate_position_size(
        win_rate=0.60, avg_win=150.0, avg_loss=100.0,
        current_capital=10000.0, current_pf=1.5,
    )
"""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)


class KellyCriterion:
    """
    Calculateur de taille de position selon le critere de Kelly.
    Utilise Half-Kelly (f*/2) avec plafond a 25% du capital.
    """

    def __init__(self, max_position_pct: float = 0.25, dynamic_cap: float = 0.02) -> None:
        """
        Args:
            max_position_pct: Maximum du capital a allouer (defaut 25%).
                Doit etre dans ]0, 1].
        Raises:
            TypeError: Si max_position_pct n'est pas un nombre.
            ValueError: Si max_position_pct hors de ]0, 1].
        """
        if not isinstance(max_position_pct, (int, float)):
            raise TypeError(
                f"max_position_pct doit etre un nombre, recu {type(max_position_pct).__name__}"
            )
        if max_position_pct <= 0.0 or max_position_pct > 1.0:
            raise ValueError(
                f"max_position_pct doit etre dans ]0, 1], recu {max_position_pct}"
            )

        self._max_position_pct: float = float(max_position_pct)
        self._dynamic_cap: float = float(dynamic_cap)
        self._lock: threading.RLock = threading.RLock()

        # Etat interne (dernier calcul, pour dashboard/debug)
        self._last_kelly_fraction: float | None = None
        self._last_half_kelly: float | None = None
        self._last_position_size: float | None = None
        self._last_was_capped: bool = False
        self._calculation_count: int = 0

        logger.info(
            "Kelly Criterion initialise — position max: %.0f%% du capital (Half-Kelly)",
            max_position_pct * 100,
        )

    # ------------------------------------------------------------------
    # Proprietes
    # ------------------------------------------------------------------

    @property
    def max_position_pct(self) -> float:
        """Fraction maximale du capital par position."""
        return self._max_position_pct

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def calculate_kelly_fraction(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
    ) -> float:
        """
        Calcule la fraction Kelly pure.

        f* = (p * b - q) / b
        avec p = win_rate, q = 1 - p, b = avg_win / avg_loss

        Args:
            win_rate: Entre 0.0 et 1.0 (exclus).
            avg_win: Gain moyen (> 0).
            avg_loss: Perte moyenne (> 0).

        Returns:
            Fraction entre 0.0 et 1.0 si edge positive,
            0.0 si edge negative ou entrees invalides.
        """
        with self._lock:
            if not self._validate_fraction_inputs(win_rate, avg_win, avg_loss):
                return 0.0

            f_star = self._compute_kelly(win_rate, avg_win, avg_loss)
            return max(f_star, 0.0)

    def calculate_position_size(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        current_capital: float,
        current_pf: float,
    ) -> float:
        """
        Calcule la taille de position en euros avec Half-Kelly.

        Args:
            win_rate: Taux de trades gagnants (]0, 1[).
            avg_win: Gain moyen en euros (> 0).
            avg_loss: Perte moyenne en euros (> 0).
            current_capital: Capital disponible en euros (> 0).
            current_pf: Profit Factor actuel (>= 1.0 pour trader).

        Returns:
            Taille de position en euros (jamais superieure a
            max_position_pct * capital). 0.0 si conditions non remplies.
        """
        with self._lock:
            self._calculation_count += 1

            # --- Validation ---
            if not self._validate_position_inputs(
                win_rate, avg_win, avg_loss, current_capital, current_pf
            ):
                self._store_zero()
                return 0.0

            # --- Filtre Profit Factor ---
            if current_pf < 1.0:
                logger.info(
                    "Kelly: PF %.2f < 1.0 — position 0.00 euros (0.00%% capital)",
                    current_pf,
                )
                self._store_zero()
                return 0.0

            # --- Calcul Kelly brut ---
            f_star = self._compute_kelly(win_rate, avg_win, avg_loss)
            self._last_kelly_fraction = f_star

            if f_star <= 0.0:
                logger.info(
                    "Kelly: %.2f%% edge -> position 0.00 euros (0.00%% capital)",
                    f_star * 100,
                )
                self._last_half_kelly = f_star / 2.0
                self._last_position_size = 0.0
                self._last_was_capped = False
                return 0.0

            # --- Half-Kelly + cap ---
            half_kelly = f_star / 2.0
            effective = min(half_kelly, self._max_position_pct)
            was_capped = half_kelly > self._max_position_pct
            position_size = round(current_capital * effective, 2)

            # --- Stockage ---
            self._last_half_kelly = half_kelly
            self._last_position_size = position_size
            self._last_was_capped = was_capped

            # --- Log spec: "Kelly: X.XX% edge -> position Y.YY euros (Z.ZZ% capital)" ---
            logger.info(
                "Kelly: %.2f%% edge -> position %.2f euros (%.2f%% capital)",
                f_star * 100,
                position_size,
                effective * 100,
            )

            return position_size

    def calculate_position_size_dynamic(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        capital: float,
        current_pf: float,
        consecutive_losses: int = 0,
    ) -> float:
        """
        Taille de position Kelly avec decrement apres pertes consecutives.

        Apres 3 pertes consecutives, applique un facteur de reduction :
            f = base_kelly * 0.85^(consecutive_losses - 2)
        Half-Kelly applique. Plafond absolu a 2% du capital.

        Args:
            win_rate: Taux de trades gagnants (]0, 1[).
            avg_win: Gain moyen en euros (> 0).
            avg_loss: Perte moyenne en euros (> 0).
            capital: Capital disponible en euros (> 0).
            current_pf: Profit Factor actuel (doit etre >= 1.0 pour trader).
            consecutive_losses: Nombre de pertes consecutives (>= 0, defaut 0).

        Returns:
            Taille de position en euros, plafonnee a 2% du capital.
            0.0 si conditions non remplies (PF < 1.0, edge negative, entrees invalides).
        """
        with self._lock:
            # --- Validation ---
            if not self._validate_position_inputs(
                win_rate, avg_win, avg_loss, capital, current_pf
            ):
                return 0.0

            if not isinstance(consecutive_losses, int) or consecutive_losses < 0:
                logger.warning(
                    "Kelly dynamic: consecutive_losses invalide (%s)", consecutive_losses
                )
                return 0.0

            # --- Filtre Profit Factor ---
            if current_pf < 1.0:
                logger.info(
                    "Kelly dynamic: PF %.2f < 1.0 — position 0.00 euros",
                    current_pf,
                )
                return 0.0

            # --- Calcul Kelly brut + Half-Kelly ---
            f_star = self._compute_kelly(win_rate, avg_win, avg_loss)
            if f_star <= 0.0:
                return 0.0

            kelly = f_star / 2.0

            # --- Decrement apres 3 pertes consecutives ---
            if consecutive_losses >= 3:
                exponent = consecutive_losses - 2
                kelly *= 0.85 ** exponent
                logger.info(
                    "Kelly dynamic: %d pertes => facteur 0.85^%d = %.4f applique",
                    consecutive_losses,
                    exponent,
                    0.85 ** exponent,
                )

            # --- Plafond dynamique ---
            position = min(kelly * capital, capital * self._dynamic_cap)

            logger.info(
                "Kelly dynamic: position %.2f euros (%.4f%% capital, %d pertes consecutives)",
                position,
                (position / capital) * 100 if capital > 0 else 0.0,
                consecutive_losses,
            )
            return position

    def get_status(self) -> dict:
        """Retourne l'etat du calculateur."""
        with self._lock:
            return {
                "max_position_pct": self._max_position_pct,
                "last_kelly_fraction": (
                    round(self._last_kelly_fraction, 6)
                    if self._last_kelly_fraction is not None
                    else None
                ),
                "last_half_kelly": (
                    round(self._last_half_kelly, 6)
                    if self._last_half_kelly is not None
                    else None
                ),
                "last_position_size": (
                    round(self._last_position_size, 2)
                    if self._last_position_size is not None
                    else None
                ),
                "last_was_capped": self._last_was_capped,
                "calculation_count": self._calculation_count,
            }

    def reset(self) -> None:
        """Reinitialise l'etat interne."""
        with self._lock:
            self._last_kelly_fraction = None
            self._last_half_kelly = None
            self._last_position_size = None
            self._last_was_capped = False
            self._calculation_count = 0
            logger.info("Kelly Criterion: reinitialise")

    # ------------------------------------------------------------------
    # Methodes privees
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_kelly(win_rate: float, avg_win: float, avg_loss: float) -> float:
        """f* = (p * b - q) / b   —   O(1), pas de validation."""
        p = win_rate
        q = 1.0 - p
        b = avg_win / avg_loss
        return (p * b - q) / b

    def _store_zero(self) -> None:
        """Stocke un resultat nul dans l'etat interne."""
        self._last_kelly_fraction = None
        self._last_half_kelly = None
        self._last_position_size = 0.0
        self._last_was_capped = False

    def _validate_fraction_inputs(
        self, win_rate: float, avg_win: float, avg_loss: float
    ) -> bool:
        """Valide les entrees pour calculate_kelly_fraction."""
        for name, value in [
            ("win_rate", win_rate),
            ("avg_win", avg_win),
            ("avg_loss", avg_loss),
        ]:
            if not isinstance(value, (int, float)):
                logger.warning(
                    "Kelly: parametre '%s' invalide (type %s)",
                    name,
                    type(value).__name__,
                )
                return False

        if win_rate <= 0.0 or win_rate >= 1.0:
            logger.warning("Kelly: win_rate hors plage (%.4f)", win_rate)
            return False
        if avg_win <= 0.0:
            logger.warning("Kelly: avg_win invalide (%.2f)", avg_win)
            return False
        if avg_loss <= 0.0:
            logger.warning("Kelly: avg_loss invalide (%.2f)", avg_loss)
            return False

        return True

    def _validate_position_inputs(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        current_capital: float,
        current_pf: float,
    ) -> bool:
        """Valide toutes les entrees pour calculate_position_size."""
        for name, value in [
            ("win_rate", win_rate),
            ("avg_win", avg_win),
            ("avg_loss", avg_loss),
            ("current_capital", current_capital),
            ("current_pf", current_pf),
        ]:
            if not isinstance(value, (int, float)):
                logger.warning(
                    "Kelly: parametre '%s' invalide (type %s)",
                    name,
                    type(value).__name__,
                )
                return False

        if win_rate <= 0.0 or win_rate >= 1.0:
            logger.warning("Kelly: win_rate hors plage (%.4f)", win_rate)
            return False
        if avg_win <= 0.0:
            logger.warning("Kelly: avg_win invalide (%.2f)", avg_win)
            return False
        if avg_loss <= 0.0:
            logger.warning("Kelly: avg_loss invalide (%.2f)", avg_loss)
            return False
        if current_capital <= 0.0:
            logger.warning("Kelly: capital invalide (%.2f)", current_capital)
            return False
        if current_pf < 0.0:
            logger.warning("Kelly: profit factor invalide (%.2f)", current_pf)
            return False

        return True


# ======================================================================
# Tests integres
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

    kelly = KellyCriterion(max_position_pct=0.25)

    # ----- Test 1 : Fraction Kelly pure — cas nominal -----
    print("\n=== Test 1 : calculate_kelly_fraction — cas nominal ===")
    # win_rate=0.60, avg_win=150, avg_loss=100 => b=1.5
    # f* = (0.60 * 1.5 - 0.40) / 1.5 = (0.90 - 0.40) / 1.5 = 0.3333
    frac = kelly.calculate_kelly_fraction(0.60, 150.0, 100.0)
    assert_eq("f* (60% WR, 1.5:1 ratio)", frac, 0.3333, tolerance=0.001)

    # ----- Test 2 : Fraction Kelly pure — edge negative -----
    print("\n=== Test 2 : calculate_kelly_fraction — edge negative ===")
    # win_rate=0.30, avg_win=100, avg_loss=100 => b=1.0
    # f* = (0.30 * 1.0 - 0.70) / 1.0 = -0.40 => retourne 0.0
    frac = kelly.calculate_kelly_fraction(0.30, 100.0, 100.0)
    assert_eq("f* edge negative", frac, 0.0)

    # ----- Test 3 : Fraction Kelly — win_rate = 50%, ratio 2:1 -----
    print("\n=== Test 3 : calculate_kelly_fraction — 50% WR, 2:1 ratio ===")
    # f* = (0.50 * 2.0 - 0.50) / 2.0 = 0.50 / 2.0 = 0.25
    frac = kelly.calculate_kelly_fraction(0.50, 200.0, 100.0)
    assert_eq("f* (50% WR, 2:1 ratio)", frac, 0.25, tolerance=0.001)

    # ----- Test 4 : Position size — cas nominal -----
    print("\n=== Test 4 : calculate_position_size — cas nominal ===")
    # f* = 0.3333, half-kelly = 0.1667, cap = 0.25 => pas cappe
    # position = 10000 * 0.1667 = 1666.67
    pos = kelly.calculate_position_size(0.60, 150.0, 100.0, 10000.0, 1.5)
    assert_eq("position size nominal", pos, 1666.67, tolerance=1.0)

    # ----- Test 5 : Position size — Half-Kelly cappe a 25% -----
    print("\n=== Test 5 : calculate_position_size — cap a 25% ===")
    # win_rate=0.80, avg_win=300, avg_loss=100 => b=3.0
    # f* = (0.80 * 3.0 - 0.20) / 3.0 = 2.20 / 3.0 = 0.7333
    # half-kelly = 0.3667 > 0.25 => cappe a 0.25
    # position = 10000 * 0.25 = 2500.00
    pos = kelly.calculate_position_size(0.80, 300.0, 100.0, 10000.0, 2.0)
    assert_eq("position size cappe", pos, 2500.0, tolerance=0.01)

    # ----- Test 6 : PF < 1.0 — pas de trade -----
    print("\n=== Test 6 : calculate_position_size — PF < 1.0 ===")
    pos = kelly.calculate_position_size(0.60, 150.0, 100.0, 10000.0, 0.8)
    assert_eq("PF < 1.0 => 0", pos, 0.0)

    # ----- Test 7 : Edge negative dans position_size -----
    print("\n=== Test 7 : calculate_position_size — edge negative ===")
    pos = kelly.calculate_position_size(0.30, 100.0, 100.0, 10000.0, 1.2)
    assert_eq("edge negative => 0", pos, 0.0)

    # ----- Test 8 : Entrees invalides -----
    print("\n=== Test 8 : Validation des entrees invalides ===")
    assert_eq("win_rate = 0", kelly.calculate_kelly_fraction(0.0, 100.0, 100.0), 0.0)
    assert_eq("win_rate = 1", kelly.calculate_kelly_fraction(1.0, 100.0, 100.0), 0.0)
    assert_eq("win_rate negatif", kelly.calculate_kelly_fraction(-0.1, 100.0, 100.0), 0.0)
    assert_eq("avg_win = 0", kelly.calculate_kelly_fraction(0.5, 0.0, 100.0), 0.0)
    assert_eq("avg_loss = 0", kelly.calculate_kelly_fraction(0.5, 100.0, 0.0), 0.0)
    assert_eq("avg_win negatif", kelly.calculate_kelly_fraction(0.5, -50.0, 100.0), 0.0)
    assert_eq("type string", kelly.calculate_kelly_fraction("0.5", 100.0, 100.0), 0.0)
    assert_eq(
        "capital negatif",
        kelly.calculate_position_size(0.5, 100.0, 100.0, -1000.0, 1.5),
        0.0,
    )
    assert_eq(
        "pf negatif",
        kelly.calculate_position_size(0.5, 100.0, 100.0, 10000.0, -1.0),
        0.0,
    )

    # ----- Test 9 : Constructeur — max_position_pct invalide -----
    print("\n=== Test 9 : Constructeur — validation max_position_pct ===")
    total += 1
    try:
        KellyCriterion(max_position_pct=0.0)
        failed += 1
        print("  FAIL  max_position_pct=0: pas de ValueError")
    except ValueError:
        passed += 1
        print("  PASS  max_position_pct=0: ValueError levee")

    total += 1
    try:
        KellyCriterion(max_position_pct=1.5)
        failed += 1
        print("  FAIL  max_position_pct=1.5: pas de ValueError")
    except ValueError:
        passed += 1
        print("  PASS  max_position_pct=1.5: ValueError levee")

    total += 1
    try:
        KellyCriterion(max_position_pct="abc")
        failed += 1
        print("  FAIL  max_position_pct='abc': pas de TypeError")
    except TypeError:
        passed += 1
        print("  PASS  max_position_pct='abc': TypeError levee")

    # ----- Test 10 : get_status -----
    print("\n=== Test 10 : get_status ===")
    kelly2 = KellyCriterion(max_position_pct=0.20)
    status = kelly2.get_status()
    assert_eq("status max_position_pct", status["max_position_pct"], 0.20)
    assert_eq("status calculation_count init", status["calculation_count"], 0)
    assert_eq("status last_kelly_fraction init", status["last_kelly_fraction"], None)

    kelly2.calculate_position_size(0.60, 150.0, 100.0, 5000.0, 1.5)
    status = kelly2.get_status()
    assert_eq("status calculation_count apres 1 calcul", status["calculation_count"], 1)
    assert_eq("status last_kelly_fraction", status["last_kelly_fraction"] is not None, True)
    assert_eq("status last_position_size > 0", status["last_position_size"] > 0, True)

    # ----- Test 11 : Position avec max_position_pct personnalise -----
    print("\n=== Test 11 : max_position_pct personnalise (10%) ===")
    kelly3 = KellyCriterion(max_position_pct=0.10)
    # f* = 0.3333, half = 0.1667 > 0.10 => cappe a 10%
    pos = kelly3.calculate_position_size(0.60, 150.0, 100.0, 10000.0, 1.5)
    assert_eq("position cappee a 10%", pos, 1000.0, tolerance=0.01)

    # ----- Test 12 : reset -----
    print("\n=== Test 12 : reset ===")
    kelly.reset()
    status = kelly.get_status()
    assert_eq("apres reset: calculation_count", status["calculation_count"], 0)
    assert_eq("apres reset: last_position_size", status["last_position_size"], None)

    # ----- Test 13 : Thread-safety basique -----
    print("\n=== Test 13 : Thread-safety ===")
    import concurrent.futures

    kelly_mt = KellyCriterion(max_position_pct=0.25)
    errors = []

    def thread_task(i: int) -> float:
        try:
            return kelly_mt.calculate_position_size(
                win_rate=0.55 + (i % 10) * 0.01,
                avg_win=100.0 + i,
                avg_loss=80.0,
                current_capital=10000.0,
                current_pf=1.2 + (i % 5) * 0.1,
            )
        except Exception as exc:
            errors.append(str(exc))
            return -1.0

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(thread_task, i) for i in range(100)]
        results = [f.result() for f in futures]

    total += 1
    if not errors and all(r >= 0 for r in results):
        passed += 1
        print(f"  PASS  100 calculs concurrents sans erreur (count={kelly_mt.get_status()['calculation_count']})")
    else:
        failed += 1
        print(f"  FAIL  Erreurs concurrentes: {errors}")

    # ----- Test 14 : Kelly exact — win_rate=0.50, ratio 1:1 -----
    print("\n=== Test 14 : Kelly exact — breakeven (50%, 1:1) ===")
    # f* = (0.50 * 1.0 - 0.50) / 1.0 = 0.0
    frac = kelly.calculate_kelly_fraction(0.50, 100.0, 100.0)
    assert_eq("breakeven => 0", frac, 0.0)

    # ----- Resume -----
    print(f"\n{'='*60}")
    print(f"RESULTATS : {passed}/{total} passes, {failed} echecs")
    print(f"{'='*60}")

    sys.exit(0 if failed == 0 else 1)