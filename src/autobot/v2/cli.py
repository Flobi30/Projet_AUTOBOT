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

    backtest = subparsers.add_parser("backtest", help="Run one isolated research backtest")
    _add_validation_args(backtest)
    backtest.set_defaults(handler=lambda args: _cmd_validation(args, mode="backtest"))

    walk_forward = subparsers.add_parser("walk-forward", help="Run one isolated walk-forward validation")
    _add_validation_args(walk_forward)
    walk_forward.set_defaults(handler=lambda args: _cmd_validation(args, mode="walk_forward"))

    matrix = subparsers.add_parser("matrix", help="Run a multi-symbol research validation matrix")
    _add_matrix_args(matrix)
    matrix.set_defaults(handler=_cmd_matrix)

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
    parser.add_argument("--data-source", choices=["csv", "autobot_state_db"], required=True)
    parser.add_argument("--data-path", required=True)
    parser.add_argument("--symbols", required=True, help="Comma-separated symbol list, for example TRXEUR,BTCEUR")
    parser.add_argument("--strategies", default="grid,trend,mean_reversion")
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
    parser.add_argument("--write-registry-recommendations", action="store_true")
    parser.add_argument("--write-loss-attribution", action="store_true")
    parser.add_argument("--write-setup-quality", action="store_true")
    parser.add_argument("--write-strategy-regime", action="store_true")
    parser.add_argument("--write-strategy-regime-baselines", action="store_true")
    parser.add_argument("--write-strategy-regime-walk-forward", action="store_true")
    parser.add_argument("--write-strategy-scorecard", action="store_true")


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

    symbols = _csv_tuple(args.symbols, "--symbols", uppercase=True)
    strategies = _csv_tuple(args.strategies, "--strategies")
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

    if args.write_registry_recommendations:
        from autobot.v2.research.registry_recommendations import (
            recommend_from_matrix,
            write_registry_recommendation_report,
        )
        from autobot.v2.strategy_validation_registry import load_registry

        registry_path = Path(args.registry_path)
        registry_payload = load_registry(registry_path) if registry_path.exists() else None
        recommendation_report = write_registry_recommendation_report(
            recommend_from_matrix(result, registry_payload=registry_payload),
            output_dir / "registry_recommendations",
        )
        output["registry_recommendation_report"] = recommendation_report.to_dict()

    if args.write_loss_attribution:
        from autobot.v2.research.loss_attribution import write_matrix_loss_attribution_report

        loss_report = write_matrix_loss_attribution_report(
            result,
            output_dir / "loss_attribution",
        )
        output["loss_attribution_report"] = loss_report.to_dict()

    if args.write_setup_quality:
        from autobot.v2.research.setup_quality import write_matrix_setup_quality_report

        setup_report = write_matrix_setup_quality_report(
            result,
            output_dir / "setup_quality",
        )
        output["setup_quality_report"] = setup_report.to_dict()

    if args.write_strategy_regime:
        from autobot.v2.research.strategy_regime_report import write_matrix_strategy_regime_report

        strategy_regime_report = write_matrix_strategy_regime_report(
            result,
            output_dir / "strategy_regime",
        )
        output["strategy_regime_report"] = strategy_regime_report.to_dict()

    if args.write_strategy_regime_baselines:
        from autobot.v2.research.strategy_regime_baselines import write_matrix_strategy_regime_baseline_report

        baseline_report = write_matrix_strategy_regime_baseline_report(
            config,
            result,
            output_dir / "strategy_regime_baselines",
        )
        output["strategy_regime_baseline_report"] = baseline_report.to_dict()

    if args.write_strategy_regime_walk_forward:
        from autobot.v2.research.strategy_regime_walk_forward import write_matrix_strategy_regime_walk_forward_report

        walk_forward_report = write_matrix_strategy_regime_walk_forward_report(
            config,
            result,
            output_dir / "strategy_regime_walk_forward",
        )
        output["strategy_regime_walk_forward_report"] = walk_forward_report.to_dict()

    if args.write_strategy_scorecard:
        from autobot.v2.research.strategy_scorecard import score_matrix, write_strategy_scorecard_report

        scorecard_report = write_strategy_scorecard_report(
            score_matrix(
                result,
                fees_included=True,
                slippage_included=True,
                baseline_included=args.write_strategy_regime_baselines,
                out_of_sample_included=(args.mode == "walk_forward" or args.write_strategy_regime_walk_forward),
            ),
            output_dir / "strategy_scorecard",
        )
        output["strategy_scorecard_report"] = scorecard_report.to_dict()

    output["safety_notes"] = [
        "Research matrix only.",
        "No strategy registry mutation is performed by this command.",
        "No runtime paper/live service is started.",
        "No Kraken order can be created by this command.",
        "No live trading permission is granted.",
    ]
    _print_json(output)
    return 0


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
