"""Batch validation matrix for AUTOBOT research strategy families."""

from __future__ import annotations

import json
import argparse
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Sequence

from autobot.v2.cost_profiles import COST_PROFILE_NAMES, DEFAULT_RESEARCH_COST_PROFILE
from autobot.v2.strategy_validation_registry import load_registry

from .execution_cost_model import ExecutionCostConfig, execution_cost_config_for_profile
from .trade_journal import TradeJournal
from .validation_runner import DataSource, RunMode, StrategyName, ValidationRunnerConfig, run_validation


@dataclass(frozen=True)
class MatrixRunConfig:
    run_id: str
    data_source: DataSource
    data_path: Path
    symbols: tuple[str, ...]
    strategies: tuple[StrategyName, ...] = ("trend", "mean_reversion")
    mode: RunMode = "backtest"
    output_dir: Path = Path("reports/research_matrix")
    initial_capital_eur: float = 1_000.0
    order_notional_eur: float = 100.0
    min_closed_trades: int = 30
    min_profit_factor: float = 1.2
    max_drawdown_pct: float = 15.0
    min_signal_net_edge_bps: float | None = None
    cost_config: ExecutionCostConfig = field(default_factory=ExecutionCostConfig)
    strategy_configs: dict[str, dict[str, Any]] = field(default_factory=dict)
    start_at: str | None = None
    end_at: str | None = None
    limit: int | None = None
    train_window_bars: int = 200
    test_window_bars: int = 100
    step_window_bars: int | None = None
    min_folds: int = 3
    min_passing_folds: int = 2
    include_regime_context: bool = False

    def __post_init__(self) -> None:
        if not self.symbols:
            raise ValueError("symbols must not be empty")
        if not self.strategies:
            raise ValueError("strategies must not be empty")


@dataclass(frozen=True)
class MatrixCellResult:
    run_id: str
    symbol: str
    strategy: str
    mode: str
    status: str
    decision: str | None = None
    reason: str | None = None
    bar_count: int = 0
    closed_trades: int = 0
    net_pnl_eur: float | None = None
    total_return_pct: float | None = None
    profit_factor: float | None = None
    max_drawdown_pct: float | None = None
    fees_eur: float | None = None
    spread_cost_eur: float | None = None
    slippage_eur: float | None = None
    latency_cost_eur: float | None = None
    baseline_net_pnl_eur: dict[str, float] = field(default_factory=dict)
    beats_no_trade: bool | None = None
    beats_buy_and_hold: bool | None = None
    beats_random_signal_same_frequency: bool | None = None
    average_mfe_to_cost_ratio: float | None = None
    average_exit_capture_bps: float | None = None
    contract_signal_boundary_enforced: bool = False
    execution_path: str = "legacy_research_fill_model"
    input_snapshot_fingerprint: str | None = None
    cost_config: dict[str, Any] = field(default_factory=dict)
    report_path: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MatrixRunResult:
    run_id: str
    mode: str
    cell_count: int
    success_count: int
    error_count: int
    results: tuple[MatrixCellResult, ...]
    cost_config: dict[str, Any] = field(default_factory=dict)
    json_report_path: str | None = None
    markdown_report_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "mode": self.mode,
            "cell_count": self.cell_count,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "results": [result.to_dict() for result in self.results],
            "cost_config": dict(self.cost_config),
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
        }


