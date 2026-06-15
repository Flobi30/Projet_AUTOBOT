import json
import sqlite3

import pytest

from autobot.v2.research.execution_cost_model import ExecutionCostConfig
from autobot.v2.research.trade_journal import TradeJournal
from autobot.v2.research.validation_runner import (
    ValidationRunnerConfig,
    load_bars_for_validation,
    main,
    make_signal_generator_factory,
    run_validation,
)


pytestmark = pytest.mark.integration


def _write_grid_csv(path):
    path.write_text(
        "\n".join(
            [
                "timestamp,symbol,timeframe,open,high,low,close,volume",
                "2026-05-31T00:00:00+00:00,TRXEUR,1m,100,101,99,100,1000",
                "2026-05-31T00:01:00+00:00,TRXEUR,1m,99.05,100,98,99.05,1000",
                "2026-05-31T00:02:00+00:00,TRXEUR,1m,99.6,100,98,99.6,1000",
            ]
        ),
        encoding="utf-8",
    )


def test_grid_factory_uses_selected_cost_profile_for_expected_round_trip_cost():
    cost_config = ExecutionCostConfig(
        cost_profile="paper_current_taker",
        taker_fee_bps=40.0,
        maker_fee_bps=25.0,
        fallback_spread_bps=8.0,
        slippage_bps=3.0,
        latency_buffer_bps=0.0,
    )

    generator = make_signal_generator_factory("grid", cost_config=cost_config)()

    assert generator.config.estimated_round_trip_cost_bps == pytest.approx(94.0)


def test_grid_factory_preserves_explicit_expected_round_trip_cost_override():
    cost_config = ExecutionCostConfig(
        cost_profile="paper_current_taker",
        taker_fee_bps=40.0,
        maker_fee_bps=25.0,
        fallback_spread_bps=8.0,
        slippage_bps=3.0,
        latency_buffer_bps=0.0,
    )

    generator = make_signal_generator_factory(
        "grid",
        {"estimated_round_trip_cost_bps": 77.0},
        cost_config=cost_config,
    )()

    assert generator.config.estimated_round_trip_cost_bps == pytest.approx(77.0)


def test_validation_runner_runs_backtest_from_csv(tmp_path):
    csv_path = tmp_path / "bars.csv"
    _write_grid_csv(csv_path)
    config = ValidationRunnerConfig(
        run_id="pytest_runner_backtest",
        strategy="grid",
        data_source="csv",
        data_path=csv_path,
        symbol="TRXEUR",
        dataset_id="pytest_csv",
        output_dir=tmp_path / "reports",
        min_closed_trades=1,
        cost_config=ExecutionCostConfig(taker_fee_bps=0.0, fallback_spread_bps=0.0, slippage_bps=0.0),
        strategy_config={"range_percent": 4.0, "num_levels": 5, "entry_touch_bps": 20.0, "take_profit_bps": 40.0},
    )

    result = run_validation(config)

    assert result.mode == "backtest"
    assert result.bar_count == 3
    assert result.result.strategy_id == "dynamic_grid"
    assert result.result.trade_count == 1
    assert (tmp_path / "reports" / "backtests" / "pytest_runner_backtest.md").exists()


def test_validation_runner_filters_multi_symbol_csv_to_requested_symbol(tmp_path):
    csv_path = tmp_path / "bars.csv"
    csv_path.write_text(
        "\n".join(
            [
                "timestamp,symbol,timeframe,open,high,low,close,volume",
                "2026-05-31T00:00:00+00:00,TRXEUR,1m,1.0,1.1,0.9,1.0,1000",
                "2026-05-31T00:01:00+00:00,XXBTZEUR,1m,65000,65100,64900,65000,1000",
                "2026-05-31T00:02:00+00:00,BTCZEUR,1m,65010,65110,64910,65010,1000",
            ]
        ),
        encoding="utf-8",
    )
    config = ValidationRunnerConfig(
        run_id="pytest_runner_csv_symbol_filter",
        strategy="grid",
        data_source="csv",
        data_path=csv_path,
        symbol="BTCZEUR",
        dataset_id="pytest_multi_symbol_csv",
    )

    bars = load_bars_for_validation(config)

    assert [bar.symbol for bar in bars] == ["BTCZEUR", "BTCZEUR"]
    assert [bar.close for bar in bars] == [65000.0, 65010.0]
    assert bars[0].metadata["raw_symbol"] == "XXBTZEUR"


def test_validation_runner_applies_time_filters_to_csv(tmp_path):
    csv_path = tmp_path / "bars.csv"
    csv_path.write_text(
        "\n".join(
            [
                "timestamp,symbol,timeframe,open,high,low,close,volume",
                "2026-05-31T00:00:00+00:00,TRXEUR,1m,1.0,1.1,0.9,1.0,1000",
                "2026-05-31T00:01:00+00:00,TRXEUR,1m,1.1,1.2,1.0,1.1,1000",
                "2026-05-31T00:02:00+00:00,TRXEUR,1m,1.2,1.3,1.1,1.2,1000",
                "2026-05-31T00:03:00+00:00,TRXEUR,1m,1.3,1.4,1.2,1.3,1000",
            ]
        ),
        encoding="utf-8",
    )
    config = ValidationRunnerConfig(
        run_id="pytest_runner_csv_time_filter",
        strategy="grid",
        data_source="csv",
        data_path=csv_path,
        symbol="TRXEUR",
        dataset_id="pytest_csv_time_filter",
        start_at="2026-05-31T00:01:00+00:00",
        end_at="2026-05-31T00:02:00+00:00",
        limit=1,
    )

    bars = load_bars_for_validation(config)

    assert len(bars) == 1
    assert bars[0].timestamp.isoformat() == "2026-05-31T00:01:00+00:00"
    assert bars[0].close == 1.1


