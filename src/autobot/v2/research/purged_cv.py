"""Research-only purged cross-validation fold planning.

This module only defines temporal folds.  It does not fit a model, score a
strategy, or communicate with AUTOBOT's runtime.  Walk-forward remains the
authoritative out-of-sample method; purged CV is supplementary evidence for
future parameter/model research where labels can overlap in time.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Any, Iterable, Sequence

from .trade_journal import TradeRecord


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class PurgedObservation:
    observation_id: str
    start_at: datetime
    end_at: datetime

    def __post_init__(self) -> None:
        if not self.observation_id.strip():
            raise ValueError("observation_id is required")
        if _as_utc(self.end_at) < _as_utc(self.start_at):
            raise ValueError("end_at cannot be before start_at")


@dataclass(frozen=True)
class PurgedCVFold:
    fold_index: int
    test_observation_ids: tuple[str, ...]
    train_observation_ids: tuple[str, ...]
    purged_observation_ids: tuple[str, ...]
    embargoed_observation_ids: tuple[str, ...]
    test_start_at: str
    test_end_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PurgedCVPlan:
    observation_count: int
    requested_folds: int
    embargo_bars: int
    estimated_bar_seconds: float | None
    folds: tuple[PurgedCVFold, ...]
    status: str
    research_only: bool = True
    live_promotion_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_count": self.observation_count,
            "requested_folds": self.requested_folds,
            "embargo_bars": self.embargo_bars,
            "estimated_bar_seconds": self.estimated_bar_seconds,
            "folds": [fold.to_dict() for fold in self.folds],
            "status": self.status,
            "research_only": True,
            "live_promotion_allowed": False,
        }


def observations_from_trade_records(trades: Iterable[TradeRecord]) -> tuple[PurgedObservation, ...]:
    """Convert closed research trades into temporally labeled observations."""

    result = [
        PurgedObservation(
            observation_id=f"{trade.run_id}:{index}:{trade.symbol}:{trade.opened_at.isoformat()}",
            start_at=_as_utc(trade.opened_at),
            end_at=_as_utc(trade.closed_at),
        )
        for index, trade in enumerate(trades)
    ]
    return tuple(sorted(result, key=lambda item: (item.start_at, item.end_at, item.observation_id)))


def build_purged_cv_plan(
    observations: Sequence[PurgedObservation],
    *,
    folds: int = 5,
    embargo_bars: int = 1,
) -> PurgedCVPlan:
    """Create chronological test folds while purging overlapping labels.

    Train memberships may include observations on both sides of the test fold;
    consequently this plan is for research model selection only.  It must not
    replace AUTOBOT's chronological walk-forward performance validation.
    """

    if folds < 2:
        raise ValueError("folds must be at least two")
    if embargo_bars < 0:
        raise ValueError("embargo_bars cannot be negative")
    ordered = tuple(sorted(observations, key=lambda item: (item.start_at, item.end_at, item.observation_id)))
    if len(ordered) < folds * 2:
        return PurgedCVPlan(
            observation_count=len(ordered),
            requested_folds=folds,
            embargo_bars=embargo_bars,
            estimated_bar_seconds=_estimated_bar_seconds(ordered),
            folds=(),
            status="insufficient_observations",
        )
    chunk_size = len(ordered) // folds
    bar_seconds = _estimated_bar_seconds(ordered)
    plan: list[PurgedCVFold] = []
    for index in range(folds):
        test_start = index * chunk_size
        test_end = len(ordered) if index == folds - 1 else min(len(ordered), (index + 1) * chunk_size)
        test = ordered[test_start:test_end]
        test_start_at = test[0].start_at
        test_end_at = max(item.end_at for item in test)
        embargo_end = test_end_at + timedelta(seconds=(bar_seconds or 0.0) * embargo_bars)
        train: list[str] = []
        purged: list[str] = []
        embargoed: list[str] = []
        test_ids = {item.observation_id for item in test}
        for item in ordered:
            if item.observation_id in test_ids:
                continue
            overlaps_test = item.start_at <= test_end_at and item.end_at >= test_start_at
            is_embargoed = test_end_at < item.start_at <= embargo_end
            if overlaps_test:
                purged.append(item.observation_id)
            elif is_embargoed:
                embargoed.append(item.observation_id)
            else:
                train.append(item.observation_id)
        plan.append(
            PurgedCVFold(
                fold_index=index + 1,
                test_observation_ids=tuple(item.observation_id for item in test),
                train_observation_ids=tuple(train),
                purged_observation_ids=tuple(purged),
                embargoed_observation_ids=tuple(embargoed),
                test_start_at=test_start_at.isoformat(),
                test_end_at=test_end_at.isoformat(),
            )
        )
    return PurgedCVPlan(
        observation_count=len(ordered),
        requested_folds=folds,
        embargo_bars=embargo_bars,
        estimated_bar_seconds=bar_seconds,
        folds=tuple(plan),
        status="research_planning_only",
    )


def _estimated_bar_seconds(observations: Sequence[PurgedObservation]) -> float | None:
    starts = [item.start_at for item in observations]
    gaps = [
        max(0.0, (right - left).total_seconds())
        for left, right in zip(starts, starts[1:])
        if right > left
    ]
    return float(median(gaps)) if gaps else None
