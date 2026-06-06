"""Research-vs-official-paper parity runner.

This is a read-only wrapper around the existing validation matrix and paper
ledger comparison tools. It does not mutate runtime state and cannot submit
orders.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from autobot.v2.paper.ledger_loader import load_state_db_paper_ledger

from .execution_cost_model import ExecutionCostConfig
from .paper_research_comparison import (
    PaperResearchComparisonReport,
    compare_paper_to_research,
    write_paper_research_comparison_report,
)
from .validation_matrix import MatrixRunConfig, run_validation_matrix


@dataclass(frozen=True)
class ResearchPaperParityConfig:
    run_id: str
    state_db_path: Path
    symbols: tuple[str, ...]
    strategies: tuple[str, ...] = ("grid", "trend", "mean_reversion")
    output_dir: Path = Path("reports/research/research_paper_parity")
    mode: str = "backtest"
    initial_capital_eur: float = 1_000.0
    order_notional_eur: float = 100.0
    min_closed_trades: int = 30
    min_profit_factor: float = 1.2
    max_drawdown_pct: float = 15.0
    start_at: str | None = None
    end_at: str | None = None
    limit: int | None = None
    include_regime_context: bool = False
    cost_config: ExecutionCostConfig = field(default_factory=ExecutionCostConfig)

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id must not be empty")
        if not self.symbols:
            raise ValueError("symbols must not be empty")
        if not self.strategies:
            raise ValueError("strategies must not be empty")
        if self.mode not in {"backtest", "walk_forward"}:
            raise ValueError("mode must be backtest or walk_forward")
        self.cost_config.validate()


def run_research_paper_parity(config: ResearchPaperParityConfig) -> PaperResearchComparisonReport:
    """Replay research on a state DB and compare with official paper ledger."""

    matrix = run_validation_matrix(
        MatrixRunConfig(
            run_id=f"{config.run_id}_matrix",
            data_source="autobot_state_db",
            data_path=config.state_db_path,
            symbols=config.symbols,
            strategies=config.strategies,  # type: ignore[arg-type]
            mode=config.mode,  # type: ignore[arg-type]
            output_dir=config.output_dir / "matrix",
            initial_capital_eur=config.initial_capital_eur,
            order_notional_eur=config.order_notional_eur,
            min_closed_trades=config.min_closed_trades,
            min_profit_factor=config.min_profit_factor,
            max_drawdown_pct=config.max_drawdown_pct,
            cost_config=config.cost_config,
            start_at=config.start_at,
            end_at=config.end_at,
            limit=config.limit,
            include_regime_context=config.include_regime_context,
        )
    )
    paper = load_state_db_paper_ledger(config.state_db_path)
    return write_paper_research_comparison_report(
        compare_paper_to_research(
            paper.journal,
            matrix,
            run_id=config.run_id,
            paper_source_type=paper.source_type,
            paper_source_path=paper.source_path,
            initial_capital_eur=config.initial_capital_eur,
            warnings=paper.warnings,
        ),
        config.output_dir,
    )


def summarize_research_paper_parity(report: PaperResearchComparisonReport) -> dict[str, Any]:
    """Small machine-readable summary for non-regression reports."""

    return {
        "run_id": report.run_id,
        "bucket_count": report.bucket_count,
        "divergent_bucket_count": report.divergent_bucket_count,
        "paper_trade_count": report.paper_trade_count,
        "research_trade_count": report.research_trade_count,
        "paper_net_pnl_eur": report.paper_net_pnl_eur,
        "research_net_pnl_eur": report.research_net_pnl_eur,
        "alignment_counts": dict(report.alignment_counts),
        "diagnostic_counts": dict(report.diagnostic_counts),
        "recommendation_counts": dict(report.recommendation_counts),
        "warnings": list(report.warnings),
        "safety_notes": list(report.safety_notes),
    }
