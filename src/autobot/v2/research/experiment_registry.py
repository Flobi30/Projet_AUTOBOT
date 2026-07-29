"""Append-only, reproducible experiment registry for AUTOBOT research.

The registry records evidence; it does not route orders, allocate capital, or
change strategy runtime policy.  A rejected experiment cannot be reopened
under the same material fingerprint, which makes repeated parameter fishing
visible instead of silently erasing it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import logging
import math
from pathlib import Path
import sqlite3
from itertools import product
from time import sleep
from typing import Any, Callable, Iterable, Mapping, Sequence, TypeVar

from .alpha_hypothesis_lab import CANONICAL_RESEARCH_STAGES, next_research_stage, normalize_research_stage


logger = logging.getLogger(__name__)
_T = TypeVar("_T")
STAGES = CANONICAL_RESEARCH_STAGES
TERMINAL_STATUSES = {"REJECTED", "INSUFFICIENT_DATA"}
PASS_STATUS = "PASSED"
DEFAULT_EXPERIMENT_REGISTRY_PATH = Path("data/research/experiment_registry.sqlite3")
FINAL_HOLDOUT_REVIEW_DIMENSION = "final_holdout_review"
RESEARCH_EVIDENCE_STAGES = frozenset({"NET_SMOKE", "WALK_FORWARD", "STRESS_MONTE_CARLO"})
REQUIRED_PASSED_METRIC_KEYS = {
    "NET_SMOKE": frozenset({"adapter_decision", "variant_count"}),
    "WALK_FORWARD": frozenset({"trade_count", "net_pnl_eur"}),
    "STRESS_MONTE_CARLO": frozenset(
        {
            "trade_count",
            "assumed_trial_count",
            "trial_scope_id",
            "statistical_validation_artifact",
            "probabilistic_sharpe",
            "deflated_sharpe",
            "robustness",
            "statistical_gate",
            "statistical_gate_decision",
            "statistical_evidence_fingerprint",
        }
    ),
}


class ExperimentRegistryError(ValueError):
    """Raised when an experiment would violate a research invariant."""


@dataclass(frozen=True)
class ExperimentSpec:
    hypothesis_id: str
    template_id: str
    thesis: str
    code_commit: str
    image_ref: str
    data_snapshot_id: str
    feature_versions: Mapping[str, str]
    parameters: Mapping[str, Any]
    seed: int
    cost_model: Mapping[str, Any]
    environment: Mapping[str, Any]
    holdout_id: str | None = None
    research_campaign_id: str | None = None
    predecessor_experiment_id: str | None = None
    predecessor_trial_count_floor: int | None = None
    material_data_signature: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        for field_name in ("hypothesis_id", "template_id", "thesis", "code_commit", "image_ref", "data_snapshot_id"):
            if not str(getattr(self, field_name) or "").strip():
                raise ValueError(f"{field_name} is required")
        if not isinstance(self.seed, int):
            raise ValueError("seed must be an integer")
        object.__setattr__(self, "feature_versions", {str(key): str(value) for key, value in self.feature_versions.items()})
        object.__setattr__(self, "parameters", dict(self.parameters))
        object.__setattr__(self, "cost_model", dict(self.cost_model))
        object.__setattr__(self, "environment", dict(self.environment))
        campaign_id = str(self.research_campaign_id or "").strip().lower() or None
        if campaign_id is not None and not all(character.isalnum() or character in "_.-" for character in campaign_id):
            raise ValueError("research_campaign_id must contain only letters, digits, _, . or -")
        object.__setattr__(self, "research_campaign_id", campaign_id)
        predecessor_id = str(self.predecessor_experiment_id or "").strip() or None
        floor = self.predecessor_trial_count_floor
        signature = self.material_data_signature
        if signature is not None:
            if not isinstance(signature, Mapping) or not str(signature.get("fingerprint") or "").strip():
                raise ValueError("material_data_signature requires a fingerprint")
            if not isinstance(signature.get("capability_states"), Mapping):
                raise ValueError("material_data_signature requires capability_states")
            object.__setattr__(self, "material_data_signature", dict(signature))
        if predecessor_id is not None or floor is not None:
            if campaign_id is None:
                raise ValueError("successor experiment requires research_campaign_id")
            if predecessor_id is None or not isinstance(floor, int) or floor < 1:
                raise ValueError("successor experiment requires predecessor_experiment_id and positive predecessor_trial_count_floor")
            if not isinstance(signature, Mapping) or not str(signature.get("fingerprint") or "").strip():
                raise ValueError("successor experiment requires a material_data_signature fingerprint")
        object.__setattr__(self, "predecessor_experiment_id", predecessor_id)

    @property
    def material_fingerprint(self) -> str:
        payload = asdict(self)
        # Keep the identity of pre-campaign experiment specifications stable.
        # A schema migration must never turn an identical legacy experiment
        # into a fresh material fingerprint that could be run a second time.
        for optional_field in (
            "research_campaign_id",
            "predecessor_experiment_id",
            "predecessor_trial_count_floor",
            "material_data_signature",
        ):
            if payload.get(optional_field) is None:
                payload.pop(optional_field, None)
        return _fingerprint(payload)

    @property
    def experiment_id(self) -> str:
        return f"exp_{self.material_fingerprint[:20]}"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["material_fingerprint"] = self.material_fingerprint
        payload["experiment_id"] = self.experiment_id
        payload["research_only"] = True
        payload["paper_capital_allowed"] = False
        payload["live_allowed"] = False
        payload["promotable"] = False
        return payload


@dataclass(frozen=True)
class ExperimentState:
    experiment_id: str
    hypothesis_id: str
    template_id: str
    material_fingerprint: str
    latest_stage: str | None
    latest_status: str | None
    terminal: bool
    trial_count: int
    paper_capital_allowed: bool = False
    live_allowed: bool = False
    promotable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StatisticalValidationArtifact:
    """Immutable multiple-testing evidence for one material experiment.

    The registry owns the lower bound of the trial count.  A statistical
    producer may use a stricter local floor (for example, bounded folds), but
    it can never submit a count below the append-only registry evidence.
    This is research evidence only; it carries no shadow, paper or live
    authorization.
    """

    experiment_id: str
    hypothesis_id: str
    research_campaign_id: str | None
    trial_scope_id: str
    registry_trial_count: int
    effective_trial_count: int
    schema_version: int = 1
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False
    promotable: bool = False

    def __post_init__(self) -> None:
        experiment_id = str(self.experiment_id or "").strip()
        hypothesis_id = str(self.hypothesis_id or "").strip().lower()
        campaign_id = str(self.research_campaign_id or "").strip().lower() or None
        trial_scope_id = str(self.trial_scope_id or "").strip().lower()
        if not experiment_id or not hypothesis_id or not trial_scope_id:
            raise ValueError("statistical validation artifact identifiers are required")
        expected_scope = campaign_id or f"hypothesis_{hypothesis_id}"
        if trial_scope_id != expected_scope:
            raise ValueError("statistical validation artifact trial_scope_id must match its registry scope")
        if any(not character.isalnum() and character not in "_.-" for character in trial_scope_id):
            raise ValueError("statistical validation artifact trial_scope_id is invalid")
        if isinstance(self.registry_trial_count, bool) or isinstance(self.effective_trial_count, bool):
            raise ValueError("statistical validation artifact trial counts must be integers")
        registry_trial_count = int(self.registry_trial_count)
        effective_trial_count = int(self.effective_trial_count)
        if registry_trial_count < 0 or effective_trial_count < 1:
            raise ValueError("statistical validation artifact trial counts are invalid")
        if effective_trial_count < registry_trial_count:
            raise ValueError("effective trial count cannot understate append-only registry evidence")
        if self.schema_version != 1:
            raise ValueError("unsupported statistical validation artifact schema")
        if not self.research_only or self.paper_capital_allowed or self.live_allowed or self.promotable:
            raise ValueError("statistical validation artifact must remain research-only and non-promotional")
        object.__setattr__(self, "experiment_id", experiment_id)
        object.__setattr__(self, "hypothesis_id", hypothesis_id)
        object.__setattr__(self, "research_campaign_id", campaign_id)
        object.__setattr__(self, "trial_scope_id", trial_scope_id)
        object.__setattr__(self, "registry_trial_count", registry_trial_count)
        object.__setattr__(self, "effective_trial_count", effective_trial_count)

    @property
    def fingerprint(self) -> str:
        payload = asdict(self)
        return _fingerprint(payload)

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "fingerprint": self.fingerprint}

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "StatisticalValidationArtifact":
        if not isinstance(payload, Mapping):
            raise ValueError("statistical validation artifact must be a mapping")
        raw = dict(payload)
        supplied_fingerprint = str(raw.pop("fingerprint", "") or "").strip().lower()
        artifact = cls(**raw)
        if supplied_fingerprint != artifact.fingerprint:
            raise ValueError("statistical validation artifact fingerprint mismatch")
        return artifact


class ExperimentRegistry:
    """SQLite-backed append-only experiment metadata, trials and gate evidence."""

    def __init__(
        self,
        path: str | Path = DEFAULT_EXPERIMENT_REGISTRY_PATH,
        *,
        sqlite_timeout_seconds: float = 30.0,
        write_retries: int = 3,
        retry_base_delay_seconds: float = 0.05,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        self.path = Path(path)
        if sqlite_timeout_seconds <= 0.0 or write_retries < 0 or retry_base_delay_seconds < 0.0:
            raise ValueError("invalid experiment-registry SQLite retry configuration")
        self._sqlite_timeout_seconds = float(sqlite_timeout_seconds)
        self._busy_timeout_ms = max(1, int(self._sqlite_timeout_seconds * 1000))
        self._write_retries = int(write_retries)
        self._retry_base_delay_seconds = float(retry_base_delay_seconds)
        self._sleeper = sleeper

    def register_experiment(self, spec: ExperimentSpec) -> ExperimentState:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        def _write(connection: sqlite3.Connection) -> ExperimentState:
            self._validate_successor_spec(connection, spec)
            existing = connection.execute(
                "SELECT experiment_id FROM experiments WHERE material_fingerprint = ?",
                (spec.material_fingerprint,),
            ).fetchone()
            if existing:
                return self._state(connection, str(existing[0]))
            connection.execute(
                """
                INSERT INTO experiments (
                    experiment_id, material_fingerprint, hypothesis_id, template_id, research_campaign_id,
                    created_at, spec_json, research_only, paper_capital_allowed,
                    live_allowed, promotable
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 0, 0, 0)
                """,
                (
                    spec.experiment_id,
                    spec.material_fingerprint,
                    spec.hypothesis_id,
                    spec.template_id,
                    spec.research_campaign_id,
                    _now(),
                    _json(spec.to_dict()),
                ),
            )
            return self._state(connection, spec.experiment_id)

        return self._run_write("register_experiment", _write)

    def reserve_holdout(
        self,
        *,
        holdout_id: str,
        data_snapshot_id: str,
        immutable_fingerprint: str,
        manifest: Mapping[str, Any] | None = None,
    ) -> bool:
        if not all(str(value or "").strip() for value in (holdout_id, data_snapshot_id, immutable_fingerprint)):
            raise ExperimentRegistryError("holdout id, snapshot id and fingerprint are required")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        manifest_json = _json(dict(manifest or {}))
        def _write(connection: sqlite3.Connection) -> bool:
            existing = connection.execute(
                "SELECT data_snapshot_id, immutable_fingerprint, manifest_json FROM holdout_reservations WHERE holdout_id = ?",
                (holdout_id,),
            ).fetchone()
            if existing:
                if tuple(existing) != (data_snapshot_id, immutable_fingerprint, manifest_json):
                    raise ExperimentRegistryError("holdout_id is already reserved for different immutable data")
                return False
            connection.execute(
                """
                INSERT INTO holdout_reservations
                    (holdout_id, data_snapshot_id, immutable_fingerprint, manifest_json, reserved_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (holdout_id, data_snapshot_id, immutable_fingerprint, manifest_json, _now()),
            )
            return True

        return self._run_write("reserve_holdout", _write)

    def record_trial(
        self,
        *,
        experiment_id: str,
        dimension: str,
        value: Mapping[str, Any] | Sequence[Any] | str | int | float | bool | None,
        uses_holdout: bool = False,
        optimization: bool = True,
        holdout_id: str | None = None,
    ) -> str:
        if str(dimension) == FINAL_HOLDOUT_REVIEW_DIMENSION:
            raise ExperimentRegistryError(
                "final_holdout_review must be recorded through record_final_holdout_review"
            )
        return self._record_trial(
            experiment_id=experiment_id,
            dimension=dimension,
            value=value,
            uses_holdout=uses_holdout,
            optimization=optimization,
            holdout_id=holdout_id,
        )

    def record_regime_segmentation_trial(
        self,
        *,
        experiment_id: str,
        segmentation_id: str,
        segmentation_version: str,
        segmentation_fingerprint: str,
        labels: Sequence[str],
        max_segments: int,
        data_snapshot_id: str,
        feature_config_fingerprint: str,
    ) -> str:
        """Record one bounded regime split as an optimization trial.

        Regime segmentation changes the research decision surface and therefore
        counts toward multiple-testing evidence.  The split must be explicitly
        bound to the immutable data snapshot of its parent experiment; it is
        never a runtime configuration or a promotion decision.
        """

        normalized_id = str(segmentation_id or "").strip().lower()
        normalized_version = str(segmentation_version or "").strip()
        normalized_fingerprint = str(segmentation_fingerprint or "").strip().lower()
        normalized_snapshot_id = str(data_snapshot_id or "").strip()
        normalized_feature_config_fingerprint = str(feature_config_fingerprint or "").strip().lower()
        normalized_labels = tuple(
            str(label).strip().lower() for label in labels if str(label).strip()
        )
        try:
            bounded_max_segments = int(max_segments)
        except (TypeError, ValueError) as exc:
            raise ExperimentRegistryError("max_segments must be an integer") from exc

        if not normalized_id or not all(character.isalnum() or character in "_.-" for character in normalized_id):
            raise ExperimentRegistryError("segmentation_id must contain only letters, digits, _, . or -")
        if (
            not normalized_version
            or not normalized_fingerprint
            or not normalized_snapshot_id
            or not normalized_feature_config_fingerprint
        ):
            raise ExperimentRegistryError(
                "segmentation version, fingerprints and data_snapshot_id are required"
            )
        if (
            bounded_max_segments < 1
            or not normalized_labels
            or len(normalized_labels) > bounded_max_segments
            or len(set(normalized_labels)) != len(normalized_labels)
        ):
            raise ExperimentRegistryError("segmentation labels must be between 1 and max_segments")

        with self._connect() as connection:
            self._initialize(connection)
            state = self._state(connection, experiment_id)
            if state.terminal:
                raise ExperimentRegistryError("terminal experiment cannot record additional trials")
            row = connection.execute(
                "SELECT spec_json FROM experiments WHERE experiment_id = ?", (experiment_id,)
            ).fetchone()
            if row is None:
                raise ExperimentRegistryError(f"unknown experiment: {experiment_id}")
            try:
                experiment_spec = json.loads(str(row[0]))
            except json.JSONDecodeError as exc:
                raise ExperimentRegistryError("stored experiment spec is invalid JSON") from exc
            if str(experiment_spec.get("data_snapshot_id") or "").strip() != normalized_snapshot_id:
                raise ExperimentRegistryError("regime segmentation data_snapshot_id must match experiment")

        return self.record_trial(
            experiment_id=experiment_id,
            dimension="regime_segmentation",
            value={
                "schema_version": 2,
                "segmentation_id": normalized_id,
                "segmentation_version": normalized_version,
                "segmentation_fingerprint": normalized_fingerprint,
                "feature_config_fingerprint": normalized_feature_config_fingerprint,
                "labels": list(normalized_labels),
                "max_segments": bounded_max_segments,
                "data_snapshot_id": normalized_snapshot_id,
                "research_only": True,
                "paper_capital_allowed": False,
                "live_allowed": False,
                "promotable": False,
            },
        )

    def _record_trial(
        self,
        *,
        experiment_id: str,
        dimension: str,
        value: Mapping[str, Any] | Sequence[Any] | str | int | float | bool | None,
        uses_holdout: bool = False,
        optimization: bool = True,
        holdout_id: str | None = None,
    ) -> str:
        if uses_holdout and optimization:
            raise ExperimentRegistryError("immutable holdout cannot be used for optimization")
        with self._connect() as connection:
            self._initialize(connection)
            state = self._state(connection, experiment_id)
            if state.terminal:
                raise ExperimentRegistryError("terminal experiment cannot record additional trials")
            resolved_holdout_id = self._validate_holdout_use(
                connection,
                experiment_id=experiment_id,
                uses_holdout=uses_holdout,
                holdout_id=holdout_id,
            )
            normalized = {
                "dimension": str(dimension),
                "value": value,
                "uses_holdout": uses_holdout,
                "optimization": optimization,
                "holdout_id": resolved_holdout_id,
            }
            fingerprint = _fingerprint({"experiment_id": experiment_id, **normalized})
            trial_id = f"trial_{fingerprint[:20]}"
            connection.execute(
                """
                INSERT OR IGNORE INTO experiment_trials
                    (trial_id, experiment_id, dimension, value_json, uses_holdout, optimization, holdout_id, fingerprint, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trial_id,
                    experiment_id,
                    str(dimension),
                    _json(value),
                    int(uses_holdout),
                    int(optimization),
                    resolved_holdout_id,
                    fingerprint,
                    _now(),
                ),
            )
            return trial_id

    def record_final_holdout_review(
        self,
        *,
        experiment_id: str,
        metrics: Mapping[str, Any],
        reasons: Sequence[str] = (),
        artifact: Mapping[str, Any],
    ) -> str:
        """Append immutable final-holdout evidence without optimizing on it.

        A final holdout is evidence for accepting or rejecting an already
        frozen experiment, never a source of a new parameter choice.  The
        method is intentionally research-only and records no promotion.
        """

        if not isinstance(metrics, Mapping) or not metrics:
            raise ExperimentRegistryError("final holdout review metrics are required")
        if not isinstance(artifact, Mapping) or not artifact:
            raise ExperimentRegistryError("final holdout review requires a sealed result artifact")
        # Claim before evaluating/storing the final artifact. A malformed
        # attempt stays owned by the same experiment and fails closed rather
        # than allowing another material experiment to inspect the holdout.
        self.claim_final_holdout_review(experiment_id=experiment_id)
        review_evidence = self._validate_final_holdout_artifact(
            experiment_id=experiment_id,
            metrics=metrics,
            artifact=artifact,
        )
        if self.has_final_holdout_review(experiment_id):
            raise ExperimentRegistryError("final holdout review is already recorded for this experiment")
        return self._record_trial(
            experiment_id=experiment_id,
            dimension=FINAL_HOLDOUT_REVIEW_DIMENSION,
            value={
                "metrics": dict(metrics),
                "reasons": [str(item) for item in reasons],
                "review_kind": "final_immutable_holdout",
                "artifact": dict(artifact),
                "shadow_review_evidence": review_evidence.to_dict(),
            },
            uses_holdout=True,
            optimization=False,
        )

    def claim_final_holdout_review(self, *, experiment_id: str) -> bool:
        """Exclusively bind a sealed holdout to one material experiment.

        A physical holdout may be reserved as immutable source metadata before
        experiments are registered, but its final review may be claimed by one
        experiment only. The same experiment can resume its interrupted review;
        a different experiment is rejected before it can consume the holdout.
        """

        def _write(connection: sqlite3.Connection) -> bool:
            row = connection.execute(
                "SELECT spec_json FROM experiments WHERE experiment_id = ?", (experiment_id,)
            ).fetchone()
            if row is None:
                raise ExperimentRegistryError(f"unknown experiment: {experiment_id}")
            try:
                spec = json.loads(str(row[0]))
            except json.JSONDecodeError as exc:
                raise ExperimentRegistryError("stored experiment spec is invalid JSON") from exc
            holdout_id = str(spec.get("holdout_id") or "").strip()
            if not holdout_id:
                raise ExperimentRegistryError("experiment has no reserved immutable holdout")
            if not connection.execute(
                "SELECT 1 FROM holdout_reservations WHERE holdout_id = ?", (holdout_id,)
            ).fetchone():
                raise ExperimentRegistryError("experiment holdout must be reserved before final review")
            existing = connection.execute(
                "SELECT experiment_id FROM final_holdout_review_claims WHERE holdout_id = ?", (holdout_id,)
            ).fetchone()
            if existing is not None:
                if str(existing[0]) != str(experiment_id):
                    raise ExperimentRegistryError(
                        "immutable holdout is already claimed by another material experiment"
                    )
                return False
            connection.execute(
                """
                INSERT INTO final_holdout_review_claims (holdout_id, experiment_id, claimed_at)
                VALUES (?, ?, ?)
                """,
                (holdout_id, experiment_id, _now()),
            )
            return True

        return self._run_write("claim_final_holdout_review", _write)

    def record_gate_result(
        self,
        *,
        experiment_id: str,
        stage: str,
        status: str,
        metrics: Mapping[str, Any] | None = None,
        reasons: Sequence[str] = (),
        artifacts: Sequence[Mapping[str, Any]] = (),
    ) -> ExperimentState:
        try:
            stage = normalize_research_stage(stage)
        except ValueError as exc:
            raise ExperimentRegistryError(str(exc)) from exc
        status = str(status).upper()
        if status not in {PASS_STATUS, *TERMINAL_STATUSES}:
            raise ExperimentRegistryError("gate status must be PASSED, REJECTED or INSUFFICIENT_DATA")
        if metrics is not None and not isinstance(metrics, Mapping):
            raise ExperimentRegistryError("gate metrics must be a mapping when supplied")
        metrics_payload = dict(metrics or {})
        if stage == "STRESS_MONTE_CARLO" and status == PASS_STATUS and metrics_payload:
            _attach_statistical_evidence_fingerprint(metrics_payload)
        metrics_json = _json(metrics_payload)
        reasons_json = _json(list(reasons))
        transition_id = f"gate_{_fingerprint({'experiment_id': experiment_id, 'stage': stage, 'status': status, 'metrics': metrics_payload, 'reasons': list(reasons)})[:20]}"
        expected_artifact_ids = frozenset(
            self._artifact_id(experiment_id=experiment_id, stage=stage, artifact=artifact)
            for artifact in artifacts
        )

        def _write(connection: sqlite3.Connection) -> ExperimentState:
            previous = self._state(connection, experiment_id)
            if previous.terminal and previous.latest_stage != stage:
                raise ExperimentRegistryError("terminal experiment cannot advance")
            existing_transition = connection.execute(
                """
                SELECT status, metrics_json, reasons_json
                FROM experiment_transitions
                WHERE transition_id = ?
                """,
                (transition_id,),
            ).fetchone()
            if existing_transition is not None:
                if tuple(existing_transition) != (status, metrics_json, reasons_json):
                    raise ExperimentRegistryError("existing gate transition differs from retry payload")
                existing_artifact_ids = {
                    str(row[0])
                    for row in connection.execute(
                        "SELECT artifact_id FROM experiment_artifacts WHERE experiment_id = ? AND stage = ?",
                        (experiment_id, stage),
                    ).fetchall()
                }
                if existing_artifact_ids != set(expected_artifact_ids):
                    raise ExperimentRegistryError("existing gate artifacts differ from retry payload")
                return self._state(connection, experiment_id)

            if previous.terminal:
                raise ExperimentRegistryError("terminal experiment cannot advance")
            expected = STAGES[0] if previous.latest_stage is None else _next_stage(previous.latest_stage)
            if stage != expected:
                raise ExperimentRegistryError(f"expected stage {expected}, received {stage}")
            existing_stage = connection.execute(
                "SELECT transition_id FROM experiment_transitions WHERE experiment_id = ? AND stage = ?",
                (experiment_id, stage),
            ).fetchone()
            if existing_stage is not None:
                raise ExperimentRegistryError("gate stage is already recorded with different evidence")
            if status == PASS_STATUS:
                _validate_passed_stage_evidence(stage=stage, metrics=metrics_payload, artifacts=artifacts)
                if stage == "STRESS_MONTE_CARLO":
                    self._validate_statistical_validation_artifact(
                        connection,
                        experiment_id=experiment_id,
                        metrics=metrics_payload,
                    )
            if stage == STAGES[-1] and status == PASS_STATUS:
                self._require_final_holdout_review(connection, experiment_id=experiment_id)
            connection.execute(
                """
                INSERT INTO experiment_transitions
                    (transition_id, experiment_id, stage, status, metrics_json, reasons_json, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (transition_id, experiment_id, stage, status, metrics_json, reasons_json, _now()),
            )
            for artifact in artifacts:
                self._record_artifact(connection, experiment_id=experiment_id, stage=stage, artifact=artifact)
            return self._state(connection, experiment_id)

        return self._run_write("record_gate_result", _write)

    def record_runner_evidence(
        self,
        *,
        spec: ExperimentSpec,
        report: Any,
        variant_count: int,
        symbols: Sequence[str] = (),
        timeframes: Sequence[str] = (),
        regimes: Sequence[str] = (),
        record_trial_dimensions: bool = True,
    ) -> ExperimentState:
        """Project a bounded runner report into canonical trial and gate evidence.

        The runner remains research-only.  Trial dimensions are recorded before
        validation whenever possible so that multiple-testing statistics can use
        the same evidence as the later gate projection.  A repeated report
        cannot reopen a terminal material experiment.
        """

        if variant_count < 0:
            raise ExperimentRegistryError("variant_count cannot be negative")
        state = self.register_experiment(spec)
        if state.terminal:
            return state
        run_id = str(getattr(report, "run_id", "") or "").strip()
        if not run_id:
            raise ExperimentRegistryError("runner report must carry a run_id")
        if record_trial_dimensions:
            self.record_trial_plan(
                experiment_id=state.experiment_id,
                variant_count=variant_count,
                symbols=symbols,
                timeframes=timeframes,
                regimes=regimes,
            )

        runner_artifacts = _runner_report_artifacts(report)
        for gate in tuple(getattr(report, "gates", ())):
            try:
                stage = normalize_research_stage(str(getattr(gate, "gate", "")))
            except ValueError as exc:
                raise ExperimentRegistryError(str(exc)) from exc
            status_text = str(getattr(gate, "status", "")).upper()
            if status_text == "HUMAN_REVIEW_REQUIRED":
                break
            status = PASS_STATUS if bool(getattr(gate, "passed", False)) else (
                "INSUFFICIENT_DATA" if status_text in {"DATA_MISSING", "INSUFFICIENT_DATA"} else "REJECTED"
            )
            current = self.get_state(state.experiment_id)
            if current.terminal:
                return current
            if current.latest_stage is not None and STAGES.index(stage) <= STAGES.index(current.latest_stage):
                continue
            metrics = dict(getattr(gate, "metrics", {}) or {})
            if stage == "STRESS_MONTE_CARLO" and status == PASS_STATUS:
                if not isinstance(metrics.get("statistical_gate"), Mapping):
                    gate_artifacts = getattr(gate, "artifacts", {}) or {}
                    if isinstance(gate_artifacts, Mapping) and isinstance(gate_artifacts.get("statistical_gate"), Mapping):
                        metrics["statistical_gate"] = dict(gate_artifacts["statistical_gate"])
                assumed_trial_count = metrics.get("assumed_trial_count")
                if isinstance(assumed_trial_count, bool) or not isinstance(assumed_trial_count, int):
                    raise ExperimentRegistryError("STRESS_MONTE_CARLO assumed_trial_count must be an integer")
                artifact = self.build_statistical_validation_artifact(
                    experiment_id=current.experiment_id,
                    effective_trial_count=assumed_trial_count,
                )
                metrics["trial_scope_id"] = artifact.trial_scope_id
                metrics["statistical_validation_artifact"] = artifact.to_dict()
            current = self.record_gate_result(
                experiment_id=state.experiment_id,
                stage=stage,
                status=status,
                metrics=metrics,
                reasons=tuple(str(item) for item in (getattr(gate, "reasons", ()) or ())),
                # Every passed material gate must carry the same immutable
                # runner report.  This makes stage evidence independently
                # auditable instead of relying on an unbound earlier report.
                artifacts=runner_artifacts if status == PASS_STATUS else (),
            )
            if current.terminal:
                return current
        return self.get_state(state.experiment_id)

    def record_trial_plan(
        self,
        *,
        experiment_id: str,
        variant_count: int,
        symbols: Sequence[str] = (),
        timeframes: Sequence[str] = (),
        regimes: Sequence[str] = (),
    ) -> int:
        """Append a deterministic, auditable trial plan before validation.

        Dimension rows preserve the research decision surface.  Candidate rows
        represent the configurations used by multiple-testing correction.  An
        omitted timeframe or regime stays explicitly unspecified rather than
        being guessed from a dataset or a report.
        """

        if variant_count < 0:
            raise ExperimentRegistryError("variant_count cannot be negative")
        normalized_symbols = _normalized_trial_values(symbols, uppercase=True)
        normalized_timeframes = _normalized_trial_values(timeframes)
        normalized_regimes = _normalized_trial_values(regimes)

        for index in range(variant_count):
            self.record_trial(
                experiment_id=experiment_id,
                dimension="parameter_variant",
                value={"variant_index": index},
            )
        for symbol in normalized_symbols:
            self.record_trial(experiment_id=experiment_id, dimension="pair", value={"symbol": symbol})
        for timeframe in normalized_timeframes:
            self.record_trial(experiment_id=experiment_id, dimension="timeframe", value={"timeframe": timeframe})
        for regime in normalized_regimes:
            self.record_trial(experiment_id=experiment_id, dimension="regime", value={"regime": regime})

        candidate_symbols = normalized_symbols or ("UNSPECIFIED",)
        candidate_timeframes = normalized_timeframes or ("UNSPECIFIED",)
        candidate_regimes = normalized_regimes or ("UNSPECIFIED",)
        candidate_count = 0
        for variant_index, symbol, timeframe, regime in product(
            range(variant_count), candidate_symbols, candidate_timeframes, candidate_regimes
        ):
            self.record_trial(
                experiment_id=experiment_id,
                dimension="candidate_configuration",
                value={
                    "variant_index": variant_index,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "regime": regime,
                },
            )
            candidate_count += 1
        return candidate_count

    def claim_bounded_research_execution(self, *, experiment_id: str, coordinator_run_id: str) -> bool:
        """Atomically reserve one immutable material experiment for automation.

        A bounded coordinator is allowed one attempt for a material
        fingerprint.  The claim intentionally never expires: after a process
        crash, fail closed and require new data, a new thesis or a new template
        rather than silently replaying an uncertain experiment.  The normal
        gate/artifact evidence records the actual outcome separately.
        """

        run_id = str(coordinator_run_id or "").strip()
        if not run_id:
            raise ExperimentRegistryError("coordinator_run_id is required")
        with self._connect() as connection:
            self._initialize(connection)
            state = self._state(connection, experiment_id)
            if state.terminal:
                return False
            execution_id = f"bounded_execution_{_fingerprint({'experiment_id': experiment_id, 'run_id': run_id})[:20]}"
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO bounded_research_execution_claims
                    (experiment_id, execution_id, coordinator_run_id, claimed_at)
                VALUES (?, ?, ?, ?)
                """,
                (experiment_id, execution_id, run_id, _now()),
            )
            return cursor.rowcount == 1

    def claim_bounded_research_snapshot(
        self,
        *,
        feature_snapshot_id: str,
        feature_snapshot_fingerprint: str,
        coordinator_run_id: str,
    ) -> bool:
        """Atomically limit unattended research to one attempt per snapshot.

        This is stricter than material-experiment deduplication. A daily
        point-in-time feature snapshot gets one autonomous smoke decision, not
        one decision per template. Further exploration of the same data remains
        an explicit human-reviewed research action.
        """

        snapshot_id = str(feature_snapshot_id or "").strip()
        fingerprint = str(feature_snapshot_fingerprint or "").strip()
        run_id = str(coordinator_run_id or "").strip()
        if not snapshot_id or not fingerprint or not run_id:
            raise ExperimentRegistryError("snapshot id, fingerprint and coordinator run id are required")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            self._initialize(connection)
            claim_id = f"bounded_snapshot_{_fingerprint({'snapshot': fingerprint, 'run_id': run_id})[:20]}"
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO bounded_research_snapshot_claims
                    (feature_snapshot_fingerprint, claim_id, feature_snapshot_id, coordinator_run_id, claimed_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (fingerprint, claim_id, snapshot_id, run_id, _now()),
            )
            return cursor.rowcount == 1

    def migrate_legacy_memory(self, records: Iterable[Mapping[str, Any]]) -> int:
        """Append legacy memory records once without treating them as gate evidence."""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        inserted = 0
        with self._connect() as connection:
            self._initialize(connection)
            for record in records:
                run_id = str(record.get("run_id") or "").strip()
                if not run_id:
                    continue
                payload = dict(record)
                fingerprint = _fingerprint(payload)
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO legacy_memory_imports
                        (legacy_run_id, record_fingerprint, record_json, imported_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (run_id, fingerprint, _json(payload), _now()),
                )
                inserted += int(cursor.rowcount == 1)
        return inserted

    def get_state(self, experiment_id: str) -> ExperimentState:
        if not self.path.exists():
            raise ExperimentRegistryError("experiment registry does not exist")
        with self._connect() as connection:
            self._initialize(connection)
            return self._state(connection, experiment_id)

    def trial_count(self, *, hypothesis_id: str | None = None) -> int:
        if not self.path.exists():
            return 0
        with self._connect() as connection:
            self._initialize(connection)
            if hypothesis_id is None:
                return int(connection.execute("SELECT COUNT(*) FROM experiment_trials").fetchone()[0])
            return int(
                connection.execute(
                    """
                    SELECT COUNT(*) FROM experiment_trials AS trial
                    JOIN experiments AS experiment ON experiment.experiment_id = trial.experiment_id
                    WHERE experiment.hypothesis_id = ?
                    """,
                    (hypothesis_id,),
                ).fetchone()[0]
            )

    def validation_trial_count(self, *, hypothesis_id: str, research_campaign_id: str | None = None) -> int:
        """Return the conservative count used by multiple-testing validation.

        Candidate configurations encode the crossed decision surface and every
        explicit regime segmentation is an additional model-selection choice.
        Both therefore contribute to the correction.  When an explicit
        campaign is supplied, every material experiment in that campaign
        contributes.  Older registry evidence predating the campaign schema
        remains conservatively scoped to its hypothesis instead of silently
        disappearing from the correction.
        """

        normalized_hypothesis_id = str(hypothesis_id or "").strip()
        normalized_campaign_id = str(research_campaign_id or "").strip().lower() or None
        if not normalized_hypothesis_id or not self.path.exists():
            return 0
        if normalized_campaign_id is not None and not all(
            character.isalnum() or character in "_.-" for character in normalized_campaign_id
        ):
            raise ExperimentRegistryError("research_campaign_id must contain only letters, digits, _, . or -")
        with self._connect() as connection:
            self._initialize(connection)
            return self._validation_trial_count_for_scope(
                connection,
                hypothesis_id=normalized_hypothesis_id,
                research_campaign_id=normalized_campaign_id,
            )

    def build_statistical_validation_artifact(
        self,
        *,
        experiment_id: str,
        effective_trial_count: int,
    ) -> StatisticalValidationArtifact:
        """Bind an external statistical report to the registry trial floor.

        This method is side-effect free.  It may be called by a runner after it
        has recorded a bounded trial plan, then supplied to the passed stress
        gate as immutable, content-addressed evidence.
        """

        if isinstance(effective_trial_count, bool) or not isinstance(effective_trial_count, int):
            raise ExperimentRegistryError("effective_trial_count must be an integer")
        with self._connect() as connection:
            self._initialize(connection)
            row = connection.execute(
                "SELECT hypothesis_id, research_campaign_id FROM experiments WHERE experiment_id = ?",
                (experiment_id,),
            ).fetchone()
            if row is None:
                raise ExperimentRegistryError(f"unknown experiment: {experiment_id}")
            hypothesis_id = str(row[0] or "").strip().lower()
            campaign_id = str(row[1] or "").strip().lower() or None
            registry_trial_count = self._validation_trial_count_for_scope(
                connection,
                hypothesis_id=hypothesis_id,
                research_campaign_id=campaign_id,
            )
        try:
            return StatisticalValidationArtifact(
                experiment_id=experiment_id,
                hypothesis_id=hypothesis_id,
                research_campaign_id=campaign_id,
                trial_scope_id=campaign_id or f"hypothesis_{hypothesis_id}",
                registry_trial_count=registry_trial_count,
                effective_trial_count=effective_trial_count,
            )
        except ValueError as exc:
            raise ExperimentRegistryError(str(exc)) from exc

    def _validation_trial_count_for_scope(
        self,
        connection: sqlite3.Connection,
        *,
        hypothesis_id: str,
        research_campaign_id: str | None,
    ) -> int:
        scope_column = "experiment.research_campaign_id" if research_campaign_id is not None else "experiment.hypothesis_id"
        scope_value = research_campaign_id if research_campaign_id is not None else hypothesis_id
        candidate_count = int(
            connection.execute(
                f"""
                SELECT COUNT(*) FROM experiment_trials AS trial
                JOIN experiments AS experiment ON experiment.experiment_id = trial.experiment_id
                WHERE {scope_column} = ?
                  AND trial.dimension IN ('candidate_configuration', 'regime_segmentation')
                """,
                (scope_value,),
            ).fetchone()[0]
        )
        inherited_floor = self._campaign_predecessor_trial_floor(
            connection,
            research_campaign_id=research_campaign_id,
        )
        if candidate_count:
            return candidate_count + inherited_floor
        fallback_count = int(
            connection.execute(
                f"""
                SELECT COUNT(*) FROM experiment_trials AS trial
                JOIN experiments AS experiment ON experiment.experiment_id = trial.experiment_id
                WHERE {scope_column} = ?
                """,
                (scope_value,),
            ).fetchone()[0]
        )
        return fallback_count + inherited_floor

    def _validate_statistical_validation_artifact(
        self,
        connection: sqlite3.Connection,
        *,
        experiment_id: str,
        metrics: Mapping[str, Any] | None,
    ) -> None:
        if not isinstance(metrics, Mapping):
            raise ExperimentRegistryError("STRESS_MONTE_CARLO PASSED requires metrics evidence")
        try:
            artifact = StatisticalValidationArtifact.from_mapping(metrics.get("statistical_validation_artifact"))
        except (TypeError, ValueError) as exc:
            raise ExperimentRegistryError(f"invalid statistical validation artifact: {exc}") from exc
        if artifact.experiment_id != str(experiment_id):
            raise ExperimentRegistryError("statistical validation artifact experiment_id mismatch")
        assumed_trial_count = metrics.get("assumed_trial_count")
        if isinstance(assumed_trial_count, bool) or not isinstance(assumed_trial_count, int):
            raise ExperimentRegistryError("STRESS_MONTE_CARLO assumed_trial_count must be an integer")
        if assumed_trial_count != artifact.effective_trial_count:
            raise ExperimentRegistryError("assumed_trial_count must match statistical validation artifact")
        if str(metrics.get("trial_scope_id") or "").strip().lower() != artifact.trial_scope_id:
            raise ExperimentRegistryError("trial_scope_id must match statistical validation artifact")
        row = connection.execute(
            "SELECT hypothesis_id, research_campaign_id FROM experiments WHERE experiment_id = ?",
            (experiment_id,),
        ).fetchone()
        if row is None:
            raise ExperimentRegistryError(f"unknown experiment: {experiment_id}")
        hypothesis_id = str(row[0] or "").strip().lower()
        campaign_id = str(row[1] or "").strip().lower() or None
        registry_trial_count = self._validation_trial_count_for_scope(
            connection,
            hypothesis_id=hypothesis_id,
            research_campaign_id=campaign_id,
        )
        try:
            expected = StatisticalValidationArtifact(
                experiment_id=experiment_id,
                hypothesis_id=hypothesis_id,
                research_campaign_id=campaign_id,
                trial_scope_id=campaign_id or f"hypothesis_{hypothesis_id}",
                registry_trial_count=registry_trial_count,
                effective_trial_count=artifact.effective_trial_count,
            )
        except ValueError as exc:
            raise ExperimentRegistryError(str(exc)) from exc
        if artifact.to_dict() != expected.to_dict():
            raise ExperimentRegistryError("statistical validation artifact does not match append-only registry evidence")
        _validate_statistical_evidence_fingerprint(metrics)

    def has_final_holdout_review(self, experiment_id: str) -> bool:
        """Return whether immutable final-holdout evidence exists for one experiment."""

        if not self.path.exists():
            return False
        with self._connect() as connection:
            self._initialize(connection)
            return self._has_final_holdout_review(connection, experiment_id=experiment_id)

    def export_manifest(self, experiment_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            self._initialize(connection)
            experiment = connection.execute(
                "SELECT spec_json FROM experiments WHERE experiment_id = ?", (experiment_id,)
            ).fetchone()
            if not experiment:
                raise ExperimentRegistryError(f"unknown experiment: {experiment_id}")
            transitions = connection.execute(
                "SELECT stage, status, metrics_json, reasons_json, recorded_at FROM experiment_transitions WHERE experiment_id = ? ORDER BY recorded_at, transition_id",
                (experiment_id,),
            ).fetchall()
            trials = connection.execute(
                "SELECT dimension, value_json, uses_holdout, optimization, holdout_id, recorded_at FROM experiment_trials WHERE experiment_id = ? ORDER BY recorded_at, trial_id",
                (experiment_id,),
            ).fetchall()
            artifacts = connection.execute(
                "SELECT stage, path, fingerprint, metadata_json, recorded_at FROM experiment_artifacts WHERE experiment_id = ? ORDER BY recorded_at, artifact_id",
                (experiment_id,),
            ).fetchall()
            spec = json.loads(str(experiment[0]))
            holdout = None
            final_holdout_review_claim = None
            if spec.get("holdout_id"):
                holdout = connection.execute(
                    "SELECT data_snapshot_id, immutable_fingerprint, manifest_json, reserved_at FROM holdout_reservations WHERE holdout_id = ?",
                    (spec["holdout_id"],),
                ).fetchone()
                final_holdout_review_claim = connection.execute(
                    "SELECT experiment_id, claimed_at FROM final_holdout_review_claims WHERE holdout_id = ?",
                    (spec["holdout_id"],),
                ).fetchone()
        return {
            "experiment": spec,
            "state": self.get_state(experiment_id).to_dict(),
            "transitions": [
                {"stage": row[0], "status": row[1], "metrics": json.loads(row[2]), "reasons": json.loads(row[3]), "recorded_at": row[4]}
                for row in transitions
            ],
            "trials": [
                {
                    "dimension": row[0],
                    "value": json.loads(row[1]),
                    "uses_holdout": bool(row[2]),
                    "optimization": bool(row[3]),
                    "holdout_id": row[4],
                    "recorded_at": row[5],
                }
                for row in trials
            ],
            "artifacts": [
                {
                    "stage": row[0],
                    "path": row[1],
                    "fingerprint": row[2],
                    "metadata": json.loads(row[3]),
                    "recorded_at": row[4],
                }
                for row in artifacts
            ],
            "holdout": (
                {
                    "holdout_id": spec["holdout_id"],
                    "data_snapshot_id": holdout[0],
                    "immutable_fingerprint": holdout[1],
                    "manifest": json.loads(holdout[2]),
                    "reserved_at": holdout[3],
                }
                if holdout
                else None
            ),
            "final_holdout_review_claim": (
                {
                    "holdout_id": spec["holdout_id"],
                    "experiment_id": final_holdout_review_claim[0],
                    "claimed_at": final_holdout_review_claim[1],
                    "owned_by_experiment": final_holdout_review_claim[0] == experiment_id,
                }
                if final_holdout_review_claim
                else None
            ),
            "bounded_research_execution_claim": self._bounded_research_execution_claim(experiment_id),
            "research_only": True,
            "paper_capital_allowed": False,
            "live_allowed": False,
            "promotable": False,
        }

    def _state(self, connection: sqlite3.Connection, experiment_id: str) -> ExperimentState:
        experiment = connection.execute(
            "SELECT hypothesis_id, template_id, material_fingerprint FROM experiments WHERE experiment_id = ?",
            (experiment_id,),
        ).fetchone()
        if not experiment:
            raise ExperimentRegistryError(f"unknown experiment: {experiment_id}")
        latest = connection.execute(
            "SELECT stage, status FROM experiment_transitions WHERE experiment_id = ? ORDER BY recorded_at DESC, transition_id DESC LIMIT 1",
            (experiment_id,),
        ).fetchone()
        count = int(connection.execute("SELECT COUNT(*) FROM experiment_trials WHERE experiment_id = ?", (experiment_id,)).fetchone()[0])
        latest_stage = str(latest[0]) if latest else None
        latest_status = str(latest[1]) if latest else None
        completed = latest_stage == STAGES[-1] and latest_status == PASS_STATUS
        return ExperimentState(
            experiment_id=experiment_id,
            hypothesis_id=str(experiment[0]),
            template_id=str(experiment[1]),
            material_fingerprint=str(experiment[2]),
            latest_stage=latest_stage,
            latest_status=latest_status,
            terminal=latest_status in TERMINAL_STATUSES or completed,
            trial_count=count,
        )

    def _validate_successor_spec(self, connection: sqlite3.Connection, spec: ExperimentSpec) -> None:
        """Reject a campaign-only retry that lacks a material predecessor link.

        A successor is still a new append-only experiment.  This validation
        only establishes that it cannot drop the predecessor's multiple-testing
        burden or re-label a performance rejection as a data refresh.
        """

        predecessor_id = spec.predecessor_experiment_id
        if predecessor_id is None:
            return
        predecessor = connection.execute(
            "SELECT hypothesis_id, template_id, spec_json FROM experiments WHERE experiment_id = ?",
            (predecessor_id,),
        ).fetchone()
        if predecessor is None:
            raise ExperimentRegistryError("successor predecessor_experiment_id is unknown")
        predecessor_state = self._state(connection, predecessor_id)
        if predecessor_state.latest_status != "INSUFFICIENT_DATA":
            raise ExperimentRegistryError("successor predecessor must be terminal INSUFFICIENT_DATA, never a performance rejection")
        if str(predecessor[0]) != spec.hypothesis_id or str(predecessor[1]) != spec.template_id:
            raise ExperimentRegistryError("successor must preserve predecessor hypothesis_id and template_id")
        predecessor_spec = json.loads(str(predecessor[2]))
        prior_signature = predecessor_spec.get("material_data_signature")
        if not isinstance(prior_signature, Mapping) or not str(prior_signature.get("fingerprint") or "").strip():
            raise ExperimentRegistryError("successor predecessor lacks a comparable material_data_signature")
        current_signature = spec.material_data_signature or {}
        if str(prior_signature.get("fingerprint")) == str(current_signature.get("fingerprint")):
            raise ExperimentRegistryError("successor material_data_signature must differ from predecessor")
        required_floor = self._experiment_candidate_trial_count(connection, predecessor_id)
        if int(spec.predecessor_trial_count_floor or 0) < required_floor:
            raise ExperimentRegistryError("successor predecessor_trial_count_floor is below predecessor candidate trials")

    @staticmethod
    def _experiment_candidate_trial_count(connection: sqlite3.Connection, experiment_id: str) -> int:
        candidate_count = int(
            connection.execute(
                """
                SELECT COUNT(*) FROM experiment_trials
                WHERE experiment_id = ?
                  AND dimension IN ('candidate_configuration', 'regime_segmentation')
                """,
                (experiment_id,),
            ).fetchone()[0]
        )
        if candidate_count:
            return candidate_count
        return int(
            connection.execute(
                "SELECT COUNT(*) FROM experiment_trials WHERE experiment_id = ?",
                (experiment_id,),
            ).fetchone()[0]
        )

    @staticmethod
    def _campaign_predecessor_trial_floor(connection: sqlite3.Connection, *, research_campaign_id: str | None) -> int:
        if research_campaign_id is None:
            return 0
        rows = connection.execute(
            "SELECT spec_json FROM experiments WHERE research_campaign_id = ?",
            (research_campaign_id,),
        ).fetchall()
        floors_by_predecessor: dict[str, int] = {}
        for (raw_spec,) in rows:
            try:
                spec = json.loads(str(raw_spec))
            except json.JSONDecodeError as exc:
                raise ExperimentRegistryError("stored experiment spec is invalid JSON") from exc
            predecessor_id = str(spec.get("predecessor_experiment_id") or "").strip()
            floor = spec.get("predecessor_trial_count_floor")
            if predecessor_id and isinstance(floor, int) and floor > 0:
                floors_by_predecessor[predecessor_id] = max(floors_by_predecessor.get(predecessor_id, 0), floor)
        return sum(floors_by_predecessor.values())

    def _bounded_research_execution_claim(self, experiment_id: str) -> dict[str, str] | None:
        if not self.path.exists():
            return None
        with self._connect() as connection:
            self._initialize(connection)
            row = connection.execute(
                """
                SELECT execution_id, coordinator_run_id, claimed_at
                FROM bounded_research_execution_claims
                WHERE experiment_id = ?
                """,
                (experiment_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "execution_id": str(row[0]),
            "coordinator_run_id": str(row[1]),
            "claimed_at": str(row[2]),
        }

    @staticmethod
    def _validate_holdout_use(
        connection: sqlite3.Connection,
        *,
        experiment_id: str,
        uses_holdout: bool,
        holdout_id: str | None,
    ) -> str | None:
        if not uses_holdout:
            if holdout_id:
                raise ExperimentRegistryError("holdout_id requires uses_holdout=true")
            return None
        experiment = connection.execute(
            "SELECT spec_json FROM experiments WHERE experiment_id = ?", (experiment_id,)
        ).fetchone()
        if not experiment:
            raise ExperimentRegistryError(f"unknown experiment: {experiment_id}")
        reserved_id = str(json.loads(str(experiment[0])).get("holdout_id") or "").strip()
        if not reserved_id:
            raise ExperimentRegistryError("experiment has no reserved immutable holdout")
        if holdout_id and holdout_id != reserved_id:
            raise ExperimentRegistryError("trial holdout_id does not match the experiment holdout")
        reservation = connection.execute(
            "SELECT 1 FROM holdout_reservations WHERE holdout_id = ?", (reserved_id,)
        ).fetchone()
        if not reservation:
            raise ExperimentRegistryError("experiment holdout must be reserved before use")
        return reserved_id

    def _validate_final_holdout_artifact(
        self,
        *,
        experiment_id: str,
        metrics: Mapping[str, Any],
        artifact: Mapping[str, Any],
    ) -> Any:
        """Require final-review evidence to match the experiment's sealed partition.

        The CLI performs file-system verification before calling this method.
        The registry independently binds the resulting artifact to the immutable
        experiment and reservation so direct library calls cannot submit free
        metrics for an unrelated or unreserved holdout.
        """

        from .shadow_review_evidence import ShadowReviewEvidenceError, parse_shadow_review_evidence

        required = (
            "holdout_partition",
            "role",
            "result_fingerprint",
            "sha256",
            "data_root",
            "shadow_review_evidence",
        )
        if any(not artifact.get(key) for key in required):
            raise ExperimentRegistryError("final holdout artifact is incomplete")
        if str(artifact.get("role")) != FINAL_HOLDOUT_REVIEW_DIMENSION.replace("final_", ""):
            raise ExperimentRegistryError("final holdout artifact must use the holdout_review role")
        with self._connect() as connection:
            self._initialize(connection)
            row = connection.execute(
                "SELECT spec_json FROM experiments WHERE experiment_id = ?", (experiment_id,)
            ).fetchone()
            if not row:
                raise ExperimentRegistryError(f"unknown experiment: {experiment_id}")
            spec = json.loads(str(row[0]))
            environment = spec.get("environment")
            expected_partition = environment.get("holdout_partition") if isinstance(environment, Mapping) else None
            holdout_id = str(spec.get("holdout_id") or "").strip()
            if not isinstance(expected_partition, Mapping) or not holdout_id:
                raise ExperimentRegistryError("experiment lacks physical holdout partition provenance")
            if str(expected_partition.get("partition_id") or "") != holdout_id:
                raise ExperimentRegistryError("experiment holdout provenance does not match holdout_id")
            if dict(artifact.get("holdout_partition") or {}) != dict(expected_partition):
                raise ExperimentRegistryError("final holdout artifact partition does not match the experiment")
            reservation = connection.execute(
                "SELECT immutable_fingerprint, manifest_json FROM holdout_reservations WHERE holdout_id = ?",
                (holdout_id,),
            ).fetchone()
            if not reservation:
                raise ExperimentRegistryError("experiment holdout must be reserved before final review")
            if str(reservation[0]) != str(expected_partition.get("fingerprint") or ""):
                raise ExperimentRegistryError("holdout reservation fingerprint does not match experiment provenance")
            try:
                reservation_manifest = json.loads(str(reservation[1]))
            except json.JSONDecodeError as exc:
                raise ExperimentRegistryError("holdout reservation manifest is invalid") from exc
            if reservation_manifest != {"partition": dict(expected_partition)}:
                raise ExperimentRegistryError("holdout reservation provenance does not match the experiment")
        try:
            evidence = parse_shadow_review_evidence(
                artifact["shadow_review_evidence"],
                experiment_id=experiment_id,
            )
        except ShadowReviewEvidenceError as exc:
            raise ExperimentRegistryError(f"final holdout evidence is invalid: {exc}") from exc
        _validate_final_holdout_metrics(metrics, evidence=evidence)
        _validate_final_holdout_provenance(
            evidence=evidence,
            experiment_id=experiment_id,
            experiment_spec=spec,
            holdout_partition=expected_partition,
        )
        return evidence

    @staticmethod
    def _has_final_holdout_review(connection: sqlite3.Connection, *, experiment_id: str) -> bool:
        experiment = connection.execute(
            "SELECT spec_json FROM experiments WHERE experiment_id = ?", (experiment_id,)
        ).fetchone()
        if not experiment:
            raise ExperimentRegistryError(f"unknown experiment: {experiment_id}")
        try:
            spec = json.loads(str(experiment[0]))
        except json.JSONDecodeError:
            return False
        holdout_id = str(spec.get("holdout_id") or "").strip()
        if not holdout_id:
            return False
        claim = connection.execute(
            "SELECT experiment_id FROM final_holdout_review_claims WHERE holdout_id = ?", (holdout_id,)
        ).fetchone()
        if claim is None or str(claim[0]) != str(experiment_id):
            # Legacy records without an exclusive claim remain historical but
            # are intentionally not acceptable evidence for SHADOW_REVIEW.
            return False
        environment = spec.get("environment")
        expected_partition = environment.get("holdout_partition") if isinstance(environment, Mapping) else None
        if not isinstance(expected_partition, Mapping):
            return False
        rows = connection.execute(
                """
                SELECT value_json FROM experiment_trials
                WHERE experiment_id = ?
                  AND dimension = ?
                  AND uses_holdout = 1
                  AND optimization = 0
                  AND holdout_id = ?
                """,
                (experiment_id, FINAL_HOLDOUT_REVIEW_DIMENSION, holdout_id),
            ).fetchall()
        from .shadow_review_evidence import ShadowReviewEvidenceError, parse_shadow_review_evidence

        for row in rows:
            try:
                value = json.loads(str(row[0]))
                artifact = value.get("artifact") if isinstance(value, Mapping) else None
                evidence = value.get("shadow_review_evidence") if isinstance(value, Mapping) else None
                if not isinstance(artifact, Mapping) or not isinstance(evidence, Mapping):
                    continue
                parsed = parse_shadow_review_evidence(evidence, experiment_id=experiment_id)
                _validate_final_holdout_metrics(value.get("metrics") or {}, evidence=parsed)
                _validate_final_holdout_provenance(
                    evidence=parsed,
                    experiment_id=experiment_id,
                    experiment_spec=spec,
                    holdout_partition=expected_partition,
                )
            except (json.JSONDecodeError, ShadowReviewEvidenceError, ExperimentRegistryError, TypeError, ValueError):
                continue
            return True
        return False

    @classmethod
    def _require_final_holdout_review(cls, connection: sqlite3.Connection, *, experiment_id: str) -> None:
        if not cls._has_final_holdout_review(connection, experiment_id=experiment_id):
            raise ExperimentRegistryError(
                "SHADOW_REVIEW PASSED requires immutable final holdout review evidence"
            )

    @staticmethod
    def _record_artifact(
        connection: sqlite3.Connection,
        *,
        experiment_id: str,
        stage: str,
        artifact: Mapping[str, Any],
    ) -> None:
        path = str(artifact.get("path") or "").strip()
        fingerprint = str(artifact.get("fingerprint") or _fingerprint(dict(artifact)))
        artifact_id = ExperimentRegistry._artifact_id(
            experiment_id=experiment_id,
            stage=stage,
            artifact=artifact,
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO experiment_artifacts
                (artifact_id, experiment_id, stage, path, fingerprint, metadata_json, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (artifact_id, experiment_id, stage, path, fingerprint, _json(dict(artifact)), _now()),
        )

    @staticmethod
    def _artifact_id(*, experiment_id: str, stage: str, artifact: Mapping[str, Any]) -> str:
        path = str(artifact.get("path") or "").strip()
        fingerprint = str(artifact.get("fingerprint") or _fingerprint(dict(artifact)))
        if not path:
            raise ExperimentRegistryError("artifact path is required")
        return f"artifact_{_fingerprint({'experiment_id': experiment_id, 'stage': stage, 'path': path, 'fingerprint': fingerprint})[:20]}"

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=self._sqlite_timeout_seconds)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
            connection.execute("PRAGMA journal_mode = WAL")
            return connection
        except Exception:
            connection.close()
            raise

    def _run_write(self, operation_name: str, operation: Callable[[sqlite3.Connection], _T]) -> _T:
        """Run one idempotent registry write with bounded SQLite lock recovery.

        This helper is intentionally reserved for operations whose result can be
        re-read deterministically after an uncertain SQLite acknowledgement.
        More sensitive final-holdout recording remains separately fail-closed.
        """

        last_error: sqlite3.OperationalError | None = None
        for attempt in range(self._write_retries + 1):
            connection: sqlite3.Connection | None = None
            try:
                connection = self._connect()
                # Serialize the read/validate/write sequence across registry
                # processes. This prevents a second writer from observing an
                # absent experiment, holdout or claim between the first read
                # and its immutable insert.
                connection.execute("BEGIN IMMEDIATE")
                self._initialize(connection)
                result = operation(connection)
                connection.commit()
                return result
            except sqlite3.OperationalError as exc:
                if connection is not None:
                    try:
                        connection.rollback()
                    except sqlite3.DatabaseError as rollback_error:
                        raise ExperimentRegistryError(
                            f"experiment registry {operation_name} rollback failed"
                        ) from rollback_error
                if not _is_transient_lock(exc) or attempt >= self._write_retries:
                    raise
                last_error = exc
                delay = self._retry_base_delay_seconds * (2 ** attempt)
                logger.warning(
                    "Experiment-registry SQLite busy during %s; retry %s/%s in %.3fs",
                    operation_name,
                    attempt + 1,
                    self._write_retries,
                    delay,
                )
                self._sleeper(delay)
            except Exception:
                if connection is not None:
                    try:
                        connection.rollback()
                    except sqlite3.DatabaseError as rollback_error:
                        raise ExperimentRegistryError(
                            f"experiment registry {operation_name} rollback failed"
                        ) from rollback_error
                raise
            finally:
                if connection is not None:
                    connection.close()
        if last_error is not None:
            raise last_error
        raise AssertionError("unreachable experiment-registry SQLite retry state")

    @staticmethod
    def _initialize(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS experiments (
                experiment_id TEXT PRIMARY KEY,
                material_fingerprint TEXT NOT NULL UNIQUE,
                hypothesis_id TEXT NOT NULL,
                template_id TEXT NOT NULL,
                research_campaign_id TEXT,
                created_at TEXT NOT NULL,
                spec_json TEXT NOT NULL,
                research_only INTEGER NOT NULL CHECK (research_only = 1),
                paper_capital_allowed INTEGER NOT NULL CHECK (paper_capital_allowed = 0),
                live_allowed INTEGER NOT NULL CHECK (live_allowed = 0),
                promotable INTEGER NOT NULL CHECK (promotable = 0)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS experiment_trials (
                trial_id TEXT PRIMARY KEY,
                experiment_id TEXT NOT NULL REFERENCES experiments(experiment_id),
                dimension TEXT NOT NULL,
                value_json TEXT NOT NULL,
                uses_holdout INTEGER NOT NULL CHECK (uses_holdout IN (0, 1)),
                optimization INTEGER NOT NULL CHECK (optimization IN (0, 1)),
                holdout_id TEXT REFERENCES holdout_reservations(holdout_id),
                fingerprint TEXT NOT NULL UNIQUE,
                recorded_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS experiment_transitions (
                transition_id TEXT PRIMARY KEY,
                experiment_id TEXT NOT NULL REFERENCES experiments(experiment_id),
                stage TEXT NOT NULL,
                status TEXT NOT NULL,
                metrics_json TEXT NOT NULL,
                reasons_json TEXT NOT NULL,
                recorded_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS experiment_artifacts (
                artifact_id TEXT PRIMARY KEY,
                experiment_id TEXT NOT NULL REFERENCES experiments(experiment_id),
                stage TEXT NOT NULL,
                path TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                recorded_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS holdout_reservations (
                holdout_id TEXT PRIMARY KEY,
                data_snapshot_id TEXT NOT NULL,
                immutable_fingerprint TEXT NOT NULL,
                manifest_json TEXT NOT NULL DEFAULT '{}',
                reserved_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS final_holdout_review_claims (
                holdout_id TEXT PRIMARY KEY REFERENCES holdout_reservations(holdout_id),
                experiment_id TEXT NOT NULL UNIQUE REFERENCES experiments(experiment_id),
                claimed_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS legacy_memory_imports (
                legacy_run_id TEXT NOT NULL,
                record_fingerprint TEXT NOT NULL UNIQUE,
                record_json TEXT NOT NULL,
                imported_at TEXT NOT NULL,
                PRIMARY KEY (legacy_run_id, record_fingerprint)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS bounded_research_execution_claims (
                experiment_id TEXT PRIMARY KEY REFERENCES experiments(experiment_id),
                execution_id TEXT NOT NULL UNIQUE,
                coordinator_run_id TEXT NOT NULL,
                claimed_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS bounded_research_snapshot_claims (
                feature_snapshot_fingerprint TEXT PRIMARY KEY,
                claim_id TEXT NOT NULL UNIQUE,
                feature_snapshot_id TEXT NOT NULL,
                coordinator_run_id TEXT NOT NULL,
                claimed_at TEXT NOT NULL
            )
            """
        )
        _ensure_column(connection, "experiments", "research_campaign_id", "TEXT")
        _ensure_column(connection, "experiment_trials", "holdout_id", "TEXT REFERENCES holdout_reservations(holdout_id)")
        _ensure_column(connection, "holdout_reservations", "manifest_json", "TEXT NOT NULL DEFAULT '{}'")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_experiments_research_campaign_id ON experiments(research_campaign_id)"
        )
        for table in (
            "experiments",
            "experiment_trials",
            "experiment_transitions",
            "experiment_artifacts",
            "holdout_reservations",
            "final_holdout_review_claims",
            "legacy_memory_imports",
            "bounded_research_execution_claims",
            "bounded_research_snapshot_claims",
        ):
            _create_append_only_triggers(connection, table)


