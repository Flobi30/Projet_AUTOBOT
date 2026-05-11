"""Paper-only capital budget rebalancing.

This module plans budget moves between paper engines. It does not open,
close, or force trades; it only decides how much virtual budget each running
engine should receive based on opportunity quality and runtime performance.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.getenv(name)
    try:
        value = float(raw) if raw not in (None, "") else default
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    try:
        value = int(raw) if raw not in (None, "") else default
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


@dataclass(frozen=True)
class PaperCapitalRebalanceConfig:
    enabled: bool = True
    interval_seconds: int = 1800
    min_instance_eur: float = 25.0
    min_transfer_eur: float = 5.0
    max_move_pct: float = 25.0
    min_weight: float = 0.02
    max_weight: float = 0.30
    reserve_cash_pct: float = 0.0
    max_drawdown_pct: float = 20.0

    @classmethod
    def from_env(cls) -> "PaperCapitalRebalanceConfig":
        return cls(
            enabled=_env_bool("PAPER_DYNAMIC_CAPITAL_REBALANCE_ENABLED", True),
            interval_seconds=_env_int("PAPER_DYNAMIC_REBALANCE_INTERVAL_SECONDS", 1800, 60, 86_400),
            min_instance_eur=_env_float("PAPER_DYNAMIC_REBALANCE_MIN_INSTANCE_EUR", 25.0, 0.0, 1_000_000.0),
            min_transfer_eur=_env_float("PAPER_DYNAMIC_REBALANCE_MIN_TRANSFER_EUR", 5.0, 0.0, 1_000_000.0),
            max_move_pct=_env_float("PAPER_DYNAMIC_REBALANCE_MAX_MOVE_PCT", 25.0, 0.0, 100.0),
            min_weight=_env_float("PAPER_DYNAMIC_REBALANCE_MIN_WEIGHT", 0.02, 0.0, 1.0),
            max_weight=_env_float("PAPER_DYNAMIC_REBALANCE_MAX_WEIGHT", 0.30, 0.001, 1.0),
            reserve_cash_pct=_env_float("PAPER_DYNAMIC_REBALANCE_RESERVE_PCT", 0.0, 0.0, 95.0),
            max_drawdown_pct=_env_float("PAPER_DYNAMIC_REBALANCE_MAX_DRAWDOWN_PCT", 20.0, 1.0, 95.0),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "interval_seconds": self.interval_seconds,
            "min_instance_eur": self.min_instance_eur,
            "min_transfer_eur": self.min_transfer_eur,
            "max_move_pct": self.max_move_pct,
            "min_weight": self.min_weight,
            "max_weight": self.max_weight,
            "reserve_cash_pct": self.reserve_cash_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
        }


@dataclass(frozen=True)
class PaperInstanceCapital:
    instance_id: str
    symbol: str
    current_capital: float
    allocated_capital: float
    available_capital: float
    opportunity_score: float
    profit_factor: float = 1.0
    drawdown: float = 0.0
    open_positions: int = 0
    status: str = "running"


@dataclass(frozen=True)
class PaperCapitalTarget:
    instance_id: str
    symbol: str
    current_capital: float
    allocated_capital: float
    available_capital: float
    score: float
    weight: float
    target_capital: float
    delta: float
    reducible_capital: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "symbol": self.symbol,
            "current_capital": round(self.current_capital, 2),
            "allocated_capital": round(self.allocated_capital, 2),
            "available_capital": round(self.available_capital, 2),
            "score": round(self.score, 3),
            "weight": round(self.weight, 5),
            "target_capital": round(self.target_capital, 2),
            "delta": round(self.delta, 2),
            "reducible_capital": round(self.reducible_capital, 2),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class PaperCapitalTransfer:
    from_instance_id: str
    to_instance_id: str
    amount: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_instance_id": self.from_instance_id,
            "to_instance_id": self.to_instance_id,
            "amount": round(self.amount, 2),
            "reason": self.reason,
        }


@dataclass
class PaperCapitalRebalancePlan:
    enabled: bool
    applied: bool
    reason: str
    timestamp: str
    total_capital: float
    investable_capital: float
    reserve_cash: float
    targets: list[PaperCapitalTarget] = field(default_factory=list)
    transfers: list[PaperCapitalTransfer] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "applied": self.applied,
            "reason": self.reason,
            "timestamp": self.timestamp,
            "total_capital": round(self.total_capital, 2),
            "investable_capital": round(self.investable_capital, 2),
            "reserve_cash": round(self.reserve_cash, 2),
            "targets": [target.to_dict() for target in self.targets],
            "transfers": [transfer.to_dict() for transfer in self.transfers],
            "config": dict(self.config),
        }


class PaperCapitalReallocator:
    """Build bounded budget transfer plans for paper engines."""

    def __init__(self, config: PaperCapitalRebalanceConfig | None = None) -> None:
        self.config = config or PaperCapitalRebalanceConfig.from_env()

    def disabled_plan(self, reason: str) -> PaperCapitalRebalancePlan:
        return PaperCapitalRebalancePlan(
            enabled=False,
            applied=False,
            reason=reason,
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_capital=0.0,
            investable_capital=0.0,
            reserve_cash=0.0,
            config=self.config.to_dict(),
        )

    def build_plan(self, instances: Iterable[PaperInstanceCapital]) -> PaperCapitalRebalancePlan:
        items = [item for item in instances if item.current_capital > 0.0]
        total = sum(max(0.0, item.current_capital) for item in items)
        reserve = total * (self.config.reserve_cash_pct / 100.0)
        investable = max(0.0, total - reserve)
        if not self.config.enabled:
            return self._empty_plan("disabled", total, investable, reserve)
        if len(items) < 2:
            return self._empty_plan("not_enough_instances", total, investable, reserve)
        if investable <= 0.0:
            return self._empty_plan("no_investable_capital", total, investable, reserve)

        weights = self._weights(items)
        targets: list[PaperCapitalTarget] = []
        for item in items:
            weight = weights.get(item.instance_id, 0.0)
            raw_target = investable * weight
            protected_floor = max(item.allocated_capital, self.config.min_instance_eur)
            target_capital = max(protected_floor, raw_target)
            delta = target_capital - item.current_capital
            reducible = self._reducible_capital(item, target_capital)
            reason = "increase" if delta > 0 else "reduce" if delta < 0 else "hold"
            targets.append(
                PaperCapitalTarget(
                    instance_id=item.instance_id,
                    symbol=item.symbol,
                    current_capital=item.current_capital,
                    allocated_capital=item.allocated_capital,
                    available_capital=item.available_capital,
                    score=self._effective_score(item),
                    weight=weight,
                    target_capital=target_capital,
                    delta=delta,
                    reducible_capital=reducible,
                    reason=reason,
                )
            )

        transfers = self._build_transfers(targets)
        reason = "planned" if transfers else "no_eligible_transfer"
        return PaperCapitalRebalancePlan(
            enabled=True,
            applied=False,
            reason=reason,
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_capital=total,
            investable_capital=investable,
            reserve_cash=reserve,
            targets=targets,
            transfers=transfers,
            config=self.config.to_dict(),
        )

    def with_applied_transfers(
        self,
        plan: PaperCapitalRebalancePlan,
        applied_transfers: Iterable[PaperCapitalTransfer],
        *,
        reason: str | None = None,
    ) -> PaperCapitalRebalancePlan:
        transfers = list(applied_transfers)
        return PaperCapitalRebalancePlan(
            enabled=plan.enabled,
            applied=bool(transfers),
            reason=reason or ("applied" if transfers else plan.reason),
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_capital=plan.total_capital,
            investable_capital=plan.investable_capital,
            reserve_cash=plan.reserve_cash,
            targets=plan.targets,
            transfers=transfers,
            config=plan.config,
        )

    def _empty_plan(
        self,
        reason: str,
        total_capital: float,
        investable_capital: float,
        reserve_cash: float,
    ) -> PaperCapitalRebalancePlan:
        return PaperCapitalRebalancePlan(
            enabled=self.config.enabled,
            applied=False,
            reason=reason,
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_capital=total_capital,
            investable_capital=investable_capital,
            reserve_cash=reserve_cash,
            config=self.config.to_dict(),
        )

    def _weights(self, items: list[PaperInstanceCapital]) -> dict[str, float]:
        scores = {item.instance_id: self._effective_score(item) for item in items}
        return self._normalize_with_bounds(scores)

    def _effective_score(self, item: PaperInstanceCapital) -> float:
        opportunity = _clamp(item.opportunity_score, 0.0, 100.0)
        pf = item.profit_factor
        if pf == float("inf"):
            pf_score = 90.0
        else:
            pf_score = _clamp(((pf - 0.80) / 1.70) * 100.0, 0.0, 100.0)
        drawdown_pct = max(0.0, item.drawdown * 100.0)
        dd_score = _clamp(100.0 - (drawdown_pct / max(self.config.max_drawdown_pct, 1e-9) * 100.0), 0.0, 100.0)
        activity_bonus = 5.0 if item.open_positions > 0 else 0.0
        return _clamp((opportunity * 0.55) + (pf_score * 0.25) + (dd_score * 0.20) + activity_bonus, 0.0, 100.0)

    def _normalize_with_bounds(self, scores: Mapping[str, float]) -> dict[str, float]:
        if not scores:
            return {}
        ids = list(scores.keys())
        n = len(ids)
        min_w = max(0.0, self.config.min_weight)
        max_w = min(1.0, self.config.max_weight)
        if min_w * n > 1.0:
            min_w = 1.0 / n
        if max_w * n < 1.0:
            max_w = 1.0 / n
        if min_w > max_w:
            min_w = max_w

        budget = 1.0 - (min_w * n)
        if budget <= 0.0:
            return {instance_id: 1.0 / n for instance_id in ids}

        normalized = {instance_id: min_w for instance_id in ids}
        remaining_cap = {instance_id: max(0.0, max_w - min_w) for instance_id in ids}
        remaining = budget
        active = {instance_id for instance_id in ids if remaining_cap[instance_id] > 0.0}
        while remaining > 1e-12 and active:
            score_sum = sum(max(0.0, float(scores[instance_id])) for instance_id in active)
            spent = 0.0
            exhausted: set[str] = set()
            for instance_id in list(active):
                share = (1.0 / len(active)) if score_sum <= 0.0 else max(0.0, scores[instance_id]) / score_sum
                add = min(remaining * share, remaining_cap[instance_id])
                normalized[instance_id] += add
                remaining_cap[instance_id] -= add
                spent += add
                if remaining_cap[instance_id] <= 1e-12:
                    exhausted.add(instance_id)
            remaining = max(0.0, remaining - spent)
            active -= exhausted
            if spent <= 1e-12:
                break

        total = sum(normalized.values())
        if total <= 0.0:
            return {instance_id: 1.0 / n for instance_id in ids}
        return {instance_id: normalized[instance_id] / total for instance_id in ids}

    def _reducible_capital(self, item: PaperInstanceCapital, target_capital: float) -> float:
        protected = max(item.allocated_capital, self.config.min_instance_eur, target_capital)
        free_surplus = max(0.0, item.current_capital - protected)
        cycle_cap = item.current_capital * (self.config.max_move_pct / 100.0)
        return max(0.0, min(free_surplus, cycle_cap, item.available_capital))

    def _build_transfers(self, targets: list[PaperCapitalTarget]) -> list[PaperCapitalTransfer]:
        min_transfer = self.config.min_transfer_eur
        donors = sorted(
            [target for target in targets if target.delta < -min_transfer and target.reducible_capital >= min_transfer],
            key=lambda target: target.reducible_capital,
            reverse=True,
        )
        receivers = sorted(
            [target for target in targets if target.delta > min_transfer],
            key=lambda target: target.delta,
            reverse=True,
        )
        transfers: list[PaperCapitalTransfer] = []
        receiver_need = {target.instance_id: target.delta for target in receivers}
        for donor in donors:
            donor_left = donor.reducible_capital
            for receiver in receivers:
                if donor_left < min_transfer:
                    break
                need = receiver_need.get(receiver.instance_id, 0.0)
                if need < min_transfer:
                    continue
                amount = min(donor_left, need)
                if amount < min_transfer:
                    continue
                amount = round(amount, 2)
                transfers.append(
                    PaperCapitalTransfer(
                        from_instance_id=donor.instance_id,
                        to_instance_id=receiver.instance_id,
                        amount=amount,
                        reason="paper_score_rebalance",
                    )
                )
                donor_left -= amount
                receiver_need[receiver.instance_id] = max(0.0, need - amount)
        return transfers