def run_validation_matrix(config: MatrixRunConfig, *, write_reports: bool = True) -> MatrixRunResult:
    cells: list[MatrixCellResult] = []
    for symbol in config.symbols:
        for strategy in config.strategies:
            cell_run_id = f"{config.run_id}_{symbol}_{strategy}".replace("/", "_")
            runner_config = ValidationRunnerConfig(
                run_id=cell_run_id,
                strategy=strategy,
                data_source=config.data_source,
                data_path=config.data_path,
                symbol=symbol.upper(),
                dataset_id=f"{config.data_source}:{symbol.upper()}",
                mode=config.mode,
                output_dir=config.output_dir / "cells",
                initial_capital_eur=config.initial_capital_eur,
                order_notional_eur=config.order_notional_eur,
                min_closed_trades=config.min_closed_trades,
                min_profit_factor=config.min_profit_factor,
                max_drawdown_pct=config.max_drawdown_pct,
                min_signal_net_edge_bps=config.min_signal_net_edge_bps,
                cost_config=config.cost_config,
                strategy_config=dict(config.strategy_configs.get(strategy, {})),
                start_at=config.start_at,
                end_at=config.end_at,
                limit=config.limit,
                train_window_bars=config.train_window_bars,
                test_window_bars=config.test_window_bars,
                step_window_bars=config.step_window_bars,
                min_folds=config.min_folds,
                min_passing_folds=config.min_passing_folds,
                include_regime_context=config.include_regime_context,
            )
            try:
                runner_result = run_validation(runner_config)
                cells.append(_cell_from_runner_result(cell_run_id, symbol, strategy, runner_result))
            except Exception as exc:
                cells.append(
                    MatrixCellResult(
                        run_id=cell_run_id,
                        symbol=symbol.upper(),
                        strategy=strategy,
                        mode=config.mode,
                        status="error",
                        error=str(exc),
                    )
                )
    result = MatrixRunResult(
        run_id=config.run_id,
        mode=config.mode,
        cell_count=len(cells),
        success_count=sum(1 for cell in cells if cell.status == "ok"),
        error_count=sum(1 for cell in cells if cell.status == "error"),
        results=tuple(cells),
        cost_config=config.cost_config.to_dict(),
    )
    if write_reports:
        result = _write_matrix_reports(config, result)
    return result


def _cell_from_runner_result(cell_run_id: str, symbol: str, strategy: str, runner_result: Any) -> MatrixCellResult:
    # Imported lazily because loss_attribution consumes MatrixRunResult for its
    # aggregate reports and would otherwise create a module import cycle.
    from .loss_attribution import analyze_trade_journal, analyze_trade_losses

    result = runner_result.result
    if runner_result.mode == "backtest":
        metrics = result.metrics
        baseline_net_pnl = {baseline.name: baseline.net_pnl_eur for baseline in result.baselines}
        attribution = analyze_trade_journal(result.journal_path) if result.journal_path else None
        contract_boundary = bool(result.contract_signal_boundary_enforced)
        return MatrixCellResult(
            run_id=cell_run_id,
            symbol=symbol.upper(),
            strategy=strategy,
            mode=runner_result.mode,
            status="ok",
            decision=result.decision.status if contract_boundary else "research_only",
            reason=(
                result.decision.reason
                if contract_boundary
                else f"alpha_contract_boundary_missing; {result.decision.reason}"
            ),
            bar_count=runner_result.bar_count,
            closed_trades=result.trade_count,
            net_pnl_eur=metrics.total_net_pnl_eur,
            total_return_pct=metrics.total_return_pct,
            profit_factor=metrics.profit_factor,
            max_drawdown_pct=metrics.max_drawdown_pct,
            fees_eur=metrics.total_fees_eur,
            spread_cost_eur=metrics.total_spread_cost_eur,
            slippage_eur=metrics.total_slippage_eur,
            latency_cost_eur=metrics.total_latency_cost_eur,
            baseline_net_pnl_eur=baseline_net_pnl,
            beats_no_trade=_beats_baseline(metrics.total_net_pnl_eur, baseline_net_pnl, "no_trade"),
            beats_buy_and_hold=_beats_baseline(metrics.total_net_pnl_eur, baseline_net_pnl, "buy_and_hold"),
            beats_random_signal_same_frequency=_beats_baseline(
                metrics.total_net_pnl_eur,
                baseline_net_pnl,
                "random_signal_same_frequency",
            ),
            average_mfe_to_cost_ratio=attribution.average_mfe_to_cost_ratio if attribution else None,
            average_exit_capture_bps=attribution.average_exit_capture_bps if attribution else None,
            contract_signal_boundary_enforced=contract_boundary,
            execution_path=result.execution_path,
            input_snapshot_fingerprint=result.input_snapshot_fingerprint,
            cost_config=dict(result.cost_config),
            report_path=result.markdown_report_path,
        )
    fold_metrics = [fold.backtest_result.metrics for fold in result.folds]
    baseline_net_pnl = _aggregate_fold_baselines(result.folds)
    fold_records = []
    for fold in result.folds:
        journal_path = fold.backtest_result.journal_path
        if journal_path:
            fold_records.extend(TradeJournal.from_json(journal_path).records)
    attribution = analyze_trade_losses(fold_records, run_id=cell_run_id) if fold_records else None
    contract_boundary = bool(result.folds) and all(
        fold.backtest_result.contract_signal_boundary_enforced for fold in result.folds
    )
    return MatrixCellResult(
        run_id=cell_run_id,
        symbol=symbol.upper(),
        strategy=strategy,
        mode=runner_result.mode,
        status="ok",
        decision=result.decision.status if contract_boundary else "research_only",
        reason=(
            result.decision.reason
            if contract_boundary
            else f"alpha_contract_boundary_missing; {result.decision.reason}"
        ),
        bar_count=runner_result.bar_count,
        closed_trades=result.total_closed_trades,
        net_pnl_eur=result.aggregate_net_pnl_eur,
        total_return_pct=result.average_fold_return_pct,
        profit_factor=None,
        max_drawdown_pct=result.worst_fold_drawdown_pct,
        fees_eur=sum(metrics.total_fees_eur for metrics in fold_metrics),
        spread_cost_eur=sum(metrics.total_spread_cost_eur for metrics in fold_metrics),
        slippage_eur=sum(metrics.total_slippage_eur for metrics in fold_metrics),
        latency_cost_eur=sum(metrics.total_latency_cost_eur for metrics in fold_metrics),
        baseline_net_pnl_eur=baseline_net_pnl,
        beats_no_trade=_beats_baseline(result.aggregate_net_pnl_eur, baseline_net_pnl, "no_trade"),
        beats_buy_and_hold=_beats_baseline(result.aggregate_net_pnl_eur, baseline_net_pnl, "buy_and_hold"),
        beats_random_signal_same_frequency=_beats_baseline(
            result.aggregate_net_pnl_eur,
            baseline_net_pnl,
            "random_signal_same_frequency",
        ),
        average_mfe_to_cost_ratio=attribution.average_mfe_to_cost_ratio if attribution else None,
        average_exit_capture_bps=attribution.average_exit_capture_bps if attribution else None,
        contract_signal_boundary_enforced=contract_boundary,
        execution_path=(
            "alpha_contract_rolling_oos_fixed_policy"
            if contract_boundary
            else "legacy_rolling_oos_fixed_policy"
        ),
        cost_config=result.folds[0].backtest_result.cost_config if result.folds else {},
        report_path=result.markdown_report_path,
    )


