"""Standard read-only AUTOBOT validation bundle.

This runner orchestrates the existing research and paper-reporting tools into a
single repeatable workflow. It does not start runtime services, submit orders,
mutate the strategy registry, or grant live trading permission.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from autobot.v2.paper.ledger_loader import load_state_db_paper_ledger
from autobot.v2.paper.paper_trading_engine import PaperDailyConfig, PaperTradingEngine
from autobot.v2.pnl_causality_audit import PnlCausalityAuditEngine, PnlCausalityConfig
from autobot.v2.research.cost_parity_audit import CostParityAuditConfig, audit_cost_parity, write_cost_parity_audit_report
from autobot.v2.research.dataset_builder import DatasetBuildConfig, build_dataset_from_state_db
from autobot.v2.research.decision_trace_audit import (
    DecisionTraceAuditConfig,
    audit_decision_traces,
    write_decision_trace_audit_report,
)
from autobot.v2.research.execution_cost_model import ExecutionCostConfig
from autobot.v2.research.loss_attribution import write_matrix_loss_attribution_report
from autobot.v2.research.paper_research_comparison import (
    compare_paper_to_research,
    write_paper_research_comparison_report,
)
from autobot.v2.research.registry_recommendations import (
    recommend_from_matrix,
    write_registry_recommendation_report,
)
from autobot.v2.research.setup_quality import write_matrix_setup_quality_report
from autobot.v2.research.strategy_regime_baselines import write_matrix_strategy_regime_baseline_report
from autobot.v2.research.strategy_regime_report import write_matrix_strategy_regime_report
from autobot.v2.research.strategy_regime_walk_forward import write_matrix_strategy_regime_walk_forward_report
from autobot.v2.research.strategy_scorecard import score_matrix, write_strategy_scorecard_report
from autobot.v2.research.validation_matrix import MatrixRunConfig, run_validation_matrix
from autobot.v2.strategy_validation_registry import load_registry


@dataclass(frozen=True)
class StandardAuditConfig:
    run_id: str
    state_db_path: Path
    output_dir: Path = Path("reports/research_standard")
    dataset_output_dir: Path | None = None
    symbols: tuple[str, ...] = ()
    strategies: tuple[str, ...] = ("grid", "trend", "mean_reversion")
    timeframe: str = "5m"
    mode: str = "backtest"
    report_date: date | None = None
    initial_capital_eur: float = 1_000.0
    order_notional_eur: float = 100.0
    min_closed_trades: int = 30
    min_profit_factor: float = 1.2
    max_drawdown_pct: float = 15.0
    min_signal_net_edge_bps: float | None = None
    start_at: str | None = None
    end_at: str | None = None
    limit: int | None = None
    train_window_bars: int = 200
    test_window_bars: int = 100
    step_window_bars: int | None = None
    min_folds: int = 3
    min_passing_folds: int = 2
    include_regime_context: bool = False
    cost_config: ExecutionCostConfig = field(default_factory=ExecutionCostConfig)
    strategy_configs: dict[str, dict[str, Any]] = field(default_factory=dict)
    registry_path: Path = Path("docs/research/strategy_hypotheses.json")
    trend_shadow_db_path: Path | None = None
    mean_reversion_shadow_db_path: Path | None = None
    setup_shadow_db_path: Path | None = None
    decision_trace_limit: int = 10_000
    decision_trace_sample_limit: int = 2_000
    pnl_causality_window_hours: int = 720
    export_parquet: bool = False

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id must not be empty")
        if not self.symbols:
            raise ValueError("symbols must not be empty")
        if not self.strategies:
            raise ValueError("strategies must not be empty")
        if self.mode not in {"backtest", "walk_forward"}:
            raise ValueError("mode must be backtest or walk_forward")


@dataclass(frozen=True)
class PnlCausalityArtifact:
    summary: dict[str, Any]
    json_report_path: str
    markdown_report_path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": dict(self.summary),
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
        }


@dataclass(frozen=True)
class StandardAuditResult:
    run_id: str
    generated_at: str
    output_dir: str
    report_date: str
    dataset: dict[str, Any]
    matrix: dict[str, Any]
    paper_loader: dict[str, Any]
    paper_daily: dict[str, Any]
    paper_vs_research: dict[str, Any]
    decision_trace: dict[str, Any]
    cost_parity: dict[str, Any]
    pnl_causality: dict[str, Any]
    json_report_path: str | None = None
    markdown_report_path: str | None = None
    safety_notes: tuple[str, ...] = (
        "Standard AUTOBOT audit is read-only.",
        "No runtime paper/live service is started.",
        "No paper or live order is created.",
        "No strategy registry mutation is performed.",
        "No Kraken order can be created by this command.",
        "No live trading permission is granted.",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": "standard-audit",
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "output_dir": self.output_dir,
            "report_date": self.report_date,
            "dataset": self.dataset,
            "matrix": self.matrix,
            "paper_loader": self.paper_loader,
            "paper_daily": self.paper_daily,
            "paper_vs_research": self.paper_vs_research,
            "decision_trace": self.decision_trace,
            "cost_parity": self.cost_parity,
            "pnl_causality": self.pnl_causality,
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
            "safety_notes": list(self.safety_notes),
        }


def run_standard_audit(config: StandardAuditConfig) -> StandardAuditResult:
    """Run the canonical research + paper comparison workflow."""

    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    dataset_output_dir = config.dataset_output_dir or (Path("data/research") / config.run_id)

    dataset = build_dataset_from_state_db(
        DatasetBuildConfig(
            run_id=f"{config.run_id}_dataset",
            state_db_path=config.state_db_path,
            output_dir=dataset_output_dir,
            symbols=config.symbols,
            timeframes=(config.timeframe,),
            start_at=config.start_at,
            end_at=config.end_at,
            limit=config.limit,
            export_csv=True,
            export_parquet=config.export_parquet,
            canonicalize_symbols=True,
        )
    )
    export = next((item for item in dataset.exports if item.timeframe == config.timeframe), None)
    if export is None or not export.csv_path:
        raise ValueError(f"dataset export for timeframe {config.timeframe!r} did not produce a CSV path")

    matrix_config = MatrixRunConfig(
        run_id=f"{config.run_id}_matrix",
        data_source="csv",
        data_path=Path(export.csv_path),
        symbols=config.symbols,
        strategies=config.strategies,  # type: ignore[arg-type]
        mode=config.mode,  # type: ignore[arg-type]
        output_dir=output_dir / "research_matrix",
        initial_capital_eur=config.initial_capital_eur,
        order_notional_eur=config.order_notional_eur,
        min_closed_trades=config.min_closed_trades,
        min_profit_factor=config.min_profit_factor,
        max_drawdown_pct=config.max_drawdown_pct,
        min_signal_net_edge_bps=config.min_signal_net_edge_bps,
        cost_config=config.cost_config,
        strategy_configs=config.strategy_configs,
        start_at=config.start_at,
        end_at=config.end_at,
        limit=None,
        train_window_bars=config.train_window_bars,
        test_window_bars=config.test_window_bars,
        step_window_bars=config.step_window_bars,
        min_folds=config.min_folds,
        min_passing_folds=config.min_passing_folds,
        include_regime_context=config.include_regime_context,
    )
    matrix = run_validation_matrix(matrix_config)
    matrix_payload = matrix.to_dict()
    _attach_standard_matrix_reports(
        config=matrix_config,
        result=matrix,
        output=matrix_payload,
        output_dir=matrix_config.output_dir,
        registry_path=config.registry_path,
        mode=config.mode,
    )

    loaded_paper = load_state_db_paper_ledger(config.state_db_path)
    report_date = config.report_date or _latest_report_date(loaded_paper.journal.records)
    paper_daily = PaperTradingEngine(
        PaperDailyConfig(
            report_date=report_date,
            run_id=f"{config.run_id}_paper_daily",
            initial_capital_eur=config.initial_capital_eur,
            output_dir=output_dir / "paper_daily",
        )
    ).build_daily_report(loaded_paper.journal, loaded_paper.decisions, write_report=True)

    decision_trace = write_decision_trace_audit_report(
        audit_decision_traces(
            DecisionTraceAuditConfig(
                state_db_path=str(config.state_db_path),
                run_id=f"{config.run_id}_decision_trace",
                limit=config.decision_trace_limit,
                trace_sample_limit=config.decision_trace_sample_limit,
            )
        ),
        output_dir / "decision_trace",
    )
    comparison = write_paper_research_comparison_report(
        compare_paper_to_research(
            loaded_paper.journal,
            matrix,
            run_id=f"{config.run_id}_paper_vs_research",
            paper_source_type=loaded_paper.source_type,
            paper_source_path=loaded_paper.source_path,
            initial_capital_eur=config.initial_capital_eur,
            warnings=loaded_paper.warnings,
            decision_trace_report=decision_trace,
        ),
        output_dir / "paper_vs_research",
    )
    cost_parity = write_cost_parity_audit_report(
        audit_cost_parity(
            CostParityAuditConfig(
                run_id=f"{config.run_id}_cost_parity",
                state_db_path=config.state_db_path,
                trend_shadow_db_path=config.trend_shadow_db_path,
                mean_reversion_shadow_db_path=config.mean_reversion_shadow_db_path,
                setup_shadow_db_path=config.setup_shadow_db_path,
                output_dir=output_dir / "cost_parity",
                research_cost_config=config.cost_config,
            )
        ),
        output_dir / "cost_parity",
    )
    pnl_causality = _write_pnl_causality_artifact(
        PnlCausalityAuditEngine(
            PnlCausalityConfig(window_hours=config.pnl_causality_window_hours, limit=50_000)
        ).build_snapshot(state_db_path=config.state_db_path, paper_mode=True),
        output_dir / "pnl_causality",
        f"{config.run_id}_pnl_causality",
    )

    result = StandardAuditResult(
        run_id=config.run_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        output_dir=str(output_dir),
        report_date=report_date.isoformat(),
        dataset=dataset.to_dict(),
        matrix=matrix_payload,
        paper_loader=loaded_paper.to_dict(),
        paper_daily=paper_daily.to_dict(),
        paper_vs_research=comparison.to_dict(),
        decision_trace=_decision_trace_artifact_payload(decision_trace),
        cost_parity=cost_parity.to_dict(),
        pnl_causality=pnl_causality.to_dict(),
    )
    return write_standard_audit_result(result, output_dir)


def write_standard_audit_result(result: StandardAuditResult, output_dir: Path) -> StandardAuditResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{result.run_id}.json"
    md_path = output_dir / f"{result.run_id}.md"
    json_path.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(render_standard_audit_result(result), encoding="utf-8")
    return replace(result, json_report_path=str(json_path), markdown_report_path=str(md_path))


def render_standard_audit_result(result: StandardAuditResult) -> str:
    matrix = result.matrix
    paper = result.paper_daily
    comparison = result.paper_vs_research
    cost_warnings = result.cost_parity.get("warnings") or []
    pnl_summary = result.pnl_causality.get("summary") or {}
    lines = [
        f"# AUTOBOT Standard Audit - {result.run_id}",
        "",
        f"Generated at: `{result.generated_at}`",
        f"Report date: `{result.report_date}`",
        "",
        "## Summary",
        "",
        "| Area | Key Result |",
        "| --- | --- |",
        f"| Dataset | {result.dataset.get('usable_sample_count', 0)} usable samples, {len(result.dataset.get('exports', []))} export(s) |",
        f"| Research matrix | {matrix.get('success_count', 0)} / {matrix.get('cell_count', 0)} cells ok |",
        f"| Paper daily | {paper.get('trade_count', 0)} trades, decision `{paper.get('decision')}` |",
        f"| Paper vs research | {comparison.get('divergent_bucket_count', 0)} divergent bucket(s) / {comparison.get('bucket_count', 0)} |",
        f"| Cost parity | {', '.join(cost_warnings) if cost_warnings else 'no global warnings'} |",
        f"| PnL causality | {pnl_summary.get('closed_trades', 0)} closed trades, PF `{pnl_summary.get('profit_factor')}` |",
        "",
        "## Artifacts",
        "",
        f"- Dataset report: `{result.dataset.get('markdown_report_path')}`",
        f"- Matrix report: `{matrix.get('markdown_report_path')}`",
        f"- Paper daily report: `{paper.get('markdown_report_path')}`",
        f"- Paper vs research report: `{comparison.get('markdown_report_path')}`",
        f"- Decision trace report: `{result.decision_trace.get('markdown_report_path')}`",
        f"- Cost parity report: `{result.cost_parity.get('markdown_report_path')}`",
        f"- PnL causality report: `{result.pnl_causality.get('markdown_report_path')}`",
        "",
        "## Safety",
        "",
    ]
    lines.extend(f"- {note}" for note in result.safety_notes)
    lines.append("")
    return "\n".join(lines)


def _attach_standard_matrix_reports(
    *,
    config: MatrixRunConfig,
    result: Any,
    output: dict[str, Any],
    output_dir: Path,
    registry_path: Path,
    mode: str,
) -> None:
    registry_payload = load_registry(registry_path) if registry_path.exists() else None
    recommendation_report = write_registry_recommendation_report(
        recommend_from_matrix(result, registry_payload=registry_payload),
        output_dir / "registry_recommendations",
    )
    loss_report = write_matrix_loss_attribution_report(result, output_dir / "loss_attribution")
    setup_report = write_matrix_setup_quality_report(result, output_dir / "setup_quality")
    strategy_regime_report = write_matrix_strategy_regime_report(result, output_dir / "strategy_regime")
    baseline_report = write_matrix_strategy_regime_baseline_report(
        config,
        result,
        output_dir / "strategy_regime_baselines",
    )
    walk_forward_report = write_matrix_strategy_regime_walk_forward_report(
        config,
        result,
        output_dir / "strategy_regime_walk_forward",
    )
    scorecard_report = write_strategy_scorecard_report(
        score_matrix(
            result,
            fees_included=True,
            slippage_included=True,
            baseline_included=True,
            out_of_sample_included=(mode == "walk_forward"),
        ),
        output_dir / "strategy_scorecard",
    )
    output["standard_reports_enabled"] = True
    output["registry_recommendation_report"] = recommendation_report.to_dict()
    output["loss_attribution_report"] = loss_report.to_dict()
    output["setup_quality_report"] = setup_report.to_dict()
    output["strategy_regime_report"] = strategy_regime_report.to_dict()
    output["strategy_regime_baseline_report"] = baseline_report.to_dict()
    output["strategy_regime_walk_forward_report"] = walk_forward_report.to_dict()
    output["strategy_scorecard_report"] = scorecard_report.to_dict()


def _latest_report_date(records: tuple[Any, ...]) -> date:
    dates = [record.closed_at.date() for record in records if getattr(record, "closed_at", None)]
    return max(dates) if dates else datetime.now(timezone.utc).date()


def _decision_trace_artifact_payload(report: Any) -> dict[str, Any]:
    return {
        "run_id": report.run_id,
        "generated_at": report.generated_at,
        "config": report.config.to_dict(),
        "data_sources": report.data_sources,
        "summary": report.summary.to_dict(),
        "stored_trace_sample_count": len(report.traces),
        "json_report_path": report.json_report_path,
        "markdown_report_path": report.markdown_report_path,
    }


def _write_pnl_causality_artifact(snapshot: dict[str, Any], output_dir: Path, run_id: str) -> PnlCausalityArtifact:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{run_id}.json"
    md_path = output_dir / f"{run_id}.md"
    json_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_render_pnl_causality_snapshot(run_id, snapshot), encoding="utf-8")
    return PnlCausalityArtifact(
        summary=dict(snapshot.get("summary") or {}),
        json_report_path=str(json_path),
        markdown_report_path=str(md_path),
    )


def _render_pnl_causality_snapshot(run_id: str, snapshot: dict[str, Any]) -> str:
    summary = snapshot.get("summary") or {}
    findings = summary.get("primary_findings") or []
    lines = [
        f"# PnL Causality Snapshot - {run_id}",
        "",
        f"Mode: `{snapshot.get('mode')}`",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Closed Trades | {summary.get('closed_trades', 0)} |",
        f"| Net PnL EUR | {summary.get('net_pnl_eur', 0.0)} |",
        f"| Profit Factor | {summary.get('profit_factor')} |",
        f"| Win Rate | {summary.get('win_rate')} |",
        f"| Fees EUR | {summary.get('fees_eur', 0.0)} |",
        f"| Avg Fee bps | {summary.get('avg_fee_bps')} |",
        f"| Avg Net Return bps | {summary.get('avg_net_return_bps')} |",
        "",
        "## Primary Findings",
        "",
    ]
    if findings:
        for item in findings:
            lines.append(
                f"- `{item.get('finding')}` severity `{item.get('severity')}` action `{item.get('recommended_action')}`"
            )
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "- Read-only PnL causality snapshot.",
            "- No paper or live order is created.",
            "- No live trading permission is granted.",
            "",
        ]
    )
    return "\n".join(lines)
