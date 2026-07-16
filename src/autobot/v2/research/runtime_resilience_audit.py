"""Read-only runtime resilience evidence for AUTOBOT research/shadow safety.

The audit intentionally has no runtime, router, paper or exchange imports. It
observes the SQLite state database and filesystem only, then returns canonical
fail-closed incidents for the independent risk boundary to consume later.
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import shutil
import sqlite3
from typing import Literal

from autobot.v2.research.resilience_readiness import (
    FailClosedIncidentSummary,
    summarize_fail_closed_incidents,
)


WebSocketStatus = Literal["connected", "disconnected", "unknown"]
DEFAULT_MAX_DATA_AGE_SECONDS = 300
DEFAULT_MIN_FREE_DISK_BYTES = 2 * 1024 * 1024 * 1024


class RuntimeResilienceAuditError(ValueError):
    """Raised when a caller supplies an invalid read-only audit configuration."""


@dataclass(frozen=True)
class RuntimeResilienceAudit:
    status: str
    state_db_path: str
    database_exists: bool
    sqlite_integrity_check: str | None
    latest_market_observed_at: str | None
    market_data_age_seconds: float | None
    max_data_age_seconds: int
    free_disk_bytes: int | None
    min_free_disk_bytes: int
    websocket_status: WebSocketStatus
    incident_types: tuple[str, ...]
    fail_closed: FailClosedIncidentSummary
    reasons: tuple[str, ...]
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False
    order_submission_attempted: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def audit_runtime_resilience(
    state_db: str | Path,
    *,
    max_data_age_seconds: int = DEFAULT_MAX_DATA_AGE_SECONDS,
    min_free_disk_bytes: int = DEFAULT_MIN_FREE_DISK_BYTES,
    websocket_status: WebSocketStatus = "unknown",
    evaluated_at: datetime | None = None,
) -> RuntimeResilienceAudit:
    """Observe runtime readiness without creating or changing any database."""

    if max_data_age_seconds < 0:
        raise RuntimeResilienceAuditError("max_data_age_seconds must be non-negative")
    if min_free_disk_bytes < 0:
        raise RuntimeResilienceAuditError("min_free_disk_bytes must be non-negative")
    if websocket_status not in {"connected", "disconnected", "unknown"}:
        raise RuntimeResilienceAuditError("websocket_status must be connected, disconnected or unknown")

    path = Path(state_db).resolve()
    now = _as_utc(evaluated_at or datetime.now(timezone.utc))
    incidents: list[str] = []
    reasons: list[str] = []
    integrity: str | None = None
    latest_observed_at: str | None = None
    data_age_seconds: float | None = None
    free_disk_bytes: int | None = None

    try:
        free_disk_bytes = int(shutil.disk_usage(path.parent).free)
        if free_disk_bytes < min_free_disk_bytes:
            incidents.append("DISK_FULL")
            reasons.append("free_disk_below_minimum")
    except OSError as exc:
        incidents.append("DISK_FULL")
        reasons.append(f"disk_usage_error:{type(exc).__name__}")

    if not path.is_file():
        incidents.append("SQLITE_CORRUPT")
        reasons.append("state_db_missing")
    else:
        try:
            with closing(sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)) as connection:
                connection.execute("PRAGMA query_only = ON")
                integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
                if integrity.lower() != "ok":
                    incidents.append("SQLITE_CORRUPT")
                    reasons.append(f"sqlite_integrity:{integrity}")
                latest_observed_at = _latest_market_observed_at(connection)
        except sqlite3.OperationalError as exc:
            _record_sqlite_operational_failure(incidents, reasons, exc)
        except sqlite3.DatabaseError as exc:
            incidents.append("SQLITE_CORRUPT")
            reasons.append(f"sqlite_read_error:{type(exc).__name__}")

    if latest_observed_at is None:
        incidents.append("DATA_STALE")
        reasons.append("market_price_samples_missing")
    else:
        observed = _parse_utc(latest_observed_at)
        if observed is None:
            incidents.append("DATA_STALE")
            reasons.append("latest_market_timestamp_invalid")
        else:
            data_age_seconds = max(0.0, (now - observed).total_seconds())
            if observed > now:
                incidents.append("DATA_STALE")
                reasons.append("latest_market_timestamp_in_future")
            elif data_age_seconds > max_data_age_seconds:
                incidents.append("DATA_STALE")
                reasons.append("market_data_stale")

    if websocket_status == "disconnected":
        incidents.append("WEBSOCKET_DISCONNECTED")
        reasons.append("websocket_reported_disconnected")
    elif websocket_status == "unknown":
        reasons.append("websocket_not_observed")

    summary = summarize_fail_closed_incidents(tuple(incidents))
    if summary.incident_types:
        status = "INCIDENTS_DETECTED"
    elif websocket_status == "unknown":
        status = "PARTIAL_OBSERVABILITY"
    else:
        status = "RESILIENCE_HEALTHY"
    return RuntimeResilienceAudit(
        status=status,
        state_db_path=str(path),
        database_exists=path.is_file(),
        sqlite_integrity_check=integrity,
        latest_market_observed_at=latest_observed_at,
        market_data_age_seconds=data_age_seconds,
        max_data_age_seconds=max_data_age_seconds,
        free_disk_bytes=free_disk_bytes,
        min_free_disk_bytes=min_free_disk_bytes,
        websocket_status=websocket_status,
        incident_types=summary.incident_types,
        fail_closed=summary,
        reasons=tuple(reasons),
    )


def _latest_market_observed_at(connection: sqlite3.Connection) -> str | None:
    table = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'market_price_samples'"
    ).fetchone()
    if not table:
        return None
    row = connection.execute(
        "SELECT observed_at FROM market_price_samples ORDER BY observed_at DESC, id DESC LIMIT 1"
    ).fetchone()
    return str(row[0]) if row and row[0] else None


def _record_sqlite_operational_failure(
    incidents: list[str],
    reasons: list[str],
    error: sqlite3.OperationalError,
) -> None:
    """Treat only busy/locked evidence as a temporary SQLite lock.

    A read-only schema error means the persistence contract is no longer
    trustworthy. It is therefore stricter than a transient lock and must halt
    the future risk envelope rather than merely block new orders.
    """

    message = str(error).lower()
    if "locked" in message or "busy" in message:
        incidents.append("SQLITE_LOCKED")
        reasons.append(f"sqlite_locked:{type(error).__name__}")
        return
    incidents.append("SQLITE_CORRUPT")
    reasons.append(f"sqlite_operational_error:{type(error).__name__}")


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _parse_utc(value: str) -> datetime | None:
    try:
        return _as_utc(datetime.fromisoformat(str(value).replace("Z", "+00:00")))
    except ValueError:
        return None