def _beats_baseline(strategy_net_pnl: float, baselines: dict[str, float], name: str) -> bool | None:
    baseline = baselines.get(name)
    return None if baseline is None else float(strategy_net_pnl) > float(baseline)


def _aggregate_fold_baselines(folds: Sequence[Any]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for fold in folds:
        for baseline in fold.backtest_result.baselines:
            totals[baseline.name] = totals.get(baseline.name, 0.0) + float(baseline.net_pnl_eur)
    return totals


def _write_matrix_reports(config: MatrixRunConfig, result: MatrixRunResult) -> MatrixRunResult:
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{config.run_id}.json"
    md_path = output_dir / f"{config.run_id}.md"
    json_path.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(render_matrix_report(result), encoding="utf-8")
    return MatrixRunResult(
        run_id=result.run_id,
        mode=result.mode,
        cell_count=result.cell_count,
        success_count=result.success_count,
        error_count=result.error_count,
        results=result.results,
        cost_config=result.cost_config,
        json_report_path=str(json_path),
        markdown_report_path=str(md_path),
    )


def render_matrix_report(result: MatrixRunResult) -> str:
    sorted_cells = sorted(
        result.results,
        key=lambda cell: (
            cell.status != "ok",
            -(cell.net_pnl_eur or -10**12),
            cell.symbol,
            cell.strategy,
        ),
    )
    lines = [
        f"# Research Validation Matrix - {result.run_id}",
        "",
        f"Mode: `{result.mode}`",
        f"Cells: `{result.cell_count}`",
        f"Success: `{result.success_count}`",
        f"Errors: `{result.error_count}`",
        f"Cost config: `{json.dumps(result.cost_config, sort_keys=True)}`",
        "",
        "## Results",
        "",
        "| Symbol | Strategy | Status | Contract | Execution Path | Decision | Reason | Bars | Trades | Net PnL | Fees | Spread | Slippage | Return | PF | Max DD | No-trade | Buy & Hold | Random | MFE/Cost | Exit Capture |",
        "| --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- | ---: | ---: |",
    ]
    for cell in sorted_cells:
        lines.append(
            f"| {cell.symbol} | {cell.strategy} | {cell.status} | "
            f"{_fmt_bool(cell.contract_signal_boundary_enforced)} | {cell.execution_path} | {cell.decision or ''} | "
            f"{cell.reason or cell.error or ''} | {cell.bar_count} | {cell.closed_trades} | "
            f"{_fmt(cell.net_pnl_eur)} | {_fmt(cell.fees_eur)} | {_fmt(cell.spread_cost_eur)} | "
            f"{_fmt(cell.slippage_eur)} | {_fmt(cell.total_return_pct)} | {_fmt(cell.profit_factor)} | "
            f"{_fmt(cell.max_drawdown_pct)} | {_fmt_bool(cell.beats_no_trade)} | "
            f"{_fmt_bool(cell.beats_buy_and_hold)} | {_fmt_bool(cell.beats_random_signal_same_frequency)} | "
            f"{_fmt(cell.average_mfe_to_cost_ratio)} | {_fmt(cell.average_exit_capture_bps)} |"
        )
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "This matrix is research-only. It does not authorize live trading and does not update the strategy registry automatically.",
            "",
        ]
    )
    return "\n".join(lines)


