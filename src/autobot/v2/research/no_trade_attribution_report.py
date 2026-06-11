"""Read-only attribution report for non-executed AUTOBOT decisions."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class NoTradeAttributionReport:
    run_id: str
    generated_at: str
    state_db_path: str
    total_decisions: int
    counts: dict[str, int]
    top_symbols: tuple[tuple[str, int], ...]
    top_strategies: tuple[tuple[str, int], ...]
    top_reasons: tuple[tuple[str, int], ...]
    hourly_counts: tuple[tuple[str, int], ...]
    last_persisted_at: str | None
    log_comparison: dict[str, Any]
    json_report_path: str | None = None
    markdown_report_path: str | None = None
    live_promotion_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_no_trade_attribution_report(
    *, state_db_path: str | Path, run_id: str, log_path: str | Path | None = None
) -> NoTradeAttributionReport:
    path = Path(state_db_path)
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT symbol, strategy, event_type, event_status, reason, created_at "
            "FROM decision_ledger ORDER BY created_at ASC, id ASC"
        ).fetchall()
    finally:
        connection.close()

    category_counts: Counter[str] = Counter()
    symbols: Counter[str] = Counter()
    strategies: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    hours: Counter[str] = Counter()
    for row in rows:
        event_type = str(row["event_type"] or "").lower()
        event_status = str(row["event_status"] or "").lower()
        reason = str(row["reason"] or "unknown")
        reason_lower = reason.lower()
        categories = _categories(event_type, event_status, reason_lower)
        if not categories:
            continue
        for category in categories:
            category_counts[category] += 1
        symbols[str(row["symbol"] or "UNKNOWN")] += 1
        strategies[str(row["strategy"] or "UNKNOWN")] += 1
        reasons[reason] += 1
        created_at = str(row["created_at"] or "")
        hours[created_at[:13] or "unknown"] += 1

    return NoTradeAttributionReport(
        run_id=run_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        state_db_path=str(path),
        total_decisions=len(rows),
        counts={key: category_counts.get(key, 0) for key in (
            "no_trade", "abstain", "governance_block", "cost_guard",
            "microstructure_filter", "router_selected_no_trade",
        )},
        top_symbols=tuple(symbols.most_common(20)),
        top_strategies=tuple(strategies.most_common(20)),
        top_reasons=tuple(reasons.most_common(20)),
        hourly_counts=tuple(sorted(hours.items())),
        last_persisted_at=str(rows[-1]["created_at"]) if rows else None,
        log_comparison=_compare_log(log_path),
    )


def write_no_trade_attribution_report(
    report: NoTradeAttributionReport, output_dir: str | Path
) -> NoTradeAttributionReport:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / f"{report.run_id}.json"
    markdown_path = output / f"{report.run_id}.md"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(render_no_trade_attribution_report(report), encoding="utf-8")
    return replace(report, json_report_path=str(json_path), markdown_report_path=str(markdown_path))


def render_no_trade_attribution_report(report: NoTradeAttributionReport) -> str:
    lines = [
        f"# No-Trade Attribution - {report.run_id}", "", "## Summary", "",
        f"- Total decision ledger rows: `{report.total_decisions}`",
        f"- Last persisted decision: `{report.last_persisted_at or 'none'}`",
    ]
    for key, value in report.counts.items():
        lines.append(f"- {key}: `{value}`")
    for title, rows in (("Top Symbols", report.top_symbols), ("Top Strategies", report.top_strategies), ("Top Reasons", report.top_reasons)):
        lines.extend(["", f"## {title}", "", "| Value | Count |", "| --- | ---: |"])
        lines.extend(f"| {value} | {count} |" for value, count in rows)
        if not rows:
            lines.append("| none | 0 |")
    lines.extend(["", "## Hourly Evolution", "", "| UTC Hour | Count |", "| --- | ---: |"])
    lines.extend(f"| {hour} | {count} |" for hour, count in report.hourly_counts)
    lines.extend(["", "## Log Comparison", ""])
    if report.log_comparison.get("available"):
        lines.extend(
            f"- {key}: `{value}`"
            for key, value in report.log_comparison.items()
            if key not in {"available", "path"}
        )
        lines.append(f"- log_path: `{report.log_comparison.get('path')}`")
    else:
        lines.append(f"- unavailable: `{report.log_comparison.get('reason', 'unknown')}`")
    lines.extend(["", "## Safety", "", "Read-only report. No order, promotion, sizing or live flag is modified."])
    return "\n".join(lines) + "\n"


def _categories(event_type: str, event_status: str, reason: str) -> set[str]:
    text = " ".join((event_type, event_status, reason))
    result: set[str] = set()
    if "no_trade" in text:
        result.add("no_trade")
    if "abstain" in text:
        result.add("abstain")
    if "governance" in text or "router_selected_no_trade" in text:
        result.add("governance_block")
    if "cost_guard" in text:
        result.add("cost_guard")
    if "microstructure" in text:
        result.add("microstructure_filter")
    if "router_selected_no_trade" in text:
        result.add("router_selected_no_trade")
    return result


def _compare_log(log_path: str | Path | None) -> dict[str, Any]:
    if log_path is None:
        return {"available": False, "reason": "log_path_not_provided"}
    path = Path(log_path)
    if not path.exists():
        return {"available": False, "reason": "log_path_missing", "path": str(path)}
    text = path.read_text(encoding="utf-8", errors="replace").lower()
    return {
        "available": True,
        "path": str(path),
        "router_selected_no_trade": text.count("router_selected_no_trade"),
        "governance_block": text.count("strategy governance gate"),
        "cost_guard": text.count("cost_guard"),
        "microstructure_filter": text.count("microstructure"),
    }
