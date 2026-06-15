import pytest
import json

from autobot.v2.research.execution_cost_model import ExecutionCostConfig
from autobot.v2.research.validation_matrix import MatrixRunConfig, main, run_validation_matrix


pytestmark = pytest.mark.integration


def _write_csv(path):
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


def _config(tmp_path, csv_path, *, strategy_configs=None):
    return MatrixRunConfig(
        run_id="pytest_matrix",
        data_source="csv",
        data_path=csv_path,
        symbols=("TRXEUR",),
        strategies=("grid", "trend"),
        output_dir=tmp_path / "matrix",
        min_closed_trades=1,
        cost_config=ExecutionCostConfig(taker_fee_bps=0.0, fallback_spread_bps=0.0, slippage_bps=0.0),
        strategy_configs=strategy_configs
        or {
            "grid": {"range_percent": 4.0, "num_levels": 5, "entry_touch_bps": 20.0, "take_profit_bps": 40.0},
            "trend": {"breakout_window": 2, "momentum_window": 1, "atr_window": 1},
        },
    )


def test_validation_matrix_runs_strategy_symbol_grid_and_writes_summary(tmp_path):
    csv_path = tmp_path / "bars.csv"
    _write_csv(csv_path)

    result = run_validation_matrix(_config(tmp_path, csv_path))

    assert result.cell_count == 2
    assert result.success_count == 2
    assert result.error_count == 0
    assert {cell.strategy for cell in result.results} == {"grid", "trend"}
    assert all(cell.status == "ok" for cell in result.results)
    assert all(cell.report_path for cell in result.results)
    assert result.cost_config["taker_fee_bps"] == pytest.approx(0.0)
    assert all(cell.cost_config["fallback_spread_bps"] == pytest.approx(0.0) for cell in result.results)
    assert all(cell.fees_eur is not None for cell in result.results)
    assert all(cell.slippage_eur is not None for cell in result.results)
    grid_cell = next(cell for cell in result.results if cell.strategy == "grid")
    assert set(grid_cell.baseline_net_pnl_eur) == {
        "no_trade",
        "buy_and_hold",
        "random_signal_same_frequency",
    }
    assert isinstance(grid_cell.beats_no_trade, bool)
    assert isinstance(grid_cell.beats_buy_and_hold, bool)
    assert isinstance(grid_cell.beats_random_signal_same_frequency, bool)
    assert grid_cell.average_mfe_to_cost_ratio is not None
    assert grid_cell.average_exit_capture_bps is not None
    assert (tmp_path / "matrix" / "pytest_matrix.md").exists()
    assert (tmp_path / "matrix" / "pytest_matrix.json").exists()
    markdown = (tmp_path / "matrix" / "pytest_matrix.md").read_text(encoding="utf-8")
    assert "Cost config" in markdown
    assert "Slippage" in markdown
    assert "MFE/Cost" in markdown
    assert "Exit Capture" in markdown


def test_validation_matrix_records_cell_errors_without_aborting(tmp_path):
    csv_path = tmp_path / "bars.csv"
    _write_csv(csv_path)
    config = _config(
        tmp_path,
        csv_path,
        strategy_configs={
            "grid": {"unknown_parameter": True},
            "trend": {"breakout_window": 2, "momentum_window": 1, "atr_window": 1},
        },
    )

    result = run_validation_matrix(config, write_reports=False)

    assert result.cell_count == 2
    assert result.success_count == 1
    assert result.error_count == 1
    error_cell = next(cell for cell in result.results if cell.status == "error")
    assert error_cell.strategy == "grid"
    assert "unknown_parameter" in (error_cell.error or "")


def test_validation_matrix_cli_can_write_registry_recommendations(tmp_path, capsys):
    csv_path = tmp_path / "bars.csv"
    _write_csv(csv_path)
    registry_path = tmp_path / "strategy_hypotheses.json"
    registry_path.write_text(
        json.dumps({"hypotheses": [{"strategy_id": "dynamic_grid", "validation_status": "candidate"}]}),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--run-id",
            "pytest_matrix_cli",
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
            "--registry-path",
            str(registry_path),
            "--write-registry-recommendations",
            "--write-loss-attribution",
            "--write-setup-quality",
            "--write-strategy-regime",
            "--write-strategy-regime-baselines",
            "--write-strategy-regime-walk-forward",
            "--write-strategy-scorecard",
        ]
    )

    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["cell_count"] == 1
    assert output["registry_recommendation_report"]["recommendations"][0]["live_promotion_allowed"] is False
    assert output["loss_attribution_report"]["analyzed_cell_count"] == 1
    assert output["setup_quality_report"]["run_id"] == "pytest_matrix_cli_matrix"
    assert output["setup_quality_report"]["trade_count"] == 1
    assert output["strategy_regime_report"]["run_id"] == "pytest_matrix_cli_strategy_regime"
    assert output["strategy_regime_report"]["trade_count"] == 1
    assert output["strategy_regime_baseline_report"]["run_id"] == (
        "pytest_matrix_cli_strategy_regime_baseline_comparison"
    )
    assert output["strategy_regime_baseline_report"]["bucket_count"] == 1
    assert output["strategy_regime_walk_forward_report"]["run_id"] == (
        "pytest_matrix_cli_strategy_regime_walk_forward"
    )
    assert output["strategy_scorecard_report"]["run_id"] == "pytest_matrix_cli"
    assert output["strategy_scorecard_report"]["results"][0]["live_promotion_allowed"] is False
    assert (
        tmp_path
        / "matrix"
        / "registry_recommendations"
        / "pytest_matrix_cli_registry_recommendations.md"
    ).exists()
    assert (
        tmp_path
        / "matrix"
        / "loss_attribution"
        / "pytest_matrix_cli_matrix_loss_attribution.md"
    ).exists()
    assert (
        tmp_path
        / "matrix"
        / "setup_quality"
        / "pytest_matrix_cli_matrix_setup_quality.md"
    ).exists()
    assert (
        tmp_path
        / "matrix"
        / "strategy_regime"
        / "pytest_matrix_cli_strategy_regime.md"
    ).exists()
    assert (
        tmp_path
        / "matrix"
        / "strategy_regime_baselines"
        / "pytest_matrix_cli_strategy_regime_baseline_comparison.md"
    ).exists()
    assert (
        tmp_path
        / "matrix"
        / "strategy_regime_walk_forward"
        / "pytest_matrix_cli_strategy_regime_walk_forward.md"
    ).exists()
    assert (
        tmp_path
        / "matrix"
        / "strategy_scorecard"
        / "pytest_matrix_cli_strategy_scorecard.md"
    ).exists()
