"""Isolated paper-only validation harness for instance split mechanics.

This module never starts AUTOBOT runtime services and never creates an order.
It validates capital transfer, child isolation, durable lineage and the
single-split lifetime rule with an isolated SQLite database.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from autobot.v2.instance_split_policy import (
    InstanceSplitEvidence,
    InstanceSplitPolicy,
    InstanceSplitPolicyConfig,
)


@dataclass
class SimulatedInstanceAccount:
    instance_id: str
    initial_capital_eur: float
    current_capital_eur: float

    def apply_return(self, return_ratio: float) -> None:
        self.current_capital_eur *= 1.0 + float(return_ratio)


@dataclass(frozen=True)
class InstanceSplitValidationResult:
    run_id: str
    generated_at: str
    status: str
    first_decision: Mapping[str, Any]
    second_decision: Mapping[str, Any] | None
    checks: Mapping[str, bool]
    parent: Mapping[str, Any]
    child: Mapping[str, Any] | None
    lineage_db_path: str
    json_report_path: str | None = None
    markdown_report_path: str | None = None
    safety_notes: tuple[str, ...] = (
        "Research-only mechanics validation.",
        "No AUTOBOT runtime service is started.",
        "No Kraken endpoint or credential is used.",
        "No paper or live order is created.",
        "No live promotion permission is granted.",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "status": self.status,
            "first_decision": dict(self.first_decision),
            "second_decision": dict(self.second_decision) if self.second_decision else None,
            "checks": dict(self.checks),
            "parent": dict(self.parent),
            "child": dict(self.child) if self.child else None,
            "lineage_db_path": self.lineage_db_path,
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
            "safety_notes": list(self.safety_notes),
        }


def run_instance_split_validation(
    *,
    run_id: str,
    evidence: InstanceSplitEvidence | Mapping[str, Any],
    output_dir: str | Path,
    child_return_series: Sequence[float] = (0.01, -0.004, 0.006),
) -> InstanceSplitValidationResult:
    """Validate automatic split mechanics in a fully isolated sandbox."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    lineage_db_path = output_path / f"{run_id}_lineage.db"
    if lineage_db_path.exists():
        lineage_db_path.unlink()

    ev = evidence if isinstance(evidence, InstanceSplitEvidence) else InstanceSplitEvidence(**dict(evidence))
    sandbox_config = replace(InstanceSplitPolicyConfig(), executor_enabled=True)
    policy = InstanceSplitPolicy(sandbox_config)
    first = policy.evaluate(ev)

    parent = SimulatedInstanceAccount(
        instance_id=ev.parent_instance_id,
        initial_capital_eur=float(ev.parent_capital_eur),
        current_capital_eur=float(ev.parent_capital_eur),
    )
    child: SimulatedInstanceAccount | None = None
    second = None
    checks: dict[str, bool] = {
        "first_split_policy_passed": first.executable_now,
        "paper_mode_only": bool(ev.paper_mode),
        "live_promotion_disabled": not first.live_promotion_allowed,
        "no_order_path": True,
    }

    if first.executable_now:
        child_capital = float(first.planned_child_capital_eur)
        parent.current_capital_eur -= child_capital
        child = SimulatedInstanceAccount(
            instance_id=f"{ev.parent_instance_id}-child-1",
            initial_capital_eur=child_capital,
            current_capital_eur=child_capital,
        )
        total_after_transfer = parent.current_capital_eur + child.current_capital_eur
        checks["capital_conserved_at_split"] = _close(total_after_transfer, ev.parent_capital_eur)

        parent_after_transfer = parent.current_capital_eur
        for item in child_return_series:
            child.apply_return(float(item))
        checks["child_state_changes_independently"] = (
            not _close(child.current_capital_eur, child.initial_capital_eur)
            and _close(parent.current_capital_eur, parent_after_transfer)
        )

        _record_lineage(
            lineage_db_path,
            parent_instance_id=parent.instance_id,
            child_instance_id=child.instance_id,
            child_capital_eur=child.initial_capital_eur,
        )
        persistent_count = _parent_split_count(lineage_db_path, parent.instance_id)
        checks["lineage_persisted"] = persistent_count == 1
        second_evidence = replace(ev, parent_lifetime_split_count=persistent_count)
        second = policy.evaluate(second_evidence)
        checks["second_split_blocked_for_lifetime"] = (
            not second.executable_now and "parent_already_split" in second.blockers
        )
    else:
        checks.update(
            {
                "capital_conserved_at_split": False,
                "child_state_changes_independently": False,
                "lineage_persisted": False,
                "second_split_blocked_for_lifetime": False,
            }
        )

    status = "PASS" if all(checks.values()) else "FAIL"
    result = InstanceSplitValidationResult(
        run_id=run_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        status=status,
        first_decision=first.to_dict(),
        second_decision=second.to_dict() if second else None,
        checks=checks,
        parent=asdict(parent),
        child=asdict(child) if child else None,
        lineage_db_path=str(lineage_db_path),
    )
    return write_instance_split_validation_result(result, output_path)


def write_instance_split_validation_result(
    result: InstanceSplitValidationResult,
    output_dir: str | Path,
) -> InstanceSplitValidationResult:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / f"{result.run_id}.json"
    markdown_path = output_path / f"{result.run_id}.md"
    final_result = replace(
        result,
        json_report_path=str(json_path),
        markdown_report_path=str(markdown_path),
    )
    json_path.write_text(
        json.dumps(final_result.to_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    markdown_path.write_text(_render_markdown(final_result), encoding="utf-8")
    return final_result


def _record_lineage(
    path: Path,
    *,
    parent_instance_id: str,
    child_instance_id: str,
    child_capital_eur: float,
) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS instance_lineage (
                child_instance_id TEXT PRIMARY KEY,
                parent_instance_id TEXT NOT NULL,
                child_capital REAL NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO instance_lineage
            (child_instance_id, parent_instance_id, child_capital, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                child_instance_id,
                parent_instance_id,
                float(child_capital_eur),
                datetime.now(timezone.utc).isoformat(),
            ),
        )


def _parent_split_count(path: Path, parent_instance_id: str) -> int:
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM instance_lineage WHERE parent_instance_id = ?",
            (parent_instance_id,),
        ).fetchone()
    return int(row[0] if row else 0)


def _render_markdown(result: InstanceSplitValidationResult) -> str:
    lines = [
        f"# Instance Split Validation - {result.run_id}",
        "",
        f"Verdict: **{result.status}**",
        f"Generated at: `{result.generated_at}`",
        "",
        "## Mechanical checks",
        "",
    ]
    lines.extend(
        f"- {'PASS' if passed else 'FAIL'}: `{name}`"
        for name, passed in result.checks.items()
    )
    lines.extend(
        [
            "",
            "## Result",
            "",
            f"- Parent: `{result.parent}`",
            f"- Child: `{result.child}`",
            f"- First decision: `{dict(result.first_decision)}`",
            f"- Second decision: `{dict(result.second_decision) if result.second_decision else None}`",
            "",
            "## Safety",
            "",
        ]
    )
    lines.extend(f"- {note}" for note in result.safety_notes)
    lines.append("")
    return "\n".join(lines)


def _close(left: float, right: float, tolerance: float = 1e-9) -> bool:
    return abs(float(left) - float(right)) <= tolerance
