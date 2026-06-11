"""Read-only reconciliation of legacy open positions."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class OrphanPosition:
    position_id: str
    instance_id: str | None
    open_time: str | None
    buy_price: float
    volume: float
    notional_eur: float
    strategy: str | None
    symbol: str | None
    metadata: dict[str, Any]
    current_instance_link: bool
    trade_ledger_rows: int
    recommended_status: str
    impact: tuple[str, ...]


@dataclass(frozen=True)
class OrphanPositionReconciliationReport:
    run_id: str
    generated_at: str
    state_db_path: str
    open_position_count: int
    orphan_count: int
    orphan_notional_eur: float
    positions: tuple[OrphanPosition, ...]
    write_performed: bool = False
    live_promotion_allowed: bool = False
    json_report_path: str | None = None
    markdown_report_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["positions"] = [asdict(position) for position in self.positions]
        return payload


def audit_orphan_positions(*, state_db_path: str | Path, run_id: str) -> OrphanPositionReconciliationReport:
    path = Path(state_db_path)
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        position_columns = {row[1] for row in connection.execute("PRAGMA table_info(positions)")}
        ledger_exists = _table_exists(connection, "trade_ledger")
        instance_exists = _table_exists(connection, "instance_state")
        rows = connection.execute("SELECT * FROM positions WHERE lower(status) = 'open' ORDER BY open_time, id").fetchall()
        positions: list[OrphanPosition] = []
        for row in rows:
            position_id = str(row["id"])
            instance_id = str(row["instance_id"] or "") or None
            symbol = str(row["symbol"] or "") or None if "symbol" in position_columns else None
            metadata = _json_object(row["metadata"] if "metadata" in position_columns else None)
            current_link = bool(instance_exists and instance_id and connection.execute(
                "SELECT 1 FROM instance_state WHERE instance_id = ? LIMIT 1", (instance_id,)
            ).fetchone())
            ledger_rows = 0
            if ledger_exists:
                ledger_rows = int(connection.execute(
                    "SELECT COUNT(*) FROM trade_ledger WHERE position_id = ? OR instance_id = ?",
                    (position_id, instance_id),
                ).fetchone()[0])
            buy_price = float(row["buy_price"] or 0.0)
            volume = float(row["volume"] or 0.0)
            orphan = not current_link or not symbol or not metadata.get("buy_txid")
            if not orphan:
                continue
            status = "needs_manual_review"
            if not current_link and not symbol:
                status = "legacy_orphan_candidate"
            impact = (
                "ignore_for_current_runtime: instance is not currently loaded" if not current_link else "current instance link exists",
                "dashboard/open-position counts may be inflated",
                "capital or drawdown reports reading raw positions may be misleading",
                "safe_to_mark_reconciled_later only after backup and human approval",
            )
            positions.append(OrphanPosition(
                position_id=position_id,
                instance_id=instance_id,
                open_time=str(row["open_time"] or "") or None,
                buy_price=buy_price,
                volume=volume,
                notional_eur=buy_price * volume,
                strategy=str(row["strategy"] or "") or None,
                symbol=symbol,
                metadata=metadata,
                current_instance_link=current_link,
                trade_ledger_rows=ledger_rows,
                recommended_status=status,
                impact=impact,
            ))
    finally:
        connection.close()
    return OrphanPositionReconciliationReport(
        run_id=run_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        state_db_path=str(path),
        open_position_count=len(rows),
        orphan_count=len(positions),
        orphan_notional_eur=sum(item.notional_eur for item in positions),
        positions=tuple(positions),
    )


def write_orphan_position_report(report: OrphanPositionReconciliationReport, output_dir: str | Path) -> OrphanPositionReconciliationReport:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / f"{report.run_id}.json"
    markdown_path = output / f"{report.run_id}.md"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    lines = [
        f"# Orphan Position Reconciliation - {report.run_id}", "",
        f"- Open positions: `{report.open_position_count}`",
        f"- Orphan candidates: `{report.orphan_count}`",
        f"- Approximate orphan notional: `{report.orphan_notional_eur:.6f} EUR`", "",
        "| Position | Instance | Opened | Symbol | Strategy | Notional EUR | Instance link | Ledger rows | Recommendation |",
        "| --- | --- | --- | --- | --- | ---: | --- | ---: | --- |",
    ]
    for item in report.positions:
        lines.append(
            f"| {item.position_id} | {item.instance_id or 'none'} | {item.open_time or 'unknown'} | "
            f"{item.symbol or 'null'} | {item.strategy or 'unknown'} | {item.notional_eur:.6f} | "
            f"{item.current_instance_link} | {item.trade_ledger_rows} | {item.recommended_status} |"
        )
        lines.extend(
            [
                "",
                f"### {item.position_id}",
                "",
                f"- Metadata: `{json.dumps(item.metadata, sort_keys=True)}`",
                f"- Current instance link: `{item.current_instance_link}`",
                f"- Linked trade-ledger rows: `{item.trade_ledger_rows}`",
                f"- Recommended status: `{item.recommended_status}`",
            ]
        )
        lines.extend(f"- Impact: {impact}" for impact in item.impact)
    lines.extend(["", "No database mutation was performed. Human approval is required before reconciliation."])
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return replace(report, json_report_path=str(json_path), markdown_report_path=str(markdown_path))


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    return connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _json_object(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value) if isinstance(value, (str, bytes)) else value
        return dict(parsed) if isinstance(parsed, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
