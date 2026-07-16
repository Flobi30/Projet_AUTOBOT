"""Research/shadow artifact governance, parity checks and drift safety.

This module is deliberately side-effect free.  It cannot send an order, enable
paper capital or promote a strategy.  Its only automatic outcomes are risk
reductions: observation, throttling, disabled new entries or quarantine.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from autobot.v2.contracts import (
    FeatureSnapshotReference,
    RiskMandateReference,
    StrategyArtifactReference,
    TargetPortfolio,
    contract_fingerprint,
)

from .experiment_registry import DEFAULT_EXPERIMENT_REGISTRY_PATH, ExperimentRegistry, ExperimentRegistryError


ARTIFACT_STATUSES = frozenset(
    {
        "RESEARCH",
        "REJECTED",
        "SHADOW_ELIGIBLE",
        "SHADOW",
        "THROTTLED",
        "QUARANTINED",
        "RETIRED",
    }
)
SHADOW_ACTIONS = ("NORMAL", "WATCH", "REDUCE", "DISABLE_NEW_ENTRIES", "QUARANTINE")
GRID_ALIASES = frozenset({"grid", "grid_async", "grid_core", "dynamic_grid"})
EXPERIMENT_BOUND_SHADOW_STATUSES = frozenset({"SHADOW_ELIGIBLE", "SHADOW", "THROTTLED", "QUARANTINED"})
ORDER_INTENT_SHADOW_ARTIFACT_STATUSES = frozenset({"SHADOW_ELIGIBLE", "SHADOW"})
DEFAULT_STRATEGY_ARTIFACT_REGISTRY_PATH = Path("data/research/strategy_artifacts.sqlite3")


class ShadowGovernanceError(ValueError):
    """Raised when shadow governance would weaken a safety invariant."""


@dataclass(frozen=True)
class StrategyArtifact:
    strategy_id: str
    strategy_version: str
    code_commit: str
    data_snapshot_id: str
    feature_versions: Mapping[str, str]
    parameters: Mapping[str, Any]
    risk_mandate_fingerprint: str
    validation_manifest_fingerprint: str
    feature_snapshots: tuple[FeatureSnapshotReference, ...] = ()
    risk_mandate: RiskMandateReference | None = None
    status: str = "RESEARCH"
    rollback_artifact_id: str | None = None
    experiment_id: str | None = None
    experiment_fingerprint: str | None = None
    human_approval_reference: str | None = None
    paper_capital_allowed: bool = False
    live_allowed: bool = False
    automatic_promotion_allowed: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "strategy_id",
            "strategy_version",
            "code_commit",
            "data_snapshot_id",
            "risk_mandate_fingerprint",
            "validation_manifest_fingerprint",
        ):
            if not str(getattr(self, field_name) or "").strip():
                raise ShadowGovernanceError(f"{field_name} is required")
        normalized_status = str(self.status).upper()
        if normalized_status not in ARTIFACT_STATUSES:
            raise ShadowGovernanceError(f"unsupported artifact status: {self.status}")
        if self.strategy_id.lower() in GRID_ALIASES and normalized_status != "RETIRED":
            raise ShadowGovernanceError("grid aliases must remain RETIRED")
        if self.paper_capital_allowed or self.live_allowed or self.automatic_promotion_allowed:
            raise ShadowGovernanceError("shadow artifact cannot permit paper, live or automatic promotion")
        snapshots = tuple(self.feature_snapshots)
        if any(not isinstance(item, FeatureSnapshotReference) for item in snapshots):
            raise ShadowGovernanceError("feature_snapshots must contain FeatureSnapshotReference values")
        snapshot_versions = _feature_versions_from_snapshots(snapshots)
        normalized_versions = {str(key): str(value) for key, value in self.feature_versions.items()}
        if snapshots and snapshot_versions != normalized_versions:
            raise ShadowGovernanceError("feature snapshot versions must match artifact feature_versions")
        if snapshots and self.data_snapshot_id != _data_snapshot_id_from_feature_snapshots(snapshots):
            raise ShadowGovernanceError("feature snapshots must match artifact data_snapshot_id")
        if normalized_status in EXPERIMENT_BOUND_SHADOW_STATUSES and not snapshots:
            raise ShadowGovernanceError("shadow artifact requires point-in-time feature snapshot evidence")
        risk_mandate = self.risk_mandate
        if risk_mandate is not None:
            if not isinstance(risk_mandate, RiskMandateReference):
                raise ShadowGovernanceError("risk_mandate must be a RiskMandateReference")
            if risk_mandate.strategy_id != self.strategy_id.lower():
                raise ShadowGovernanceError("risk mandate strategy_id must match artifact strategy_id")
            if risk_mandate.fingerprint != self.risk_mandate_fingerprint:
                raise ShadowGovernanceError("risk mandate fingerprint must match artifact risk_mandate_fingerprint")
        experiment_id = str(self.experiment_id or "").strip() or None
        experiment_fingerprint = str(self.experiment_fingerprint or "").strip() or None
        human_approval_reference = str(self.human_approval_reference or "").strip() or None
        if bool(experiment_id) != bool(experiment_fingerprint):
            raise ShadowGovernanceError("experiment_id and experiment_fingerprint must be supplied together")
        if normalized_status in EXPERIMENT_BOUND_SHADOW_STATUSES:
            if not experiment_id:
                raise ShadowGovernanceError("shadow artifact requires an experiment binding")
            if not human_approval_reference:
                raise ShadowGovernanceError("shadow artifact requires an explicit human approval reference")
            if risk_mandate is None:
                raise ShadowGovernanceError("shadow artifact requires immutable risk mandate evidence")
        object.__setattr__(self, "strategy_id", self.strategy_id.lower())
        object.__setattr__(self, "strategy_version", self.strategy_version.strip())
        object.__setattr__(self, "code_commit", self.code_commit.strip())
        object.__setattr__(self, "data_snapshot_id", self.data_snapshot_id.strip())
        object.__setattr__(self, "feature_versions", normalized_versions)
        object.__setattr__(self, "feature_snapshots", snapshots)
        object.__setattr__(self, "risk_mandate", risk_mandate)
        object.__setattr__(self, "parameters", dict(self.parameters))
        object.__setattr__(self, "status", normalized_status)
        object.__setattr__(self, "experiment_id", experiment_id)
        object.__setattr__(self, "experiment_fingerprint", experiment_fingerprint)
        object.__setattr__(self, "human_approval_reference", human_approval_reference)

    @property
    def artifact_id(self) -> str:
        return f"strategy_artifact_{self.fingerprint[:20]}"

    @property
    def fingerprint(self) -> str:
        return _fingerprint(asdict(self))

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["artifact_id"] = self.artifact_id
        payload["fingerprint"] = self.fingerprint
        payload["paper_capital_allowed"] = False
        payload["live_allowed"] = False
        payload["automatic_promotion_allowed"] = False
        return payload

    def to_order_intent_reference(self) -> StrategyArtifactReference:
        """Return the immutable provenance facts required by an OrderIntent.

        The returned object is non-executable.  Its purpose is to make a
        shadow intent reject any mismatch between its signal evidence and the
        strategy artifact registered for that experiment.
        """

        return StrategyArtifactReference(
            artifact_id=self.artifact_id,
            fingerprint=self.fingerprint,
            strategy_id=self.strategy_id,
            strategy_version=self.strategy_version,
            code_commit=self.code_commit,
            data_snapshot_id=self.data_snapshot_id,
            feature_versions=self.feature_versions,
            status=self.status,
            feature_snapshots=self.feature_snapshots,
            risk_mandate=self.risk_mandate,
        )


def strategy_artifact_reference_from_mapping(value: Mapping[str, Any]) -> StrategyArtifactReference:
    """Parse a serialized artifact only when its identity is self-consistent.

    This is intentionally pure and read-only: the runtime preview can validate
    immutable provenance without opening or mutating the registry database.
    The later shadow scheduler must still resolve the reference from the
    append-only registry before it can write a real shadow observation.
    """

    if not isinstance(value, Mapping):
        raise ShadowGovernanceError("strategy_artifact_required")
    payload = dict(value)
    claimed_artifact_id = str(payload.pop("artifact_id", "") or "").strip()
    claimed_fingerprint = str(payload.pop("fingerprint", "") or "").strip()
    if not claimed_artifact_id or not claimed_fingerprint:
        raise ShadowGovernanceError("strategy_artifact_identity_required")
    raw_snapshots = payload.get("feature_snapshots") or ()
    if not isinstance(raw_snapshots, (list, tuple)):
        raise ShadowGovernanceError("strategy_artifact_feature_snapshots_invalid")
    payload["feature_snapshots"] = tuple(
        feature_snapshot_reference_from_mapping(item) for item in raw_snapshots
    )
    raw_mandate = payload.get("risk_mandate")
    if raw_mandate is not None:
        payload["risk_mandate"] = risk_mandate_reference_from_mapping(raw_mandate)
    try:
        artifact = StrategyArtifact(**payload)
    except TypeError as exc:
        raise ShadowGovernanceError("strategy_artifact_payload_invalid") from exc
    if claimed_artifact_id != artifact.artifact_id:
        raise ShadowGovernanceError("strategy_artifact_id_mismatch")
    if claimed_fingerprint != artifact.fingerprint:
        raise ShadowGovernanceError("strategy_artifact_fingerprint_mismatch")
    return artifact.to_order_intent_reference()


def feature_snapshot_reference_from_mapping(value: Mapping[str, Any]) -> FeatureSnapshotReference:
    """Normalize persisted feature evidence without opening a mutable store.

    Materialized spot and derivatives manifests use the same provenance facts
    but historically named their snapshot fingerprint differently.  This
    adapter makes the boundary explicit and rejects any bundle that did not
    prove point-in-time runtime parity.
    """

    if not isinstance(value, Mapping):
        raise ShadowGovernanceError("feature_snapshot_reference_required")
    serialized_contract = "contract_version" in value
    if not serialized_contract:
        feature_count = int(value.get("feature_count") or 0)
        if feature_count <= 0:
            raise ShadowGovernanceError("feature_snapshot_feature_values_required")
        if value.get("parity_ok") is not True:
            raise ShadowGovernanceError("feature_snapshot_parity_not_proven")
    try:
        return FeatureSnapshotReference(
            feature_snapshot_id=str(value.get("feature_snapshot_id") or ""),
            fingerprint=str(value.get("feature_snapshot_fingerprint") or value.get("fingerprint") or ""),
            snapshot_kind=str(value.get("snapshot_kind") or "FEATURE_SNAPSHOT"),
            source_snapshot_id=str(value.get("source_snapshot_id") or ""),
            source_snapshot_fingerprint=str(value.get("source_snapshot_fingerprint") or ""),
            feature_registry_fingerprint=str(value.get("feature_registry_fingerprint") or ""),
            feature_versions=value.get("feature_versions") or {},
            runtime_parity_proven=value.get("runtime_parity_proven") is True,
            ingestion_time_unknown_count=int(value.get("ingestion_time_unknown_count") or 0),
        )
    except (TypeError, ValueError) as exc:
        raise ShadowGovernanceError("feature_snapshot_reference_invalid") from exc


def risk_mandate_reference_from_mapping(value: Mapping[str, Any]) -> RiskMandateReference:
    """Normalize serialized immutable risk evidence without loading mutable policy files."""

    if not isinstance(value, Mapping):
        raise ShadowGovernanceError("risk_mandate_reference_required")
    try:
        return RiskMandateReference(
            mandate_id=str(value.get("mandate_id") or ""),
            strategy_id=str(value.get("strategy_id") or ""),
            fingerprint=str(value.get("fingerprint") or ""),
            mode_allowed=str(value.get("mode_allowed") or ""),
            capital_max_eur=value.get("capital_max_eur"),
            expires_at=str(value.get("expires_at") or ""),
            human_approved_required_for_risk_increase=value.get("human_approved_required_for_risk_increase") is True,
            shadow_notional_max_eur=value.get("shadow_notional_max_eur", 0.0),
            paper_capital_allowed=value.get("paper_capital_allowed") is True,
            live_allowed=value.get("live_allowed") is True,
        )
    except (TypeError, ValueError) as exc:
        raise ShadowGovernanceError("risk_mandate_reference_invalid") from exc


def _feature_snapshots_from_experiment_environment(
    environment: Mapping[str, Any],
) -> tuple[FeatureSnapshotReference, ...]:
    payloads: list[Mapping[str, Any]] = []
    for key in ("feature_snapshot", "derivatives_snapshot"):
        value = environment.get(key)
        if value is None:
            continue
        if not isinstance(value, Mapping):
            raise ShadowGovernanceError(f"experiment {key} evidence is invalid")
        payloads.append(value)
    return tuple(feature_snapshot_reference_from_mapping(item) for item in payloads)


def _feature_versions_from_snapshots(
    snapshots: tuple[FeatureSnapshotReference, ...],
) -> dict[str, str]:
    versions: dict[str, str] = {}
    snapshot_ids: set[str] = set()
    for snapshot in snapshots:
        if snapshot.feature_snapshot_id in snapshot_ids:
            raise ShadowGovernanceError("feature snapshot ids must be unique")
        snapshot_ids.add(snapshot.feature_snapshot_id)
        for feature_id, version in snapshot.feature_versions.items():
            if feature_id in versions:
                raise ShadowGovernanceError("feature snapshots cannot overlap feature versions")
            versions[feature_id] = version
    return versions


def _data_snapshot_id_from_feature_snapshots(
    snapshots: tuple[FeatureSnapshotReference, ...],
) -> str:
    """Recreate the data identity used by manifested experiments.

    AUTOBOT currently supports either one canonical feature bundle or the
    explicit spot-plus-derivatives pair produced by the manifested experiment
    builder.  Rejecting other compositions is safer than quietly assigning an
    arbitrary combined identity.
    """

    if len(snapshots) == 1:
        return snapshots[0].source_snapshot_id
    if len(snapshots) != 2:
        raise ShadowGovernanceError("unsupported feature snapshot composition")
    by_kind = {snapshot.snapshot_kind: snapshot for snapshot in snapshots}
    if set(by_kind) != {"FEATURE_SNAPSHOT", "DERIVATIVES_POINT_IN_TIME"}:
        raise ShadowGovernanceError("unsupported feature snapshot composition")
    return "combined_" + sha256(
        json.dumps(
            {
                "spot": by_kind["FEATURE_SNAPSHOT"].source_snapshot_id,
                "derivatives": by_kind["DERIVATIVES_POINT_IN_TIME"].source_snapshot_id,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:16]


def build_strategy_artifact_from_experiment(
    *,
    experiment_registry: ExperimentRegistry,
    experiment_id: str,
    strategy_version: str,
    risk_mandate_fingerprint: str,
    validation_manifest_fingerprint: str,
    risk_mandate: RiskMandateReference | None = None,
    requested_status: str = "RESEARCH",
    human_approval_reference: str | None = None,
) -> StrategyArtifact:
    """Build an immutable artifact from append-only experiment evidence.

    This is the only supported construction path for a shadow-governed status.
    It cannot promote paper/live; a human reference authorizes only a research
    shadow artifact after all experiment gates have passed.
    """

    try:
        state = experiment_registry.get_state(experiment_id)
        manifest = experiment_registry.export_manifest(experiment_id)
    except ExperimentRegistryError as exc:
        raise ShadowGovernanceError(f"experiment binding unavailable: {exc}") from exc
    spec = manifest.get("experiment")
    if not isinstance(spec, Mapping):
        raise ShadowGovernanceError("experiment manifest is missing its immutable specification")
    status = str(requested_status).upper()
    if status not in ARTIFACT_STATUSES:
        raise ShadowGovernanceError(f"unsupported artifact status: {requested_status}")
    if status in EXPERIMENT_BOUND_SHADOW_STATUSES:
        if state.latest_stage != "SHADOW_REVIEW" or state.latest_status != "PASSED" or not state.terminal:
            raise ShadowGovernanceError("shadow artifact requires a passed terminal SHADOW_REVIEW experiment")
        if not experiment_registry.has_final_holdout_review(state.experiment_id):
            raise ShadowGovernanceError("shadow artifact requires immutable final holdout review evidence")
        if not str(human_approval_reference or "").strip():
            raise ShadowGovernanceError("shadow artifact requires an explicit human approval reference")
        if risk_mandate is None:
            raise ShadowGovernanceError("shadow artifact requires immutable risk mandate evidence")
        if risk_mandate.strategy_id != str(state.hypothesis_id).lower():
            raise ShadowGovernanceError("risk mandate strategy_id must match experiment hypothesis")
        if risk_mandate.fingerprint != str(risk_mandate_fingerprint).strip():
            raise ShadowGovernanceError("risk mandate fingerprint must match immutable risk mandate evidence")
    feature_versions = spec.get("feature_versions")
    parameters = spec.get("parameters")
    if not isinstance(feature_versions, Mapping) or not isinstance(parameters, Mapping):
        raise ShadowGovernanceError("experiment specification is missing feature versions or parameters")
    environment = spec.get("environment")
    if not isinstance(environment, Mapping):
        raise ShadowGovernanceError("experiment specification is missing its environment")
    snapshots = _feature_snapshots_from_experiment_environment(environment)
    if status in EXPERIMENT_BOUND_SHADOW_STATUSES and not snapshots:
        raise ShadowGovernanceError("shadow artifact requires point-in-time feature snapshot evidence")
    return StrategyArtifact(
        strategy_id=str(state.hypothesis_id),
        strategy_version=strategy_version,
        code_commit=str(spec.get("code_commit") or ""),
        data_snapshot_id=str(spec.get("data_snapshot_id") or ""),
        feature_versions={str(key): str(value) for key, value in feature_versions.items()},
        parameters=dict(parameters),
        risk_mandate_fingerprint=risk_mandate_fingerprint,
        validation_manifest_fingerprint=validation_manifest_fingerprint,
        feature_snapshots=snapshots,
        risk_mandate=risk_mandate,
        status=status,
        experiment_id=state.experiment_id,
        experiment_fingerprint=state.material_fingerprint,
        human_approval_reference=human_approval_reference,
    )


@dataclass(frozen=True)
class ShadowObservation:
    artifact_id: str
    observed_at: datetime
    data_available_at: datetime
    source_snapshot_id: str
    feature_fingerprint: str
    target_portfolio: TargetPortfolio

    def __post_init__(self) -> None:
        for field_name in ("artifact_id", "source_snapshot_id", "feature_fingerprint"):
            if not str(getattr(self, field_name) or "").strip():
                raise ShadowGovernanceError(f"{field_name} is required")
        for field_name in ("observed_at", "data_available_at"):
            value = getattr(self, field_name)
            if value.tzinfo is None or value.utcoffset() is None:
                raise ShadowGovernanceError(f"{field_name} must be timezone-aware")
            object.__setattr__(self, field_name, value.astimezone(timezone.utc))
        if self.observed_at < self.data_available_at:
            raise ShadowGovernanceError("shadow observation cannot precede data availability")


@dataclass(frozen=True)
class ShadowParityResult:
    status: str
    reasons: tuple[str, ...]
    batch_target_fingerprint: str
    shadow_target_fingerprint: str
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False


@dataclass(frozen=True)
class ShadowPerformanceWindow:
    trade_count: int
    rolling_profit_factor: float | None
    rolling_expectancy_eur: float | None
    max_drawdown_pct: float | None
    feature_drift_score: float | None
    cost_drift_bps: float | None
    data_age: timedelta

    def __post_init__(self) -> None:
        if self.trade_count < 0:
            raise ShadowGovernanceError("trade_count cannot be negative")
        if self.data_age < timedelta(0):
            raise ShadowGovernanceError("data_age cannot be negative")
        for field_name in (
            "rolling_profit_factor",
            "rolling_expectancy_eur",
            "max_drawdown_pct",
            "feature_drift_score",
            "cost_drift_bps",
        ):
            value = getattr(self, field_name)
            if value is not None and not math.isfinite(float(value)):
                raise ShadowGovernanceError(f"{field_name} must be finite when supplied")
        if self.feature_drift_score is not None and not 0.0 <= self.feature_drift_score <= 1.0:
            raise ShadowGovernanceError("feature_drift_score must be in [0, 1]")


@dataclass(frozen=True)
class ShadowSafetyPolicy:
    max_data_age: timedelta = timedelta(minutes=5)
    min_trade_count_for_performance: int = 50
    watch_profit_factor: float = 1.10
    reduce_profit_factor: float = 1.00
    disable_profit_factor: float = 0.90
    quarantine_profit_factor: float = 0.80
    reduce_drawdown_pct: float = 10.0
    disable_drawdown_pct: float = 15.0
    quarantine_drawdown_pct: float = 25.0
    reduce_feature_drift: float = 0.30
    disable_feature_drift: float = 0.55
    quarantine_feature_drift: float = 0.80
    watch_cost_drift_bps: float = 5.0
    reduce_cost_drift_bps: float = 10.0
    disable_cost_drift_bps: float = 20.0
    quarantine_cost_drift_bps: float = 40.0

    def __post_init__(self) -> None:
        if self.max_data_age <= timedelta(0) or self.min_trade_count_for_performance < 1:
            raise ShadowGovernanceError("shadow safety policy thresholds must be positive")
        if not (
            self.quarantine_profit_factor <= self.disable_profit_factor <= self.reduce_profit_factor <= self.watch_profit_factor
        ):
            raise ShadowGovernanceError("profit-factor thresholds must become stricter monotonically")
        if not (
            self.reduce_drawdown_pct <= self.disable_drawdown_pct <= self.quarantine_drawdown_pct
            and self.reduce_feature_drift <= self.disable_feature_drift <= self.quarantine_feature_drift
        ):
            raise ShadowGovernanceError("drawdown and drift thresholds must become stricter monotonically")
        cost_thresholds = (
            self.watch_cost_drift_bps,
            self.reduce_cost_drift_bps,
            self.disable_cost_drift_bps,
            self.quarantine_cost_drift_bps,
        )
        if any(not math.isfinite(float(value)) or float(value) < 0.0 for value in cost_thresholds):
            raise ShadowGovernanceError("cost drift thresholds must be finite and non-negative")
        if not (
            self.watch_cost_drift_bps
            <= self.reduce_cost_drift_bps
            <= self.disable_cost_drift_bps
            <= self.quarantine_cost_drift_bps
        ):
            raise ShadowGovernanceError("cost drift thresholds must become stricter monotonically")


@dataclass(frozen=True)
class ShadowSafetyDecision:
    action: str
    reasons: tuple[str, ...]
    next_artifact_status: str
    risk_increase_allowed: bool = False
    paper_capital_allowed: bool = False
    live_allowed: bool = False
    automatic_promotion_allowed: bool = False


class StrategyArtifactRegistry:
    """Append-only source of truth for versioned research/shadow artifacts."""

    def __init__(
        self,
        path: str | Path = DEFAULT_STRATEGY_ARTIFACT_REGISTRY_PATH,
        *,
        experiment_registry_path: str | Path = DEFAULT_EXPERIMENT_REGISTRY_PATH,
    ) -> None:
        self.path = Path(path)
        self.experiment_registry_path = Path(experiment_registry_path)

    def register(self, artifact: StrategyArtifact) -> str:
        self._validate_shadow_experiment_binding(artifact)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            self._initialize(connection)
            connection.execute(
                """
                INSERT OR IGNORE INTO strategy_artifacts
                    (artifact_id, fingerprint, strategy_id, status, artifact_json, recorded_at,
                     paper_capital_allowed, live_allowed, automatic_promotion_allowed)
                VALUES (?, ?, ?, ?, ?, ?, 0, 0, 0)
                """,
                (
                    artifact.artifact_id,
                    artifact.fingerprint,
                    artifact.strategy_id,
                    artifact.status,
                    _canonical_json(artifact.to_dict()),
                    _utc_now().isoformat(),
                ),
            )
            return artifact.artifact_id

    def _validate_shadow_experiment_binding(self, artifact: StrategyArtifact) -> None:
        if artifact.status not in EXPERIMENT_BOUND_SHADOW_STATUSES:
            return
        try:
            experiment_registry = ExperimentRegistry(self.experiment_registry_path)
            state = experiment_registry.get_state(str(artifact.experiment_id))
        except ExperimentRegistryError as exc:
            raise ShadowGovernanceError(f"shadow artifact experiment binding unavailable: {exc}") from exc
        if state.material_fingerprint != artifact.experiment_fingerprint:
            raise ShadowGovernanceError("shadow artifact experiment fingerprint mismatch")
        if state.latest_stage != "SHADOW_REVIEW" or state.latest_status != "PASSED" or not state.terminal:
            raise ShadowGovernanceError("shadow artifact experiment has not passed terminal SHADOW_REVIEW")
        if not experiment_registry.has_final_holdout_review(str(artifact.experiment_id)):
            raise ShadowGovernanceError("shadow artifact experiment lacks immutable final holdout review evidence")

    def record_safety_decision(self, artifact: StrategyArtifact, decision: ShadowSafetyDecision) -> bool:
        """Append one non-increasing-risk decision, rejecting action relaxation."""

        artifact_id = self.register(artifact)
        with self._connect() as connection:
            self._initialize(connection)
            previous = connection.execute(
                "SELECT action FROM strategy_safety_events WHERE artifact_id = ? ORDER BY recorded_at DESC, event_id DESC LIMIT 1",
                (artifact_id,),
            ).fetchone()
            if previous and SHADOW_ACTIONS.index(decision.action) < SHADOW_ACTIONS.index(str(previous[0])):
                raise ShadowGovernanceError("automatic shadow safety action cannot relax risk")
            payload = {
                "artifact_id": artifact_id,
                "action": decision.action,
                "reasons": list(decision.reasons),
                "next_artifact_status": decision.next_artifact_status,
            }
            fingerprint = _fingerprint(payload)
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO strategy_safety_events
                    (event_id, artifact_id, action, reasons_json, next_status, fingerprint, recorded_at,
                     paper_capital_allowed, live_allowed, automatic_promotion_allowed)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 0)
                """,
                (
                    f"shadow_safety_{fingerprint[:20]}",
                    artifact_id,
                    decision.action,
                    _canonical_json(list(decision.reasons)),
                    decision.next_artifact_status,
                    fingerprint,
                    _utc_now().isoformat(),
                ),
            )
            return cursor.rowcount == 1

    def latest_action(self, artifact_id: str) -> str:
        if not self.path.exists():
            return "NORMAL"
        with self._connect() as connection:
            self._initialize(connection)
            row = connection.execute(
                "SELECT action FROM strategy_safety_events WHERE artifact_id = ? ORDER BY recorded_at DESC, event_id DESC LIMIT 1",
                (artifact_id,),
            ).fetchone()
        return str(row[0]) if row else "NORMAL"

    def export_manifest(self, artifact_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            self._initialize(connection)
            artifact = connection.execute(
                "SELECT artifact_json FROM strategy_artifacts WHERE artifact_id = ?", (artifact_id,)
            ).fetchone()
            if not artifact:
                raise ShadowGovernanceError(f"unknown strategy artifact: {artifact_id}")
            events = connection.execute(
                "SELECT action, reasons_json, next_status, recorded_at FROM strategy_safety_events WHERE artifact_id = ? ORDER BY recorded_at, event_id",
                (artifact_id,),
            ).fetchall()
        return {
            "artifact": json.loads(str(artifact[0])),
            "safety_events": [
                {"action": row[0], "reasons": json.loads(row[1]), "next_status": row[2], "recorded_at": row[3]}
                for row in events
            ],
            "research_only": True,
            "paper_capital_allowed": False,
            "live_allowed": False,
            "automatic_promotion_allowed": False,
        }

    def resolve_shadow_order_intent_reference(self, artifact_id: str) -> StrategyArtifactReference:
        """Resolve one registered shadow artifact without mutating its registry.

        This method is deliberately intended for an offline/batch binding step,
        not the hot signal handler. It opens the append-only registry through a
        SQLite read-only URI, verifies the stored artifact identity and returns
        only a non-executable contract reference.
        """

        requested_id = str(artifact_id or "").strip()
        if not requested_id:
            raise ShadowGovernanceError("artifact_id is required")
        path = self.path.resolve()
        if not path.is_file():
            raise ShadowGovernanceError("strategy artifact registry is unavailable")
        try:
            with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=30.0) as connection:
                connection.execute("PRAGMA query_only = ON")
                row = connection.execute(
                    "SELECT artifact_json FROM strategy_artifacts WHERE artifact_id = ?",
                    (requested_id,),
                ).fetchone()
        except sqlite3.Error as exc:
            raise ShadowGovernanceError("strategy artifact registry read failed") from exc
        if not row:
            raise ShadowGovernanceError("unknown strategy artifact")
        try:
            reference = strategy_artifact_reference_from_mapping(json.loads(str(row[0])))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ShadowGovernanceError("strategy artifact registry record is invalid") from exc
        if reference.status not in ORDER_INTENT_SHADOW_ARTIFACT_STATUSES:
            raise ShadowGovernanceError("strategy artifact is not eligible for a new shadow order intent")
        if not reference.feature_snapshots:
            raise ShadowGovernanceError("strategy artifact lacks point-in-time feature snapshot evidence")
        return reference

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30.0)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    @staticmethod
    def _initialize(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS strategy_artifacts (
                artifact_id TEXT PRIMARY KEY,
                fingerprint TEXT NOT NULL UNIQUE,
                strategy_id TEXT NOT NULL,
                status TEXT NOT NULL,
                artifact_json TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                paper_capital_allowed INTEGER NOT NULL CHECK (paper_capital_allowed = 0),
                live_allowed INTEGER NOT NULL CHECK (live_allowed = 0),
                automatic_promotion_allowed INTEGER NOT NULL CHECK (automatic_promotion_allowed = 0)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS strategy_safety_events (
                event_id TEXT PRIMARY KEY,
                artifact_id TEXT NOT NULL REFERENCES strategy_artifacts(artifact_id),
                action TEXT NOT NULL,
                reasons_json TEXT NOT NULL,
                next_status TEXT NOT NULL,
                fingerprint TEXT NOT NULL UNIQUE,
                recorded_at TEXT NOT NULL,
                paper_capital_allowed INTEGER NOT NULL CHECK (paper_capital_allowed = 0),
                live_allowed INTEGER NOT NULL CHECK (live_allowed = 0),
                automatic_promotion_allowed INTEGER NOT NULL CHECK (automatic_promotion_allowed = 0)
            )
            """
        )
        for table in ("strategy_artifacts", "strategy_safety_events"):
            for operation in ("UPDATE", "DELETE"):
                connection.execute(
                    f"""
                    CREATE TRIGGER IF NOT EXISTS {table}_append_only_{operation.lower()}
                    BEFORE {operation} ON {table}
                    BEGIN
                        SELECT RAISE(ABORT, '{table} is append-only');
                    END
                    """
                )


def evaluate_shadow_parity(
    *,
    artifact: StrategyArtifact,
    batch_observation: ShadowObservation,
    shadow_observation: ShadowObservation,
    max_observation_lag: timedelta = timedelta(minutes=5),
) -> ShadowParityResult:
    """Compare two point-in-time decisions without routing either one."""

    reasons: list[str] = []
    if artifact.status not in {"SHADOW_ELIGIBLE", "SHADOW", "THROTTLED"}:
        reasons.append("artifact_not_shadow_eligible")
    if batch_observation.artifact_id != artifact.artifact_id or shadow_observation.artifact_id != artifact.artifact_id:
        reasons.append("artifact_fingerprint_mismatch")
    if batch_observation.source_snapshot_id != artifact.data_snapshot_id or shadow_observation.source_snapshot_id != artifact.data_snapshot_id:
        reasons.append("data_snapshot_mismatch")
    if batch_observation.feature_fingerprint != shadow_observation.feature_fingerprint:
        reasons.append("feature_fingerprint_mismatch")
    if abs(batch_observation.observed_at - shadow_observation.observed_at) > max_observation_lag:
        reasons.append("observation_lag_exceeds_limit")
    if shadow_observation.observed_at - shadow_observation.data_available_at > max_observation_lag:
        reasons.append("shadow_data_stale")
    batch_target = contract_fingerprint(batch_observation.target_portfolio)
    shadow_target = contract_fingerprint(shadow_observation.target_portfolio)
    if batch_target != shadow_target:
        reasons.append("target_portfolio_mismatch")
    return ShadowParityResult(
        status="PARITY_OK" if not reasons else "PARITY_BLOCKED",
        reasons=tuple(reasons),
        batch_target_fingerprint=batch_target,
        shadow_target_fingerprint=shadow_target,
    )


def decide_shadow_safety(
    performance: ShadowPerformanceWindow,
    *,
    policy: ShadowSafetyPolicy = ShadowSafetyPolicy(),
    previous_action: str = "NORMAL",
) -> ShadowSafetyDecision:
    """Return the most conservative action; automatic risk increases are impossible."""

    previous = _validate_action(previous_action)
    reasons: list[str] = []
    calculated = "NORMAL"
    if performance.data_age > policy.max_data_age:
        calculated = "DISABLE_NEW_ENTRIES"
        reasons.append("market_data_stale")
    if performance.trade_count < policy.min_trade_count_for_performance:
        calculated = _more_severe(calculated, "WATCH")
        reasons.append("insufficient_shadow_sample")
    if performance.rolling_profit_factor is not None:
        pf = performance.rolling_profit_factor
        if pf <= policy.quarantine_profit_factor:
            calculated = _more_severe(calculated, "QUARANTINE")
            reasons.append("rolling_profit_factor_quarantine")
        elif pf <= policy.disable_profit_factor:
            calculated = _more_severe(calculated, "DISABLE_NEW_ENTRIES")
            reasons.append("rolling_profit_factor_disabled")
        elif pf <= policy.reduce_profit_factor:
            calculated = _more_severe(calculated, "REDUCE")
            reasons.append("rolling_profit_factor_reduced")
        elif pf <= policy.watch_profit_factor:
            calculated = _more_severe(calculated, "WATCH")
            reasons.append("rolling_profit_factor_watch")
    if performance.rolling_expectancy_eur is not None and performance.rolling_expectancy_eur < 0.0:
        calculated = _more_severe(calculated, "REDUCE")
        reasons.append("rolling_expectancy_negative")
    if performance.max_drawdown_pct is not None:
        drawdown = performance.max_drawdown_pct
        if drawdown >= policy.quarantine_drawdown_pct:
            calculated = _more_severe(calculated, "QUARANTINE")
            reasons.append("drawdown_quarantine")
        elif drawdown >= policy.disable_drawdown_pct:
            calculated = _more_severe(calculated, "DISABLE_NEW_ENTRIES")
            reasons.append("drawdown_disabled")
        elif drawdown >= policy.reduce_drawdown_pct:
            calculated = _more_severe(calculated, "REDUCE")
            reasons.append("drawdown_reduced")
    if performance.feature_drift_score is not None:
        drift = performance.feature_drift_score
        if drift >= policy.quarantine_feature_drift:
            calculated = _more_severe(calculated, "QUARANTINE")
            reasons.append("feature_drift_quarantine")
        elif drift >= policy.disable_feature_drift:
            calculated = _more_severe(calculated, "DISABLE_NEW_ENTRIES")
            reasons.append("feature_drift_disabled")
        elif drift >= policy.reduce_feature_drift:
            calculated = _more_severe(calculated, "REDUCE")
            reasons.append("feature_drift_reduced")
    if performance.cost_drift_bps is not None:
        # Only adverse incremental costs can reduce a shadow envelope.  A
        # favourable execution difference is still recorded, but cannot be
        # treated as a reason to increase risk automatically.
        cost_drift = performance.cost_drift_bps
        if cost_drift >= policy.quarantine_cost_drift_bps:
            calculated = _more_severe(calculated, "QUARANTINE")
            reasons.append("cost_drift_quarantine")
        elif cost_drift >= policy.disable_cost_drift_bps:
            calculated = _more_severe(calculated, "DISABLE_NEW_ENTRIES")
            reasons.append("cost_drift_disabled")
        elif cost_drift >= policy.reduce_cost_drift_bps:
            calculated = _more_severe(calculated, "REDUCE")
            reasons.append("cost_drift_reduced")
        elif cost_drift >= policy.watch_cost_drift_bps:
            calculated = _more_severe(calculated, "WATCH")
            reasons.append("cost_drift_watch")
    action = _more_severe(previous, calculated)
    return ShadowSafetyDecision(
        action=action,
        reasons=tuple(sorted(set(reasons))) or ("shadow_metrics_within_observation_policy",),
        next_artifact_status=_status_for_action(action),
    )


def apply_shadow_safety(artifact: StrategyArtifact, decision: ShadowSafetyDecision) -> StrategyArtifact:
    """Apply a non-increasing-risk status transition to an immutable artifact."""

    # Observation cannot start shadow or relax a throttle.  The only automatic
    # changes allowed here are reductions from an already shadow-capable state.
    if decision.action in {"NORMAL", "WATCH"}:
        return artifact
    if artifact.status in {"REJECTED", "RETIRED", "QUARANTINED"}:
        return artifact
    if artifact.status not in {"SHADOW_ELIGIBLE", "SHADOW", "THROTTLED"}:
        return artifact
    return replace(artifact, status=decision.next_artifact_status)


def _status_for_action(action: str) -> str:
    action = _validate_action(action)
    if action == "QUARANTINE":
        return "QUARANTINED"
    if action in {"REDUCE", "DISABLE_NEW_ENTRIES"}:
        return "THROTTLED"
    return "SHADOW"


def _more_severe(first: str, second: str) -> str:
    return first if SHADOW_ACTIONS.index(first) >= SHADOW_ACTIONS.index(second) else second


def _validate_action(action: str) -> str:
    normalized = str(action).upper()
    if normalized not in SHADOW_ACTIONS:
        raise ShadowGovernanceError(f"unsupported shadow action: {action}")
    return normalized


def _fingerprint(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
