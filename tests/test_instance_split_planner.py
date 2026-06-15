import sqlite3

import pytest

from autobot.v2.instance_split_planner import build_instance_split_plan, write_instance_split_plan


pytestmark = pytest.mark.unit


def _evidence(**overrides):
    payload = {
        "parent_instance_id": "parent_1",
        "strategy_id": "dynamic_grid",
        "strategy_status": "paper_validated",
        "paper_mode": True,
        "live_promotion_allowed": False,
        "parent_capital_eur": 4000.0,
        "parent_available_eur": 2000.0,
        "net_pnl_eur": 50.0,
        "official_paper_net_pnl_eur": 50.0,
        "profit_factor": 1.5,
        "trade_count": 150,
        "validation_days": 10,
        "max_drawdown_pct": 6.0,
        "strategy_scorecard": 82.0,
        "dominant_failure_mode": "healthy",
    }
    payload.update(overrides)
    return payload


def _lineage_db(path):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE instance_lineage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_instance_id TEXT,
                child_instance_id TEXT,
                created_at TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO instance_lineage (parent_instance_id, child_instance_id, created_at)
            VALUES (?, ?, ?)
            """,
            ("parent_1", "child_1", "2026-06-01T00:00:00+00:00"),
        )


def test_split_planner_uses_persistent_lineage_to_block_second_split(tmp_path):
    state_db = tmp_path / "state.db"
    _lineage_db(state_db)

    plan = build_instance_split_plan(
        run_id="pytest_split_plan",
        state_db_path=state_db,
        parent_evidence=(_evidence(),),
    )

    assert len(plan.decisions) == 1
    assert sum(1 for decision in plan.decisions if decision.allowed_to_plan) == 0
    assert plan.decisions[0].allowed_to_plan is False
    assert "parent_already_split" in plan.decisions[0].blockers


def test_split_planner_writes_report_and_keeps_executor_off(tmp_path):
    plan = build_instance_split_plan(
        run_id="pytest_split_plan_report",
        state_db_path=tmp_path / "missing.db",
        parent_evidence=(_evidence(),),
    )
    written = write_instance_split_plan(plan, tmp_path / "reports")

    assert sum(1 for decision in plan.decisions if decision.executable_now) == 0
    assert sum(1 for decision in plan.decisions if decision.live_promotion_allowed) == 0
    assert "ENABLE_INSTANCE_SPLIT_EXECUTOR defaults to false." in plan.safety_notes
    assert (tmp_path / "reports" / "pytest_split_plan_report.md").exists()
    assert (tmp_path / "reports" / "pytest_split_plan_report.json").exists()
    assert written.markdown_report_path
