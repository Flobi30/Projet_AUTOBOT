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

from autobot.v2.cost_profiles import COST_PROFILE_NAMES, DEFAULT_RESEARCH_COST_PROFILE
from autobot.v2.research.kraken_symbol_mapping import AUTOBOT_DEFAULT_ACTIVE_SYMBOLS, detect_active_autobot_symbols

AUTOBOT_TOP14_EUR_SYMBOLS = AUTOBOT_DEFAULT_ACTIVE_SYMBOLS
AUTOBOT_STANDARD_STRATEGIES = ("trend", "mean_reversion")
MATRIX_PRESETS = {
    "autobot-top14-eur": {
        "symbols": AUTOBOT_TOP14_EUR_SYMBOLS,
        "strategies": AUTOBOT_STANDARD_STRATEGIES,
        "description": "Standard AUTOBOT top-14 Kraken EUR research universe; grid remains archived research-only.",
    }
}


def _add_cost_profile_args(parser: argparse.ArgumentParser, *, include_latency: bool = False) -> None:
    parser.add_argument(
        "--cost-profile",
        choices=COST_PROFILE_NAMES,
        default=DEFAULT_RESEARCH_COST_PROFILE,
        help="Canonical cost profile; numeric cost flags are explicit overrides.",
    )
    parser.add_argument("--fee-bps", type=float, default=None, help="Override taker fee for this run")
    parser.add_argument("--spread-bps", type=float, default=None, help="Override fallback spread for this run")
    parser.add_argument("--slippage-bps", type=float, default=None, help="Override slippage per leg")
    if include_latency:
        parser.add_argument("--latency-buffer-bps", type=float, default=None, help="Override latency buffer per leg")


