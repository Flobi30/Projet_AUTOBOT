"""Read-only cost parity audit for AUTOBOT paper, shadow and research layers.

The audit checks whether official paper ledgers and shadow labs use cost
assumptions comparable with the research ``ExecutionCostModel``. It never
creates orders, mutates ledgers, changes strategy routing, or grants live
trading permission.
"""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from autobot.v2.shadow_cost_bridge import conservative_shadow_cost_defaults

from .execution_cost_model import ExecutionCostConfig


SHADOW_SOURCES: tuple[tuple[str, str], ...] = (
    ("trend_shadow", "trend_shadow_trades"),
    ("mean_reversion_shadow", "mean_reversion_shadow_trades"),
    ("setup_shadow", "setup_shadow_trades"),
)


@dataclass(frozen=True)
class CostParityAuditConfig:
    run_id: str
    state_db_path: str | Path | None = None
    trend_shadow_db_path: str | Path | None = None
    mean_reversion_shadow_db_path: str | Path | None = None
    setup_shadow_db_path: str | Path | None = None
    output_dir: str | Path = "reports/research/cost_parity"
    research_cost_config: ExecutionCostConfig = field(default_factory=ExecutionCostConfig)
    warning_delta_bps: float = 5.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "state_db_path": str(self.state_db_path) if self.state_db_path else None,
            "trend_shadow_db_path": str(self.trend_shadow_db_path) if self.trend_shadow_db_path else None,
            "mean_reversion_shadow_db_path": (
                str(self.mean_reversion_shadow_db_path) if self.mean_reversion_shadow_db_path else None
            ),
            "setup_shadow_db_path": str(self.setup_shadow_db_path) if self.setup_shadow_db_path else None,
            "output_dir": str(self.output_dir),
            "research_cost_config": self.research_cost_config.to_dict(),
            "warning_delta_bps": float(self.warning_delta_bps),
        }


@dataclass(frozen=True)
class CostSourceSummary:
    source: str
    source_path: str | None
    status: str
    table: str | None = None
    trade_count: int = 0
    cost_row_count: int = 0
    total_notional_eur: float = 0.0
    total_fees_eur: float = 0.0
    total_slippage_eur: float = 0.0
    total_cost_eur: float = 0.0
    avg_fee_bps: float | None = None
    avg_slippage_bps: float | None = None
    avg_total_cost_bps: float | None = None
    expected_cost_bps_per_side: float | None = None
    cost_delta_bps: float | None = None
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["warnings"] = list(self.warnings)
        return data


@dataclass(frozen=True)
class CostParityAuditReport:
    run_id: str
    generated_at: str
    config: CostParityAuditConfig
    research_cost_config: dict[str, float]
    expected_cost_bps_per_side: float
    expected_fee_bps_per_side: float
    expected_legacy_shadow_slippage_bps_per_side: float
    sources: tuple[CostSourceSummary, ...]
    warnings: tuple[str, ...] = ()
    json_report_path: str | None = None
    markdown_report_path: str | None = None
    safety_notes: tuple[str, ...] = field(
        default=(
            "Read-only cost parity audit.",
            "No paper or live order is created.",
            "No strategy registry mutation is performed.",
            "No live trading permission is granted.",
        )
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "config": self.config.to_dict(),
            "research_cost_config": dict(self.research_cost_config),
            "expected_cost_bps_per_side": self.expected_cost_bps_per_side,
            "expected_fee_bps_per_side": self.expected_fee_bps_per_side,
            "expected_legacy_shadow_slippage_bps_per_side": self.expected_legacy_shadow_slippage_bps_per_side,
            "sources": [source.to_dict() for source in self.sources],
            "warnings": list(self.warnings),
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
            "safety_notes": list(self.safety_notes),
        }


def audit_cost_parity(config: CostParityAuditConfig) -> CostParityAuditReport:
    """Audit cost assumptions across read-only persisted evidence."""

    config.research_cost_config.validate()
    if not math.isfinite(float(config.warning_delta_bps)) or float(config.warning_delta_bps) < 0.0:
        raise ValueError("warning_delta_bps must be finite and non-negative")

    defaults = conservative_shadow_cost_defaults(config.research_cost_config)
    expected = defaults.effective_cost_bps_per_side
    sources = [
        _audit_state_db_costs(
            config.state_db_path,
            expected_cost_bps=expected,
            warning_delta_bps=config.warning_delta_bps,
        )
    ]
    shadow_paths: dict[str, str | Path | None] = {
        "trend_shadow": config.trend_shadow_db_path,
        "mean_reversion_shadow": config.mean_reversion_shadow_db_path,
        "setup_shadow": config.setup_shadow_db_path,
    }
    for source, table in SHADOW_SOURCES:
        sources.append(
            _audit_shadow_costs(
                source=source,
                path=shadow_paths[source],
                table=table,
                expected_cost_bps=expected,
                warning_delta_bps=config.warning_delta_bps,
            )
        )

    warnings = tuple(dict.fromkeys(warning for source in sources for warning in source.warnings))
    return CostParityAuditReport(
        run_id=config.run_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        config=config,
        research_cost_config=config.research_cost_config.to_dict(),
        expected_cost_bps_per_side=expected,
        expected_fee_bps_per_side=defaults.fee_bps_per_side,
        expected_legacy_shadow_slippage_bps_per_side=defaults.slippage_bps_per_side,
        sources=tuple(sources),
        warnings=warnings,
    )


