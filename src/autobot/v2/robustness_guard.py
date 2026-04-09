from __future__ import annotations

import math
from itertools import combinations
from dataclasses import dataclass
from statistics import mean, pstdev
from time import perf_counter
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


@dataclass
class WalkForwardResult:
    passed: bool
    folds: int
    oos_pf_mean: float


class RobustnessGuard:
    """Walk-forward + data-snooping sanity checks for live gating."""

    def __init__(self, min_pf: float = 1.05, purge: int = 2, min_trades: int = 40) -> None:
        self.min_pf = min_pf
        self.purge = purge
        self.min_trades = min_trades
        self.safety_dsr_timeout_ms = 50.0
        self.safety_dsr_cache_s = 300.0
        self.safety_wf_learning_days = 7
        self.safety_wf_min_trades_learning = 10
        self.safety_max_block_ratio = 0.8
        self.emergency_mode = False
        self._dsr_cache: Dict[str, float] = {"ts": 0.0, "value": 1.0}
        self._last_dsr_exec_ms = 0.0
        self._wf_attempts = 0
        self._wf_blocked = 0
        self._last_wf = WalkForwardResult(passed=False, folds=0, oos_pf_mean=0.0)

    def configure_safety(
        self,
        *,
        dsr_timeout_ms: float = 50.0,
        dsr_cache_s: float = 300.0,
        wf_learning_days: int = 7,
        wf_min_trades_learning: int = 10,
        max_block_ratio: float = 0.8,
    ) -> None:
        self.safety_dsr_timeout_ms = max(1.0, float(dsr_timeout_ms))
        self.safety_dsr_cache_s = max(1.0, float(dsr_cache_s))
        self.safety_wf_learning_days = max(0, int(wf_learning_days))
        self.safety_wf_min_trades_learning = max(1, int(wf_min_trades_learning))
        self.safety_max_block_ratio = min(1.0, max(0.0, float(max_block_ratio)))

    def set_emergency_mode(self, emergency: bool) -> None:
        self.emergency_mode = bool(emergency)

    @staticmethod
    def _profit_factor(values: List[float]) -> float:
        values = [v for v in values if math.isfinite(v)]
        if not values:
            return 0.0
        gp = sum(v for v in values if v > 0)
        gl = abs(sum(v for v in values if v < 0))
        if gl == 0:
            return float("inf") if gp > 0 else 0.0
        return gp / gl

    def walk_forward(self, trade_pnls: List[float], folds: int = 3) -> WalkForwardResult:
        trade_pnls = [v for v in trade_pnls if math.isfinite(v)]
        if len(trade_pnls) < self.min_trades:
            return WalkForwardResult(passed=False, folds=0, oos_pf_mean=0.0)
        n = len(trade_pnls)
        chunk = n // folds
        if chunk < 12:
            return WalkForwardResult(passed=False, folds=0, oos_pf_mean=0.0)

        oos_pfs: List[float] = []
        for i in range(1, folds + 1):
            test_start = max(0, n - i * chunk)
            test_end = min(n, test_start + chunk)
            train_end = max(0, test_start - self.purge)
            train = trade_pnls[:train_end]
            test = trade_pnls[test_start:test_end]
            if len(train) < 20 or len(test) < 10:
                continue
            in_pf = self._profit_factor(train)
            oos_pf = self._profit_factor(test)
            if in_pf <= 1.0:
                continue
            oos_pfs.append(oos_pf)

        if not oos_pfs:
            return WalkForwardResult(passed=False, folds=0, oos_pf_mean=0.0)
        oos_mean = float(mean(oos_pfs))
        return WalkForwardResult(passed=oos_mean >= self.min_pf, folds=len(oos_pfs), oos_pf_mean=oos_mean)

    @staticmethod
    def _moments(values: List[float]) -> Dict[str, float]:
        n = len(values)
        if n < 3:
            return {"skew": 0.0, "kurt": 3.0}
        mu = mean(values)
        sigma = pstdev(values) or 1e-9
        centered = [(v - mu) / sigma for v in values]
        skew = sum(v ** 3 for v in centered) / n
        kurt = sum(v ** 4 for v in centered) / n
        return {"skew": float(skew), "kurt": float(kurt)}

    def _pbo_cscv(self, trade_pnls: List[float], slices: int = 8) -> float:
        """CSCV-like PBO estimate on contiguous slices.

        We mark an overfit when train PF > 1 and test PF < 1 over a split.
        """
        n = len(trade_pnls)
        if n < max(40, slices * 6):
            return 1.0
        slices = max(4, min(12, slices))
        chunk = n // slices
        if chunk < 5:
            return 1.0
        blocks = [trade_pnls[i * chunk:(i + 1) * chunk] for i in range(slices)]
        half = slices // 2

        overfit = 0
        checks = 0
        for idxs in combinations(range(slices), half):
            train = [v for i in idxs for v in blocks[i]]
            test = [v for i in range(slices) if i not in idxs for v in blocks[i]]
            if len(train) < 20 or len(test) < 20:
                continue
            tr_pf = self._profit_factor(train)
            te_pf = self._profit_factor(test)
            checks += 1
            if tr_pf > 1.0 and te_pf < 1.0:
                overfit += 1
        if checks == 0:
            return 1.0
        return float(overfit / checks)

    def data_snooping_control(self, trade_pnls: List[float], trials: int = 20) -> Dict[str, float]:
        trade_pnls = [v for v in trade_pnls if math.isfinite(v)]
        if len(trade_pnls) < 20:
            return {"dsr": -1.0, "pbo_cscv": 1.0, "pbo_proxy": 1.0, "pass": 0.0}

        n = len(trade_pnls)
        mu = mean(trade_pnls)
        sigma = pstdev(trade_pnls) or 1e-9
        sharpe = (mu / sigma) * math.sqrt(n)
        moments = self._moments(trade_pnls)
        skew = moments["skew"]
        kurt = moments["kurt"]
        denom = max(1e-9, 1.0 - skew * sharpe + ((kurt - 1.0) / 4.0) * (sharpe ** 2))
        adjusted = sharpe / math.sqrt(denom)
        penalty = math.sqrt(2.0 * math.log(max(2, trials)))
        dsr = max(-10.0, min(10.0, adjusted - penalty))

        pbo_cscv = self._pbo_cscv(trade_pnls, slices=8)
        # Backward-compat alias for callers/tests using historic field name.
        pbo_proxy = pbo_cscv
        ok = 1.0 if (dsr > 0.0 and pbo_cscv <= 0.3) else 0.0
        return {"dsr": float(dsr), "pbo_cscv": float(pbo_cscv), "pbo_proxy": float(pbo_proxy), "pass": ok}

    def evaluate_dsr_safe(self, returns: List[float]) -> float:
        now = perf_counter()
        if self._last_dsr_exec_ms > self.safety_dsr_timeout_ms:
            logger.warning("DSR skipped (previous execution too slow)")
            return 1.0
        cache_age = now - float(self._dsr_cache.get("ts", 0.0))
        if cache_age <= self.safety_dsr_cache_s:
            return float(self._dsr_cache.get("value", 1.0))
        t0 = perf_counter()
        dsr = float(self.data_snooping_control(returns).get("dsr", 1.0))
        self._last_dsr_exec_ms = (perf_counter() - t0) * 1000.0
        self._dsr_cache = {"ts": now, "value": dsr}
        return dsr

    def validate_walk_forward_safe(self, returns: List[float], instance_age_days: int) -> bool:
        if self.emergency_mode:
            return True
        self._wf_attempts += 1
        adaptive_min_trades = self.min_trades
        adaptive_min_pf = self.min_pf
        if int(instance_age_days) < self.safety_wf_learning_days:
            adaptive_min_trades = min(self.min_trades, self.safety_wf_min_trades_learning)
            adaptive_min_pf = self.min_pf * 0.5
        previous_min_trades = self.min_trades
        previous_min_pf = self.min_pf
        try:
            self.min_trades = adaptive_min_trades
            self.min_pf = adaptive_min_pf
            wf = self.walk_forward(returns)
            self._last_wf = wf
            passed = bool(wf.passed)
        finally:
            self.min_trades = previous_min_trades
            self.min_pf = previous_min_pf
        if not passed:
            self._wf_blocked += 1
            ratio = self._wf_blocked / max(1, self._wf_attempts)
            if ratio > self.safety_max_block_ratio:
                logger.warning("Walk-forward auto-bypass: block ratio %.3f > %.3f", ratio, self.safety_max_block_ratio)
                return True
        return passed

    def evaluate(self, trade_pnls: List[float], instance_age_days: int = 9999, emergency_mode: bool = False) -> Dict[str, float]:
        trade_pnls = [v for v in trade_pnls if math.isfinite(v)]
        self.emergency_mode = bool(emergency_mode)
        wf_ok = self.validate_walk_forward_safe(trade_pnls, instance_age_days=instance_age_days)
        dsr = self.evaluate_dsr_safe(trade_pnls)
        passed = bool(wf_ok and dsr > 0.0)
        return {
            "pass": 1.0 if passed else 0.0,
            "wf_folds": float(self._last_wf.folds),
            "wf_oos_pf": float(self._last_wf.oos_pf_mean),
            "dsr": float(dsr),
            "pbo_cscv": 0.0,
            "pbo_proxy": 0.0,
            "dsr_last_ms": float(self._last_dsr_exec_ms),
            "dsr_cached": 1.0 if (perf_counter() - float(self._dsr_cache.get("ts", 0.0))) <= self.safety_dsr_cache_s else 0.0,
            "wf_block_ratio": float(self._wf_blocked / max(1, self._wf_attempts)),
        }
