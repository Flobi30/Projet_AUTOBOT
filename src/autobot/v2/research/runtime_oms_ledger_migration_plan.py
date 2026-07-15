"""Build a read-only canonical migration plan for legacy runtime OMS evidence.

This is deliberately a planner, not a migration.  It opens the runtime state
database through SQLite ``mode=ro``, never creates a table or output database,
and never imports an execution, paper or reconciliation component.  Legacy
facts that cannot satisfy the versioned contracts are counted as quarantined;
the planner never invents a strategy, market identity, decision or lifecycle
state to make a row look migratable.
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from autobot.v2.contracts import FillEvent, OrderEvent, contract_fingerprint, contract_to_dict


MIGRATION_PLAN_VERSION = 1
_RESEARCH_EXECUTION_MODES = frozenset({"shadow", "shadow_paper"})
_ORDER_EVENT_TYPES = {
    "NEW": "CREATED",
    "CREATED": "CREATED",
    "SENT": "SUBMITTED",
    "SUBMITTED": "SUBMITTED",
    "ACK": "ACKNOWLEDGED",
    "ACKNOWLEDGED": "ACKNOWLEDGED",
    "PARTIAL": "PARTIALLY_FILLED",
    "PARTIALLY_FILLED": "PARTIALLY_FILLED",
    "FILLED": "FILLED",
    "CANCELED": "CANCELLED",
    "CANCELLED": "CANCELLED",
    "REJECTED": "REJECTED",
    "UNKNOWN": "UNKNOWN",
}
_REQUIRED_COLUMNS = {
    "orders": frozenset({"client_order_id", "exchange_order_id"}),
    "order_state_transitions": frozenset({"id", "client_order_id", "to_status", "occurred_at"}),
    "trade_ledger": frozenset(
        {
            "id",
            "trade_id",
            "exchange_order_id",
            "decision_id",
            "signal_id",
            "strategy_id",
            "execution_mode",
            "volume",
            "executed_price",
            "fees",
            "created_at",
        }
    ),
}


@dataclass(frozen=True)
class RuntimeOMSLedgerMigrationPlan:
    """A compact, non-executable review artifact for one legacy state DB."""

    plan_version: int
    status: str
    state_db_path: str
    database_exists: bool
    database_sha256_before: str | None
    database_sha256_after: str | None
    source_table_row_counts: Mapping[str, int]
    missing_columns: Mapping[str, tuple[str, ...]]
    canonical_intent_candidate_count: int
    unmigratable_order_intent_count: int
    reconstructable_order_event_count: int
    order_event_reconciliation_required_count: int
    reconstructable_fill_event_count: int
    quarantine_reason_counts: Mapping[str, int]
    candidate_fingerprint: str | None
    quarantine_fingerprint: str | None
    reasons: tuple[str, ...]
    research_only: bool = True
    migration_allowed: bool = False
    paper_capital_allowed: bool = False
    live_allowed: bool = False
    order_submission_attempted: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def plan_runtime_oms_ledger_migration(state_db: str | Path) -> RuntimeOMSLedgerMigrationPlan:
    """Inspect legacy runtime evidence and describe only defensible mappings.

    Canonical ``OrderIntent`` records are intentionally never reconstructed:
    the legacy ``orders`` table has no verified strategy version or canonical
    market identity.  Events and fills may be mechanically representable, but
    they remain review-only until canonical intents and provenance exist.
    """

    path = Path(state_db).resolve()
    if not path.is_file():
        return _empty_plan(path, "NO_RUNTIME_ORDER_EVIDENCE", ("state_db_missing",))

    before = _sha256_file(path)
    try:
        with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as connection:
            connection.row_factory = sqlite3.Row
            columns = _table_columns(connection)
            missing = {
                table: tuple(sorted(required - columns.get(table, frozenset())))
                for table, required in _REQUIRED_COLUMNS.items()
                if required - columns.get(table, frozenset())
            }
            counts = {table: _row_count(connection, table) for table in _REQUIRED_COLUMNS if table in columns}
            if not counts or not any(counts.values()):
                status, reasons = "NO_RUNTIME_ORDER_EVIDENCE", ("no_runtime_order_or_trade_rows",)
                candidates: list[dict[str, Any]] = []
                quarantined: list[dict[str, str]] = []
                event_review_count = 0
                intent_count = 0
            elif missing:
                status = "INCOMPLETE_RUNTIME_LEDGER"
                reasons = tuple(f"missing_columns:{table}" for table in sorted(missing))
                candidates = []
                quarantined = []
                event_review_count = 0
                intent_count = 0
            else:
                candidates, quarantined, event_review_count = _build_candidates(connection)
                intent_count = counts.get("orders", 0)
                status = "MIGRATION_REVIEW_REQUIRED"
                reasons = (
                    "automatic_migration_forbidden",
                    "legacy_orders_lack_verified_strategy_version_and_canonical_market_identity",
                    "reconstructable_events_require_canonical_intent_and_human_reconciliation",
                )
    except sqlite3.DatabaseError as exc:
        return RuntimeOMSLedgerMigrationPlan(
            plan_version=MIGRATION_PLAN_VERSION,
            status="INCOMPLETE_RUNTIME_LEDGER",
            state_db_path=str(path),
            database_exists=True,
            database_sha256_before=before,
            database_sha256_after=_sha256_file(path),
            source_table_row_counts={},
            missing_columns={},
            canonical_intent_candidate_count=0,
            unmigratable_order_intent_count=0,
            reconstructable_order_event_count=0,
            order_event_reconciliation_required_count=0,
            reconstructable_fill_event_count=0,
            quarantine_reason_counts={},
            candidate_fingerprint=None,
            quarantine_fingerprint=None,
            reasons=(f"sqlite_read_error:{type(exc).__name__}",),
        )

    after = _sha256_file(path)
    if before != after:
        status = "RECONCILIATION_REQUIRED"
        reasons = tuple(reasons) + ("database_changed_during_read_only_planning",)

    order_events = [candidate for candidate in candidates if candidate["contract_type"] == "OrderEvent"]
    fills = [candidate for candidate in candidates if candidate["contract_type"] == "FillEvent"]
    return RuntimeOMSLedgerMigrationPlan(
        plan_version=MIGRATION_PLAN_VERSION,
        status=status,
        state_db_path=str(path),
        database_exists=True,
        database_sha256_before=before,
        database_sha256_after=after,
        source_table_row_counts=counts,
        missing_columns=missing,
        canonical_intent_candidate_count=0,
        unmigratable_order_intent_count=intent_count,
        reconstructable_order_event_count=len(order_events),
        order_event_reconciliation_required_count=event_review_count,
        reconstructable_fill_event_count=len(fills),
        quarantine_reason_counts=_reason_counts(quarantined),
        candidate_fingerprint=_fingerprint(candidates),
        quarantine_fingerprint=_fingerprint(quarantined),
        reasons=tuple(reasons),
    )


def _empty_plan(path: Path, status: str, reasons: tuple[str, ...]) -> RuntimeOMSLedgerMigrationPlan:
    return RuntimeOMSLedgerMigrationPlan(
        plan_version=MIGRATION_PLAN_VERSION,
        status=status,
        state_db_path=str(path),
        database_exists=False,
        database_sha256_before=None,
        database_sha256_after=None,
        source_table_row_counts={},
        missing_columns={},
        canonical_intent_candidate_count=0,
        unmigratable_order_intent_count=0,
        reconstructable_order_event_count=0,
        order_event_reconciliation_required_count=0,
        reconstructable_fill_event_count=0,
        quarantine_reason_counts={},
        candidate_fingerprint=None,
        quarantine_fingerprint=None,
        reasons=reasons,
    )


def _build_candidates(connection: sqlite3.Connection) -> tuple[list[dict[str, Any]], list[dict[str, str]], int]:
    candidates: list[dict[str, Any]] = []
    quarantined: list[dict[str, str]] = []
    orders_by_exchange, known_client_order_ids = _orders_by_exchange_id(connection)
    events, event_quarantine, event_review_count = _order_event_candidates(connection, known_client_order_ids)
    fills, fill_quarantine = _fill_event_candidates(connection, orders_by_exchange)
    candidates.extend(events)
    candidates.extend(fills)
    quarantined.extend(event_quarantine)
    quarantined.extend(fill_quarantine)
    return candidates, quarantined, event_review_count


def _orders_by_exchange_id(connection: sqlite3.Connection) -> tuple[dict[str, tuple[str, ...]], frozenset[str]]:
    mapping: dict[str, list[str]] = {}
    client_order_ids: set[str] = set()
    for row in connection.execute("SELECT client_order_id, exchange_order_id FROM orders"):
        exchange_order_id = _text(row["exchange_order_id"])
        client_order_id = _text(row["client_order_id"])
        if client_order_id:
            client_order_ids.add(client_order_id)
        if exchange_order_id and client_order_id:
            mapping.setdefault(exchange_order_id, []).append(client_order_id)
    return {key: tuple(sorted(set(value))) for key, value in mapping.items()}, frozenset(client_order_ids)


def _order_event_candidates(
    connection: sqlite3.Connection, known_client_order_ids: frozenset[str]
) -> tuple[list[dict[str, Any]], list[dict[str, str]], int]:
    candidates: list[dict[str, Any]] = []
    quarantined: list[dict[str, str]] = []
    reconciliation_required = 0
    query = "SELECT id, client_order_id, from_status, to_status, reason, occurred_at FROM order_state_transitions ORDER BY id"
    for row in connection.execute(query):
        source_id = str(row["id"])
        client_order_id = _text(row["client_order_id"])
        event_type = _ORDER_EVENT_TYPES.get(_text(row["to_status"]).upper())
        occurred_at = _parse_utc(row["occurred_at"])
        if not client_order_id:
            quarantined.append(_quarantine("order_state_transitions", source_id, "missing_client_order_id"))
            continue
        if client_order_id not in known_client_order_ids:
            quarantined.append(_quarantine("order_state_transitions", source_id, "unresolved_legacy_order"))
            continue
        if event_type is None:
            quarantined.append(_quarantine("order_state_transitions", source_id, "unsupported_legacy_order_status"))
            continue
        if occurred_at is None:
            quarantined.append(_quarantine("order_state_transitions", source_id, "invalid_or_naive_occurred_at"))
            continue
        warnings: list[str] = []
        if not _text(row["from_status"]):
            warnings.append("missing_from_status")
        if warnings:
            reconciliation_required += 1
        event = OrderEvent(
            client_order_id=client_order_id,
            event_type=event_type,
            occurred_at=occurred_at,
            reason=_text(row["reason"]) or "legacy_runtime_transition",
        )
        candidates.append(
            _candidate(
                source_table="order_state_transitions",
                source_row_id=source_id,
                contract_type="OrderEvent",
                contract=event,
                warnings=warnings,
            )
        )
    return candidates, quarantined, reconciliation_required


def _fill_event_candidates(
    connection: sqlite3.Connection, orders_by_exchange: Mapping[str, tuple[str, ...]]
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    candidates: list[dict[str, Any]] = []
    quarantined: list[dict[str, str]] = []
    query = """
        SELECT id, trade_id, exchange_order_id, decision_id, signal_id, strategy_id,
               execution_mode, volume, executed_price, fees, created_at
        FROM trade_ledger
        ORDER BY id
    """
    for row in connection.execute(query):
        source_id = str(row["id"])
        missing_provenance = [
            field_name
            for field_name in ("decision_id", "signal_id", "strategy_id", "execution_mode")
            if not _text(row[field_name])
        ]
        if missing_provenance:
            quarantined.append(_quarantine("trade_ledger", source_id, f"missing_{missing_provenance[0]}"))
            continue
        execution_mode = _text(row["execution_mode"]).lower()
        if execution_mode not in _RESEARCH_EXECUTION_MODES:
            quarantined.append(_quarantine("trade_ledger", source_id, "unsupported_execution_mode"))
            continue
        trade_id = _text(row["trade_id"])
        if not trade_id:
            quarantined.append(_quarantine("trade_ledger", source_id, "missing_trade_id"))
            continue
        exchange_order_id = _text(row["exchange_order_id"])
        matched_order_ids = orders_by_exchange.get(exchange_order_id, ())
        if len(matched_order_ids) != 1:
            reason = "unresolved_client_order_id" if not matched_order_ids else "ambiguous_client_order_id"
            quarantined.append(_quarantine("trade_ledger", source_id, reason))
            continue
        occurred_at = _parse_utc(row["created_at"])
        if occurred_at is None:
            quarantined.append(_quarantine("trade_ledger", source_id, "invalid_or_naive_occurred_at"))
            continue
        try:
            fill = FillEvent(
                client_order_id=matched_order_ids[0],
                fill_id=trade_id,
                occurred_at=occurred_at,
                quantity=float(row["volume"]),
                average_price=float(row["executed_price"]),
                fees=float(row["fees"] or 0.0),
            )
        except (TypeError, ValueError):
            quarantined.append(_quarantine("trade_ledger", source_id, "invalid_fill_values"))
            continue
        candidates.append(
            _candidate(
                source_table="trade_ledger",
                source_row_id=source_id,
                contract_type="FillEvent",
                contract=fill,
                warnings=(),
            )
        )
    return candidates, quarantined


def _candidate(
    *,
    source_table: str,
    source_row_id: str,
    contract_type: str,
    contract: OrderEvent | FillEvent,
    warnings: list[str] | tuple[str, ...],
) -> dict[str, Any]:
    return {
        "source_table": source_table,
        "source_row_id": source_row_id,
        "contract_type": contract_type,
        "contract": contract_to_dict(contract),
        "contract_fingerprint": contract_fingerprint(contract),
        "warnings": tuple(sorted(warnings)),
    }


def _quarantine(source_table: str, source_row_id: str, reason: str) -> dict[str, str]:
    return {"source_table": source_table, "source_row_id": source_row_id, "reason": reason}


def _table_columns(connection: sqlite3.Connection) -> dict[str, frozenset[str]]:
    tables = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    columns: dict[str, frozenset[str]] = {}
    for row in tables:
        table = str(row[0])
        escaped = table.replace('"', '""')
        columns[table] = frozenset(str(column[1]) for column in connection.execute(f'PRAGMA table_info("{escaped}")'))
    return columns


def _row_count(connection: sqlite3.Connection, table: str) -> int:
    escaped = table.replace('"', '""')
    return int(connection.execute(f'SELECT COUNT(*) FROM "{escaped}"').fetchone()[0])


def _parse_utc(value: object) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _reason_counts(rows: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        reason = row["reason"]
        counts[reason] = counts.get(reason, 0) + 1
    return dict(sorted(counts.items()))


def _fingerprint(rows: list[dict[str, Any]]) -> str | None:
    if not rows:
        return None
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