def _next_stage(stage: str) -> str:
    try:
        return next_research_stage(stage)
    except ValueError as exc:
        raise ExperimentRegistryError(str(exc)) from exc


def _validate_final_holdout_metrics(metrics: Mapping[str, Any], *, evidence: Any) -> None:
    """Bind the legacy summary fields to the sealed evidence envelope.

    Keeping this check inside the registry means a caller cannot submit one
    positive number to the old ``metrics`` field while attaching evidence for a
    different set of closed holdout trades.  The function intentionally accepts
    no execution concepts and only reads the immutable evidence contract.
    """

    if not isinstance(metrics, Mapping):
        raise ExperimentRegistryError("final holdout review metrics are required")
    try:
        supplied_net_pnl = float(metrics.get("net_pnl_eur"))
    except (TypeError, ValueError):
        raise ExperimentRegistryError("final holdout metrics must include net_pnl_eur") from None
    if not math.isfinite(supplied_net_pnl):
        raise ExperimentRegistryError("final holdout net_pnl_eur must be finite")
    if not math.isclose(supplied_net_pnl, float(evidence.net_pnl_eur), abs_tol=1e-9):
        raise ExperimentRegistryError("final holdout metrics net_pnl_eur does not match sealed evidence")
    supplied_count = metrics.get("trade_count")
    if supplied_count is not None:
        if isinstance(supplied_count, bool):
            raise ExperimentRegistryError("final holdout trade_count is invalid")
        try:
            normalized_count = int(supplied_count)
        except (TypeError, ValueError):
            raise ExperimentRegistryError("final holdout trade_count is invalid") from None
        if normalized_count != int(evidence.trade_count):
            raise ExperimentRegistryError("final holdout metrics trade_count does not match sealed evidence")


