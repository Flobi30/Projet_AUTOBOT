"""
Tests unitaires pour le module Kelly Criterion Sizing.

Couvre :
- Cas nominaux (Kelly positif, Half-Kelly, cap 25%)
- Cas limites (division par zéro, valeurs négatives, PF < 1)
- Thread-safety (accès concurrents)
- get_status() et reset()
- calculate_kelly_fraction() standalone

À exécuter avec: python3 -m pytest test_kelly_criterion.py -v
Ou directement : python3 test_kelly_criterion.py
"""

import threading
import sys
import os

# Ajouter le répertoire parent au path pour l'import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from modules.kelly_criterion import KellyCriterion


# ==================================================================
# Test runner intégré (pas de dépendance pytest)
# ==================================================================


class TestRunner:
    """Mini framework de tests intégré."""
    __test__ = False

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.total = 0

    def assert_eq(self, name, actual, expected, tolerance=0.01):
        self.total += 1
        if isinstance(expected, float):
            ok = abs(actual - expected) < tolerance
        else:
            ok = actual == expected
        if ok:
            self.passed += 1
            print(f"  ✅ {name}: {actual}")
        else:
            self.failed += 1
            print(f"  ❌ {name}: attendu {expected}, obtenu {actual}")

    def assert_true(self, name, condition):
        self.total += 1
        if condition:
            self.passed += 1
            print(f"  ✅ {name}")
        else:
            self.failed += 1
            print(f"  ❌ {name}")

    def assert_raises(self, name, exc_type, fn):
        self.total += 1
        try:
            fn()
            self.failed += 1
            print(f"  ❌ {name}: pas d'exception levée")
        except exc_type:
            self.passed += 1
            print(f"  ✅ {name}: {exc_type.__name__} levée")
        except Exception as e:
            self.failed += 1
            print(f"  ❌ {name}: mauvaise exception {type(e).__name__}: {e}")

    def summary(self):
        print(f"\n{'='*60}")
        print(f"RÉSULTATS : {self.passed}/{self.total} passés, {self.failed} échecs")
        print(f"{'='*60}")
        return self.failed == 0


