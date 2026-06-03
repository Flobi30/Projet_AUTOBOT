import json
import sqlite3
from datetime import datetime, timezone

import pytest

from autobot.v2 import cli
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


def test_cli_audit_is_read_only(tmp_path, capsys):
    report_path = tmp_path / "audit.md"
    report_path.write_text("# Audit\n", encoding="utf-8")

    exit_code = cli.main(["audit", "--report-path", str(report_path), "--strict"])

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["exists"] is True
    assert output["live_trading_changed"] is False
    assert output["registry_mutated"] is False


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
