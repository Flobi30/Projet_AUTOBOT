"""
Tests: MeanReversionStrategy — No-double-push contract

Validates that should_enter() and should_exit() never call _push() internally.
Only update() is allowed to push a price into the window.

Bug context: old API accepted price args on should_enter/should_exit and called
_push() directly, causing the same price to be pushed twice per tick when both
methods were called sequentially — corrupting the running mean/std.
"""

import pytest

from autobot.v2.strategies.mean_reversion import MeanReversionStrategy


pytestmark = pytest.mark.unit

# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def unlock_production_guard():
    """Bypass the PRODUCTION_READY guard for the duration of each test."""
    MeanReversionStrategy.PRODUCTION_READY = True
    yield
    MeanReversionStrategy.PRODUCTION_READY = False


@pytest.fixture
def strategy():
    return MeanReversionStrategy(window=20, deviation=2.0)


# ── helpers ───────────────────────────────────────────────────────────────────

def _samples(s: MeanReversionStrategy) -> int:
    return s.get_status()["samples"]


def _mean(s: MeanReversionStrategy) -> float | None:
    return s.get_status()["mean"]


# ── tests ─────────────────────────────────────────────────────────────────────

class TestUpdateOncePerTick:
    """update() pushes exactly one price per call."""

    def test_update_once_per_tick(self, strategy):
        strategy.update(100.0)
        assert _samples(strategy) == 1

    def test_multiple_updates_increment_by_one(self, strategy):
        for i in range(5):
            strategy.update(float(100 + i))
            assert _samples(strategy) == i + 1


class TestShouldEnterNoPush:
    """should_enter() must not push any price into the window."""

    def test_should_enter_no_push_not_ready(self, strategy):
        strategy.update(100.0)
        samples_before = _samples(strategy)
        strategy.should_enter()
        assert _samples(strategy) == samples_before

    def test_should_enter_no_push_window_full(self, strategy):
        for _ in range(20):
            strategy.update(100.0)
        samples_before = _samples(strategy)
        mean_before = _mean(strategy)

        strategy.should_enter()

        assert _samples(strategy) == samples_before
        assert _mean(strategy) == mean_before

    def test_should_enter_no_push_returns_true(self, strategy):
        """Even when should_enter fires, the window must not grow."""
        for _ in range(19):
            strategy.update(100.0)
        strategy.update(50.0)  # extreme drop → should_enter == True
        samples_before = _samples(strategy)
        mean_before = _mean(strategy)

        result = strategy.should_enter()

        assert result is True
        assert _samples(strategy) == samples_before
        assert _mean(strategy) == mean_before


class TestShouldExitNoPush:
    """should_exit() must not push any price into the window."""

    def test_should_exit_no_push_not_ready(self, strategy):
        strategy.update(100.0)
        samples_before = _samples(strategy)
        strategy.should_exit()
        assert _samples(strategy) == samples_before

    def test_should_exit_no_push_window_full(self, strategy):
        for _ in range(20):
            strategy.update(100.0)
        samples_before = _samples(strategy)
        mean_before = _mean(strategy)

        strategy.should_exit()

        assert _samples(strategy) == samples_before
        assert _mean(strategy) == mean_before

    def test_should_exit_no_push_returns_true(self, strategy):
        """Even when should_exit fires, the window must not grow."""
        # Enter a position first
        for _ in range(19):
            strategy.update(100.0)
        strategy.update(50.0)
        assert strategy.should_enter() is True  # now in_position

        # Push prices back toward mean to trigger exit
        for _ in range(20):
            strategy.update(100.0)
        samples_before = _samples(strategy)
        mean_before = _mean(strategy)

        result = strategy.should_exit()

        assert result is True
        assert _samples(strategy) == samples_before
        assert _mean(strategy) == mean_before


class TestNoDoublePushSequential:
    """Sequential should_enter() / should_exit() calls in the same tick must
    leave the window unchanged (the old double-push bug scenario)."""

    def test_no_double_push_sequential(self, strategy):
        for _ in range(19):
            strategy.update(100.0)
        strategy.update(50.0)  # extreme drop

        mean_before = _mean(strategy)
        samples_before = _samples(strategy)

        # Simulate typical tick processing
        if strategy.should_enter():
            pass
        elif strategy.should_exit():
            pass

        assert _samples(strategy) == samples_before, (
            "Window grew: should_enter/should_exit called _push() internally"
        )
        assert _mean(strategy) == mean_before, (
            "Mean shifted: internal push corrupted running stats"
        )

    def test_no_double_push_both_called_unconditionally(self, strategy):
        """Even if both methods are called regardless of result, no double push."""
        for _ in range(19):
            strategy.update(100.0)
        strategy.update(50.0)

        mean_before = _mean(strategy)
        samples_before = _samples(strategy)

        strategy.should_enter()
        strategy.should_exit()

        assert _samples(strategy) == samples_before
        assert _mean(strategy) == mean_before

    def test_no_double_push_multiple_ticks(self, strategy):
        """Over many ticks, sequential queries must never inflate the window."""
        for tick in range(1, 101):
            price = 100.0 + (tick % 5) * 0.1
            strategy.update(price)

            expected = min(tick, 20)  # window capped at maxlen=20
            samples_after_update = _samples(strategy)

            strategy.should_enter()
            strategy.should_exit()

            assert _samples(strategy) == samples_after_update, (
                f"Window inflated at tick {tick}"
            )


class TestWindowSizeConsistency:
    """Window never exceeds its configured maxlen, regardless of how many
    update() calls are made or how many times should_enter/should_exit are
    queried."""

    def test_window_size_capped_at_maxlen(self):
        s = MeanReversionStrategy(window=100, deviation=2.0)
        for i in range(100):
            s.update(float(100 + i))
        assert _samples(s) == 100, "Window should hold exactly 100 samples"

    def test_window_size_not_doubled_by_queries(self):
        s = MeanReversionStrategy(window=100, deviation=2.0)
        for i in range(100):
            s.update(float(100 + i))
            s.should_enter()
            s.should_exit()
        assert _samples(s) == 100, (
            "Window size is 100 (not 200): each query must not re-push"
        )

    def test_window_size_stable_after_overflow(self, strategy):
        """After pushing more than window prices, len stays at window."""
        for i in range(50):  # 50 > window=20
            strategy.update(float(100 + i))
        assert _samples(strategy) == 20

        mean_after_50 = _mean(strategy)
        strategy.should_enter()
        strategy.should_exit()
        assert _samples(strategy) == 20
        assert _mean(strategy) == mean_after_50
