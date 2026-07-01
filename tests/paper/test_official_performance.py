import json
import sqlite3

import pytest

from autobot.v2.paper.official_performance import (
    OfficialPaperPerformanceConfig,
    build_official_paper_performance_report,
)


pytestmark = pytest.mark.unit


def _strategy_entry(strategy_id: str, status: str = "shadow_passed") -> dict:
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


def _write_registry(path):
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
            _strategy_entry("trend_momentum", "shadow_passed"),
            _strategy_entry("mean_reversion", "learning"),
            _strategy_entry("dynamic_grid", "retired_from_execution"),
            _strategy_entry("no_trade_baseline", "paper_validated"),
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _create_state_db(path):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE trade_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id TEXT NOT NULL,
                position_id TEXT,
                instance_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                expected_price REAL,
                executed_price REAL NOT NULL,
                volume REAL NOT NULL,
                fees REAL DEFAULT 0,
                slippage_bps REAL,
                realized_pnl REAL,
                is_opening_leg INTEGER DEFAULT 0,
                is_closing_leg INTEGER DEFAULT 0,
                exchange_order_id TEXT,
                decision_id TEXT,
                signal_id TEXT,
                strategy_id TEXT,
                timeframe TEXT,
                signal_source TEXT,
                gross_pnl REAL,
                net_pnl REAL,
                regime TEXT,
                execution_liquidity TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        rows = [
            ("legacy", None, "inst", "TRXEUR", "sell", 1.10, 1.10, 100.0, 0.2, 2.0, 99.0, 0, 1, None, None, None, None, None, None, 99.2, 99.0, "range", "taker", "2026-07-01T00:00:00+00:00"),
            ("open1", "pos1", "inst", "TRXEUR", "buy", 1.00, 1.00, 100.0, 0.1, 1.0, None, 1, 0, None, None, None, "trend_momentum", "5m", "pytest", None, None, "range", "taker", "2026-07-01T01:00:00+00:00"),
            ("close1", "pos1", "inst", "TRXEUR", "sell", 1.10, 1.10, 100.0, 0.3, 2.0, 10.0, 0, 1, None, None, None, "trend_momentum", "5m", "pytest", 10.4, 10.0, "range", "taker", "2026-07-01T02:00:00+00:00"),
            ("open2", "pos2", "inst", "XLMEUR", "buy", 1.00, 1.00, 100.0, 0.1, 1.0, None, 1, 0, None, None, None, "trend_momentum", "15m", "pytest", None, None, "trend", "taker", "2026-07-01T03:00:00+00:00"),
            ("close2", "pos2", "inst", "XLMEUR", "sell", 0.96, 0.96, 100.0, 0.3, 2.0, -4.0, 0, 1, None, None, None, "trend_momentum", "15m", "pytest", -3.6, -4.0, "trend", "taker", "2026-07-01T04:00:00+00:00"),
            ("unknown", "pos3", "inst", "ADAEUR", "sell", 1.05, 1.05, 10.0, 0.2, 1.0, 1.0, 0, 1, None, None, None, "unregistered_alpha", "5m", "pytest", 1.2, 1.0, "range", "taker", "2026-07-01T05:00:00+00:00"),
            ("grid", "pos4", "inst", "BTCEUR", "sell", 100.0, 100.0, 1.0, 0.2, 1.0, 1.0, 0, 1, None, None, None, "dynamic_grid", "5m", "pytest", 1.2, 1.0, "range", "taker", "2026-07-01T06:00:00+00:00"),
        ]
        conn.executemany(
            """
            INSERT INTO trade_ledger
            (trade_id, position_id, instance_id, symbol, side, expected_price, executed_price,
             volume, fees, slippage_bps, realized_pnl, is_opening_leg, is_closing_leg,
             exchange_order_id, decision_id, signal_id, strategy_id, timeframe, signal_source,
             gross_pnl, net_pnl, regime, execution_liquidity, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )


def test_official_paper_summary_excludes_legacy_and_retired_grid(tmp_path):
    state_db = tmp_path / "state.db"
    registry = tmp_path / "strategy_hypotheses.json"
    _create_state_db(state_db)
    _write_registry(registry)

    report = build_official_paper_performance_report(
        OfficialPaperPerformanceConfig(
            state_db_path=state_db,
            registry_path=registry,
            initial_capital_eur=500.0,
            run_id="pytest_p1",
        ),
        write_report=False,
    )
    payload = report.to_dict()

    assert payload["legacy"]["legacy_unattributed_trade_count"] == 1
    assert payload["legacy"]["non_official_excluded_trade_count"] == 2
    assert payload["legacy"]["official_attributed_trade_count"] == 3
    trend = next(item for item in payload["ranking"] if item["strategy_id"] == "trend_momentum")
    assert trend["metrics"]["closed_trade_count"] == 2
    assert trend["metrics"]["profit_factor"] == pytest.approx(2.5)
    assert trend["metrics"]["expectancy_eur"] == pytest.approx(3.0)
    assert trend["metrics"]["fees_eur"] == pytest.approx(0.8)
    assert trend["metrics"]["slippage_eur"] > 0.0
    assert trend["metrics"]["fees_included"] is True
    assert trend["metrics"]["slippage_included"] is True
    assert trend["promotable"] is False

    keys = [bucket["key"] for bucket in payload["by_strategy_symbol_timeframe_regime"]]
    assert {
        "strategy_id": "trend_momentum",
        "symbol": "TRXEUR",
        "timeframe": "5m",
        "regime": "range",
    } in keys
    grid = next(item for item in payload["ranking"] if item["strategy_id"] == "dynamic_grid")
    assert grid["decision"] == "disabled"
    assert grid["metrics"]["closed_trade_count"] == 0


def test_official_paper_summary_blocks_unregistered_and_keeps_no_trade_as_reference(tmp_path):
    state_db = tmp_path / "state.db"
    registry = tmp_path / "strategy_hypotheses.json"
    _create_state_db(state_db)
    _write_registry(registry)

    report = build_official_paper_performance_report(
        OfficialPaperPerformanceConfig(
            state_db_path=state_db,
            registry_path=registry,
            run_id="pytest_p1",
        ),
        write_report=False,
    ).to_dict()

    unknown = next(item for item in report["ranking"] if item["strategy_id"] == "unregistered_alpha")
    assert unknown["decision"] == "blocked"
    assert unknown["reason"] == "strategy_not_in_registry"
    assert report["baseline"]["strategy_id"] == "no_trade_baseline"
    assert report["baseline"]["status"] == "reference_only"
    assert report["baseline"]["promotable"] is False
    assert all(item["promotable"] is False for item in report["ranking"])
