"""Deterministic, research-only evaluation of sealed final holdout evidence.

This module deliberately sits after a physical holdout partition and before
any future promotion workflow.  It does not read market data, route orders,
write a registry, or change a strategy state.  Its only output is an
immutable, non-promotable research verdict that binds closed-trade metrics to
the sealed holdout identity and to explicitly supplied baseline outcomes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import math
from typing import Any, Mapping, Sequence

from .holdout_partition import HoldoutPartitionReference


HOLDOUT_EVALUATOR_SCHEMA_VERSION = 1
REQUIRED_BASELINES = frozenset({"no_trade", "buy_and_hold", "placebo"})
VERDICT_PASSED = "HOLDOUT_PASSED_RESEARCH_ONLY"
VERDICT_REJECTED = "REJECTED"
VERDICT_INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class HoldoutEvaluatorError(ValueError):
    """Raised when final-review evidence cannot be trusted."""


@dataclass(frozen=True)
class HoldoutProvenance:
    """Portable identity binding final metrics to one immutable holdout."""

    experiment_id: str
    partition_id: str
    partition_fingerprint: str
    holdout_snapshot_id: str
    holdout_snapshot_fingerprint: str
    source_snapshot_id: str
    source_snapshot_fingerprint: str
    code_commit: str
    feature_versions: Mapping[str, str]
    parameter_fingerprint: str
    cost_model_fingerprint: str
    fingerprint: str

    def __post_init__(self) -> None:
        for field_name in (
            "experiment_id",
            "partition_id",
            "partition_fingerprint",
            "holdout_snapshot_id",
            "holdout_snapshot_fingerprint",
            "source_snapshot_id",
            "source_snapshot_fingerprint",
            "code_commit",
            "parameter_fingerprint",
            "cost_model_fingerprint",
            "fingerprint",
        ):
            if not str(getattr(self, field_name) or "").strip():
                raise HoldoutEvaluatorError(f"{field_name} is required")
        normalized_features = {str(key).strip(): str(value).strip() for key, value in self.feature_versions.items()}
        if not normalized_features or any(not key or not value for key, value in normalized_features.items()):
            raise HoldoutEvaluatorError("feature_versions must contain non-empty versions")
        object.__setattr__(self, "feature_versions", dict(sorted(normalized_features.items())))
        if self.fingerprint != _fingerprint(self.identity_dict()):
            raise HoldoutEvaluatorError("provenance fingerprint does not match its immutable identity")

    @classmethod
    def from_partition(
        cls,
        partition: HoldoutPartitionReference,
        *,
        experiment_id: str,
        code_commit: str,
        feature_versions: Mapping[str, str],
        parameter_fingerprint: str,
        cost_model_fingerprint: str,
    ) -> "HoldoutProvenance":
        identity = {
            "schema_version": HOLDOUT_EVALUATOR_SCHEMA_VERSION,
            "experiment_id": experiment_id,
            "partition_id": partition.partition_id,
            "partition_fingerprint": partition.fingerprint,
            "holdout_snapshot_id": partition.holdout_snapshot_id,
            "holdout_snapshot_fingerprint": partition.holdout_snapshot_fingerprint,
            "source_snapshot_id": partition.source_snapshot_id,
            "source_snapshot_fingerprint": partition.source_snapshot_fingerprint,
            "code_commit": code_commit,
            "feature_versions": dict(sorted((str(key), str(value)) for key, value in feature_versions.items())),
            "parameter_fingerprint": parameter_fingerprint,
            "cost_model_fingerprint": cost_model_fingerprint,
        }
        return cls(**{key: value for key, value in identity.items() if key != "schema_version"}, fingerprint=_fingerprint(identity))

    def identity_dict(self) -> dict[str, Any]:
        return {
            "schema_version": HOLDOUT_EVALUATOR_SCHEMA_VERSION,
            "experiment_id": self.experiment_id,
            "partition_id": self.partition_id,
            "partition_fingerprint": self.partition_fingerprint,
            "holdout_snapshot_id": self.holdout_snapshot_id,
            "holdout_snapshot_fingerprint": self.holdout_snapshot_fingerprint,
            "source_snapshot_id": self.source_snapshot_id,
            "source_snapshot_fingerprint": self.source_snapshot_fingerprint,
            "code_commit": self.code_commit,
            "feature_versions": dict(self.feature_versions),
            "parameter_fingerprint": self.parameter_fingerprint,
            "cost_model_fingerprint": self.cost_model_fingerprint,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.identity_dict(), "fingerprint": self.fingerprint}


@dataclass(frozen=True)
class ClosedResearchTrade:
    """Already-closed research trade used only as final holdout evidence."""

    trade_id: str
    net_pnl_eur: float
    symbol: str | None = None
    period: str | None = None
    regime: str | None = None

    def __post_init__(self) -> None:
        if not str(self.trade_id or "").strip():
            raise HoldoutEvaluatorError("trade_id is required")
        if not math.isfinite(float(self.net_pnl_eur)):
            raise HoldoutEvaluatorError("net_pnl_eur must be finite")


@dataclass(frozen=True)
class BaselineOutcome:
    """Explicit, closed baseline outcome covering the exact holdout window."""

    name: str
    net_pnl_eur: float
    trade_count: int

    def __post_init__(self) -> None:
        if str(self.name or "").strip() not in REQUIRED_BASELINES:
            raise HoldoutEvaluatorError(f"unsupported baseline: {self.name}")
        if not math.isfinite(float(self.net_pnl_eur)):
            raise HoldoutEvaluatorError("baseline net_pnl_eur must be finite")
        if int(self.trade_count) < 0:
            raise HoldoutEvaluatorError("baseline trade_count cannot be negative")
        if self.name == "no_trade" and float(self.net_pnl_eur) != 0.0:
            raise HoldoutEvaluatorError("no_trade baseline must have zero net_pnl_eur")


@dataclass(frozen=True)
class HoldoutEvaluationConfig:
    min_closed_trades: int = 30
    max_positive_pnl_concentration: float = 0.60

    def __post_init__(self) -> None:
        if int(self.min_closed_trades) < 1:
            raise HoldoutEvaluatorError("min_closed_trades must be positive")
        if not 0.0 < float(self.max_positive_pnl_concentration) <= 1.0:
            raise HoldoutEvaluatorError("max_positive_pnl_concentration must be in (0, 1]")


@dataclass(frozen=True)
class HoldoutEvaluationArtifact:
    provenance: HoldoutProvenance
    verdict: str
    blockers: tuple[str, ...]
    trade_count: int
    net_pnl_eur: float
    profit_factor: float | None
    baseline_outcomes: Mapping[str, BaselineOutcome]
    concentration: Mapping[str, Mapping[str, Any]]
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False
    promotable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": HOLDOUT_EVALUATOR_SCHEMA_VERSION,
            "provenance": self.provenance.to_dict(),
            "verdict": self.verdict,
            "blockers": list(self.blockers),
            "trade_count": self.trade_count,
            "net_pnl_eur": self.net_pnl_eur,
            "profit_factor": self.profit_factor,
            "baseline_outcomes": {name: asdict(outcome) for name, outcome in sorted(self.baseline_outcomes.items())},
            "concentration": {name: dict(value) for name, value in sorted(self.concentration.items())},
            "research_only": True,
            "paper_capital_allowed": False,
            "live_allowed": False,
            "promotable": False,
        }


def evaluate_sealed_holdout(
    *,
    partition: HoldoutPartitionReference,
    provenance: HoldoutProvenance,
    closed_trades: Sequence[ClosedResearchTrade],
    baselines: Sequence[BaselineOutcome],
    config: HoldoutEvaluationConfig = HoldoutEvaluationConfig(),
) -> HoldoutEvaluationArtifact:
    """Evaluate final closed-trade evidence without any promotion side effect.

    Missing required baselines and insufficient samples produce conservative
    verdicts; malformed identity or trade data raises ``HoldoutEvaluatorError``
    before any result can be trusted.
    """

    _validate_partition_provenance(partition, provenance)
    trades = tuple(closed_trades)
    if len({trade.trade_id for trade in trades}) != len(trades):
        raise HoldoutEvaluatorError("closed holdout trade_ids must be unique")
    baseline_map = _baseline_map(baselines)
    blockers: list[str] = []
    missing_baselines = sorted(REQUIRED_BASELINES.difference(baseline_map))
    blockers.extend(f"required_baseline_missing:{name}" for name in missing_baselines)
    if len(trades) < config.min_closed_trades:
        blockers.append("insufficient_closed_trade_count")

    net_pnl = sum(float(trade.net_pnl_eur) for trade in trades)
    gross_profit = sum(max(float(trade.net_pnl_eur), 0.0) for trade in trades)
    gross_loss = -sum(min(float(trade.net_pnl_eur), 0.0) for trade in trades)
    profit_factor = None if gross_loss == 0.0 else gross_profit / gross_loss
    concentration = {
        dimension: _concentration(trades, dimension)
        for dimension in ("symbol", "period", "regime")
    }
    for dimension, assessment in concentration.items():
        max_share = assessment.get("max_positive_pnl_share")
        if max_share is not None and float(max_share) > config.max_positive_pnl_concentration:
            blockers.append(
                f"concentration_{dimension}_above_{config.max_positive_pnl_concentration:.4f}"
            )
    if not missing_baselines:
        best_baseline = max(float(item.net_pnl_eur) for item in baseline_map.values())
        if net_pnl <= best_baseline:
            blockers.append("does_not_beat_required_baselines")
    if net_pnl <= 0.0:
        blockers.append("non_positive_holdout_net_pnl")

    if "insufficient_closed_trade_count" in blockers:
        verdict = VERDICT_INSUFFICIENT_DATA
    elif blockers:
        verdict = VERDICT_REJECTED
    else:
        verdict = VERDICT_PASSED
    return HoldoutEvaluationArtifact(
        provenance=provenance,
        verdict=verdict,
        blockers=tuple(sorted(set(blockers))),
        trade_count=len(trades),
        net_pnl_eur=net_pnl,
        profit_factor=profit_factor,
        baseline_outcomes=baseline_map,
        concentration=concentration,
    )


def _validate_partition_provenance(partition: HoldoutPartitionReference, provenance: HoldoutProvenance) -> None:
    expected = {
        "partition_id": partition.partition_id,
        "partition_fingerprint": partition.fingerprint,
        "holdout_snapshot_id": partition.holdout_snapshot_id,
        "holdout_snapshot_fingerprint": partition.holdout_snapshot_fingerprint,
        "source_snapshot_id": partition.source_snapshot_id,
        "source_snapshot_fingerprint": partition.source_snapshot_fingerprint,
    }
    for field_name, expected_value in expected.items():
        if getattr(provenance, field_name) != expected_value:
            raise HoldoutEvaluatorError(f"provenance {field_name} does not match sealed holdout partition")


def _baseline_map(baselines: Sequence[BaselineOutcome]) -> dict[str, BaselineOutcome]:
    result: dict[str, BaselineOutcome] = {}
    for baseline in baselines:
        if baseline.name in result:
            raise HoldoutEvaluatorError(f"duplicate baseline: {baseline.name}")
        result[baseline.name] = baseline
    return result


def _concentration(trades: Sequence[ClosedResearchTrade], dimension: str) -> dict[str, Any]:
    attributed = [trade for trade in trades if str(getattr(trade, dimension) or "").strip()]
    if not attributed:
        return {"status": "UNAVAILABLE", "max_positive_pnl_share": None, "by_value": {}}
    positive_by_value: dict[str, float] = {}
    for trade in attributed:
        value = str(getattr(trade, dimension)).strip()
        positive_by_value[value] = positive_by_value.get(value, 0.0) + max(float(trade.net_pnl_eur), 0.0)
    total_positive = sum(positive_by_value.values())
    if total_positive <= 0.0:
        return {"status": "NO_POSITIVE_PNL", "max_positive_pnl_share": None, "by_value": positive_by_value}
    shares = {value: pnl / total_positive for value, pnl in sorted(positive_by_value.items())}
    return {
        "status": "ASSESSED",
        "max_positive_pnl_share": max(shares.values()),
        "by_value": shares,
    }


def _fingerprint(payload: Mapping[str, Any]) -> str:
    return sha256(json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()
