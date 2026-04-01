"""
ShadowTradingManager – AutoBot V2
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Manages paper-trading instances running in parallel with live trading.
Instances are promoted to live when their Profit Factor (PF) exceeds 1.5
after a mode-specific validation period and a minimum of 30 trades.

Validation durations:
  • crypto      – 14 days  (2 weeks)
  • forex       – 21 days  (3 weeks)
  • commodities – 28 days  (4 weeks)

Thread-safety: all public methods are guarded by a single ``threading.RLock``.
Complexity: O(1) per instance for every operation (dict-based storage).
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── constants ────────────────────────────────────────────────────────────────

PF_PROMOTION_THRESHOLD: float = 1.5
MIN_TRADES_FOR_PROMOTION: int = 30
MAX_TRANSFER_RATIO: float = 0.25  # max 25% of paper_capital per promotion

class Mode(Enum):
    CRYPTO = "crypto"
    FOREX = "forex"
    COMMODITIES = "commodities"


VALIDATION_DAYS: Dict[Mode, int] = {
    Mode.CRYPTO: 14,
    Mode.FOREX: 21,
    Mode.COMMODITIES: 28,
}


class InstanceState(Enum):
    SHADOW = "shadow"
    PROMOTED = "promoted"


# ── data model ───────────────────────────────────────────────────────────────

@dataclass
class ShadowInstance:
    """Represents a single paper-trading shadow instance."""

    instance_id: str
    mode: Mode
    state: InstanceState = InstanceState.SHADOW
    pf: float = 0.0
    trades: int = 0
    registered_at: float = field(default_factory=time.monotonic)
    paper_capital: float = 0.0          # isolated paper capital
    promoted_at: Optional[float] = None
    # Individual trade results for internal PF verification
    _trade_results: List[float] = field(default_factory=list, repr=False)

    @property
    def age_days(self) -> float:
        """Elapsed days since registration (monotonic clock)."""
        return (time.monotonic() - self.registered_at) / 86_400

    @property
    def validation_days(self) -> int:
        return VALIDATION_DAYS[self.mode]

    @property
    def validation_complete(self) -> bool:
        return self.age_days >= self.validation_days

    @property
    def meets_pf_threshold(self) -> bool:
        return self.pf >= PF_PROMOTION_THRESHOLD

    def compute_pf(self) -> float:
        """Recalculate PF from individual trade results.

        PF = (winning_trades / total_trades) × (avg_win / avg_loss)
        Returns 0.0 when there are no trades or no losing trades.
        """
        if not self._trade_results:
            return 0.0

        wins = [t for t in self._trade_results if t > 0]
        losses = [t for t in self._trade_results if t <= 0]

        total = len(self._trade_results)
        if not wins or not losses:
            # No wins → PF 0; no losses → treat as infinite, cap at a high value
            return 0.0 if not wins else float("inf")

        win_ratio = len(wins) / total
        avg_win = sum(wins) / len(wins)
        avg_loss = abs(sum(losses) / len(losses))

        if avg_loss == 0:
            return float("inf")

        return win_ratio * (avg_win / avg_loss)


# ── manager ──────────────────────────────────────────────────────────────────

class ShadowTradingManager:
    """Manages shadow (paper) trading instances alongside live trading.

    All public methods are O(1) per instance and thread-safe (RLock).
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._instances: Dict[str, ShadowInstance] = {}
        # NOTE: _live_ids removed – use InstanceState.PROMOTED checks instead

    # ── public API ───────────────────────────────────────────────────────

    def register_instance(self, instance_id: str, mode: str) -> None:
        """Register a new shadow (paper-trading) instance.

        Parameters
        ----------
        instance_id : str
            Unique identifier for the instance.
        mode : str
            One of ``"crypto"``, ``"forex"``, ``"commodities"``.

        Raises
        ------
        ValueError
            If *instance_id* is already registered or *mode* is invalid,
            or conflicts with a promoted (live) instance.
        """
        resolved_mode = self._resolve_mode(mode)
        with self._lock:
            if instance_id in self._instances:
                existing = self._instances[instance_id]
                if existing.state == InstanceState.PROMOTED:
                    raise ValueError(
                        f"Instance '{instance_id}' conflicts with a live instance"
                    )
                raise ValueError(f"Instance '{instance_id}' already registered")
            inst = ShadowInstance(instance_id=instance_id, mode=resolved_mode)
            self._instances[instance_id] = inst
        logger.info("Shadow [%s]: registered (mode=%s, validation=%dd)",
                    instance_id, resolved_mode.value, inst.validation_days)

    def record_trade(self, instance_id: str, pnl: float) -> None:
        """Record an individual trade result for internal PF computation.

        Parameters
        ----------
        instance_id : str
            Instance to record the trade for.
        pnl : float
            Profit/loss of the trade (positive = win, negative/zero = loss).
        """
        with self._lock:
            inst = self._get_instance(instance_id)
            inst._trade_results.append(pnl)

    def update_performance(self, instance_id: str, pf: float, trades: int) -> bool:
        """Update the performance metrics for a shadow instance.

        If individual trades have been recorded via ``record_trade()``,
        the PF is recalculated internally and the passed *pf* is ignored.

        Returns ``True`` when the instance now qualifies for promotion
        (PF ≥ 1.5, validation period elapsed, and ≥ 30 trades).

        Raises
        ------
        KeyError
            If *instance_id* is not registered.
        ValueError
            If *pf* < 0 or *trades* < 0.
        """
        if pf < 0:
            raise ValueError("Profit factor must be non-negative")
        if trades < 0:
            raise ValueError("Trade count must be non-negative")

        with self._lock:
            inst = self._get_instance(instance_id)
            if inst.state == InstanceState.PROMOTED:
                already_promoted = True
            else:
                already_promoted = False
                # Recalculate PF from individual trades if available
                if inst._trade_results:
                    inst.pf = inst.compute_pf()
                    inst.trades = len(inst._trade_results)
                else:
                    inst.pf = pf
                    inst.trades = trades

                qualifies = (inst.meets_pf_threshold
                             and inst.validation_complete
                             and inst.trades >= MIN_TRADES_FOR_PROMOTION)
                current_pf = inst.pf
                days = inst.age_days

        if already_promoted:
            logger.warning("Shadow [%s]: already promoted – ignoring update",
                           instance_id)
            return False

        status = "ELIGIBLE" if qualifies else "SHADOW"
        logger.info(
            "Shadow [%s]: PF=%.2f après %d jours → %s",
            instance_id, current_pf, int(days), status,
        )
        return qualifies

    def should_promote_to_live(self, instance_id: str) -> bool:
        """Check whether a shadow instance should be promoted to live.

        Criteria:
        1. Instance still in SHADOW state.
        2. PF ≥ 1.5
        3. Validation period for its mode has elapsed.
        4. At least 30 trades recorded.
        """
        with self._lock:
            inst = self._get_instance(instance_id)
            if inst.state != InstanceState.SHADOW:
                return False
            return (inst.meets_pf_threshold
                    and inst.validation_complete
                    and inst.trades >= MIN_TRADES_FOR_PROMOTION)

    def transfer_capital(self, instance_id: str, amount: float) -> bool:
        """Transfer isolated paper capital to a live slot, promoting the instance.

        The transfer amount is capped at 25% of the instance's paper_capital.
        Returns ``True`` on success. Fails (returns ``False``) when:
        * The instance does not qualify for promotion.
        * The amount is non-positive.
        * The instance is already promoted (live conflict).

        On success the instance is marked ``PROMOTED``.
        """
        if amount <= 0:
            logger.error("Shadow [%s]: invalid transfer amount %.2f",
                         instance_id, amount)
            return False

        with self._lock:
            inst = self._get_instance(instance_id)

            if not self.should_promote_to_live(instance_id):
                deny_reason = "does not qualify for promotion"
                denied = True
            elif inst.state == InstanceState.PROMOTED:
                deny_reason = "conflict – id already promoted/live"
                denied = True
            else:
                denied = False
                # Cap transfer at 25% of current paper_capital (if any capital set)
                if inst.paper_capital > 0:
                    max_allowed = inst.paper_capital * MAX_TRANSFER_RATIO
                    effective_amount = min(amount, max_allowed)
                else:
                    effective_amount = amount

                # Perform the "transfer" – mark as promoted
                inst.paper_capital = effective_amount
                inst.state = InstanceState.PROMOTED
                inst.promoted_at = time.monotonic()
                result_pf = inst.pf
                result_days = int(inst.age_days)
                result_capital = effective_amount

        if denied:
            logger.warning("Shadow [%s]: transfer denied – %s",
                           instance_id, deny_reason)
            return False

        logger.info(
            "Shadow [%s]: PF=%.2f après %d jours → PROMOTION/LIVE (capital=%.2f)",
            instance_id, result_pf, result_days, result_capital,
        )
        return True

    def get_status(self) -> dict:
        """Return a snapshot of all instances and overall manager state."""
        with self._lock:
            instances = {}
            shadow_count = 0
            promoted_count = 0
            live_ids: list[str] = []

            for iid, inst in self._instances.items():
                is_shadow = inst.state == InstanceState.SHADOW
                is_promoted = inst.state == InstanceState.PROMOTED

                if is_shadow:
                    shadow_count += 1
                if is_promoted:
                    promoted_count += 1
                    live_ids.append(iid)

                instances[iid] = {
                    "mode": inst.mode.value,
                    "state": inst.state.value,
                    "pf": inst.pf,
                    "trades": inst.trades,
                    "age_days": round(inst.age_days, 2),
                    "validation_days": inst.validation_days,
                    "validation_complete": inst.validation_complete,
                    "meets_pf_threshold": inst.meets_pf_threshold,
                    "eligible_for_promotion": (
                        is_shadow
                        and inst.meets_pf_threshold
                        and inst.validation_complete
                        and inst.trades >= MIN_TRADES_FOR_PROMOTION
                    ),
                    "paper_capital": inst.paper_capital,
                    "promoted_at": inst.promoted_at,
                }

        return {
            "total_instances": len(instances),
            "shadow_count": shadow_count,
            "promoted_count": promoted_count,
            "live_ids": live_ids,
            "instances": instances,
        }

    # ── internals ────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_mode(mode: str) -> Mode:
        try:
            return Mode(mode.lower())
        except ValueError:
            valid = ", ".join(m.value for m in Mode)
            raise ValueError(
                f"Invalid mode '{mode}'. Must be one of: {valid}"
            ) from None

    def _get_instance(self, instance_id: str) -> ShadowInstance:
        try:
            return self._instances[instance_id]
        except KeyError:
            raise KeyError(f"Instance '{instance_id}' not found") from None


