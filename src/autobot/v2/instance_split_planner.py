"""Read-only instance split planning helpers.

The planner inspects persisted lineage and evidence, then delegates to
``InstanceSplitPolicy``. It never creates child instances by itself.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .instance_split_policy import InstanceSplitDecision, InstanceSplitEvidence, InstanceSplitPolicy


@dataclass(frozen=True)
class InstanceSplitPlan:
    run_id: str
    generated_at: str
    state_db_path: str | None
    decisions: tuple[InstanceSplitDecision, ...]
    json_report_path: str | None = None
    markdown_report_path: str | None = None
    safety_notes: tuple[str, ...] = (
        "Read-only split planning only.",
        "ENABLE_INSTANCE_SPLIT_EXECUTOR defaults to false.",
        "No instance is created by this planner.",
        "No paper or live order is created.",
        "No live trading permission is granted.",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "state_db_path": self.state_db_path,
            "decisions": [decision.to_dict() for decision in self.decisions],
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
            "safety_notes": list(self.safety_notes),
        }


def build_instance_split_plan(
    *,
    run_id: str,
    state_db_path: str | Path | None,
    parent_evidence: Sequence[Mapping[str, Any]],
    policy: InstanceSplitPolicy | None = None,
) -> InstanceSplitPlan:
    policy = policy or InstanceSplitPolicy()
    split_counts = load_parent_split_counts(state_db_path)
    decisions: list[InstanceSplitDecision] = []
    for item in parent_evidence:
        payload = dict(item)
        parent_id = str(payload.get("parent_instance_id") or payload.get("instance_id") or "")
        payload["parent_instance_id"] = parent_id
        payload.setdefault("parent_lifetime_split_count", split_counts.get(parent_id, 0))
        decisions.append(policy.evaluate(InstanceSplitEvidence(**_normalized_evidence_payload(payload))))
    return InstanceSplitPlan(
        run_id=run_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        state_db_path=str(state_db_path) if state_db_path else None,
        decisions=tuple(decisions),
    )


def load_parent_split_counts(state_db_path: str | Path | None) -> dict[str, int]:
    if state_db_path is None:
        return {}
    path = Path(state_db_path)
    if not path.exists():
        return {}
    try:
        with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as conn:
            if not _table_exists(conn, "instance_lineage"):
                return {}
            rows = conn.execute(
                """
                SELECT parent_instance_id, COUNT(*) AS child_count
                FROM instance_lineage
                GROUP BY parent_instance_id
                """
            ).fetchall()
    except sqlite3.Error:
        return {}
    return {str(parent_id): int(count) for parent_id, count in rows if parent_id}


def write_instance_split_plan(plan: InstanceSplitPlan, output_dir: str | Path) -> InstanceSplitPlan:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / f"{plan.run_id}.json"
    markdown_path = output_path / f"{plan.run_id}.md"
    json_path.write_text(json.dumps(plan.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(render_instance_split_plan(plan), encoding="utf-8")
    return InstanceSplitPlan(
        run_id=plan.run_id,
        generated_at=plan.generated_at,
        state_db_path=plan.state_db_path,
        decisions=plan.decisions,
        json_report_path=str(json_path),
        markdown_report_path=str(markdown_path),
        safety_notes=plan.safety_notes,
    )


def render_instance_split_plan(plan: InstanceSplitPlan) -> str:
    lines = [
        f"# Instance Split Plan - {plan.run_id}",
        "",
        f"Generated at: `{plan.generated_at}`",
        f"State DB: `{plan.state_db_path or 'not_configured'}`",
        "",
        "## Decisions",
        "",
        "| Parent | Status | Plan Allowed | Executable | Child Capital | Parent After | Blockers |",
        "| --- | --- | --- | --- | ---: | ---: | --- |",
    ]
    for decision in plan.decisions:
        evidence = dict(decision.evidence)
        lines.append(
            f"| {evidence.get('parent_instance_id') or '-'} | {decision.status} | "
            f"{'yes' if decision.allowed_to_plan else 'no'} | {'yes' if decision.executable_now else 'no'} | "
            f"{decision.planned_child_capital_eur:.2f} | {decision.parent_capital_after_eur:.2f} | "
            f"{', '.join(decision.blockers) or 'none'} |"
        )
    lines.extend(["", "## Safety", ""])
    lines.extend(f"- {note}" for note in plan.safety_notes)
    lines.append("")
    return "\n".join(lines)


def _normalized_evidence_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {
        "parent_instance_id",
        "parent_capital_eur",
        "parent_available_eur",
        "parent_lifetime_split_count",
        "paper_mode",
        "strategy_id",
        "strategy_status",
        "net_pnl_eur",
        "profit_factor",
        "trade_count",
        "validation_days",
        "max_drawdown_pct",
        "strategy_scorecard",
        "dominant_failure_mode",
        "official_paper_net_pnl_eur",
        "live_promotion_allowed",
        "metadata",
    }
    return {key: payload[key] for key in allowed if key in payload}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None
