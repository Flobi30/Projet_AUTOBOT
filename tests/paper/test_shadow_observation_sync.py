import json
import sqlite3
from pathlib import Path

import pytest

from autobot.v2 import cli
from autobot.v2.paper.official_performance import (
    OfficialPaperPerformanceConfig,
    build_official_paper_performance_report,
)
from autobot.v2.paper.shadow_observation_sync import (
    ShadowPaperObservationSyncConfig,
    sync_shadow_paper_observations,
)
from autobot.v2.strategy_runtime_policy import (
    EXECUTION_MODE_SHADOW_PAPER,
    shadow_paper_strategy_block_reason,
    trade_ledger_append_block_reason,
)


pytestmark = pytest.mark.unit


def _strategy_entry(strategy_id: str, status: str = "learning") -> dict:
    return {
        "strategy_id": strategy_id,
        "family": strategy_id,
        "hypothesis": "pytest",
        "market": "spot_crypto",
        "timeframe": "5m",
        "required_data": ["ohlcv"],
        "entry_logic": "pytest",
        "exit_logic": "pytest",
        "risk_model": "pytest",
        "fees_model": {"profile": "paper_current_taker"},
        "slippage_model": {"profile": "paper_current_taker"},
        "expected_market_regime": "range",
        "failure_modes": ["insufficient_edge"],
        "baseline_comparison": {"no_trade": "required"},
        "validation_status": status,
        "last_backtest_id": None,
        "paper_status": "shadow_only",
        "decision": "continue_testing",
        "decision_reason": "pytest",
    }


