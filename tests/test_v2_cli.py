import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from autobot.v2 import cli
from autobot.v2.research.experiment_registry import ExperimentRegistry, ExperimentSpec
from autobot.v2.research.research_memory_store import ResearchMemoryStore
from autobot.v2.research.trade_journal import TradeJournal, TradeRecord


pytestmark = pytest.mark.integration


def _write_grid_csv(path):
    path.write_text(
        "\n".join(
            [
                "timestamp,symbol,timeframe,open,high,low,close,volume",
                "2026-06-03T00:00:00+00:00,TRXEUR,1m,100,101,99,100,1000",
                "2026-06-03T00:01:00+00:00,TRXEUR,1m,99.05,100,98,99.05,1000",
                "2026-06-03T00:02:00+00:00,TRXEUR,1m,99.60,100,98,99.60,1000",
                "2026-06-03T00:03:00+00:00,TRXEUR,1m,100.20,101,99,100.20,1000",
            ]
        ),
        encoding="utf-8",
    )


def _write_symbols_csv(path, symbols):
    lines = ["timestamp,symbol,timeframe,open,high,low,close,volume"]
    for symbol in symbols:
        lines.extend(
            [
                f"2026-06-03T00:00:00+00:00,{symbol},1m,100,101,99,100,1000",
                f"2026-06-03T00:01:00+00:00,{symbol},1m,99.05,100,98,99.05,1000",
                f"2026-06-03T00:02:00+00:00,{symbol},1m,99.60,100,98,99.60,1000",
                f"2026-06-03T00:03:00+00:00,{symbol},1m,100.20,101,99,100.20,1000",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def _trade_journal(path):
    opened = datetime(2026, 6, 3, 9, tzinfo=timezone.utc)
    closed = datetime(2026, 6, 3, 10, tzinfo=timezone.utc)
    journal = TradeJournal(
        [
            TradeRecord(
                run_id="paper_cli",
                strategy_id="trend_momentum",
                symbol="TRXEUR",
                side="buy",
                opened_at=opened,
                closed_at=closed,
                quantity=10.0,
                entry_price=1.0,
                exit_price=1.2,
                gross_pnl_eur=2.0,
                net_pnl_eur=1.2,
                fees_eur=0.4,
                spread_cost_eur=0.2,
                slippage_eur=0.2,
                entry_reason="pytest_entry",
                exit_reason="pytest_exit",
            )
        ]
    )
    journal.to_json(path)


def _write_strategy_registry(path):
    entry = {
        "strategy_id": "trend_momentum",
        "hypothesis": "pytest",
        "market": "spot_crypto",
        "timeframe": "5m",
        "required_data": ["ohlcv"],
        "entry_logic": "pytest",
        "exit_logic": "pytest",
        "risk_model": "pytest",
        "fees_model": {"profile": "paper_current_taker"},
        "slippage_model": {"profile": "paper_current_taker"},
        "expected_market_regime": "trend",
        "failure_modes": ["insufficient_edge"],
        "baseline_comparison": {"no_trade": "required"},
        "validation_status": "shadow_passed",
        "last_backtest_id": None,
        "paper_status": "shadow_only",
        "decision": "continue_testing",
        "decision_reason": "pytest",
    }
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
        "hypotheses": [entry],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _state_db_with_closed_trade(path):
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
                execution_liquidity TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE decision_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                decision_id TEXT,
                signal_id TEXT,
                instance_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                strategy TEXT,
                engine TEXT,
                event_type TEXT NOT NULL,
                event_status TEXT,
                reason TEXT,
                source TEXT NOT NULL,
                payload_json TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO decision_ledger
            (event_id, decision_id, signal_id, instance_id, symbol, strategy, engine, event_type,
             event_status, reason, source, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "evt_sell",
                "dec_sell",
                "sig_sell",
                "inst_1",
                "TRXEUR",
                "grid",
                "trend_momentum",
                "decision",
                "sell_accepted",
                "take_profit",
                "signal_handler_runtime",
                '{"side":"sell"}',
                "2026-06-03T09:59:00+00:00",
            ),
        )
        conn.executemany(
            """
            INSERT INTO trade_ledger
            (trade_id, position_id, instance_id, symbol, side, expected_price, executed_price,
             volume, fees, slippage_bps, realized_pnl, is_opening_leg, is_closing_leg,
             exchange_order_id, decision_id, signal_id, execution_liquidity, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "buy",
                    "pos_1",
                    "inst_1",
                    "TRXEUR",
                    "buy",
                    1.0,
                    1.0,
                    10.0,
                    0.1,
                    1.0,
                    None,
                    1,
                    0,
                    "BUY",
                    None,
                    None,
                    "taker",
                    "2026-06-03T09:00:00+00:00",
                ),
                (
                    "sell",
                    "pos_1",
                    "inst_1",
                    "TRXEUR",
                    "sell",
                    1.2,
                    1.2,
                    10.0,
                    0.1,
                    1.0,
                    1.8,
                    0,
                    1,
                    "SELL",
                    "dec_sell",
                    "sig_sell",
                    "taker",
                    "2026-06-03T10:00:00+00:00",
                ),
            ],
        )


def _state_db_with_market_samples(path):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS market_price_samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sample_id TEXT,
                symbol TEXT,
                price REAL,
                observed_at TEXT,
                bucket_start TEXT,
                source TEXT,
                created_at TEXT
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO market_price_samples
            (sample_id, symbol, price, observed_at, bucket_start, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("px1", "TRXEUR", 0.25, "2026-06-04T00:00:05+00:00", "b1", "runtime", "c1"),
                ("px2", "TRXEUR", 0.26, "2026-06-04T00:00:55+00:00", "b1", "runtime", "c2"),
                ("px3", "TRXEUR", 0.27, "2026-06-04T00:01:10+00:00", "b2", "runtime", "c3"),
                ("px4", "XXBTZEUR", 65000.0, "2026-06-04T00:00:10+00:00", "b1", "runtime", "c4"),
            ],
        )


def _trend_shadow_db_with_trade(path):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE trend_shadow_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                variant TEXT,
                position_id TEXT,
                entry_price REAL,
                exit_price REAL,
                volume REAL,
                notional REAL,
                fees REAL,
                realized_pnl REAL,
                reason TEXT,
                opened_at TEXT,
                closed_at TEXT,
                created_at TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO trend_shadow_trades
            (symbol, variant, position_id, entry_price, exit_price, volume, notional, fees,
             realized_pnl, reason, opened_at, closed_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "TRXEUR",
                "pytest",
                "shadow_pos_1",
                1.0,
                1.01,
                100.0,
                100.0,
                0.5,
                0.5,
                "take_profit",
                "2026-06-04T00:00:00+00:00",
                "2026-06-04T00:01:00+00:00",
                "2026-06-04T00:01:00+00:00",
            ),
        )


def test_cli_audit_is_read_only(tmp_path, capsys):
    report_path = tmp_path / "audit.md"
    report_path.write_text("# Audit\n", encoding="utf-8")

    exit_code = cli.main(["audit", "--report-path", str(report_path), "--strict"])

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["exists"] is True
    assert output["live_trading_changed"] is False
    assert output["registry_mutated"] is False


def test_cli_build_dataset_exports_ohlcv_research_only(tmp_path, capsys):
    db_path = tmp_path / "state.db"
    _state_db_with_market_samples(db_path)

    exit_code = cli.main(
        [
            "build-dataset",
            "--run-id",
            "pytest_build_dataset",
            "--state-db",
            str(db_path),
            "--symbols",
            "TRXEUR,BTCZEUR",
            "--timeframes",
            "1m,5m",
            "--output-dir",
            str(tmp_path / "datasets"),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["run_id"] == "pytest_build_dataset"
    assert output["raw_sample_count"] == 4
    assert output["symbols"] == ["BTCZEUR", "TRXEUR"]
    assert output["raw_symbols"] == ["XXBTZEUR"]
    assert output["normalized_symbol_count"] == 1
    assert output["exports"][0]["csv_path"]
    assert output["exports"][0]["quality"]["row_count"] == 3
    assert "No runtime paper/live service is started." in output["safety_notes"]
    assert "No live trading permission is granted." in output["safety_notes"]
    assert (tmp_path / "datasets" / "pytest_build_dataset_manifest.json").exists()
    assert (tmp_path / "datasets" / "pytest_build_dataset_quality.md").exists()


def test_cli_backtest_runs_research_validation(tmp_path, capsys):
    csv_path = tmp_path / "bars.csv"
    _write_grid_csv(csv_path)

    exit_code = cli.main(
        [
            "backtest",
            "--run-id",
            "pytest_cli_backtest",
            "--strategy",
            "grid",
            "--data-source",
            "csv",
            "--data-path",
            str(csv_path),
            "--symbol",
            "TRXEUR",
            "--output-dir",
            str(tmp_path / "reports"),
            "--min-closed-trades",
            "1",
            "--fee-bps",
            "0",
            "--spread-bps",
            "0",
            "--slippage-bps",
            "0",
            "--strategy-config-json",
            json.dumps({"range_percent": 4.0, "num_levels": 5, "entry_touch_bps": 20.0, "take_profit_bps": 40.0}),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["mode"] == "backtest"
    assert output["bar_count"] == 4
    assert output["result"]["strategy_id"] == "dynamic_grid"
    assert output["result"]["decision"]["live_promotion_allowed"] is False
    assert "No live trading permission is granted." in output["safety_notes"]


def test_cli_matrix_runs_research_matrix_without_registry_mutation(tmp_path, capsys):
    csv_path = tmp_path / "bars.csv"
    _write_grid_csv(csv_path)

    exit_code = cli.main(
        [
            "matrix",
            "--run-id",
            "pytest_cli_matrix",
            "--data-source",
            "csv",
            "--data-path",
            str(csv_path),
            "--symbols",
            "TRXEUR",
            "--strategies",
            "grid",
            "--output-dir",
            str(tmp_path / "matrix"),
            "--min-closed-trades",
            "1",
            "--fee-bps",
            "0",
            "--spread-bps",
            "0",
            "--slippage-bps",
            "0",
            "--strategy-config-json",
            json.dumps(
                {
                    "grid": {
                        "range_percent": 4.0,
                        "num_levels": 5,
                        "entry_touch_bps": 20.0,
                        "take_profit_bps": 40.0,
                    }
                }
            ),
            "--write-loss-attribution",
            "--write-strategy-scorecard",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["run_id"] == "pytest_cli_matrix"
    assert output["cell_count"] == 1
    assert output["success_count"] == 1
    assert output["results"][0]["strategy"] == "grid"
    assert output["loss_attribution_report"]["analyzed_cell_count"] == 1
    assert output["strategy_scorecard_report"]["results"][0]["live_promotion_allowed"] is False
    assert "No strategy registry mutation is performed by this command." in output["safety_notes"]
    assert "No live trading permission is granted." in output["safety_notes"]
    assert (tmp_path / "matrix" / "pytest_cli_matrix.md").exists()
    assert (tmp_path / "matrix" / "loss_attribution" / "pytest_cli_matrix_matrix_loss_attribution.md").exists()
    assert (tmp_path / "matrix" / "strategy_scorecard" / "pytest_cli_matrix_strategy_scorecard.md").exists()


def test_cli_matrix_preset_fills_top14_symbols(tmp_path, capsys):
    csv_path = tmp_path / "bars.csv"
    _write_symbols_csv(csv_path, cli.AUTOBOT_TOP14_EUR_SYMBOLS)

    exit_code = cli.main(
        [
            "matrix",
            "--run-id",
            "pytest_cli_top14",
            "--preset",
            "autobot-top14-eur",
            "--data-source",
            "csv",
            "--data-path",
            str(csv_path),
            "--strategies",
            "grid",
            "--output-dir",
            str(tmp_path / "top14_matrix"),
            "--min-closed-trades",
            "1",
            "--train-window-bars",
            "1",
            "--test-window-bars",
            "3",
            "--step-window-bars",
            "4",
            "--min-folds",
            "1",
            "--min-passing-folds",
            "1",
            "--fee-bps",
            "0",
            "--spread-bps",
            "0",
            "--slippage-bps",
            "0",
            "--strategy-config-json",
            json.dumps(
                {
                    "grid": {
                        "range_percent": 4.0,
                        "num_levels": 5,
                        "entry_touch_bps": 20.0,
                        "take_profit_bps": 40.0,
                    }
                }
            ),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["preset"] == "autobot-top14-eur"
    assert output["standard_reports_enabled"] is False
    assert output["cell_count"] == len(cli.AUTOBOT_TOP14_EUR_SYMBOLS)
    assert output["error_count"] == 0
    assert {item["symbol"] for item in output["results"]} == set(cli.AUTOBOT_TOP14_EUR_SYMBOLS)
    assert "No live trading permission is granted." in output["safety_notes"]


def test_cli_matrix_standard_reports_writes_full_research_bundle(tmp_path, capsys):
    csv_path = tmp_path / "bars.csv"
    _write_grid_csv(csv_path)

    exit_code = cli.main(
        [
            "matrix",
            "--run-id",
            "pytest_cli_standard_reports",
            "--data-source",
            "csv",
            "--data-path",
            str(csv_path),
            "--symbols",
            "TRXEUR",
            "--strategies",
            "grid",
            "--output-dir",
            str(tmp_path / "standard_matrix"),
            "--min-closed-trades",
            "1",
            "--train-window-bars",
            "1",
            "--test-window-bars",
            "3",
            "--step-window-bars",
            "4",
            "--min-folds",
            "1",
            "--min-passing-folds",
            "1",
            "--fee-bps",
            "0",
            "--spread-bps",
            "0",
            "--slippage-bps",
            "0",
            "--strategy-config-json",
            json.dumps(
                {
                    "grid": {
                        "range_percent": 4.0,
                        "num_levels": 5,
                        "entry_touch_bps": 20.0,
                        "take_profit_bps": 40.0,
                    }
                }
            ),
            "--standard-reports",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["standard_reports_enabled"] is True
    assert output["registry_recommendation_report"]["recommendations"][0]["live_promotion_allowed"] is False
    assert output["loss_attribution_report"]["analyzed_cell_count"] == 1
    assert output["setup_quality_report"]["trade_count"] == 1
    assert output["strategy_regime_report"]["trade_count"] == 1
    assert output["strategy_regime_baseline_report"]["bucket_count"] == 1
    assert output["strategy_regime_walk_forward_report"]["evaluated_bucket_count"] == 1
    assert output["strategy_scorecard_report"]["results"][0]["live_promotion_allowed"] is False
    assert (tmp_path / "standard_matrix" / "registry_recommendations").exists()
    assert (tmp_path / "standard_matrix" / "strategy_regime_walk_forward").exists()


def test_cli_validate_strategies_builds_dataset_and_standard_matrix(tmp_path, capsys):
    db_path = tmp_path / "state.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE market_price_samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sample_id TEXT,
                symbol TEXT,
                price REAL,
                observed_at TEXT,
                bucket_start TEXT,
                source TEXT,
                created_at TEXT
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO market_price_samples
            (sample_id, symbol, price, observed_at, bucket_start, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("s1", "TRXEUR", 100.0, "2026-06-03T00:00:00+00:00", "b1", "runtime", "c1"),
                ("s2", "TRXEUR", 99.05, "2026-06-03T00:01:00+00:00", "b2", "runtime", "c2"),
                ("s3", "TRXEUR", 99.60, "2026-06-03T00:02:00+00:00", "b3", "runtime", "c3"),
                ("s4", "TRXEUR", 100.20, "2026-06-03T00:03:00+00:00", "b4", "runtime", "c4"),
            ],
        )

    exit_code = cli.main(
        [
            "validate-strategies",
            "--run-id",
            "pytest_cli_validate_strategies",
            "--state-db",
            str(db_path),
            "--symbols",
            "TRXEUR",
            "--strategies",
            "grid",
            "--timeframe",
            "1m",
            "--dataset-output-dir",
            str(tmp_path / "datasets"),
            "--output-dir",
            str(tmp_path / "validation"),
            "--min-closed-trades",
            "1",
            "--train-window-bars",
            "1",
            "--test-window-bars",
            "3",
            "--step-window-bars",
            "4",
            "--min-folds",
            "1",
            "--min-passing-folds",
            "1",
            "--fee-bps",
            "0",
            "--spread-bps",
            "0",
            "--slippage-bps",
            "0",
            "--strategy-config-json",
            json.dumps(
                {
                    "grid": {
                        "range_percent": 4.0,
                        "num_levels": 5,
                        "entry_touch_bps": 20.0,
                        "take_profit_bps": 40.0,
                    }
                }
            ),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["command"] == "validate-strategies"
    assert output["dataset"]["symbols"] == ["TRXEUR"]
    assert output["matrix"]["cell_count"] == 1
    assert output["matrix"]["success_count"] == 1
    assert output["strategy_scorecard_report"]["results"][0]["live_promotion_allowed"] is False
    assert "No runtime paper/live service is started." in output["safety_notes"]
    assert "No live trading permission is granted." in output["safety_notes"]
    assert (tmp_path / "datasets" / "pytest_cli_validate_strategies_dataset_1m.csv").exists()
    assert (tmp_path / "validation" / "pytest_cli_validate_strategies.json").exists()
    assert (tmp_path / "validation" / "strategy_scorecard").exists()


def test_cli_standard_audit_runs_full_read_only_bundle(tmp_path, capsys):
    db_path = tmp_path / "state.db"
    _state_db_with_closed_trade(db_path)
    _state_db_with_market_samples(db_path)

    exit_code = cli.main(
        [
            "standard-audit",
            "--run-id",
            "pytest_standard_audit",
            "--state-db",
            str(db_path),
            "--symbols",
            "TRXEUR",
            "--strategies",
            "grid",
            "--timeframe",
            "1m",
            "--report-date",
            "2026-06-03",
            "--dataset-output-dir",
            str(tmp_path / "standard_datasets"),
            "--output-dir",
            str(tmp_path / "standard_audit"),
            "--min-closed-trades",
            "1",
            "--train-window-bars",
            "1",
            "--test-window-bars",
            "3",
            "--step-window-bars",
            "4",
            "--min-folds",
            "1",
            "--min-passing-folds",
            "1",
            "--fee-bps",
            "0",
            "--spread-bps",
            "0",
            "--slippage-bps",
            "0",
            "--strategy-config-json",
            json.dumps(
                {
                    "grid": {
                        "range_percent": 4.0,
                        "num_levels": 5,
                        "entry_touch_bps": 20.0,
                        "take_profit_bps": 40.0,
                    }
                }
            ),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["command"] == "standard-audit"
    assert output["dataset"]["symbols"] == ["TRXEUR"]
    assert output["matrix"]["cell_count"] == 1
    assert output["matrix"]["standard_reports_enabled"] is True
    assert output["paper_loader"]["trade_count"] == 1
    assert output["paper_daily"]["trade_count"] == 1
    assert output["paper_vs_research"]["paper_trade_count"] == 1
    assert output["decision_trace"]["summary"]["trace_count"] >= 1
    assert output["cost_parity"]["sources"][0]["source"] == "official_paper_trade_ledger"
    assert output["pnl_causality"]["summary"]["closed_trades"] == 0
    assert "No live trading permission is granted." in output["safety_notes"]
    assert (tmp_path / "standard_audit" / "pytest_standard_audit.md").exists()
    assert (tmp_path / "standard_audit" / "paper_vs_research" / "pytest_standard_audit_paper_vs_research.md").exists()
    assert (tmp_path / "standard_audit" / "cost_parity" / "pytest_standard_audit_cost_parity.md").exists()


def test_cli_standard_audit_can_skip_matrix_annex_reports(tmp_path, capsys):
    db_path = tmp_path / "state.db"
    _state_db_with_closed_trade(db_path)
    _state_db_with_market_samples(db_path)

    exit_code = cli.main(
        [
            "standard-audit",
            "--run-id",
            "pytest_standard_audit_quick",
            "--state-db",
            str(db_path),
            "--symbols",
            "TRXEUR",
            "--strategies",
            "grid",
            "--timeframe",
            "1m",
            "--report-date",
            "2026-06-03",
            "--dataset-output-dir",
            str(tmp_path / "quick_datasets"),
            "--output-dir",
            str(tmp_path / "quick_audit"),
            "--min-closed-trades",
            "1",
            "--train-window-bars",
            "1",
            "--test-window-bars",
            "3",
            "--step-window-bars",
            "4",
            "--min-folds",
            "1",
            "--min-passing-folds",
            "1",
            "--skip-standard-reports",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["matrix"]["standard_reports_enabled"] is False
    assert output["matrix"]["standard_reports_skipped_reason"] == "disabled_by_standard_audit_config"
    assert output["matrix"]["quick_loss_attribution_report"]["analyzed_cell_count"] == 1
    assert output["matrix"]["quick_loss_attribution_report"]["cells"][0]["attribution_report_path"] is None
    assert output["paper_loader"]["trade_count"] == 1
    assert output["paper_vs_research"]["paper_trade_count"] == 1
    assert "No live trading permission is granted." in output["safety_notes"]
    markdown = (tmp_path / "quick_audit" / "pytest_standard_audit_quick.md").read_text(encoding="utf-8")
    assert "| Loss attribution |" in markdown
    assert "MFE/cost" in markdown
    assert "main failure" in markdown
    assert "- Quick loss attribution report:" in markdown


def test_cli_walk_forward_runs_research_validation(tmp_path, capsys):
    csv_path = tmp_path / "bars.csv"
    _write_grid_csv(csv_path)
    extra = "\n".join(
        [
            "2026-06-03T00:04:00+00:00,TRXEUR,1m,100,101,99,100,1000",
            "2026-06-03T00:05:00+00:00,TRXEUR,1m,99.05,100,98,99.05,1000",
            "2026-06-03T00:06:00+00:00,TRXEUR,1m,99.60,100,98,99.60,1000",
            "2026-06-03T00:07:00+00:00,TRXEUR,1m,100.20,101,99,100.20,1000",
        ]
    )
    csv_path.write_text(csv_path.read_text(encoding="utf-8") + "\n" + extra, encoding="utf-8")

    exit_code = cli.main(
        [
            "walk-forward",
            "--run-id",
            "pytest_cli_wf",
            "--strategy",
            "grid",
            "--data-source",
            "csv",
            "--data-path",
            str(csv_path),
            "--symbol",
            "TRXEUR",
            "--output-dir",
            str(tmp_path / "reports"),
            "--min-closed-trades",
            "1",
            "--train-window-bars",
            "1",
            "--test-window-bars",
            "3",
            "--step-window-bars",
            "4",
            "--min-folds",
            "2",
            "--min-passing-folds",
            "1",
            "--fee-bps",
            "0",
            "--spread-bps",
            "0",
            "--slippage-bps",
            "0",
            "--strategy-config-json",
            json.dumps({"range_percent": 4.0, "num_levels": 5, "entry_touch_bps": 20.0, "take_profit_bps": 40.0}),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["mode"] == "walk_forward"
    assert output["result"]["fold_count"] == 2
    assert output["result"]["decision"]["live_promotion_allowed"] is False


def test_cli_paper_builds_daily_report_from_journal(tmp_path, capsys):
    journal_path = tmp_path / "journal.json"
    _trade_journal(journal_path)

    exit_code = cli.main(
        [
            "paper",
            "--journal-path",
            str(journal_path),
            "--report-date",
            "2026-06-03",
            "--output-dir",
            str(tmp_path / "paper_reports"),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["mode"] == "paper"
    assert output["trade_count"] == 1
    assert output["metrics"]["total_net_pnl_eur"] == pytest.approx(1.2)
    assert output["decision"] == "CONTINUE"
    assert output["safety_notes"][-1] == "No live trading permission is granted."
    assert (tmp_path / "paper_reports" / "daily_2026-06-03.md").exists()


def test_cli_paper_can_read_state_db_trade_ledger(tmp_path, capsys):
    db_path = tmp_path / "state.db"
    _state_db_with_closed_trade(db_path)

    exit_code = cli.main(
        [
            "paper",
            "--state-db",
            str(db_path),
            "--report-date",
            "2026-06-03",
            "--output-dir",
            str(tmp_path / "paper_reports"),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["loader"]["source_type"] == "state_db_trade_ledger"
    assert output["trade_count"] == 1
    assert output["decision_count"] == 1
    assert output["metrics"]["total_net_pnl_eur"] == pytest.approx(1.8)
    assert output["strategy_statuses"][0]["strategy_id"] == "trend_momentum"


def test_cli_paper_performance_summary_reads_official_post_p0_ledger(tmp_path, capsys):
    db_path = tmp_path / "state.db"
    registry_path = tmp_path / "strategy_hypotheses.json"
    _state_db_with_closed_trade(db_path)
    _write_strategy_registry(registry_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("ALTER TABLE trade_ledger ADD COLUMN strategy_id TEXT")
        conn.execute("ALTER TABLE trade_ledger ADD COLUMN timeframe TEXT")
        conn.execute("ALTER TABLE trade_ledger ADD COLUMN signal_source TEXT")
        conn.execute("ALTER TABLE trade_ledger ADD COLUMN gross_pnl REAL")
        conn.execute("ALTER TABLE trade_ledger ADD COLUMN net_pnl REAL")
        conn.execute("ALTER TABLE trade_ledger ADD COLUMN regime TEXT")
        conn.execute("ALTER TABLE trade_ledger ADD COLUMN execution_mode TEXT")
        conn.execute(
            """
            UPDATE trade_ledger
            SET strategy_id='trend_momentum',
                timeframe='5m',
                signal_source='pytest',
                gross_pnl=2.0,
                net_pnl=1.8,
                regime='range',
                execution_mode='paper_capital'
            WHERE side='sell'
            """
        )

    exit_code = cli.main(
        [
            "paper-performance-summary",
            "--state-db",
            str(db_path),
            "--registry-path",
            str(registry_path),
            "--run-id",
            "pytest_summary",
            "--output-dir",
            str(tmp_path / "official_paper"),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["source"] == "official_post_p0_trade_ledger"
    assert output["ranking"][0]["strategy_id"] == "trend_momentum"
    assert output["ranking"][0]["metrics"]["closed_trade_count"] == 1
    assert output["ranking"][0]["promotable"] is False
    assert output["baseline"]["strategy_id"] == "no_trade_baseline"
    assert (tmp_path / "official_paper" / "pytest_summary.md").exists()


def test_cli_compare_paper_research_reports_divergence(tmp_path, capsys):
    journal_path = tmp_path / "journal.json"
    _trade_journal(journal_path)
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(
        json.dumps(
            {
                "run_id": "pytest_matrix",
                "mode": "backtest",
                "cell_count": 1,
                "success_count": 1,
                "error_count": 0,
                "results": [
                    {
                        "run_id": "pytest_matrix_TRXEUR_trend",
                        "symbol": "TRXEUR",
                        "strategy": "trend",
                        "mode": "backtest",
                        "status": "ok",
                        "decision": "modify",
                        "reason": "non_positive_net_pnl",
                        "bar_count": 120,
                        "closed_trades": 2,
                        "net_pnl_eur": -2.5,
                        "profit_factor": 0.8,
                        "max_drawdown_pct": 4.0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = cli.main(
        [
            "compare-paper-research",
            "--run-id",
            "pytest_compare",
            "--matrix-path",
            str(matrix_path),
            "--journal-path",
            str(journal_path),
            "--output-dir",
            str(tmp_path / "compare_reports"),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["run_id"] == "pytest_compare"
    assert output["matrix_run_id"] == "pytest_matrix"
    assert output["divergent_bucket_count"] == 1
    assert output["buckets"][0]["alignment"] == "paper_positive_research_negative"
    assert "No live trading permission is granted." in output["safety_notes"]
    assert (tmp_path / "compare_reports" / "pytest_compare.md").exists()


def test_cli_compare_paper_research_accepts_validate_strategies_output(tmp_path, capsys):
    journal_path = tmp_path / "journal.json"
    _trade_journal(journal_path)
    workflow_path = tmp_path / "validate_strategies.json"
    workflow_path.write_text(
        json.dumps(
            {
                "command": "validate-strategies",
                "run_id": "pytest_validate",
                "dataset": {"run_id": "pytest_validate_dataset"},
                "matrix": {
                    "run_id": "pytest_matrix_nested",
                    "mode": "backtest",
                    "cell_count": 1,
                    "success_count": 1,
                    "error_count": 0,
                    "results": [
                        {
                            "run_id": "pytest_matrix_TRXEUR_trend",
                            "symbol": "TRXEUR",
                            "strategy": "trend",
                            "mode": "backtest",
                            "status": "ok",
                            "decision": "modify",
                            "reason": "non_positive_net_pnl",
                            "bar_count": 120,
                            "closed_trades": 2,
                            "net_pnl_eur": -2.5,
                            "profit_factor": 0.8,
                            "max_drawdown_pct": 4.0,
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )

    exit_code = cli.main(
        [
            "compare-paper-research",
            "--run-id",
            "pytest_compare_nested",
            "--matrix-path",
            str(workflow_path),
            "--journal-path",
            str(journal_path),
            "--output-dir",
            str(tmp_path / "compare_reports"),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["matrix_run_id"] == "pytest_matrix_nested"
    assert output["divergent_bucket_count"] == 1
    assert output["buckets"][0]["alignment"] == "paper_positive_research_negative"
    assert "No live trading permission is granted." in output["safety_notes"]


def test_cli_compare_paper_research_attaches_state_db_decision_trace(tmp_path, capsys):
    db_path = tmp_path / "state.db"
    _state_db_with_closed_trade(db_path)
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(
        json.dumps(
            {
                "run_id": "pytest_matrix",
                "mode": "backtest",
                "cell_count": 1,
                "success_count": 1,
                "error_count": 0,
                "results": [
                    {
                        "run_id": "pytest_matrix_TRXEUR_trend",
                        "symbol": "TRXEUR",
                        "strategy": "trend",
                        "mode": "backtest",
                        "status": "ok",
                        "decision": "modify",
                        "reason": "non_positive_net_pnl",
                        "bar_count": 120,
                        "closed_trades": 2,
                        "net_pnl_eur": -2.5,
                        "profit_factor": 0.8,
                        "max_drawdown_pct": 4.0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = cli.main(
        [
            "compare-paper-research",
            "--run-id",
            "pytest_compare_trace",
            "--matrix-path",
            str(matrix_path),
            "--state-db",
            str(db_path),
            "--output-dir",
            str(tmp_path / "compare_reports"),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    bucket = output["buckets"][0]
    assert exit_code == 0
    assert output["decision_trace_run_id"] == "pytest_compare_trace_decision_trace"
    assert output["decision_trace_audit_summary"]["trace_count"] == 1
    assert bucket["decision_traces"]["trace_count"] == 1
    assert "decision_trace_missing_order" in bucket["diagnostics"]
    assert "decision_trace_missing_signal" in bucket["diagnostics"]
    assert "No live trading permission is granted." in output["safety_notes"]


def test_cli_cost_parity_audits_read_only_cost_sources(tmp_path, capsys):
    db_path = tmp_path / "state.db"
    shadow_db = tmp_path / "trend_shadow.db"
    _state_db_with_closed_trade(db_path)
    _trend_shadow_db_with_trade(shadow_db)

    exit_code = cli.main(
        [
            "cost-parity",
            "--run-id",
            "pytest_cost_parity_cli",
            "--state-db",
            str(db_path),
            "--trend-shadow-db",
            str(shadow_db),
            "--output-dir",
            str(tmp_path / "cost_parity_reports"),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["run_id"] == "pytest_cost_parity_cli"
    assert output["research_cost_config"]["cost_profile"] == "research_stress"
    assert output["expected_cost_bps_per_side"] == pytest.approx(49.0)
    sources = {source["source"]: source for source in output["sources"]}
    assert sources["official_paper_trade_ledger"]["status"] == "ok"
    assert sources["trend_shadow"]["status"] == "ok"
    assert sources["trend_shadow"]["avg_total_cost_bps"] == pytest.approx(25.0)
    assert "No live trading permission is granted." in output["safety_notes"]
    assert (tmp_path / "cost_parity_reports" / "pytest_cost_parity_cli.md").exists()


def test_cli_data_quality_reports_gaps_without_runtime_mutation(tmp_path, capsys):
    csv_path = tmp_path / "bars.csv"
    csv_path.write_text(
        "\n".join(
            [
                "timestamp,symbol,timeframe,open,high,low,close,volume",
                "2026-06-01T00:00:00+00:00,TRXEUR,5m,100,101,99,100,0",
                "2026-06-01T00:20:00+00:00,TRXEUR,5m,100,102,99,101,0",
            ]
        ),
        encoding="utf-8",
    )

    exit_code = cli.main(
        [
            "data-quality",
            "--run-id",
            "pytest_data_quality_cli",
            "--paths",
            str(csv_path),
            "--default-timeframe",
            "5m",
            "--output-dir",
            str(tmp_path / "data_quality"),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["overall_status"] == "not_ready"
    assert output["files"][0]["usable_for_backtest"] is False
    assert "data_gaps_present" in output["files"][0]["exclusions"]
    assert "No live trading permission is granted." in output["safety_notes"]
    assert (tmp_path / "data_quality" / "pytest_data_quality_cli.md").exists()


def test_cli_collect_research_daily_is_research_only(monkeypatch, tmp_path, capsys):
    from autobot.v2.research import daily_data_collection_runner
    from autobot.v2.research.daily_data_collection_runner import DailyResearchDataCollectionResult

    config_path = tmp_path / "research_daily.yaml"
    config_path.write_text("safety:\n  research_only: true\n", encoding="utf-8")
    calls = {}

    def fake_runner(*, config_path, run_id):
        calls["config_path"] = str(config_path)
        calls["run_id"] = run_id
        return DailyResearchDataCollectionResult(
            run_id=run_id,
            generated_at="2026-06-07T00:00:00+00:00",
            config_path=str(config_path),
            operations=(),
            microstructure_result=None,
            microstructure_profile_path=None,
            data_readiness_dashboard_path=None,
        )

    monkeypatch.setattr(daily_data_collection_runner, "run_daily_research_data_collection", fake_runner)

    exit_code = cli.main(
        [
            "collect-research-daily",
            "--config",
            str(config_path),
            "--run-id",
            "pytest_daily_cli",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert calls == {"config_path": str(config_path), "run_id": "pytest_daily_cli"}
    assert output["run_id"] == "pytest_daily_cli"
    assert output["live_promotion_allowed"] is False
    assert "No paper or live order is created." in output["safety_notes"]


def test_cli_strategy_edge_review_writes_research_only_reports(tmp_path, capsys):
    orchestrator_path = tmp_path / "orchestrator.json"
    high_conviction_path = tmp_path / "hc.json"
    primary = {
        "cost_profile": "research_stress",
        "total_net_pnl_eur": 7.0,
        "profit_factor": 1.05,
        "total_trade_count": 20,
        "positive_fold_count": 1,
        "fold_count": 4,
        "largest_positive_symbol_share": 0.70,
        "contributors": [
            {"symbol": "BCHEUR", "net_pnl_eur": 12.0, "trade_count": 5},
            {"symbol": "XLMZEUR", "net_pnl_eur": -5.0, "trade_count": 6},
        ],
    }
    orchestrator_path.write_text(
        json.dumps(
            {
                "strategy_scores": [
                    {"strategy_name": "trend_momentum", "status": "research_signal_only", "evidence": {"profit_factor": 0.3}},
                    {"strategy_name": "mean_reversion", "status": "research_signal_only", "evidence": {"profit_factor": 1.0}},
                    {"strategy_name": "relative_value", "status": "no_go", "evidence": {}},
                    {"strategy_name": "grid", "status": "archived", "evidence": {}},
                ],
                "pair_scores": [
                    {"symbol": "BCHEUR", "closed_trade_count": 5, "net_pnl_eur": 12.0, "profit_factor": 2.0},
                    {"symbol": "XLMZEUR", "closed_trade_count": 6, "net_pnl_eur": -5.0, "profit_factor": 0.5},
                ],
                "high_conviction_walk_forward": {"primary_aggregate": primary},
            }
        ),
        encoding="utf-8",
    )
    high_conviction_path.write_text(
        json.dumps(
            {
                "primary_aggregate": primary,
                "aggregates": [
                    {"cost_profile": "paper_current_taker", "total_net_pnl_eur": 8.0, "profit_factor": 1.1},
                    {"cost_profile": "research_stress", "total_net_pnl_eur": 7.0, "profit_factor": 1.05},
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = cli.main(
        [
            "strategy-edge-review",
            "--run-id",
            "pytest_strategy_edge_cli",
            "--strategy-orchestrator-report",
            str(orchestrator_path),
            "--high-conviction-report",
            str(high_conviction_path),
            "--report-date",
            "2026-06-29",
            "--output-dir",
            str(tmp_path / "edge_reports"),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["live_promotion_allowed"] is False
    assert output["orders_created"] is False
    assert output["runtime_modified"] is False
    assert Path(output["review_markdown_path"]).exists()
    assert Path(output["improvement_markdown_path"]).exists()


def test_cli_collect_history_uses_detected_active_symbols_when_omitted(monkeypatch, tmp_path, capsys):
    from autobot.v2.research import historical_data_collector
    from autobot.v2.research.historical_data_collector import (
        HistoricalDataCollectionResult,
        HistoricalDataFile,
    )
    from autobot.v2.research.data_quality_report import DataFoundationReadinessReport

    calls = {}

    def fake_collect(config, **kwargs):
        calls["symbols"] = tuple(config.symbols)
        calls["export_parquet"] = config.export_parquet
        return HistoricalDataCollectionResult(
            run_id=config.run_id,
            provider=config.provider,
            generated_at="2026-06-16T00:00:00+00:00",
            files=(
                HistoricalDataFile(
                    symbol="BTCZEUR",
                    kraken_ohlcv_symbol="XXBTZEUR",
                    runtime_symbol="XXBTZEUR",
                    timeframe="5m",
                    provider=config.provider,
                    row_count=0,
                    start_at=None,
                    end_at=None,
                ),
            ),
            readiness=DataFoundationReadinessReport(
                run_id="pytest_readiness",
                generated_at="2026-06-16T00:00:00+00:00",
                files=(),
                usable_file_count=0,
                unusable_file_count=0,
                symbol_coverage={},
                overall_status="ready_for_ohlcv_research",
                status_tiers=("ready_for_ohlcv_research",),
                recommendations=(),
            ),
        )

    monkeypatch.setattr(cli, "detect_active_autobot_symbols", lambda: ("BTCZEUR", "TRXEUR"))
    monkeypatch.setattr(historical_data_collector, "collect_historical_ohlcv", fake_collect)

    exit_code = cli.main(
        [
            "collect-history",
            "--run-id",
            "pytest_collect_history",
            "--timeframes",
            "5m",
            "--output-dir",
            str(tmp_path / "history"),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert calls["symbols"] == ("BTCZEUR", "TRXEUR")
    assert calls["export_parquet"] is False
    assert output["run_id"] == "pytest_collect_history"


def test_cli_no_trade_attribution_is_read_only(tmp_path, capsys):
    import sqlite3

    db_path = tmp_path / "state.db"
    connection = sqlite3.connect(db_path)
    connection.execute(
        "CREATE TABLE decision_ledger (id INTEGER PRIMARY KEY, symbol TEXT, strategy TEXT, "
        "event_type TEXT, event_status TEXT, reason TEXT, created_at TEXT)"
    )
    connection.execute(
        "INSERT INTO decision_ledger(symbol,strategy,event_type,event_status,reason,created_at) "
        "VALUES('TRXEUR','grid','no_trade','abstain','router_selected_no_trade','2026-06-11T10:00:00+00:00')"
    )
    connection.commit()
    connection.close()

    exit_code = cli.main([
        "no-trade-attribution", "--run-id", "cli-no-trade", "--state-db", str(db_path),
        "--output-dir", str(tmp_path / "reports"),
    ])

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["counts"]["no_trade"] == 1
    assert output["live_promotion_allowed"] is False


def test_cli_orphan_reconciliation_requires_dry_run_and_does_not_write(tmp_path, capsys):
    import sqlite3

    db_path = tmp_path / "state.db"
    connection = sqlite3.connect(db_path)
    connection.execute(
        "CREATE TABLE positions (id TEXT, instance_id TEXT, buy_price REAL, volume REAL, "
        "status TEXT, open_time TEXT, strategy TEXT, metadata TEXT, symbol TEXT)"
    )
    connection.execute("CREATE TABLE instance_state (instance_id TEXT PRIMARY KEY)")
    connection.execute("CREATE TABLE trade_ledger (position_id TEXT, instance_id TEXT)")
    connection.execute(
        "INSERT INTO positions VALUES('legacy','old',1.0,1.0,'open','2026-05-01','grid','{}',NULL)"
    )
    connection.commit()
    connection.close()

    exit_code = cli.main([
        "reconcile-orphan-positions", "--run-id", "cli-orphan", "--state-db", str(db_path),
        "--dry-run", "--output-dir", str(tmp_path / "reports"),
    ])

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["orphan_count"] == 1
    assert output["write_performed"] is False
    connection = sqlite3.connect(db_path)
    try:
        assert connection.execute("SELECT status FROM positions WHERE id='legacy'").fetchone()[0] == "open"
    finally:
        connection.close()


def test_cli_strategy_experiments_batch_accepts_csv_dataset(tmp_path, capsys):
    csv_path = tmp_path / "bars.csv"
    _write_grid_csv(csv_path)

    exit_code = cli.main(
        [
            "strategy-experiments-batch",
            "--run-id",
            "pytest_batch_csv_cli",
            "--data-source",
            "csv",
            "--data-path",
            str(csv_path),
            "--symbols",
            "TRXEUR",
            "--strategies",
            "grid",
            "--output-dir",
            str(tmp_path / "batch_csv_cli"),
            "--min-closed-trades",
            "1",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["data_source"] == "csv"
    assert output["state_db_path"] == ""
    assert output["symbols"] == ["TRXEUR"]
    assert output["status_by_strategy"]["grid"] in {"research_only", "shadow_candidate"}
    assert "No live trading permission is granted." in output["safety_notes"]
    assert (tmp_path / "batch_csv_cli" / "pytest_batch_csv_cli.md").exists()


def test_cli_split_plan_blocks_unvalidated_parent_without_creating_child(tmp_path, capsys):
    evidence = json.dumps(
        [
            {
                "parent_instance_id": "parent_1",
                "strategy_id": "dynamic_grid",
                "strategy_status": "research_only",
                "paper_mode": True,
                "live_promotion_allowed": False,
                "parent_capital_eur": 4000.0,
                "parent_available_eur": 2000.0,
                "net_pnl_eur": -10.0,
                "official_paper_net_pnl_eur": -10.0,
                "profit_factor": 0.5,
                "trade_count": 150,
                "validation_days": 7,
                "max_drawdown_pct": 8.0,
                "strategy_scorecard": 20.0,
                "dominant_failure_mode": "weak_mfe_below_cost",
            }
        ]
    )

    exit_code = cli.main(
        [
            "split-plan",
            "--run-id",
            "pytest_split_plan_cli",
            "--state-db",
            str(tmp_path / "missing_state.db"),
            "--evidence-json",
            evidence,
            "--output-dir",
            str(tmp_path / "split_plan"),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    decision = output["decisions"][0]
    assert decision["allowed_to_plan"] is False
    assert decision["executable_now"] is False
    assert decision["live_promotion_allowed"] is False
    assert "blocked_failure_mode:weak_mfe_below_cost" in decision["blockers"]
    assert "No instance is created by this planner." in output["safety_notes"]
    assert (tmp_path / "split_plan" / "pytest_split_plan_cli.md").exists()


def test_cli_split_validation_runs_isolated_paper_mechanics(tmp_path, capsys):
    evidence = json.dumps(
        {
            "parent_instance_id": "parent_validated",
            "parent_capital_eur": 4000.0,
            "parent_available_eur": 3000.0,
            "parent_lifetime_split_count": 0,
            "paper_mode": True,
            "strategy_id": "trend_momentum",
            "strategy_status": "paper_validated",
            "net_pnl_eur": 250.0,
            "profit_factor": 1.45,
            "trade_count": 180,
            "validation_days": 14,
            "max_drawdown_pct": 6.0,
            "strategy_scorecard": 84.0,
            "dominant_failure_mode": "healthy",
            "official_paper_net_pnl_eur": 220.0,
            "live_promotion_allowed": False,
        }
    )

    exit_code = cli.main(
        [
            "split-validation",
            "--run-id",
            "pytest_split_validation_cli",
            "--evidence-json",
            evidence,
            "--output-dir",
            str(tmp_path / "split_validation"),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["status"] == "PASS"
    assert output["checks"]["capital_conserved_at_split"] is True
    assert output["checks"]["second_split_blocked_for_lifetime"] is True
    assert output["checks"]["no_order_path"] is True
    assert output["first_decision"]["live_promotion_allowed"] is False
    assert (tmp_path / "split_validation" / "pytest_split_validation_cli.md").exists()


def test_cli_leaderboard_scores_matrix_without_registry_mutation(tmp_path, capsys):
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(
        json.dumps(
            {
                "run_id": "pytest_matrix",
                "mode": "backtest",
                "cell_count": 1,
                "success_count": 1,
                "error_count": 0,
                "results": [
                    {
                        "run_id": "pytest_matrix_TRXEUR_grid",
                        "symbol": "TRXEUR",
                        "strategy": "grid",
                        "mode": "backtest",
                        "status": "ok",
                        "decision": "modify",
                        "reason": "profit_factor_below_threshold",
                        "bar_count": 120,
                        "closed_trades": 10,
                        "net_pnl_eur": -2.5,
                        "profit_factor": 0.8,
                        "max_drawdown_pct": 4.0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = cli.main(
        [
            "leaderboard",
            "--matrix-path",
            str(matrix_path),
            "--output-dir",
            str(tmp_path / "scorecards"),
            "--baseline-included",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["results"][0]["strategy_id"] == "grid"
    assert output["results"][0]["live_promotion_allowed"] is False
    assert output["results"][0]["decision"] == "reject"
    assert "No live trading permission is granted." in output["safety_notes"]
    assert (tmp_path / "scorecards" / "pytest_matrix_strategy_scorecard.md").exists()


def test_cli_migrates_research_memory_to_append_only_experiment_registry(tmp_path, capsys):
    memory_path = tmp_path / "memory.sqlite3"
    registry_path = tmp_path / "experiment_registry.sqlite3"
    ResearchMemoryStore(memory_path).append(
        {
            "run_id": "pytest_legacy_memory",
            "hypothesis_id": "trend_momentum",
            "alpha_family_id": "trend_momentum",
            "template_id": "regime_filtered_trend",
            "created_at": "2026-07-11T00:00:00+00:00",
            "data_snapshot": {"snapshot_id": "pytest"},
            "parameters_tested": {"lookback": 24},
            "variant_count": 1,
            "symbols_tested": ["BTCZEUR"],
            "gate_results": [],
            "final_status": "INSUFFICIENT_DATA",
            "rejection_reasons": [],
            "trial_count_for_family": 1,
            "trial_count_for_template": 1,
            "related_rejected_hypotheses": [],
            "do_not_rerun_until": None,
            "requires_new_data_before_rerun": True,
            "paper_capital_allowed": False,
            "live_allowed": False,
            "promotable": False,
        }
    )

    exit_code = cli.main(
        [
            "experiment-registry-migrate-memory",
            "--memory-path",
            str(memory_path),
            "--registry-path",
            str(registry_path),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["legacy_records_seen"] == 1
    assert output["legacy_records_inserted"] == 1
    assert output["research_only"] is True
    assert output["paper_capital_allowed"] is False
    assert output["live_allowed"] is False


def test_cli_reserves_an_immutable_experiment_holdout_without_enabling_execution(tmp_path, capsys):
    registry_path = tmp_path / "experiment_registry.sqlite3"
    manifest_path = tmp_path / "holdout.json"
    manifest_path.write_text(json.dumps({"period": "2026-Q3", "symbols": ["BTCZEUR"]}), encoding="utf-8")

    exit_code = cli.main(
        [
            "experiment-registry-reserve-holdout",
            "--registry-path",
            str(registry_path),
            "--holdout-id",
            "holdout_2026_q3",
            "--data-snapshot-id",
            "ohlcv_holdout_2026_q3",
            "--immutable-fingerprint",
            "fingerprint-holdout",
            "--manifest-path",
            str(manifest_path),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["reserved"] is True
    assert output["optimization_allowed"] is False
    assert output["paper_capital_allowed"] is False
    assert output["live_allowed"] is False


def test_cli_records_final_holdout_review_without_enabling_execution(tmp_path, capsys):
    registry_path = tmp_path / "experiment_registry.sqlite3"
    registry = ExperimentRegistry(registry_path)
    experiment = registry.register_experiment(
        ExperimentSpec(
            hypothesis_id="funding_basis",
            template_id="funding_extreme_reversion",
            thesis="CLI final holdout review fixture",
            code_commit="pytest-commit",
            data_snapshot_id="snapshot-pytest",
            feature_versions={"basis_bps": "1.0.0"},
            parameters={"threshold": 2.5},
            seed=7,
            cost_model={"fee_bps": 16.0},
            environment={"mode": "research"},
            holdout_id="holdout_cli_review",
        )
    )
    registry.reserve_holdout(
        holdout_id="holdout_cli_review",
        data_snapshot_id="snapshot-pytest-holdout",
        immutable_fingerprint="holdout-cli-review-fingerprint",
    )

    exit_code = cli.main(
        [
            "experiment-registry-record-final-holdout-review",
            "--registry-path",
            str(registry_path),
            "--experiment-id",
            experiment.experiment_id,
            "--metrics-json",
            '{"net_pnl_eur": 3.0, "profit_factor": 1.2}',
            "--reasons",
            "final_review,pytest",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["final_holdout_review_recorded"] is True
    assert output["optimization_allowed"] is False
    assert output["paper_capital_allowed"] is False
    assert output["live_allowed"] is False


def test_cli_sqlite_restore_drill_is_non_authorizing_and_preserves_backup(tmp_path, capsys):
    backup_path = tmp_path / "backup.sqlite3"
    with sqlite3.connect(backup_path) as connection:
        connection.execute("CREATE TABLE evidence (id INTEGER PRIMARY KEY, value TEXT)")
        connection.execute("INSERT INTO evidence(value) VALUES ('preserved')")
    before = backup_path.read_bytes()

    exit_code = cli.main(["sqlite-restore-drill", "--backup-path", str(backup_path)])

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["temporary_restore_cleaned"] is True
    assert output["research_only"] is True
    assert output["paper_capital_allowed"] is False
    assert output["live_allowed"] is False
    assert backup_path.read_bytes() == before


def test_cli_runtime_oms_ledger_migration_plan_is_non_authorizing(tmp_path, capsys):
    state_db = tmp_path / "state.sqlite3"
    with sqlite3.connect(state_db) as connection:
        connection.execute("CREATE TABLE orders (client_order_id TEXT, exchange_order_id TEXT)")
        connection.execute(
            "CREATE TABLE order_state_transitions (id INTEGER PRIMARY KEY, client_order_id TEXT, from_status TEXT, to_status TEXT, reason TEXT, occurred_at TEXT)"
        )
        connection.execute(
            "CREATE TABLE trade_ledger (id INTEGER PRIMARY KEY, trade_id TEXT, exchange_order_id TEXT, decision_id TEXT, signal_id TEXT, strategy_id TEXT, execution_mode TEXT, volume REAL, executed_price REAL, fees REAL, created_at TEXT)"
        )
        connection.execute("INSERT INTO orders VALUES ('client-1', 'exchange-1')")
        connection.execute("INSERT INTO order_state_transitions VALUES (1, 'client-1', NULL, 'SENT', NULL, '2026-07-15T12:00:00+00:00')")
    before = state_db.read_bytes()

    exit_code = cli.main(["runtime-oms-ledger-migration-plan", "--state-db", str(state_db)])

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["status"] == "MIGRATION_REVIEW_REQUIRED"
    assert output["migration_allowed"] is False
    assert output["paper_capital_allowed"] is False
    assert output["live_allowed"] is False
    assert state_db.read_bytes() == before


def test_cli_pre_registers_material_trial_plan_before_runner_statistics(tmp_path):
    feature_manifest = tmp_path / "feature_snapshot.json"
    feature_manifest.write_text(
        json.dumps(
            {
                "status": "READY",
                "parity_ok": True,
                "feature_count": 2,
                "feature_snapshot_id": "features_pytest",
                "fingerprint": "feature-fingerprint",
                "source_snapshot_id": "ohlcv_pytest",
                "source_snapshot_fingerprint": "source-fingerprint",
                "feature_registry_fingerprint": "registry-fingerprint",
                "feature_versions": {"momentum_3_bps": "1.0.0"},
                "ingestion_time_unknown_count": 0,
                "runtime_parity_proven": True,
            }
        ),
        encoding="utf-8",
    )
    args = cli._build_parser().parse_args(
        [
            "alpha-hypothesis-runner",
            "--hypothesis-id",
            "long_trend",
            "--commit",
            "pytest-commit",
            "--feature-snapshot-manifest",
            str(feature_manifest),
            "--experiment-registry",
            str(tmp_path / "experiment_registry.sqlite3"),
            "--symbols",
            "BTCZEUR,ETHZEUR",
            "--max-variants",
            "2",
            "--trial-timeframes",
            "1h,15m",
            "--trial-regimes",
            "trend,range",
        ]
    )

    context = cli._prepare_alpha_experiment_context(
        args,
        data_paths=(),
        hypothesis_id=args.hypothesis_id,
        code_commit=args.commit,
    )

    assert context["validation_trial_count"] == 16
    assert context["registry"].validation_trial_count(hypothesis_id="long_trend") == 16
    assert context["spec"].to_dict()["paper_capital_allowed"] is False
    assert context["spec"].to_dict()["live_allowed"] is False


def test_cli_skips_a_terminal_material_experiment_before_research_retries(tmp_path, capsys):
    feature_manifest = tmp_path / "feature_snapshot.json"
    feature_manifest.write_text(
        json.dumps(
            {
                "status": "READY",
                "parity_ok": True,
                "feature_count": 2,
                "feature_snapshot_id": "features_terminal",
                "fingerprint": "feature-fingerprint-terminal",
                "source_snapshot_id": "ohlcv_terminal",
                "source_snapshot_fingerprint": "source-fingerprint-terminal",
                "feature_registry_fingerprint": "registry-fingerprint-terminal",
                "feature_versions": {"momentum_3_bps": "1.0.0"},
                "ingestion_time_unknown_count": 0,
                "runtime_parity_proven": True,
            }
        ),
        encoding="utf-8",
    )
    command = [
        "alpha-hypothesis-runner",
        "--hypothesis-id",
        "long_trend",
        "--mode",
        "data_check",
        "--commit",
        "pytest-commit-terminal",
        "--feature-snapshot-manifest",
        str(feature_manifest),
        "--experiment-registry",
        str(tmp_path / "experiment_registry.sqlite3"),
        "--memory-path",
        str(tmp_path / "memory.sqlite3"),
        "--output-dir",
        str(tmp_path / "reports"),
        "--symbols",
        "BTCZEUR",
        "--max-variants",
        "1",
    ]

    assert cli.main(command) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["experiment_registry"]["state"]["terminal"] is True
    assert first["paper_capital_allowed"] is False
    assert first["live_allowed"] is False

    assert cli.main(command) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["final_decision"] == "MATERIAL_EXPERIMENT_ALREADY_TERMINAL"
    assert second["experiment_registry"]["recorded"] is False
    assert second["paper_capital_allowed"] is False
    assert second["live_allowed"] is False
