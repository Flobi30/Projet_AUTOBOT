"""Unified research CLI for AUTOBOT V2.

The CLI is deliberately limited to audit, research validation, scorecards and
paper reporting. It never starts runtime services, never submits Kraken orders,
and never mutates the strategy registry.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

AUTOBOT_TOP14_EUR_SYMBOLS = (
    "BTCZEUR",
    "ETHZEUR",
    "SOLEUR",
    "LTCZEUR",
    "XLMZEUR",
    "XRPZEUR",
    "TRXEUR",
    "ADAEUR",
    "LINKEUR",
    "DOTEUR",
    "BCHEUR",
    "ATOMEUR",
    "AVAXEUR",
    "AAVEEUR",
)
AUTOBOT_STANDARD_STRATEGIES = ("grid", "trend", "mean_reversion")
MATRIX_PRESETS = {
    "autobot-top14-eur": {
        "symbols": AUTOBOT_TOP14_EUR_SYMBOLS,
        "strategies": AUTOBOT_STANDARD_STRATEGIES,
        "description": "Standard AUTOBOT top-14 Kraken EUR research universe.",
    }
}


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return int(args.handler(args))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AUTOBOT V2 research and paper-report CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit = subparsers.add_parser("audit", help="Print the current research audit report status")
    audit.add_argument("--report-path", default="docs/AUTOBOT_AUDIT_REPORT.md")
    audit.add_argument("--strict", action="store_true", help="Return non-zero if the audit report is missing")
    audit.set_defaults(handler=_cmd_audit)

    build_dataset = subparsers.add_parser(
        "build-dataset",
        help="Build clean research OHLCV datasets from AUTOBOT market_price_samples",
    )
    build_dataset.add_argument("--run-id", required=True)
    build_dataset.add_argument("--state-db", required=True, help="Read-only AUTOBOT state DB containing market_price_samples")
    build_dataset.add_argument("--symbols", default=None, help="Comma-separated symbol list; omit to export all symbols")
    build_dataset.add_argument("--timeframes", default="1m,5m,15m", help="Comma-separated timeframes, e.g. 1m,5m,15m")
    build_dataset.add_argument("--start-at", default=None)
    build_dataset.add_argument("--end-at", default=None)
    build_dataset.add_argument("--limit", type=int, default=None)
    build_dataset.add_argument("--output-dir", default="data/research")
    build_dataset.add_argument("--no-csv", action="store_true", help="Do not write CSV exports")
    build_dataset.add_argument("--parquet", action="store_true", help="Also attempt Parquet exports if dependencies exist")
    build_dataset.add_argument(
        "--no-canonical-symbols",
        action="store_true",
        help="Keep raw exchange symbols instead of canonical research aliases",
    )
    build_dataset.set_defaults(handler=_cmd_build_dataset)

    backtest = subparsers.add_parser("backtest", help="Run one isolated research backtest")
    _add_validation_args(backtest)
    backtest.set_defaults(handler=lambda args: _cmd_validation(args, mode="backtest"))

    walk_forward = subparsers.add_parser("walk-forward", help="Run one isolated walk-forward validation")
    _add_validation_args(walk_forward)
    walk_forward.set_defaults(handler=lambda args: _cmd_validation(args, mode="walk_forward"))

    matrix = subparsers.add_parser("matrix", help="Run a multi-symbol research validation matrix")
    _add_matrix_args(matrix)
    matrix.set_defaults(handler=_cmd_matrix)

    validate_strategies = subparsers.add_parser(
        "validate-strategies",
        help="Build a canonical research dataset and run the standard validation matrix",
    )
    _add_validate_strategies_args(validate_strategies)
    validate_strategies.set_defaults(handler=_cmd_validate_strategies)

    standard_audit = subparsers.add_parser(
        "standard-audit",
        help="Run the full read-only AUTOBOT validation bundle from a state DB",
    )
    _add_standard_audit_args(standard_audit)
    standard_audit.set_defaults(handler=_cmd_standard_audit)

    grid_experiments = subparsers.add_parser(
        "grid-experiments",
        help="Run research-only grid improvement experiments from a state DB",
    )
    _add_grid_experiment_args(grid_experiments)
    grid_experiments.set_defaults(handler=_cmd_grid_experiments)

    paper = subparsers.add_parser("paper", help="Build a paper daily report from journal or SQLite ledgers")
    paper.add_argument("--journal-path", default=None, help="TradeJournal JSON file to summarize")
    paper.add_argument("--state-db", default=None, help="Read-only AUTOBOT state DB containing trade_ledger")
    paper.add_argument("--paper-trades-db", default=None, help="Read-only legacy paper_trades.db to summarize via FIFO")
    paper.add_argument("--decisions-path", default=None, help="Optional JSON list of paper decision records")
    paper.add_argument("--report-date", required=True, help="Daily report date in YYYY-MM-DD")
    paper.add_argument("--run-id", default=None)
    paper.add_argument("--initial-capital-eur", type=float, default=1_000.0)
    paper.add_argument("--output-dir", default="reports/paper")
    paper.add_argument("--max-daily-loss-pct", type=float, default=0.03)
    paper.add_argument("--strategy-disable-loss-pct", type=float, default=0.02)
    paper.add_argument("--max-strategy-risk-rejections", type=int, default=10)
    paper.add_argument("--no-write-report", action="store_true")
    paper.set_defaults(handler=_cmd_paper)

    compare = subparsers.add_parser(
        "compare-paper-research",
        help="Compare official paper ledger evidence with a research matrix report",
    )
    compare.add_argument("--matrix-path", required=True)
    compare.add_argument("--journal-path", default=None, help="TradeJournal JSON file to compare")
    compare.add_argument("--state-db", default=None, help="Read-only AUTOBOT state DB containing trade_ledger")
    compare.add_argument("--paper-trades-db", default=None, help="Read-only legacy paper_trades.db to compare via FIFO")
    compare.add_argument(
        "--decision-state-db",
        default=None,
        help="Optional read-only AUTOBOT state DB used to attach decision trace diagnostics",
    )
    compare.add_argument("--decision-trace-limit", type=int, default=10_000)
    compare.add_argument("--decision-trace-sample-limit", type=int, default=2_000)
    compare.add_argument("--report-date", default=None, help="Optional paper close date filter in YYYY-MM-DD")
    compare.add_argument("--run-id", required=True)
    compare.add_argument("--initial-capital-eur", type=float, default=1_000.0)
    compare.add_argument("--output-dir", default="reports/research/paper_research_comparison")
    compare.add_argument("--no-write-report", action="store_true")
    compare.set_defaults(handler=_cmd_compare_paper_research)

    cost_parity = subparsers.add_parser(
        "cost-parity",
        help="Audit read-only parity between research, official paper and shadow cost assumptions",
    )
    cost_parity.add_argument("--run-id", required=True)
    cost_parity.add_argument("--state-db", default=None, help="Read-only AUTOBOT state DB containing trade_ledger")
    cost_parity.add_argument("--trend-shadow-db", default=None, help="Read-only trend shadow SQLite DB")
    cost_parity.add_argument("--mean-reversion-shadow-db", default=None, help="Read-only mean reversion shadow SQLite DB")
    cost_parity.add_argument("--setup-shadow-db", default=None, help="Read-only setup shadow SQLite DB")
    cost_parity.add_argument("--output-dir", default="reports/research/cost_parity")
    cost_parity.add_argument("--fee-bps", type=float, default=16.0)
    cost_parity.add_argument("--spread-bps", type=float, default=8.0)
    cost_parity.add_argument("--slippage-bps", type=float, default=4.0)
    cost_parity.add_argument("--latency-buffer-bps", type=float, default=1.0)
    cost_parity.add_argument("--warning-delta-bps", type=float, default=5.0)
    cost_parity.add_argument("--slippage-anomaly-threshold-bps", type=float, default=100.0)
    cost_parity.add_argument("--no-write-report", action="store_true")
    cost_parity.set_defaults(handler=_cmd_cost_parity)

    leaderboard = subparsers.add_parser("leaderboard", help="Write a strategy scorecard from a matrix JSON report")
    leaderboard.add_argument("--matrix-path", required=True)
    leaderboard.add_argument("--output-dir", default="reports/research_scorecards")
    leaderboard.add_argument("--fees-missing", action="store_true")
    leaderboard.add_argument("--slippage-missing", action="store_true")
    leaderboard.add_argument("--baseline-included", action="store_true")
    leaderboard.add_argument("--out-of-sample-included", action="store_true")
    leaderboard.add_argument("--no-write-report", action="store_true")
    leaderboard.set_defaults(handler=_cmd_leaderboard)

    return parser


def _add_validation_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--strategy", choices=["grid", "trend", "mean_reversion"], required=True)
    parser.add_argument("--data-source", choices=["csv", "autobot_state_db"], required=True)
    parser.add_argument("--data-path", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--dataset-id", default=None)
    parser.add_argument("--output-dir", default="reports/research_validation")
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
    parser.add_argument("--fee-bps", type=float, default=16.0)
    parser.add_argument("--spread-bps", type=float, default=8.0)
    parser.add_argument("--slippage-bps", type=float, default=4.0)
    parser.add_argument("--strategy-config-json", default="{}")


def _add_matrix_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--preset", choices=sorted(MATRIX_PRESETS), default=None)
    parser.add_argument("--data-source", choices=["csv", "autobot_state_db"], required=True)
    parser.add_argument("--data-path", required=True)
    parser.add_argument("--symbols", default=None, help="Comma-separated symbol list, for example TRXEUR,BTCEUR")
    parser.add_argument("--strategies", default=None)
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
    parser.add_argument("--fee-bps", type=float, default=16.0)
    parser.add_argument("--spread-bps", type=float, default=8.0)
    parser.add_argument("--slippage-bps", type=float, default=4.0)
    parser.add_argument("--strategy-config-json", default="{}")
    parser.add_argument("--registry-path", default="docs/research/strategy_hypotheses.json")
    parser.add_argument(
        "--standard-reports",
        action="store_true",
        help="Write the standard AUTOBOT research report bundle for the matrix run.",
    )
    parser.add_argument("--write-registry-recommendations", action="store_true")
    parser.add_argument("--write-loss-attribution", action="store_true")
    parser.add_argument("--write-setup-quality", action="store_true")
    parser.add_argument("--write-strategy-regime", action="store_true")
    parser.add_argument("--write-strategy-regime-baselines", action="store_true")
    parser.add_argument("--write-strategy-regime-walk-forward", action="store_true")
    parser.add_argument("--write-strategy-scorecard", action="store_true")


def _add_validate_strategies_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--state-db", required=True, help="Read-only AUTOBOT state DB containing market_price_samples")
    parser.add_argument("--symbols", default=None, help="Comma-separated symbols; defaults to AUTOBOT top-14 EUR preset")
    parser.add_argument("--strategies", default=None, help="Comma-separated strategies; defaults to grid,trend,mean_reversion")
    parser.add_argument("--timeframe", default="5m", help="Dataset timeframe used for validation, e.g. 1m,5m,15m")
    parser.add_argument("--mode", choices=["backtest", "walk_forward"], default="backtest")
    parser.add_argument("--dataset-output-dir", default=None)
    parser.add_argument("--output-dir", default="reports/research_standard")
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
    parser.add_argument("--fee-bps", type=float, default=16.0)
    parser.add_argument("--spread-bps", type=float, default=8.0)
    parser.add_argument("--slippage-bps", type=float, default=4.0)
    parser.add_argument("--strategy-config-json", default="{}")
    parser.add_argument("--registry-path", default="docs/research/strategy_hypotheses.json")
    parser.add_argument("--parquet", action="store_true", help="Also attempt Parquet dataset export if dependencies exist")


def _add_standard_audit_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--state-db", required=True, help="Read-only AUTOBOT state DB")
    parser.add_argument("--symbols", default=None, help="Comma-separated symbols; defaults to AUTOBOT top-14 EUR preset")
    parser.add_argument("--strategies", default=None, help="Comma-separated strategies; defaults to grid,trend,mean_reversion")
    parser.add_argument("--timeframe", default="5m", help="Dataset timeframe used for validation, e.g. 1m,5m,15m")
    parser.add_argument("--mode", choices=["backtest", "walk_forward"], default="backtest")
    parser.add_argument("--report-date", default=None, help="Paper daily report date; defaults to latest realized close")
    parser.add_argument("--dataset-output-dir", default=None)
    parser.add_argument("--output-dir", default="reports/research_standard")
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
    parser.add_argument(
        "--skip-standard-reports",
        action="store_true",
        help="Skip expensive matrix annex reports for broad quick evidence runs",
    )
    parser.add_argument("--fee-bps", type=float, default=16.0)
    parser.add_argument("--spread-bps", type=float, default=8.0)
    parser.add_argument("--slippage-bps", type=float, default=4.0)
    parser.add_argument("--strategy-config-json", default="{}")
    parser.add_argument("--registry-path", default="docs/research/strategy_hypotheses.json")
    parser.add_argument("--trend-shadow-db", default=None)
    parser.add_argument("--mean-reversion-shadow-db", default=None)
    parser.add_argument("--setup-shadow-db", default=None)
    parser.add_argument("--decision-trace-limit", type=int, default=10_000)
    parser.add_argument("--decision-trace-sample-limit", type=int, default=2_000)
    parser.add_argument("--pnl-causality-window-hours", type=int, default=720)
    parser.add_argument("--parquet", action="store_true", help="Also attempt Parquet dataset export if dependencies exist")


def _add_grid_experiment_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--state-db", required=True, help="Read-only AUTOBOT state DB containing market_price_samples")
    parser.add_argument("--symbols", required=True, help="Comma-separated symbols, e.g. TRXEUR,BTCEUR")
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--output-dir", default="reports/research/grid_experiments")
    parser.add_argument("--dataset-output-dir", default="data/research/grid_experiments")
    parser.add_argument("--initial-capital-eur", type=float, default=1_000.0)
    parser.add_argument("--order-notional-eur", type=float, default=100.0)
    parser.add_argument("--start-at", default=None)
    parser.add_argument("--end-at", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--fee-bps", type=float, default=16.0)
    parser.add_argument("--spread-bps", type=float, default=8.0)
    parser.add_argument("--slippage-bps", type=float, default=4.0)
    parser.add_argument("--latency-buffer-bps", type=float, default=1.0)
    parser.add_argument("--min-closed-trades", type=int, default=30)
    parser.add_argument("--candidate-min-closed-trades", type=int, default=100)
    parser.add_argument("--candidate-min-profit-factor", type=float, default=1.20)
    parser.add_argument("--candidate-min-mfe-to-cost", type=float, default=1.50)
    parser.add_argument("--candidate-max-drawdown-pct", type=float, default=12.0)
    parser.add_argument("--train-window-bars", type=int, default=200)
    parser.add_argument("--test-window-bars", type=int, default=100)
    parser.add_argument("--step-window-bars", type=int, default=None)
    parser.add_argument("--min-folds", type=int, default=3)
    parser.add_argument("--max-variants", type=int, default=None)
    parser.add_argument(
        "--no-regime-context",
        action="store_true",
        help="Do not enrich experiment bars with research regime context",
    )


def _cmd_audit(args: argparse.Namespace) -> int:
    report_path = Path(args.report_path)
    payload = {
        "command": "audit",
        "report_path": str(report_path),
        "exists": report_path.exists(),
        "live_trading_changed": False,
        "registry_mutated": False,
        "safety_notes": [
            "CLI audit command is read-only.",
            "No runtime paper/live service is started.",
            "No Kraken order can be created by this command.",
        ],
    }
    if report_path.exists():
        payload["bytes"] = report_path.stat().st_size
    _print_json(payload)
    return 0 if payload["exists"] or not args.strict else 1


def _cmd_build_dataset(args: argparse.Namespace) -> int:
    from autobot.v2.research.dataset_builder import DatasetBuildConfig, build_dataset_from_state_db

    symbols = _csv_tuple(args.symbols, "--symbols", uppercase=True) if args.symbols else ()
    timeframes = _csv_tuple(args.timeframes, "--timeframes")
    config = DatasetBuildConfig(
        run_id=args.run_id,
        state_db_path=Path(args.state_db),
        output_dir=Path(args.output_dir),
        symbols=symbols,
        timeframes=timeframes,
        start_at=args.start_at,
        end_at=args.end_at,
        limit=args.limit,
        export_csv=not args.no_csv,
        export_parquet=bool(args.parquet),
        canonicalize_symbols=not args.no_canonical_symbols,
    )
    result = build_dataset_from_state_db(config)
    _print_json(result.to_dict())
    return 0


def _cmd_validation(args: argparse.Namespace, *, mode: str) -> int:
    from autobot.v2.research.execution_cost_model import ExecutionCostConfig
    from autobot.v2.research.validation_runner import ValidationRunnerConfig, run_validation

    strategy_config = _loads_object(args.strategy_config_json, "--strategy-config-json")
    config = ValidationRunnerConfig(
        run_id=args.run_id,
        strategy=args.strategy,
        data_source=args.data_source,
        data_path=Path(args.data_path),
        symbol=args.symbol.upper(),
        dataset_id=args.dataset_id or f"{args.data_source}:{args.symbol.upper()}",
        mode=mode,
        output_dir=Path(args.output_dir),
        initial_capital_eur=args.initial_capital_eur,
        order_notional_eur=args.order_notional_eur,
        min_closed_trades=args.min_closed_trades,
        min_profit_factor=args.min_profit_factor,
        max_drawdown_pct=args.max_drawdown_pct,
        min_signal_net_edge_bps=args.min_signal_net_edge_bps,
        cost_config=ExecutionCostConfig(
            taker_fee_bps=args.fee_bps,
            fallback_spread_bps=args.spread_bps,
            slippage_bps=args.slippage_bps,
        ),
        strategy_config=strategy_config,
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
    result = run_validation(config)
    payload = result.to_dict()
    payload["safety_notes"] = [
        "Research validation only.",
        "No strategy registry mutation is performed.",
        "No live trading permission is granted.",
    ]
    _print_json(payload)
    return 0


def _cmd_matrix(args: argparse.Namespace) -> int:
    from autobot.v2.research.execution_cost_model import ExecutionCostConfig
    from autobot.v2.research.validation_matrix import MatrixRunConfig, run_validation_matrix

    preset = MATRIX_PRESETS.get(args.preset) if args.preset else None
    symbols = _resolve_csv_or_preset_tuple(
        args.symbols,
        preset,
        "symbols",
        "--symbols",
        uppercase=True,
    )
    strategies = _resolve_csv_or_preset_tuple(
        args.strategies,
        preset,
        "strategies",
        "--strategies",
        default=AUTOBOT_STANDARD_STRATEGIES,
    )
    strategy_configs = _loads_object(args.strategy_config_json, "--strategy-config-json")
    output_dir = Path(args.output_dir)
    config = MatrixRunConfig(
        run_id=args.run_id,
        data_source=args.data_source,
        data_path=Path(args.data_path),
        symbols=symbols,
        strategies=strategies,  # type: ignore[arg-type]
        mode=args.mode,
        output_dir=output_dir,
        initial_capital_eur=args.initial_capital_eur,
        order_notional_eur=args.order_notional_eur,
        min_closed_trades=args.min_closed_trades,
        min_profit_factor=args.min_profit_factor,
        max_drawdown_pct=args.max_drawdown_pct,
        min_signal_net_edge_bps=args.min_signal_net_edge_bps,
        cost_config=ExecutionCostConfig(
            taker_fee_bps=args.fee_bps,
            fallback_spread_bps=args.spread_bps,
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
    output["preset"] = args.preset
    output["standard_reports_enabled"] = bool(args.standard_reports)

    write_registry_recommendations = args.write_registry_recommendations or args.standard_reports
    write_loss_attribution = args.write_loss_attribution or args.standard_reports
    write_setup_quality = args.write_setup_quality or args.standard_reports
    write_strategy_regime = args.write_strategy_regime or args.standard_reports
    write_strategy_regime_baselines = args.write_strategy_regime_baselines or args.standard_reports
    write_strategy_regime_walk_forward = args.write_strategy_regime_walk_forward or args.standard_reports
    write_strategy_scorecard = args.write_strategy_scorecard or args.standard_reports

    _attach_matrix_report_bundle(
        config=config,
        result=result,
        output=output,
        output_dir=output_dir,
        registry_path=Path(args.registry_path),
        mode=args.mode,
        write_registry_recommendations=write_registry_recommendations,
        write_loss_attribution=write_loss_attribution,
        write_setup_quality=write_setup_quality,
        write_strategy_regime=write_strategy_regime,
        write_strategy_regime_baselines=write_strategy_regime_baselines,
        write_strategy_regime_walk_forward=write_strategy_regime_walk_forward,
        write_strategy_scorecard=write_strategy_scorecard,
    )

    output["safety_notes"] = [
        "Research matrix only.",
        "No strategy registry mutation is performed by this command.",
        "No runtime paper/live service is started.",
        "No Kraken order can be created by this command.",
        "No live trading permission is granted.",
    ]
    _print_json(output)
    return 0


def _cmd_validate_strategies(args: argparse.Namespace) -> int:
    from autobot.v2.research.dataset_builder import DatasetBuildConfig, build_dataset_from_state_db
    from autobot.v2.research.execution_cost_model import ExecutionCostConfig
    from autobot.v2.research.validation_matrix import MatrixRunConfig, run_validation_matrix

    symbols = _csv_tuple(args.symbols, "--symbols", uppercase=True) if args.symbols else AUTOBOT_TOP14_EUR_SYMBOLS
    strategies = (
        _csv_tuple(args.strategies, "--strategies")
        if args.strategies
        else AUTOBOT_STANDARD_STRATEGIES
    )
    strategy_configs = _loads_object(args.strategy_config_json, "--strategy-config-json")
    dataset_output_dir = Path(args.dataset_output_dir) if args.dataset_output_dir else Path("data/research") / args.run_id
    dataset_run_id = f"{args.run_id}_dataset"
    timeframe = args.timeframe.lower()
    dataset_result = build_dataset_from_state_db(
        DatasetBuildConfig(
            run_id=dataset_run_id,
            state_db_path=Path(args.state_db),
            output_dir=dataset_output_dir,
            symbols=symbols,
            timeframes=(timeframe,),
            start_at=args.start_at,
            end_at=args.end_at,
            limit=args.limit,
            export_csv=True,
            export_parquet=bool(args.parquet),
            canonicalize_symbols=True,
        )
    )
    export = next((item for item in dataset_result.exports if item.timeframe == timeframe), None)
    if export is None or not export.csv_path:
        raise ValueError(f"dataset export for timeframe {timeframe!r} did not produce a CSV path")
    output_dir = Path(args.output_dir)
    matrix_config = MatrixRunConfig(
        run_id=args.run_id,
        data_source="csv",
        data_path=Path(export.csv_path),
        symbols=symbols,
        strategies=strategies,  # type: ignore[arg-type]
        mode=args.mode,
        output_dir=output_dir,
        initial_capital_eur=args.initial_capital_eur,
        order_notional_eur=args.order_notional_eur,
        min_closed_trades=args.min_closed_trades,
        min_profit_factor=args.min_profit_factor,
        max_drawdown_pct=args.max_drawdown_pct,
        min_signal_net_edge_bps=args.min_signal_net_edge_bps,
        cost_config=ExecutionCostConfig(
            taker_fee_bps=args.fee_bps,
            fallback_spread_bps=args.spread_bps,
            slippage_bps=args.slippage_bps,
        ),
        strategy_configs=strategy_configs,
        start_at=args.start_at,
        end_at=args.end_at,
        limit=None,
        train_window_bars=args.train_window_bars,
        test_window_bars=args.test_window_bars,
        step_window_bars=args.step_window_bars,
        min_folds=args.min_folds,
        min_passing_folds=args.min_passing_folds,
        include_regime_context=args.include_regime_context,
    )
    matrix_result = run_validation_matrix(matrix_config)
    output: dict[str, Any] = {
        "command": "validate-strategies",
        "run_id": args.run_id,
        "dataset": dataset_result.to_dict(),
        "matrix": matrix_result.to_dict(),
        "preset": "autobot-top14-eur" if not args.symbols else None,
        "standard_reports_enabled": True,
    }
    _attach_matrix_report_bundle(
        config=matrix_config,
        result=matrix_result,
        output=output,
        output_dir=output_dir,
        registry_path=Path(args.registry_path),
        mode=args.mode,
        write_registry_recommendations=True,
        write_loss_attribution=True,
        write_setup_quality=True,
        write_strategy_regime=True,
        write_strategy_regime_baselines=True,
        write_strategy_regime_walk_forward=True,
        write_strategy_scorecard=True,
    )
    output["safety_notes"] = [
        "Standard research validation workflow only.",
        "Builds canonical datasets and research reports.",
        "No strategy registry mutation is performed by this command.",
        "No runtime paper/live service is started.",
        "No Kraken order can be created by this command.",
        "No live trading permission is granted.",
    ]
    _print_json(output)
    return 0


def _cmd_standard_audit(args: argparse.Namespace) -> int:
    from autobot.v2.research.execution_cost_model import ExecutionCostConfig
    from autobot.v2.research.standard_audit_runner import StandardAuditConfig, run_standard_audit

    symbols = _csv_tuple(args.symbols, "--symbols", uppercase=True) if args.symbols else AUTOBOT_TOP14_EUR_SYMBOLS
    strategies = (
        _csv_tuple(args.strategies, "--strategies")
        if args.strategies
        else AUTOBOT_STANDARD_STRATEGIES
    )
    result = run_standard_audit(
        StandardAuditConfig(
            run_id=args.run_id,
            state_db_path=Path(args.state_db),
            output_dir=Path(args.output_dir),
            dataset_output_dir=Path(args.dataset_output_dir) if args.dataset_output_dir else None,
            symbols=symbols,
            strategies=strategies,
            timeframe=args.timeframe.lower(),
            mode=args.mode,
            report_date=date.fromisoformat(args.report_date) if args.report_date else None,
            initial_capital_eur=args.initial_capital_eur,
            order_notional_eur=args.order_notional_eur,
            min_closed_trades=args.min_closed_trades,
            min_profit_factor=args.min_profit_factor,
            max_drawdown_pct=args.max_drawdown_pct,
            min_signal_net_edge_bps=args.min_signal_net_edge_bps,
            start_at=args.start_at,
            end_at=args.end_at,
            limit=args.limit,
            train_window_bars=args.train_window_bars,
            test_window_bars=args.test_window_bars,
            step_window_bars=args.step_window_bars,
            min_folds=args.min_folds,
            min_passing_folds=args.min_passing_folds,
            include_regime_context=args.include_regime_context,
            include_standard_reports=not bool(args.skip_standard_reports),
            cost_config=ExecutionCostConfig(
                taker_fee_bps=args.fee_bps,
                fallback_spread_bps=args.spread_bps,
                slippage_bps=args.slippage_bps,
            ),
            strategy_configs=_loads_object(args.strategy_config_json, "--strategy-config-json"),
            registry_path=Path(args.registry_path),
            trend_shadow_db_path=Path(args.trend_shadow_db) if args.trend_shadow_db else None,
            mean_reversion_shadow_db_path=(
                Path(args.mean_reversion_shadow_db) if args.mean_reversion_shadow_db else None
            ),
            setup_shadow_db_path=Path(args.setup_shadow_db) if args.setup_shadow_db else None,
            decision_trace_limit=args.decision_trace_limit,
            decision_trace_sample_limit=args.decision_trace_sample_limit,
            pnl_causality_window_hours=args.pnl_causality_window_hours,
            export_parquet=bool(args.parquet),
        )
    )
    _print_json(result.to_dict())
    return 0


def _cmd_grid_experiments(args: argparse.Namespace) -> int:
    from autobot.v2.research.execution_cost_model import ExecutionCostConfig
    from autobot.v2.research.grid_experiment_runner import GridExperimentConfig, run_grid_experiments

    symbols = _csv_tuple(args.symbols, "--symbols", uppercase=True)
    result = run_grid_experiments(
        GridExperimentConfig(
            run_id=args.run_id,
            state_db_path=Path(args.state_db),
            symbols=symbols,
            timeframe=args.timeframe.lower(),
            output_dir=Path(args.output_dir),
            dataset_output_dir=Path(args.dataset_output_dir),
            initial_capital_eur=args.initial_capital_eur,
            order_notional_eur=args.order_notional_eur,
            cost_config=ExecutionCostConfig(
                taker_fee_bps=args.fee_bps,
                fallback_spread_bps=args.spread_bps,
                slippage_bps=args.slippage_bps,
                latency_buffer_bps=args.latency_buffer_bps,
            ),
            min_closed_trades=args.min_closed_trades,
            candidate_min_closed_trades=args.candidate_min_closed_trades,
            candidate_min_profit_factor=args.candidate_min_profit_factor,
            candidate_min_mfe_to_cost=args.candidate_min_mfe_to_cost,
            candidate_max_drawdown_pct=args.candidate_max_drawdown_pct,
            max_variants=args.max_variants,
            start_at=args.start_at,
            end_at=args.end_at,
            limit=args.limit,
            include_regime_context=not bool(args.no_regime_context),
            train_window_bars=args.train_window_bars,
            test_window_bars=args.test_window_bars,
            step_window_bars=args.step_window_bars,
            min_folds=args.min_folds,
        )
    )
    _print_json(result.to_dict())
    return 0


def _attach_matrix_report_bundle(
    *,
    config: Any,
    result: Any,
    output: dict[str, Any],
    output_dir: Path,
    registry_path: Path,
    mode: str,
    write_registry_recommendations: bool,
    write_loss_attribution: bool,
    write_setup_quality: bool,
    write_strategy_regime: bool,
    write_strategy_regime_baselines: bool,
    write_strategy_regime_walk_forward: bool,
    write_strategy_scorecard: bool,
) -> None:
    if write_registry_recommendations:
        from autobot.v2.research.registry_recommendations import (
            recommend_from_matrix,
            write_registry_recommendation_report,
        )
        from autobot.v2.strategy_validation_registry import load_registry

        registry_payload = load_registry(registry_path) if registry_path.exists() else None
        recommendation_report = write_registry_recommendation_report(
            recommend_from_matrix(result, registry_payload=registry_payload),
            output_dir / "registry_recommendations",
        )
        output["registry_recommendation_report"] = recommendation_report.to_dict()

    if write_loss_attribution:
        from autobot.v2.research.loss_attribution import write_matrix_loss_attribution_report

        loss_report = write_matrix_loss_attribution_report(
            result,
            output_dir / "loss_attribution",
        )
        output["loss_attribution_report"] = loss_report.to_dict()

    if write_setup_quality:
        from autobot.v2.research.setup_quality import write_matrix_setup_quality_report

        setup_report = write_matrix_setup_quality_report(
            result,
            output_dir / "setup_quality",
        )
        output["setup_quality_report"] = setup_report.to_dict()

    if write_strategy_regime:
        from autobot.v2.research.strategy_regime_report import write_matrix_strategy_regime_report

        strategy_regime_report = write_matrix_strategy_regime_report(
            result,
            output_dir / "strategy_regime",
        )
        output["strategy_regime_report"] = strategy_regime_report.to_dict()

    if write_strategy_regime_baselines:
        from autobot.v2.research.strategy_regime_baselines import write_matrix_strategy_regime_baseline_report

        baseline_report = write_matrix_strategy_regime_baseline_report(
            config,
            result,
            output_dir / "strategy_regime_baselines",
        )
        output["strategy_regime_baseline_report"] = baseline_report.to_dict()

    if write_strategy_regime_walk_forward:
        from autobot.v2.research.strategy_regime_walk_forward import write_matrix_strategy_regime_walk_forward_report

        walk_forward_report = write_matrix_strategy_regime_walk_forward_report(
            config,
            result,
            output_dir / "strategy_regime_walk_forward",
        )
        output["strategy_regime_walk_forward_report"] = walk_forward_report.to_dict()

    if write_strategy_scorecard:
        from autobot.v2.research.strategy_scorecard import score_matrix, write_strategy_scorecard_report

        scorecard_report = write_strategy_scorecard_report(
            score_matrix(
                result,
                fees_included=True,
                slippage_included=True,
                baseline_included=write_strategy_regime_baselines,
                out_of_sample_included=(mode == "walk_forward" or write_strategy_regime_walk_forward),
            ),
            output_dir / "strategy_scorecard",
        )
        output["strategy_scorecard_report"] = scorecard_report.to_dict()


def _cmd_paper(args: argparse.Namespace) -> int:
    from autobot.v2.paper.ledger_loader import load_paper_trades_db_journal, load_state_db_paper_ledger
    from autobot.v2.paper.paper_trading_engine import PaperDailyConfig, PaperDecisionRecord, PaperTradingEngine
    from autobot.v2.research.trade_journal import TradeJournal

    source_count = sum(1 for value in (args.journal_path, args.state_db, args.paper_trades_db) if value)
    if source_count != 1:
        raise ValueError("paper command requires exactly one of --journal-path, --state-db, or --paper-trades-db")
    report_date = date.fromisoformat(args.report_date)
    loader_summary = None
    if args.state_db:
        loaded = load_state_db_paper_ledger(args.state_db, report_date=report_date)
        journal = loaded.journal
        decisions = list(loaded.decisions)
        loader_summary = loaded.to_dict()
    elif args.paper_trades_db:
        loaded = load_paper_trades_db_journal(args.paper_trades_db, report_date=report_date)
        journal = loaded.journal
        decisions = []
        loader_summary = loaded.to_dict()
    else:
        journal = TradeJournal.from_json(args.journal_path)
        decisions = _load_paper_decisions(Path(args.decisions_path), PaperDecisionRecord) if args.decisions_path else []
    config = PaperDailyConfig(
        report_date=report_date,
        run_id=args.run_id,
        initial_capital_eur=args.initial_capital_eur,
        output_dir=Path(args.output_dir),
        max_daily_loss_pct=args.max_daily_loss_pct,
        strategy_disable_loss_pct=args.strategy_disable_loss_pct,
        max_strategy_risk_rejections=args.max_strategy_risk_rejections,
    )
    report = PaperTradingEngine(config).build_daily_report(
        journal,
        decisions,
        write_report=not args.no_write_report,
    )
    payload = report.to_dict()
    if loader_summary is not None:
        payload["loader"] = loader_summary
    payload["safety_notes"] = [
        "Paper report only.",
        "No orders are created by this CLI command.",
        "No live trading permission is granted.",
    ]
    _print_json(payload)
    return 0


def _cmd_compare_paper_research(args: argparse.Namespace) -> int:
    from autobot.v2.paper.ledger_loader import load_paper_trades_db_journal, load_state_db_paper_ledger
    from autobot.v2.research.decision_trace_audit import DecisionTraceAuditConfig, audit_decision_traces
    from autobot.v2.research.paper_research_comparison import (
        compare_paper_to_research,
        write_paper_research_comparison_report,
    )
    from autobot.v2.research.registry_recommendations import load_matrix_result
    from autobot.v2.research.trade_journal import TradeJournal

    source_count = sum(1 for value in (args.journal_path, args.state_db, args.paper_trades_db) if value)
    if source_count != 1:
        raise ValueError(
            "compare-paper-research requires exactly one of --journal-path, --state-db, or --paper-trades-db"
        )
    report_date = date.fromisoformat(args.report_date) if args.report_date else None
    loader_summary = None
    if args.state_db:
        loaded = load_state_db_paper_ledger(args.state_db, report_date=report_date)
        journal = loaded.journal
        paper_source_type = loaded.source_type
        paper_source_path = loaded.source_path
        warnings = loaded.warnings
        loader_summary = loaded.to_dict()
    elif args.paper_trades_db:
        loaded = load_paper_trades_db_journal(args.paper_trades_db, report_date=report_date)
        journal = loaded.journal
        paper_source_type = loaded.source_type
        paper_source_path = loaded.source_path
        warnings = loaded.warnings
        loader_summary = loaded.to_dict()
    else:
        journal = TradeJournal.from_json(args.journal_path)
        paper_source_type = "trade_journal_json"
        paper_source_path = str(Path(args.journal_path))
        warnings = ()

    matrix = load_matrix_result(args.matrix_path)
    decision_trace_report = None
    decision_state_db = args.decision_state_db or args.state_db
    if decision_state_db:
        decision_trace_report = audit_decision_traces(
            DecisionTraceAuditConfig(
                state_db_path=str(decision_state_db),
                run_id=f"{args.run_id}_decision_trace",
                limit=args.decision_trace_limit,
                trace_sample_limit=args.decision_trace_sample_limit,
            )
        )
    report = compare_paper_to_research(
        journal,
        matrix,
        run_id=args.run_id,
        paper_source_type=paper_source_type,
        paper_source_path=paper_source_path,
        initial_capital_eur=args.initial_capital_eur,
        warnings=warnings,
        decision_trace_report=decision_trace_report,
    )
    if not args.no_write_report:
        report = write_paper_research_comparison_report(report, args.output_dir)
    payload = report.to_dict()
    if loader_summary is not None:
        payload["loader"] = loader_summary
    if decision_trace_report is not None:
        payload["decision_trace_audit_summary"] = decision_trace_report.summary.to_dict()
    _print_json(payload)
    return 0


def _cmd_cost_parity(args: argparse.Namespace) -> int:
    from autobot.v2.research.cost_parity_audit import (
        CostParityAuditConfig,
        audit_cost_parity,
        write_cost_parity_audit_report,
    )
    from autobot.v2.research.execution_cost_model import ExecutionCostConfig

    config = CostParityAuditConfig(
        run_id=args.run_id,
        state_db_path=args.state_db,
        trend_shadow_db_path=args.trend_shadow_db,
        mean_reversion_shadow_db_path=args.mean_reversion_shadow_db,
        setup_shadow_db_path=args.setup_shadow_db,
        output_dir=Path(args.output_dir),
        research_cost_config=ExecutionCostConfig(
            taker_fee_bps=args.fee_bps,
            fallback_spread_bps=args.spread_bps,
            slippage_bps=args.slippage_bps,
            latency_buffer_bps=args.latency_buffer_bps,
        ),
        warning_delta_bps=args.warning_delta_bps,
        slippage_anomaly_threshold_bps=args.slippage_anomaly_threshold_bps,
    )
    report = audit_cost_parity(config)
    if not args.no_write_report:
        report = write_cost_parity_audit_report(report, args.output_dir)
    _print_json(report.to_dict())
    return 0


def _cmd_leaderboard(args: argparse.Namespace) -> int:
    from autobot.v2.research.registry_recommendations import load_matrix_result
    from autobot.v2.research.strategy_scorecard import score_matrix, write_strategy_scorecard_report

    matrix = load_matrix_result(args.matrix_path)
    report = score_matrix(
        matrix,
        fees_included=not args.fees_missing,
        slippage_included=not args.slippage_missing,
        baseline_included=args.baseline_included,
        out_of_sample_included=args.out_of_sample_included,
    )
    if not args.no_write_report:
        report = write_strategy_scorecard_report(report, args.output_dir)
    payload = report.to_dict()
    payload["safety_notes"] = list(report.safety_notes) + [
        "Leaderboard command does not mutate the strategy registry.",
        "No live trading permission is granted.",
    ]
    _print_json(payload)
    return 0


def _load_paper_decisions(path: Path, record_cls: type) -> list[Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("paper decisions JSON must contain a list")
    decisions = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("paper decision rows must be JSON objects")
        decisions.append(
            record_cls(
                timestamp=_parse_datetime(item["timestamp"]),
                strategy_id=str(item["strategy_id"]),
                symbol=str(item["symbol"]),
                action=str(item["action"]),
                status=str(item["status"]),
                reason=str(item.get("reason") or ""),
                risk_blockers=tuple(str(value) for value in item.get("risk_blockers", ())),
                risk_warnings=tuple(str(value) for value in item.get("risk_warnings", ())),
                metadata=dict(item.get("metadata") or {}),
            )
        )
    return decisions


def _loads_object(text: str, label: str) -> dict[str, Any]:
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must decode to a JSON object")
    return payload


def _csv_tuple(text: str, label: str, *, uppercase: bool = False) -> tuple[str, ...]:
    values = []
    for item in text.split(","):
        value = item.strip()
        if not value:
            continue
        values.append(value.upper() if uppercase else value)
    if not values:
        raise ValueError(f"{label} must contain at least one value")
    return tuple(values)


def _resolve_csv_or_preset_tuple(
    text: str | None,
    preset: dict[str, Any] | None,
    preset_key: str,
    label: str,
    *,
    uppercase: bool = False,
    default: tuple[str, ...] | None = None,
) -> tuple[str, ...]:
    if text is not None:
        return _csv_tuple(text, label, uppercase=uppercase)
    if preset is not None:
        values = tuple(str(value) for value in preset[preset_key])
        return tuple(value.upper() for value in values) if uppercase else values
    if default is not None:
        return default
    raise ValueError(f"{label} is required unless --preset supplies {preset_key}")


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