def _cost_config_from_args(args: argparse.Namespace):
    from autobot.v2.research.execution_cost_model import execution_cost_config_for_profile

    return execution_cost_config_for_profile(
        args.cost_profile,
        fee_bps=args.fee_bps,
        spread_bps=args.spread_bps,
        slippage_bps=args.slippage_bps,
        latency_buffer_bps=getattr(args, "latency_buffer_bps", None),
    )


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

    collect_history = subparsers.add_parser(
        "collect-history",
        help="Collect public Kraken OHLCV history for research datasets",
    )
    collect_history.add_argument("--run-id", required=True)
    collect_history.add_argument(
        "--symbols",
        default=None,
        help="Comma-separated symbol list; omit to use detected active AUTOBOT pairs",
    )
    collect_history.add_argument("--timeframes", default="1m,5m,15m,1h")
    collect_history.add_argument("--output-dir", default="data/research/historical")
    collect_history.add_argument("--since", type=int, default=None)
    collect_history.add_argument("--start-at", default=None, help="ISO8601 start timestamp for forward pagination")
    collect_history.add_argument("--end-at", default=None, help="ISO8601 end timestamp for forward pagination")
    collect_history.add_argument("--max-pages", type=int, default=1)
    collect_history.add_argument("--sleep-seconds", type=float, default=0.0)
    collect_history.add_argument("--dedupe", choices=["true", "false"], default="true")
    collect_history.add_argument("--fail-on-gaps", action="store_true")
    collect_history.add_argument("--no-csv", action="store_true")
    collect_history.add_argument("--no-parquet", action="store_true")
    collect_history.set_defaults(handler=_cmd_collect_history)

    collect_research_daily = subparsers.add_parser(
        "collect-research-daily",
        help="Run the isolated daily research data collection bundle",
    )
    collect_research_daily.add_argument("--config", required=True)
    collect_research_daily.add_argument("--run-id", required=True)
    collect_research_daily.set_defaults(handler=_cmd_collect_research_daily)

    data_quality = subparsers.add_parser(
        "data-quality",
        help="Analyze CSV/Parquet research datasets for gaps, volume and book availability",
    )
    data_quality.add_argument("--run-id", required=True)
    data_quality.add_argument("--paths", required=True, help="Comma-separated CSV/Parquet files")
    data_quality.add_argument("--default-timeframe", default="unknown")
    data_quality.add_argument("--output-dir", default="reports/research/data_foundation")
    data_quality.set_defaults(handler=_cmd_data_quality)

    no_trade = subparsers.add_parser(
        "no-trade-attribution",
        help="Build a read-only attribution report from decision_ledger",
    )
    no_trade.add_argument("--run-id", required=True)
    no_trade.add_argument("--state-db", required=True)
    no_trade.add_argument("--log-path", default=None)
    no_trade.add_argument("--output-dir", default="reports/research")
    no_trade.set_defaults(handler=_cmd_no_trade_attribution)

    orphan_positions = subparsers.add_parser(
        "reconcile-orphan-positions",
        help="Audit legacy open positions without modifying the database",
    )
    orphan_positions.add_argument("--run-id", required=True)
    orphan_positions.add_argument("--state-db", required=True)
    orphan_positions.add_argument("--output-dir", default="reports/research")
    orphan_positions.add_argument("--dry-run", action="store_true", required=True)
    orphan_positions.set_defaults(handler=_cmd_reconcile_orphan_positions)

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

    strategy_experiments = subparsers.add_parser(
        "strategy-experiments",
        help="Run research-only trend and mean-reversion experiments from a state DB",
    )
    _add_strategy_experiment_args(strategy_experiments)
    strategy_experiments.set_defaults(handler=_cmd_strategy_experiments)

    strategy_batch = subparsers.add_parser(
        "strategy-experiments-batch",
        help="Run read-only multi-window validation for trend/mean_reversion; grid is explicit archived research only",
    )
    _add_strategy_batch_args(strategy_batch)
    strategy_batch.set_defaults(handler=_cmd_strategy_experiments_batch)

    high_conviction = subparsers.add_parser(
        "high-conviction-swing",
        help="Replay recent signals as research-only high-conviction/swing candidates",
    )
    _add_high_conviction_swing_args(high_conviction)
    high_conviction.set_defaults(handler=_cmd_high_conviction_swing)

    high_conviction_discovery = subparsers.add_parser(
        "high-conviction-discovery",
        help="Discover research-only high-conviction/swing setups from OHLCV data",
    )
    _add_high_conviction_discovery_args(high_conviction_discovery)
    high_conviction_discovery.set_defaults(handler=_cmd_high_conviction_discovery)

    high_conviction_portfolio = subparsers.add_parser(
        "high-conviction-portfolio-replay",
        help="Replay high-conviction OHLCV setups with finite capital and portfolio constraints",
    )
    _add_high_conviction_portfolio_args(high_conviction_portfolio)
    high_conviction_portfolio.set_defaults(handler=_cmd_high_conviction_portfolio_replay)

    high_conviction_walk_forward = subparsers.add_parser(
        "high-conviction-walk-forward",
        help="Run research-only High Conviction portfolio-aware walk-forward validation",
    )
    _add_high_conviction_walk_forward_args(high_conviction_walk_forward)
    high_conviction_walk_forward.set_defaults(handler=_cmd_high_conviction_walk_forward)

    strategy_orchestrator = subparsers.add_parser(
        "strategy-orchestrator-research",
        help="Run the research-only multi-strategy score and instance treasury simulation",
    )
    _add_strategy_orchestrator_args(strategy_orchestrator)
    strategy_orchestrator.set_defaults(handler=_cmd_strategy_orchestrator_research)

    strategy_edge = subparsers.add_parser(
        "strategy-edge-review",
        help="Build research-only strategy edge triage and improvement reports",
    )
    _add_strategy_edge_review_args(strategy_edge)
    strategy_edge.set_defaults(handler=_cmd_strategy_edge_review)

    relative_value = subparsers.add_parser(
        "relative-value-portfolio-replay",
        help="Research-only Kraken Spot long-only relative-value portfolio replay",
    )
    _add_relative_value_portfolio_args(relative_value)
    relative_value.set_defaults(handler=_cmd_relative_value_portfolio_replay)

    alpha_smoke = subparsers.add_parser(
        "alpha-smoke-runner",
        help="Run bounded read-only Alpha Hypothesis Lab smoke tests",
    )
    alpha_smoke.add_argument("--run-id", required=True)
    alpha_smoke.add_argument("--data-paths", required=True, help="Comma-separated OHLCV CSV/Parquet path(s) or directories")
    alpha_smoke.add_argument("--hypotheses-path", default="docs/research/alpha_hypotheses.json")
    alpha_smoke.add_argument("--output-dir", default="reports/research/alpha_smoke")
    alpha_smoke.add_argument("--symbols", default="BTCZEUR,ETHZEUR,BCHEUR,ADAEUR,XRPZEUR,SOLEUR")
    alpha_smoke.add_argument("--cost-profile", default="research_stress")
    alpha_smoke.add_argument("--max-variants", type=int, default=5)
    alpha_smoke.add_argument("--max-symbols", type=int, default=6)
    alpha_smoke.add_argument("--max-cpu-seconds", type=float, default=60.0)
    alpha_smoke.add_argument("--order-notional-eur", type=float, default=100.0)
    alpha_smoke.add_argument("--commit", default=None, help="Optional commit SHA to stamp in the generated report")
    alpha_smoke.set_defaults(handler=_cmd_alpha_smoke_runner)

    volatility_breakout_wf = subparsers.add_parser(
        "volatility-breakout-walk-forward",
        help="Run strict research-only P18C walk-forward for volatility_breakout_high_conviction",
    )
    volatility_breakout_wf.add_argument("--run-id", required=True)
    volatility_breakout_wf.add_argument("--data-paths", required=True, help="Comma-separated OHLCV CSV/Parquet path(s) or directories")
    volatility_breakout_wf.add_argument("--output-dir", default="reports/research")
    volatility_breakout_wf.add_argument("--symbols", default="BTCZEUR,ETHZEUR,BCHEUR,ADAEUR,XRPZEUR,SOLEUR")
    volatility_breakout_wf.add_argument("--cost-profile", default="research_stress")
    volatility_breakout_wf.add_argument("--max-variants", type=int, default=5)
    volatility_breakout_wf.add_argument("--folds", type=int, default=5)
    volatility_breakout_wf.add_argument("--train-fraction", type=float, default=0.45)
    volatility_breakout_wf.add_argument("--order-notional-eur", type=float, default=100.0)
    volatility_breakout_wf.add_argument("--max-cpu-seconds", type=float, default=120.0)
    volatility_breakout_wf.add_argument("--commit", default=None, help="Optional commit SHA to stamp in the generated report")
    volatility_breakout_wf.set_defaults(handler=_cmd_volatility_breakout_walk_forward)

    alpha_hypothesis_runner = subparsers.add_parser(
        "alpha-hypothesis-runner",
        help="Run the bounded research-only Alpha Hypothesis Runner gates",
    )
    alpha_hypothesis_runner.add_argument("--hypothesis-id", required=True)
    alpha_hypothesis_runner.add_argument(
        "--mode",
        choices=["data_check", "smoke", "walk_forward", "full_research"],
        default="smoke",
    )
    alpha_hypothesis_runner.add_argument("--state-db", default=None)
    alpha_hypothesis_runner.add_argument("--data-paths", default="")
    alpha_hypothesis_runner.add_argument("--hypotheses-path", default="docs/research/alpha_hypotheses.json")
    alpha_hypothesis_runner.add_argument("--autonomy-policy", default="docs/research/alpha_autonßž»ÚÚ$z{-®éÜj×port=not args.no_write_report,
        )
    )
    _print_json(report.to_dict())
    return 0 if report.status != "FAIL" else 2