def _validate_final_holdout_provenance(
    *,
    evidence: Any,
    experiment_id: str,
    experiment_spec: Mapping[str, Any],
    holdout_partition: Mapping[str, Any],
) -> None:
    """Confirm that an evaluated holdout belongs to this frozen experiment.

    The evaluator signs the complete provenance.  The registry repeats the
    comparison against its immutable ExperimentSpec and physical partition so
    evidence cannot be copied from a different parameter set, feature bundle,
    cost profile, code revision or partition.
    """

    holdout = evidence.holdout_evaluation
    provenance = holdout.get("provenance")
    if not isinstance(provenance, Mapping):
        raise ExperimentRegistryError("sealed holdout provenance is required")
    expected = {
        "experiment_id": str(experiment_id),
        "code_commit": str(experiment_spec.get("code_commit") or ""),
        "feature_versions": {
            str(key): str(value) for key, value in dict(experiment_spec.get("feature_versions") or {}).items()
        },
        "parameter_fingerprint": _fingerprint(dict(experiment_spec.get("parameters") or {})),
        "cost_model_fingerprint": _fingerprint(dict(experiment_spec.get("cost_model") or {})),
    }
    for field_name, expected_value in expected.items():
        if provenance.get(field_name) != expected_value:
            raise ExperimentRegistryError(f"sealed holdout provenance {field_name} does not match experiment")
    partition_fields = {
        "partition_id": holdout_partition.get("partition_id"),
        "partition_fingerprint": holdout_partition.get("partition_fingerprint")
        or holdout_partition.get("fingerprint"),
        "holdout_snapshot_id": holdout_partition.get("holdout_snapshot_id"),
        "holdout_snapshot_fingerprint": holdout_partition.get("holdout_snapshot_fingerprint"),
        "source_snapshot_id": holdout_partition.get("source_snapshot_id"),
        "source_snapshot_fingerprint": holdout_partition.get("source_snapshot_fingerprint"),
    }
    for field_name, expected_value in partition_fields.items():
        if not str(expected_value or "").strip():
            raise ExperimentRegistryError(f"experiment holdout partition lacks {field_name}")
        if provenance.get(field_name) != expected_value:
            raise ExperimentRegistryError(f"sealed holdout provenance {field_name} does not match partition")


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _normalized_trial_values(values: Sequence[str], *, uppercase: bool = False) -> tuple[str, ...]:
    normalized = {
        (str(value).strip().upper() if uppercase else str(value).strip())
        for value in values
        if str(value).strip()
    }
    return tuple(sorted(normalized))