def test_validation_runner_canonicalizes_state_db_symbols(tmp_path):
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
                ("btc1", "XXBTZEUR", 65000.0, "2026-05-31T00:00:00+00:00", "b1", "runtime", "c1"),
                ("btc2", "XBTZEUR", 65010.0, "2026-05-31T00:01:00+00:00", "b2", "runtime", "c2"),
                ("eth1", "XETHZEUR", 3000.0, "2026-05-31T00:02:00+00:00", "b3", "runtime", "c3"),
            ],
        )
    config = ValidationRunnerConfig(
        run_id="pytest_runner_state_db_aliases",
        strategy="grid",
        data_source="autobot_state_db",
        data_path=db_path,
        symbol="BTCZEUR",
        dataset_id="pytest_state_db",
    )

    bars = load_bars_for_validation(config)

    assert [bar.symbol for bar in bars] == ["BTCZEUR", "BTCZEUR"]
    assert [bar.close for bar in bars] == [65000.0, 65010.0]
    assert bars[0].metadata["raw_symbol"] == "XXBTZEUR"


def test_validation_runner_can_attach_regime_context_to_journal(tmp_path):
    csv_path = tmp_path / "bars.csv"
    _write_grid_csv(csv_path)
    config = ValidationRunnerConfig(
        run_id="pytest_runner_regime_context",
        strategy="grid",
        data_source="csv",
        data_path=csv_path,
        symbol="TRXEUR",
        dataset_id="pytest_csv",
        output_dir=tmp_path / "reports",
        min_closed_trades=1,
        include_regime_context=True,
        cost_config=ExecutionCostConfig(taker_fee_bps=0.0, fallback_spread_bps=0.0, slippage_bps=0.0),
        strategy_config={"range_percent": 4.0, "num_levels": 5, "entry_touch_bps": 20.0, "take_profit_bps": 40.0},
    )

    result = run_validation(config)
    journal = TradeJournal.from_json(result.result.journal_path)

    assert result.result.trade_count == 1
    assert journal.records[0].metadata["entry"]["regime_context"]["symbol"] == "TRXEUR"
    assert journal.records[0].metadata["entry"]["regime_source"] == "research_regime_features"
    assert result.result.decision.live_promotion_allowed is False


def test_validation_runner_runs_walk_forward_from_csv(tmp_path):
    csv_path = tmp_path / "bars.csv"
    csv_path.write_text(
        "\n".join(
            [
                "timestamp,symbol,timeframe,open,high,low,close,volume",
                "2026-05-31T00:00:00+00:00,TRXEUR,1m,50,51,49,50,1000",
                "2026-05-31T00:01:00+00:00,TRXEUR,1m,100,101,99,100,1000",
                "2026-05-31T00:02:00+00:00,TRXEUR,1m,99.05,100,98,99.05,1000",
                "2026-05-31T00:03:00+00:00,TRXEUR,1m,99.6,100,98,99.6,1000",
                "2026-05-31T00:04:00+00:00,TRXEUR,1m,60,61,59,60,1000",
                "2026-05-31T00:05:00+00:00,TRXEUR,1m,100,101,99,100,1000",
                "2026-05-31T00:06:00+00:00,TRXEUR,1m,99.05,100,98,99.05,1000",
                "2026-05-31T00:07:00+00:00,TRXEUR,1m,99.6,100,98,99.6,1000",
            ]
        ),
        encoding="utf-8",
    )
    config = ValidationRunnerConfig(
        run_id="pytest_runner_wf",
        strategy="grid",
        data_source="csv",
        data_path=csv_path,
        symbol="TRXEUR",
        dataset_id="pytest_csv",
        mode="walk_forward",
        output_dir=tmp_path / "reports",
        min_closed_trades=1,
        train_window_bars=1,
        test_window_bars=3,
        step_window_bars=4,
        min_folds=2,
        min_passing_folds=1,
        cost_config=ExecutionCostConfig(taker_fee_bps=0.0, fallback_spread_bps=0.0, slippage_bps=0.0),
        strategy_config={"range_percent": 4.0, "num_levels": 5, "entry_touch_bps": 20.0, "take_profit_bps": 40.0},
    )

    result = run_validation(config)

    assert result.mode == "walk_forward"
    assert result.bar_count == 8
    assert result.result.fold_count == 2
    assert result.result.total_closed_trades == 2
    assert result.result.decision.live_promotion_allowed is False
    assert (tmp_path / "reports" / "walk_forward" / "pytest_runner_wf.md").exists()


def test_validation_runner_cli_outputs_json(tmp_path, capsys):
    csv_path = tmp_path / "bars.csv"
    _write_grid_csv(csv_path)

    exit_code = main(
        [
            "--run-id",
            "pytest_runner_cli",
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
    assert output["bar_count"] == 3
    assert output["result"]["strategy_id"] == "dynamic_grid"