def run_tests():
    t = TestRunner()
    kelly = KellyCriterion(max_position_pct=0.25)

    # === Constructeur ===
    print("\n=== Constructeur ===")
    t.assert_eq("défaut 25%", KellyCriterion().max_position_pct, 0.25)
    t.assert_eq("custom 10%", KellyCriterion(max_position_pct=0.10).max_position_pct, 0.10)
    t.assert_eq("custom 100%", KellyCriterion(max_position_pct=1.0).max_position_pct, 1.0)
    t.assert_raises("pct=0 → ValueError", ValueError, lambda: KellyCriterion(max_position_pct=0))
    t.assert_raises("pct=-0.1 → ValueError", ValueError, lambda: KellyCriterion(max_position_pct=-0.1))
    t.assert_raises("pct=1.5 → ValueError", ValueError, lambda: KellyCriterion(max_position_pct=1.5))
    t.assert_raises("pct='abc' → TypeError", TypeError, lambda: KellyCriterion(max_position_pct="abc"))

    # === Kelly fraction pure ===
    print("\n=== calculate_kelly_fraction ===")
    # f* = (0.6 * 1.5 - 0.4) / 1.5 = 0.3333
    t.assert_eq("60% WR, 1.5:1", kelly.calculate_kelly_fraction(0.60, 150.0, 100.0), 0.3333, 0.001)
    # f* = (0.5 * 2.0 - 0.5) / 2.0 = 0.25
    t.assert_eq("50% WR, 2:1", kelly.calculate_kelly_fraction(0.50, 200.0, 100.0), 0.25, 0.001)
    # Edge négatif → 0 (clampé)
    t.assert_eq("30% WR, 1:1 → 0", kelly.calculate_kelly_fraction(0.30, 100.0, 100.0), 0.0)
    # Breakeven exact
    t.assert_eq("50% WR, 1:1 → 0", kelly.calculate_kelly_fraction(0.50, 100.0, 100.0), 0.0)
    # Invalides
    t.assert_eq("WR=0 → 0", kelly.calculate_kelly_fraction(0.0, 100.0, 100.0), 0.0)
    t.assert_eq("WR=1 → 0", kelly.calculate_kelly_fraction(1.0, 100.0, 100.0), 0.0)
    t.assert_eq("avg_win=0 → 0", kelly.calculate_kelly_fraction(0.5, 0.0, 100.0), 0.0)
    t.assert_eq("avg_loss=0 → 0", kelly.calculate_kelly_fraction(0.5, 100.0, 0.0), 0.0)
    t.assert_eq("string → 0", kelly.calculate_kelly_fraction("bad", 100.0, 100.0), 0.0)

    # === Position size — cas nominaux ===
    print("\n=== calculate_position_size — nominaux ===")
    # Half-Kelly: 0.3333/2 = 0.1667 → 10000 * 0.1667 = 1666.67
    t.assert_eq("nominal 60%/1.5:1", kelly.calculate_position_size(0.60, 150.0, 100.0, 10000.0, 1.5), 1666.67, 1.0)
    # Half-Kelly: 0.325/2 = 0.1625 → 10000 * 0.1625 = 1625
    t.assert_eq("55%/2:1", kelly.calculate_position_size(0.55, 200.0, 100.0, 10000.0, 1.2), 1625.0, 1.0)
    # Cap at 25%: f*=0.88, half=0.44 > 0.25 → 10000 * 0.25 = 2500
    t.assert_eq("cap 25%", kelly.calculate_position_size(0.90, 500.0, 100.0, 10000.0, 4.5), 2500.0, 1.0)
    # Cap 10%: f*=0.3333, half=0.1667 > 0.10 → 10000 * 0.10 = 1000
    kelly_10 = KellyCriterion(max_position_pct=0.10)
    t.assert_eq("cap 10%", kelly_10.calculate_position_size(0.60, 150.0, 100.0, 10000.0, 1.5), 1000.0, 1.0)
    # Small capital
    t.assert_eq("100€ capital", kelly.calculate_position_size(0.60, 15.0, 10.0, 100.0, 1.5), 16.67, 0.5)
    # PF = 1.0 exact
    t.assert_true("PF=1.0 → >0", kelly.calculate_position_size(0.60, 150.0, 100.0, 10000.0, 1.0) > 0)

    # === Position size — cas limites ===
    print("\n=== calculate_position_size — cas limites ===")
    t.assert_eq("PF<1 → 0", kelly.calculate_position_size(0.60, 150.0, 100.0, 10000.0, 0.8), 0.0)
    t.assert_eq("Kelly négatif → 0", kelly.calculate_position_size(0.30, 50.0, 100.0, 10000.0, 1.2), 0.0)
    t.assert_eq("WR=0 → 0", kelly.calculate_position_size(0.0, 150.0, 100.0, 10000.0, 1.5), 0.0)
    t.assert_eq("WR=1 → 0", kelly.calculate_position_size(1.0, 150.0, 100.0, 10000.0, 1.5), 0.0)
    t.assert_eq("WR<0 → 0", kelly.calculate_position_size(-0.5, 150.0, 100.0, 10000.0, 1.5), 0.0)
    t.assert_eq("avg_win=0 → 0", kelly.calculate_position_size(0.6, 0.0, 100.0, 10000.0, 1.5), 0.0)
    t.assert_eq("avg_loss=0 → 0", kelly.calculate_position_size(0.6, 150.0, 0.0, 10000.0, 1.5), 0.0)
    t.assert_eq("capital=0 → 0", kelly.calculate_position_size(0.6, 150.0, 100.0, 0.0, 1.5), 0.0)
    t.assert_eq("capital<0 → 0", kelly.calculate_position_size(0.6, 150.0, 100.0, -500.0, 1.5), 0.0)
    t.assert_eq("PF<0 → 0", kelly.calculate_position_size(0.6, 150.0, 100.0, 10000.0, -1.0), 0.0)
    t.assert_eq("None → 0", kelly.calculate_position_size(None, 150.0, 100.0, 10000.0, 1.5), 0.0)
    t.assert_eq("string → 0", kelly.calculate_position_size("bad", 150.0, 100.0, 10000.0, 1.5), 0.0)

    # === get_status ===
    print("\n=== get_status ===")
    k2 = KellyCriterion(max_position_pct=0.20)
    s = k2.get_status()
    t.assert_eq("init max_pct", s["max_position_pct"], 0.20)
    t.assert_eq("init count", s["calculation_count"], 0)
    t.assert_eq("init frac", s["last_kelly_fraction"], None)

    k2.calculate_position_size(0.60, 150.0, 100.0, 5000.0, 1.5)
    s = k2.get_status()
    t.assert_eq("count=1", s["calculation_count"], 1)
    t.assert_true("frac not None", s["last_kelly_fraction"] is not None)
    t.assert_true("position > 0", s["last_position_size"] > 0)

    # Capped status
    k2_wide = KellyCriterion(max_position_pct=0.25)
    k2_wide.calculate_position_size(0.90, 500.0, 100.0, 10000.0, 4.5)
    t.assert_true("was_capped=True", k2_wide.get_status()["last_was_capped"])

    # === reset ===
    print("\n=== reset ===")
    kelly.reset()
    s = kelly.get_status()
    t.assert_eq("reset count", s["calculation_count"], 0)
    t.assert_eq("reset position", s["last_position_size"], None)
    # Can reuse after reset
    pos = kelly.calculate_position_size(0.60, 150.0, 100.0, 10000.0, 1.5)
    t.assert_true("reuse after reset", pos > 0)

    # === Thread safety ===
    print("\n=== Thread safety ===")
    import concurrent.futures
    kelly_mt = KellyCriterion(max_position_pct=0.25)
    errors = []

    def task(i):
        try:
            return kelly_mt.calculate_position_size(
                0.55 + (i % 10) * 0.01, 100.0 + i, 80.0, 10000.0, 1.2 + (i % 5) * 0.1
            )
        except Exception as e:
            errors.append(str(e))
            return -1.0

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(task, range(100)))

    t.assert_true("100 threads, 0 erreurs", len(errors) == 0)
    t.assert_true("tous résultats >= 0", all(r >= 0 for r in results))
    t.assert_eq("100 calculs comptés", kelly_mt.get_status()["calculation_count"], 100)

    # === Résumé ===
    ok = t.summary()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.WARNING)
    run_tests()
