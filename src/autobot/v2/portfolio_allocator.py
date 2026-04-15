"""Portfolio-level capital and risk allocator (Lot 5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class AllocationConstraints:
    max_capital_per_instance_ratio: float = 0.10
    max_capital_per_cluster_ratio: float = 0.35
    reserve_cash_ratio: float = 0.20
    max_total_active_risk_ratio: float = 0.50
    risk_per_capital_ratio: float = 0.02


@dataclass
class AllocationPlan:
    symbol_caps: Dict[str, float]
    total_allocated: float
    reserve_cash: float
    risk_budget_remaining: float
    reasons: Dict[str, str] = field(default_factory=dict)
    explain: Dict[str, float] = field(default_factory=dict)


class PortfolioAllocator:
    def __init__(self, constraints: AllocationConstraints) -> None:
        self.constraints = constraints

    def build_plan(
        self,
        ranked_candidates: List[str],
        total_capital: float,
        current_symbol_exposure: Dict[str, float],
        current_cluster_exposure: Dict[str, float],
        current_active_risk: float,
        symbol_to_cluster: Dict[str, str],
    ) -> AllocationPlan:
        total_capital = max(0.0, float(total_capital))
        reserve_cash = total_capital * self.constraints.reserve_cash_ratio
        investable = max(0.0, total_capital - reserve_cash)

        max_instance_abs = total_capital * self.constraints.max_capital_per_instance_ratio
        max_cluster_abs = total_capital * self.constraints.max_capital_per_cluster_ratio
        max_active_risk_abs = total_capital * self.constraints.max_total_active_risk_ratio
        risk_budget = max(0.0, max_active_risk_abs - max(0.0, float(current_active_risk)))

        symbol_caps: Dict[str, float] = {}
        reasons: Dict[str, str] = {}
        allocated = 0.0

        candidates = list(dict.fromkeys(ranked_candidates))
        for idx, symbol in enumerate(candidates):
            remaining_candidates = max(1, len(candidates) - idx)
            remaining_capital = max(0.0, investable - allocated)
            if remaining_capital <= 0.0:
                reasons[symbol] = "no_investable_capital"
                continue

            cluster = symbol_to_cluster.get(symbol, "OTHER")
            cluster_used = max(0.0, float(current_cluster_exposure.get(cluster, 0.0)))
            cluster_remaining = max(0.0, max_cluster_abs - cluster_used)

            symbol_used = max(0.0, float(current_symbol_exposure.get(symbol, 0.0)))
            instance_remaining = max(0.0, max_instance_abs - symbol_used)

            soft_target = remaining_capital / remaining_candidates
            cap = min(soft_target, remaining_capital, cluster_remaining, instance_remaining)
            if cap <= 0.0:
                reasons[symbol] = "instance_or_cluster_cap_reached"
                continue

            risk_for_cap = cap * self.constraints.risk_per_capital_ratio
            if risk_for_cap > risk_budget:
                cap = max(0.0, risk_budget / max(1e-9, self.constraints.risk_per_capital_ratio))

            if cap <= 0.0:
                reasons[symbol] = "risk_cap_reached"
                continue

            symbol_caps[symbol] = cap
            allocated += cap
            risk_budget = max(0.0, risk_budget - (cap * self.constraints.risk_per_capital_ratio))
            current_cluster_exposure[cluster] = cluster_used + cap

        return AllocationPlan(
            symbol_caps=symbol_caps,
            total_allocated=allocated,
            reserve_cash=reserve_cash,
            risk_budget_remaining=risk_budget,
            reasons=reasons,
            explain={
                "total_capital": total_capital,
                "investable_capital": investable,
                "max_instance_abs": max_instance_abs,
                "max_cluster_abs": max_cluster_abs,
                "max_active_risk_abs": max_active_risk_abs,
                "risk_per_capital_ratio": self.constraints.risk_per_capital_ratio,
            },
        )
