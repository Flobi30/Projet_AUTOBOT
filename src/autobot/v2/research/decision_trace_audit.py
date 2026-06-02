"""Canonical decision trace coverage audit for AUTOBOT research.

The audit is read-only. It checks whether existing runtime tables can explain a
decision from signal to rejection outcome or from signal to order/trade/PnL.
It does not alter paper execution, live routing, risk thresholds or strategy
promotion.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


@dataclass(frozen=True)
class DecisionTraceAuditConfig:
    state_db_path: str
    run_id: str = "decision_trace_audit"
    limit: int = 10_000
    trace_sample_limit: int = 500

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DecisionTrace:
    trace_id: str
    decision_id: str | None
    signal_id: str | None
    symbol: str | None
    strategy: str | None
    engine: str | None
    first_seen_at: str | None
    event_types: tuple[str, ...]
    event_statuses: tuple[str, ...]
    reasons: tuple[str, ...]
    has_signal: bool
    has_decision: bool
    is_rejected: bool
    is_execution_path: bool
    has_order: bool
    has_fill: bool
    has_trade: bool
    has_pnl: bool
    has_outcome: bool
    net_pnl_eur: float
    outcome_labels: tuple[str, ...]
    missing_stages: tuple[str, ...]
    canonical_complete: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DecisionTraceAuditSummary:
    trace_count: int
    canonical_complete_count: int
    canonical_complete_ratio: float
    signal_without_decision_count: int
    rejected_trace_count: int
    rejected_with_outcome_count: int
    execution_trace_count: int
    execution_complete_count: int
    orphan_order_count: int
    orphan_trade_count: int
    total_net_pnl_eur: float
    missing_stage_counts: dict[str, int]
    event_type_counts: dict[str, int]
    event_status_counts: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DecisionTraceAuditReport:
    run_id: str
    generated_at: str
    config: DecisionTraceAuditConfig
    data_sources: dict[str, Any]
    summary: DecisionTraceAuditSummary
    traces: tuple[DecisionTrace, ...] = field(default_factory=tuple)
    json_report_path: str | None = None
    markdown_report_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "config": self.config.to_dict(),
            "data_sources": self.data_sources,
            "summary": self.summary.to_dict(),
            "traces": [trace.to_dict() for trace in self.traces],
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
        }


def audit_decision_traces(config: DecisionTraceAuditConfig | str | Path) -> DecisionTraceAuditReport:
    cfg = config if isinstance(config, DecisionTraceAuditConfig) else DecisionTraceAuditConfig(state_db_path=str(config))
    data = _load_state_data(cfg)
    traces, orphan_orders, orphan_trades = _build_traces(data)
    summary = _summary(traces, orphan_orders=orphan_orders, orphan_trades=orphan_trades)
    sorted_traces = tuple(sorted(traces, key=lambda item: (item.first_seen_at or "", item.trace_id)))
    sample_limit = max(0, int(cfg.trace_sample_limit))
    return DecisionTraceAuditReport(
        run_id=cfg.run_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        config=cfg,
        data_sources=data["sources"],
        summary=summary,
        traces=sorted_traces[:sample_limit] if sample_limit else (),
    )


def write_decision_trace_audit_report(
    report: DecisionTraceAuditReport,
    output_dir: str | Path,
) -> DecisionTraceAuditReport:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / f"{report.run_id}.json"
    md_path = output_path / f"{report.run_id}.md"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(render_decision_trace_audit_report(report), encoding="utf-8")
    return replace(report, json_report_path=str(json_path), markdown_report_path=str(md_path))


def render_decision_trace_audit_report(report: DecisionTraceAuditReport) -> str:
    summary = report.summary
    lines = [
        f"# Decision Trace Audit - {report.run_id}",
        "",
        "## Summary",
        "",
        f"- Traces: `{summary.trace_count}`",
        f"- Stored trace sample: `{len(report.traces)}` / `{report.config.trace_sample_limit}`",
        f"- Canonical complete traces: `{summary.canonical_complete_count}`",
        f"- Canonical complete ratio: `{summary.canonical_complete_ratio:.2f}%`",
        f"- Signal without decision: `{summary.signal_without_decision_count}`",
        f"- Rejected traces: `{summary.rejected_trace_count}`",
        f"- Rejected with outcome: `{summary.rejected_with_outcome_count}`",
        f"- Execution traces: `{summary.execution_trace_count}`",
        f"- Execution complete: `{summary.execution_complete_count}`",
        f"- Orphan orders: `{summary.orphan_order_count}`",
        f"- Orphan trades: `{summary.orphan_trade_count}`",
        f"- Total linked net PnL EUR: `{summary.total_net_pnl_eur:.6f}`",
        "",
        "## Missing Stages",
        "",
        "| Stage | Count |",
        "| --- | ---: |",
    ]
    for stage, count in sorted(summary.missing_stage_counts.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"| {stage} | {count} |")
    if not summary.missing_stage_counts:
        lines.append("| none | 0 |")
    lines.extend(
        [
            "",
            "## Event Types",
            "",
            "| Event Type | Count |",
            "| --- | ---: |",
        ]
    )
    for event_type, count in sorted(summary.event_type_counts.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"| {event_type} | {count} |")
    if not summary.event_type_counts:
        lines.append("| none | 0 |")
    lines.extend(
        [
            "",
            "## Top Incomplete Traces",
            "",
            "| Trace | Symbol | Engine | Statuses | Missing | Net PnL | Reasons |",
            "| --- | --- | --- | --- | --- | ---: | --- |",
        ]
    )
    incomplete = [trace for trace in report.traces if not trace.canonical_complete]
    for trace in incomplete[:50]:
        lines.append(
            f"| {trace.trace_id} | {trace.symbol or ''} | {trace.engine or ''} | "
            f"{', '.join(trace.event_statuses) or ''} | {', '.join(trace.missing_stages) or ''} | "
            f"{trace.net_pnl_eur:.6f} | {', '.join(trace.reasons) or ''} |"
        )
    if not incomplete:
        lines.append("| none |  |  |  |  | 0.000000 |  |")
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "This audit is read-only and research-only. It does not authorize paper or live execution.",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit AUTOBOT decision trace coverage")
    parser.add_argument("--state-db", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--run-id", default="decision_trace_audit")
    parser.add_argument("--limit", type=int, default=10_000)
    parser.add_argument("--trace-sample-limit", type=int, default=500)
    args = parser.parse_args(argv)

    report = write_decision_trace_audit_report(
        audit_decision_traces(
            DecisionTraceAuditConfig(
                state_db_path=args.state_db,
                run_id=args.run_id,
                limit=args.limit,
                trace_sample_limit=args.trace_sample_limit,
            )
        ),
        args.output_dir,
    )
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 0


def _load_state_data(config: DecisionTraceAuditConfig) -> dict[str, Any]:
    path = Path(config.state_db_path)
    sources = {
        "state_db_path": str(path),
        "status": "missing",
        "tables": {},
    }
    if not path.exists():
        return {"sources": sources, "decision_rows": [], "orders": [], "trades": [], "outcomes": []}
    with _read_only_conn(path) as conn:
        tables = _table_names(conn)
        sources["status"] = "ok"
        sources["available_tables"] = sorted(tables)
        decision_rows = _select_rows(
            conn,
            "decision_ledger",
            "SELECT * FROM decision_ledger ORDER BY created_at ASC, id ASC LIMIT ?",
            (max(1, int(config.limit)),),
            sources,
        )
        orders = _select_rows(conn, "orders", "SELECT * FROM orders", (), sources)
        trades = _select_rows(conn, "trade_ledger", "SELECT * FROM trade_ledger", (), sources)
        outcomes = _select_rows(conn, "signal_outcomes", "SELECT * FROM signal_outcomes", (), sources)
    return {
        "sources": sources,
        "decision_rows": decision_rows,
        "orders": orders,
        "trades": trades,
        "outcomes": outcomes,
    }


def _build_traces(data: Mapping[str, Any]) -> tuple[list[DecisionTrace], int, int]:
    typed_rows: list[tuple[str, Mapping[str, Any]]] = []
    for row in data.get("decision_rows", []):
        typed_rows.append(("events", row))
    for row in data.get("orders", []):
        typed_rows.append(("orders", row))
    for row in data.get("trades", []):
        typed_rows.append(("trades", row))
    for row in data.get("outcomes", []):
        typed_rows.append(("outcomes", row))

    parent: dict[str, str] = {}

    def find(key: str) -> str:
        parent.setdefault(key, key)
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    def union(left: str, right: str) -> None:
        root_left = find(left)
        root_right = find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    for _, row in typed_rows:
        keys = _trace_keys(row)
        if not keys:
            continue
        first = keys[0]
        find(first)
        for key in keys[1:]:
            union(first, key)

    component_keys: dict[str, set[str]] = defaultdict(set)
    for key in list(parent):
        component_keys[find(key)].add(key)
    component_trace_ids = {root: _canonical_trace_id(keys) for root, keys in component_keys.items()}
    builders: dict[str, dict[str, Any]] = {
        trace_id: {"events": [], "orders": [], "trades": [], "outcomes": []}
        for trace_id in component_trace_ids.values()
    }

    orphan_orders = 0
    orphan_trades = 0
    for kind, row in typed_rows:
        if kind == "orders" and not _has_decision_or_signal_link(row):
            orphan_orders += 1
        if kind == "trades" and not _has_decision_or_signal_link(row):
            orphan_trades += 1
        keys = _trace_keys(row)
        if not keys:
            continue
        trace_id = component_trace_ids[find(keys[0])]
        builders[trace_id][kind].append(row)

    return [_trace_from_builder(trace_id, builder) for trace_id, builder in builders.items()], orphan_orders, orphan_trades


def _trace_from_builder(trace_id: str, builder: Mapping[str, Any]) -> DecisionTrace:
    events = tuple(builder.get("events", ()))
    orders = tuple(builder.get("orders", ()))
    trades = tuple(builder.get("trades", ()))
    outcomes = tuple(builder.get("outcomes", ()))
    all_rows = events + orders + trades + outcomes
    first = min((_created_at(row) for row in all_rows if _created_at(row)), default=None)

    event_types = tuple(sorted({str(row.get("event_type")) for row in events if row.get("event_type")}))
    statuses = tuple(sorted({str(row.get("event_status") or row.get("status") or row.get("original_status")) for row in all_rows if row.get("event_status") or row.get("status") or row.get("original_status")}))
    reasons = tuple(sorted({str(row.get("reason") or row.get("rejection_reason") or row.get("last_error_code")) for row in all_rows if row.get("reason") or row.get("rejection_reason") or row.get("last_error_code")}))
    has_signal = any(str(row.get("event_type")) == "signal" for row in events)
    has_decision = any(str(row.get("event_type")) == "decision" for row in events)
    is_rejected = any("reject" in str(status).lower() for status in statuses + reasons)
    has_order = bool(orders) or any(str(row.get("event_type")) == "order" for row in events)
    has_fill = any(_is_filled_order(row) for row in orders) or bool(trades)
    has_trade = bool(trades)
    has_pnl = any(int(row.get("is_closing_leg") or 0) == 1 and row.get("realized_pnl") is not None for row in trades)
    has_outcome = bool(outcomes)
    is_execution_path = has_order or has_trade or any(_status_implies_execution(status) for status in statuses)
    net_pnl = sum(_safe_float(row.get("realized_pnl")) for row in trades if int(row.get("is_closing_leg") or 0) == 1)
    outcome_labels = tuple(sorted({str(row.get("outcome_label")) for row in outcomes if row.get("outcome_label")}))
    missing = _missing_stages(
        has_signal=has_signal,
        has_decision=has_decision,
        is_rejected=is_rejected,
        is_execution_path=is_execution_path,
        has_order=has_order,
        has_fill=has_fill,
        has_trade=has_trade,
        has_pnl=has_pnl,
        has_outcome=has_outcome,
    )
    return DecisionTrace(
        trace_id=trace_id,
        decision_id=_first_text(all_rows, "decision_id"),
        signal_id=_first_text(all_rows, "signal_id"),
        symbol=_first_text(all_rows, "symbol"),
        strategy=_first_text(all_rows, "strategy"),
        engine=_first_text(all_rows, "engine"),
        first_seen_at=first,
        event_types=event_types,
        event_statuses=statuses,
        reasons=reasons,
        has_signal=has_signal,
        has_decision=has_decision,
        is_rejected=is_rejected,
        is_execution_path=is_execution_path,
        has_order=has_order,
        has_fill=has_fill,
        has_trade=has_trade,
        has_pnl=has_pnl,
        has_outcome=has_outcome,
        net_pnl_eur=net_pnl,
        outcome_labels=outcome_labels,
        missing_stages=missing,
        canonical_complete=not missing,
    )


def _missing_stages(
    *,
    has_signal: bool,
    has_decision: bool,
    is_rejected: bool,
    is_execution_path: bool,
    has_order: bool,
    has_fill: bool,
    has_trade: bool,
    has_pnl: bool,
    has_outcome: bool,
) -> tuple[str, ...]:
    missing: list[str] = []
    if not has_signal:
        missing.append("signal")
    if not has_decision:
        missing.append("decision")
    if is_rejected:
        if not has_outcome:
            missing.append("outcome")
    elif is_execution_path:
        if not has_order:
            missing.append("order")
        if not has_fill:
            missing.append("fill")
        if not has_trade:
            missing.append("trade")
        if not has_pnl:
            missing.append("pnl")
    elif has_decision:
        missing.append("terminal_status")
    return tuple(missing)


def _summary(traces: Sequence[DecisionTrace], *, orphan_orders: int, orphan_trades: int) -> DecisionTraceAuditSummary:
    missing = Counter(stage for trace in traces for stage in trace.missing_stages)
    event_types = Counter(event_type for trace in traces for event_type in trace.event_types)
    statuses = Counter(status for trace in traces for status in trace.event_statuses)
    rejected = [trace for trace in traces if trace.is_rejected]
    execution = [trace for trace in traces if trace.is_execution_path]
    complete = [trace for trace in traces if trace.canonical_complete]
    return DecisionTraceAuditSummary(
        trace_count=len(traces),
        canonical_complete_count=len(complete),
        canonical_complete_ratio=(len(complete) / len(traces) * 100.0) if traces else 0.0,
        signal_without_decision_count=sum(1 for trace in traces if trace.has_signal and not trace.has_decision),
        rejected_trace_count=len(rejected),
        rejected_with_outcome_count=sum(1 for trace in rejected if trace.has_outcome),
        execution_trace_count=len(execution),
        execution_complete_count=sum(1 for trace in execution if trace.canonical_complete),
        orphan_order_count=orphan_orders,
        orphan_trade_count=orphan_trades,
        total_net_pnl_eur=sum(trace.net_pnl_eur for trace in traces),
        missing_stage_counts=dict(missing),
        event_type_counts=dict(event_types),
        event_status_counts=dict(statuses),
    )


def _select_rows(
    conn: sqlite3.Connection,
    table: str,
    query: str,
    params: Sequence[Any],
    sources: dict[str, Any],
) -> list[dict[str, Any]]:
    if table not in _table_names(conn):
        sources["tables"][table] = {"status": "missing", "rows": 0}
        return []
    rows = [dict(row) for row in conn.execute(query, tuple(params))]
    sources["tables"][table] = {"status": "ok", "rows": len(rows)}
    return rows


def _read_only_conn(path: Path) -> sqlite3.Connection:
    uri = path.resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _table_names(conn: sqlite3.Connection) -> set[str]:
    return {str(row["name"]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _trace_keys(row: Mapping[str, Any]) -> tuple[str, ...]:
    keys: list[str] = []
    for key in (
        "decision_id",
        "signal_id",
        "client_order_id",
        "exchange_order_id",
        "position_id",
        "event_id",
        "trade_id",
        "outcome_id",
    ):
        value = row.get(key)
        if value not in (None, ""):
            keys.append(f"{key}:{value}")
    return tuple(dict.fromkeys(keys))


def _canonical_trace_id(keys: Iterable[str]) -> str:
    priority = {
        "decision_id": 0,
        "signal_id": 1,
        "client_order_id": 2,
        "exchange_order_id": 3,
        "position_id": 4,
        "event_id": 5,
        "trade_id": 6,
        "outcome_id": 7,
    }
    return sorted(keys, key=lambda key: (priority.get(key.split(":", 1)[0], 99), key))[0]


def _has_decision_or_signal_link(row: Mapping[str, Any]) -> bool:
    return any(row.get(key) not in (None, "") for key in ("decision_id", "signal_id"))


def _created_at(row: Mapping[str, Any]) -> str | None:
    value = row.get("created_at") or row.get("decision_created_at") or row.get("observed_at")
    return str(value) if value not in (None, "") else None


def _first_text(rows: Iterable[Mapping[str, Any]], key: str) -> str | None:
    for row in rows:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _is_filled_order(row: Mapping[str, Any]) -> bool:
    status = str(row.get("status") or "").lower()
    return "fill" in status or _safe_float(row.get("filled_qty")) > 0.0


def _status_implies_execution(status: str) -> bool:
    lowered = str(status or "").lower()
    return any(token in lowered for token in ("accept", "submit", "sent", "fill", "execute", "mirror"))


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


if __name__ == "__main__":
    raise SystemExit(main())