def _write_registry(path: Path) -> None:
    payload = {
        "decision_statuses": [
            "learning",
            "candidate",
            "backtest_passed",
            "walk_forward_passed",
            "shadow_passed",
            "paper_validated",
            "rejected",
            "retired_from_execution",
        ],
        "live_auto_promotion_allowed": False,
        "hypotheses": [
            _strategy_entry("trend_momentum", "learning"),
            _strategy_entry("mean_reversion", "learning"),
            _strategy_entry("high_conviction_swing", "learning"),
            _strategy_entry("opportunity_scoring", "learning"),
            _strategy_entry("dynamic_grid", "retired_from_execution"),
            _strategy_entry("no_trade_baseline", "paper_validated"),
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_shadow_db(path: Path, table: str) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            f"""
            CREATE TABLE {table} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                variant TEXT NOT NULL,
                position_id TEXT NOT NULL,
                entry_price REAL NOT NULL,
                exit_price REAL NOT NULL,
                volume REAL NOT NULL,
                notional REAL NOT NULL,
                fees REAL NOT NULL,
                realized_pnl REAL NOT NULL,
                reason TEXT NOT NULL,
                opened_at TEXT NOT NULL,
                closed_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            f"""
            INSERT INTO {table}
            (symbol, variant, position_id, entry_price, exit_price, volume,
             notional, fees, realized_pnl, reason, opened_at, closed_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "TRXEUR",
                "balanced",
                "shadow_pos_1",
                1.00,
                1.08,
                100.0,
                100.0,
                1.50,
                6.50,
                "take_profit",
                "2026-07-01T01:00:00+00:00",
                "2026-07-01T03:00:00+00:00",
                "2026-07-01T03:00:01+00:00",
            ),
        )


def test_learning_strategy_can_write_shadow_paper_observation_with_strategy_id(tmp_path):
    state_db = tmp_path / "state.db"
    registry = tmp_path / "strategy_hypotheses.json"
    trend_db = tmp_path / "trend_shadow_lab.db"
    mean_db = tmp_path / "mean_reversion_shadow_lab.db"
    _write_registry(registry)
    _write_shadow_db(trend_db, "trend_shadow_trades")

    report = sync_shadow_paper_observations(
        ShadowPaperObservationSyncConfig(
            state_db_path=state_db,
            registry_path=registry,
            trend_shadow_db_path=trend_db,
            mean_reversion_shadow_db_path=mean_db,
            output_dir=tmp_path / "reports",
            run_id="pytest_shadow_sync",
        )
    ).to_dict()

    trend = next(item for item in report["source_results"] if item["strategy_id"] == "trend_momentum")
    assert trend["inserted_trade_count"] == 1
    assert trend["duplicate_trade_count"] == 0

    with sqlite3.connect(state_db) as conn:
        rows = conn.execute(
            """
            SELECT strategy_id, execution_mode, is_opening_leg, is_closing_leg, net_pnl, gross_pnl
            FROM trade_ledger
            ORDER BY id ASC
            """
        ).fetchall()
    assert len(rows) == 2
    assert {row[0] for row in rows} == {"trend_momentum"}
    assert {row[1] for row in rows} == {EXECUTION_MODE_SHADOW_PAPER}
    assert rows[-1][3] == 1
    assert rows[-1][4] == pytest.approx(6.50)
    assert rows[-1][5] == pytest.approx(8.00)


def test_shadow_sync_is_idempotent_and_does_not_duplicate_ledger_rows(tmp_path):
    state_db = tmp_path / "state.db"
    registry = tmp_path / "strategy_hypotheses.json"
    trend_db = tmp_path / "trend_shadow_lab.db"
    _write_registry(registry)
    _write_shadow_db(trend_db, "trend_shadow_trades")

    config = ShadowPaperObservationSyncConfig(
        state_db_path=state_db,
        registry_path=registry,
        trend_shadow_db_path=trend_db,
        mean_reversion_shadow_db_path=tmp_path / "missing_mean.db",
        run_id="pytest_shadow_sync",
        output_dir=tmp_path / "reports",
    )
    sync_shadow_paper_observations(config)
    second = sync_shadow_paper_observations(config).to_dict()

    trend = next(item for item in second["source_results"] if item["strategy_id"] == "trend_momentum")
    assert trend["inserted_trade_count"] == 0
    assert trend["duplicate_trade_count"] == 1
    with sqlite3.connect(state_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM trade_ledger").fetchone()[0] == 2


def test_learning_shadow_observations_are_not_promotable_paper_capital(tmp_path):
    state_db = tmp_path / "state.db"
    registry = tmp_path / "strategy_hypotheses.json"
    trend_db = tmp_path / "trend_shadow_lab.db"
    _write_registry(registry)
    _write_shadow_db(trend_db, "trend_shadow_trades")
    sync_shadow_paper_observations(
        ShadowPaperObservationSyncConfig(
            state_db_path=state_db,
            registry_path=registry,
            trend_shadow_db_path=trend_db,
            mean_reversion_shadow_db_path=tmp_path / "missing_mean.db",
            run_id="pytest_shadow_sync",
            output_dir=tmp_path / "reports",
        )
    )

    assert (
        trade_ledger_append_block_reason("trend_momentum", execution_mode="paper_capital")
        == "paper_capital_requires_promotion_gate"
    )
    summary = build_official_paper_performance_report(
        OfficialPaperPerformanceConfig(
            state_db_path=state_db,
            registry_path=registry,
            run_id="pytest_summary",
        ),
        write_report=False,
    ).to_dict()
    trend = next(item for item in summary["ranking"] if item["strategy_id"] == "trend_momentum")
    assert trend["decision"] == "keep_observing"
    assert trend["promotable"] is False
    assert trend["paper_capital_metrics"]["closed_trade_count"] == 0
    assert trend["shadow_paper_metrics"]["closed_trade_count"] == 1
    assert summary["legacy"]["shadow_paper_trade_count"] == 1
    assert summary["legacy"]["paper_capital_trade_count"] == 0


def test_rejected_retired_and_grid_strategies_cannot_write_shadow_paper():
    assert shadow_paper_strategy_block_reason("dynamic_grid") == "grid_retired_research_only"
    assert shadow_paper_strategy_block_reason("grid") == "grid_retired_research_only"
    assert shadow_paper_strategy_block_reason("relative_value") == "shadow_paper_strategy_not_allowed"


def test_metrics_distinguish_shadow_paper_and_paper_capital(tmp_path):
    state_db = tmp_path / "state.db"
    registry = tmp_path / "strategy_hypotheses.json"
    trend_db = tmp_path / "trend_shadow_lab.db"
    _write_registry(registry)
    _write_shadow_db(trend_db, "trend_shadow_trades")
    sync_shadow_paper_observations(
        ShadowPaperObservationSyncConfig(
            state_db_path=state_db,
            registry_path=registry,
            trend_shadow_db_path=trend_db,
            mean_reversion_shadow_db_path=tmp_path / "missing_mean.db",
            run_id="pytest_shadow_sync",
            output_dir=tmp_path / "reports",
        )
    )
    with sqlite3.connect(state_db) as conn:
        conn.execute(
            """
            INSERT INTO trade_ledger
            (trade_id, position_id, instance_id, symbol, side, expected_price, executed_price,
             volume, fees, slippage_bps, realized_pnl, is_opening_leg, is_closing_leg,
             strategy_id, timeframe, signal_source, gross_pnl, net_pnl, regime,
             execution_liquidity, execution_mode, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "paper_close",
                "paper_pos",
                "inst",
                "XLMEUR",
                "sell",
                1.10,
                1.10,
                10.0,
                0.2,
                1.0,
                0.8,
                0,
                1,
                "trend_momentum",
                "5m",
                "pytest",
                1.0,
                0.8,
                "trend",
                "taker",
                "paper_capital",
                "2026-07-01T04:00:00+00:00",
            ),
        )

    summary = build_official_paper_performance_report(
        OfficialPaperPerformanceConfig(
            state_db_path=state_db,
            registry_path=registry,
            run_id="pytest_summary",
        ),
        write_report=False,
    ).to_dict()
    by_mode = {bucket["key"]["execution_mode"]: bucket for bucket in summary["by_strategy_execution_mode"]}
    assert by_mode["shadow_paper"]["metrics"]["closed_trade_count"] == 1
    assert by_mode["paper_capital"]["metrics"]["closed_trade_count"] == 1
    trend = next(item for item in summary["ranking"] if item["strategy_id"] == "trend_momentum")
    assert trend["metrics"]["closed_trade_count"] == 2
    assert trend["shadow_paper_metrics"]["closed_trade_count"] == 1
    assert trend["paper_capital_metrics"]["closed_trade_count"] == 1


def test_cli_shadow_paper_observations_syncs_and_reports(tmp_path, capsys):
    state_db = tmp_path / "state.db"
    registry = tmp_path / "strategy_hypotheses.json"
    trend_db = tmp_path / "trend_shadow_lab.db"
    output_dir = tmp_path / "shadow_reports"
    _write_registry(registry)
    _write_shadow_db(trend_db, "trend_shadow_trades")

    exit_code = cli.main(
        [
            "shadow-paper-observations",
            "--state-db",
            str(state_db),
            "--registry-path",
            str(registry),
            "--trend-shadow-db",
            str(trend_db),
            "--mean-reversion-shadow-db",
            str(tmp_path / "missing_mean.db"),
            "--run-id",
            "pytest_cli_shadow",
            "--output-dir",
            str(output_dir),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["execution_mode"] == "shadow_paper"
    trend = next(item for item in payload["source_results"] if item["strategy_id"] == "trend_momentum")
    assert trend["inserted_trade_count"] == 1
    assert (output_dir / "pytest_cli_shadow.md").exists()
