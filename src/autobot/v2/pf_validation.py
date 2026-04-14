"""
Lightweight PF validation helpers (baseline vs improved, OOS, sensitivity).

Designed for low-compute environments (Hetzner CX shared vCPU).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence


@dataclass(frozen=True)
class ValidationSlice:
    trade_count: int
    profit_factor: float
    expectancy: float
    net_pnl: float


def _metrics(pnls: Sequence[float]) -> ValidationSlice:
    gross_profit = sum(x for x in pnls if x > 0)
    gross_loss = abs(sum(x for x in pnls if x < 0))
    trade_count = len(pnls)
    pf = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
    expectancy = (sum(pnls) / trade_count) if trade_count else 0.0
    return ValidationSlice(
        trade_count=trade_count,
        profit_factor=float(pf),
        expectancy=float(expectancy),
        net_pnl=float(sum(pnls)),
    )


def walk_forward_validate(
    pnls: Sequence[float],
    train_size: int = 80,
    test_size: int = 40,
    step: int = 40,
    min_test_trades: int = 15,
) -> List[ValidationSlice]:
    """Compute rolling OOS slices over pnl sequence."""
    if train_size <= 0 or test_size <= 0 or step <= 0:
        return []
    out: List[ValidationSlice] = []
    n = len(pnls)
    start = 0
    while start + train_size + test_size <= n:
        test = pnls[start + train_size:start + train_size + test_size]
        if len(test) >= min_test_trades:
            out.append(_metrics(test))
        start += step
    return out


def apply_cost_sensitivity(
    pnls: Iterable[float],
    fee_slippage_penalty_per_trade: float,
) -> List[float]:
    """Stress-test pnls by applying a fixed penalty per trade."""
    return [float(x) - float(fee_slippage_penalty_per_trade) for x in pnls]

