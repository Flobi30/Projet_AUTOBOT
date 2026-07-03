"""Read-only integrity checks for the AUTOBOT runtime SQLite state DB."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from autobot.v2.strategy_runtime_policy import LEGACY_UNATTRIBUTED_STRATEGY_ID


VALID_SCORE_BUCKETS = {"high", "medium", "low", "missing"}


@dataclass(frozen=True)
class DbIntegrityConfig:
    state_db_path: Path
    output_dir: Path = Path("reports/paper/db_integrity")
    run_id: str | None = None
    snapshot_dir: Path | None = None
    write_report: bool = True
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def resolved_run_id(self) -> str:
        if self.run_id:
            return self.run_id
        return f"db_integrity_{self.generated_at.strftime('%Y%m%d_%H%M%S')}"


@dataclass(frozen=True)
class DbIntegrityReport:
    run_id: str
    generated_at: str
    state_db_path: str
    inspected_db_path: str
    source_mode: str
    status: str
    checks: dict[str, Any]
    warnings: tuple[str, ...]
    safety_notes: tuple[str, ...]
    json_report_path: str | None = None
    markdown_report_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["warnings"] = list(self.warnings)
        data["safety_notes"] = list(self.safety_notes)
        return data


def build_db_integrity_report(config: DbIntegrityConfig) -> DbIntegrityReport:
    inspected_path = _snapshot_db(config.state_db_path, config.snapshot_dir, config.resolved_run_id)
    source_mode = "snapshot" if inspected_path != config.state_db_path else "read_only"
    warnings: list[str] = []
    checks: dict[str, Any] = {
        "trade_ledger_exists": False,
        "decision_ledger_exists": False,
        "journal_mode": None,
        "busy_timeout_ms": None,
        "trade_id_unique_index_present": False,
        "duplicate_trade_id_groups": 0,
        "economic_duplicate_groups": 0,
        "legacy_unattributed_closed_trades": 0,
        "official_metrics_legacy_policy": "excluded_by_strategy_id_gate",
        "invalid_score_bucket_rows": 0,
        "negative_cost_rows": 0,
        "legacy_rows_used_by_official_metrics": False,
    }
    if not inspected_path.exists():
        warnings.append("state_db_missing")
        report = _report(config, inspected_path, source_mode, "FAIL", checks, warnings)
        return _maybe_write(report, config)

    try:
        with _connect_readonly(inspected_path) as conn:
            checks["journal_mode"] = _pragma_scalar(conn, "journal_mode")
            checks["busy_timeout_ms"] = _pragma_scalar(conn, "busy_timeout")
            if not _table_exists(conn, "trade_ledger"):
                warnings.append("trade_ledger_missing")
                report = _report(config, inspected_path, source_mode, "FAIL", checks, warnings)
                return _maybe_write(report, config)
            checks["trade_ledger_exists"] = True
            columns = _columns(conn, "trade_ledger")
            checks["missing_required_columns"] = sorted(
                column
                for column in ("strategy_id", "execution_mode", "decision_id", "fees")
                if column not in columns
            )
            for column in checks["missing_required_columns"]:
                warnings.append(f"trade_ledger_column_missing:{column}")
            checks["decision_ledger_exists"] = _table_exists(conn, "decision_ledger")
            checks["trade_id_unique_index_present"] = _has_unique_trade_id_index(conn)
            checks["duplicate_trade_id_groups"] = _scalar_int(
                conn,
                """
                SELECT COUNT(*) FROM (
                    SELECT trade_id FROM trade_ledger
                    WHERE trade_id IS NOT NULL AND trade_id != ''
                    GROUP BY trade_id HAVING COUNT(*) > 1
                )
                """,
            )
            checks["economic_duplicate_groups"] = _economic_duplicate_groups(conn, columns)
            if "strategy_id" in columns:
                checks["legacy_unattributed_closed_trades"] = _scalar_int(
                    conn,
                    """
                    SELECT COUNT(*) FROM trade_ledger
                    WHERE COALESCE(is_closing_leg, 0) = 1
                      AND (strategy_id IS NULL OR strategy_id = '' OR strategy_id = ?)
                    """,
                    (LEGACY_UNATTRIBUTED_STRATEGY_ID,),
                )
            else:
                checks["legacy_unattributed_closed_trades"] = _scalar_int(
                    conn,
                    "SELECT COUNT(*) FROM trade_ledger WHERE COALESCE(is_closing_leg, 0) = 1",
                )
            if "fees" in columns:
                fee_expr = "COALESCE(fees, 0) < 0" if "fees" in columns else "0"
                checks["negative_cost_rows"] = _scalar_int(
                    conn,
                    f"SELECT COUNT(*) FROM trade_ledger WHERE {fee_expr}",
                )
            checks["invalid_score_bucket_rows"] = _invalid_score_bucket_rows(conn, columns)
    except sqlite3.Error as exc:
        warnings.append(f"sqlite_error:{exc}")
        report = _report(config, inspected_path, source_mode, "FAIL", checks, warnings)
        return _maybe_write(report, config)

    status = "PASS"
    if checks["duplicate_trade_id_groups"] or checks["negative_cost_rows"]:
        status = "FAIL"
    elif (
        checks["economic_duplicate_groups"]
        or checks["invalid_score_bucket_rows"]
        or not checks["trade_id_unique_index_present"]
        or checks.get("missing_required_columns")
    ):
        status = "PASS_WITH_WARNINGS"
    report = _report(config, inspected_path, source_mode, status, checks, warnings)
    return _maybe_write(report, config)


def _report(
    config: DbIntegrityConfig,
    inspected_path: Path,
    source_mode: str,
    status: str,
    checks: Mapping[str, Any],
    warnings: list[str],
) -> DbIntegrityReport:
    return DbIntegrityReport(
        run_id=config.resolved_run_id,
        generated_at=config.generated_at.isoformat(),
        state_db_path=str(config.state_db_path),
        inspected_db_path=str(inspected_path),
        source_mode=source_mode,
        status=status,
        checks=dict(checks),
        warnings=tuple(warnings),
        safety_notes=(
            "Read-only DB integrity check.",
            "No trade, order, paper capital, live flag, or strategy promotion is created.",
            "Legacy/unattributed rows are allowed as history but excluded by official strategy metrics.",
        ),
    )


def _maybe_write(report: DbIntegrityReport, config: DbIntegrityConfig) -> DbIntegrityReport:
    if not config.write_report:
        return report
    config.output_dir.mkdir(parents=True, exist_ok=True)
    base = config.output_dir / report.run_id
    json_path = base.with_suffix(".json")
    markdown_path = base.with_suffix(".md")
    report_with_paths = DbIntegrityReport(
        **{
            **report.to_dict(),
            "warnings": tuple(report.warnings),
            "safety_notes": tuple(report.safety_notes),
            "json_report_path": str(json_path),
            "markdown_report_path": str(markdown_path),
        }
    )
    json_path.write_text(json.dumps(report_with_paths.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(_markdown(report_with_paths), encoding="utf-8")
    return report_with_paths


def _snapshot_db(source: Path, snapshot_dir: Path | None, run_id: str) -> Path:
    if snapshot_dir is None or not source.exists():
        return source
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    target = snapshot_dir / f"{run_id}_{source.name}"
    shutil.copy2(source, target)
    for suffix in ("-wal", "-shm"):
        sibling = Path(f"{source}{suffix}")
        if sibling.exists():
            shutil.copy2(sibling, Path(f"{target}{suffix}"))
    return target


def _connect_readonly(path: Path) -> sqlite3.Connection:
    timeout_ms = _env_int("SQLITE_BUSY_TIMEOUT_MS", 30_000, 1_000, 300_000)
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=timeout_ms / 1000.0)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout={timeout_ms}")
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _pragma_scalar(conn: sqlite3.Connection, name: str) -> Any:
    row = conn.execute(f"PRAGMA {name}").fetchone()
    if row is None:
        return None
    return row[0]


def _scalar_int(conn: sqlite3.Connection, query: str, params: tuple[Any, ...] = ()) -> int:
    row = conn.execute(query, params).fetchone()
    return int(row[0] or 0) if row is not None else 0


def _has_unique_trade_id_index(conn: sqlite3.Connection) -> bool:
    for row in conn.execute("PRAGMA index_list(trade_ledger)").fetchall():
        index_name = str(row[1])
        unique = bool(row[2])
        if not unique:
            continue
        columns = [str(column[2]) for column in conn.execute(f"PRAGMA index_info({index_name})").fetchall()]
        if columns == ["trade_id"]:
            return True
    return False


def _economic_duplicate_groups(conn: sqlite3.Connection, columns: set[str]) -> int:
    def expr(column: str, default: str = "''") -> str:
        if column not in columns:
            return f"{default} AS {column}"
        return f"COALESCE({column}, {default}) AS {column}"

    pnl_expr = (
        "ROUND(COALESCE(net_pnl, realized_pnl, 0), 12) AS pnl"
        if "net_pnl" in columns
        else "ROUND(COALESCE(realized_pnl, 0), 12) AS pnl"
    )
    query = f"""
        SELECT COUNT(*) FROM (
            SELECT
                {expr("strategy_id")},
                {expr("execution_mode")},
                {expr("position_id")},
                {expr("symbol")},
                {expr("side")},
                ROUND(COALESCE(executed_price, 0), 12) AS px,
                ROUND(COALESCE(volume, 0), 12) AS qty,
                {pnl_expr},
                {expr("created_at")}
            FROM trade_ledger
            WHERE COALESCE(is_closing_leg, 0) = 1
            GROUP BY strategy_id, execution_mode, position_id, symbol, side, px, qty, pnl, created_at
            HAVING COUNT(*) > 1
        )
    """
    return _scalar_int(conn, query)


def _invalid_score_bucket_rows(conn: sqlite3.Connection, columns: set[str]) -> int:
    if "decision_id" not in columns:
        return 0
    invalid = 0
    for row in conn.execute(
        "SELECT decision_id FROM trade_ledger WHERE COALESCE(is_closing_leg, 0) = 1"
    ).fetchall():
        metadata = _json_object(row["decision_id"])
        bucket = metadata.get("score_bucket")
        if bucket is not None and str(bucket) not in VALID_SCORE_BUCKETS:
            invalid += 1
    return invalid


def _json_object(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, (str, bytes)) and raw:
        try:
            payload = json.loads(raw)
            return dict(payload) if isinstance(payload, dict) else {}
        except Exception:
            return {}
    return {}


def _env_int(name: str, default: int, min_value: int, max_value: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(min_value, min(max_value, value))


def _markdown(report: DbIntegrityReport) -> str:
    lines = [
        f"# DB Integrity - {report.run_id}",
        "",
        f"- Generated: `{report.generated_at}`",
        f"- Status: `{report.status}`",
        f"- Source mode: `{report.source_mode}`",
        f"- State DB: `{report.state_db_path}`",
        f"- Inspected DB: `{report.inspected_db_path}`",
        "",
        "## Checks",
        "",
    ]
    for key, value in sorted(report.checks.items()):
        lines.append(f"- `{key}`: `{value}`")
    if report.warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in report.warnings)
    lines.extend(["", "## Safety", ""])
    lines.extend(f"- {note}" for note in report.safety_notes)
    return "\n".join(lines) + "\n"
