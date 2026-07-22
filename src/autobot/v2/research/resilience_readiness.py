"""Fail-closed resilience primitives and paper-readiness evaluation.

All operations in this module are local and hermetic.  They model how AUTOBOT
must react to uncertainty; they neither submit/cancel orders nor change runtime
flags.  A readiness result is documentation for human review, never a mandate.
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory, mkstemp
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


class ResilienceError(ValueError):
    """Raised when a resilience or readiness invariant is violated."""


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
        action = str(self.action).upper()
        if incident not in INCIDENT_TYPES or action not in FAIL_CLOSED_ACTIONS:
            raise ResilienceError("unsupported incident or fail-closed action")
        if self.risk_increase_allowed or self.paper_capital_allowed or self.live_allowed:
            raise ResilienceError("resilience decisions cannot increase risk or enable paper/live")
        object.__setattr__(self, "incident_type", incident)
        object.__setattr__(self, "action", action)


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
        if self.action not in FAIL_CLOSED_ACTIONS:
            raise ResilienceError("unsupported fail-closed action")
        if self.research_only is not True or self.paper_capital_allowed or self.live_allowed:
            raise ResilienceError("incident summaries cannot authorize paper or live")
        object.__setattr__(self, "incident_types", normalized)


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
        terminal = _validate_action(self.terminal_action)
        if terminal != normalized_steps[-1]:
            raise ResilienceError("recovery plan terminal action must match its final step")
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
class PaperReadinessDossier:
    status: str
    blockers: tuple[str, ...]
    layer_statuses: Mapping[int, str]
    kill_switch_tested: bool
    reconciliation_tested: bool
    restore_tested: bool
    paper_capital_allowed: bool = False
    live_allowed: bool = False
    automatic_promotion_allowed: bool = False

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
        try:
            os.link(temporary_path, destination_path)
        except FileExistsError as exc:
            raise ResilienceError("SQLite backup destination already exists; refusing to overwrite it") from exc
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


def evaluate_human_paper_readiness(
    *,
    layer_statuses: Mapping[int, str],
    kill_switch_tested: bool,
    reconciliation_tested: bool,
    restore_tested: bool,
) -> PaperReadinessDossier:
    """Produce a non-authorizing dossier from explicit evidence only."""

    required_layers = (3, 5, 10, 11, 12, 13, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24)
    normalized = {int(key): str(value).upper() for key, value in layer_statuses.items()}
    blockers = [f"layer_{layer}_{normalized.get(layer, 'MISSING').lower()}" for layer in required_layers if normalized.get(layer) != "VERIFIED"]
    if not kill_switch_tested:
        blockers.append("kill_switch_not_tested")
    if not reconciliation_tested:
        blockers.append("reconciliation_not_tested")
    if not restore_tested:
        blockers.append("restore_not_tested")
    return PaperReadinessDossier(
        status="READY_FOR_HUMAN_PAPER_REVIEW" if not blockers else "NOT_READY_FOR_HUMAN_PAPER_REVIEW",
        blockers=tuple(blockers),
        layer_statuses=normalized,
        kill_switch_tested=kill_switch_tested,
        reconciliation_tested=reconciliation_tested,
        restore_tested=restore_tested,
    )


def build_readiness_dossier_from_coverage(
    coverage_path: str | Path,
    *,
    kill_switch_tested: bool = False,
    reconciliation_tested: bool = False,
    restore_tested: bool = False,
) -> PaperReadinessDossier:
    """Read the versioned coverage matrix without changing any runtime flag."""

    path = Path(coverage_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    layers = payload.get("layers")
    if not isinstance(layers, list):
        raise ResilienceError("layer coverage payload must contain a layers list")
    statuses = {int(item["id"]): str(item["status"]) for item in layers if "id" in item and "status" in item}
    return evaluate_human_paper_readiness(
        layer_statuses=statuses,
        kill_switch_tested=kill_switch_tested,
        reconciliation_tested=reconciliation_tested,
        restore_tested=restore_tested,
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
        "",
        "## Blockers",
        "",
    ]
    lines.extend(f"- `{blocker}`" for blocker in dossier.blockers) if dossier.blockers else lines.append("- None")
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


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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
