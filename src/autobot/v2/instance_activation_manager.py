"""Tier-based instance activation manager (Lot 4)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .scalability_guard import ScalingState


@dataclass(frozen=True)
class ActivationInput:
    ranked_symbols: List[str]
    avg_rank_score: float
    guard_state: ScalingState
    health_score: float
    running_instances: int
    now_ts: float


@dataclass
class ActivationDecision:
    action: str  # hold | promote | demote | freeze
    target_instances: int
    target_tier: int
    selected_symbols: List[str] = field(default_factory=list)
    reason: str = ""


class InstanceActivationManager:
    TIERS = (1, 2, 5, 10, 20, 30, 50, 80)

    def __init__(
        self,
        default_tier: int = 1,
        promote_score_min: float = 70.0,
        demote_score_max: float = 45.0,
        promote_health_min: float = 70.0,
        demote_health_max: float = 50.0,
        hysteresis_cycles: int = 2,
        cooldown_seconds: int = 1800,
    ) -> None:
        self.current_tier = self._normalize_tier(default_tier)
        self.promote_score_min = promote_score_min
        self.demote_score_max = demote_score_max
        self.promote_health_min = promote_health_min
        self.demote_health_max = demote_health_max
        self.hysteresis_cycles = max(1, int(hysteresis_cycles))
        self.cooldown_seconds = max(1, int(cooldown_seconds))
        self._promote_votes = 0
        self._demote_votes = 0
        self._last_change_ts = 0.0

    def decide(self, inp: ActivationInput) -> ActivationDecision:
        selected = list(inp.ranked_symbols[: self.current_tier])

        if inp.guard_state != ScalingState.ALLOW_SCALE_UP:
            self._promote_votes = 0
            self._demote_votes = 0
            return ActivationDecision(
                action="freeze",
                target_instances=min(inp.running_instances, self.current_tier),
                target_tier=self.current_tier,
                selected_symbols=selected,
                reason=f"guard={inp.guard_state.value}",
            )

        if (inp.now_ts - self._last_change_ts) < self.cooldown_seconds:
            return ActivationDecision(
                action="hold",
                target_instances=self.current_tier,
                target_tier=self.current_tier,
                selected_symbols=selected,
                reason="cooldown",
            )

        can_promote = self._can_promote(inp)
        should_demote = self._should_demote(inp)

        if can_promote:
            self._promote_votes += 1
            self._demote_votes = 0
            if self._promote_votes >= self.hysteresis_cycles:
                self._promote_votes = 0
                self._last_change_ts = inp.now_ts
                self.current_tier = self._next_tier(self.current_tier)
                return ActivationDecision(
                    action="promote",
                    target_instances=self.current_tier,
                    target_tier=self.current_tier,
                    selected_symbols=list(inp.ranked_symbols[: self.current_tier]),
                    reason="promote_thresholds",
                )
            return ActivationDecision(
                action="hold",
                target_instances=self.current_tier,
                target_tier=self.current_tier,
                selected_symbols=selected,
                reason="promote_hysteresis",
            )

        if should_demote:
            self._demote_votes += 1
            self._promote_votes = 0
            if self._demote_votes >= self.hysteresis_cycles:
                self._demote_votes = 0
                self._last_change_ts = inp.now_ts
                self.current_tier = self._prev_tier(self.current_tier)
                return ActivationDecision(
                    action="demote",
                    target_instances=self.current_tier,
                    target_tier=self.current_tier,
                    selected_symbols=list(inp.ranked_symbols[: self.current_tier]),
                    reason="demote_thresholds",
                )
            return ActivationDecision(
                action="hold",
                target_instances=self.current_tier,
                target_tier=self.current_tier,
                selected_symbols=selected,
                reason="demote_hysteresis",
            )

        self._promote_votes = 0
        self._demote_votes = 0
        return ActivationDecision(
            action="hold",
            target_instances=self.current_tier,
            target_tier=self.current_tier,
            selected_symbols=selected,
            reason="stable",
        )

    def _can_promote(self, inp: ActivationInput) -> bool:
        return (
            inp.avg_rank_score >= self.promote_score_min
            and inp.health_score >= self.promote_health_min
            and len(inp.ranked_symbols) >= self._next_tier(self.current_tier)
            and self.current_tier < self.TIERS[-1]
        )

    def _should_demote(self, inp: ActivationInput) -> bool:
        return (
            inp.avg_rank_score <= self.demote_score_max
            or inp.health_score <= self.demote_health_max
            or len(inp.ranked_symbols) < self.current_tier
        ) and self.current_tier > self.TIERS[0]

    def _next_tier(self, tier: int) -> int:
        for t in self.TIERS:
            if t > tier:
                return t
        return self.TIERS[-1]

    def _prev_tier(self, tier: int) -> int:
        prev = self.TIERS[0]
        for t in self.TIERS:
            if t >= tier:
                return prev
            prev = t
        return self.TIERS[-1]

    def _normalize_tier(self, tier: int) -> int:
        if tier <= self.TIERS[0]:
            return self.TIERS[0]
        for t in self.TIERS:
            if tier <= t:
                return t
        return self.TIERS[-1]