def _fingerprint(value: Any) -> str:
    return sha256(_json(value).encode("utf-8")).hexdigest()


def _is_transient_lock(error: sqlite3.OperationalError) -> bool:
    message = str(error).lower()
    return "locked" in message or "busy" in message


def _validate_passed_stage_evidence(
    *,
    stage: str,
    metrics: Mapping[str, Any] | None,
    artifacts: Sequence[Mapping[str, Any]],
) -> None:
    """Fail closed when a material research gate lacks reproducible evidence.

    The registry does not calculate the statistics itself, but it refuses to
    record a passed NET_SMOKE, WALK_FORWARD or STRESS_MONTE_CARLO transition
    unless the producer supplied the stage's minimum metrics and a
    content-addressed report artifact.  This blocks direct API callers from
    advancing a material experiment with an empty success record.
    """

    if stage not in RESEARCH_EVIDENCE_STAGES:
        return
    if not isinstance(metrics, Mapping) or not metrics:
        raise ExperimentRegistryError(f"{stage} PASSED requires metrics evidence")
    missing = sorted(key for key in REQUIRED_PASSED_METRIC_KEYS[stage] if key not in metrics)
    if missing:
        raise ExperimentRegistryError(
            f"{stage} PASSED missing required metrics: {', '.join(missing)}"
        )
    if not artifacts:
        raise ExperimentRegistryError(f"{stage} PASSED requires a content-addressed report artifact")
    for artifact in artifacts:
        if not isinstance(artifact, Mapping):
            raise ExperimentRegistryError(f"{stage} PASSED artifact must be a mapping")
        path = str(artifact.get("path") or "").strip()
        fingerprint = str(artifact.get("fingerprint") or "").strip().lower()
        if not path:
            raise ExperimentRegistryError(f"{stage} PASSED artifact path is required")
        if len(fingerprint) != 64 or any(character not in "0123456789abcdef" for character in fingerprint):
            raise ExperimentRegistryError(
                f"{stage} PASSED artifact fingerprint must be a SHA-256 digest"
            )