def _fmt(value: float | None) -> str:
    return "" if value is None else f"{value:.6f}"


def _fmt_bool(value: bool | None) -> str:
    if value is None:
        return ""
    return "yes" if value else "no"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run AUTOBOT research validation matrix")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--data-source", choices=["csv", "autobot_state_db"], required=True)
    parser.add_argument("--data-path", required=True)
    parser.add_argument("--symbols", required=True, help="Comma-separated symbol list, for example TRXEUR,BTCEUR")
    parser.add_argument("--strategies", default="trend,mean_reversion")
    parser.add_argument("--mode", choices=["backtest", "walk_forward"], default="backtest")
    parser.add_argument("--output-dir", default="reports/research_matrix")
    parser.add_argument("--initial-capital-eur", type=float, default=1_000.0)
    parser.add_argument("--order-notional-eur", type=float, default=100.0)
    parser.add_argument("--min-closed-trades", type=int, default=30)
    parser.add_argument("--min-profit-factor", type=float, default=1.2)
    parser.add_argument("--max-drawdown-pct", type=float, default=15.0)
    parser.add_argument("--min-signal-net-edge-bps", type=float, default=None)
    parser.add_argument("--start-at", default=None)
    parser.add_argument("--end-at", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--train-window-bars", type=int, default=200)
    parser.add_argument("--test-window-bars", type=int, default=100)
    parser.add_argument("--step-window-bars", type=int, default=None)
    parser.add_argument("--min-folds", type=int, default=3)
    parser.add_argument("--min-passing-folds", type=int, default=2)
    parser.add_argument("--include-regime-context", action="store_true")
    parser.add_argument("--cost-profile", choices=COST_PROFILE_NAMES, default=DEFAULT_RESEARCH_COST_PROFILE)
    parser.add_argument("--fee-bps", type=float, default=None)
    parser.add_argument("--spread-bps", type=float, default=None)
    parser.add_argument("--slippage-bps", type=float, default=None)
    parser.add_argument("--strategy-config-json", default="{}")
    parser.add_argument("--registry-path", default="docs/research/strategy_hypotheses.json")
    parser.add_argument("--write-registry-recommendations", action="store_true")
    parser.add_argument("--write-loss-attribution", action="store_true")
    parser.add_argument("--write-setup-quality", action="store_true")
    parser.add_argument("--write-strategy-regime", action="store_true")
    parser.add_argument("--write-strategy-regime-baselines", action="store_true")
    parser.add_argument("--write-strategy-regime-walk-forward", action="store_true")
    parser.add_argument("--write-strategy-scorecard", action="store_true")
    args = parser.parse_args(argv)

    symbols = tuple(item.strip().upper() for item in args.symbols.split(",") if item.strip())
    strategies = tuple(item.strip() for item in args.strategies.split(",") if item.strip())
    strategy_configs = json.loads(args.strategy_config_json)
    if not isinstance(strategy_configs, dict):
        raise ValueError("--strategy-config-json must decode to an object")

    config = MatrixRunConfig(
        run_id=args.run_id,
        data_source=args.data_source,
        data_path=Path(args.data_path),
        symbols=symbols,
        strategies=strategies,
        mode=args.mode,
        output_dir=Path(args.output_dir),
        initial_capital_eur=args.initial_capital_eur,
        order_notional_eur=args.order_notional_eur,
        min_closed_trades=args.min_closed_trades,
        min_profit_factor=args.min_profit_factor,
        max_drawdown_pct=args.max_drawdown_pct,
        min_signal_net_edge_bps=args.min_signal_net_edge_bps,
        cost_config=execution_cost_config_for_profile(
            args.cost_profile,
            fee_bps=args.fee_bps,
            spread_bps=args.spread_bps,
            slippage_bps=args.slippage_bps,
        ),
        strategy_configs=strategy_configs,
        start_at=args.start_at,
        end_at=args.end_at,
        limit=args.limit,
        train_window_bars=args.train_window_bars,
        test_window_bars=args.test_window_bars,
        step_window_bars=args.step_window_bars,
        min_folds=args.min_folds,
        min_passing_folds=args.min_passing_folds,
        include_regime_context=args.include_regime_context,
    )
    result = run_validation_matrix(config)
    output: dict[str, Any] = result.to_dict()

    if args.write_registry_recommendations:
        from .registry_recommendations import recommend_from_matrix, write_registry_recommendation_report

        registry_payload = load_registry(args.registry_path) if Path(args.registry_path).exists() else None
        recommendation_report = write_registry_recommendation_report(
            recommend_from_matrix(result, registry_payload=registry_payload),
            Path(args.output_dir) / "registry_recommendations",
        )
        output["registry_recommendation_report"] = recommendation_report.to_dict()

    if args.write_loss_attribution:
        from .loss_attribution import write_matrix_loss_attribution_report

        loss_report = write_matrix_loss_attribution_report(
            result,
            Path(args.output_dir) / "loss_attribution",
        )
        output["loss_attribution_report"] = loss_report.to_dict()

    if args.write_setup_quality:
        from .setup_quality import write_matrix_setup_quality_report

        setup_report = write_matrix_setup_quality_report(
            result,
            Path(args.output_dir) / "setup_quality",
        )
        output["setup_quality_report"] = setup_report.to_dict()

    if args.write_strategy_regime:
        from .strategy_regime_report import write_matrix_strategy_regime_report

        strategy_regime_report = write_matrix_strategy_regime_report(
            result,
            Path(args.output_dir) / "strategy_regime",
        )
        output["strategy_regime_report"] = strategy_regime_report.to_dict()

    if args.write_strategy_regime_baselines:
        from .strategy_regime_baselines import write_matrix_strategy_regime_baseline_report

        baseline_report = write_matrix_strategy_regime_baseline_report(
            config,
            result,
            Path(args.output_dir) / "strategy_regime_baselines",
        )
        output["strategy_regime_baseline_report"] = baseline_report.to_dict()

    if args.write_strategy_regime_walk_forward:
        from .strategy_regime_walk_forward import write_matrix_strategy_regime_walk_forward_report

        walk_forward_report = write_matrix_strategy_regime_walk_forward_report(
            config,
            result,
            Path(args.output_dir) / "strategy_regime_walk_forward",
        )
        output["strategy_regime_walk_forward_report"] = walk_forward_report.to_dict()

    if args.write_strategy_scorecard:
        from .strategy_scorecard import score_matrix, write_strategy_scorecard_report

        scorecard_report = write_strategy_scorecard_report(
            score_matrix(
                result,
                fees_included=True,
                slippage_included=True,
                baseline_included=args.write_strategy_regime_baselines,
                out_of_sample_included=(args.mode == "walk_forward" or args.write_strategy_regime_walk_forward),
            ),
            Path(args.output_dir) / "strategy_scorecard",
        )
        output["strategy_scorecard_report"] = scorecard_report.to_dict()

    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