# ── integrated tests ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import traceback
    import concurrent.futures
    from unittest.mock import patch, PropertyMock

    _passed = 0
    _failed = 0
    _errors: list[str] = []

    def _run_test(name: str, fn):
        global _passed, _failed
        try:
            fn()
            _passed += 1
            print(f"  ✅ {name}")
        except Exception as exc:
            _failed += 1
            _errors.append(f"{name}: {exc}")
            print(f"  ❌ {name} — {exc}")
            traceback.print_exc()

    def _make_eligible(mgr: ShadowTradingManager, iid: str, mode: str = "crypto"):
        """Helper: register + fast-forward so instance qualifies for promotion."""
        mgr.register_instance(iid, mode)
        inst = mgr._instances[iid]
        # Backdate registration so validation period is elapsed
        inst.registered_at = time.monotonic() - (VALIDATION_DAYS[inst.mode] + 1) * 86_400
        mgr.update_performance(iid, 2.0, 50)

    # ── 1. Registration ──────────────────────────────────────────────────

    def test_register_crypto():
        m = ShadowTradingManager()
        m.register_instance("c1", "crypto")
        assert "c1" in m._instances
        assert m._instances["c1"].mode == Mode.CRYPTO

    def test_register_forex():
        m = ShadowTradingManager()
        m.register_instance("f1", "forex")
        assert m._instances["f1"].mode == Mode.FOREX

    def test_register_commodities():
        m = ShadowTradingManager()
        m.register_instance("x1", "commodities")
        assert m._instances["x1"].mode == Mode.COMMODITIES

    def test_register_duplicate():
        m = ShadowTradingManager()
        m.register_instance("dup", "crypto")
        try:
            m.register_instance("dup", "forex")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    def test_register_invalid_mode():
        m = ShadowTradingManager()
        try:
            m.register_instance("bad", "stocks")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    # ── 2. UpdatePerformance ─────────────────────────────────────────────

    def test_update_basic():
        m = ShadowTradingManager()
        m.register_instance("u1", "crypto")
        result = m.update_performance("u1", 1.0, 10)
        assert result is False  # not eligible yet

    def test_update_eligible():
        m = ShadowTradingManager()
        _make_eligible(m, "u2", "crypto")
        inst = m._instances["u2"]
        assert inst.pf >= PF_PROMOTION_THRESHOLD
        assert inst.trades >= MIN_TRADES_FOR_PROMOTION

    def test_update_pf_too_low():
        m = ShadowTradingManager()
        m.register_instance("u3", "crypto")
        inst = m._instances["u3"]
        inst.registered_at = time.monotonic() - 20 * 86_400
        result = m.update_performance("u3", 0.5, 50)
        assert result is False

    def test_update_too_early():
        m = ShadowTradingManager()
        m.register_instance("u4", "crypto")
        # Don't backdate → validation not complete
        result = m.update_performance("u4", 2.0, 50)
        assert result is False

    def test_update_already_promoted():
        m = ShadowTradingManager()
        _make_eligible(m, "u5", "crypto")
        m.transfer_capital("u5", 100.0)
        result = m.update_performance("u5", 3.0, 100)
        assert result is False

    # ── 3. ShouldPromote ─────────────────────────────────────────────────

    def test_should_promote_fresh():
        m = ShadowTradingManager()
        m.register_instance("sp1", "crypto")
        assert m.should_promote_to_live("sp1") is False

    def test_should_promote_ready():
        m = ShadowTradingManager()
        _make_eligible(m, "sp2", "crypto")
        assert m.should_promote_to_live("sp2") is True

    def test_should_promote_pf_insufficient():
        m = ShadowTradingManager()
        m.register_instance("sp3", "crypto")
        inst = m._instances["sp3"]
        inst.registered_at = time.monotonic() - 20 * 86_400
        m.update_performance("sp3", 1.0, 50)
        assert m.should_promote_to_live("sp3") is False

    def test_should_promote_already_promoted():
        m = ShadowTradingManager()
        _make_eligible(m, "sp4", "crypto")
        m.transfer_capital("sp4", 100.0)
        assert m.should_promote_to_live("sp4") is False

    def test_should_promote_pf_exactly_threshold():
        m = ShadowTradingManager()
        m.register_instance("sp5", "crypto")
        inst = m._instances["sp5"]
        inst.registered_at = time.monotonic() - 20 * 86_400
        m.update_performance("sp5", 1.5, 50)
        assert m.should_promote_to_live("sp5") is True

    # ── 4. TransferCapital ───────────────────────────────────────────────

    def test_transfer_success():
        m = ShadowTradingManager()
        _make_eligible(m, "tc1", "crypto")
        assert m.transfer_capital("tc1", 500.0) is True
        assert m._instances["tc1"].state == InstanceState.PROMOTED

    def test_transfer_not_qualified():
        m = ShadowTradingManager()
        m.register_instance("tc2", "crypto")
        assert m.transfer_capital("tc2", 500.0) is False

    def test_transfer_zero_amount():
        m = ShadowTradingManager()
        _make_eligible(m, "tc3", "crypto")
        assert m.transfer_capital("tc3", 0.0) is False

    def test_transfer_negative_amount():
        m = ShadowTradingManager()
        _make_eligible(m, "tc4", "crypto")
        assert m.transfer_capital("tc4", -100.0) is False

    # ── 5. GetStatus ─────────────────────────────────────────────────────

    def test_status_empty():
        m = ShadowTradingManager()
        s = m.get_status()
        assert s["total_instances"] == 0
        assert s["shadow_count"] == 0
        assert s["promoted_count"] == 0
        assert s["live_ids"] == []

    def test_status_populated():
        m = ShadowTradingManager()
        m.register_instance("gs1", "crypto")
        m.register_instance("gs2", "forex")
        s = m.get_status()
        assert s["total_instances"] == 2
        assert s["shadow_count"] == 2
        assert s["promoted_count"] == 0
        assert "gs1" in s["instances"]
        assert "gs2" in s["instances"]

    def test_status_after_promotion():
        m = ShadowTradingManager()
        _make_eligible(m, "gs3", "crypto")
        m.transfer_capital("gs3", 100.0)
        s = m.get_status()
        assert s["promoted_count"] == 1
        assert "gs3" in s["live_ids"]
        assert s["instances"]["gs3"]["state"] == "promoted"

    # ── 6. ValidationDurations ───────────────────────────────────────────

    def test_validation_crypto_14d():
        m = ShadowTradingManager()
        m.register_instance("vd1", "crypto")
        assert m._instances["vd1"].validation_days == 14

    def test_validation_forex_21d():
        m = ShadowTradingManager()
        m.register_instance("vd2", "forex")
        assert m._instances["vd2"].validation_days == 21

    def test_validation_commodities_28d():
        m = ShadowTradingManager()
        m.register_instance("vd3", "commodities")
        assert m._instances["vd3"].validation_days == 28

    def test_validation_complete_crypto():
        m = ShadowTradingManager()
        m.register_instance("vc1", "crypto")
        inst = m._instances["vc1"]
        assert inst.validation_complete is False
        inst.registered_at = time.monotonic() - 15 * 86_400
        assert inst.validation_complete is True

    def test_validation_complete_forex():
        m = ShadowTradingManager()
        m.register_instance("vc2", "forex")
        inst = m._instances["vc2"]
        inst.registered_at = time.monotonic() - 22 * 86_400
        assert inst.validation_complete is True

    def test_validation_complete_commodities():
        m = ShadowTradingManager()
        m.register_instance("vc3", "commodities")
        inst = m._instances["vc3"]
        inst.registered_at = time.monotonic() - 29 * 86_400
        assert inst.validation_complete is True

    # ── 7. ThreadSafety ──────────────────────────────────────────────────

    def test_concurrent_registrations():
        m = ShadowTradingManager()
        errors = []

        def _register(i: int):
            try:
                m.register_instance(f"conc_{i}", "crypto")
            except Exception as e:
                errors.append(e)

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
            list(pool.map(_register, range(100)))

        assert len(errors) == 0, f"Got {len(errors)} errors: {errors[:5]}"
        assert len(m._instances) == 100

    def test_concurrent_updates():
        m = ShadowTradingManager()
        for i in range(50):
            m.register_instance(f"cu_{i}", "crypto")
            inst = m._instances[f"cu_{i}"]
            inst.registered_at = time.monotonic() - 20 * 86_400

        errors = []

        def _update(i: int):
            try:
                m.update_performance(f"cu_{i}", 2.0, 50)
            except Exception as e:
                errors.append(e)

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
            list(pool.map(_update, range(50)))

        assert len(errors) == 0, f"Got {len(errors)} errors: {errors[:5]}"
        # All should now be eligible
        for i in range(50):
            assert m.should_promote_to_live(f"cu_{i}") is True

    # ── additional tests to reach 35+ ─────────────────────────────────

    def test_register_case_insensitive_mode():
        """Mode string should be case-insensitive (e.g. 'CRYPTO' → Mode.CRYPTO)."""
        m = ShadowTradingManager()
        m.register_instance("ci1", "CRYPTO")
        assert m._instances["ci1"].mode == Mode.CRYPTO

    def test_transfer_already_promoted_conflict():
        """Transfer on an already-promoted instance must fail."""
        m = ShadowTradingManager()
        _make_eligible(m, "tap1", "crypto")
        assert m.transfer_capital("tap1", 100.0) is True
        # Second transfer should fail
        assert m.transfer_capital("tap1", 50.0) is False

    def test_update_not_enough_trades():
        """PF and duration OK but trades < 30 → not eligible."""
        m = ShadowTradingManager()
        m.register_instance("ut1", "crypto")
        inst = m._instances["ut1"]
        inst.registered_at = time.monotonic() - 20 * 86_400
        result = m.update_performance("ut1", 2.0, 20)
        assert result is False
        assert m.should_promote_to_live("ut1") is False

    def test_status_mixed_shadow_and_promoted():
        """Status with a mix of shadow + promoted instances."""
        m = ShadowTradingManager()
        _make_eligible(m, "mix1", "crypto")
        m.register_instance("mix2", "forex")
        m.transfer_capital("mix1", 100.0)
        s = m.get_status()
        assert s["shadow_count"] == 1
        assert s["promoted_count"] == 1
        assert s["total_instances"] == 2
        assert "mix1" in s["live_ids"]
        assert "mix2" not in s["live_ids"]

    def test_validation_not_complete_at_boundary():
        """Exactly at validation_days the instance should be considered complete."""
        m = ShadowTradingManager()
        m.register_instance("vb1", "forex")
        inst = m._instances["vb1"]
        # Set exactly at 21 days
        inst.registered_at = time.monotonic() - 21 * 86_400
        assert inst.validation_complete is True
        # Set just under 21 days
        inst.registered_at = time.monotonic() - 20.99 * 86_400
        assert inst.validation_complete is False

    # ── runner ───────────────────────────────────────────────────────────

    all_tests = [
        # 1. Registration (5)
        ("Registration: crypto mode", test_register_crypto),
        ("Registration: forex mode", test_register_forex),
        ("Registration: commodities mode", test_register_commodities),
        ("Registration: duplicate ID", test_register_duplicate),
        ("Registration: invalid mode", test_register_invalid_mode),
        # 2. UpdatePerformance (5)
        ("UpdatePerformance: basic", test_update_basic),
        ("UpdatePerformance: eligible", test_update_eligible),
        ("UpdatePerformance: PF trop bas", test_update_pf_too_low),
        ("UpdatePerformance: trop tôt", test_update_too_early),
        ("UpdatePerformance: déjà promu", test_update_already_promoted),
        # 3. ShouldPromote (5)
        ("ShouldPromote: fresh instance", test_should_promote_fresh),
        ("ShouldPromote: ready", test_should_promote_ready),
        ("ShouldPromote: PF insuffisant", test_should_promote_pf_insufficient),
        ("ShouldPromote: déjà promu", test_should_promote_already_promoted),
        ("ShouldPromote: PF exactement 1.5", test_should_promote_pf_exactly_threshold),
        # 4. TransferCapital (4)
        ("TransferCapital: succès", test_transfer_success),
        ("TransferCapital: non qualifié", test_transfer_not_qualified),
        ("TransferCapital: montant nul", test_transfer_zero_amount),
        ("TransferCapital: montant négatif", test_transfer_negative_amount),
        # 5. GetStatus (3)
        ("GetStatus: vide", test_status_empty),
        ("GetStatus: peuplé", test_status_populated),
        ("GetStatus: après promotion", test_status_after_promotion),
        # 6. ValidationDurations (6)
        ("ValidationDurations: crypto 14j", test_validation_crypto_14d),
        ("ValidationDurations: forex 21j", test_validation_forex_21d),
        ("ValidationDurations: commodités 28j", test_validation_commodities_28d),
        ("ValidationDurations: crypto complete", test_validation_complete_crypto),
        ("ValidationDurations: forex complete", test_validation_complete_forex),
        ("ValidationDurations: commodities complete", test_validation_complete_commodities),
        # 7. ThreadSafety (2)
        ("ThreadSafety: 100 registrations concurrents", test_concurrent_registrations),
        ("ThreadSafety: 50 updates concurrents", test_concurrent_updates),
        # 8. Additional (5)
        ("Registration: case-insensitive mode", test_register_case_insensitive_mode),
        ("TransferCapital: already promoted conflict", test_transfer_already_promoted_conflict),
        ("UpdatePerformance: not enough trades", test_update_not_enough_trades),
        ("GetStatus: mixed shadow+promoted", test_status_mixed_shadow_and_promoted),
        ("ValidationDurations: boundary check", test_validation_not_complete_at_boundary),
    ]

    print(f"\n{'='*60}")
    print(f" ShadowTradingManager — {len(all_tests)} tests intégrés")
    print(f"{'='*60}\n")

    for name, fn in all_tests:
        _run_test(name, fn)

    print(f"\n{'='*60}")
    print(f" Résultat: {_passed} ✅  /  {_failed} ❌  (total: {len(all_tests)})")
    if _errors:
        print(f"\n Échecs:")
        for e in _errors:
            print(f"   • {e}")
    print(f"{'='*60}\n")

    exit(0 if _failed == 0 else 1)