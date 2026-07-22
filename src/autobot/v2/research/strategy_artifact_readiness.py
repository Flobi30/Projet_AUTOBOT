"""Read-only readiness audit for governed AUTOBOT shadow artifacts.

This module intentionally inspects SQLite registries through read-only
connections.  It never initializes or migrates a schema, creates an artifact,
starts shadow runtime, or imports the order/paper/runtime stacks.  Its purpose
is to expose the evidence that is still missing before a human could register
one non-executable shadow artifact.
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from typing import Any

from autobot.v2.research.resilience_readiness import (
    ResilienceError,
    SQLiteBackupManifest,
    create_verified_sqlite_backup,
)


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


@dataclass(frozen=True)
class SQLiteAuditSnapshot:
    """Provenance for one short-lived SQLite snapshot used by a read-only audit.

    The snapshot is created through SQLite's backup API while the source is
    opened with ``mode=ro``.  The source checksum before/after is evidence for
    non-concurrent test runs; a change can also be caused by an independent
    runtime writer, so it is reported rather than blamed on the audit.
    """

    source_path: str
    source_sha256_before: str
    source_sha256_after: str
    snapshot_sha256: str
    integrity_check: str
    foreign_key_violation_count: int
    source_changed_during_snapshot: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StrategyArtifactSnapshotAudit:
    """An audit performed only against private, temporary SQLite snapshots.

    This is deliberately a diagnostic hand-off.  It neither retains a copy of
    the registry nor registers an artifact, starts shadow runtime, enables
    paper/live, or imports execution components.
    """

    status: str
    registry_path: str
    artifact_registry_path: str
    readiness: StrategyArtifactReadinessAudit | None
    registry_snapshot: SQLiteAuditSnapshot | None
    artifact_registry_snapshot: SQLiteAuditSnapshot | None
    temporary_snapshots_cleaned: bool
    blocker: str | None = None
    research_only: bool = True
    shadow_runtime_started: bool = False
    paper_capital_allowed: bool = False
    live_allowed: bool = False
    automatic_promotion_allowed: bool = False
    order_created: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["readiness"] = self.readiness.to_dict() if self.readiness is not None else None
        payload["registry_snapshot"] = self.registry_snapshot.to_dict() if self.registry_snapshot is not None else None
        payload["artifact_registry_snapshot"] = (
            self.artifact_registry_snapshot.to_dict() if self.artifact_registry_snapshot is not None else None
        )
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
        with closing(_read_only_connection(registry)) as connection:
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


def audit_strategy_artifact_readiness_snapshot(
    registry_path: str | Path = DEFAULT_EXPERIMENT_REGISTRY_PATH,
    *,
    artifact_registry_path: str | Path = DEFAULT_ARTIFACT_REGISTRY_PATH,
) -> StrategyArtifactSnapshotAudit:
    """Audit a consistent temporary snapshot instead of a live SQLite registry.

    SQLite WAL databases may require sidecar files for a direct read-only
    connection.  Taking a verified backup snapshot first prevents the audit
    worker from needing write access to the live registry directory and makes
    the second audit safe to run in a network-less, read-only container.  The
    audit fails closed if either existing source cannot be snapshotted; it
    never falls back to reading the live source directly.
    """

    registry_source = Path(registry_path).resolve()
    artifact_source = Path(artifact_registry_path).resolve()
    if not registry_source.is_file():
        readiness = audit_strategy_artifact_readiness(registry_source, artifact_registry_path=artifact_source)
        return StrategyArtifactSnapshotAudit(
            status=readiness.status,
            registry_path=str(registry_source),
            artifact_registry_path=str(artifact_source),
            readiness=readiness,
            registry_snapshot=None,
            artifact_registry_snapshot=None,
            temporary_snapshots_cleaned=True,
            blocker="experiment_registry_missing",
        )

    snapshot_paths: tuple[Path, ...] = ()
    try:
        with TemporaryDirectory(prefix="autobot-strategy-artifact-readiness-") as temporary_directory:
            temporary_root = Path(temporary_directory)
            registry_snapshot_path = temporary_root / "experiment_registry.sqlite3"
            registry_snapshot = _create_audit_snapshot(registry_source, registry_snapshot_path)
            snapshot_paths = (registry_snapshot_path,)

            artifact_snapshot: SQLiteAuditSnapshot | None = None
            audit_artifact_path = temporary_root / "strategy_artifacts.sqlite3"
            if artifact_source.is_file():
                artifact_snapshot = _create_audit_snapshot(artifact_source, audit_artifact_path)
                snapshot_paths = (*snapshot_paths, audit_artifact_path)

            readiness = audit_strategy_artifact_readiness(
                registry_snapshot_path,
                artifact_registry_path=audit_artifact_path,
            )
            # The facts in ``readiness`` came from snapshots, but callers need
            # stable source paths rather than now-deleted temporary filenames.
            readiness = replace(
                readiness,
                registry_path=str(registry_source),
                artifact_registry_path=str(artifact_source),
            )
            status = readiness.status
    except (OSError, ResilienceError, sqlite3.Error) as exc:
        return StrategyArtifactSnapshotAudit(
            status="SNAPSHOT_UNAVAILABLE",
            registry_path=str(registry_source),
            artifact_registry_path=str(artifact_source),
            readiness=None,
            registry_snapshot=None,
            artifact_registry_snapshot=None,
            temporary_snapshots_cleaned=all(not path.exists() for path in snapshot_paths),
            blocker=f"verified_snapshot_failed:{type(exc).__name__}",
        )

    return StrategyArtifactSnapshotAudit(
        status=status,
        registry_path=str(registry_source),
        artifact_registry_path=str(artifact_source),
        readiness=readiness,
        registry_snapshot=registry_snapshot,
        artifact_registry_snapshot=artifact_snapshot,
        temporary_snapshots_cleaned=all(not path.exists() for path in snapshot_paths),
    )


def _create_audit_snapshot(source: Path, destination: Path) -> SQLiteAuditSnapshot:
    source_sha256_before = _sha256_file(source)
    manifest = create_verified_sqlite_backup(source, destination)
    source_sha256_after = _sha256_file(source)
    return _snapshot_from_manifest(
        manifest,
        source_sha256_before=source_sha256_before,
        source_sha256_after=source_sha256_after,
    )


def _snapshot_from_manifest(
    manifest: SQLiteBackupManifest,
    *,
    source_sha256_before: str,
    source_sha256_after: str,
) -> SQLiteAuditSnapshot:
    return SQLiteAuditSnapshot(
        source_path=manifest.source_path,
        source_sha256_before=source_sha256_before,
        source_sha256_after=source_sha256_after,
        snapshot_sha256=manifest.backup_sha256,
        integrity_check=manifest.integrity_check,
        foreign_key_violation_count=manifest.foreign_key_violation_count,
        source_changed_during_snapshot=source_sha256_before != source_sha256_after,
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
        with closing(_read_only_connection(path)) as connection:
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
        with closing(_read_only_connection(path)) as connection:
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


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
