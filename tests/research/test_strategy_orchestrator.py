import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from autobot.v2.cli import main as cli_main
from autobot.v2.research.strategy_orchestrator import (
    InstanceTreasury,
    StrategyMetaScore,
    StrategyOrchestratorConfig,
    StrategyPerformanceEvidence,
    StrategyResearchSignal,
    _score_evidence,
    build_strategy_orchestrator_report,
    simulate_instance_treasury,
    write_strategy_orchestrator_report,
)


pytestmark = pytest.mark.unit


def _signal(*, capital_eligible=True, net_pnl=10.0, strategy="high_conviction_swing"):
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    return StrategyResearchSignal(
        strategy_name=strategy,
        symbol="TRXEUR",
        timestamp=start,
        direction="buy",
        confidence=0.8,
        expected_move_bps=500.0,
        cost_profile="research_stress",
        regime="multi_timeframe_swing",
        reason="pytest_signal",
        instance_id="research-parent-001",
        research_only=True,
        metadata={
            "capital_eligible": capital_eligible,
            "no_capital_reason": "pytest_no_capital",
            "exit_at": (start + timedelta(hours=2)).isoformat(),
            "entry_price": 1.0,
            "exit_price": 1.1,
            "source_notional_eur": 100.0,
            "gross_pnl_eur": net_pnl + 1.0,
            "net_pnl_eur": net_pnl,
            "fees_eur": 0.5,
            "spread_cost_eur": 0.25,
            "slippage_eur": 0.15,
            "latency_cost_eur": 0.10,
            "logical_stop_bps": 100.0,
            "mae_bps": -20.0,
        },
    )


def _score(strategy="high_conviction_swing", score=80.0, status="active_research"):
    evidence = StrategyPerformanceEvidence(
        strategy_name=strategy,
        status=status,
        cost_profile="research_stress",
        signal_count=1,
        trade_count=100,
        net_pnl_eur=20.0,
        profit_factor=1.5,
        winrate_pct=55.0,
        max_drawdown_pct=5.0,
        positive_folds=5,
        total_folds=5,
        largest_positive_symbol_share=0.2,
        validation_days=10,
        costs_covered=True,
        runtime_comparable=True,
    )
    return StrategyMetaScore(
        strategy_name=strategy,
        score=score,
        status=status,
        candidate_paper_recommended=False,
        reasons=(),
        blockers=(),
        evidence=evidence,
    )


def _config(tmp_path: Path) -> StrategyOrchestratorConfig:
    return StrategyOrchestratorConfig(
        run_id="pytest_treasury",
        data_paths=(tmp_path,),
        output_dir=tmp_path / "reports",
        high_conviction_train_window_bars=48,
        high_conviction_test_window_bars=24,
        high_conviction_step_window_bars=24,
        high_conviction_min_folds=3,
        high_conviction_min_expected_move_bps=200.0,
        high_conviction_max_hold_hours=2.0,
    )