def _attach_statistical_evidence_fingerprint(metrics: dict[str, Any]) -> None:
    """Seal serialized PSR/DSR/robustness evidence before a passed stress gate.

    The registry cannot recompute statistics without the OOS trade sequence,
    but it can enforce that every serialized diagnostic describes the same
    sample and multiple-testing count as the immutable transition.  The
    resulting fingerprint makes that exact evidence visible in the append-only
    transition and rejects a later mismatched retry.
    """

    fingerprint = _statistical_evidence_fingerprint(metrics)
    supplied = str(metrics.get("statistical_evidence_fingerprint") or "").strip().lower()
    if supplied and supplied != fingerprint:
        raise ExperimentRegistryError("statistical evidence fingerprint does not match serialized evidence")
    metrics["statistical_evidence_fingerprint"] = fingerprint


def _validate_statistical_evidence_fingerprint(metrics: Mapping[str, Any]) -> None:
    supplied = str(metrics.get("statistical_evidence_fingerprint") or "").strip().lower()
    expected = _statistical_evidence_fingerprint(metrics)
    if supplied != expected:
        raise ExperimentRegistryError("statistical evidence fingerprint does not match serialized evidence")


def _statistical_evidence_fingerprint(metrics: Mapping[str, Any]) -> str:
    """Validate and fingerprint one passed statistical-gate payload.

    This is deliberately a serialization contract, not a second statistical
    implementation.  It prevents the DSR, PSR, robustness report and
    consolidated gate from silently referring to different samples or trial
    counts between the runner and the append-only experiment registry.
    """

    trade_count = _positive_metric_int(metrics.get("trade_count"), "trade_count")
    trial_count = _positive_metric_int(metrics.get("assumed_trial_count"), "assumed_trial_count")
    deflated = _required_metric_mapping(metrics, "deflated_sharpe")
    probabilistic = _required_metric_mapping(metrics, "probabilistic_sharpe")
    robustness = _required_metric_mapping(metrics, "robustness")
    summary = _required_metric_mapping(metrics, "statistical_gate")

    if _positive_metric_int(deflated.get("sample_count"), "deflated_sharpe.sample_count") != trade_count:
        raise ExperimentRegistryError("deflated_sharpe sample_count must match trade_count")
    if _positive_metric_int(deflated.get("assumed_trial_count"), "deflated_sharpe.assumed_trial_count") != trial_count:
        raise ExperimentRegistryError("deflated_sharpe assumed_trial_count must match assumed_trial_count")
    if _positive_metric_int(probabilistic.get("sample_count"), "probabilistic_sharpe.sample_count") != trade_count:
        raise ExperimentRegistryError("probabilistic_sharpe sample_count must match trade_count")
    if _positive_metric_int(robustness.get("trade_count"), "robustness.trade_count") != trade_count:
        raise ExperimentRegistryError("robustness trade_count must match trade_count")
    monte_carlo = _required_metric_mapping(robustness, "monte_carlo")
    if _positive_metric_int(monte_carlo.get("sample_count"), "robustness.monte_carlo.sample_count") != trade_count:
        raise ExperimentRegistryError("robustness monte_carlo sample_count must match trade_count")
    if _positive_metric_int(summary.get("trade_count"), "statistical_gate.trade_count") != trade_count:
        raise ExperimentRegistryError("statistical gate trade_count must match trade_count")
    if _positive_metric_int(summary.get("trial_count"), "statistical_gate.trial_count") != trial_count:
        raise ExperimentRegistryError("statistical gate trial_count must match assumed_trial_count")

    _require_metric_flags(deflated, "deflated_sharpe", paper_key="paper_candidate_allowed", live_key="live_promotion_allowed")
    _require_metric_flags(probabilistic, "probabilistic_sharpe", paper_key="paper_candidate_allowed", live_key="live_promotion_allowed")
    _require_metric_flags(robustness, "robustness", paper_key="paper_candidate_allowed", live_key="live_promotion_allowed")
    _require_metric_flags(summary, "statistical_gate", paper_key="paper_capital_allowed", live_key="live_allowed")

    if deflated.get("acceptable") is not True:
        raise ExperimentRegistryError("deflated_sharpe must be acceptable for a passed stress gate")
    if probabilistic.get("acceptable") is not True:
        raise ExperimentRegistryError("probabilistic_sharpe must be acceptable for a passed stress gate")
    if str(robustness.get("verdict") or "") != "observation_ready_not_promoted":
        raise ExperimentRegistryError("robustness verdict must remain observation_ready_not_promoted")
    decision = str(metrics.get("statistical_gate_decision") or "").strip()
    if decision != "SHADOW_REVIEW_ELIGIBLE" or str(summary.get("decision") or "").strip() != decision:
        raise ExperimentRegistryError("statistical gate decision must be SHADOW_REVIEW_ELIGIBLE and match its summary")
    if summary.get("shadow_review_eligible") is not True:
        raise ExperimentRegistryError("statistical gate summary must confirm shadow review eligibility")
    blockers = summary.get("blockers")
    if not isinstance(blockers, (list, tuple)) or blockers:
        raise ExperimentRegistryError("passed statistical gate summary cannot carry blockers")

    return _fingerprint(
        {
            "schema_version": 1,
            "trade_count": trade_count,
            "assumed_trial_count": trial_count,
            "trial_scope_id": str(metrics.get("trial_scope_id") or "").strip().lower(),
            "deflated_sharpe": dict(deflated),
            "probabilistic_sharpe": dict(probabilistic),
            "robustness": dict(robustness),
            "statistical_gate": dict(summary),
            "statistical_gate_decision": decision,
        }
    )