def _cmd_score_filter_simulation(args: argparse.Namespace) -> int:
    from autobot.v2.paper.score_filter_simulation import (
        ScoreFilterSimulationConfig,
        build_score_filter_simulation_report,
    )

    report = build_score_filter_simulation_report(
        ScoreFilterSimulationConfig(
            state_db_path=Path(args.state_db),
            output_dir=Path(args.output_dir),
            run_id=args.run_id,
            initial_capital_eur=args.initial_capital_eur,
            write_report=not args.no_write_report,
        )
    )
    _print_json(report.to_dict())
    return 0


def _cmd_forward_edge_simulation(args: argparse.Namespace) -> int:
    from autobot.v2.paper.forward_edge_simulation import (
        ForwardEdgeSimulationConfig,
        build_forward_edge_simulation_report,
    )

    report = build_forward_edge_simulation_report(
        ForwardEdgeSimulationConfig(
            state_db_path=Path(args.state_db),
            output_dir=Path(args.output_dir),
            run_id=args.run_id,
            initial_capital_eur=args.initial_capital_eur,
            cost_profile_name=args.cost_profile,
            top_quantile_fraction=args.top_quantile_fraction,
            write_report=not args.no_write_report,
        )
    )
    _print_json(report.to_dict())
    return 0


def _cmd_forward_edge_validation(args: argparse.Namespace) -> int:
    from autobot.v2.paper.forward_edge_validation import (
        ForwardEdgeValidationConfig,
        build_forward_edge_validation_report,
    )

    report = build_forward_edge_validation_report(
        ForwardEdgeValidationConfig(
            state_db_path=Path(args.state_db),
            since=args.since,
            since_commit=args.since_commit,
            output_dir=Path(args.output_dir),
            run_id=args.run_id,
            initial_capital_eur=args.initial_capital_eur,
            cost_profile_name=args.cost_profile,
            top_quantile_fraction=args.top_quantile_fraction,
            write_report=not args.no_write_report,
        )
    )
    _print_json(report.to_dict())
    return 0


def _cmd_opportunity_score_audit(args: argparse.Namespace) -> int:
    from autobot.v2.paper.opportunity_score_audit import (
        OpportunityScoreAuditConfig,
        build_opportunity_score_audit_report,
    )

    report = build_opportunity_score_audit_report(
        OpportunityScoreAuditConfig(
            state_db_path=Path(args.state_db),
            since=args.since,
            since_commit=args.since_commit,
            output_dir=Path(args.output_dir),
            run_id=args.run_id,
            initial_capital_eur=args.initial_capital_eur,
            cost_profile_name=args.cost_profile,
            write_report=not args.no_write_report,
        )
    )
    _print_json(report.to_dict())
    return 0