def _write(path: Path, rows: list[dict[str, object]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["timestamp", "symbol", "timeframe", "open", "high", "low", "close", "volume"],
        )
        writer.writeheader()
        writer.writerows(rows)
    return path


def _bar(timestamp: datetime, timeframe: str, price: float, spread: float) -> dict[str, object]:
    return {
        "timestamp": timestamp.isoformat(),
        "symbol": "TRXEUR",
        "timeframe": timeframe,
        "open": f"{price:.8f}",
        "high": f"{price + spread:.8f}",
        "low": f"{max(0.01, price - spread):.8f}",
        "close": f"{price:.8f}",
        "volume": "1000",
    }


def _dataset(tmp_path: Path) -> tuple[Path, ...]:
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    hourly = [_bar(start + timedelta(hours=index), "1h", 96.0 + index * 0.28, 0.55) for index in range(36)]
    fifteen = [_bar(start + timedelta(minutes=15 * index), "15m", 98.0 + index * 0.11, 0.35) for index in range(120)]
    five = [_bar(start + timedelta(minutes=5 * index), "5m", 98.0 + index * 0.04, 0.20) for index in range(420)]
    return (
        _write(tmp_path / "trx_5m.csv", five),
        _write(tmp_path / "trx_15m.csv", fifteen),
        _write(tmp_path / "trx_1h.csv", hourly),
    )


def test_treasury_sizes_only_from_realized_equity_and_not_unrealized_pnl(tmp_path):
    treasury = InstanceTreasury(
        instance_id="research-parent-001",
        parent_instance_id=None,
        instance_role="standalone",
        instance_treasury_eur=500.0,
        realized_equity_eur=500.0,
        available_cash_eur=500.0,
        reserved_exposure_eur=0.0,
        realized_pnl_eur=0.0,
        unrealized_pnl_eur=500.0,
        max_instance_exposure_pct=0.60,
        max_strategy_exposure_pct=0.50,
        max_symbol_exposure_pct=0.20,
        max_daily_loss_pct=0.03,
        max_drawdown_pct=0.10,
    )
    simulation = simulate_instance_treasury(
        treasury=treasury,
        signals=(_signal(),),
        cost_profile="research_stress",
        scores={"high_conviction_swing": _score()},
        config=_config(tmp_path),
    )

    accepted = [item for item in simulation.allocation_decisions if item.accepted]
    assert len(accepted) == 1
    assert accepted[0].sizing_equity_eur == 500.0
    assert accepted[0].allocated_notional_eur == pytest.approx(100.0)
    assert simulation.final_treasury.realized_equity_eur == pytest.approx(510.0)
    assert simulation.final_treasury.unrealized_pnl_eur == 0.0


def test_no_capital_research_signal_cannot_reserve_instance_treasury(tmp_path):
    simulation = simulate_instance_treasury(
        treasury=InstanceTreasury.starting(instance_id="research-parent-001"),
        signals=(_signal(capital_eligible=False, strategy="relative_value"),),
        cost_profile="research_stress",
        scores={"relative_value": _score("relative_value", status="no_go")},
        config=_config(tmp_path),
    )

    assert simulation.metrics["trade_count"] == 0
    assert simulation.allocation_decisions[0].accepted is False
    assert simulation.allocation_decisions[0].reason == "pytest_no_capital"


def test_candidate_paper_gate_requires_four_of_five_folds_and_all_strict_criteria():
    base = StrategyPerformanceEvidence(
        strategy_name="high_conviction_swing",
        status="active_research",
        cost_profile="research_stress",
        signal_count=60,
        trade_count=50,
        net_pnl_eur=10.0,
        profit_factor=1.31,
        winrate_pct=52.0,
        max_drawdown_pct=9.0,
        positive_folds=3,
        total_folds=5,
        largest_positive_symbol_share=0.39,
        validation_days=10,
        costs_covered=True,
        runtime_comparable=True,
    )
    treasury = InstanceTreasury.starting(instance_id="research-parent-001")
    rejected = _score_evidence(base, treasury)
    accepted = _score_evidence(
        StrategyPerformanceEvidence(**{**base.to_dict(), "positive_folds": 4}),
        treasury,
    )

    assert rejected.candidate_paper_recommended is False
    assert "fewer_than_4_of_5_positive_folds" in rejected.blockers
    assert accepted.candidate_paper_recommended is True
    assert accepted.live_promotion_allowed is False


@pytest.mark.parametrize(
    ("overrides", "blocker"),
    [
        ({"trade_count": 49}, "insufficient_closed_trades_under_50"),
        ({"profit_factor": 1.30}, "profit_factor_not_above_1_30"),
        ({"max_drawdown_pct": 10.1}, "max_drawdown_above_10_pct"),
        ({"largest_positive_symbol_share": 0.41}, "single_symbol_positive_pnl_above_40_pct"),
        ({"costs_covered": False}, "costs_not_covered"),
        ({"runtime_comparable": False}, "legacy_or_non_comparable_cost_profile"),
        ({"validation_days": 6}, "validation_window_too_short"),
    ],
)
def test_candidate_paper_gate_fails_closed_for_every_required_condition(overrides, blocker):
    payload = {
        "strategy_name": "high_conviction_swing",
        "status": "active_research",
        "cost_profile": "research_stress",
        "signal_count": 60,
        "trade_count": 50,
        "net_pnl_eur": 10.0,
        "profit_factor": 1.31,
        "winrate_pct": 52.0,
        "max_drawdown_pct": 9.0,
        "positive_folds": 4,
        "total_folds": 5,
        "largest_positive_symbol_share": 0.39,
        "validation_days": 10,
        "costs_covered": True,
        "runtime_comparable": True,
    }
    payload.update(overrides)
    result = _score_evidence(
        StrategyPerformanceEvidence(**payload),
        InstanceTreasury.starting(instance_id="research-parent-001"),
    )

    assert result.candidate_paper_recommended is False
    assert blocker in result.blockers


def test_full_orchestrator_keeps_grid_archived_and_split_executor_off(tmp_path, monkeypatch):
    monkeypatch.setenv("ENABLE_INSTANCE_SPLIT_EXECUTOR", "true")
    report = build_strategy_orchestrator_report(
        StrategyOrchestratorConfig(
            **{**_config(tmp_path).__dict__, "data_paths": _dataset(tmp_path)}
        )
    )

    statuses = {score.strategy_name: score.status for score in report.strategy_scores}
    assert statuses["grid"] == "archived"
    assert statuses["relative_value"] == "no_go"
    assert report.paper_candidate_allowed is False
    assert report.live_promotion_allowed is False
    assert report.pair_scores
    assert report.signal_scores
    assert all(score.cost_profile != "research_legacy" for score in report.signal_scores)
    assert report.simulated_child_plan.child_created is False
    assert report.simulated_child_plan.split_decision.executor_enabled is False
    assert report.simulated_child_plan.split_decision.executable_now is False
    assert report.advanced_quant_diagnostics["research_only"] is True
    assert report.advanced_quant_diagnostics["paper_candidate_allowed"] is False
    assert report.advanced_quant_diagnostics["live_promotion_allowed"] is False
    assert report.advanced_quant_diagnostics["robustness"]["verdict"] == "insufficient_sample"


def test_orchestrator_cli_writes_research_only_report(tmp_path, capsys):
    paths = _dataset(tmp_path)
    exit_code = cli_main(
        [
            "strategy-orchestrator-research",
            "--run-id",
            "pytest_orchestrator_cli",
            "--data-paths",
            ",".join(str(path) for path in paths),
            "--symbols",
            "TRXEUR",
            "--output-dir",
            str(tmp_path / "cli_reports"),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["paper_candidate_allowed"] is False
    assert payload["live_promotion_allowed"] is False
    assert payload["simulated_child_plan"]["child_created"] is False
    assert (tmp_path / "cli_reports" / "pytest_orchestrator_cli.json").exists()


def test_write_report_preserves_research_only_contract(tmp_path):
    report = build_strategy_orchestrator_report(
        StrategyOrchestratorConfig(
            **{**_config(tmp_path).__dict__, "data_paths": _dataset(tmp_path)}
        )
    )
    written = write_strategy_orchestrator_report(report, tmp_path / "written")

    assert written.json_report_path
    assert written.markdown_report_path
    assert Path(written.json_report_path).exists()
    assert "No child instance is created" in Path(written.markdown_report_path).read_text(encoding="utf-8")
