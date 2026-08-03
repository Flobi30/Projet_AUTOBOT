"""Fail-closed resilience primitives and paper-readiness evaluation.

All operations in this module are local and hermetic.  They model how AUTOBOT
must react to uncertainty; they neither submit/cancel orders nor change runtime
flags.  A readiness result is documentation for human review, never a mandate.
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
from shutil import rmtree
import sqlite3
from tempfile import TemporaryDirectory, mkdtemp, mkstemp
from time import sleep
from typing import Any, Callable, Mapping, Sequence, TypeVar


INCIDENT_TYPES = frozenset(
    {
        "WEBSOCKET_DISCONNECTED",
        "API_UNAVAILABLE",
        "DATA_STALE",
        "SQLITE_LOCKED",
        "SQLITE_CORRUPT",
        "DISK_FULL",
        "CONTAINER_RESTARTED",
        "ORDER_UNKNOWN",
        "RECONCILIATION_REQUIRED",
        "RISK_LIMIT_BREACH",
    }
)
FAIL_CLOSED_ACTIONS = (
    "NORMAL",
    "BLOCK_NEW_SIGNALS",
    "BLOCK_NEW_ORDERS",
    "CANCEL_OPEN_ORDERS",
    "REDUCE_POSITIONS",
    "HALT",
)
# This is intentionally an *instruction* map, not an execution map.  It
# captures the least set of monotonic safeguards a future independently
# approved executor must apply for each uncertainty class.  Research/shadow
# code may inspect or test it, but must not execute it.
_RECOVERY_STEPS_BY_INCIDENT: Mapping[str, tuple[str, ...]] = {
    "DATA_STALE": ("BLOCK_NEW_SIGNALS",),
    "WEBSOCKET_DISCONNECTED": ("BLOCK_NEW_SIGNALS", "BLOCK_NEW_ORDERS"),
    "API_UNAVAILABLE": ("BLOCK_NEW_ORDERS",),
    "SQLITE_LOCKED": ("BLOCK_NEW_ORDERS",),
    "CONTAINER_RESTARTED": ("BLOCK_NEW_SIGNALS", "BLOCK_NEW_ORDERS"),
    "SQLITE_CORRUPT": ("BLOCK_NEW_SIGNALS", "BLOCK_NEW_ORDERS", "HALT"),
    "DISK_FULL": ("BLOCK_NEW_SIGNALS", "BLOCK_NEW_ORDERS", "HALT"),
    "ORDER_UNKNOWN": ("BLOCK_NEW_SIGNALS", "BLOCK_NEW_ORDERS", "CANCEL_OPEN_ORDERS", "HALT"),
    "RECONCILIATION_REQUIRED": (
        "BLOCK_NEW_SIGNALS",
        "BLOCK_NEW_ORDERS",
        "CANCEL_OPEN_ORDERS",
        "HALT",
    ),
    "RISK_LIMIT_BREACH": (
        "BLOCK_NEW_SIGNALS",
        "BLOCK_NEW_ORDERS",
        "CANCEL_OPEN_ORDERS",
        "REDUCE_POSITIONS",
        "HALT",
    ),
}
_T = TypeVar("_T")


# This is a deliberately small, versioned inventory of SQLite state that is
# required to reconstruct AUTOBOT's research/observation safety posture.  It
# is not a discovery mechanism: a backup job must never silently sweep an
# arbitrary data directory or include credentials/configuration by accident.
DEFAULT_SQLITE_BACKUP_SCOPE: tuple[tuple[str, str, bool, str], ...] = (
    ("runtime_state", "data/autobot_state.db", True, "observation runtime state and append-only ledger"),
    ("global_kill_switch", "data/global_kill_switch.db", True, "persistent fail-closed kill-switch state"),
    ("experiment_registry", "data/research/experiment_registry.sqlite3", False, "append-only research experiment registry"),
    ("strategy_artifacts", "data/research/strategy_artifacts.sqlite3", False, "append-only governed strategy artifacts"),
)
SQLITE_BACKUP_SCOPE_VERSION = "autobot_sqlite_backup_scope_v1"
SQLITE_BACKUP_DURABILITY_MARKER_FILENAME = ".autobot_backup_bundle_durability.json"
SQLITE_BACKUP_DURABILITY_MARKER_SCHEMA_VERSION = 1


class ResilienceError(ValueError):
    """Raised when a resilience or readiness invariant is violated."""


@dataclass(frozen=True)
class RuntimeDeploymentEvidence:
    """Fresh, non-authorizing evidence from one controlled VPS validation.

    A readiness dossier cannot infer deployment health from local tests. This
    compact record binds a source commit to GitHub, VPS and container facts,
    while retaining only non-secret safety state. It is evidence for a human
    decision, never a mandate to enable paper or live execution.
    """

    source_commit: str
    github_commit: str
    vps_commit: str
    container_revision: str
    observed_at: str
    container_healthy: bool
    health_endpoint_healthy: bool
    websocket_connected: bool
    program_execution_locked: bool
    observation_only_runtime: bool
    paper_capital_disabled: bool
    live_disabled: bool
    automatic_promotion_disabled: bool

    def __post_init__(self) -> None:
        for field_name in ("source_commit", "github_commit", "vps_commit", "container_revision"):
            value = str(getattr(self, field_name)).strip().lower()
            if not _is_commit_identifier(value):
                raise ResilienceError(f"{field_name} must be a Git commit identifier")
            object.__setattr__(self, field_name, value)
        observed_at = _parse_aware_utc(self.observed_at, "observed_at")
        object.__setattr__(self, "observed_at", observed_at.isoformat())
        for field_name in (
            "container_healthy",
            "health_endpoint_healthy",
            "websocket_connected",
            "program_execution_locked",
            "observation_only_runtime",
            "paper_capital_disabled",
            "live_disabled",
            "automatic_promotion_disabled",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise ResilienceError(f"{field_name} must be a boolean")

    def blockers(
        self,
        *,
        evaluated_at: datetime,
        max_age_seconds: int,
    ) -> tuple[str, ...]:
        if max_age_seconds < 0:
            raise ResilienceError("max_deployment_evidence_age_seconds must be non-negative")
        now = _as_utc(evaluated_at)
        observed = _parse_aware_utc(self.observed_at, "observed_at")
        blockers: list[str] = []
        if observed > now:
            blockers.append("deployment_evidence_in_future")
        elif (now - observed).total_seconds() > max_age_seconds:
            blockers.append("deployment_evidence_stale")
        if self.source_commit != self.github_commit:
            blockers.append("github_commit_not_aligned_with_source")
        if self.source_commit != self.vps_commit:
            blockers.append("vps_commit_not_aligned_with_source")
        if self.source_commit != self.container_revision:
            blockers.append("container_revision_not_aligned_with_source")
        if not self.container_healthy:
            blockers.append("container_not_healthy")
        if not self.health_endpoint_healthy:
            blockers.append("health_endpoint_not_healthy")
        if not self.websocket_connected:
            blockers.append("websocket_not_connected")
        if not self.program_execution_locked:
            blockers.append("program_execution_lock_not_confirmed")
        if not self.observation_only_runtime:
            blockers.append("observation_only_runtime_not_confirmed")
        if not self.paper_capital_disabled:
            blockers.append("paper_capital_not_disabled")
        if not self.live_disabled:
            blockers.append("live_not_disabled")
        if not self.automatic_promotion_disabled:
            blockers.append("automatic_promotion_not_disabled")
        return tuple(blockers)


_RUNTIME_DEPLOYMENT_EVIDENCE_FIELDS = frozenset(
    {
        "source_commit",
        "github_commit",
        "vps_commit",
        "container_revision",
        "observed_at",
        "container_healthy",
        "health_endpoint_healthy",
        "websocket_connected",
        "program_execution_locked",
        "observation_only_runtime",
        "paper_capital_disabled",
        "live_disabled",
        "automatic_promotion_disabled",
    }
)


def runtime_deployment_evidence_from_mapping(payload: Mapping[str, Any]) -> RuntimeDeploymentEvidence:
    """Validate the exact non-secret schema emitted by the VPS verifier.

    The readiness path must not silently discard an unexpected field or infer a
    missing safety assertion.  This function only validates supplied evidence;
    it neither contacts a VPS nor changes a runtime state.
    """

    if not isinstance(payload, Mapping):
        raise ResilienceError("deployment evidence must be a JSON object")
    provided_fields = {str(field) for field in payload}
    missing = sorted(_RUNTIME_DEPLOYMENT_EVIDENCE_FIELDS - provided_fields)
    unexpected = sorted(provided_fields - _RUNTIME_DEPLOYMENT_EVIDENCE_FIELDS)
    if missing:
        raise ResilienceError(f"deployment evidence missing fields: {', '.join(missing)}")
    if unexpected:
        raise ResilienceError(f"deployment evidence has unexpected fields: {', '.join(unexpected)}")
    return RuntimeDeploymentEvidence(
        **{field: payload[field] for field in _RUNTIME_DEPLOYMENT_EVIDENCE_FIELDS}  # type: ignore[arg-type]
    )


def load_runtime_deployment_evidence(source: str | Path) -> RuntimeDeploymentEvidence:
    """Load one verifier record without accepting an implicit or partial schema."""

    path = Path(source)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResilienceError(f"unable to load deployment evidence: {path}") from exc
    return runtime_deployment_evidence_from_mapping(payload)


@dataclass(frozen=True)
class IncidentDecision:
    incident_type: str
    action: str
    reason: str
    risk_increase_allowed: bool = False
    paper_capital_allowed: bool = False
    live_allowed: bool = False

    def __post_init__(self) -> None:
        incident = str(self.incident_type).upper()
        action = _validate_action(self.action)
        if incident not in INCIDENT_TYPES or action not in FAIL_CLOSED_ACTIONS:
            raise ResilienceError("unsupported incident or fail-closed action")
        required_action = _RECOVERY_STEPS_BY_INCIDENT[incident][-1]
        if FAIL_CLOSED_ACTIONS.index(action) < FAIL_CLOSED_ACTIONS.index(required_action):
            raise ResilienceError("incident decision action is weaker than the required fail-closed action")
        reason = str(self.reason or "").strip()
        if not reason:
            raise ResilienceError("incident decision requires a non-empty reason")
        if self.risk_increase_allowed or self.paper_capital_allowed or self.live_allowed:
            raise ResilienceError("resilience decisions cannot increase risk or enable paper/live")
        object.__setattr__(self, "incident_type", incident)
        object.__setattr__(self, "action", action)
        object.__setattr__(self, "reason", reason)


@dataclass(frozen=True)
class FailClosedIncidentSummary:
    """Canonical, non-authorizing result for one or more runtime incidents."""

    incident_types: tuple[str, ...]
    action: str
    reasons: tuple[str, ...]
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False

    def __post_init__(self) -> None:
        normalized = _normalize_incident_types(self.incident_types)
        action = _validate_action(self.action)
        if normalized:
            required_action = "NORMAL"
            for incident in normalized:
                required_action = _more_severe(
                    required_action,
                    _RECOVERY_STEPS_BY_INCIDENT[incident][-1],
                )
            if FAIL_CLOSED_ACTIONS.index(action) < FAIL_CLOSED_ACTIONS.index(required_action):
                raise ResilienceError("incident summary action is weaker than the required fail-closed action")
        reasons = tuple(str(reason).strip() for reason in self.reasons)
        if normalized and (not reasons or any(not reason for reason in reasons)):
            raise ResilienceError("incident summary requires non-empty reasons")
        if self.research_only is not True or self.paper_capital_allowed or self.live_allowed:
            raise ResilienceError("incident summaries cannot authorize paper or live")
        object.__setattr__(self, "incident_types", normalized)
        object.__setattr__(self, "action", action)
        object.__setattr__(self, "reasons", reasons)


@dataclass(frozen=True)
class FailClosedRecoveryPlan:
    """Non-executable escalation steps for one or more uncertain states.

    The plan intentionally describes the required control-plane ordering only.
    It never calls an order router, cancels an order, closes a position, or
    changes a runtime flag.  This makes it safe to exercise in research and on
    the VPS while preserving a contract for a future independently reviewed
    execution boundary.
    """

    incident_types: tuple[str, ...]
    steps: tuple[str, ...]
    terminal_action: str
    execution_authorized: bool = False
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False

    def __post_init__(self) -> None:
        normalized_incidents = _normalize_incident_types(self.incident_types)
        if not normalized_incidents:
            raise ResilienceError("recovery plans require at least one incident")
        if not self.steps:
            raise ResilienceError("recovery plans require at least one step")
        normalized_steps = tuple(_validate_action(step) for step in self.steps)
        if "NORMAL" in normalized_steps:
            raise ResilienceError("recovery plans cannot contain NORMAL")
        if tuple(sorted(set(normalized_steps), key=FAIL_CLOSED_ACTIONS.index)) != normalized_steps:
            raise ResilienceError("recovery plan steps must be unique and monotonic")
        required_steps: set[str] = set()
        for incident in normalized_incidents:
            required_steps.update(_RECOVERY_STEPS_BY_INCIDENT[incident])
        if not required_steps.issubset(set(normalized_steps)):
            raise ResilienceError("recovery plan omits a required fail-closed step")
        terminal = _validate_action(self.terminal_action)
        if terminal != normalized_steps[-1]:
            raise ResilienceError("recovery plan terminal action must match its final step")
        required_terminal = max(required_steps, key=FAIL_CLOSED_ACTIONS.index)
        if FAIL_CLOSED_ACTIONS.index(terminal) < FAIL_CLOSED_ACTIONS.index(required_terminal):
            raise ResilienceError("recovery plan terminal action is weaker than required")
        if self.execution_authorized or self.research_only is not True or self.paper_capital_allowed or self.live_allowed:
            raise ResilienceError("recovery plans cannot authorize execution, paper or live")
        object.__setattr__(self, "incident_types", normalized_incidents)
        object.__setattr__(self, "steps", normalized_steps)
        object.__setattr__(self, "terminal_action", terminal)


@dataclass(frozen=True)
class FailClosedDrillScenario:
    """One hermetic proof that an incident follows the declared hierarchy."""

    incident_type: str
    decision_action: str
    recovery_steps: tuple[str, ...]
    passed: bool


@dataclass(frozen=True)
class FailClosedDrillReport:
    """Evidence from a side-effect-free fail-closed hierarchy drill."""

    scenarios: tuple[FailClosedDrillScenario, ...]
    composite_incident_types: tuple[str, ...]
    composite_steps: tuple[str, ...]
    composite_terminal_action: str
    all_passed: bool
    order_submission_attempted: bool = False
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.scenarios or not self.composite_incident_types:
            raise ResilienceError("fail-closed drills require at least one scenario")
        if not self.all_passed:
            raise ResilienceError("fail-closed drill cannot report success with failed scenarios")
        if self.order_submission_attempted or self.research_only is not True or self.paper_capital_allowed or self.live_allowed:
            raise ResilienceError("fail-closed drills cannot submit orders or authorize paper/live")


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    initial_delay_seconds: float = 0.05
    multiplier: float = 2.0
    max_delay_seconds: float = 1.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ResilienceError("max_attempts must be positive")
        for field_name in ("initial_delay_seconds", "multiplier", "max_delay_seconds"):
            value = float(getattr(self, field_name))
            if not math.isfinite(value) or value < 0.0:
                raise ResilienceError(f"{field_name} must be finite and non-negative")
        if self.multiplier < 1.0:
            raise ResilienceError("retry multiplier must be at least one")


@dataclass(frozen=True)
class RetryResult:
    recovered: bool
    attempts: int
    delays_seconds: tuple[float, ...]
    error_type: str | None
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False


@dataclass(frozen=True)
class SQLiteBackupManifest:
    source_path: str
    backup_path: str
    source_sha256: str
    backup_sha256: str
    integrity_check: str
    foreign_key_violation_count: int
    encrypted: bool
    created_at: str
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False


@dataclass(frozen=True)
class SQLiteBackupScopeEntry:
    """One fixed, non-secret SQLite source included in the resilience scope."""

    identifier: str
    relative_source_path: str
    required: bool
    purpose: str

    def __post_init__(self) -> None:
        identifier = str(self.identifier).strip().lower()
        if not identifier or not all(character.isalnum() or character == "_" for character in identifier):
            raise ResilienceError("backup scope identifier must contain only lowercase-safe characters")
        relative_path = Path(str(self.relative_source_path))
        if relative_path.is_absolute() or ".." in relative_path.parts or not relative_path.parts:
            raise ResilienceError("backup scope source must be a relative path")
        if relative_path.parts[0] != "data" or relative_path.suffix.lower() not in {".db", ".sqlite3"}:
            raise ResilienceError("backup scope source must be a SQLite file below data/")
        if not isinstance(self.required, bool) or not str(self.purpose).strip():
            raise ResilienceError("backup scope entry requires required flag and purpose")
        object.__setattr__(self, "identifier", identifier)
        object.__setattr__(self, "relative_source_path", relative_path.as_posix())
        object.__setattr__(self, "purpose", str(self.purpose).strip())


@dataclass(frozen=True)
class SQLiteBackupScopeAuditEntry:
    """Read-only availability evidence for one fixed backup source."""

    identifier: str
    relative_source_path: str
    purpose: str
    required: bool
    status: str
    source_path: str
    source_sha256: str | None

    def __post_init__(self) -> None:
        if self.status not in {"READY", "MISSING_REQUIRED", "MISSING_OPTIONAL"}:
            raise ResilienceError("unsupported backup scope audit status")
        if self.status == "READY" and not _is_sha256(self.source_sha256):
            raise ResilienceError("ready backup source requires a SHA-256 fingerprint")
        if self.status != "READY" and self.source_sha256 is not None:
            raise ResilienceError("missing backup source cannot carry a fingerprint")


@dataclass(frozen=True)
class SQLiteBackupScopeAudit:
    """Read-only inventory of the explicitly allowed local backup sources."""

    repo_dir: str
    scope_version: str
    scope_fingerprint: str
    entries: tuple[SQLiteBackupScopeAuditEntry, ...]
    audited_at: str
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False

    def __post_init__(self) -> None:
        if self.scope_version != SQLITE_BACKUP_SCOPE_VERSION or not _is_sha256(self.scope_fingerprint):
            raise ResilienceError("backup scope audit requires the canonical scope and fingerprint")
        if self.research_only is not True or self.paper_capital_allowed or self.live_allowed:
            raise ResilienceError("backup scope audits cannot authorize paper or live")
        _parse_aware_utc(self.audited_at, "audited_at")
        identifiers = tuple(entry.identifier for entry in self.entries)
        if not identifiers or len(identifiers) != len(set(identifiers)):
            raise ResilienceError("backup scope audit identifiers must be unique")

    @property
    def missing_required(self) -> tuple[str, ...]:
        return tuple(entry.identifier for entry in self.entries if entry.status == "MISSING_REQUIRED")

    @property
    def ready_entries(self) -> tuple[SQLiteBackupScopeAuditEntry, ...]:
        return tuple(entry for entry in self.entries if entry.status == "READY")


@dataclass(frozen=True)
class SQLiteBackupBundleEntry:
    """One completed or explicitly skipped member of a local backup bundle."""

    audit: SQLiteBackupScopeAuditEntry
    status: str
    backup: SQLiteBackupManifest | None

    def __post_init__(self) -> None:
        if self.status not in {"BACKED_UP", "SKIPPED_OPTIONAL_MISSING"}:
            raise ResilienceError("unsupported backup bundle entry status")
        if self.status == "BACKED_UP":
            if self.audit.status != "READY" or self.backup is None:
                raise ResilienceError("backed-up scope entry requires ready source evidence")
        elif self.audit.status != "MISSING_OPTIONAL" or self.backup is not None:
            raise ResilienceError("only optional missing scope entries may be skipped")


@dataclass(frozen=True)
class SQLiteBackupBundleManifest:
    """Local bundle of approved SQLite resilience sources.

    Individual SQLite snapshots are integrity-checked, but they are captured
    sequentially and are not an inter-database transaction.  The manifest
    records the capture window so later recovery review does not infer a false
    global atomicity.  Retention, encryption and off-VPS replication remain
    separate operator-policy responsibilities.
    """

    bundle_id: str
    bundle_path: str
    manifest_path: str
    scope: SQLiteBackupScopeAudit
    entries: tuple[SQLiteBackupBundleEntry, ...]
    capture_started_at: str
    capture_finished_at: str
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False

    def __post_init__(self) -> None:
        if self.research_only is not True or self.paper_capital_allowed or self.live_allowed:
            raise ResilienceError("SQLite backup bundles cannot authorize paper or live")
        _validate_backup_bundle_id(self.bundle_id)
        capture_started_at = _parse_aware_utc(self.capture_started_at, "capture_started_at")
        capture_finished_at = _parse_aware_utc(self.capture_finished_at, "capture_finished_at")
        if capture_finished_at < capture_started_at:
            raise ResilienceError("backup bundle capture window is invalid")
        if self.scope.missing_required:
            raise ResilienceError("backup bundle cannot be complete with missing required scope sources")
        if not self.entries:
            raise ResilienceError("backup bundle requires at least one scope entry")
        identifiers = tuple(entry.audit.identifier for entry in self.entries)
        if identifiers != tuple(entry.identifier for entry in self.scope.entries):
            raise ResilienceError("backup bundle entries must preserve the canonical scope order")
        if any(entry.status == "BACKED_UP" and entry.backup is None for entry in self.entries):
            raise ResilienceError("backup bundle entry is missing its backup manifest")


@dataclass(frozen=True)
class SQLiteBackupBundleRestoreDrillEntry:
    """Read-only restoration evidence for one bundled SQLite snapshot."""

    identifier: str
    backup_path: str
    restore: SQLiteRestoreDrillManifest

    def __post_init__(self) -> None:
        _validate_backup_bundle_id(self.identifier)
        if Path(self.backup_path).name != f"{self.identifier}.sqlite3":
            raise ResilienceError("backup bundle restore entry has an unexpected snapshot filename")


@dataclass(frozen=True)
class SQLiteBackupBundleRestoreDrillManifest:
    """Evidence that every present bundle member restored in disposable space."""

    bundle_path: str
    bundle_manifest_sha256_before: str
    bundle_manifest_sha256_after: str
    entries: tuple[SQLiteBackupBundleRestoreDrillEntry, ...]
    verified_at: str
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False

    def __post_init__(self) -> None:
        if self.research_only is not True or self.paper_capital_allowed or self.live_allowed:
            raise ResilienceError("backup bundle restore drills cannot authorize paper or live")
        if not _is_sha256(self.bundle_manifest_sha256_before) or not _is_sha256(self.bundle_manifest_sha256_after):
            raise ResilienceError("backup bundle restore drill requires manifest fingerprints")
        if self.bundle_manifest_sha256_before != self.bundle_manifest_sha256_after:
            raise ResilienceError("backup bundle restore drill modified its manifest input")
        _parse_aware_utc(self.verified_at, "verified_at")
        identifiers = tuple(entry.identifier for entry in self.entries)
        if not identifiers or len(identifiers) != len(set(identifiers)):
            raise ResilienceError("backup bundle restore drill entries must be unique")


@dataclass(frozen=True)
class SQLiteRestoreDrillManifest:
    backup_path: str
    backup_sha256_before: str
    backup_sha256_after: str
    restored_sha256: str
    source_schema_sha256: str
    restored_schema_sha256: str
    source_table_row_counts: Mapping[str, int]
    restored_table_row_counts: Mapping[str, int]
    integrity_check: str
    source_foreign_key_violation_count: int
    restored_foreign_key_violation_count: int
    temporary_restore_cleaned: bool
    verified_at: str
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False


@dataclass(frozen=True)
class EphemeralSQLiteRestoreDrillManifest:
    """Evidence from a backup/restore drill that leaves no retained backup."""

    source_path: str
    backup: SQLiteBackupManifest
    restore: SQLiteRestoreDrillManifest
    temporary_backup_cleaned: bool
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False

    def __post_init__(self) -> None:
        if self.research_only is not True or self.paper_capital_allowed or self.live_allowed:
            raise ResilienceError("ephemeral restore drills cannot authorize paper or live")
        if not self.temporary_backup_cleaned:
            raise ResilienceError("ephemeral restore drill must remove its temporary backup")


@dataclass(frozen=True)
class LayerVerificationResult:
    """One fail-closed assessment of a declared 24-layer coverage row.

    ``VERIFIED`` is deliberately harder than a prose claim in the coverage
    matrix.  It must bind the current source revision to concrete code, test
    and runtime-evidence files inside the reviewed repository.  This value is
    only review evidence; it never authorizes any execution mode.
    """

    layer_id: int
    declared_status: str
    effective_status: str
    blockers: tuple[str, ...]
    verification_source_commit: str | None = None


@dataclass(frozen=True)
class LayerCoverageAudit:
    """Read-only validation of the machine-readable 24-layer matrix."""

    coverage_path: str
    repository_root: str
    expected_source_commit: str | None
    schema_version: int | None
    results: tuple[LayerVerificationResult, ...]
    blockers: tuple[str, ...]
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False
    automatic_promotion_allowed: bool = False

    def __post_init__(self) -> None:
        if (
            self.research_only is not True
            or self.paper_capital_allowed
            or self.live_allowed
            or self.automatic_promotion_allowed
        ):
            raise ResilienceError("layer coverage audits cannot authorize execution")

    @property
    def effective_statuses(self) -> dict[int, str]:
        return {result.layer_id: result.effective_status for result in self.results}

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PaperReadinessDossier:
    status: str
    blockers: tuple[str, ...]
    layer_statuses: Mapping[int, str]
    kill_switch_tested: bool
    reconciliation_tested: bool
    restore_tested: bool
    deployment_evidence: RuntimeDeploymentEvidence | None = None
    coverage_audit: LayerCoverageAudit | None = None
    paper_capital_allowed: bool = False
    live_allowed: bool = False
    automatic_promotion_allowed: bool = False

    def __post_init__(self) -> None:
        if self.status not in {"READY_FOR_HUMAN_PAPER_REVIEW", "NOT_READY_FOR_HUMAN_PAPER_REVIEW"}:
            raise ResilienceError("unsupported paper readiness status")
        if self.paper_capital_allowed or self.live_allowed or self.automatic_promotion_allowed:
            raise ResilienceError("paper readiness dossiers cannot authorize paper, live or promotion")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def decide_fail_closed(incident_type: str, *, previous_action: str = "NORMAL") -> IncidentDecision:
    """Map uncertainty to a monotonic risk-reducing action."""

    incident = str(incident_type).upper()
    if incident not in INCIDENT_TYPES:
        raise ResilienceError(f"unsupported incident type: {incident_type}")
    mapping = {
        "WEBSOCKET_DISCONNECTED": ("BLOCK_NEW_ORDERS", "market_stream_disconnected"),
        "API_UNAVAILABLE": ("BLOCK_NEW_ORDERS", "exchange_api_unavailable"),
        "DATA_STALE": ("BLOCK_NEW_SIGNALS", "market_data_stale"),
        "SQLITE_LOCKED": ("BLOCK_NEW_ORDERS", "persistence_lock_uncertain_state"),
        "SQLITE_CORRUPT": ("HALT", "persistence_integrity_untrusted"),
        "DISK_FULL": ("HALT", "persistence_cannot_be_trusted"),
        "CONTAINER_RESTARTED": ("BLOCK_NEW_ORDERS", "state_reconciliation_required_after_restart"),
        "ORDER_UNKNOWN": ("HALT", "order_state_unknown"),
        "RECONCILIATION_REQUIRED": ("HALT", "position_or_order_divergence"),
        "RISK_LIMIT_BREACH": ("HALT", "risk_limit_breach_requires_manual_review"),
    }
    calculated, reason = mapping[incident]
    action = _more_severe(_validate_action(previous_action), calculated)
    return IncidentDecision(incident, action, reason)


def plan_fail_closed_recovery(incident_types: Sequence[str]) -> FailClosedRecoveryPlan:
    """Return the future execution-control ordering without performing it.

    Every action is a fail-closed control-plane instruction.  In particular,
    ``CANCEL_OPEN_ORDERS`` and ``REDUCE_POSITIONS`` are evidence of the order
    in which a future reviewed execution boundary must act; this research
    helper deliberately does neither.
    """

    normalized = _normalize_incident_types(incident_types)
    if not normalized:
        raise ResilienceError("recovery plans require at least one incident")
    steps: set[str] = set()
    for incident in normalized:
        steps.update(_RECOVERY_STEPS_BY_INCIDENT[incident])
    ordered = tuple(sorted(steps, key=FAIL_CLOSED_ACTIONS.index))
    return FailClosedRecoveryPlan(
        incident_types=normalized,
        steps=ordered,
        terminal_action=ordered[-1],
    )


def run_fail_closed_drill(incident_types: Sequence[str] | None = None) -> FailClosedDrillReport:
    """Exercise the complete hierarchy in memory without touching runtime state."""

    normalized = _normalize_incident_types(incident_types or tuple(sorted(INCIDENT_TYPES)))
    if not normalized:
        raise ResilienceError("fail-closed drills require at least one incident")
    scenarios: list[FailClosedDrillScenario] = []
    for incident in normalized:
        decision = decide_fail_closed(incident)
        recovery = plan_fail_closed_recovery((incident,))
        passed = (
            recovery.terminal_action == decision.action
            and recovery.steps == _RECOVERY_STEPS_BY_INCIDENT[incident]
            and recovery.execution_authorized is False
        )
        scenarios.append(
            FailClosedDrillScenario(
                incident_type=incident,
                decision_action=decision.action,
                recovery_steps=recovery.steps,
                passed=passed,
            )
        )
    composite = plan_fail_closed_recovery(normalized)
    expected_terminal = summarize_fail_closed_incidents(normalized).action
    all_passed = all(scenario.passed for scenario in scenarios) and composite.terminal_action == expected_terminal
    return FailClosedDrillReport(
        scenarios=tuple(scenarios),
        composite_incident_types=normalized,
        composite_steps=composite.steps,
        composite_terminal_action=composite.terminal_action,
        all_passed=all_passed,
    )


def summarize_fail_closed_incidents(incident_types: Sequence[str]) -> FailClosedIncidentSummary:
    """Collapse current incidents into one monotonic, non-authorizing action.

    This is a bridge from runtime health observations into the future risk
    envelope. It remains side-effect free: callers decide how to enforce the
    resulting reduction, block or halt.
    """

    normalized = _normalize_incident_types(incident_types)
    action = "NORMAL"
    reasons: list[str] = []
    for incident in normalized:
        decision = decide_fail_closed(incident, previous_action=action)
        action = decision.action
        reasons.append(f"{incident.lower()}:{decision.reason}")
    return FailClosedIncidentSummary(
        incident_types=normalized,
        action=action,
        reasons=tuple(reasons),
    )


def retry_bounded(
    operation: Callable[[], _T],
    *,
    retryable: tuple[type[BaseException], ...],
    policy: RetryPolicy = RetryPolicy(),
    sleeper: Callable[[float], None] = sleep,
) -> tuple[_T | None, RetryResult]:
    """Retry only known transient failures; never hide a final error state."""

    delays: list[float] = []
    for attempt in range(1, policy.max_attempts + 1):
        try:
            return operation(), RetryResult(True, attempt, tuple(delays), None)
        except retryable as exc:
            if attempt >= policy.max_attempts:
                return None, RetryResult(False, attempt, tuple(delays), type(exc).__name__)
            delay = min(policy.max_delay_seconds, policy.initial_delay_seconds * (policy.multiplier ** (attempt - 1)))
            delays.append(delay)
            sleeper(delay)
    raise AssertionError("retry policy exhausted without producing a result")


def canonical_sqlite_backup_scope() -> tuple[SQLiteBackupScopeEntry, ...]:
    """Return the fixed, versioned set of non-secret SQLite backup sources."""

    return tuple(SQLiteBackupScopeEntry(*entry) for entry in DEFAULT_SQLITE_BACKUP_SCOPE)


def audit_sqlite_backup_scope(repo_dir: str | Path) -> SQLiteBackupScopeAudit:
    """Inspect the fixed local SQLite scope without creating backups or directories."""

    resolved_repo_dir = Path(repo_dir).resolve()
    if not resolved_repo_dir.is_dir():
        raise ResilienceError("backup scope repository directory does not exist")
    resolved_data_dir = (resolved_repo_dir / "data").resolve()
    scope = canonical_sqlite_backup_scope()
    scope_fingerprint = _sqlite_backup_scope_fingerprint(scope)
    audit_entries: list[SQLiteBackupScopeAuditEntry] = []
    for entry in scope:
        source_path = (resolved_repo_dir / entry.relative_source_path).resolve()
        if not _is_path_within(source_path, resolved_data_dir):
            raise ResilienceError("backup scope source resolves outside the repository data directory")
        if source_path.is_file():
            status = "READY"
            source_sha256: str | None = _sha256_file(source_path)
        else:
            status = "MISSING_REQUIRED" if entry.required else "MISSING_OPTIONAL"
            source_sha256 = None
        audit_entries.append(
            SQLiteBackupScopeAuditEntry(
                identifier=entry.identifier,
                relative_source_path=entry.relative_source_path,
                purpose=entry.purpose,
                required=entry.required,
                status=status,
                source_path=str(source_path),
                source_sha256=source_sha256,
            )
        )
    return SQLiteBackupScopeAudit(
        repo_dir=str(resolved_repo_dir),
        scope_version=SQLITE_BACKUP_SCOPE_VERSION,
        scope_fingerprint=scope_fingerprint,
        entries=tuple(audit_entries),
        audited_at=datetime.now(timezone.utc).isoformat(),
    )


def create_verified_sqlite_backup_bundle(
    repo_dir: str | Path,
    bundle_path: str | Path,
) -> SQLiteBackupBundleManifest:
    """Create one sequential local bundle from the explicit resilience scope.

    Only the fixed scope under ``repo_dir/data`` is read.  The caller chooses
    the writable destination; this helper never enables retention, encryption,
    replication, paper capital or live execution.
    """

    audit = audit_sqlite_backup_scope(repo_dir)
    if audit.missing_required:
        raise ResilienceError(
            "required SQLite backup sources are missing: " + ", ".join(audit.missing_required)
        )
    destination_path = Path(bundle_path).resolve()
    _validate_backup_bundle_id(destination_path.name)
    if destination_path.exists():
        raise ResilienceError("SQLite backup bundle destination already exists; refusing to overwrite it")
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    staging_path = Path(mkdtemp(prefix=".autobot-sqlite-backup-bundle-", dir=destination_path.parent))
    capture_started_at = datetime.now(timezone.utc).isoformat()
    try:
        bundle_entries: list[SQLiteBackupBundleEntry] = []
        for audit_entry in audit.entries:
            if audit_entry.status == "READY":
                staged_backup_path = staging_path / f"{audit_entry.identifier}.sqlite3"
                backup = create_verified_sqlite_backup(audit_entry.source_path, staged_backup_path)
                bundle_entries.append(
                    SQLiteBackupBundleEntry(
                        audit=audit_entry,
                        status="BACKED_UP",
                        backup=replace(backup, backup_path=str(destination_path / staged_backup_path.name)),
                    )
                )
            else:
                bundle_entries.append(
                    SQLiteBackupBundleEntry(
                        audit=audit_entry,
                        status="SKIPPED_OPTIONAL_MISSING",
                        backup=None,
                    )
                )
        manifest_path = destination_path / "manifest.json"
        manifest = SQLiteBackupBundleManifest(
            bundle_id=destination_path.name,
            bundle_path=str(destination_path),
            manifest_path=str(manifest_path),
            scope=audit,
            entries=tuple(bundle_entries),
            capture_started_at=capture_started_at,
            capture_finished_at=datetime.now(timezone.utc).isoformat(),
        )
        (staging_path / "manifest.json").write_text(
            json.dumps(asdict(manifest), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _sync_file_to_disk(staging_path / "manifest.json")
        _sync_directory_to_disk(staging_path)
        os.replace(staging_path, destination_path)
        _sync_directory_to_disk(destination_path.parent)
        _publish_sqlite_backup_bundle_durability_marker(destination_path)
        return manifest
    except Exception:
        if staging_path.exists():
            rmtree(staging_path)
        raise


def verify_sqlite_backup_bundle_restore_drill(
    bundle_path: str | Path,
) -> SQLiteBackupBundleRestoreDrillManifest:
    """Restore each present fixed-scope bundle member in disposable space.

    This verifies an already-created local bundle.  It never restores a
    snapshot into the AUTOBOT runtime location, creates a source database or
    interprets arbitrary paths embedded in the bundle manifest.
    """

    resolved_bundle_path = Path(bundle_path).resolve()
    _validate_backup_bundle_id(resolved_bundle_path.name)
    manifest_path = resolved_bundle_path / "manifest.json"
    if not resolved_bundle_path.is_dir() or not manifest_path.is_file():
        raise ResilienceError("SQLite backup bundle manifest does not exist")
    manifest_sha256_before = _sha256_file(manifest_path)
    _verify_sqlite_backup_bundle_durability_marker(resolved_bundle_path, manifest_sha256_before)
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResilienceError("SQLite backup bundle manifest is unreadable") from exc
    if not isinstance(payload, Mapping):
        raise ResilienceError("SQLite backup bundle manifest must be an object")
    if payload.get("bundle_id") != resolved_bundle_path.name:
        raise ResilienceError("SQLite backup bundle manifest identifier does not match its directory")
    scope_payload = payload.get("scope")
    entries_payload = payload.get("entries")
    if not isinstance(scope_payload, Mapping) or not isinstance(entries_payload, list):
        raise ResilienceError("SQLite backup bundle manifest has an invalid scope or entries payload")
    if scope_payload.get("scope_version") != SQLITE_BACKUP_SCOPE_VERSION:
        raise ResilienceError("SQLite backup bundle manifest has an unsupported scope version")
    expected_scope = canonical_sqlite_backup_scope()
    if scope_payload.get("scope_fingerprint") != _sqlite_backup_scope_fingerprint(expected_scope):
        raise ResilienceError("SQLite backup bundle manifest scope fingerprint mismatch")
    if (
        payload.get("research_only") is not True
        or payload.get("paper_capital_allowed") is not False
        or payload.get("live_allowed") is not False
    ):
        raise ResilienceError("SQLite backup bundle manifest must remain non-authorizing")
    if len(entries_payload) != len(expected_scope):
        raise ResilienceError("SQLite backup bundle manifest entry count does not match the canonical scope")

    drill_entries: list[SQLiteBackupBundleRestoreDrillEntry] = []
    for expected, entry_payload in zip(expected_scope, entries_payload, strict=True):
        if not isinstance(entry_payload, Mapping):
            raise ResilienceError("SQLite backup bundle manifest entry must be an object")
        audit_payload = entry_payload.get("audit")
        if not isinstance(audit_payload, Mapping):
            raise ResilienceError("SQLite backup bundle manifest entry lacks audit evidence")
        if (
            audit_payload.get("identifier") != expected.identifier
            or audit_payload.get("relative_source_path") != expected.relative_source_path
            or audit_payload.get("required") is not expected.required
        ):
            raise ResilienceError("SQLite backup bundle manifest does not match the canonical scope")
        status = entry_payload.get("status")
        backup_payload = entry_payload.get("backup")
        if status == "SKIPPED_OPTIONAL_MISSING":
            if expected.required or backup_payload is not None or audit_payload.get("status") != "MISSING_OPTIONAL":
                raise ResilienceError("required or backed-up SQLite bundle entry cannot be skipped")
            continue
        if (
            status != "BACKED_UP"
            or audit_payload.get("status") != "READY"
            or not isinstance(backup_payload, Mapping)
        ):
            raise ResilienceError("SQLite backup bundle entry is neither a valid backup nor an optional skip")
        snapshot_path = resolved_bundle_path / f"{expected.identifier}.sqlite3"
        if not snapshot_path.is_file():
            raise ResilienceError("SQLite backup bundle snapshot is missing")
        recorded_backup_name = str(backup_payload.get("backup_path") or "").replace("\\", "/").rsplit("/", 1)[-1]
        if recorded_backup_name != snapshot_path.name:
            raise ResilienceError("SQLite backup bundle manifest has an unexpected snapshot filename")
        expected_backup_sha256 = str(backup_payload.get("backup_sha256") or "")
        if not _is_sha256(expected_backup_sha256) or _sha256_file(snapshot_path) != expected_backup_sha256:
            raise ResilienceError("SQLite backup bundle snapshot fingerprint mismatch")
        restore = verify_sqlite_restore_drill(snapshot_path)
        drill_entries.append(
            SQLiteBackupBundleRestoreDrillEntry(
                identifier=expected.identifier,
                backup_path=str(snapshot_path),
                restore=restore,
            )
        )
    if not drill_entries:
        raise ResilienceError("SQLite backup bundle contains no snapshots to restore")
    manifest_sha256_after = _sha256_file(manifest_path)
    return SQLiteBackupBundleRestoreDrillManifest(
        bundle_path=str(resolved_bundle_path),
        bundle_manifest_sha256_before=manifest_sha256_before,
        bundle_manifest_sha256_after=manifest_sha256_after,
        entries=tuple(drill_entries),
        verified_at=datetime.now(timezone.utc).isoformat(),
    )


def create_verified_sqlite_backup(
    source: str | Path,
    destination: str | Path,
    *,
    encrypted: bool = False,
) -> SQLiteBackupManifest:
    """Create and integrity-check a SQLite backup; encryption is explicit, never implied."""

    source_path = Path(source).resolve()
    destination_path = Path(destination).resolve()
    if not source_path.exists():
        raise ResilienceError("SQLite backup source does not exist")
    if source_path == destination_path:
        raise ResilienceError("SQLite backup destination must differ from its source")
    if destination_path.exists():
        raise ResilienceError("SQLite backup destination already exists; refusing to overwrite it")
    if encrypted:
        raise ResilienceError("encryption must be provided by an approved external backup layer")
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_fd, temporary_name = mkstemp(
        prefix=f".{destination_path.name}.",
        suffix=".tmp",
        dir=destination_path.parent,
    )
    os.close(temporary_fd)
    temporary_path = Path(temporary_name)
    # Opening the source explicitly read-only makes this safe for a live
    # runtime SQLite database: SQLite's backup API can obtain a consistent
    # snapshot without giving this job write access to the source database.
    source_uri = f"{source_path.as_uri()}?mode=ro"
    try:
        with (
            closing(sqlite3.connect(source_uri, uri=True)) as source_connection,
            closing(sqlite3.connect(temporary_path)) as destination_connection,
        ):
            source_connection.backup(destination_connection)
            integrity, foreign_key_violation_count = _verify_sqlite_consistency(
                destination_connection,
                context="SQLite backup",
            )
        _sync_file_to_disk(temporary_path)
        try:
            os.link(temporary_path, destination_path)
        except FileExistsError as exc:
            raise ResilienceError("SQLite backup destination already exists; refusing to overwrite it") from exc
        _sync_directory_to_disk(destination_path.parent)
    finally:
        _remove_sqlite_artifacts(temporary_path)
    return SQLiteBackupManifest(
        source_path=str(source_path),
        backup_path=str(destination_path),
        source_sha256=_sha256_file(source_path),
        backup_sha256=_sha256_file(destination_path),
        integrity_check=integrity,
        foreign_key_violation_count=foreign_key_violation_count,
        encrypted=False,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def verify_sqlite_restore_drill(backup: str | Path) -> SQLiteRestoreDrillManifest:
    """Restore a backup into a disposable directory and verify it without runtime writes."""

    backup_path = Path(backup).resolve()
    if not backup_path.is_file():
        raise ResilienceError("SQLite restore drill backup does not exist")

    backup_sha256_before = _sha256_file(backup_path)
    try:
        with closing(sqlite3.connect(f"file:{backup_path}?mode=ro", uri=True)) as source_connection:
            source_integrity, source_foreign_key_violation_count = _verify_sqlite_consistency(
                source_connection,
                context="SQLite restore drill source",
            )
            source_schema_sha256 = _sqlite_schema_sha256(source_connection)
            source_table_row_counts = _sqlite_table_row_counts(source_connection)

            with TemporaryDirectory(prefix="autobot-sqlite-restore-drill-") as temporary_directory:
                restored_path = Path(temporary_directory) / "restored.sqlite3"
                with closing(sqlite3.connect(restored_path)) as restored_connection:
                    source_connection.backup(restored_connection)
                    restored_connection.commit()
                    restored_integrity, restored_foreign_key_violation_count = _verify_sqlite_consistency(
                        restored_connection,
                        context="SQLite restore drill",
                    )
                    restored_schema_sha256 = _sqlite_schema_sha256(restored_connection)
                    restored_table_row_counts = _sqlite_table_row_counts(restored_connection)
                restored_sha256 = _sha256_file(restored_path)
    except sqlite3.DatabaseError as exc:
        raise ResilienceError("SQLite restore drill could not read the backup safely") from exc

    backup_sha256_after = _sha256_file(backup_path)
    if backup_sha256_before != backup_sha256_after:
        raise ResilienceError("SQLite restore drill modified its backup input")
    if source_schema_sha256 != restored_schema_sha256 or source_table_row_counts != restored_table_row_counts:
        raise ResilienceError("SQLite restore drill schema or row-count mismatch")

    return SQLiteRestoreDrillManifest(
        backup_path=str(backup_path),
        backup_sha256_before=backup_sha256_before,
        backup_sha256_after=backup_sha256_after,
        restored_sha256=restored_sha256,
        source_schema_sha256=source_schema_sha256,
        restored_schema_sha256=restored_schema_sha256,
        source_table_row_counts=source_table_row_counts,
        restored_table_row_counts=restored_table_row_counts,
        integrity_check=restored_integrity,
        source_foreign_key_violation_count=source_foreign_key_violation_count,
        restored_foreign_key_violation_count=restored_foreign_key_violation_count,
        temporary_restore_cleaned=True,
        verified_at=datetime.now(timezone.utc).isoformat(),
    )


def run_ephemeral_sqlite_restore_drill(source: str | Path) -> EphemeralSQLiteRestoreDrillManifest:
    """Create, restore and remove a temporary SQLite backup without runtime writes."""

    source_path = Path(source).resolve()
    if not source_path.is_file():
        raise ResilienceError("SQLite ephemeral restore source does not exist")
    with TemporaryDirectory(prefix="autobot-sqlite-ephemeral-restore-") as temporary_directory:
        backup_path = Path(temporary_directory) / "backup.sqlite3"
        backup = create_verified_sqlite_backup(source_path, backup_path)
        restore = verify_sqlite_restore_drill(backup_path)
    return EphemeralSQLiteRestoreDrillManifest(
        source_path=str(source_path),
        backup=backup,
        restore=restore,
        temporary_backup_cleaned=not backup_path.exists(),
    )


_COVERAGE_STATUSES = frozenset({"COMPLETE", "PARTIAL", "MISSING", "UNSAFE", "VERIFIED"})
_VERIFIED_COVERAGE_PATH_FIELDS = ("code_paths", "test_paths", "runtime_evidence_paths")


def audit_layer_coverage(
    coverage_path: str | Path,
    *,
    repository_root: str | Path | None = None,
    expected_source_commit: str | None = None,
) -> LayerCoverageAudit:
    """Validate whether declared ``VERIFIED`` coverage has concrete evidence.

    The coverage matrix remains the human-maintained statement of programme
    maturity.  This audit does not upgrade any row.  It only prevents a row
    from being consumed as ``VERIFIED`` unless its structured evidence binds
    a source revision to local code, test and runtime-evidence artefacts.
    Relative paths are constrained to the repository root to prevent a review
    from silently reaching into credentials or arbitrary host files.
    """

    coverage = Path(coverage_path).resolve()
    if not coverage.is_file():
        raise ResilienceError("layer coverage path does not exist")
    root = _resolve_coverage_repository_root(coverage, repository_root)
    if coverage != root and root not in coverage.parents:
        raise ResilienceError("layer coverage path must remain inside the repository root")

    expected_commit = _normalize_optional_commit(expected_source_commit, "expected_source_commit")
    try:
        payload = json.loads(coverage.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ResilienceError("layer coverage payload must be valid JSON") from exc
    if not isinstance(payload, Mapping):
        raise ResilienceError("layer coverage payload must be an object")
    layers = payload.get("layers")
    if not isinstance(layers, list):
        raise ResilienceError("layer coverage payload must contain a layers list")

    raw_schema_version = payload.get("schema_version")
    if raw_schema_version is not None and (isinstance(raw_schema_version, bool) or not isinstance(raw_schema_version, int)):
        raise ResilienceError("layer coverage schema_version must be an integer when supplied")

    results: list[LayerVerificationResult] = []
    blockers: list[str] = []
    seen_ids: set[int] = set()
    for raw_layer in layers:
        if not isinstance(raw_layer, Mapping):
            raise ResilienceError("every layer coverage row must be an object")
        raw_id = raw_layer.get("id")
        if isinstance(raw_id, bool) or not isinstance(raw_id, int) or raw_id <= 0:
            raise ResilienceError("layer coverage row id must be a positive integer")
        if raw_id in seen_ids:
            raise ResilienceError(f"duplicate layer coverage id: {raw_id}")
        seen_ids.add(raw_id)
        status = str(raw_layer.get("status") or "").strip().upper()
        if status not in _COVERAGE_STATUSES:
            results.append(
                LayerVerificationResult(
                    layer_id=raw_id,
                    declared_status=status or "MISSING",
                    effective_status="UNSAFE",
                    blockers=("unsupported_status",),
                )
            )
            blockers.append(f"layer_{raw_id}_unsupported_status")
            continue
        if status != "VERIFIED":
            results.append(
                LayerVerificationResult(
                    layer_id=raw_id,
                    declared_status=status,
                    effective_status=status,
                    blockers=(),
                )
            )
            continue

        verification_blockers, source_commit = _verify_declared_layer_evidence(
            raw_layer.get("verification"),
            repository_root=root,
            expected_source_commit=expected_commit,
        )
        effective_status = "VERIFIED" if not verification_blockers else "PARTIAL"
        results.append(
            LayerVerificationResult(
                layer_id=raw_id,
                declared_status=status,
                effective_status=effective_status,
                blockers=verification_blockers,
                verification_source_commit=source_commit,
            )
        )
        blockers.extend(f"layer_{raw_id}_verification_{blocker}" for blocker in verification_blockers)

    return LayerCoverageAudit(
        coverage_path=str(coverage),
        repository_root=str(root),
        expected_source_commit=expected_commit,
        schema_version=raw_schema_version,
        results=tuple(results),
        blockers=tuple(sorted(set(blockers))),
    )


def write_layer_coverage_audit(audit: LayerCoverageAudit, destination: str | Path) -> Path:
    """Write a compact, non-authorizing audit report for human review."""

    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# AUTOBOT — Layer coverage evidence audit",
        "",
        "- This is a read-only governance audit; it cannot authorize paper, live or promotion.",
        f"- Coverage matrix: `{audit.coverage_path}`",
        f"- Repository root: `{audit.repository_root}`",
        f"- Expected source commit: `{audit.expected_source_commit or 'UNBOUND'}`",
        "",
        "## Results",
        "",
        "| Layer | Declared | Effective | Evidence blockers |",
        "| ---: | --- | --- | --- |",
    ]
    for result in audit.results:
        detail = ", ".join(result.blockers) if result.blockers else "none"
        lines.append(
            f"| {result.layer_id} | `{result.declared_status}` | `{result.effective_status}` | `{detail}` |"
        )
    lines.extend(["", "## Global blockers", ""])
    lines.extend(f"- `{blocker}`" for blocker in audit.blockers) if audit.blockers else lines.append("- None")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _resolve_coverage_repository_root(
    coverage: Path,
    repository_root: str | Path | None,
) -> Path:
    if repository_root is not None:
        root = Path(repository_root).resolve()
        if not root.is_dir():
            raise ResilienceError("layer coverage repository root does not exist")
        return root
    for candidate in (coverage.parent, *coverage.parents):
        if (
            (candidate / "AGENTS.md").is_file()
            or (candidate / "pyproject.toml").is_file()
            or (candidate / "src" / "autobot").is_dir()
        ):
            return candidate.resolve()
    return coverage.parent.resolve()


def _normalize_optional_commit(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if not _is_commit_identifier(normalized):
        raise ResilienceError(f"{field_name} must be a Git commit identifier")
    return normalized


def _verify_declared_layer_evidence(
    verification: Any,
    *,
    repository_root: Path,
    expected_source_commit: str | None,
) -> tuple[tuple[str, ...], str | None]:
    if not isinstance(verification, Mapping):
        return ("missing",), None

    blockers: list[str] = []
    source_commit: str | None = None
    raw_source_commit = verification.get("source_commit")
    if not isinstance(raw_source_commit, str) or not _is_commit_identifier(raw_source_commit.strip().lower()):
        blockers.append("source_commit_invalid")
    else:
        source_commit = raw_source_commit.strip().lower()
        if expected_source_commit is None:
            blockers.append("source_commit_unbound")
        elif source_commit != expected_source_commit:
            blockers.append("source_commit_mismatch")

    for field_name in _VERIFIED_COVERAGE_PATH_FIELDS:
        values = verification.get(field_name)
        if isinstance(values, (str, bytes)) or not isinstance(values, Sequence) or not values:
            blockers.append(f"{field_name}_missing")
            continue
        for raw_path in values:
            if not isinstance(raw_path, str) or not raw_path.strip():
                blockers.append(f"{field_name}_invalid")
                continue
            try:
                resolved = _resolve_coverage_evidence_path(repository_root, raw_path)
            except ResilienceError:
                blockers.append(f"{field_name}_outside_repository")
                continue
            if not resolved.is_file():
                blockers.append(f"{field_name}_not_found")

    return tuple(sorted(set(blockers))), source_commit


def _resolve_coverage_evidence_path(repository_root: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        raise ResilienceError("coverage evidence paths must be repository-relative")
    resolved = (repository_root / candidate).resolve()
    if resolved != repository_root and repository_root not in resolved.parents:
        raise ResilienceError("coverage evidence path escapes repository root")
    return resolved


def evaluate_human_paper_readiness(
    *,
    layer_statuses: Mapping[int, str],
    kill_switch_tested: bool,
    reconciliation_tested: bool,
    restore_tested: bool,
    deployment_evidence: RuntimeDeploymentEvidence | None = None,
    expected_source_commit: str | None = None,
    evaluated_at: datetime | None = None,
    max_deployment_evidence_age_seconds: int = 300,
    coverage_audit: LayerCoverageAudit | None = None,
    additional_blockers: Sequence[str] = (),
) -> PaperReadinessDossier:
    """Produce a non-authorizing dossier from explicit evidence only."""

    if max_deployment_evidence_age_seconds < 0:
        raise ResilienceError("max_deployment_evidence_age_seconds must be non-negative")
    expected_commit: str | None = None
    if expected_source_commit is not None:
        expected_commit = str(expected_source_commit).strip().lower()
        if not _is_commit_identifier(expected_commit):
            raise ResilienceError("expected_source_commit must be a Git commit identifier")
    required_layers = (3, 5, 10, 11, 12, 13, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24)
    normalized = {int(key): str(value).upper() for key, value in layer_statuses.items()}
    blockers = [f"layer_{layer}_{normalized.get(layer, 'MISSING').lower()}" for layer in required_layers if normalized.get(layer) != "VERIFIED"]
    blockers.extend(str(blocker) for blocker in additional_blockers if str(blocker).strip())
    if not kill_switch_tested:
        blockers.append("kill_switch_not_tested")
    if not reconciliation_tested:
        blockers.append("reconciliation_not_tested")
    if not restore_tested:
        blockers.append("restore_not_tested")
    if deployment_evidence is None:
        blockers.append("deployment_evidence_missing")
    else:
        blockers.extend(
            deployment_evidence.blockers(
                evaluated_at=evaluated_at or datetime.now(timezone.utc),
                max_age_seconds=max_deployment_evidence_age_seconds,
            )
        )
        if expected_commit is not None:
            if deployment_evidence.source_commit != expected_commit:
                blockers.append("deployment_evidence_source_commit_mismatch")
    return PaperReadinessDossier(
        status="READY_FOR_HUMAN_PAPER_REVIEW" if not blockers else "NOT_READY_FOR_HUMAN_PAPER_REVIEW",
        blockers=tuple(blockers),
        layer_statuses=normalized,
        kill_switch_tested=kill_switch_tested,
        reconciliation_tested=reconciliation_tested,
        restore_tested=restore_tested,
        deployment_evidence=deployment_evidence,
        coverage_audit=coverage_audit,
    )


def build_readiness_dossier_from_coverage(
    coverage_path: str | Path,
    *,
    repository_root: str | Path | None = None,
    kill_switch_tested: bool = False,
    reconciliation_tested: bool = False,
    restore_tested: bool = False,
    deployment_evidence: RuntimeDeploymentEvidence | None = None,
    expected_source_commit: str | None = None,
    evaluated_at: datetime | None = None,
    max_deployment_evidence_age_seconds: int = 300,
) -> PaperReadinessDossier:
    """Read the versioned coverage matrix without changing any runtime flag."""

    audit = audit_layer_coverage(
        coverage_path,
        repository_root=repository_root,
        expected_source_commit=expected_source_commit,
    )
    return evaluate_human_paper_readiness(
        layer_statuses=audit.effective_statuses,
        kill_switch_tested=kill_switch_tested,
        reconciliation_tested=reconciliation_tested,
        restore_tested=restore_tested,
        deployment_evidence=deployment_evidence,
        expected_source_commit=expected_source_commit,
        evaluated_at=evaluated_at,
        max_deployment_evidence_age_seconds=max_deployment_evidence_age_seconds,
        coverage_audit=audit,
        additional_blockers=audit.blockers,
    )


def write_readiness_dossier(dossier: PaperReadinessDossier, destination: str | Path) -> Path:
    """Write a compact, non-authorizing review artifact."""

    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# AUTOBOT — Paper readiness dossier",
        "",
        f"- Status: `{dossier.status}`",
        "- This document does not activate paper capital, live trading or promotion.",
        f"- Kill switch tested: `{dossier.kill_switch_tested}`",
        f"- Reconciliation tested: `{dossier.reconciliation_tested}`",
        f"- Restore tested: `{dossier.restore_tested}`",
        f"- Deployment evidence supplied: `{dossier.deployment_evidence is not None}`",
        "",
        "## Blockers",
        "",
    ]
    lines.extend(f"- `{blocker}`" for blocker in dossier.blockers) if dossier.blockers else lines.append("- None")
    if dossier.coverage_audit is not None:
        audit = dossier.coverage_audit
        lines.extend(
            [
                "",
                "## Coverage evidence audit",
                "",
                f"- Coverage matrix: `{audit.coverage_path}`",
                f"- Expected source commit: `{audit.expected_source_commit or 'UNBOUND'}`",
                f"- Audit blockers: `{len(audit.blockers)}`",
            ]
        )
    if dossier.deployment_evidence is not None:
        evidence = dossier.deployment_evidence
        lines.extend(
            [
                "",
                "## Deployment evidence",
                "",
                f"- Source commit: `{evidence.source_commit}`",
                f"- GitHub commit: `{evidence.github_commit}`",
                f"- VPS commit: `{evidence.vps_commit}`",
                f"- Container revision: `{evidence.container_revision}`",
                f"- Observed at: `{evidence.observed_at}`",
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _validate_action(action: str) -> str:
    normalized = str(action).upper()
    if normalized not in FAIL_CLOSED_ACTIONS:
        raise ResilienceError(f"unsupported fail-closed action: {action}")
    return normalized


def _normalize_incident_types(incident_types: Sequence[str]) -> tuple[str, ...]:
    if isinstance(incident_types, (str, bytes)):
        raise ResilienceError("incident_types must be a sequence, not a string")
    normalized = tuple(
        sorted({str(value).strip().upper() for value in incident_types if str(value).strip()})
    )
    unsupported = sorted(set(normalized) - INCIDENT_TYPES)
    if unsupported:
        raise ResilienceError(f"unsupported incident types: {', '.join(unsupported)}")
    return normalized


def _more_severe(first: str, second: str) -> str:
    return first if FAIL_CLOSED_ACTIONS.index(first) >= FAIL_CLOSED_ACTIONS.index(second) else second


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _parse_aware_utc(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ResilienceError(f"{field_name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ResilienceError(f"{field_name} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _is_commit_identifier(value: str) -> bool:
    return 7 <= len(value) <= 64 and all(character in "0123456789abcdef" for character in value)


def _is_sha256(value: str | None) -> bool:
    normalized = str(value or "").strip().lower()
    return len(normalized) == 64 and all(character in "0123456789abcdef" for character in normalized)


def _is_path_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _validate_backup_bundle_id(value: str) -> None:
    normalized = str(value).strip()
    if (
        not normalized
        or normalized in {".", ".."}
        or ".." in normalized
        or not all(character.isalnum() or character in "_.-" for character in normalized)
    ):
        raise ResilienceError("backup bundle identifier is unsafe")


def _sqlite_backup_scope_fingerprint(scope: Sequence[SQLiteBackupScopeEntry]) -> str:
    payload = [asdict(entry) for entry in scope]
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sync_file_to_disk(path: Path) -> None:
    """Synchronize a completed file before it is treated as backup evidence."""

    try:
        # On Windows, ``os.fsync`` rejects a read-only file descriptor. Every
        # target here is a private staged copy or a compact marker, so opening
        # it read/write is safe and keeps the same helper valid on Linux.
        with path.open("r+b") as handle:
            os.fsync(handle.fileno())
    except OSError as exc:
        raise ResilienceError(f"could not synchronize SQLite backup file: {path.name}") from exc


def _sync_directory_to_disk(directory: Path) -> bool:
    """Synchronize directory metadata when the host offers POSIX directory fsync.

    Windows does not expose a portable directory descriptor through ``os.open``.
    In that case every file and marker is still synchronized, but the marker
    records that directory-entry durability was not independently proven. The
    Linux VPS will take the stricter POSIX branch.
    """

    if os.name == "nt":
        return False
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(directory, flags)
    except OSError as exc:
        raise ResilienceError(f"could not open SQLite backup directory for synchronization: {directory.name}") from exc
    try:
        os.fsync(descriptor)
    except OSError as exc:
        raise ResilienceError(f"could not synchronize SQLite backup directory: {directory.name}") from exc
    finally:
        os.close(descriptor)
    return True


def _publish_sqlite_backup_bundle_durability_marker(bundle_path: Path) -> None:
    """Write the final fail-closed receipt for an atomically published bundle."""

    manifest_path = bundle_path / "manifest.json"
    marker_path = bundle_path / SQLITE_BACKUP_DURABILITY_MARKER_FILENAME
    manifest_sha256 = _sha256_file(manifest_path)
    base_payload = {
        "schema_version": SQLITE_BACKUP_DURABILITY_MARKER_SCHEMA_VERSION,
        "bundle_id": bundle_path.name,
        "manifest_filename": manifest_path.name,
        "manifest_sha256": manifest_sha256,
        "publication_complete": True,
    }
    _write_durable_json(
        marker_path,
        {
            **base_payload,
            "durability_status": "PENDING_FINAL_DIRECTORY_SYNC",
        },
    )
    directory_sync_supported = _sync_directory_to_disk(bundle_path)
    final_status = (
        "DURABLE_FILE_AND_DIRECTORY_SYNCED"
        if directory_sync_supported
        else "FILE_SYNCED_DIRECTORY_SYNC_UNAVAILABLE"
    )
    _write_durable_json(
        marker_path,
        {
            **base_payload,
            "durability_status": final_status,
        },
    )
    try:
        _sync_directory_to_disk(bundle_path)
    except Exception:
        # The earlier pending receipt was already directory-synchronized. Put
        # that conservative state back on disk before surfacing the failure so
        # a later restore drill cannot mistake an interrupted final fsync for
        # a completed publication.
        _write_durable_json(
            marker_path,
            {
                **base_payload,
                "durability_status": "PENDING_FINAL_DIRECTORY_SYNC",
            },
        )
        try:
            _sync_directory_to_disk(bundle_path)
        except Exception:
            # The pending marker is still safer than a success claim. Preserve
            # the original synchronization failure for the caller.
            pass
        raise


def _verify_sqlite_backup_bundle_durability_marker(bundle_path: Path, manifest_sha256: str) -> None:
    """Reject bundles whose atomic publication did not reach its final receipt."""

    marker_path = bundle_path / SQLITE_BACKUP_DURABILITY_MARKER_FILENAME
    if not marker_path.is_file():
        raise ResilienceError("SQLite backup bundle is not durably published")
    try:
        payload = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResilienceError("SQLite backup bundle durability marker is unreadable") from exc
    if not isinstance(payload, Mapping):
        raise ResilienceError("SQLite backup bundle durability marker must be an object")
    if payload.get("schema_version") != SQLITE_BACKUP_DURABILITY_MARKER_SCHEMA_VERSION:
        raise ResilienceError("SQLite backup bundle durability marker has an unsupported schema version")
    if payload.get("bundle_id") != bundle_path.name or payload.get("manifest_filename") != "manifest.json":
        raise ResilienceError("SQLite backup bundle durability marker does not match its bundle")
    if payload.get("publication_complete") is not True or payload.get("manifest_sha256") != manifest_sha256:
        raise ResilienceError("SQLite backup bundle durability marker does not match its manifest")
    if payload.get("durability_status") not in {
        "DURABLE_FILE_AND_DIRECTORY_SYNCED",
        "FILE_SYNCED_DIRECTORY_SYNC_UNAVAILABLE",
    }:
        raise ResilienceError("SQLite backup bundle is not durably published")


def _write_durable_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Write and synchronize a compact non-secret backup publication record."""

    try:
        with path.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise ResilienceError(f"could not synchronize SQLite backup publication record: {path.name}") from exc


