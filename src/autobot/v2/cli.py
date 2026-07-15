"""Unified research CLI for AUTOBOT V2.

The CLI is deliberately limited to audit, research validation, scorecards,
paper reporting and governed non-executable artifact registration. It never
starts runtime services, submits Kraken orders or changes runtime policy.
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
    collect_history.add_argument(
        "--parquet",
        action="store_true",
        help="Write an explicit Parquet copy with the same point-in-time timestamps as CSV",
    )
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
    alpha_hypothesis_runner.add_argument("--autonomy-policy", default="docs/research/alpha_autonomy_policy.json")
    alpha_hypothesis_runner.add_argument(
        "--output-dir",
        default="data/research/reports/alpha_hypothesis_runner",
        help="Runtime-writable output directory; copy compact decision reports into reports/ explicitly if needed.",
    )
    alpha_hypothesis_runner.add_argument("--run-id", default=None)
    alpha_hypothesis_runner.add_argument("--symbols", default="BTCZEUR,ETHZEUR,BCHEUR,ADAEUR,XRPZEUR,SOLEUR")
    alpha_hypothesis_runner.add_argument("--cost-profile", default="research_stress")
    alpha_hypothesis_runner.add_argument("--max-runtime-seconds", type=float, default=120.0)
    alpha_hypothesis_runner.add_argument("--max-variants", type=int, default=5)
    alpha_hypothesis_runner.add_argument("--max-symbols", type=int, default=6)
    alpha_hypothesis_runner.add_argument("--max-data-rows", type=int, default=250000)
    alpha_hypothesis_runner.add_argument("--commit", default=None)
    alpha_hypothesis_runner.add_argument("--templates", default="docs/research/strategy_templates.json")
    alpha_hypothesis_runner.add_argument("--template-id", default=None)
    alpha_hypothesis_runner.add_argument("--memory-path", default="data/research/alpha_research_memory.sqlite3")
    alpha_hypothesis_runner.add_argument(
        "--feature-snapshot-manifest",
        default=None,
        help="Optional verified feature snapshot manifest. When supplied, runner evidence is appended to the experiment registry.",
    )
    alpha_hypothesis_runner.add_argument(
        "--derivatives-feature-snapshot-manifest",
        default=None,
        help="Optional verified DERIVATIVES_POINT_IN_TIME snapshot; it is bound materially to manifested experiment evidence.",
    )
    alpha_hypothesis_runner.add_argument("--experiment-registry", default="data/research/experiment_registry.sqlite3")
    alpha_hypothesis_runner.add_argument("--experiment-seed", type=int, default=0)
    alpha_hypothesis_runner.add_argument(
        "--trial-timeframes",
        default="",
        help="Explicit research timeframes counted in the pre-run trial plan; omitted values stay unspecified.",
    )
    alpha_hypothesis_runner.add_argument(
        "--trial-regimes",
        default="",
        help="Explicit research regimes counted in the pre-run trial plan; omitted values stay unspecified.",
    )
    alpha_hypothesis_runner.add_argument(
        "--holdout-id",
        default=None,
        help="Previously reserved immutable holdout identifier; never available for optimization.",
    )
    alpha_hypothesis_runner.set_defaults(handler=_cmd_alpha_hypothesis_runner)

    experiment_registry_migrate = subparsers.add_parser(
        "experiment-registry-migrate-memory",
        help="Import legacy AUTOBOT research memory into the append-only experiment registry",
    )
    experiment_registry_migrate.add_argument("--memory-path", default="data/research/alpha_research_memory.sqlite3")
    experiment_registry_migrate.add_argument("--registry-path", default="data/research/experiment_registry.sqlite3")
    experiment_registry_migrate.set_defaults(handler=_cmd_experiment_registry_migrate_memory)

    experiment_registry_holdout = subparsers.add_parser(
        "experiment-registry-reserve-holdout",
        help="Reserve an immutable research holdout; it can only be used for final non-optimizing review.",
    )
    experiment_registry_holdout.add_argument("--registry-path", default="data/research/experiment_registry.sqlite3")
    experiment_registry_holdout.add_argument("--holdout-id", required=True)
    experiment_registry_holdout.add_argument("--data-snapshot-id", required=True)
    experiment_registry_holdout.add_argument("--immutable-fingerprint", required=True)
    experiment_registry_holdout.add_argument("--manifest-path", default=None)
    experiment_registry_holdout.set_defaults(handler=_cmd_experiment_registry_reserve_holdout)

    experiment_registry_holdout_review = subparsers.add_parser(
        "experiment-registry-record-final-holdout-review",
        help="Record non-optimizing immutable-holdout evidence for a frozen research experiment.",
    )
    experiment_registry_holdout_review.add_argument("--registry-path", default="data/research/experiment_registry.sqlite3")
    experiment_registry_holdout_review.add_argument("--experiment-id", required=True)
    experiment_registry_holdout_review.add_argument(
        "--metrics-json",
        required=True,
        help="JSON object of final holdout metrics; it is evidence only and cannot enable execution.",
    )
    experiment_registry_holdout_review.add_argument(
        "--reasons",
        default="",
        help="Optional comma-separated review reasons.",
    )
    experiment_registry_holdout_review.set_defaults(handler=_cmd_experiment_registry_record_final_holdout_review)

    strategy_artifact_register = subparsers.add_parser(
        "strategy-artifact-register",
        help="Register a non-executable research/shadow artifact from immutable experiment evidence",
    )
    strategy_artifact_register.add_argument(
        "--experiment-registry-path",
        default="data/research/experiment_registry.sqlite3",
    )
    strategy_artifact_register.add_argument(
        "--artifact-registry-path",
        default="data/research/strategy_artifacts.sqlite3",
    )
    strategy_artifact_register.add_argument("--experiment-id", required=True)
    strategy_artifact_register.add_argument("--strategy-version", required=True)
    strategy_artifact_register.add_argument("--risk-mandate-fingerprint", required=True)
    strategy_artifact_register.add_argument(
        "--risk-mandates",
        default="docs/research/strategy_risk_mandates.json",
        help="Versioned research risk mandates used to derive immutable evidence for a shadow-capable artifact.",
    )
    strategy_artifact_register.add_argument(
        "--risk-mandate-id",
        default=None,
        help="Required for a shadow-capable artifact; it must resolve to the experiment strategy.",
    )
    strategy_artifact_register.add_argument("--validation-manifest-fingerprint", required=True)
    strategy_artifact_register.add_argument(
        "--status",
        choices=("RESEARCH", "REJECTED", "SHADOW_ELIGIBLE", "SHADOW", "THROTTLED", "QUARANTINED", "RETIRED"),
        default="RESEARCH",
    )
    strategy_artifact_register.add_argument(
        "--human-approval-reference",
        default=None,
        help="Required for any shadow-capable status; this is an audit reference, never a live/paper authorization.",
    )
    strategy_artifact_register.set_defaults(handler=_cmd_strategy_artifact_register)

    strategy_artifact_resolve = subparsers.add_parser(
        "strategy-artifact-resolve-reference",
        help="Read one registered shadow artifact into a non-executable order-intent reference",
    )
    strategy_artifact_resolve.add_argument(
        "--artifact-registry-path",
        default="data/research/strategy_artifacts.sqlite3",
    )
    strategy_artifact_resolve.add_argument("--artifact-id", required=True)
    strategy_artifact_resolve.set_defaults(handler=_cmd_strategy_artifact_resolve_reference)

    alpha_hypothesis_scheduler = subparsers.add_parser(
        "alpha-hypothesis-scheduler",
        help="Rank bounded alpha hypotheses from the knowledge base, templates, data readiness and research memory",
    )
    alpha_hypothesis_scheduler.add_argument("--state-db", default=None)
    alpha_hypothesis_scheduler.add_argument("--data-paths", required=True)
    alpha_hypothesis_scheduler.add_argument("--knowledge-base", default="docs/research/alpha_knowledge_base.json")
    alpha_hypothesis_scheduler.add_argument("--templates", default="docs/research/strategy_templates.json")
    alpha_hypothesis_scheduler.add_argument("--hypotheses", default="docs/research/alpha_hypotheses.json")
    alpha_hypothesis_scheduler.add_argument("--memory-path", default="data/research/alpha_research_memory.sqlite3")
    alpha_hypothesis_scheduler.add_argument(
        "--output-dir",
        default="data/research/reports/alpha_hypothesis_runner",
        help="Runtime-writable output directory for scheduler/runner evidence.",
    )
    alpha_hypothesis_scheduler.add_argument("--run-id", default=None)
    alpha_hypothesis_scheduler.add_argument("--max-variants", type=int, default=5)
    alpha_hypothesis_scheduler.add_argument("--max-symbols", type=int, default=6)
    alpha_hypothesis_scheduler.add_argument("--max-runtime-seconds", type=int, default=300)
    alpha_hypothesis_scheduler.add_argument(
        "--no-memory-backfill",
        action="store_true",
        help="Skip conservative historical memory backfill before ranking",
    )
    alpha_hypothesis_scheduler.set_defaults(handler=_cmd_alpha_hypothesis_scheduler)

    data_capability_scan = subparsers.add_parser(
        "data-capability-scan",
        help="Scan research data capabilities and explain which alpha families are unlocked or blocked",
    )
    data_capability_scan.add_argument("--run-id", default=None)
    data_capability_scan.add_argument("--state-db", default=None)
    data_capability_scan.add_argument("--data-roots", required=True, help="Comma-separated data/report roots to scan")
    data_capability_scan.add_argument("--memory-path", default="data/research/alpha_research_memory.sqlite3")
    data_capability_scan.add_argument("--output-dir", default="reports/research")
    data_capability_scan.set_defaults(handler=_cmd_data_capability_scan)

    sqlite_restore_drill = subparsers.add_parser(
        "sqlite-restore-drill",
        help="Verify a SQLite backup through a disposable research-only restore drill",
    )
    sqlite_restore_drill.add_argument("--backup-path", required=True)
    sqlite_restore_drill.set_defaults(handler=_cmd_sqlite_restore_drill)

    runtime_oms_ledger_audit = subparsers.add_parser(
        "runtime-oms-ledger-audit",
        help="Read existing runtime OMS/ledger evidence without modifying SQLite or routing orders",
    )
    runtime_oms_ledger_audit.add_argument("--state-db", required=True)
    runtime_oms_ledger_audit.set_defaults(handler=_cmd_runtime_oms_ledger_audit)

    runtime_oms_ledger_migration_plan = subparsers.add_parser(
        "runtime-oms-ledger-migration-plan",
        help="Build a non-executable, read-only canonical migration plan for runtime OMS/ledger evidence",
    )
    runtime_oms_ledger_migration_plan.add_argument("--state-db", required=True)
    runtime_oms_ledger_migration_plan.set_defaults(handler=_cmd_runtime_oms_ledger_migration_plan)

    canonicalize_ohlcv = subparsers.add_parser(
        "canonicalize-ohlcv",
        help="Build a deterministic research-only canonical OHLCV snapshot from raw CSV exports",
    )
    canonicalize_ohlcv.add_argument("--run-id", default=None)
    canonicalize_ohlcv.add_argument("--raw-paths", required=True, help="Comma-separated raw OHLCV files or directories")
    canonicalize_ohlcv.add_argument("--output-dir", default="data/research/canonical/ohlcv")
    canonicalize_ohlcv.add_argument("--manifest-dir", default="data/research/manifests")
    canonicalize_ohlcv.add_argument("--quarantine-dir", default="data/research/quarantine")
    canonicalize_ohlcv.add_argument(
        "--report-dir",
        default="data/research/reports/canonical_ohlcv",
        help="Runtime-writable report directory; compact decision reports may be copied into reports/ separately.",
    )
    canonicalize_ohlcv.add_argument("--exchange", default="kraken")
    canonicalize_ohlcv.add_argument("--market-type", default="spot")
    canonicalize_ohlcv.add_argument(
        "--market-mapping-source",
        choices=("kraken_public", "none"),
        default="kraken_public",
        help="Use explicit public Kraken AssetPairs base/quote mappings; 'none' retains unverified mappings.",
    )
    canonicalize_ohlcv.add_argument("--max-files", type=int, default=None)
    canonicalize_ohlcv.add_argument("--max-rows", type=int, default=None)
    canonicalize_ohlcv.set_defaults(handler=_cmd_canonicalize_ohlcv)

    materialize_features = subparsers.add_parser(
        "materialize-feature-snapshot",
        help="Materialize a deterministic research-only feature bundle from a canonical OHLCV v2 manifest",
    )
    materialize_features.add_argument("--run-id", default=None)
    materialize_features.add_argument("--canonical-manifest", required=True)
    materialize_features.add_argument("--output-dir", default="data/research/canonical/features")
    materialize_features.add_argument("--manifest-dir", default="data/research/manifests")
    materialize_features.add_argument(
        "--report-dir",
        default="data/research/reports/canonical_features",
        help="Runtime-writable report directory; compact decision reports may be copied into reports/ separately.",
    )
    materialize_features.add_argument(
        "--feature-ids",
        default="return_1_bps,momentum_3_bps,volatility_20_bps,atr_14_bps",
        help="Comma-separated registered feature IDs. Defaults to the canonical OHLCV library.",
    )
    materialize_features.set_defaults(handler=_cmd_materialize_feature_snapshot)

    materialize_derivatives_features = subparsers.add_parser(
        "materialize-derivatives-feature-snapshot",
        help="Materialize a point-in-time, research-only feature bundle from canonical derivatives histories",
    )
    materialize_derivatives_features.add_argument("--run-id", default=None)
    materialize_derivatives_features.add_argument("--derivatives-manifest", required=True)
    materialize_derivatives_features.add_argument("--as-of-time", required=True, help="UTC ISO-8601 cutoff; future or unavailable rows are excluded")
    materialize_derivatives_features.add_argument("--output-dir", default="data/research/canonical/derivatives_features")
    materialize_derivatives_features.add_argument("--manifest-dir", default="data/research/manifests")
    materialize_derivatives_features.add_argument("--report-dir", default="data/research/reports/derivatives_features")
    materialize_derivatives_features.add_argument(
        "--feature-ids",
        default="funding_rate_relative,basis_bps,open_interest_change_24_pct",
        help="Comma-separated registered derivatives feature IDs.",
    )
    materialize_derivatives_features.set_defaults(handler=_cmd_materialize_derivatives_feature_snapshot)

    upgrade_feature_manifest = subparsers.add_parser(
        "upgrade-feature-snapshot-manifest",
        help="Backfill explicit versions into a legacy feature manifest only when its registry fingerprint verifies",
    )
    upgrade_feature_manifest.add_argument("--source-manifest", required=True)
    upgrade_feature_manifest.add_argument("--output-manifest", required=True)
    upgrade_feature_manifest.set_defaults(handler=_cmd_upgrade_feature_snapshot_manifest)

    futures_derivatives = subparsers.add_parser(
        "collect-kraken-futures-derivatives",
        help="Collect bounded public Kraken Futures derivatives data for research only",
    )
    futures_derivatives.add_argument("--run-id", default=None)
    futures_derivatives.add_argument("--assets", default="BTC,ETH", help="Comma-separated base assets, e.g. BTC,ETH,SOL")
    futures_derivatives.add_argument("--max-symbols", type=int, default=2)
    futures_derivatives.add_argument("--tick-types", default="trade,mark,spot")
    futures_derivatives.add_argument("--resolution", default="1m")
    futures_derivatives.add_argument("--max-candles", type=int, default=25)
    futures_derivatives.add_argument("--raw-dir", default="data/research/raw/kraken_futures")
    futures_derivatives.add_argument("--canonical-dir", default="data/research/canonical/derivatives")
    futures_derivatives.add_argument("--manifest-dir", default="data/research/manifests")
    futures_derivatives.add_argument("--report-dir", default="reports/research/kraken_futures_derivatives")
    futures_derivatives.add_argument("--sleep-seconds", type=float, default=0.0)
    futures_derivatives.add_argument("--timeout-seconds", type=float, default=20.0)
    futures_derivatives.add_argument("--skip-funding", action="store_true")
    futures_derivatives.add_argument("--skip-tickers", action="store_true")
    futures_derivatives.add_argument("--skip-candles", action="store_true")
    futures_derivatives.add_argument("--continue-on-error", action="store_true")
    futures_derivatives.add_argument(
        "--raw-retention-days",
        type=int,
        default=None,
        help="Optional retention for successfully canonicalized raw run directories; manifests and canonical data are retained.",
    )
    futures_derivatives.set_defaults(handler=_cmd_collect_kraken_futures_derivatives)

    strategy_autonomy = subparsers.add_parser(
        "strategy-autonomy-check",
        help="Evaluate one strategy against its research-only risk mandate",
    )
    strategy_autonomy.add_argument("--strategy-id", required=True)
    strategy_autonomy.add_argument("--state-db", default=None)
    strategy_autonomy.add_argument("--mandates", default="docs/research/strategy_risk_mandates.json")
    strategy_autonomy.add_argument("--output-dir", default=None)
    strategy_autonomy.set_defaults(handler=_cmd_strategy_autonomy_check)

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

    paper_performance = subparsers.add_parser(
        "paper-performance-summary",
        help="Build the official post-P0 paper performance summary from attributed trade_ledger rows",
    )
    paper_performance.add_argument("--state-db", required=True, help="Read-only AUTOBOT state DB containing trade_ledger")
    paper_performance.add_argument("--registry-path", default="docs/research/strategy_hypotheses.json")
    paper_performance.add_argument("--run-id", default=None)
    paper_performance.add_argument("--initial-capital-eur", type=float, default=1_000.0)
    paper_performance.add_argument("--output-dir", default="reports/paper/official_performance")
    paper_performance.add_argument("--no-write-report", action="store_true")
    paper_performance.set_defaults(handler=_cmd_paper_performance_summary)

    shadow_observations = subparsers.add_parser(
        "shadow-paper-observations",
        help="Sync closed shadow-lab trades as attributed shadow_paper ledger observations",
    )
    shadow_observations.add_argument("--state-db", required=True, help="AUTOBOT state DB containing trade_ledger")
    shadow_observations.add_argument("--registry-path", default="docs/research/strategy_hypotheses.json")
    shadow_observations.add_argument("--trend-shadow-db", default="data/trend_shadow_lab.db")
    shadow_observations.add_argument("--mean-reversion-shadow-db", default="data/mean_reversion_shadow_lab.db")
    shadow_observations.add_argument(
        "--high-conviction-data-paths",
        default=None,
        help="Comma-separated OHLCV CSV/Parquet path(s) or directories used to build closed high-conviction shadow observations",
    )
    shadow_observations.add_argument(
        "--high-conviction-feature-snapshot-manifest",
        default=None,
        help="Required READY point-in-time feature manifest for High Conviction shadow ledger writes",
    )
    shadow_observations.add_argument(
        "--high-conviction-output-dir",
        default=None,
        help="Optional output directory for the research-only high-conviction replay report",
    )
    shadow_observations.add_argument("--run-id", default=None)
    shadow_observations.add_argument("--output-dir", default="reports/paper/shadow_observations")
    shadow_observations.add_argument("--no-write-report", action="store_true")
    shadow_observations.set_defaults(handler=_cmd_shadow_paper_observations)

    paper_loss = subparsers.add_parser(
        "paper-loss-diagnostics",
        help="Diagnose post-P2 shadow_paper losses by strategy, pair, timeframe and regime",
    )
    paper_loss.add_argument("--state-db", required=True, help="AUTOBOT state DB containing trade_ledger")
    paper_loss.add_argument("--registry-path", default="docs/research/strategy_hypotheses.json")
    paper_loss.add_argument("--run-id", default=None)
    paper_loss.add_argument("--initial-capital-eur", type=float, default=1_000.0)
    paper_loss.add_argument("--min-segment-trades", type=int, default=30)
    paper_loss.add_argument("--output-dir", default="reports/paper/loss_diagnostics")
    paper_loss.add_argument("--no-write-report", action="store_true")
    paper_loss.set_defaults(handler=_cmd_paper_loss_diagnostics)

    db_integrity = subparsers.add_parser(
        "check-db-integrity",
        help="Run read-only integrity checks on the AUTOBOT state DB",
    )
    db_integrity.add_argument("--state-db", required=True, help="Read-only AUTOBOT state DB")
    db_integrity.add_argument("--run-id", default=None)
    db_integrity.add_argument("--snapshot-dir", default=None, help="Optional directory for a diagnostic DB snapshot")
    db_integrity.add_argument("--output-dir", default="reports/paper/db_integrity")
    db_integrity.add_argument("--no-write-report", action="store_true")
    db_integrity.set_defaults(handler=_cmd_check_db_integrity)

    score_filter = subparsers.add_parser(
        "score-filter-simulation",
        help="Read-only opportunity_score bucket filter simulation",
    )
    score_filter.add_argument("--state-db", required=True, help="Read-only AUTOBOT state DB containing trade_ledger")
    score_filter.add_argument("--run-id", default=None)
    score_filter.add_argument("--initial-capital-eur", type=float, default=1_000.0)
    score_filter.add_argument("--output-dir", default="reports/paper/score_filter_simulation")
    score_filter.add_argument("--no-write-report", action="store_true")
    score_filter.set_defaults(handler=_cmd_score_filter_simulation)

    forward_edge = subparsers.add_parser(
        "forward-edge-simulation",
        help="Read-only forward-safe net-edge simulation for shadow observations",
    )
    forward_edge.add_argument("--state-db", required=True, help="Read-only AUTOBOT state DB containing trade_ledger")
    forward_edge.add_argument("--run-id", default=None)
    forward_edge.add_argument("--initial-capital-eur", type=float, default=1_000.0)
    forward_edge.add_argument("--cost-profile", default="paper_current_taker")
    forward_edge.add_argument("--top-quantile-fraction", type=float, default=0.20)
    forward_edge.add_argument("--output-dir", default="reports/paper/forward_edge_simulation")
    forward_edge.add_argument("--no-write-report", action="store_true")
    forward_edge.set_defaults(handler=_cmd_forward_edge_simulation)

    forward_validation = subparsers.add_parser(
        "forward-edge-validation",
        help="Read-only forward-only validation for post-P10 shadow observations",
    )
    forward_validation.add_argument("--state-db", required=True, help="Read-only AUTOBOT state DB containing trade_ledger")
    forward_validation.add_argument("--since", default=None, help="ISO8601 cutoff; only trades opened after it are post-P10")
    forward_validation.add_argument("--since-commit", default=None, help="Known P10 commit hash mapped to its cutoff timestamp")
    forward_validation.add_argument("--run-id", default=None)
    forward_validation.add_argument("--initial-capital-eur", type=float, default=1_000.0)
    forward_validation.add_argument("--cost-profile", default="paper_current_taker")
    forward_validation.add_argument("--top-quantile-fraction", type=float, default=0.20)
    forward_validation.add_argument("--output-dir", default="reports/paper/forward_edge_validation")
    forward_validation.add_argument("--no-write-report", action="store_true")
    forward_validation.set_defaults(handler=_cmd_forward_edge_validation)

    opportunity_score_audit = subparsers.add_parser(
        "opportunity-score-audit",
        help="Read-only audit of opportunity_score distribution, forward edge alignment and high-conviction scoring",
    )
    opportunity_score_audit.add_argument("--state-db", required=True, help="Read-only AUTOBOT state DB containing trade_ledger")
    opportunity_score_audit.add_argument("--since", default=None, help="ISO8601 cutoff; only trades opened after it are included")
    opportunity_score_audit.add_argument("--since-commit", default=None, help="Known P10 commit hash mapped to its cutoff timestamp")
    opportunity_score_audit.add_argument("--run-id", default=None)
    opportunity_score_audit.add_argument("--initial-capital-eur", type=float, default=1_000.0)
    opportunity_score_audit.add_argument("--cost-profile", default="paper_current_taker")
    opportunity_score_audit.add_argument("--output-dir", default="reports/paper/opportunity_score_audit")
    opportunity_score_audit.add_argument("--no-write-report", action="store_true")
    opportunity_score_audit.set_defaults(handler=_cmd_opportunity_score_audit)

    expected_move = subparsers.add_parser(
        "expected-move-diagnostics",
        help="Research-only audit of upstream expected_move/net-edge quality in shadow observations",
    )
    expected_move.add_argument("--state-db", required=True, help="AUTOBOT state DB containing trade_ledger")
    expected_move.add_argument("--since", default=None, help="ISO8601 cutoff; only trades opened after it are included")
    expected_move.add_argument(
        "--high-conviction-data-paths",
        default=None,
        help="Optional comma-separated OHLCV path(s) used by high-conviction shadow sync",
    )
    expected_move.add_argument("--run-id", default=None)
    expected_move.add_argument("--output-dir", default="reports/paper/expected_move_diagnostics")
    expected_move.add_argument("--no-write-report", action="store_true")
    expected_move.set_defaults(handler=_cmd_expected_move_diagnostics)

    paper_confidence = subparsers.add_parser(
        "paper-confidence",
        help="Research-only statistical confidence report for one strategy_id",
    )
    paper_confidence.add_argument("--state-db", required=True, help="Read-only AUTOBOT state DB containing trade_ledger")
    paper_confidence.add_argument("--strategy-id", required=True)
    paper_confidence.add_argument("--run-id", default=None)
    paper_confidence.add_argument("--initial-capital-eur", type=float, default=1_000.0)
    paper_confidence.add_argument("--bootstrap-iterations", type=int, default=500)
    paper_confidence.add_argument("--seed", type=int, default=7)
    paper_confidence.add_argument("--output-dir", default="reports/paper/confidence")
    paper_confidence.add_argument("--no-write-report", action="store_true")
    paper_confidence.set_defaults(handler=_cmd_paper_confidence)

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

    parity = subparsers.add_parser(
        "research-paper-parity",
        help="Replay research from a state DB and compare it with official paper ledger evidence",
    )
    parity.add_argument("--run-id", required=True)
    parity.add_argument("--state-db", required=True)
    parity.add_argument("--symbols", default=None, help="Comma-separated symbols; defaults to AUTOBOT top-14 EUR preset")
    parity.add_argument("--strategies", default=None, help="Comma-separated strategies; defaults to trend,mean_reversion (Grid is explicit archived research)")
    parity.add_argument("--output-dir", default="reports/research/research_paper_parity")
    parity.add_argument("--initial-capital-eur", type=float, default=1_000.0)
    parity.add_argument("--order-notional-eur", type=float, default=100.0)
    parity.add_argument("--start-at", default=None)
    parity.add_argument("--end-at", default=None)
    parity.add_argument("--limit", type=int, default=None)
    _add_cost_profile_args(parity)
    parity.add_argument("--include-regime-context", action="store_true")
    parity.set_defaults(handler=_cmd_research_paper_parity)

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
    _add_cost_profile_args(cost_parity, include_latency=True)
    cost_parity.add_argument("--warning-delta-bps", type=float, default=5.0)
    cost_parity.add_argument("--slippage-anomaly-threshold-bps", type=float, default=100.0)
    cost_parity.add_argument("--no-write-report", action="store_true")
    cost_parity.set_defaults(handler=_cmd_cost_parity)

    split_plan = subparsers.add_parser(
        "split-plan",
        help="Evaluate read-only instance split policy evidence without creating children",
    )
    split_plan.add_argument("--run-id", required=True)
    split_plan.add_argument("--state-db", default=None)
    split_plan.add_argument("--evidence-json", required=True, help="JSON object or list of parent evidence objects")
    split_plan.add_argument("--output-dir", default="reports/research/instance_split")
    split_plan.set_defaults(handler=_cmd_split_plan)

    split_validation = subparsers.add_parser(
        "split-validation",
        help="Validate paper-only instance split mechanics in an isolated sandbox",
    )
    split_validation.add_argument("--run-id", required=True)
    split_validation.add_argument("--evidence-json", required=True)
    split_validation.add_argument(
        "--child-return-series",
        default="0.01,-0.004,0.006",
        help="Comma-separated synthetic child returns used only to verify state isolation",
    )
    split_validation.add_argument(
        "--output-dir",
        default="reports/research/instance_split_validation",
    )
    split_validation.set_defaults(handler=_cmd_split_validation)

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
    _add_cost_profile_args(parser)
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
    _add_cost_profile_args(parser)
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
    parser.add_argument("--strategies", default=None, help="Comma-separated strategies; defaults to trend,mean_reversion (Grid is explicit archived research)")
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
    _add_cost_profile_args(parser)
    parser.add_argument("--strategy-config-json", default="{}")
    parser.add_argument("--registry-path", default="docs/research/strategy_hypotheses.json")
    parser.add_argument("--parquet", action="store_true", help="Also attempt Parquet dataset export if dependencies exist")


def _add_standard_audit_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--state-db", required=True, help="Read-only AUTOBOT state DB")
    parser.add_argument("--symbols", default=None, help="Comma-separated symbols; defaults to AUTOBOT top-14 EUR preset")
    parser.add_argument("--strategies", default=None, help="Comma-separated strategies; defaults to trend,mean_reversion (Grid is explicit archived research)")
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
    _add_cost_profile_args(parser)
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
    _add_cost_profile_args(parser, include_latency=True)
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


def _add_strategy_experiment_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--state-db", required=True, help="Read-only AUTOBOT state DB containing market_price_samples")
    parser.add_argument("--symbols", required=True, help="Comma-separated symbols, e.g. TRXEUR,BTCEUR")
    parser.add_argument("--strategies", default="trend,mean_reversion", help="Comma-separated: trend,mean_reversion")
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--output-dir", default="reports/research/strategy_experiments")
    parser.add_argument("--dataset-output-dir", default="data/research/strategy_experiments")
    parser.add_argument("--initial-capital-eur", type=float, default=1_000.0)
    parser.add_argument("--order-notional-eur", type=float, default=100.0)
    parser.add_argument("--start-at", default=None)
    parser.add_argument("--end-at", default=None)
    parser.add_argument("--limit", type=int, default=None)
    _add_cost_profile_args(parser, include_latency=True)
    parser.add_argument("--min-closed-trades", type=int, default=30)
    parser.add_argument("--candidate-min-closed-trades", type=int, default=100)
    parser.add_argument("--candidate-min-profit-factor", type=float, default=1.20)
    parser.add_argument("--candidate-min-mfe-to-cost", type=float, default=1.50)
    parser.add_argument("--candidate-max-drawdown-pct", type=float, default=12.0)
    parser.add_argument("--train-window-bars", type=int, default=200)
    parser.add_argument("--test-window-bars", type=int, default=100)
    parser.add_argument("--step-window-bars", type=int, default=None)
    parser.add_argument("--min-folds", type=int, default=3)
    parser.add_argument("--max-variants-per-strategy", type=int, default=None)
    parser.add_argument(
        "--no-regime-context",
        action="store_true",
        help="Do not enrich experiment bars with research regime context",
    )


def _add_strategy_batch_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--state-db", default=None, help="Read-only AUTOBOT state DB containing market_price_samples")
    parser.add_argument("--data-source", choices=["autobot_state_db", "csv"], default="autobot_state_db")
    parser.add_argument("--data-path", default=None, help="Research dataset path when --data-source=csv")
    parser.add_argument("--symbols", default=None, help="Comma-separated symbols; defaults to AUTOBOT top-14 EUR preset")
    parser.add_argument("--strategies", default=None, help="Comma-separated strategies; defaults to trend,mean_reversion (Grid is explicit archived research)")
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--mode", choices=["backtest", "walk_forward"], default="backtest")
    parser.add_argument("--output-dir", default="reports/research/batch_strategy_validation")
    parser.add_argument("--initial-capital-eur", type=float, default=1_000.0)
    parser.add_argument("--order-notional-eur", type=float, default=100.0)
    parser.add_argument("--min-closed-trades", type=int, default=30)
    parser.add_argument("--min-profit-factor", type=float, default=1.2)
    parser.add_argument("--max-drawdown-pct", type=float, default=15.0)
    parser.add_argument("--min-mfe-to-cost", type=float, default=1.5)
    parser.add_argument("--min-exit-capture-bps", type=float, default=0.0)
    _add_cost_profile_args(parser)
    parser.add_argument("--no-regime-context", action="store_true")


def _add_high_conviction_swing_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--state-db", required=True, help="Read-only AUTOBOT state DB")
    parser.add_argument("--symbols", default=None, help="Comma-separated symbols; omit to include all recent signals")
    parser.add_argument("--output-dir", default="reports/research/high_conviction_swing")
    parser.add_argument("--lookback-hours", type=float, default=72.0)
    parser.add_argument("--start-at", default=None)
    parser.add_argument("--end-at", default=None)
    parser.add_argument("--initial-capital-eur", type=float, default=1_000.0)
    parser.add_argument("--order-notional-eur", type=float, default=100.0)
    parser.add_argument("--min-expected-move-bps", default="100,200,500,1000")
    parser.add_argument("--risk-reward-ratios", default="1.5,2,3")
    parser.add_argument("--max-hold-hours", default="6,24,72,168")
    parser.add_argument("--exit-modes", default="fixed_tp_sl,trailing,partial_runner")
    parser.add_argument("--no-mtf-required", action="store_true")
    parser.add_argument("--min-sample-trades-for-candidate", type=int, default=20)
    parser.add_argument("--candidate-min-profit-factor", type=float, default=1.2)
    parser.add_argument("--candidate-max-drawdown-bps", type=float, default=1500.0)
    _add_cost_profile_args(parser, include_latency=True)


def _add_high_conviction_discovery_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--data-paths",
        required=True,
        help="Comma-separated CSV/Parquet files or directories containing OHLCV research data",
    )
    parser.add_argument("--symbols", default=None, help="Comma-separated symbols; omit to include all OHLCV symbols")
    parser.add_argument("--output-dir", default="reports/research/high_conviction_discovery")
    parser.add_argument(
        "--setup-families",
        default="breakout_1h_4h,pullback_trend,major_support_mean_reversion,volatility_expansion,trend_continuation",
        help="Comma-separated setup families to scan",
    )
    parser.add_argument("--min-expected-move-bps", default="200,500,1000")
    parser.add_argument("--risk-reward-ratios", default="2,3")
    parser.add_argument("--max-hold-hours", default="6,24,72,168")
    parser.add_argument("--exit-modes", default="fixed_tp_sl,trailing,partial_runner,trend_invalidation")
    parser.add_argument("--initial-capital-eur", type=float, default=1_000.0)
    parser.add_argument("--order-notional-eur", type=float, default=100.0)
    parser.add_argument("--min-sample-trades-for-candidate", type=int, default=20)
    parser.add_argument("--candidate-min-profit-factor", type=float, default=1.2)
    parser.add_argument("--candidate-max-drawdown-bps", type=float, default=1500.0)
    parser.add_argument(
        "--micro-report-json",
        default=None,
        help="Optional high-conviction-swing JSON report used to compare against current grid/micro signals",
    )
    _add_cost_profile_args(parser, include_latency=True)


def _add_high_conviction_portfolio_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--data-paths", required=True, help="Comma-separated OHLCV CSV/Parquet files or directories")
    parser.add_argument("--symbols", default=None, help="Comma-separated symbols; omit to scan all OHLCV symbols")
    parser.add_argument("--output-dir", default="reports/research/high_conviction_portfolio")
    parser.add_argument(
        "--setup-families",
        default="breakout_1h_4h,pullback_trend,major_support_mean_reversion,volatility_expansion,trend_continuation",
    )
    parser.add_argument("--min-expected-move-bps", default="200,500,1000")
    parser.add_argument("--risk-reward-ratios", default="2,3")
    parser.add_argument("--max-hold-hours", default="24,72")
    parser.add_argument("--exit-modes", default="fixed_tp_sl,trailing,partial_runner,trend_invalidation")
    parser.add_argument("--cost-profiles", default="research_stress,paper_current_taker")
    parser.add_argument("--initial-capital-eur", type=float, default=500.0)
    parser.add_argument("--legacy-notional-eur", type=float, default=100.0)
    parser.add_argument("--max-position-fraction", type=float, default=0.20)
    parser.add_argument("--risk-per-trade-pct", type=float, default=0.01)
    parser.add_argument("--max-global-exposure-pct", type=float, default=0.60)
    parser.add_argument("--max-open-positions", type=int, default=3)
    parser.add_argument("--cooldown-hours", type=float, default=6.0)
    parser.add_argument("--max-daily-loss-pct", type=float, default=0.03)
    parser.add_argument("--critical-drawdown-pct", type=float, default=0.12)
    parser.add_argument("--drawdown-reduce-start-pct", type=float, default=0.05)
    parser.add_argument("--min-drawdown-exposure-multiplier", type=float, default=0.35)
    parser.add_argument("--min-sample-trades-for-candidate", type=int, default=30)
    parser.add_argument("--candidate-min-profit-factor", type=float, default=1.20)
    parser.add_argument("--candidate-max-drawdown-pct", type=float, default=0.12)


def _add_high_conviction_walk_forward_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--data-paths", required=True, help="Comma-separated OHLCV CSV/Parquet files or directories")
    parser.add_argument("--symbols", default=None, help="Comma-separated symbols; omit to scan all OHLCV symbols")
    parser.add_argument("--output-dir", default="reports/research/high_conviction_walk_forward")
    parser.add_argument(
        "--setup-families",
        default="breakout_1h_4h,pullback_trend,major_support_mean_reversion,volatility_expansion,trend_continuation",
    )
    parser.add_argument("--min-expected-move-bps", type=float, default=500.0)
    parser.add_argument("--risk-reward-ratio", type=float, default=2.0)
    parser.add_argument("--max-hold-hours", type=float, default=72.0)
    parser.add_argument("--exit-modes", default="fixed_tp_sl,trailing")
    parser.add_argument("--primary-exit-mode", default="fixed_tp_sl")
    parser.add_argument("--initial-capital-eur", type=float, default=500.0)
    parser.add_argument("--max-position-fraction", type=float, default=0.20)
    parser.add_argument("--risk-per-trade-pct", type=float, default=0.01)
    parser.add_argument("--max-global-exposure-pct", type=float, default=0.60)
    parser.add_argument("--max-open-positions", type=int, default=3)
    parser.add_argument("--cooldown-hours", type=float, default=6.0)
    parser.add_argument("--max-daily-loss-pct", type=float, default=0.03)
    parser.add_argument("--critical-drawdown-pct", type=float, default=0.12)
    parser.add_argument("--drawdown-reduce-start-pct", type=float, default=0.05)
    parser.add_argument("--min-drawdown-exposure-multiplier", type=float, default=0.35)
    parser.add_argument("--train-window-bars", type=int, default=288)
    parser.add_argument("--test-window-bars", type=int, default=192)
    parser.add_argument("--step-window-bars", type=int, default=None)
    parser.add_argument("--min-folds", type=int, default=3)
    parser.add_argument("--min-positive-fold-ratio", type=float, default=0.60)
    parser.add_argument("--min-closed-trades-for-review", type=int, default=50)
    parser.add_argument("--min-profit-factor", type=float, default=1.20)
    parser.add_argument("--max-drawdown-pct", type=float, default=0.12)
    parser.add_argument("--max-single-symbol-positive-pnl-share", type=float, default=0.60)


def _add_strategy_orchestrator_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--data-paths", required=True, help="Comma-separated OHLCV CSV/Parquet files or directories")
    parser.add_argument("--symbols", default=None, help="Comma-separated symbols; omit to scan all OHLCV symbols")
    parser.add_argument("--output-dir", default="reports/research/strategy_orchestrator")
    parser.add_argument("--instance-id", default="research-parent-001")
    parser.add_argument("--initial-treasury-eur", type=float, default=500.0)
    parser.add_argument("--cost-profiles", default="paper_current_taker,research_stress")
    parser.add_argument("--max-instance-exposure-pct", type=float, default=0.60)
    parser.add_argument("--max-strategy-exposure-pct", type=float, default=0.50)
    parser.add_argument("--max-symbol-exposure-pct", type=float, default=0.20)
    parser.add_argument("--risk-per-trade-pct", type=float, default=0.01)
    parser.add_argument("--max-open-positions", type=int, default=3)
    parser.add_argument("--cooldown-hours", type=float, default=6.0)
    parser.add_argument("--max-daily-loss-pct", type=float, default=0.03)
    parser.add_argument("--max-drawdown-pct", type=float, default=0.10)
    parser.add_argument("--min-research-meta-score", type=float, default=20.0)
    parser.add_argument("--signal-history-bars", type=int, default=384)


def _add_strategy_edge_review_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-dir", default="reports/research")
    parser.add_argument("--report-date", default=None)
    parser.add_argument("--strategy-orchestrator-report", default=None)
    parser.add_argument("--high-conviction-report", default=None)
    parser.add_argument("--min-candidate-trades", type=int, default=50)
    parser.add_argument("--min-candidate-pf", type=float, default=1.30)
    parser.add_argument("--high-quality-pf", type=float, default=1.50)
    parser.add_argument("--max-drawdown-pct", type=float, default=10.0)
    parser.add_argument("--max-single-symbol-positive-share", type=float, default=0.40)


def _add_relative_value_portfolio_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--data-paths", required=True, help="Comma-separated Kraken OHLCV CSV/Parquet paths")
    parser.add_argument("--output-dir", default="reports/research/relative_value")
    parser.add_argument(
        "--relationships",
        default="ADAEUR:XRPZEUR,XLMEUR:TRXEUR,LINKEUR:DOTEUR,AVAXEUR:SOLEUR",
        help="Comma-separated TARGET:REFERENCE or TARGET:REFERENCE1|REFERENCE2 relations",
    )
    parser.add_argument("--timeframe", default="15m")
    parser.add_argument("--rolling-window-bars", type=int, default=96)
    parser.add_argument("--entry-zscore", type=float, default=-2.0)
    parser.add_argument("--exit-zscore", type=float, default=-0.25)
    parser.add_argument("--min-correlation", type=float, default=0.50)
    parser.add_argument("--max-cointegration-pvalue", type=float, default=0.10)
    parser.add_argument("--no-require-cointegration-when-available", action="store_true")
    parser.add_argument("--cointegration-refresh-bars", type=int, default=24)
    parser.add_argument("--min-expected-move-bps", type=float, default=150.0)
    parser.add_argument("--min-expected-mfe-to-cost", type=float, default=1.5)
    parser.add_argument("--fixed-take-profit-bps", type=float, default=400.0)
    parser.add_argument("--fixed-stop-loss-bps", type=float, default=200.0)
    parser.add_argument("--trailing-activation-bps", type=float, default=200.0)
    parser.add_argument("--trailing-distance-bps", type=float, default=125.0)
    parser.add_argument("--max-hold-bars", type=int, default=96)
    parser.add_argument("--initial-capital-eur", type=float, default=500.0)
    parser.add_argument("--max-position-fraction", type=float, default=0.20)
    parser.add_argument("--risk-per-trade-pct", type=float, default=0.01)
    parser.add_argument("--max-global-exposure-pct", type=float, default=0.60)
    parser.add_argument("--max-open-positions", type=int, default=3)
    parser.add_argument("--cooldown-hours", type=float, default=6.0)
    parser.add_argument("--max-daily-loss-pct", type=float, default=0.03)
    parser.add_argument("--max-drawdown-pct", type=float, default=0.10)
    parser.add_argument("--min-order-notional-eur", type=float, default=5.0)
    parser.add_argument("--max-volatility-bps", type=float, default=600.0)
    parser.add_argument("--cost-profiles", default="paper_current_taker,research_stress")
    parser.add_argument(
        "--comparison-high-conviction-report",
        default=None,
        help="Optional high_conviction_portfolio JSON report for read-only comparison",
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


def _cmd_collect_history(args: argparse.Namespace) -> int:
    from autobot.v2.research.historical_data_collector import (
        HistoricalDataCollectorConfig,
        collect_historical_ohlcv,
    )
    symbols = (
        _csv_tuple(args.symbols, "--symbols", uppercase=True)
        if args.symbols
        else detect_active_autobot_symbols()
    )

    result = collect_historical_ohlcv(
        HistoricalDataCollectorConfig(
            run_id=args.run_id,
            symbols=symbols,
            timeframes=_csv_tuple(args.timeframes, "--timeframes"),
            output_dir=Path(args.output_dir),
            since=args.since,
            start_at=args.start_at,
            end_at=args.end_at,
            max_pages=args.max_pages,
            sleep_seconds=args.sleep_seconds,
            dedupe=_parse_bool(args.dedupe, "--dedupe"),
            fail_on_gaps=bool(args.fail_on_gaps),
            export_csv=not bool(args.no_csv),
            export_parquet=bool(args.parquet) and not bool(args.no_parquet),
        )
    )
    _print_json(result.to_dict())
    return 0


def _cmd_collect_research_daily(args: argparse.Namespace) -> int:
    from autobot.v2.research.daily_data_collection_runner import run_daily_research_data_collection

    result = run_daily_research_data_collection(
        config_path=Path(args.config),
        run_id=args.run_id,
    )
    _print_json(result.to_dict())
    return 0


def _cmd_data_quality(args: argparse.Namespace) -> int:
    from autobot.v2.research.data_quality_report import (
        analyze_dataset_files,
        build_data_foundation_readiness_report,
        write_data_foundation_readiness_report,
    )

    file_reports = analyze_dataset_files(
        _csv_tuple(args.paths, "--paths"),
        default_timeframe=args.default_timeframe,
    )
    report = write_data_foundation_readiness_report(
        build_data_foundation_readiness_report(run_id=args.run_id, file_reports=file_reports),
        Path(args.output_dir),
    )
    _print_json(report.to_dict())
    return 0


def _cmd_no_trade_attribution(args: argparse.Namespace) -> int:
    from autobot.v2.research.no_trade_attribution_report import (
        build_no_trade_attribution_report,
        write_no_trade_attribution_report,
    )

    report = write_no_trade_attribution_report(
        build_no_trade_attribution_report(
            state_db_path=args.state_db,
            run_id=args.run_id,
            log_path=args.log_path,
        ),
        args.output_dir,
    )
    _print_json(report.to_dict())
    return 0


def _cmd_reconcile_orphan_positions(args: argparse.Namespace) -> int:
    from autobot.v2.research.orphan_position_reconciliation import (
        audit_orphan_positions,
        write_orphan_position_report,
    )

    report = write_orphan_position_report(
        audit_orphan_positions(state_db_path=args.state_db, run_id=args.run_id),
        args.output_dir,
    )
    _print_json(report.to_dict())
    return 0


def _cmd_validation(args: argparse.Namespace, *, mode: str) -> int:
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
        cost_config=_cost_config_from_args(args),
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
        cost_config=_cost_config_from_args(args),
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
        cost_config=_cost_config_from_args(args),
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
            cost_config=_cost_config_from_args(args),
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
            cost_config=_cost_config_from_args(args),
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


def _cmd_strategy_experiments(args: argparse.Namespace) -> int:
    from autobot.v2.research.strategy_experiment_runner import StrategyExperimentConfig, run_strategy_experiments

    symbols = _csv_tuple(args.symbols, "--symbols", uppercase=True)
    strategies = _csv_tuple(args.strategies, "--strategies")
    result = run_strategy_experiments(
        StrategyExperimentConfig(
            run_id=args.run_id,
            state_db_path=Path(args.state_db),
            symbols=symbols,
            strategies=strategies,  # type: ignore[arg-type]
            timeframe=args.timeframe.lower(),
            output_dir=Path(args.output_dir),
            dataset_output_dir=Path(args.dataset_output_dir),
            initial_capital_eur=args.initial_capital_eur,
            order_notional_eur=args.order_notional_eur,
            cost_config=_cost_config_from_args(args),
            min_closed_trades=args.min_closed_trades,
            candidate_min_closed_trades=args.candidate_min_closed_trades,
            candidate_min_profit_factor=args.candidate_min_profit_factor,
            candidate_min_mfe_to_cost=args.candidate_min_mfe_to_cost,
            candidate_max_drawdown_pct=args.candidate_max_drawdown_pct,
            max_variants_per_strategy=args.max_variants_per_strategy,
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


def _cmd_strategy_experiments_batch(args: argparse.Namespace) -> int:
    from autobot.v2.research.batch_strategy_validation import (
        BatchStrategyValidationConfig,
        run_batch_strategy_validation,
    )

    symbols = _csv_tuple(args.symbols, "--symbols", uppercase=True) if args.symbols else AUTOBOT_TOP14_EUR_SYMBOLS
    strategies = _csv_tuple(args.strategies, "--strategies") if args.strategies else AUTOBOT_STANDARD_STRATEGIES
    data_path = Path(args.data_path) if args.data_path else None
    state_db_path = Path(args.state_db) if args.state_db else None
    if args.data_source == "csv":
        if data_path is None:
            raise ValueError("--data-path is required when --data-source=csv")
    elif state_db_path is None:
        raise ValueError("--state-db is required when --data-source=autobot_state_db")
    result = run_batch_strategy_validation(
        BatchStrategyValidationConfig(
            run_id=args.run_id,
            symbols=symbols,
            state_db_path=state_db_path,
            data_source=args.data_source,
            data_path=data_path,
            strategies=strategies,
            timeframe=args.timeframe.lower(),
            mode=args.mode,
            output_dir=Path(args.output_dir),
            initial_capital_eur=args.initial_capital_eur,
            order_notional_eur=args.order_notional_eur,
            min_closed_trades=args.min_closed_trades,
            min_profit_factor=args.min_profit_factor,
            max_drawdown_pct=args.max_drawdown_pct,
            min_mfe_to_cost=args.min_mfe_to_cost,
            min_exit_capture_bps=args.min_exit_capture_bps,
            include_regime_context=not bool(args.no_regime_context),
            cost_config=_cost_config_from_args(args),
        )
    )
    _print_json(result.to_dict())
    return 0


def _cmd_high_conviction_swing(args: argparse.Namespace) -> int:
    from autobot.v2.research.high_conviction_swing import (
        HighConvictionSwingConfig,
        build_high_conviction_swing_report,
        write_high_conviction_swing_report,
    )

    symbols = _csv_tuple(args.symbols, "--symbols", uppercase=True) if args.symbols else ()
    exit_modes = _csv_tuple(args.exit_modes, "--exit-modes")
    result = write_high_conviction_swing_report(
        build_high_conviction_swing_report(
            HighConvictionSwingConfig(
                run_id=args.run_id,
                state_db_path=Path(args.state_db),
                output_dir=Path(args.output_dir),
                symbols=symbols,
                lookback_hours=args.lookback_hours,
                start_at=args.start_at,
                end_at=args.end_at,
                initial_capital_eur=args.initial_capital_eur,
                order_notional_eur=args.order_notional_eur,
                min_expected_move_bps=_csv_float_tuple(args.min_expected_move_bps, "--min-expected-move-bps"),
                risk_reward_ratios=_csv_float_tuple(args.risk_reward_ratios, "--risk-reward-ratios"),
                max_hold_hours=_csv_float_tuple(args.max_hold_hours, "--max-hold-hours"),
                exit_modes=exit_modes,  # type: ignore[arg-type]
                require_mtf_alignment=not bool(args.no_mtf_required),
                min_sample_trades_for_candidate=args.min_sample_trades_for_candidate,
                candidate_min_profit_factor=args.candidate_min_profit_factor,
                candidate_max_drawdown_bps=args.candidate_max_drawdown_bps,
                cost_config=_cost_config_from_args(args),
            )
        ),
        Path(args.output_dir),
    )
    _print_json(result.to_dict())
    return 0


def _cmd_high_conviction_discovery(args: argparse.Namespace) -> int:
    from autobot.v2.research.high_conviction_discovery import (
        HighConvictionDiscoveryConfig,
        build_high_conviction_discovery_report,
        write_high_conviction_discovery_report,
    )

    symbols = _csv_tuple(args.symbols, "--symbols", uppercase=True) if args.symbols else ()
    data_paths = tuple(Path(path) for path in _csv_tuple(args.data_paths, "--data-paths"))
    setup_families = _csv_tuple(args.setup_families, "--setup-families")
    exit_modes = _csv_tuple(args.exit_modes, "--exit-modes")
    micro_report = Path(args.micro_report_json) if args.micro_report_json else None
    result = write_high_conviction_discovery_report(
        build_high_conviction_discovery_report(
            HighConvictionDiscoveryConfig(
                run_id=args.run_id,
                data_paths=data_paths,
                output_dir=Path(args.output_dir),
                symbols=symbols,
                setup_families=setup_families,  # type: ignore[arg-type]
                min_expected_move_bps=_csv_float_tuple(args.min_expected_move_bps, "--min-expected-move-bps"),
                risk_reward_ratios=_csv_float_tuple(args.risk_reward_ratios, "--risk-reward-ratios"),
                max_hold_hours=_csv_float_tuple(args.max_hold_hours, "--max-hold-hours"),
                exit_modes=exit_modes,  # type: ignore[arg-type]
                initial_capital_eur=args.initial_capital_eur,
                order_notional_eur=args.order_notional_eur,
                min_sample_trades_for_candidate=args.min_sample_trades_for_candidate,
                candidate_min_profit_factor=args.candidate_min_profit_factor,
                candidate_max_drawdown_bps=args.candidate_max_drawdown_bps,
                comparison_micro_report_path=micro_report,
                cost_config=_cost_config_from_args(args),
            )
        ),
        Path(args.output_dir),
    )
    _print_json(result.to_dict())
    return 0


def _cmd_high_conviction_portfolio_replay(args: argparse.Namespace) -> int:
    from autobot.v2.research.high_conviction_portfolio import (
        HighConvictionPortfolioConfig,
        build_high_conviction_portfolio_report,
        write_high_conviction_portfolio_report,
    )

    result = write_high_conviction_portfolio_report(
        build_high_conviction_portfolio_report(
            HighConvictionPortfolioConfig(
                run_id=args.run_id,
                data_paths=tuple(Path(path) for path in _csv_tuple(args.data_paths, "--data-paths")),
                output_dir=Path(args.output_dir),
                symbols=_csv_tuple(args.symbols, "--symbols", uppercase=True) if args.symbols else (),
                setup_families=_csv_tuple(args.setup_families, "--setup-families"),
                min_expected_move_bps=_csv_float_tuple(args.min_expected_move_bps, "--min-expected-move-bps"),
                risk_reward_ratios=_csv_float_tuple(args.risk_reward_ratios, "--risk-reward-ratios"),
                max_hold_hours=_csv_float_tuple(args.max_hold_hours, "--max-hold-hours"),
                exit_modes=_csv_tuple(args.exit_modes, "--exit-modes"),
                cost_profiles=_csv_tuple(args.cost_profiles, "--cost-profiles"),
                initial_capital_eur=args.initial_capital_eur,
                legacy_notional_eur=args.legacy_notional_eur,
                max_position_fraction=args.max_position_fraction,
                risk_per_trade_pct=args.risk_per_trade_pct,
                max_global_exposure_pct=args.max_global_exposure_pct,
                max_open_positions=args.max_open_positions,
                cooldown_hours=args.cooldown_hours,
                max_daily_loss_pct=args.max_daily_loss_pct,
                critical_drawdown_pct=args.critical_drawdown_pct,
                drawdown_reduce_start_pct=args.drawdown_reduce_start_pct,
                min_drawdown_exposure_multiplier=args.min_drawdown_exposure_multiplier,
                min_sample_trades_for_candidate=args.min_sample_trades_for_candidate,
                candidate_min_profit_factor=args.candidate_min_profit_factor,
                candidate_max_drawdown_pct=args.candidate_max_drawdown_pct,
            )
        ),
        Path(args.output_dir),
    )
    _print_json(result.to_dict())
    return 0


def _cmd_high_conviction_walk_forward(args: argparse.Namespace) -> int:
    from autobot.v2.research.high_conviction_walk_forward import (
        HighConvictionWalkForwardConfig,
        build_high_conviction_walk_forward_report,
        write_high_conviction_walk_forward_report,
    )

    result = write_high_conviction_walk_forward_report(
        build_high_conviction_walk_forward_report(
            HighConvictionWalkForwardConfig(
                run_id=args.run_id,
                data_paths=tuple(Path(path) for path in _csv_tuple(args.data_paths, "--data-paths")),
                output_dir=Path(args.output_dir),
                symbols=_csv_tuple(args.symbols, "--symbols", uppercase=True) if args.symbols else (),
                setup_families=_csv_tuple(args.setup_families, "--setup-families"),
                min_expected_move_bps=args.min_expected_move_bps,
                risk_reward_ratio=args.risk_reward_ratio,
                max_hold_hours=args.max_hold_hours,
                exit_modes=_csv_tuple(args.exit_modes, "--exit-modes"),
                primary_exit_mode=args.primary_exit_mode,
                initial_capital_eur=args.initial_capital_eur,
                max_position_fraction=args.max_position_fraction,
                risk_per_trade_pct=args.risk_per_trade_pct,
                max_global_exposure_pct=args.max_global_exposure_pct,
                max_open_positions=args.max_open_positions,
                cooldown_hours=args.cooldown_hours,
                max_daily_loss_pct=args.max_daily_loss_pct,
                critical_drawdown_pct=args.critical_drawdown_pct,
                drawdown_reduce_start_pct=args.drawdown_reduce_start_pct,
                min_drawdown_exposure_multiplier=args.min_drawdown_exposure_multiplier,
                train_window_bars=args.train_window_bars,
                test_window_bars=args.test_window_bars,
                step_window_bars=args.step_window_bars,
                min_folds=args.min_folds,
                min_positive_fold_ratio=args.min_positive_fold_ratio,
                min_closed_trades_for_review=args.min_closed_trades_for_review,
                min_profit_factor=args.min_profit_factor,
                max_drawdown_pct=args.max_drawdown_pct,
                max_single_symbol_positive_pnl_share=args.max_single_symbol_positive_pnl_share,
            )
        ),
        Path(args.output_dir),
    )
    _print_json(result.to_dict())
    return 0


def _cmd_strategy_orchestrator_research(args: argparse.Namespace) -> int:
    from autobot.v2.research.strategy_orchestrator import (
        StrategyOrchestratorConfig,
        build_strategy_orchestrator_report,
        write_strategy_orchestrator_report,
    )

    result = write_strategy_orchestrator_report(
        build_strategy_orchestrator_report(
            StrategyOrchestratorConfig(
                run_id=args.run_id,
                data_paths=tuple(Path(path) for path in _csv_tuple(args.data_paths, "--data-paths")),
                output_dir=Path(args.output_dir),
                instance_id=args.instance_id,
                initial_treasury_eur=args.initial_treasury_eur,
                symbols=_csv_tuple(args.symbols, "--symbols", uppercase=True) if args.symbols else (),
                cost_profiles=_csv_tuple(args.cost_profiles, "--cost-profiles"),
                max_instance_exposure_pct=args.max_instance_exposure_pct,
                max_strategy_exposure_pct=args.max_strategy_exposure_pct,
                max_symbol_exposure_pct=args.max_symbol_exposure_pct,
                risk_per_trade_pct=args.risk_per_trade_pct,
                max_open_positions=args.max_open_positions,
                cooldown_hours=args.cooldown_hours,
                max_daily_loss_pct=args.max_daily_loss_pct,
                max_drawdown_pct=args.max_drawdown_pct,
                min_research_meta_score=args.min_research_meta_score,
                signal_history_bars=args.signal_history_bars,
            )
        ),
        Path(args.output_dir),
    )
    _print_json(result.to_dict())
    return 0


def _cmd_strategy_edge_review(args: argparse.Namespace) -> int:
    from autobot.v2.research.strategy_edge_improvement import (
        StrategyEdgeReviewConfig,
        build_strategy_edge_improvement_report,
        write_strategy_edge_improvement_report,
    )

    result = write_strategy_edge_improvement_report(
        build_strategy_edge_improvement_report(
            StrategyEdgeReviewConfig(
                run_id=args.run_id,
                output_dir=Path(args.output_dir),
                report_date=args.report_date,
                strategy_orchestrator_report_path=(
                    Path(args.strategy_orchestrator_report) if args.strategy_orchestrator_report else None
                ),
                high_conviction_report_path=Path(args.high_conviction_report) if args.high_conviction_report else None,
                min_candidate_trades=args.min_candidate_trades,
                min_candidate_pf=args.min_candidate_pf,
                high_quality_pf=args.high_quality_pf,
                max_drawdown_pct=args.max_drawdown_pct,
                max_single_symbol_positive_share=args.max_single_symbol_positive_share,
            )
        ),
        Path(args.output_dir),
    )
    _print_json(result.to_dict())
    return 0


def _cmd_relative_value_portfolio_replay(args: argparse.Namespace) -> int:
    from autobot.v2.research.relative_value_engine import (
        RelativeValueConfig,
        build_relative_value_report,
        parse_relationships,
        write_relative_value_report,
    )

    result = write_relative_value_report(
        build_relative_value_report(
            RelativeValueConfig(
                run_id=args.run_id,
                data_paths=tuple(Path(path) for path in _csv_tuple(args.data_paths, "--data-paths")),
                output_dir=Path(args.output_dir),
                relationships=parse_relationships(args.relationships),
                timeframe=args.timeframe.lower(),
                rolling_window_bars=args.rolling_window_bars,
                entry_zscore=args.entry_zscore,
                exit_zscore=args.exit_zscore,
                min_correlation=args.min_correlation,
                max_cointegration_pvalue=args.max_cointegration_pvalue,
                require_cointegration_when_available=not bool(args.no_require_cointegration_when_available),
                cointegration_refresh_bars=args.cointegration_refresh_bars,
                min_expected_move_bps=args.min_expected_move_bps,
                min_expected_mfe_to_cost=args.min_expected_mfe_to_cost,
                fixed_take_profit_bps=args.fixed_take_profit_bps,
                fixed_stop_loss_bps=args.fixed_stop_loss_bps,
                trailing_activation_bps=args.trailing_activation_bps,
                trailing_distance_bps=args.trailing_distance_bps,
                max_hold_bars=args.max_hold_bars,
                initial_capital_eur=args.initial_capital_eur,
                max_position_fraction=args.max_position_fraction,
                risk_per_trade_pct=args.risk_per_trade_pct,
                max_global_exposure_pct=args.max_global_exposure_pct,
                max_open_positions=args.max_open_positions,
                cooldown_hours=args.cooldown_hours,
                max_daily_loss_pct=args.max_daily_loss_pct,
                max_drawdown_pct=args.max_drawdown_pct,
                min_order_notional_eur=args.min_order_notional_eur,
                max_volatility_bps=args.max_volatility_bps,
                cost_profiles=_csv_tuple(args.cost_profiles, "--cost-profiles"),
                comparison_high_conviction_report_path=(
                    Path(args.comparison_high_conviction_report)
                    if args.comparison_high_conviction_report
                    else None
                ),
            )
        ),
        Path(args.output_dir),
    )
    _print_json(result.to_dict())
    return 0


def _cmd_alpha_smoke_runner(args: argparse.Namespace) -> int:
    from autobot.v2.research.alpha_smoke_runner import (
        AlphaSmokeConfig,
        build_alpha_smoke_report,
        write_alpha_smoke_report,
    )

    result = write_alpha_smoke_report(
        build_alpha_smoke_report(
            AlphaSmokeConfig(
                run_id=args.run_id,
                data_paths=tuple(Path(path) for path in _csv_tuple(args.data_paths, "--data-paths")),
                hypotheses_path=Path(args.hypotheses_path),
                output_dir=Path(args.output_dir),
                symbols=_csv_tuple(args.symbols, "--symbols", uppercase=True),
                cost_profile=args.cost_profile,
                max_variants=args.max_variants,
                max_symbols=args.max_symbols,
                max_cpu_seconds=args.max_cpu_seconds,
                order_notional_eur=args.order_notional_eur,
            ),
            commit=args.commit,
        ),
        Path(args.output_dir),
    )
    _print_json(result.to_dict())
    return 0


def _cmd_volatility_breakout_walk_forward(args: argparse.Namespace) -> int:
    from autobot.v2.research.volatility_breakout_walk_forward import (
        VolatilityBreakoutWalkForwardConfig,
        build_volatility_breakout_walk_forward_report,
        write_volatility_breakout_walk_forward_report,
    )

    result = write_volatility_breakout_walk_forward_report(
        build_volatility_breakout_walk_forward_report(
            VolatilityBreakoutWalkForwardConfig(
                run_id=args.run_id,
                data_paths=tuple(Path(path) for path in _csv_tuple(args.data_paths, "--data-paths")),
                output_dir=Path(args.output_dir),
                symbols=_csv_tuple(args.symbols, "--symbols", uppercase=True),
                cost_profile=args.cost_profile,
                max_variants=args.max_variants,
                folds=args.folds,
                train_fraction=args.train_fraction,
                order_notional_eur=args.order_notional_eur,
                max_cpu_seconds=args.max_cpu_seconds,
            ),
            commit=args.commit,
        ),
        Path(args.output_dir),
    )
    _print_json(result.to_dict())
    return 0


def _cmd_alpha_hypothesis_runner(args: argparse.Namespace) -> int:
    from autobot.v2.research.alpha_hypothesis_runner import (
        AlphaHypothesisRunnerConfig,
        _current_git_commit,
        build_alpha_hypothesis_runner_report,
        write_alpha_hypothesis_runner_report,
    )
    from autobot.v2.research.alpha_hypothesis_scheduler import (
        load_strategy_templates,
        record_alpha_runner_trial,
    )

    run_id = args.run_id or f"alpha_hypothesis_runner_{args.hypothesis_id}_{args.mode}"
    data_paths = tuple(Path(path) for path in _csv_tuple(args.data_paths, "--data-paths")) if args.data_paths else ()
    pre_run_context = None
    pre_run_commit = str(args.commit or _current_git_commit() or "").strip()
    if args.feature_snapshot_manifest and pre_run_commit:
        pre_run_context = _prepare_alpha_experiment_context(
            args,
            data_paths=data_paths,
            hypothesis_id=args.hypothesis_id,
            code_commit=pre_run_commit,
        )
    if pre_run_context and pre_run_context.get("state") and pre_run_context["state"].terminal:
        state = pre_run_context["state"]
        _print_json(
            {
                "run_id": run_id,
                "hypothesis_id": state.hypothesis_id,
                "final_status": state.latest_status,
                "final_decision": "MATERIAL_EXPERIMENT_ALREADY_TERMINAL",
                "reasons": ["material_fingerprint_already_terminal", "new_data_thesis_or_template_required"],
                "experiment_registry": {
                    "path": str(Path(args.experiment_registry)),
                    "state": state.to_dict(),
                    "recorded": False,
                },
                "research_only": True,
                "paper_capital_allowed": False,
                "live_allowed": False,
                "promotable": False,
            }
        )
        return 0
    validation_trial_count_floor = int(pre_run_context.get("validation_trial_count") or 0) if pre_run_context else 0
    result = write_alpha_hypothesis_runner_report(
        build_alpha_hypothesis_runner_report(
            AlphaHypothesisRunnerConfig(
                run_id=run_id,
                hypothesis_id=args.hypothesis_id,
                mode=args.mode,
                hypotheses_path=Path(args.hypotheses_path),
                autonomy_policy_path=Path(args.autonomy_policy),
                templates_path=Path(args.templates),
                template_id=args.template_id,
                state_db=Path(args.state_db) if args.state_db else None,
                data_paths=data_paths,
                output_dir=Path(args.output_dir),
                symbols=_csv_tuple(args.symbols, "--symbols", uppercase=True),
                cost_profile=args.cost_profile,
                max_runtime_seconds=args.max_runtime_seconds,
                max_variants=args.max_variants,
                max_symbols=args.max_symbols,
                max_data_rows=args.max_data_rows,
                validation_trial_count_floor=validation_trial_count_floor,
                feature_snapshot_manifest=(
                    Path(args.feature_snapshot_manifest) if args.feature_snapshot_manifest else None
                ),
                derivatives_feature_snapshot_manifest=(
                    Path(args.derivatives_feature_snapshot_manifest)
                    if args.derivatives_feature_snapshot_manifest
                    else None
                ),
            ),
            commit=args.commit,
        ),
        Path(args.output_dir),
    )
    templates = load_strategy_templates(args.templates)
    template = _template_for_hypothesis(result.hypothesis_id, templates, template_id=args.template_id)
    if template is not None:
        record_alpha_runner_trial(
            result,
            memory_path=Path(args.memory_path),
            template_id=str(template["template_id"]),
            alpha_family_id=str(template["alpha_family_id"]),
        )
    payload = result.to_dict()
    if args.feature_snapshot_manifest:
        if pre_run_context is None:
            pre_run_context = _prepare_alpha_experiment_context(
                args,
                data_paths=data_paths,
                hypothesis_id=result.hypothesis_id,
                code_commit=str(result.commit or args.commit or ""),
            )
        if pre_run_context.get("derivatives_availability") is not None:
            derivatives_availability = pre_run_context["derivatives_availability"]
            if derivatives_availability.status != "READY":
                payload["experiment_registry"] = {
                    "recorded": False,
                    "reason": "derivatives_feature_snapshot_not_ready_for_material_experiment",
                    "derivatives_feature_snapshot": derivatives_availability.to_dict(),
                    "research_only": True,
                    "paper_capital_allowed": False,
                    "live_allowed": False,
                    "promotable": False,
                }
                _print_json(payload)
                return 0
        state = pre_run_context["registry"].record_runner_evidence(
            spec=pre_run_context["spec"],
            report=result,
            variant_count=args.max_variants,
            symbols=_csv_tuple(args.symbols, "--symbols", uppercase=True),
            timeframes=_optional_csv_tuple(args.trial_timeframes, "--trial-timeframes"),
            regimes=_optional_csv_tuple(args.trial_regimes, "--trial-regimes"),
            record_trial_dimensions=False,
        )
        payload["experiment_registry"] = {
            "path": str(Path(args.experiment_registry)),
            "state": state.to_dict(),
            "feature_snapshot": pre_run_context["provenance"].to_dict(),
            "derivatives_feature_snapshot": (
                dict(pre_run_context["spec"].environment["derivatives_snapshot"])
                if pre_run_context["spec"].environment.get("derivatives_snapshot")
                else None
            ),
            "validation_trial_count_floor": validation_trial_count_floor,
            "pre_registered_before_runner": validation_trial_count_floor > 0,
            "research_only": True,
            "paper_capital_allowed": False,
            "live_allowed": False,
            "promotable": False,
        }
    _print_json(payload)
    return 0


def _prepare_alpha_experiment_context(
    args: argparse.Namespace,
    *,
    data_paths: tuple[Path, ...],
    hypothesis_id: str,
    code_commit: str,
) -> dict[str, Any]:
    """Register a material research plan before a runner can calculate DSR.

    The helper is deliberately CLI-side: the research runner stays independent
    from SQLite and receives only a conservative trial-count floor.
    """

    from autobot.v2.research.alpha_hypothesis_lab import load_alpha_hypotheses
    from autobot.v2.research.alpha_hypothesis_scheduler import load_strategy_templates
    from autobot.v2.research.alpha_hypothesis_runner import canonical_hypothesis_id
    from autobot.v2.research.derivatives_feature_snapshot import inspect_derivatives_feature_snapshot_manifest
    from autobot.v2.research.experiment_registry import ExperimentRegistry
    from autobot.v2.research.manifested_experiment import build_manifested_experiment_spec

    resolved_hypothesis_id = canonical_hypothesis_id(hypothesis_id)
    templates = load_strategy_templates(args.templates)
    template = _template_for_hypothesis(resolved_hypothesis_id, templates, template_id=args.template_id)
    if template is None:
        raise ValueError("a registered strategy template is required for manifested experiment evidence")
    hypotheses = load_alpha_hypotheses(args.hypotheses_path)
    hypothesis = next(
        (item for item in hypotheses.get("hypotheses", ()) if str(item.get("id") or "") == resolved_hypothesis_id),
        None,
    )
    if not isinstance(hypothesis, dict):
        raise ValueError(f"hypothesis metadata missing for {resolved_hypothesis_id}")
    resolved_commit = str(code_commit or "").strip()
    if not resolved_commit:
        raise ValueError("a code commit is required for manifested experiment evidence")

    derivatives_availability = None
    if args.derivatives_feature_snapshot_manifest:
        derivatives_availability = inspect_derivatives_feature_snapshot_manifest(
            Path(args.derivatives_feature_snapshot_manifest)
        )
        if derivatives_availability.status != "READY":
            return {"derivatives_availability": derivatives_availability}

    timeframes = _optional_csv_tuple(args.trial_timeframes, "--trial-timeframes")
    regimes = _optional_csv_tuple(args.trial_regimes, "--trial-regimes")
    symbols = _csv_tuple(args.symbols, "--symbols", uppercase=True)
    spec, provenance = build_manifested_experiment_spec(
        hypothesis_id=resolved_hypothesis_id,
        template_id=str(template["template_id"]),
        thesis=str(hypothesis["thesis"]),
        code_commit=resolved_commit,
        feature_snapshot_manifest=Path(args.feature_snapshot_manifest),
        derivatives_snapshot_manifest=(
            Path(args.derivatives_feature_snapshot_manifest) if args.derivatives_feature_snapshot_manifest else None
        ),
        parameters={
            "max_variants": args.max_variants,
            "max_symbols": args.max_symbols,
            "max_data_rows": args.max_data_rows,
            "symbols": list(symbols),
            "trial_timeframes": list(timeframes),
            "trial_regimes": list(regimes),
        },
        seed=args.experiment_seed,
        cost_model={"profile": args.cost_profile},
        environment={"data_paths": [str(path) for path in data_paths]},
        holdout_id=args.holdout_id,
    )
    registry = ExperimentRegistry(Path(args.experiment_registry))
    state = registry.register_experiment(spec)
    if not state.terminal:
        registry.record_trial_plan(
            experiment_id=state.experiment_id,
            variant_count=args.max_variants,
            symbols=symbols,
            timeframes=timeframes,
            regimes=regimes,
        )
    return {
        "registry": registry,
        "spec": spec,
        "provenance": provenance,
        "state": state,
        "validation_trial_count": registry.validation_trial_count(hypothesis_id=spec.hypothesis_id),
        "derivatives_availability": derivatives_availability,
    }


def _cmd_experiment_registry_migrate_memory(args: argparse.Namespace) -> int:
    """Migrate historical research observations without treating them as gate proof."""

    from autobot.v2.research.alpha_hypothesis_scheduler import load_alpha_research_memory
    from autobot.v2.research.experiment_registry import ExperimentRegistry

    memory = load_alpha_research_memory(Path(args.memory_path))
    registry = ExperimentRegistry(Path(args.registry_path))
    inserted = registry.migrate_legacy_memory(record.to_dict() for record in memory.records)
    _print_json(
        {
            "registry_path": str(Path(args.registry_path)),
            "memory_path": str(Path(args.memory_path)),
            "legacy_records_seen": len(memory.records),
            "legacy_records_inserted": inserted,
            "research_only": True,
            "paper_capital_allowed": False,
            "live_allowed": False,
            "promotable": False,
        }
    )
    return 0


def _cmd_experiment_registry_reserve_holdout(args: argparse.Namespace) -> int:
    """Reserve immutable data for a final review, never for optimization."""

    from autobot.v2.research.experiment_registry import ExperimentRegistry

    manifest: dict[str, Any] = {}
    if args.manifest_path:
        try:
            loaded = json.loads(Path(args.manifest_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid holdout manifest: {args.manifest_path}") from exc
        if not isinstance(loaded, dict):
            raise ValueError("holdout manifest must be a JSON object")
        manifest = loaded
    registry = ExperimentRegistry(Path(args.registry_path))
    created = registry.reserve_holdout(
        holdout_id=args.holdout_id,
        data_snapshot_id=args.data_snapshot_id,
        immutable_fingerprint=args.immutable_fingerprint,
        manifest=manifest,
    )
    _print_json(
        {
            "registry_path": str(Path(args.registry_path)),
            "holdout_id": args.holdout_id,
            "data_snapshot_id": args.data_snapshot_id,
            "reserved": created,
            "optimization_allowed": False,
            "research_only": True,
            "paper_capital_allowed": False,
            "live_allowed": False,
            "promotable": False,
        }
    )
    return 0


def _cmd_experiment_registry_record_final_holdout_review(args: argparse.Namespace) -> int:
    """Record immutable final-holdout evidence without changing any execution mode."""

    from autobot.v2.research.experiment_registry import ExperimentRegistry

    try:
        metrics = json.loads(args.metrics_json)
    except json.JSONDecodeError as exc:
        raise ValueError("--metrics-json must be a JSON object") from exc
    if not isinstance(metrics, dict):
        raise ValueError("--metrics-json must be a JSON object")
    reasons = _optional_csv_tuple(args.reasons, "--reasons")
    registry = ExperimentRegistry(Path(args.registry_path))
    trial_id = registry.record_final_holdout_review(
        experiment_id=args.experiment_id,
        metrics=metrics,
        reasons=reasons,
    )
    _print_json(
        {
            "registry_path": str(registry.path),
            "experiment_id": args.experiment_id,
            "trial_id": trial_id,
            "final_holdout_review_recorded": registry.has_final_holdout_review(args.experiment_id),
            "optimization_allowed": False,
            "research_only": True,
            "paper_capital_allowed": False,
            "live_allowed": False,
            "promotable": False,
        }
    )
    return 0


def _cmd_strategy_artifact_register(args: argparse.Namespace) -> int:
    """Persist immutable research/shadow governance evidence only.

    This command does not route a signal, start a shadow service, allocate
    capital or create an order. Shadow-capable statuses remain contingent on a
    passed terminal experiment plus an explicit human approval reference.
    """

    from autobot.v2.research.experiment_registry import ExperimentRegistry
    from autobot.v2.research.shadow_governance import (
        StrategyArtifactRegistry,
        build_strategy_artifact_from_experiment,
    )
    from autobot.v2.research.strategy_risk_mandates import (
        load_strategy_risk_mandates,
        risk_mandate_reference,
    )

    experiment_registry = ExperimentRegistry(Path(args.experiment_registry_path))
    shadow_statuses = {"SHADOW_ELIGIBLE", "SHADOW", "THROTTLED", "QUARANTINED"}
    risk_mandate = None
    if str(args.status).upper() in shadow_statuses:
        mandate_id = str(args.risk_mandate_id or "").strip()
        if not mandate_id:
            raise ValueError("--risk-mandate-id is required for a shadow-capable artifact")
        mandates = load_strategy_risk_mandates(Path(args.risk_mandates))
        source_mandate = next(
            (item for item in mandates.values() if item.mandate_id == mandate_id),
            None,
        )
        if source_mandate is None:
            raise ValueError("--risk-mandate-id was not found in --risk-mandates")
        risk_mandate = risk_mandate_reference(source_mandate)
        if risk_mandate.fingerprint != str(args.risk_mandate_fingerprint).strip():
            raise ValueError("--risk-mandate-fingerprint does not match immutable mandate evidence")
    artifact = build_strategy_artifact_from_experiment(
        experiment_registry=experiment_registry,
        experiment_id=args.experiment_id,
        strategy_version=args.strategy_version,
        risk_mandate_fingerprint=args.risk_mandate_fingerprint,
        validation_manifest_fingerprint=args.validation_manifest_fingerprint,
        risk_mandate=risk_mandate,
        requested_status=args.status,
        human_approval_reference=args.human_approval_reference,
    )
    artifact_registry = StrategyArtifactRegistry(
        Path(args.artifact_registry_path),
        experiment_registry_path=experiment_registry.path,
    )
    artifact_id = artifact_registry.register(artifact)
    _print_json(
        {
            "artifact_id": artifact_id,
            "artifact": artifact.to_dict(),
            "experiment_registry_path": str(experiment_registry.path),
            "artifact_registry_path": str(artifact_registry.path),
            "risk_mandate_id": risk_mandate.mandate_id if risk_mandate else None,
            "research_only": True,
            "shadow_runtime_started": False,
            "paper_capital_allowed": False,
            "live_allowed": False,
            "automatic_promotion_allowed": False,
        }
    )
    return 0


def _cmd_strategy_artifact_resolve_reference(args: argparse.Namespace) -> int:
    """Resolve immutable shadow provenance for offline/batch binding only."""

    from autobot.v2.contracts import contract_to_dict
    from autobot.v2.research.shadow_governance import StrategyArtifactRegistry

    registry = StrategyArtifactRegistry(Path(args.artifact_registry_path))
    reference = registry.resolve_shadow_order_intent_reference(args.artifact_id)
    _print_json(
        {
            "artifact_registry_path": str(registry.path),
            "strategy_artifact_reference": contract_to_dict(reference),
            "research_only": True,
            "shadow_runtime_started": False,
            "paper_capital_allowed": False,
            "live_allowed": False,
            "automatic_promotion_allowed": False,
        }
    )
    return 0


def _cmd_alpha_hypothesis_scheduler(args: argparse.Namespace) -> int:
    from dataclasses import replace

    from autobot.v2.research.alpha_hypothesis_scheduler import (
        AlphaSchedulerConfig,
        backfill_alpha_research_memory,
        build_alpha_hypothesis_scheduler_report,
        write_alpha_hypothesis_scheduler_report,
    )

    run_id = args.run_id or "alpha_hypothesis_scheduler"
    backfill = None
    if not args.no_memory_backfill:
        backfill = backfill_alpha_research_memory(memory_path=Path(args.memory_path))
    
    built = build_alpha_hypothesis_scheduler_report(
        AlphaSchedulerConfig(
            run_id=run_id,
            state_db=Path(args.state_db) if args.state_db else None,
            data_paths=tuple(Path(path) for path in _csv_tuple(args.data_paths, "--data-paths")),
            knowledge_base_path=Path(args.knowledge_base),
            templates_path=Path(args.templates),
            hypotheses_path=Path(args.hypotheses),
            memory_path=Path(args.memory_path),
            output_dir=Path(args.output_dir),
            max_variants=args.max_variants,
            max_symbols=args.max_symbols,
            max_runtime_seconds=args.max_runtime_seconds,
        )
    )
    if backfill is not None:
        built = replace(built, memory_backfill=backfill)
    report = write_alpha_hypothesis_scheduler_report(
        built,
        Path(args.output_dir),
    )
    _print_json(report.to_dict())
    return 0


def _cmd_data_capability_scan(args: argparse.Namespace) -> int:
    from autobot.v2.research.data_capability_scanner import (
        build_data_capability_scan_report,
        write_data_capability_scan_report,
    )

    run_id = args.run_id or f"p18h_data_capability_scan_{date.today().strftime('%Y%m%d')}"
    report = write_data_capability_scan_report(
        build_data_capability_scan_report(
            run_id=run_id,
            state_db=Path(args.state_db) if args.state_db else None,
            data_roots=tuple(Path(path) for path in _csv_tuple(args.data_roots, "--data-roots")),
            memory_path=Path(args.memory_path),
        ),
        Path(args.output_dir),
    )
    _print_json(report.to_dict())
    return 0


def _cmd_canonicalize_ohlcv(args: argparse.Namespace) -> int:
    from autobot.v2.research.canonical_ohlcv_store import (
        CanonicalOHLCVConfig,
        build_canonical_ohlcv_snapshot,
        write_canonical_ohlcv_report,
    )

    run_id = args.run_id or f"p18i_canonical_ohlcv_{date.today().strftime('%Y%m%d')}"
    market_mappings = None
    if args.market_mapping_source == "kraken_public":
        from autobot.v2.research.kraken_symbol_mapping import build_kraken_public_symbol_registry

        market_mappings = build_kraken_public_symbol_registry().explicit_market_mappings()
    snapshot = build_canonical_ohlcv_snapshot(
        CanonicalOHLCVConfig(
            run_id=run_id,
            raw_paths=tuple(Path(path) for path in _csv_tuple(args.raw_paths, "--raw-paths")),
            output_dir=Path(args.output_dir),
            manifest_dir=Path(args.manifest_dir),
            quarantine_dir=Path(args.quarantine_dir),
            exchange=args.exchange,
            market_type=args.market_type,
            market_mappings=market_mappings,
            max_files=args.max_files,
            max_rows=args.max_rows,
        )
    )
    json_path, markdown_path = write_canonical_ohlcv_report(snapshot, Path(args.report_dir))
    payload = {
        **snapshot.to_dict(),
        "market_mapping_source": args.market_mapping_source,
        "explicit_market_mapping_count": len(market_mappings or {}),
        "json_report_path": str(json_path),
        "markdown_report_path": str(markdown_path),
    }
    _print_json(payload)
    return 0


def _cmd_sqlite_restore_drill(args: argparse.Namespace) -> int:
    from dataclasses import asdict

    from autobot.v2.research.resilience_readiness import verify_sqlite_restore_drill

    manifest = verify_sqlite_restore_drill(Path(args.backup_path))
    _print_json(asdict(manifest))
    return 0


def _cmd_runtime_oms_ledger_audit(args: argparse.Namespace) -> int:
    from autobot.v2.research.runtime_oms_ledger_audit import audit_runtime_oms_ledger

    _print_json(audit_runtime_oms_ledger(Path(args.state_db)).to_dict())
    return 0


def _cmd_runtime_oms_ledger_migration_plan(args: argparse.Namespace) -> int:
    from autobot.v2.research.runtime_oms_ledger_migration_plan import plan_runtime_oms_ledger_migration

    _print_json(plan_runtime_oms_ledger_migration(Path(args.state_db)).to_dict())
    return 0


def _cmd_materialize_feature_snapshot(args: argparse.Namespace) -> int:
    from autobot.v2.research.canonical_feature_snapshot import (
        CanonicalFeatureSnapshotConfig,
        build_canonical_feature_snapshot,
        write_canonical_feature_snapshot_report,
    )

    run_id = args.run_id or f"canonical_features_{date.today().strftime('%Y%m%d')}"
    snapshot = build_canonical_feature_snapshot(
        CanonicalFeatureSnapshotConfig(
            run_id=run_id,
            canonical_manifest_path=Path(args.canonical_manifest),
            output_dir=Path(args.output_dir),
            manifest_dir=Path(args.manifest_dir),
            feature_ids=_csv_tuple(args.feature_ids, "--feature-ids"),
        )
    )
    json_path, markdown_path = write_canonical_feature_snapshot_report(snapshot, Path(args.report_dir))
    _print_json({**snapshot.to_dict(), "json_report_path": str(json_path), "markdown_report_path": str(markdown_path)})
    return 0


def _cmd_materialize_derivatives_feature_snapshot(args: argparse.Namespace) -> int:
    from autobot.v2.research.derivatives_feature_snapshot import (
        DerivativesFeatureSnapshotConfig,
        build_derivatives_feature_snapshot,
        write_derivatives_feature_snapshot_report,
    )

    run_id = args.run_id or f"derivatives_features_{date.today().strftime('%Y%m%d')}"
    snapshot = build_derivatives_feature_snapshot(
        DerivativesFeatureSnapshotConfig(
            run_id=run_id,
            derivatives_manifest_path=Path(args.derivatives_manifest),
            as_of_time=_parse_datetime(args.as_of_time),
            output_dir=Path(args.output_dir),
            manifest_dir=Path(args.manifest_dir),
            feature_ids=_csv_tuple(args.feature_ids, "--feature-ids"),
        )
    )
    json_path, markdown_path = write_derivatives_feature_snapshot_report(snapshot, Path(args.report_dir))
    _print_json({**snapshot.to_dict(), "json_report_path": str(json_path), "markdown_report_path": str(markdown_path)})
    return 0


def _cmd_upgrade_feature_snapshot_manifest(args: argparse.Namespace) -> int:
    from autobot.v2.research.canonical_feature_snapshot import upgrade_feature_snapshot_manifest

    output = upgrade_feature_snapshot_manifest(args.source_manifest, args.output_manifest)
    _print_json(
        {
            "source_manifest": str(Path(args.source_manifest)),
            "upgraded_manifest": str(output),
            "research_only": True,
            "paper_capital_allowed": False,
            "live_allowed": False,
            "promotable": False,
        }
    )
    return 0


def _cmd_collect_kraken_futures_derivatives(args: argparse.Namespace) -> int:
    from autobot.v2.research.kraken_futures_derivatives_collector import (
        KrakenFuturesCollectorConfig,
        collect_kraken_futures_derivatives,
    )

    run_id = args.run_id or f"p18j_kraken_futures_derivatives_{date.today().strftime('%Y%m%d')}"
    result = collect_kraken_futures_derivatives(
        KrakenFuturesCollectorConfig(
            run_id=run_id,
            priority_assets=tuple(item.strip().upper() for item in _csv_tuple(args.assets, "--assets")),
            max_symbols=args.max_symbols,
            tick_types=tuple(item.strip().lower() for item in _csv_tuple(args.tick_types, "--tick-types")),
            resolution=args.resolution,
            max_candles=args.max_candles,
            raw_dir=Path(args.raw_dir),
            canonical_dir=Path(args.canonical_dir),
            manifest_dir=Path(args.manifest_dir),
            report_dir=Path(args.report_dir),
            collect_funding=not args.skip_funding,
            collect_tickers=not args.skip_tickers,
            collect_candles=not args.skip_candles,
            sleep_seconds=args.sleep_seconds,
            timeout_seconds=args.timeout_seconds,
            continue_on_error=args.continue_on_error,
            raw_retention_days=args.raw_retention_days,
        )
    )
    _print_json(result.to_dict())
    return 0


def _cmd_strategy_autonomy_check(args: argparse.Namespace) -> int:
    from autobot.v2.research.strategy_risk_mandates import (
        AutoKillDowngradeEngine,
        PreTradeAutonomyGate,
        StrategyHealthSnapshot,
        build_default_request,
        load_strategy_risk_mandates,
    )

    mandates = load_strategy_risk_mandates(args.mandates)
    mandate = mandates.get(args.strategy_id)
    request = build_default_request(args.strategy_id)
    gate_decision = PreTradeAutonomyGate().evaluate(mandate, request, StrategyHealthSnapshot())
    gate_payload = gate_decision.to_dict()
    kill_decision = (
        AutoKillDowngradeEngine().evaluate(mandate, StrategyHealthSnapshot()).to_dict()
        if mandate is not None
        else None
    )
    payload = {
        "strategy_id": args.strategy_id,
        "state_db": args.state_db,
        "mandate_active": mandate is not None,
        "mandate": mandate.to_dict() if mandate else None,
        "pre_trade_autonomy": gate_payload,
        "auto_kill_downgrade": kill_decision,
        "passed_checks": gate_payload["passed_checks"],
        "failed_checks": gate_payload["failed_checks"],
        "blockers": gate_payload["blockers"],
        "warnings": gate_payload["warnings"],
        "final_decision": gate_payload["final_decision"],
        "risk_direction": gate_payload["risk_direction"],
        "human_review_required": gate_payload["requires_human_approval"],
        "paper_capital_allowed": False,
        "live_allowed": False,
        "promotable": False,
    }
    _print_json(payload)
    return 0


def _template_for_hypothesis(
    hypothesis_id: str,
    templates_payload: dict[str, Any],
    *,
    template_id: str | None = None,
) -> dict[str, Any] | None:
    family_by_hypothesis = {
        "volatility_breakout": "volatility_breakout",
        "long_trend": "trend_momentum",
        "cross_momentum": "cross_sectional_momentum",
        "funding_basis": "funding_basis",
        "liquidation_cascade": "liquidation_cascade",
    }
    family_id = family_by_hypothesis.get(hypothesis_id)
    if family_id is None:
        return None
    if template_id:
        for template in templates_payload.get("templates", []):
            if template.get("template_id") == template_id and template.get("alpha_family_id") == family_id:
                return dict(template)
        return None
    for template in templates_payload.get("templates", []):
        if template.get("alpha_family_id") == family_id and template.get("required_adapter") in {
            "volatility_breakout",
            "long_trend",
            "generic_cross_sectional_ohlcv_adapter",
        }:
            return dict(template)
    for template in templates_payload.get("templates", []):
        if template.get("alpha_family_id") == family_id:
            return dict(template)
    return None


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


def _cmd_paper_performance_summary(args: argparse.Namespace) -> int:
    from autobot.v2.paper.official_performance import (
        OfficialPaperPerformanceConfig,
        build_official_paper_performance_report,
    )

    report = build_official_paper_performance_report(
        OfficialPaperPerformanceConfig(
            state_db_path=Path(args.state_db),
            registry_path=Path(args.registry_path),
            output_dir=Path(args.output_dir),
            run_id=args.run_id,
            initial_capital_eur=args.initial_capital_eur,
        ),
        write_report=not args.no_write_report,
    )
    _print_json(report.to_dict())
    return 0


def _cmd_shadow_paper_observations(args: argparse.Namespace) -> int:
    from autobot.v2.paper.shadow_observation_sync import (
        ShadowPaperObservationSyncConfig,
        sync_shadow_paper_observations,
    )

    report = sync_shadow_paper_observations(
        ShadowPaperObservationSyncConfig(
            state_db_path=Path(args.state_db),
            registry_path=Path(args.registry_path),
            trend_shadow_db_path=Path(args.trend_shadow_db),
            mean_reversion_shadow_db_path=Path(args.mean_reversion_shadow_db),
            high_conviction_data_paths=(
                tuple(Path(item) for item in _csv_tuple(args.high_conviction_data_paths, "--high-conviction-data-paths"))
                if args.high_conviction_data_paths
                else ()
            ),
            high_conviction_feature_snapshot_manifest=(
                Path(args.high_conviction_feature_snapshot_manifest)
                if args.high_conviction_feature_snapshot_manifest
                else None
            ),
            output_dir=Path(args.output_dir),
            high_conviction_output_dir=(
                Path(args.high_conviction_output_dir) if args.high_conviction_output_dir else None
            ),
            run_id=args.run_id,
            write_report=not args.no_write_report,
        ),
        write_report=not args.no_write_report,
    )
    _print_json(report.to_dict())
    return 0


def _cmd_paper_loss_diagnostics(args: argparse.Namespace) -> int:
    from autobot.v2.paper.loss_diagnostics import (
        PaperLossDiagnosticsConfig,
        build_paper_loss_diagnostics_report,
    )

    report = build_paper_loss_diagnostics_report(
        PaperLossDiagnosticsConfig(
            state_db_path=Path(args.state_db),
            registry_path=Path(args.registry_path),
            output_dir=Path(args.output_dir),
            run_id=args.run_id,
            initial_capital_eur=args.initial_capital_eur,
            min_segment_trades=args.min_segment_trades,
        ),
        write_report=not args.no_write_report,
    )
    _print_json(report.to_dict())
    return 0


def _cmd_expected_move_diagnostics(args: argparse.Namespace) -> int:
    from autobot.v2.paper.expected_move_diagnostics import (
        ExpectedMoveDiagnosticsConfig,
        build_expected_move_diagnostics,
        write_expected_move_diagnostics,
    )

    report = build_expected_move_diagnostics(
        ExpectedMoveDiagnosticsConfig(
            state_db_path=Path(args.state_db),
            output_dir=Path(args.output_dir),
            run_id=args.run_id,
            since=args.since,
            high_conviction_data_paths=(
                tuple(Path(item) for item in _csv_tuple(args.high_conviction_data_paths, "--high-conviction-data-paths"))
                if args.high_conviction_data_paths
                else ()
            ),
            write_report=not args.no_write_report,
        )
    )
    if not args.no_write_report:
        write_expected_move_diagnostics(report, Path(args.output_dir))
    _print_json(report)
    return 0


def _cmd_check_db_integrity(args: argparse.Namespace) -> int:
    from autobot.v2.paper.db_integrity import DbIntegrityConfig, build_db_integrity_report

    report = build_db_integrity_report(
        DbIntegrityConfig(
            state_db_path=Path(args.state_db),
            output_dir=Path(args.output_dir),
            run_id=args.run_id,
            snapshot_dir=Path(args.snapshot_dir) if args.snapshot_dir else None,
            write_report=not args.no_write_report,
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


def _optional_csv_tuple(text: str | None, label: str, *, uppercase: bool = False) -> tuple[str, ...]:
    if not str(text or "").strip():
        return ()
    return _csv_tuple(str(text), label, uppercase=uppercase)


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