def write_cost_parity_audit_report(
    report: CostParityAuditReport,
    output_dir: str | Path | None = None,
) -> CostParityAuditReport:
    output_path = Path(output_dir or report.config.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / f"{report.run_id}.json"
    md_path = output_path / f"{report.run_id}.md"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(render_cost_parity_audit_report(report), encoding="utf-8")
    return replace(report, json_report_path=str(json_path), markdown_report_path=str(md_path))


def render_cost_parity_audit_report(report: CostParityAuditReport) -> str:
    lines = [
        f"# Cost Parity Audit - {report.run_id}",
        "",
        "## Research Cost Baseline",
        "",
        f"- Expected per-side effective cost: `{report.expected_cost_bps_per_side:.6f}` bps",
        f"- Fee per side: `{report.expected_fee_bps_per_side:.6f}` bps",
        f"- Legacy shadow slippage bucket per side: `{report.expected_legacy_shadow_slippage_bps_per_side:.6f}` bps",
        "",
        "## Sources",
        "",
        "| Source | Status | Trades | Cost Rows | Notional EUR | Fees EUR | Slippage EUR | Total Cost EUR | Avg Fee bps | Avg Slippage bps | Avg Total bps | Delta bps | Warnings |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for source in report.sources:
        lines.append(
            f"| {source.source} | {source.status} | {source.trade_count} | {source.cost_row_count} | "
            f"{source.total_notional_eur:.6f} | {source.total_fees_eur:.6f} | "
            f"{source.total_slippage_eur:.6f} | {source.total_cost_eur:.6f} | "
            f"{_fmt(source.avg_fee_bps)} | {_fmt(source.avg_slippage_bps)} | "
            f"{_fmt(source.avg_total_cost_bps)} | {_fmt(source.cost_delta_bps)} | "
            f"{', '.join(source.warnings) or 'none'} |"
        )
    if report.warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in report.warnings)
    lines.extend(["", "## Safety", ""])
    lines.extend(f"- {note}" for note in report.safety_notes)
    lines.append("")
    return "\n".join(lines)


def _audit_state_db_costs(
    path: str | Path | None,
    *,
    expected_cost_bps: float,
    warning_delta_bps: float,
) -> CostSourceSummary:
    source = "official_paper_trade_ledger"
    if path is None:
        return _empty_source(source, None, "not_configured", expected_cost_bps, ("state_db_not_configured",))
    db_path = Path(path)
    if not db_path.exists():
        return _empty_source(source, str(db_path), "missing", expected_cost_bps, ("state_db_missing",))
    with _connect_readonly(db_path) as conn:
        if not _table_exists(conn, "trade_ledger"):
            return _empty_source(source, str(db_path), "table_missing", expected_cost_bps, ("trade_ledger_missing",))
        rows = _select_all(conn, "trade_ledger")

    total_notional = 0.0
    total_fees = 0.0
    total_slippage = 0.0
    cost_rows = 0
    position_ids: set[str] = set()
    for row in rows:
        price = _safe_float(row.get("executed_price"))
        volume = _safe_float(row.get("volume"))
        notional = abs(price * volume)
        if notional <= 0.0:
            continue
        cost_rows += 1
        position_id = str(row.get("position_id") or row.get("trade_id") or "")
        if position_id:
            position_ids.add(position_id)
        total_notional += notional
        total_fees += max(0.0, _safe_float(row.get("fees")))
        total_slippage += _slippage_cost(row)
    return _summary(
        source=source,
        source_path=str(db_path),
        status="ok",
        table="trade_ledger",
        trade_count=len(position_ids) or cost_rows,
        cost_row_count=cost_rows,
        total_notional_eur=total_notional,
        total_fees_eur=total_fees,
        total_slippage_eur=total_slippage,
        expected_cost_bps=expected_cost_bps,
        warning_delta_bps=warning_delta_bps,
        extra_warnings=(),
    )


def _audit_shadow_costs(
    *,
    source: str,
    path: str | Path | None,
    table: str,
    expected_cost_bps: float,
    warning_delta_bps: float,
) -> CostSourceSummary:
    if path is None:
        return _empty_source(source, None, "not_configured", expected_cost_bps, (f"{source}_not_configured",))
    db_path = Path(path)
    if not db_path.exists():
        return _empty_source(source, str(db_path), "missing", expected_cost_bps, (f"{source}_db_missing",))
    with _connect_readonly(db_path) as conn:
        if not _table_exists(conn, table):
            return _empty_source(source, str(db_path), "table_missing", expected_cost_bps, (f"{table}_missing",))
        rows = _select_all(conn, table)

    total_notional = 0.0
    total_fees = 0.0
    cost_rows = 0
    for row in rows:
        notional = abs(_safe_float(row.get("notional")))
        fees = max(0.0, _safe_float(row.get("fees")))
        if notional <= 0.0 and fees <= 0.0:
            continue
        cost_rows += 1
        # Shadow trade rows are closed round trips with a single entry notional.
        # Use 2x notional to compare their collapsed fees against per-side research costs.
        total_notional += notional * 2.0
        total_fees += fees
    return _summary(
        source=source,
        source_path=str(db_path),
        status="ok",
        table=table,
        trade_count=cost_rows,
        cost_row_count=cost_rows,
        total_notional_eur=total_notional,
        total_fees_eur=total_fees,
        total_slippage_eur=0.0,
        expected_cost_bps=expected_cost_bps,
        warning_delta_bps=warning_delta_bps,
        extra_warnings=("shadow_cost_components_collapsed",),
    )


def _summary(
    *,
    source: str,
    source_path: str,
    status: str,
    table: str,
    trade_count: int,
    cost_row_count: int,
    total_notional_eur: float,
    total_fees_eur: float,
    total_slippage_eur: float,
    expected_cost_bps: float,
    warning_delta_bps: float,
    extra_warnings: Iterable[str],
) -> CostSourceSummary:
    total_cost = total_fees_eur + total_slippage_eur
    avg_fee = _bps(total_fees_eur, total_notional_eur)
    avg_slippage = _bps(total_slippage_eur, total_notional_eur)
    avg_total = _bps(total_cost, total_notional_eur)
    delta = None if avg_total is None else avg_total - expected_cost_bps
    warnings = list(extra_warnings)
    if cost_row_count == 0:
        warnings.append("no_cost_rows")
    if delta is not None and abs(delta) > warning_delta_bps:
        if delta < 0.0:
            warnings.append("avg_cost_below_research_expected")
        else:
            warnings.append("avg_cost_above_research_expected")
    return CostSourceSummary(
        source=source,
        source_path=source_path,
        status=status,
        table=table,
        trade_count=trade_count,
        cost_row_count=cost_row_count,
        total_notional_eur=total_notional_eur,
        total_fees_eur=total_fees_eur,
        total_slippage_eur=total_slippage_eur,
        total_cost_eur=total_cost,
        avg_fee_bps=avg_fee,
        avg_slippage_bps=avg_slippage,
        avg_total_cost_bps=avg_total,
        expected_cost_bps_per_side=expected_cost_bps,
        cost_delta_bps=delta,
        warnings=tuple(dict.fromkeys(warnings)),
    )


def _empty_source(
    source: str,
    source_path: str | None,
    status: str,
    expected_cost_bps: float,
    warnings: Iterable[str],
) -> CostSourceSummary:
    return CostSourceSummary(
        source=source,
        source_path=source_path,
        status=status,
        expected_cost_bps_per_side=expected_cost_bps,
        warnings=tuple(warnings),
    )


def _connect_readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return row is not None


def _select_all(conn: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    rows = conn.execute(f"SELECT * FROM {table}").fetchall()
    return [dict(row) for row in rows]


def _slippage_cost(row: Mapping[str, Any]) -> float:
    slippage_bps = abs(_safe_float(row.get("slippage_bps")))
    price = abs(_safe_float(row.get("executed_price")))
    volume = abs(_safe_float(row.get("volume")))
    return (slippage_bps / 10_000.0) * price * volume


def _bps(value: float, notional: float) -> float | None:
    if notional <= 0.0:
        return None
    return (value / notional) * 10_000.0


def _safe_float(value: Any) -> float:
    try:
        result = float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return result if math.isfinite(result) else 0.0


def _fmt(value: float | None) -> str:
    return "" if value is None else f"{value:.6f}"
