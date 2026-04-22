from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Protocol, Sequence

from .config import DECISION_JOURNAL_MAX_SYMBOLS, RANKING_MIN_SCORE_ACTIVATE
from .instance_activation_manager import ActivationInput, InstanceActivationManager
from .portfolio_allocator import AllocationPlan, PortfolioAllocator
from .risk_cluster_manager import RiskClusterManager
from .scalability_guard import GuardInput, ScalabilityGuard, ScalingState


class JournalLike(Protocol):
    def log(
        self,
        *,
        decision_type: str,
        source: str,
        symbols: List[str],
        reasons: List[str],
        context: Dict[str, Any],
        session_id: Optional[str] = None,
    ) -> None:
        ...


class InstanceLike(Protocol):
    id: str
    config: Any

    def is_running(self) -> bool:
        ...

    def get_profit_factor_days(self, days: int) -> float:
        ...

    def get_current_capital(self) -> float:
        ...


@dataclass
class ScalabilityMetrics:
    cpu_pct: float
    memory_pct: float
    ws_connected: bool
    ws_stale_seconds: float
    ws_total_lag: int
    execution_failure_rate: float
    reconciliation_mismatch_ratio: float
    kill_switch_tripped: bool
    pf_degraded: bool
    validation_degraded: bool


@dataclass
class ActivationContext:
    ranked_symbols: List[str]
    scored_map: Dict[str, Dict[str, Any]]
    guard_state: ScalingState
    health_score: float
    running_instances: int
    now_ts: float


@dataclass
class ActivationResult:
    target_instances: int
    payload: Dict[str, Any]
    rejected_symbols: List[str]


