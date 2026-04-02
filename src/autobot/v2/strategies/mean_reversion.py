"""
MeanReversionStrategy – AutoBot V2
Bollinger Bands simplifié : achète quand prix < moyenne - k*std,
vend quand le prix revient à la moyenne.
Thread-safe (RLock), O(1) amortized via deque(maxlen).
Aucune dépendance externe (pas de numpy/pandas).

Uses Welford's online algorithm for numerically stable variance.

IMPORTANT: Call update(price) ONCE per tick, then query should_enter() /
should_exit() without a price argument.  Never call should_enter/should_exit
with a price directly — that was the old API that caused double-push bugs.

PRODUCTION_READY = False — this strategy is not approved for live trading.
"""

from collections import deque
from math import sqrt
from threading import RLock
import logging

logger = logging.getLogger(__name__)


class MeanReversionStrategy:
    """Mean-reversion strategy based on simplified Bollinger Bands."""

    PRODUCTION_READY = False  # Stratégie non approuvée pour production

    def __init__(self, window: int = 20, deviation: float = 2.0) -> None:
        if not self.PRODUCTION_READY:
            raise RuntimeError(
                "❌ MeanReversionStrategy non approuvée pour production. "
                "Définir PRODUCTION_READY = True pour activer."
            )
        if window < 2:
            raise ValueError("window must be >= 2")
        if deviation <= 0:
            raise ValueError("deviation must be > 0")

        self._window = window
        self._deviation = deviation

        self._prices: deque[float] = deque(maxlen=window)
        # Welford state
        self._mean_acc: float = 0.0   # running mean
        self._m2: float = 0.0         # sum of squared deviations from mean
        self._in_position: bool = False
        self._lock = RLock()
        # Last price pushed via update() — used by should_enter / should_exit
        self._current_price: float = 0.0

    # ── internal helpers (caller must hold _lock) ──────────────────

    def _push(self, price: float) -> None:
        """Add a price, maintaining Welford running mean/M2 in O(1)."""
        n = len(self._prices)
        if n == self._window:
            # Window full — remove oldest via Welford removal step
            old = self._prices[0]  # will be evicted by deque
            # Remove old value from Welford accumulators
            n_after_remove = n - 1  # = self._window - 1
            if n_after_remove == 0:
                self._mean_acc = 0.0
                self._m2 = 0.0
            else:
                old_mean = self._mean_acc
                self._mean_acc = (old_mean * n - old) / n_after_remove
                self._m2 -= (old - self._mean_acc) * (old - old_mean)
            self._prices.append(price)
            # Now add the new value
            n_now = len(self._prices)  # == self._window
            old_mean = self._mean_acc
            self._mean_acc = old_mean + (price - old_mean) / n_now
            self._m2 += (price - self._mean_acc) * (price - old_mean)
        else:
            # Window not yet full — standard Welford add
            self._prices.append(price)
            n_now = len(self._prices)
            old_mean = self._mean_acc
            self._mean_acc = old_mean + (price - old_mean) / n_now
            self._m2 += (price - self._mean_acc) * (price - old_mean)

    def _mean(self) -> float:
        return self._mean_acc

    def _std(self) -> float:
        n = len(self._prices)
        if n < 2:
            return 0.0
        variance = self._m2 / n
        # Guard against floating-point drift producing tiny negatives
        return sqrt(max(variance, 0.0))

    def _ready(self) -> bool:
        return len(self._prices) == self._window

    # ── public API ─────────────────────────────────────────────────

    def update(self, price: float) -> None:
        """Push price into the window. Call this ONCE per tick before
        querying should_enter() or should_exit()."""
        with self._lock:
            self._push(price)
            self._current_price = price

    def should_enter(self) -> bool:
        """Return True if current price < lower band and not already in position.

        Must call update(price) before calling this method.
        """
        with self._lock:
            if not self._ready() or self._in_position:
                return False
            lower = self._mean() - self._deviation * self._std()
            if self._current_price < lower:
                self._in_position = True
                return True
            return False

    def should_exit(self) -> bool:
        """Return True if current price >= mean and currently in position.

        Must call update(price) before calling this method.
        """
        with self._lock:
            if not self._ready() or not self._in_position:
                return False
            if self._current_price >= self._mean():
                self._in_position = False
                return True
            return False

    def get_status(self) -> dict:
        """Snapshot of the strategy state."""
        with self._lock:
            n = len(self._prices)
            if n == 0:
                return {
                    "ready": False,
                    "in_position": self._in_position,
                    "window": self._window,
                    "deviation": self._deviation,
                    "samples": 0,
                    "mean": None,
                    "std": None,
                    "lower_band": None,
                    "upper_band": None,
                }
            mean = self._mean()
            std = self._std()
            return {
                "ready": self._ready(),
                "in_position": self._in_position,
                "window": self._window,
                "deviation": self._deviation,
                "samples": n,
                "mean": round(mean, 6),
                "std": round(std, 6),
                "lower_band": round(mean - self._deviation * std, 6),
                "upper_band": round(mean + self._deviation * std, 6),
            }


# ═══════════════════════════════════════════════════════════════════
#  Tests intégrés
# ═══════════════════════════════════════════════════════════════════

def _run_tests() -> int:
    # Allow test instantiation without PRODUCTION_READY guard
    MeanReversionStrategy.PRODUCTION_READY = True
    try:
        return _run_tests_impl()
    finally:
        MeanReversionStrategy.PRODUCTION_READY = False


