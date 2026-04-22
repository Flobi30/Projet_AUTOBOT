"""Portfolio-level capital and risk allocator (Lot 5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Sequence


@dataclass(frozen=True)
class AllocationConstraints:
    max_capital_per_instance_ratio: float = 0.10
    max_capital_per_cluster_ratio: float = 0.35
    reserve_cash_ratio: float = 0.20
    max_total_active_risk_ratio: float = 0.50
    risk_per_capital_ratio: float = 0.02


@dataclass(frozen=True)
class WeightConstraints:
    min_weight: float = 0.05
    max_weight: float = 0.60
    reserve_cash_ratio: float = 0.20


@dataclass(frozen=True)
class SymbolMetrics:
    rolling_profit_factor: Optional[float] = None
    max_drawdown: Optional[float] = None
    realized_volatility: Optional[float] = None
    execution_cost: Optional[float] = None
    execution_stability: Optional[float] = None


@dataclass(frozen=True)
class ScoreWeights:
    profit_factor: float = 0.35
    drawdown: float = 0.20
    volatility: float = 0.15
    cost: float = 0.15
    execution_stability: float = 0.15


@dataclass
class AllocationPlan:
    symbol_caps: Dict[str, float]
    total_allocated: float
    reserve_cash: float
    risk_budget_remaining: float
    reasons: Dict[str, str] = field(default_factory=dict)
    explain: Dict[str, float] = field(default_factory=dict)


class AllocationWeightProvider:
    """Build score-aware symbol weights with explicit conservative fallback."""

    def __init__(
        self,
        *,
        score_weights: Optional[ScoreWeights] = None,
        constraints: Optional[WeightConstraints] = None,
        conservative_score: float = 0.25,
    ) -> None:
        self.score_weights = score_weights or ScoreWeights()
        self.constraints = constraints or WeightConstraints()
        self.conservative_score = max(0.0, float(conservative_score))

    def conservative_metrics(self) -> SymbolMetrics:
        return SymbolMetrics(
            rolling_profit_factor=1.0,
            max_drawdown=0.30,
            realized_volatility=0.60,
            execution_cost=0.003,
            execution_stability=0.60,
        )

    def legacy_baseline_metrics(self, symbol: str) -> SymbolMetrics:
        # Preserve legacy BTC/ETH overweight behaviour as baseline.
        up = symbol.upper()
        if "XBT" in up or "BTC" in up:
            return SymbolMetrics(1.20, 0.20, 0.45, 0.0018, 0.88)
        if "ETH" in up:
            return SymbolMetrics(1.14, 0.24, 0.50, 0.0020, 0.84)
        return SymbolMetrics(1.0, 0.30, 0.62, 0.0028, 0.74)

    def build_weighted_capital_plan(
        self,
        symbols: Sequence[str],
        total_capital: float,
        metrics_by_symbol: Optional[Mapping[str, SymbolMetrics]] = None,
    ) -> AllocationPlan:
        ordered_symbols = list(dict.fromkeys(symbols))
        total_capital = max(0.0, float(total_capital))
        reserve_cash = total_capital * self.constraints.reserve_cash_ratio
        investable = max(0.0, total_capital - reserve_cash)
        symbol_weights = self.compute_weights(ordered_symbols, metrics_by_symbol=metrics_by_symbol)
        symbol_caps = {s: round(investable * symbol_weights.get(s, 0.0), 2) for s in ordered_symbols}
        allocated = sum(symbol_caps.values())
        if symbol_caps:
            drift = round(investable - allocated, 2)
            if drift != 0.0:
                first = ordered_symbols[0]
                symbol_caps[first] = round(max(0.0, symbol_caps[first] + drift), 2)
                allocated = sum(symbol_caps.values())

        return AllocationPlan(
            symbol_caps=symbol_caps,
            total_allocated=allocated,
            reserve_cash=reserve_cash,
            risk_budget_remaining=0.0,
            reasons={},
            explain={
                "total_capital": total_capital,
                "reserve_cash_ratio": self.constraints.reserve_cash_ratio,
                "investable_capital": investable,
                "min_weight": self.constraints.min_weight,
                "max_weight": self.constraints.max_weight,
            },
        )

    def compute_weights(
        self,
        symbols: Sequence[str],
        metrics_by_symbol: Optional[Mapping[str, SymbolMetrics]] = None,
    ) -> Dict[str, float]:
        symbols = list(dict.fromkeys(symbols))
        if not symbols:
            return {}

        metrics_map = dict(metrics_by_symbol or {})
        scores: Dict[str, float] = {}
        data_quality: Dict[str, float] = {}
        for symbol in symbols:
            raw_metrics = metrics_map.get(symbol)
            if raw_metrics is None:
                # Keep legacy behaviour if no market telemetry is provided.
                raw_metrics = self.legacy_baseline_metrics(symbol)
            score, quality = self._score_symbol(raw_metrics)
            if quality < 1.0:
                # Explicit conservative fallback for missing data.
                score = min(score, self.conservative_score)
            scores[symbol] = max(0.0, score)
            data_quality[symbol] = quality

        constrained = self._normalize_with_constraints(scores)
        if not constrained:
            # Explicit conservative fallback in pathological case.
            equal = 1.0 / len(symbols)
            return {s: equal for s in symbols}

        if any(q < 1.0 for q in data_quality.values()):
            floor = min(0.20, self.constraints.max_weight)
            capped_symbols = [symbol for symbol, quality in data_quality.items() if quality < 1.0]
            excess = 0.0
            for symbol in capped_symbols:
                if constrained[symbol] > floor:
                    excess += constrained[symbol] - floor
                    constrained[symbol] = floor

            if excess > 0.0:
                eligible = [
                    s
                    for s in symbols
                    if s not in capped_symbols and constrained[s] < self.constraints.max_weight
                ]
                while excess > 1e-12 and eligible:
                    share = excess / len(eligible)
                    spent = 0.0
                    next_eligible: List[str] = []
                    for symbol in eligible:
                        room = self.constraints.max_weight - constrained[symbol]
                        add = min(room, share)
                        constrained[symbol] += add
                        spent += add
                        if room - add > 1e-12:
                            next_eligible.append(symbol)
                    excess = max(0.0, excess - spent)
                    eligible = next_eligible

            constrained = self._normalize_with_constraints(constrained)

        return constrained

    def _score_symbol(self, metrics: SymbolMetrics) -> tuple[float, float]:
        values = {
            "profit_factor": metrics.rolling_profit_factor,
            "drawdown": metrics.max_drawdown,
            "volatility": metrics.realized_volatility,
            "cost": metrics.execution_cost,
            "execution_stability": metrics.execution_stability,
        }
        defaults = self.conservative_metrics()
        default_values = {
            "profit_factor": defaults.rolling_profit_factor,
            "drawdown": defaults.max_drawdown,
            "volatility": defaults.realized_volatility,
            "cost": defaults.execution_cost,
            "execution_stability": defaults.execution_stability,
        }

        quality = 1.0
        for key, value in list(values.items()):
            if value is None:
                values[key] = default_values[key]
                quality *= 0.75

        profit_n = self._clamp((float(values["profit_factor"]) - 0.8) / 0.8)
        drawdown_n = self._clamp(1.0 - float(values["drawdown"]) / 0.40)
        vol_n = self._clamp(1.0 - float(values["volatility"]) / 1.00)
        cost_n = self._clamp(1.0 - float(values["cost"]) / 0.010)
        exec_n = self._clamp(float(values["execution_stability"]))

        sw = self.score_weights
        weighted = (
            sw.profit_factor * profit_n
            + sw.drawdown * drawdown_n
            + sw.volatility * vol_n
            + sw.cost * cost_n
            + sw.execution_stability * exec_n
        )
        return weighted, quality

    def _normalize_with_constraints(self, scores: Mapping[str, float]) -> Dict[str, float]:
        if not scores:
            return {}

        symbols = list(scores.keys())
        n = len(symbols)
        min_w = max(0.0, self.constraints.min_weight)
        max_w = min(1.0, self.constraints.max_weight)

        if min_w * n > 1.0:
            min_w = 1.0 / n
        if max_w * n < 1.0:
            max_w = 1.0 / n
        if min_w > max_w:
            min_w = max_w

        budget = 1.0 - (min_w * n)
        if budget <= 0.0:
            return {s: round(1.0 / n, 10) for s in symbols}

        normalized = {s: min_w for s in symbols}
        remaining_cap = {s: max(0.0, max_w - min_w) for s in symbols}
        priorities = {s: max(0.0, float(scores[s])) for s in symbols}
        remaining_budget = budget
        active = {s for s in symbols if remaining_cap[s] > 0.0}

        while remaining_budget > 1e-12 and active:
            p_sum = sum(priorities[s] for s in active)
            if p_sum <= 0.0:
                equal_share = remaining_budget / len(active)
                for s in list(active):
                    add = min(equal_share, remaining_cap[s])
                    normalized[s] += add
                    remaining_cap[s] -= add
                    remaining_budget -= add
                    if remaining_cap[s] <= 1e-12:
                        active.remove(s)
                continue

            exhausted: set[str] = set()
            spent_this_round = 0.0
            for s in list(active):
                wanted = remaining_budget * (priorities[s] / p_sum)
                add = min(wanted, remaining_cap[s])
                normalized[s] += add
                remaining_cap[s] -= add
                spent_this_round += add
                if remaining_cap[s] <= 1e-12:
                    exhausted.add(s)
            remaining_budget = max(0.0, remaining_budget - spent_this_round)
            active -= exhausted
            if spent_this_round <= 1e-12:
                break

        total = sum(normalized.values())
        if total <= 0:
            return {s: round(1.0 / n, 10) for s in symbols}
        return {s: normalized[s] / total for s in symbols}

    @staticmethod
    def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
        return max(low, min(high, value))


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