class DecisionJournalService:
    def __init__(self, journal: JournalLike, enabled: bool) -> None:
        self.journal = journal
        self.enabled = enabled

    @staticmethod
    def fingerprint(payload: Any) -> str:
        try:
            return json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
        except Exception:
            return repr(payload)

    def major_decision(
        self,
        *,
        decision_type: str,
        source: str,
        symbols: Optional[List[str]] = None,
        reasons: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self.enabled:
            return
        self.journal.log(
            decision_type=decision_type,
            source=source,
            symbols=symbols or [],
            reasons=reasons or [],
            context=context or {},
            session_id=os.getenv("DECISION_JOURNAL_SESSION_ID", "").strip() or None,
        )

    def rejected_opportunity(
        self,
        *,
        reason: str,
        source: str,
        symbol: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        symbols = [str(symbol)] if symbol else []
        self.major_decision(
            decision_type="rejected_opportunity",
            source=source,
            symbols=symbols,
            reasons=[reason],
            context=context or {},
        )


class ScalabilityGuardService:
    def __init__(self, guard: Optional[ScalabilityGuard]) -> None:
        self.guard = guard

    def evaluate(self, metrics: ScalabilityMetrics):
        if self.guard is None:
            return None
        return self.guard.evaluate(
            GuardInput(
                cpu_pct=metrics.cpu_pct,
                memory_pct=metrics.memory_pct,
                ws_connected=metrics.ws_connected,
                ws_stale_seconds=metrics.ws_stale_seconds,
                ws_total_lag=metrics.ws_total_lag,
                execution_failure_rate=metrics.execution_failure_rate,
                reconciliation_mismatch_ratio=metrics.reconciliation_mismatch_ratio,
                kill_switch_tripped=metrics.kill_switch_tripped,
                pf_degraded=metrics.pf_degraded,
                validation_degraded=metrics.validation_degraded,
            )
        )


class InstanceActivationService:
    def __init__(self, manager: Optional[InstanceActivationManager]) -> None:
        self.manager = manager

    def apply(self, context: ActivationContext) -> Optional[ActivationResult]:
        if self.manager is None:
            return None
        decision = self.manager.decide(
            ActivationInput(
                ranked_symbols=context.ranked_symbols,
                avg_rank_score=self._avg_score(context.ranked_symbols, context.scored_map),
                guard_state=context.guard_state,
                health_score=context.health_score,
                running_instances=context.running_instances,
                now_ts=context.now_ts,
            )
        )
        selected_set = {str(s) for s in decision.selected_symbols}
        rejected = [sym for sym in context.ranked_symbols if str(sym) not in selected_set]
        return ActivationResult(
            target_instances=max(1, int(decision.target_instances)),
            payload={
                "action": decision.action,
                "target_tier": int(decision.target_tier),
                "selected_symbols": list(decision.selected_symbols),
                "reason": decision.reason,
                "avg_rank_score": self._avg_score(context.ranked_symbols, context.scored_map),
            },
            rejected_symbols=rejected,
        )

    @staticmethod
    def _avg_score(ranked_symbols: Sequence[str], scored_map: Dict[str, Dict[str, Any]]) -> float:
        values = [
            float(scored_map.get(sym, {}).get("score", 0.0))
            for sym in ranked_symbols
            if sym in scored_map
        ]
        return (sum(values) / len(values)) if values else 0.0

    @staticmethod
    def below_threshold_symbols(ranked_symbols: Sequence[str], scored_map: Dict[str, Dict[str, Any]]) -> List[str]:
        return [
            sym
            for sym in ranked_symbols
            if sym in scored_map and float(scored_map.get(sym, {}).get("score", 0.0)) < float(RANKING_MIN_SCORE_ACTIVATE)
        ]


class PortfolioAllocationService:
    def __init__(self, allocator: Optional[PortfolioAllocator], cluster_manager: RiskClusterManager) -> None:
        self.allocator = allocator
        self.cluster_manager = cluster_manager

    def refresh_plan(
        self,
        *,
        instances: Iterable[InstanceLike],
        fallback_instances: Iterable[InstanceLike],
        ranked_symbols: List[str],
    ) -> Optional[AllocationPlan]:
        if self.allocator is None:
            return None

        active_instances = [inst for inst in instances if inst.is_running()]
        symbol_exposure: Dict[str, float] = {}
        for inst in active_instances:
            symbol = str(inst.config.symbol)
            symbol_exposure[symbol] = symbol_exposure.get(symbol, 0.0) + max(0.0, float(inst.get_current_capital()))

        cluster_exposure = self.cluster_manager.exposure_by_cluster(active_instances)
        total_capital = sum(max(0.0, float(inst.get_current_capital())) for inst in active_instances)
        if total_capital <= 0.0:
            total_capital = sum(max(0.0, float(inst.get_current_capital())) for inst in fallback_instances)

        current_active_risk = total_capital * self.allocator.constraints.risk_per_capital_ratio
        symbol_to_cluster = {sym: self.cluster_manager.cluster_for_symbol(sym) for sym in ranked_symbols}
        return self.allocator.build_plan(
            ranked_candidates=ranked_symbols,
            total_capital=total_capital,
            current_symbol_exposure=symbol_exposure,
            current_cluster_exposure=dict(cluster_exposure),
            current_active_risk=current_active_risk,
            symbol_to_cluster=symbol_to_cluster,
        )


class InstanceLifecycleService:
    @staticmethod
    def running_instances(instances: Iterable[InstanceLike]) -> List[InstanceLike]:
        return [inst for inst in instances if inst.is_running()]

    @staticmethod
    def select_worst_by_pf(instances: Iterable[InstanceLike], limit: int) -> List[InstanceLike]:
        return sorted(
            list(instances),
            key=lambda inst: float(getattr(inst, "get_profit_factor_days", lambda _d: 1.0)(30)),
        )[: max(0, int(limit))]


class BackgroundTasksService:
    def __init__(self) -> None:
        self.tasks: Dict[str, asyncio.Task] = {}

    def start(self, factories: Dict[str, Callable[[], Awaitable[Any]]]) -> None:
        for name, factory in factories.items():
            if name in self.tasks and not self.tasks[name].done():
                continue
            self.tasks[name] = asyncio.create_task(factory())

    async def stop(self, names: Optional[Iterable[str]] = None) -> None:
        targets = list(names) if names is not None else list(self.tasks.keys())
        for name in targets:
            task = self.tasks.get(name)
            if task is None:
                continue
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            self.tasks.pop(name, None)


def journal_symbol_cap() -> int:
    return max(1, int(DECISION_JOURNAL_MAX_SYMBOLS))
