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
import math
from pathlib import Path
import sqlite3
from itertools import product
from typing import Any, Iterable, Mapping, Sequence

from .alpha_hypothesis_lab import CANONICAL_RESEARCH_STAGES, next_research_stage, normalize_research_stage

STAGES = CANONICAL_RESEARCH_STAGES
TERMINAL_STATUSES = {"REJECTED", "INSUFFICIENT_DATA"}
PASS_STATUS = "PASSED"
DEFAULT_EXPERIMENT_REGISTRY_PATH = Path("data/research/experiment_registry.sqlite3")
FINAL_HOLDOUT_REVIEW_DIMENSION = "final_holdout_review"


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

    @property
    def material_fingerprint(self) -> str:
        payload = asdict(self)
        # Keep the identity of pre-campaign experiment specifications stable.
        # A schema migration must never turn an identical legacy experiment
        # into a fresh material fingerprint that could be run a second time.
        if payload.get("research_campaign_id") is None:
            payload.pop("research_campaign_id", None)
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


class ExperimentRegistry:
    """SQLite-backed append-only experiment metadata, trials and gate evidence."""

    def __init__(self, path: str | Path = DEFAULT_EXPERIMENT_REGISTRY_PATH) -> None:
        self.path = Path(path)

    def register_experiment(self, spec: ExperimentSpec) -> ExperimentState:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            self._initialize(connection)
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
        with self._connect() as connection:
            self._initialize(connection)
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
        with self._connect() as connection:
            self._initialize(connection)
            previous = self._state(connection, experiment_id)
            if previous.terminal:
                raise ExperimentRegistryError("terminal experiment cannot advance")
            expected = STAGES[0] if previous.latest_stage is None else _next_stage(previous.latest_stage)
            if stage != expected:
                raise ExperimentRegistryError(f"expected stage {expected}, received {stage}")
            if stage == STAGES[-1] and status == PASS_STATUS:
                self._require_final_holdout_review(connection, experiment_id=experiment_id)
            transition_id = f"gate_{_fingerprint({'experiment_id': experiment_id, 'stage': stage, 'status': status, 'metrics': metrics or {}, 'reasons': list(reasons)})[:20]}"
            connection.execute(
                """
                INSERT OR IGNORE INTO experiment_transitions
                    (transition_id, experiment_id, stage, status, metrics_json, reasons_json, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (transition_id, experiment_id, stage, status, _json(metrics or {}), _json(list(reasons)), _now()),
            )
            for artifact in artifacts:
                self._record_artifact(connection, experiment_id=experiment_id, stage=stage, artifact=artifact)
            return self._state(connection, experiment_id)

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
            current = self.record_gate_result(
                experiment_id=state.experiment_id,
                stage=stage,
                status=status,
                metrics=dict(getattr(gate, "metrics", {}) or {}),
                reasons=tuple(str(item) for item in (getattr(gate, "reasons", ()) or ())),
                # The report is immutable evidence for the whole runner. Bind
                # it once at the first canonical gate rather than duplicating
                # the same artifact for every later transition.
                artifacts=runner_artifacts if stage == STAGES[0] else (),
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

        Block 2 candidate configurations are preferred because they encode the
        actual crossed decision surface.  When an explicit campaign is
        supplied, every material experiment in that campaign contributes to
        the correction.  Older registry evidence predating the campaign schema
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
        scope_column = "experiment.research_campaign_id" if normalized_campaign_id is not None else "experiment.hypothesis_id"
        scope_value = normalized_campaign_id if normalized_campaign_id is not None else normalized_hypothesis_id
        with self._connect() as connection:
            self._initialize(connection)
            candidate_count = int(
                connection.execute(
                    f"""
                    SELECT COUNT(*) FROM experiment_trials AS trial
                    JOIN experiments AS experiment ON experiment.experiment_id = trial.experiment_id
                    WHERE {scope_column} = ? AND trial.dimension = 'candidate_configuration'
                    """,
                    (scope_value,),
                ).fetchone()[0]
            )
            if candidate_count:
                return candidate_count
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
        return fallback_count

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
            if spec.get("holdout_id"):
                holdout = connection.execute(
                    "SELECT data_snapshot_id, immutable_fingerprint, manifest_json, reserved_at FROM holdout_reservations WHERE holdout_id = ?",
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
        if not path:
            raise ExperimentRegistryError("artifact path is required")
        artifact_id = f"artifact_{_fingerprint({'experiment_id': experiment_id, 'stage': stage, 'path': path, 'fingerprint': fingerprint})[:20]}"
        connection.execute(
            """
            INSERT OR IGNORE INTO experiment_artifacts
                (artifact_id, experiment_id, stage, path, fingerprint, metadata_json, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (artifact_id, experiment_id, stage, path, fingerprint, _json(dict(artifact)), _now()),
        )

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
