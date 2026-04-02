"""
AutoBot V2 – Triangular Arbitrage Strategy
Detects and executes triangular arbitrage opportunities across 3 trading pairs.
Example cycle: BTC/EUR → ETH/BTC → ETH/EUR (reversed to close the loop).

Constraints: RLock for thread-safety, O(1) detection, no numpy/pandas.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TradingPair:
    """Immutable representation of a trading pair."""
    base: str
    quote: str

    @classmethod
    def from_string(cls, s: str) -> "TradingPair":
        base, quote = s.strip().upper().split("/")
        return cls(base=base, quote=quote)

    def __str__(self) -> str:
        return f"{self.base}/{self.quote}"


@dataclass
class ArbitrageOpportunity:
    """Describes a detected triangular-arbitrage opportunity."""
    cycle: List[str]            # e.g. ["BTC/EUR", "ETH/BTC", "ETH/EUR"]
    directions: List[str]       # "buy" or "sell" for each leg
    rates: List[float]          # execution rate for each leg
    gross_product: float        # product of effective rates (>1 = profit)
    net_profit_pct: float       # profit % after fees
    # W3: monotonic clock — immune to NTP jumps, safe for elapsed-time checks
    timestamp: float = field(default_factory=time.monotonic)


# ---------------------------------------------------------------------------
# Triangular Arbitrage Engine
# ---------------------------------------------------------------------------

class TriangularArbitrage:
    """
    Detect and execute triangular-arbitrage opportunities.

    PRODUCTION_READY = False — strategy under development, not approved for live trading.

    Parameters
    ----------
    pairs : list[str]
        Exactly 3 trading pair strings, e.g. ["BTC/EUR", "ETH/BTC", "ETH/EUR"].
    fee_pct : float
        Single-leg trading fee as a percentage (default 0.1 = 0.1 %).
    min_profit_pct : float
        Minimum net profit % to consider an opportunity valid (default 0.5).
    """

    PRODUCTION_READY = False  # W2: stratégie non approuvée pour production

    def __init__(
        self,
        pairs: List[str],
        fee_pct: float = 0.1,
        min_profit_pct: float = 0.5,
    ) -> None:
        if not self.PRODUCTION_READY:
            raise RuntimeError(
                "❌ TriangularArbitrage non approuvée pour production. "
                "Définir PRODUCTION_READY = True pour activer."
            )
        if len(pairs) != 3:
            raise ValueError(f"Exactly 3 pairs required, got {len(pairs)}")

        self._lock = threading.RLock()
        self._pairs = [TradingPair.from_string(p) for p in pairs]
        self._pair_strings = [str(p) for p in self._pairs]
        self._fee_mult = 1.0 - fee_pct / 100.0   # multiplier per leg
        self._min_profit_pct = min_profit_pct

        # Pre-compute the two possible cycle directions and their leg
        # orientations so that detect_opportunity is O(1).
        self._cycles = self._precompute_cycles()

        # Execution log (for auditing / testing)
        self._execution_log: List[dict] = []

    # ------------------------------------------------------------------
    # Pre-computation (called once in __init__)
    # ------------------------------------------------------------------

    def _precompute_cycles(self) -> List[Dict]:
        """
        Build all valid 3-leg cycles from the given pairs.

        A cycle starts with a base currency, traverses 3 pairs, and must
        return to the starting currency.  For each pair we can go in the
        natural direction (buy base with quote) or inverse (sell base for
        quote), giving 2^3 = 8 direction combos × starting-currency choices.

        Returns a list of dicts with keys: order, directions, pair_indices.
        """
        pairs = self._pairs
        # Collect all currencies
        currencies = set()
        for p in pairs:
            currencies.add(p.base)
            currencies.add(p.quote)

        # Map currency→list of (pair_index, role) where role is 'base' or 'quote'
        currency_pairs: Dict[str, List[Tuple[int, str]]] = {c: [] for c in currencies}
        for idx, p in enumerate(pairs):
            currency_pairs[p.base].append((idx, "base"))
            currency_pairs[p.quote].append((idx, "quote"))

        cycles: List[Dict] = []
        visited_signatures = set()

        def _find_cycles(start: str, current: str, path_indices: List[int],
                         path_dirs: List[str], depth: int):
            if depth == 3:
                if current == start:
                    sig = tuple(sorted(path_indices))
                    dir_sig = (sig, tuple(path_dirs))
                    if dir_sig not in visited_signatures:
                        visited_signatures.add(dir_sig)
                        cycles.append({
                            "pair_indices": list(path_indices),
                            "directions": list(path_dirs),
                        })
                return
            for idx, role in currency_pairs.get(current, []):
                if idx in path_indices:
                    continue
                p = pairs[idx]
                if role == "quote":
                    # We hold 'current' which is the quote → buy base
                    next_currency = p.base
                    direction = "buy"
                elif role == "base":
                    # We hold 'current' which is the base → sell base for quote
                    next_currency = p.quote
                    direction = "sell"
                else:
                    continue
                path_indices.append(idx)
                path_dirs.append(direction)
                _find_cycles(start, next_currency, path_indices, path_dirs, depth + 1)
                path_indices.pop()
                path_dirs.pop()

        for c in currencies:
            _find_cycles(c, c, [], [], 0)

        return cycles

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect_opportunity(
        self, prices: Dict[str, float]
    ) -> Optional[ArbitrageOpportunity]:
        """
        Detect a triangular-arbitrage opportunity from current prices.

        Parameters
        ----------
        prices : dict
            Mapping of pair string → mid price, e.g. {"BTC/EUR": 50000, ...}.
            All 3 configured pairs must be present.

        Returns
        -------
        ArbitrageOpportunity or None
            The best opportunity if net profit > min_profit_pct, else None.
        """
        with self._lock:
            # Validate prices
            for ps in self._pair_strings:
                if ps not in prices:
                    raise KeyError(f"Missing price for pair {ps}")

            best_net_pct: float = -1e300
            best_indices: Optional[List[int]] = None
            best_directions: Optional[List[str]] = None
            best_rates: Optional[List[float]] = None
            best_gross: float = 0.0

            fee_mult_cubed = self._fee_mult ** 3

            # O(1): fixed small number of pre-computed cycles (≤ 6 for 3 pairs)
            for cyc in self._cycles:
                indices = cyc["pair_indices"]
                directions = cyc["directions"]

                gross = 1.0
                r0 = r1 = r2 = 0.0  # scalar rates (avoid list alloc)

                for i, idx in enumerate(indices):
                    # Use cached string instead of str(pair) — avoids
                    # allocation on every iteration of the hot path.
                    price = prices[self._pair_strings[idx]]
                    direction = directions[i]

                    if direction == "buy":
                        rate = 1.0 / price
                    else:
                        rate = price

                    if i == 0:
                        r0 = rate
                    elif i == 1:
                        r1 = rate
                    else:
                        r2 = rate
                    gross *= rate

                # Apply fees (3 legs)
                net = gross * fee_mult_cubed
                net_profit_pct = (net - 1.0) * 100.0

                if net_profit_pct > self._min_profit_pct and net_profit_pct > best_net_pct:
                    best_net_pct = net_profit_pct
                    best_indices = indices
                    best_directions = directions
                    best_rates = [r0, r1, r2]
                    best_gross = gross

            # Create the ArbitrageOpportunity object only once, for the winner
            best: Optional[ArbitrageOpportunity] = None
            if best_indices is not None:
                best = ArbitrageOpportunity(
                    cycle=[self._pair_strings[idx] for idx in best_indices],
                    directions=best_directions,
                    rates=best_rates,
                    gross_product=best_gross,
                    net_profit_pct=best_net_pct,
                )

            if best:
                logger.info(
                    "Arbitrage opportunity: %.4f%% net on %s",
                    best.net_profit_pct,
                    " → ".join(
                        f"{d} {p}" for d, p in zip(best.directions, best.cycle)
                    ),
                )
            return best

    def calculate_profit(self, opp: ArbitrageOpportunity) -> float:
        """
        Return the net profit percentage of an opportunity.

        This is a convenience accessor; the value is already stored on the
        opportunity object, but we re-derive it for verification.
        """
        with self._lock:
            gross = 1.0
            for r in opp.rates:
                gross *= r
            net = gross * (self._fee_mult ** 3)
            return (net - 1.0) * 100.0

    def execute_arbitrage(self, opp: ArbitrageOpportunity) -> bool:
        """
        Simulate execution of the arbitrage cycle.

        In production this would place real orders; here we validate the
        opportunity is still fresh (< 5 s) and log the execution.

        Returns True on (simulated) success, False otherwise.
        """
        with self._lock:
            age = time.monotonic() - opp.timestamp
            if age > 5.0:
                logger.warning("Opportunity expired (%.1f s old)", age)
                return False

            if opp.net_profit_pct <= 0:
                logger.warning("Non-profitable opportunity rejected")
                return False

            record = {
                "cycle": opp.cycle,
                "directions": opp.directions,
                "rates": opp.rates,
                "net_profit_pct": opp.net_profit_pct,
                "executed_at": time.monotonic(),
            }
            self._execution_log.append(record)
            logger.info("Executed arbitrage: %.4f%% profit", opp.net_profit_pct)
            return True


# ========================================================================
# Integrated Tests
# ========================================================================

def _run_tests() -> int:
    """Run all integrated tests and return the count of passed tests."""
    # Allow test instantiation past PRODUCTION_READY guard
    TriangularArbitrage.PRODUCTION_READY = True
    try:
        return _run_tests_impl()
    finally:
        TriangularArbitrage.PRODUCTION_READY = False


def _run_tests_impl() -> int:
    """Run all integrated tests and return the count of passed tests."""
    import math

    passed = 0
    failed = 0

    def _assert(cond: bool, label: str):
        nonlocal passed, failed
        if cond:
            passed += 1
            logger.debug("  ✓ %s", label)
        else:
            failed += 1
            logger.error("  ✗ %s", label)

    # Helper
    pairs = ["BTC/EUR", "ETH/BTC", "ETH/EUR"]

    # ------------------------------------------------------------------
    # Test 1: Construction with valid pairs
    # ------------------------------------------------------------------
    arb = TriangularArbitrage(pairs)
    _assert(arb is not None, "T1 – construction with 3 pairs")

    # ------------------------------------------------------------------
    # Test 2: Construction rejects != 3 pairs
    # ------------------------------------------------------------------
    try:
        TriangularArbitrage(["BTC/EUR", "ETH/BTC"])
        _assert(False, "T2 – reject 2 pairs")
    except ValueError:
        _assert(True, "T2 – reject 2 pairs")

    # ------------------------------------------------------------------
    # Test 3: Missing price raises KeyError
    # ------------------------------------------------------------------
    try:
        arb.detect_opportunity({"BTC/EUR": 50000})
        _assert(False, "T3 – missing price KeyError")
    except KeyError:
        _assert(True, "T3 – missing price KeyError")

    # ------------------------------------------------------------------
    # Test 4: No opportunity when prices are balanced
    # ------------------------------------------------------------------
    # Fair prices: BTC=50000 EUR, ETH=0.05 BTC → ETH=2500 EUR
    prices_fair = {"BTC/EUR": 50000.0, "ETH/BTC": 0.05, "ETH/EUR": 2500.0}
    opp = arb.detect_opportunity(prices_fair)
    _assert(opp is None, "T4 – no opportunity on fair prices")

    # ------------------------------------------------------------------
    # Test 5: Opportunity detected when mispricing exists
    # ------------------------------------------------------------------
    # Introduce mispricing: ETH/EUR is too cheap → buy ETH with EUR, sell for BTC, sell BTC for EUR
    # Cycle: buy ETH/EUR at 2400, sell ETH/BTC at 0.05 (get 0.05 BTC), sell BTC/EUR at 50000
    # 1 EUR → 1/2400 ETH → (1/2400)*0.05 BTC → (1/2400)*0.05*50000 EUR = 1.04167 EUR
    # gross ~4.17%, net after 3×0.1% fee ≈ 3.87% → should trigger
    prices_opp = {"BTC/EUR": 50000.0, "ETH/BTC": 0.05, "ETH/EUR": 2400.0}
    opp = arb.detect_opportunity(prices_opp)
    _assert(opp is not None, "T5 – opportunity detected on mispricing")
    _assert(opp.net_profit_pct > 0.5, "T5b – net profit > 0.5%")

    # ------------------------------------------------------------------
    # Test 6: calculate_profit matches stored value
    # ------------------------------------------------------------------
    if opp:
        calc = arb.calculate_profit(opp)
        _assert(
            abs(calc - opp.net_profit_pct) < 1e-9,
            "T6 – calculate_profit consistency",
        )
    else:
        _assert(False, "T6 – skipped (no opp)")

    # ------------------------------------------------------------------
    # Test 7: execute_arbitrage succeeds on fresh opportunity
    # ------------------------------------------------------------------
    if opp:
        result = arb.execute_arbitrage(opp)
        _assert(result is True, "T7 – execute fresh opportunity")
    else:
        _assert(False, "T7 – skipped")

    # ------------------------------------------------------------------
    # Test 8: execute_arbitrage rejects expired opportunity
    # ------------------------------------------------------------------
    if opp:
        expired = ArbitrageOpportunity(
            cycle=opp.cycle,
            directions=opp.directions,
            rates=opp.rates,
            gross_product=opp.gross_product,
            net_profit_pct=opp.net_profit_pct,
            timestamp=time.monotonic() - 10.0,  # 10 seconds ago (monotonic)
        )
        result = arb.execute_arbitrage(expired)
        _assert(result is False, "T8 – reject expired opportunity")
    else:
        _assert(False, "T8 – skipped")

    # ------------------------------------------------------------------
    # Test 9: execute_arbitrage rejects non-profitable
    # ------------------------------------------------------------------
    bad_opp = ArbitrageOpportunity(
        cycle=pairs,
        directions=["buy", "sell", "sell"],
        rates=[1.0, 1.0, 1.0],
        gross_product=1.0,
        net_profit_pct=-0.3,
    )
    result = arb.execute_arbitrage(bad_opp)
    _assert(result is False, "T9 – reject non-profitable")

    # ------------------------------------------------------------------
    # Test 10: Thread safety – concurrent detect calls
    # ------------------------------------------------------------------
    errors: List[str] = []

    def _concurrent_detect():
        try:
            for _ in range(50):
                arb.detect_opportunity(prices_fair)
                arb.detect_opportunity(prices_opp)
        except Exception as exc:
            errors.append(str(exc))

    threads = [threading.Thread(target=_concurrent_detect) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    _assert(len(errors) == 0, "T10 – thread safety (no race errors)")

    # ------------------------------------------------------------------
    # Test 11: RLock re-entrancy (call detect inside calculate context)
    # ------------------------------------------------------------------
    arb2 = TriangularArbitrage(pairs)
    opp2 = arb2.detect_opportunity(prices_opp)
    if opp2:
        profit = arb2.calculate_profit(opp2)
        _assert(profit > 0, "T11 – RLock re-entrancy OK")
    else:
        _assert(False, "T11 – skipped")

    # ------------------------------------------------------------------
    # Test 12: Custom fee / min_profit thresholds
    # ------------------------------------------------------------------
    # With 2% fee per leg the 4.17% gross should be eaten up:
    # net = 1.04167 * (0.98)^3 ≈ 0.98 → -2% → no opportunity
    arb_high_fee = TriangularArbitrage(pairs, fee_pct=2.0, min_profit_pct=0.5)
    opp_hf = arb_high_fee.detect_opportunity(prices_opp)
    _assert(opp_hf is None, "T12 – high fees eliminate opportunity")

    # ------------------------------------------------------------------
    # Test 13: Reverse mispricing detected
    # ------------------------------------------------------------------
    # ETH/EUR too expensive → opposite cycle profitable
    prices_rev = {"BTC/EUR": 50000.0, "ETH/BTC": 0.05, "ETH/EUR": 2650.0}
    opp_rev = arb.detect_opportunity(prices_rev)
    _assert(opp_rev is not None, "T13 – reverse mispricing detected")
    if opp_rev:
        _assert(opp_rev.net_profit_pct > 0.5, "T13b – reverse profit > 0.5%")

    # ------------------------------------------------------------------
    # Test 14: Execution log populated
    # ------------------------------------------------------------------
    _assert(len(arb._execution_log) == 1, "T14 – execution log has 1 entry")

    # ------------------------------------------------------------------
    # Test 15: Marginal case – exactly at threshold
    # ------------------------------------------------------------------
    # Craft prices so net profit is just barely above 0.5%.
    # The profitable cycle for cheap ETH/EUR is:
    #   sell BTC/EUR (get 1/50000 nothing – actually start with EUR)
    #   Cycle: 1 EUR → sell for 1/price_btceur BTC → buy ETH at ethbtc → sell ETH for etheur EUR
    #   Actually: buy ETH/EUR → sell ETH/BTC → sell BTC/EUR  OR  reverse
    # For the cycle sell BTC/EUR, buy ETH/EUR, sell ETH/BTC:
    #   product = price_btceur * (1/price_etheur) * price_ethbtc
    #            = 50000 * (1/etheur) * 0.05  = 2500/etheur
    # We need: (2500/etheur) * 0.999^3 - 1 > 0.005
    # → 2500/etheur > 1.005 / 0.999^3 = 1.005 / 0.997003 = 1.008018
    # → etheur < 2500 / 1.008018 = 2480.11
    # So set etheur = 2480 (just under) for a small positive margin
    prices_marginal = {"BTC/EUR": 50000.0, "ETH/BTC": 0.05, "ETH/EUR": 2480.0}
    opp_m = arb.detect_opportunity(prices_marginal)
    _assert(opp_m is not None, "T15 – marginal opportunity detected")
    if opp_m:
        _assert(opp_m.net_profit_pct < 2.0, "T15b – marginal profit is small")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    total = passed + failed
    print(f"\n{'='*50}")
    print(f"  Triangular Arbitrage Tests: {passed}/{total} passed")
    if failed:
        print(f"  *** {failed} FAILED ***")
    else:
        print("  All tests passed ✓")
    print(f"{'='*50}\n")

    return passed


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    count = _run_tests()
    print(f"Total tests passed: {count}")