def _run_tests_impl() -> int:
    passed = 0

    # ── 1. Paramètre validation ────────────────────────────────────
    try:
        MeanReversionStrategy(window=1)
        assert False, "Should have raised ValueError"
    except ValueError:
        passed += 1

    try:
        MeanReversionStrategy(deviation=-1)
        assert False, "Should have raised ValueError"
    except ValueError:
        passed += 1

    # ── 2. Not ready until window is full ──────────────────────────
    s = MeanReversionStrategy(window=5, deviation=1.0)
    for p in [100, 101, 102, 103]:
        s.update(p)
        assert s.should_enter() is False
        assert s.get_status()["ready"] is False
    passed += 1

    # ── 3. No entry when price is within bands ─────────────────────
    s = MeanReversionStrategy(window=5, deviation=2.0)
    stable = [100.0, 100.0, 100.0, 100.0, 100.0]
    for p in stable:
        s.update(p)
    # Price at the mean → should NOT enter
    s.update(100.0)
    assert s.should_enter() is False
    passed += 1

    # ── 4. Entry on extreme drop below lower band ─────────────────
    s = MeanReversionStrategy(window=5, deviation=1.0)
    for p in [100, 100, 100, 100]:
        s.update(p)
    # 5th price is a crash → std will be non-zero, price should be below lower
    s.update(80.0)
    entered = s.should_enter()
    assert entered is True, "Expected entry on extreme drop"
    assert s.get_status()["in_position"] is True
    passed += 1

    # ── 5. No double entry ─────────────────────────────────────────
    s.update(70.0)
    assert s.should_enter() is False, "Should not enter twice"
    passed += 1

    # ── 6. Exit when price returns to mean ─────────────────────────
    exited = False
    for p in [95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105]:
        s.update(p)
        if s.should_exit():
            exited = True
            break
    assert exited is True, "Expected exit when price >= mean"
    assert s.get_status()["in_position"] is False
    passed += 1

    # ── 7. No exit when not in position ────────────────────────────
    s2 = MeanReversionStrategy(window=5, deviation=1.0)
    for p in [100, 100, 100, 100, 100]:
        s2.update(p)
        assert s2.should_exit() is False
    passed += 1

    # ── 8. get_status() returns correct structure ──────────────────
    s3 = MeanReversionStrategy(window=3, deviation=1.5)
    st = s3.get_status()
    assert st["ready"] is False
    assert st["samples"] == 0
    assert st["mean"] is None
    for p in [10, 20, 30]:
        s3.update(p)
    st = s3.get_status()
    assert st["ready"] is True
    assert st["samples"] == 3
    assert st["mean"] == 20.0
    assert st["window"] == 3
    assert st["deviation"] == 1.5
    assert "lower_band" in st and "upper_band" in st
    passed += 1

    # ── 9. O(1) deque eviction correctness ────────────────────────
    s4 = MeanReversionStrategy(window=3, deviation=2.0)
    for p in [10, 20, 30]:
        s4.update(p)
    # Push one more → oldest (10) evicted, window = [20, 30, 40]
    s4.update(40)
    st = s4.get_status()
    assert st["mean"] == 30.0, f"Expected mean=30, got {st['mean']}"
    passed += 1

    # ── 10. Thread safety (RLock re-entrance) ──────────────────────
    s5 = MeanReversionStrategy(window=5, deviation=1.0)
    with s5._lock:
        st = s5.get_status()
    assert st["samples"] == 0
    passed += 1

    # ── 11. Full cycle: enter → exit ──────────────────────────────
    s6 = MeanReversionStrategy(window=5, deviation=1.0)
    for p in [100, 100, 100, 100]:
        s6.update(p)
    s6.update(80.0)
    assert s6.should_enter() is True
    exited = False
    for p in [90, 95, 100, 105]:
        s6.update(p)
        if s6.should_exit():
            exited = True
            break
    assert exited is True
    # Can re-enter after exit
    for p in [100, 100, 100, 100]:
        s6.update(p)
    s6.update(80.0)
    re_entered = s6.should_enter()
    assert re_entered is True, "Should be able to re-enter after exit"
    passed += 1

    # ── 12. No double-push: update() + should_enter() don't corrupt stats ──
    s7 = MeanReversionStrategy(window=5, deviation=1.0)
    for p in [100, 100, 100, 100, 100]:
        s7.update(p)
    mean_before = s7.get_status()["mean"]
    # Calling should_enter() must NOT push again
    s7.should_enter()
    mean_after = s7.get_status()["mean"]
    assert mean_before == mean_after, "should_enter() must not push price"
    # Same for should_exit()
    s7.should_exit()
    mean_exit = s7.get_status()["mean"]
    assert mean_before == mean_exit, "should_exit() must not push price"
    passed += 1

    # ── 13. Concurrent threads ─────────────────────────────────────
    from threading import Thread
    s8 = MeanReversionStrategy(window=10, deviation=1.0)
    errors = []

    def feed(prices):
        try:
            for p in prices:
                s8.update(p)
                s8.should_enter()
                s8.get_status()
                s8.should_exit()
        except Exception as e:
            errors.append(e)

    t1 = Thread(target=feed, args=([100 + i * 0.1 for i in range(50)],))
    t2 = Thread(target=feed, args=([100 - i * 0.1 for i in range(50)],))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    assert len(errors) == 0, f"Thread errors: {errors}"
    passed += 1

    return passed


if __name__ == "__main__":
    count = _run_tests()
    print(f"[TESTS] {count}/{count} passed ✓")