def _remove_sqlite_artifacts(path: Path) -> None:
    """Remove only a private temporary SQLite artifact and possible sidecars."""

    for suffix in ("", "-journal", "-shm", "-wal"):
        Path(f"{path}{suffix}").unlink(missing_ok=True)


def _verify_sqlite_consistency(
    connection: sqlite3.Connection,
    *,
    context: str,
) -> tuple[str, int]:
    """Verify physical integrity and relational integrity of a SQLite snapshot."""

    integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
    if integrity.lower() != "ok":
        raise ResilienceError(f"{context} integrity check failed: {integrity}")
    foreign_key_violations = connection.execute("PRAGMA foreign_key_check").fetchall()
    if foreign_key_violations:
        raise ResilienceError(
            f"{context} foreign key check failed: {len(foreign_key_violations)} violation(s)"
        )
    return integrity, 0


def _sqlite_schema_sha256(connection: sqlite3.Connection) -> str:
    rows = connection.execute(
        "SELECT type, name, tbl_name, COALESCE(sql, '') FROM sqlite_master "
        "WHERE type IN ('index', 'table', 'trigger', 'view') ORDER BY type, name"
    ).fetchall()
    return sha256(json.dumps(rows, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


def _sqlite_table_row_counts(connection: sqlite3.Connection) -> dict[str, int]:
    table_names = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    counts: dict[str, int] = {}
    for (name,) in table_names:
        escaped_name = str(name).replace('"', '""')
        counts[str(name)] = int(connection.execute(f'SELECT COUNT(*) FROM "{escaped_name}"').fetchone()[0])
    return counts
