"""Read-only evidence audit for the legacy runtime OMS and ledger.

This module never initializes SQLite, imports an execution component, or
reconciles against an exchange. It only reports whether existing runtime rows
contain enough local evidence for a future migration to the canonical contracts.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import sqlite3
from typing import Mapping


@dataclass(frozen=True)
class ContractCutoverEvidence:
    """Traceability evidence limited to rows at or after one UTC cutover.

    The legacy runtime database is intentionally never rewritten.  This view
    makes it possible to prove that newer records satisfy the canonical
    provenance boundary without treating historical rows as trustworthy.
    """

    cutover_at: str | None
    status: str
    table_row_counts: Mapping[str, int]
    orders_missing_provenance_count: int
    transitions_missing_from_status_count: int
    untraceable_trade_count: int
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class RuntimeOMSLedgerAudit:
    status: str
    state_db_path: str
    database_exists: bool
    database_sha256_before: str | None
    database_sha256_after: str | None
    table_row_counts: Mapping[str, int]
    missing_columns: Mapping[str, tuple[str, ...]]
    non_terminal_order_count: int
    orders_missing_provenance_count: int
    transitions_missing_from_status_count: int
    untraceable_trade_count: int
    cutover_evidence: ContractCutoverEvidence
    reasons: tuple[str, ...]
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False
    order_submission_attempted: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


_REQUIRED_COLUMNS = {
    "orders": frozenset({"client_order_id", "decision_id", "signal_id", "strategy_id", "status", "created_at"}),
    "order_state_transitions": frozenset({"client_order_id", "from_status", "to_status", "occurred_at"}),
    "trade_ledger": frozenset({"trade_id", "decision_id", "signal_id", "strategy_id", "execution_mode", "created_at"}),
}
_TERMINAL_STATUSES = ("FILLED", "CANCELED", "CANCELLED", "REJECTED", "EXPIRED")


def audit_runtime_oms_ledger(
    state_db: str | Path,
    *,
    cutover_at: str | datetime | None = None,
) -> RuntimeOMSLedgerAudit:
    """Inspect a SQLite state DB through ``mode=ro`` with no side effects."""

    path = Path(state_db).resolve()
    cutover = _parse_cutover_at(cutover_at)
    if not path.is_file():
        return RuntimeOMSLedgerAudit(
            status="NO_RUNTIME_ORDER_EVIDENCE",
            state_db_path=str(path),
            database_exists=False,
            database_sha256_before=None,
            database_sha256_after=None,
            table_row_counts={},
            missing_columns={},
            non_terminal_order_count=0,
            orders_missing_provenance_count=0,
            transitions_missing_from_status_count=0,
            untraceable_trade_count=0,
            cutover_evidence=_unavailable_cutover_evidence(cutover, "state_db_missing"),
            reasons=("state_db_missing",),
        )

    before = _sha256_file(path)
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
            tables = _table_columns(connection)
            missing = {
                table: tuple(sorted(required - tables.get(table, frozenset())))
                for table, required in _REQUIRED_COLUMNS.items()
                if required - tables.get(table, frozenset())
            }
            counts = {table: _row_count(connection, table) for table in _REQUIRED_COLUMNS if table in tables}
            if not counts or not any(counts.values()):
                status, reasons = "NO_RUNTIME_ORDER_EVIDENCE", ("no_runtime_order_or_trade_rows",)
                non_terminal = missing_provenance = missing_from = untraceable = 0
            elif missing:
                status, reasons = "INCOMPLETE_RUNTIME_LEDGER", tuple(f"missing_columns:{table}" for table in sorted(missing))
                non_terminal = missing_provenance = missing_from = untraceable = 0
            else:
                non_terminal = _count_non_terminal_orders(connection)
                missing_provenance = _count_orders_missing_provenance(connection)
                missing_from = _count_transitions_missing_from_status(connection)
                untraceable = _count_untraceable_trades(connection)
                reasons_list = []
                if non_terminal:
                    reasons_list.append("non_terminal_orders_present")
                if missing_provenance:
                    reasons_list.append("orders_missing_decision_or_signal")
                if missing_from:
                    reasons_list.append("transitions_missing_from_status")
                if untraceable:
                    reasons_list.append("trades_missing_traceability")
                status = "RECONCILIATION_REQUIRED" if reasons_list else "INCOMPLETE_RUNTIME_LEDGER"
                reasons = tuple(reasons_list or ("runtime_ledger_not_bound_to_canonical_contracts",))
            cutover_evidence = _build_cutover_evidence(connection, cutover, missing)
    except sqlite3.DatabaseError as exc:
        return RuntimeOMSLedgerAudit(
            status="INCOMPLETE_RUNTIME_LEDGER", state_db_path=str(path), database_exists=True,
            database_sha256_before=before, database_sha256_after=_sha256_file(path), table_row_counts={},
            missing_columns={}, non_terminal_order_count=0, orders_missing_provenance_count=0,
            transitions_missing_from_status_count=0, untraceable_trade_count=0,
            cutover_evidence=_unavailable_cutover_evidence(cutover, f"sqlite_read_error:{type(exc).__name__}"),
            reasons=(f"sqlite_read_error:{type(exc).__name__}",),
        )

    after = _sha256_file(path)
    if before != after:
        status, reasons = "RECONCILIATION_REQUIRED", tuple(reasons) + ("database_changed_during_read_only_audit",)
    return RuntimeOMSLedgerAudit(
        status=status, state_db_path=str(path), database_exists=True,
        database_sha256_before=before, database_sha256_after=after, table_row_counts=counts,
        missing_columns=missing, non_terminal_order_count=non_terminal,
        orders_missing_provenance_count=missing_provenance,
        transitions_missing_from_status_count=missing_from, untraceable_trade_count=untraceable,
        cutover_evidence=cutover_evidence,
        reasons=reasons,
    )


def _table_columns(connection: sqlite3.Connection) -> dict[str, frozenset[str]]:
    tables = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {str(name): frozenset(str(row[1]) for row in connection.execute(f'PRAGMA table_info("{str(name).replace(chr(34), chr(34) * 2)}")')) for (name,) in tables}


def _row_count(connection: sqlite3.Connection, table: str) -> int:
    return int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])


def _count_non_terminal_orders(connection: sqlite3.Connection) -> int:
    placeholders = ",".join("?" for _ in _TERMINAL_STATUSES)
    return int(connection.execute(f"SELECT COUNT(*) FROM orders WHERE UPPER(status) NOT IN ({placeholders})", _TERMINAL_STATUSES).fetchone()[0])


def _count_orders_missing_provenance(connection: sqlite3.Connection) -> int:
    return int(
        connection.execute(
            "SELECT COUNT(*) FROM orders "
            "WHERE decision_id IS NULL OR TRIM(decision_id) = '' "
            "OR signal_id IS NULL OR TRIM(signal_id) = '' "
            "OR strategy_id IS NULL OR TRIM(strategy_id) = ''"
        ).fetchone()[0]
    )


def _count_transitions_missing_from_status(connection: sqlite3.Connection) -> int:
    return int(connection.execute("SELECT COUNT(*) FROM order_state_transitions WHERE from_status IS NULL OR TRIM(from_status) = ''").fetchone()[0])


def _count_untraceable_trades(connection: sqlite3.Connection) -> int:
    return int(
        connection.execute(
            "SELECT COUNT(*) FROM trade_ledger "
            "WHERE decision_id IS NULL OR TRIM(decision_id) = '' "
            "OR signal_id IS NULL OR TRIM(signal_id) = '' "
            "OR strategy_id IS NULL OR TRIM(strategy_id) = '' "
            "OR execution_mode IS NULL OR TRIM(execution_mode) = ''"
        ).fetchone()[0]
    )


def _build_cutover_evidence(
    connection: sqlite3.Connection,
    cutover: datetime | None,
    missing_columns: Mapping[str, tuple[str, ...]],
) -> ContractCutoverEvidence:
    if cutover is None:
        return ContractCutoverEvidence(
            cutover_at=None,
            status="CUTOVER_NOT_REQUESTED",
            table_row_counts={},
            orders_missing_provenance_count=0,
            transitions_missing_from_status_count=0,
            untraceable_trade_count=0,
            reasons=("cutover_at_not_supplied",),
        )
    if missing_columns:
        return _unavailable_cutover_evidence(cutover, "required_columns_missing")

    cutover_text = cutover.isoformat()
    counts = {
        "orders": _row_count_at_or_after(connection, "orders", "created_at", cutover_text),
        "order_state_transitions": _row_count_at_or_after(
            connection, "order_state_transitions", "occurred_at", cutover_text
        ),
        "trade_ledger": _row_count_at_or_after(connection, "trade_ledger", "created_at", cutover_text),
    }
    missing_provenance = _count_orders_missing_provenance_at_or_after(connection, cutover_text)
    missing_from = _count_transitions_missing_from_status_at_or_after(connection, cutover_text)
    untraceable = _count_untraceable_trades_at_or_after(connection, cutover_text)
    if not any(counts.values()):
        status, reasons = "NO_POST_CUTOVER_CONTRACT_EVIDENCE", ("no_rows_at_or_after_cutover",)
    elif missing_provenance or missing_from or untraceable:
        status = "POST_CUTOVER_CONTRACT_VIOLATION"
        reasons_list = []
        if missing_provenance:
            reasons_list.append("orders_missing_decision_signal_or_strategy")
        if missing_from:
            reasons_list.append("transitions_missing_from_status")
        if untraceable:
            reasons_list.append("trades_missing_traceability")
        reasons = tuple(reasons_list)
    else:
        status = "POST_CUTOVER_TRACEABLE_EVIDENCE"
        reasons = ("legacy_rows_remain_excluded_from_canonical_reconciliation",)
    return ContractCutoverEvidence(
        cutover_at=cutover_text,
        status=status,
        table_row_counts=counts,
        orders_missing_provenance_count=missing_provenance,
        transitions_missing_from_status_count=missing_from,
        untraceable_trade_count=untraceable,
        reasons=reasons,
    )


def _unavailable_cutover_evidence(cutover: datetime | None, reason: str) -> ContractCutoverEvidence:
    return ContractCutoverEvidence(
        cutover_at=cutover.isoformat() if cutover is not None else None,
        status="CUTOVER_EVIDENCE_UNAVAILABLE",
        table_row_counts={},
        orders_missing_provenance_count=0,
        transitions_missing_from_status_count=0,
        untraceable_trade_count=0,
        reasons=(reason,),
    )


def _parse_cutover_at(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("cutover_at_must_be_timezone_aware")
    return parsed.astimezone(timezone.utc)


def _row_count_at_or_after(connection: sqlite3.Connection, table: str, timestamp_column: str, cutover: str) -> int:
    return int(
        connection.execute(
            f'SELECT COUNT(*) FROM "{table}" WHERE "{timestamp_column}" >= ?', (cutover,)
        ).fetchone()[0]
    )


def _count_orders_missing_provenance_at_or_after(connection: sqlite3.Connection, cutover: str) -> int:
    return int(
        connection.execute(
            "SELECT COUNT(*) FROM orders WHERE created_at >= ? AND "
            "(decision_id IS NULL OR TRIM(decision_id) = '' "
            "OR signal_id IS NULL OR TRIM(signal_id) = '' "
            "OR strategy_id IS NULL OR TRIM(strategy_id) = '')",
            (cutover,),
        ).fetchone()[0]
    )


def _count_transitions_missing_from_status_at_or_after(connection: sqlite3.Connection, cutover: str) -> int:
    return int(
        connection.execute(
            "SELECT COUNT(*) FROM order_state_transitions WHERE occurred_at >= ? "
            "AND (from_status IS NULL OR TRIM(from_status) = '')",
            (cutover,),
        ).fetchone()[0]
    )


def _count_untraceable_trades_at_or_after(connection: sqlite3.Connection, cutover: str) -> int:
    return int(
        connection.execute(
            "SELECT COUNT(*) FROM trade_ledger WHERE created_at >= ? AND "
            "(decision_id IS NULL OR TRIM(decision_id) = '' "
            "OR signal_id IS NULL OR TRIM(signal_id) = '' "
            "OR strategy_id IS NULL OR TRIM(strategy_id) = '' "
            "OR execution_mode IS NULL OR TRIM(execution_mode) = '')",
            (cutover,),
        ).fetchone()[0]
    )


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