def _cmd_paper_confidence(args: argparse.Namespace) -> int:
    from autobot.v2.paper.paper_confidence import PaperConfidenceConfig, build_paper_confidence_report

    report = build_paper_confidence_report(
        PaperConfidenceConfig(
            state_db_path=Path(args.state_db),
            strategy_id=args.strategy_id,
            output_dir=Path(args.output_dir),
            run_id=args.run_id,
            initial_capital_eur=args.initial_capital_eur,
            bootstrap_iterations=args.bootstrap_iterations,
            seed=args.seed,
            write_report=not args.no_write_report,
        )
    )
    _print_json(report.to_dict())
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


def _cmd_research_paper_parity(args: argparse.Namespace) -> int:
    from autobot.v2.research.research_paper_parity import (
        ResearchPaperParityConfig,
        run_research_paper_parity,
        summarize_research_paper_parity,
    )

    symbols = _csv_tuple(args.symbols, "--symbols", uppercase=True) if args.symbols else AUTOBOT_TOP14_EUR_SYMBOLS
    strategies = _csv_tuple(args.strategies, "--strategies") if args.strategies else AUTOBOT_STANDARD_STRATEGIES
    report = run_research_paper_parity(
        ResearchPaperParityConfig(
            run_id=args.run_id,
            state_db_path=Path(args.state_db),
            symbols=symbols,
            strategies=strategies,
            output_dir=Path(args.output_dir),
            initial_capital_eur=args.initial_capital_eur,
            order_notional_eur=args.order_notional_eur,
            start_at=args.start_at,
            end_at=args.end_at,
            limit=args.limit,
            include_regime_context=bool(args.include_regime_context),
            cost_config=_cost_config_from_args(args),
        )
    )
    payload = report.to_dict()
    payload["summary"] = summarize_research_paper_parity(report)
    _print_json(payload)
    return 0


def _cmd_cost_parity(args: argparse.Namespace) -> int:
    from autobot.v2.research.cost_parity_audit import (
        CostParityAuditConfig,
        audit_cost_parity,
        write_cost_parity_audit_report,
    )

    config = CostParityAuditConfig(
        run_id=args.run_id,
        state_db_path=args.state_db,
        trend_shadow_db_path=args.trend_shadow_db,
        mean_reversion_shadow_db_path=args.mean_reversion_shadow_db,
        setup_shadow_db_path=args.setup_shadow_db,
        output_dir=Path(args.output_dir),
        research_cost_config=_cost_config_from_args(args),
        warning_delta_bps=args.warning_delta_bps,
        slippage_anomaly_threshold_bps=args.slippage_anomaly_threshold_bps,
    )
    report = audit_cost_parity(config)
    if not args.no_write_report:
        report = write_cost_parity_audit_report(report, args.output_dir)
    _print_json(report.to_dict())
    return 0


def _cmd_split_plan(args: argparse.Namespace) -> int:
    from autobot.v2.instance_split_planner import build_instance_split_plan, write_instance_split_plan

    evidence_payload = json.loads(args.evidence_json)
    if isinstance(evidence_payload, dict):
        evidence = [evidence_payload]
    elif isinstance(evidence_payload, list):
        evidence = evidence_payload
    else:
        raise ValueError("--evidence-json must be an object or list")
    if not all(isinstance(item, dict) for item in evidence):
        raise ValueError("--evidence-json list must contain objects")
    plan = write_instance_split_plan(
        build_instance_split_plan(
            run_id=args.run_id,
            state_db_path=Path(args.state_db) if args.state_db else None,
            parent_evidence=evidence,
        ),
        Path(args.output_dir),
    )
    _print_json(plan.to_dict())
    return 0


def _cmd_split_validation(args: argparse.Namespace) -> int:
    from autobot.v2.research.instance_split_validation_harness import (
        run_instance_split_validation,
    )

    evidence = json.loads(args.evidence_json)
    if not isinstance(evidence, dict):
        raise ValueError("--evidence-json must be an object")
    child_returns = tuple(
        float(item.strip())
        for item in str(args.child_return_series).split(",")
        if item.strip()
    )
    result = run_instance_split_validation(
        run_id=args.run_id,
        evidence=evidence,
        output_dir=Path(args.output_dir),
        child_return_series=child_returns,
    )
    _print_json(result.to_dict())
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


def _csv_float_tuple(text: str, label: str) -> tuple[float, ...]:
    values: list[float] = []
    for item in text.split(","):
        value = item.strip()
        if not value:
            continue
        try:
            parsed = float(value)
        except ValueError as exc:
            raise ValueError(f"{label} must contain numeric values") from exc
        if parsed <= 0:
            raise ValueError(f"{label} values must be positive")
        values.append(parsed)
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


def _parse_bool(value: str, label: str) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n"}:
        return False
    raise ValueError(f"{label} must be true or false")


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
