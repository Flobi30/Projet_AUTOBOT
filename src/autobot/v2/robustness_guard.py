from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import mean, pstdev
from typing import Dict, List


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

    def data_snooping_control(self, trade_pnls: List[float], trials: int = 20) -> Dict[str, float]:
        trade_pnls = [v for v in trade_pnls if math.isfinite(v)]
        if len(trade_pnls) < 20:
            return {"dsr": -1.0, "pbo_proxy": 1.0, "pass": 0.0}

        mu = mean(trade_pnls)
        sigma = pstdev(trade_pnls) or 1e-9
        sharpe = (mu / sigma) * math.sqrt(len(trade_pnls))
        penalty = math.sqrt(2.0 * math.log(max(2, trials)))
        dsr = max(-10.0, min(10.0, sharpe - penalty))

        # PBO proxy: % of tail windows with negative PF
        tail = max(10, len(trade_pnls) // 4)
        negatives = 0
        checks = 0
        for i in range(0, len(trade_pnls) - tail + 1, max(1, tail // 3)):
            checks += 1
            if self._profit_factor(trade_pnls[i:i + tail]) < 1.0:
                negatives += 1
        pbo_proxy = (negatives / checks) if checks else 1.0
        ok = 1.0 if (dsr > 0.0 and pbo_proxy <= 0.5) else 0.0
        return {"dsr": float(dsr), "pbo_proxy": float(pbo_proxy), "pass": ok}

    def evaluate(self, trade_pnls: List[float]) -> Dict[str, float]:
        trade_pnls = [v for v in trade_pnls if math.isfinite(v)]
        wf = self.walk_forward(trade_pnls)
        ds = self.data_snooping_control(trade_pnls)
        passed = bool(wf.passed and ds["pass"] > 0.5)
        return {
            "pass": 1.0 if passed else 0.0,
            "wf_folds": float(wf.folds),
            "wf_oos_pf": float(wf.oos_pf_mean),
            "dsr": float(ds["dsr"]),
            "pbo_proxy": float(ds["pbo_proxy"]),
        }
