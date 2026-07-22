"""Read-only readiness audit for governed AUTOBOT shadow artifacts.

This module intentionally inspects SQLite registries through read-only
connections.  It never initializes or migrates a schema, creates an artifact,
starts shadow runtime, or imports the order/paper/runtime stacks.  Its purpose
is to expose the evidence that is still missing before a human could register
one non-executable shadow artifact.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sqlite3
from typing import Any


DEFAULT_EXPERIMENT_REGISTRY_PATH = Path("data/research/experiment_registry.sqlite3")
DEFAULT_ARTIFACT_REGISTRY_PATH = Path("data/research/strategy_artifacts.sqlite3")

_REQUIRED_EXPERIMENT_TABLES = frozenset({"experiments", "experiment_trials", "experiment_transitions"})
_REQUIRED_EXPERIMENT_COLUMNS = {
    "experiments": frozenset(
        {
            "experiment_id",
            "hypothesis_id",
            "template_id",
            "research_campaign_id",
            "created_at",
            "spec_json",
        }
    ),
    "experiment_trials": frozenset({"experiment_id", "dimension", "uses_holdout", "optimization"}),
    "experiment_transitions": frozenset({"experiment_id", "transition_id", "stage", "status", "recorded_at"}),
}


@dataclass(frozen=True)
class StrategyArtifactReadiness:
    """Evidence state for one immutable research experiment.

    ``artifact_registration_ready`` means only that experiment evidence has
    passed the immutable research gates.  It is deliberately not an execution
    authorization: a current risk mandate and explicit human approval remain
    required by ``shadow_governance``.
    """

    experiment_id: str
    hypothesis_id: str
    template_id: str
    latest_stage: str | None
    latest_status: str | None
    terminal: bool
    trial_count: int
    final_holdout_review_present: bool
    artifact_statuses: tuple[str, ...]
    state: str
    blockers: tuple[str, ...]
    artifact_registration_ready: bool
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False
    automatic_promotion_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StrategyArtifactReadinessAudit:
    """Stable, non-authorizing summary of artifact-readiness evidence."""

    registry_path: str
    artifact_registry_path: str
    status: str
    schema_status: str
    schema_blockers: tuple[str, ...]
    experiment_count: int
    artifact_count: int
    candidates: tuple[StrategyArtifactReadiness, ...]
    artifact_registration_ready_count: int
    research_only: bool = True
    shadow_runtime_started: bool = False
    paper_capital_allowed: bool = False
    live_allowed: bool = False
    automatic_promotion_allowed: bool = False
    order_created: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["candidates"] = [candidate.to_dict() for candidate in self.candidates]
        return payload


def audit_strategy_artifact_readiness(
    registry_path: str | Path = DEFAULT_EXPERIMENT_REGISTRY_PATH,
    *,
    artifact_registry_path: str | Path = DEFAULT_ARTIFACT_REGISTRY_PATH,
) -> StrategyArtifactReadinessAudit:
    """Inspect immutable evidence without mutating either registry.

    A missing registry and a legacy schema are both reported as blockers rather
    than being silently initialized.  The actual append-only migration remains
    an explicit normal ``ExperimentRegistry`` write path, keeping this audit
    safe for runtime snapshots and VPS diagnostics.
    """

    registry = Path(registry_path)
    artifact_registry = Path(artifact_registry_path)
    if not registry.exists():
        return StrategyArtifactReadinessAudit(
            registry_path=str(registry),
            artifact_registry_path=str(artifact_registry),
            status="REGISTRY_MISSING",
            schema_status="REGISTRY_MISSING",
            schema_blockers=("experiment_registry_missing",),
            experiment_count=0,
            artifact_count=0,
            candidates=(),
            artifact_registration_ready_count=0,
        )

    try:
        with _read_only_connection(registry) as connection:
            tables = _tables(connection)
            missing_tables = sorted(_REQUIRED_EXPERIMENT_TABLES - tables)
            if missing_tables:
                return StrategyArtifactReadinessAudit(
                    registry_path=str(registry),
                    artifact_registry_path=str(artifact_registry),
                    status="SCHEMA_MIGRATION_REQUIRED",
                    schema_status="STRUCTURALLY_INCOMPLETE",
                    schema_blockers=tuple(f"missing_table:{table}" for table in missing_tables),
                    experiment_count=0,
                    artifact_count=_artifact_count(artifact_registry),
                    candidates=(),
                    artifact_registration_ready_count=0,
                )

            schema_blockers = _schema_blockers(connection)
            experiment_rows = connection.execute(
                "SELECT experiment_id, hypothesis_id, template_id FROM experiments ORDER BY created_at, experiment_id"
            ).fetchall()
            artifact_statuses = _artifact_statuses_by_experiment(artifact_registry)
            candidates = tuple(
                _candidate_readiness(
                    connection,
                    experiment_id=str(row[0]),
                    hypothesis_id=str(row[1]),
                    template_id=str(row[2]),
                    schema_blockers=schema_blockers,
                    artifact_statuses=artifact_statuses.get(str(row[0]), ()),
                )
                for row in experiment_rows
            )
    except sqlite3.Error:
        return StrategyArtifactReadinessAudit(
            registry_path=str(registry),
            artifact_registry_path=str(artifact_registry),
            status="REGISTRY_UNAVAILABLE",
            schema_status="REGISTRY_UNAVAILABLE",
            schema_blockers=("experiment_registry_read_only_open_failed",),
            experiment_count=0,
            artifact_count=_artifact_count(artifact_registry),
            candidates=(),
            artifact_registration_ready_count=0,
        )

    ready_count = sum(candidate.artifact_registration_ready for candidate in candidates)
    if schema_blockers:
        status = "SCHEMA_MIGRATION_REQUIRED"
        schema_status = "LEGACY_SCHEMA"
    elif ready_count:
        status = "HUMAN_GOVERNANCE_REQUIRED"
        schema_status = "CURRENT"
    else:
        status = "NO_SHADOW_ARTIFACT_CANDIDATE"
        schema_status = "CURRENT"
    return StrategyArtifactReadinessAudit(
        registry_path=str(registry),
        artifact_registry_path=str(artifact_registry),
        status=status,
        schema_status=schema_status,
        schema_blockers=tuple(schema_blockers),
        experiment_count=len(candidates),
        artifact_count=_artifact_count(artifact_registry),
        candidates=candidates,
        artifact_registration_ready_count=ready_count,
    )


def _candidate_readiness(
    connection: sqlite3.Connection,
    *,
    experiment_id: str,
    hypothesis_id: str,
    template_id: str,
    schema_blockers: tuple[str, ...],
    artifact_statuses: tuple[str, ...],
) -> StrategyArtifactReadiness:
    transition = connection.execute(
        """
        SELECT stage, status
        FROM experiment_transitions
        WHERE experiment_id = ?
        ORDER BY recorded_at DESC, transition_id DESC
        LIMIT 1
        """,
        (experiment_id,),
    ).fetchone()
    latest_stage = str(transition[0]) if transition is not None else None
    latest_status = str(transition[1]) if transition is not None else None
    terminal = latest_status in {"REJECTED", "INSUFFICIENT_DATA"} or (
        latest_stage == "SHADOW_REVIEW" and latest_status == "PASSED"
    )
    trial_count = int(
        connection.execute("SELECT COUNT(*) FROM experiment_trials WHERE experiment_id = ?", (experiment_id,)).fetchone()[0]
    )
    final_holdout_review_present = bool(
        connection.execute(
            """
            SELECT 1 FROM experiment_trials
            WHERE experiment_id = ?
              AND dimension = 'final_holdout_review'
              AND uses_holdout = 1
              AND optimization = 0
            LIMIT 1
            """,
            (experiment_id,),
        ).fetchone()
    )

    blockers = list(schema_blockers)
    passed_shadow_review = latest_stage == "SHADOW_REVIEW" and latest_status == "PASSED" and terminal
    if not passed_shadow_review:
        blockers.append("terminal_shadow_review_not_passed")
    if not final_holdout_review_present:
        blockers.append("immutable_final_holdout_review_missing")
    if passed_shadow_review and final_holdout_review_present:
        blockers.extend(
            (
                "explicit_human_approval_reference_required",
                "immutable_shadow_risk_mandate_required",
            )
        )
    if not artifact_statuses:
        blockers.append("strategy_artifact_not_registered")
    ready = not schema_blockers and passed_shadow_review and final_holdout_review_present
    if ready:
        state = "EVIDENCE_READY_HUMAN_GOVERNANCE_REQUIRED"
    elif latest_status in {"REJECTED", "INSUFFICIENT_DATA"}:
        state = str(latest_status)
    elif latest_stage is None:
        state = "NOT_STARTED"
    else:
        state = "GATE_EVIDENCE_INCOMPLETE"
    return StrategyArtifactReadiness(
        experiment_id=experiment_id,
        hypothesis_id=hypothesis_id,
        template_id=template_id,
        latest_stage=latest_stage,
        latest_status=latest_status,
        terminal=terminal,
        trial_count=trial_count,
        final_holdout_review_present=final_holdout_review_present,
        artifact_statuses=tuple(sorted(set(artifact_statuses))),
        state=state,
        blockers=tuple(dict.fromkeys(blockers)),
        artifact_registration_ready=ready,
    )


def _schema_blockers(connection: sqlite3.Connection) -> tuple[str, ...]:
    blockers: list[str] = []
    for table, required_columns in _REQUIRED_EXPERIMENT_COLUMNS.items():
        columns = {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}
        for column in sorted(required_columns - columns):
            blockers.append(f"missing_column:{table}.{column}")
    return tuple(blockers)


def _artifact_statuses_by_experiment(path: Path) -> dict[str, tuple[str, ...]]:
    if not path.exists():
        return {}
    try:
        with _read_only_connection(path) as connection:
            if "strategy_artifacts" not in _tables(connection):
                return {}
            rows = connection.execute("SELECT status, artifact_json FROM strategy_artifacts").fetchall()
    except sqlite3.Error:
        return {}
    statuses: dict[str, list[str]] = {}
    for raw_status, raw_payload in rows:
        try:
            payload = json.loads(str(raw_payload))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        experiment_id = str(payload.get("experiment_id") or "").strip()
        status = str(raw_status or payload.get("status") or "").strip().upper()
        if experiment_id and status:
            statuses.setdefault(experiment_id, []).append(status)
    return {experiment_id: tuple(values) for experiment_id, values in statuses.items()}


def _artifact_count(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        with _read_only_connection(path) as connection:
            if "strategy_artifacts" not in _tables(connection):
                return 0
            return int(connection.execute("SELECT COUNT(*) FROM strategy_artifacts").fetchone()[0])
    except sqlite3.Error:
        return 0


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }


def _read_only_connection(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