def _required_metric_mapping(payload: Mapping[str, Any], field_name: str) -> Mapping[str, Any]:
    value = payload.get(field_name)
    if not isinstance(value, Mapping):
        raise ExperimentRegistryError(f"{field_name} must be a mapping")
    return value


def _positive_metric_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ExperimentRegistryError(f"{field_name} must be a positive integer")
    return value


def _require_metric_flags(
    payload: Mapping[str, Any],
    field_name: str,
    *,
    paper_key: str,
    live_key: str,
) -> None:
    if payload.get("research_only") is not True:
        raise ExperimentRegistryError(f"{field_name} must remain research_only")
    if payload.get(paper_key) is not False or payload.get(live_key) is not False:
        raise ExperimentRegistryError(f"{field_name} cannot authorize paper or live")
    if field_name == "statistical_gate" and payload.get("promotable") is not False:
        raise ExperimentRegistryError("statistical_gate cannot be promotable")


def _runner_report_artifacts(report: Any) -> tuple[dict[str, Any], ...]:
    """Return content-addressed report evidence when the runner persisted it.

    In-memory/unit-test reports may have no files, which remains valid for
    transition testing. A real written report, however, becomes part of the
    reproducible experiment record instead of an unbound side file.
    """

    artifacts: list[dict[str, Any]] = []
    run_id = str(getattr(report, "run_id", "") or "").strip()
    for field_name, kind in (
        ("json_report_path", "runner_json_report"),
        ("markdown_report_path", "runner_markdown_report"),
    ):
        value = str(getattr(report, field_name, "") or "").strip()
        if not value:
            continue
        path = Path(value)
        if not path.is_file():
            continue
        artifacts.append(
            {
                "path": str(path),
                "fingerprint": sha256(path.read_bytes()).hexdigest(),
                "kind": kind,
                "runner_run_id": run_id,
            }
        )
    return tuple(artifacts)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_column(connection: sqlite3.Connection, table: str, column: str, declaration: str) -> None:
    columns = {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")


def _create_append_only_triggers(connection: sqlite3.Connection, table: str) -> None:
    for operation in ("UPDATE", "DELETE"):
        connection.execute(
            f"""
            CREATE TRIGGER IF NOT EXISTS {table.lower()}_append_only_{operation.lower()}
            BEFORE {operation} ON {table}
            BEGIN
                SELECT RAISE(ABORT, '{table} is append-only');
            END
            """
        )
