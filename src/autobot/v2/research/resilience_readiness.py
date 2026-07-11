"""Fail-closed resilience primitives and paper-readiness evaluation.

All operations in this module are local and hermetic.  They model how AUTOBOT
must react to uncertainty; they neither submit/cancel orders nor change runtime
flags.  A readiness result is documentation for human review, never a mandate.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
import sqlite3
from time import sleep
from typing import Any, Callable, Mapping, Sequence, TypeVar


INCIDENT_TYPES = frozenset(
    {
        "WEBSOCKET_DISCONNECTED",
        "API_UNAVAILABLE",
        "DATA_STALE",
        "SQLITE_LOCKED",
        "DISK_FULL",
        "CONTAINER_RESTARTED",
        "ORDER_UNKNOWN",
        "RECONCILIATION_REQUIRED",
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
    encrypted: bool
    created_at: str
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False


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
        "DISK_FULL": ("HALT", "persistence_cannot_be_trusted"),
        "CONTAINER_RESTARTED": ("BLOCK_NEW_ORDERS", "state_reconciliation_required_after_restart"),
        "ORDER_UNKNOWN": ("HALT", "order_state_unknown"),
        "RECONCILIATION_REQUIRED": ("HALT", "position_or_order_divergence"),
    }
    calculated, reason = mapping[incident]
    action = _more_severe(_validate_action(previous_action), calculated)
    return IncidentDecision(incident, action, reason)


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

    source_path = Path(source)
    destination_path = Path(destination)
    if not source_path.exists():
        raise ResilienceError("SQLite backup source does not exist")
    if encrypted:
        raise ResilienceError("encryption must be provided by an approved external backup layer")
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source_path) as source_connection, sqlite3.connect(destination_path) as destination_connection:
        source_connection.backup(destination_connection)
        integrity = str(destination_connection.execute("PRAGMA integrity_check").fetchone()[0])
    if integrity.lower() != "ok":
        raise ResilienceError(f"SQLite backup integrity check failed: {integrity}")
    return SQLiteBackupManifest(
        source_path=str(source_path),
        backup_path=str(destination_path),
        source_sha256=_sha256_file(source_path),
        backup_sha256=_sha256_file(destination_path),
        integrity_check=integrity,
        encrypted=False,
        created_at=datetime.now(timezone.utc).isoformat(),
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


def _more_severe(first: str, second: str) -> str:
    return first if FAIL_CLOSED_ACTIONS.index(first) >= FAIL_CLOSED_ACTIONS.index(second) else second


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
