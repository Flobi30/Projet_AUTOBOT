"""Research-only statistical confidence checks for attributed paper evidence."""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Sequence

from autobot.v2.paper.ledger_quality import (
    critical_ledger_warning_reason,
    critical_warning_counts,
    has_critical_ledger_warning,
    loader_warning_counts,
)
from autobot.v2.paper.ledger_loader import load_state_db_paper_ledger
from autobot.v2.research.trade_journal import TradeRecord
from autobot.v2.strategy_runtime_policy import (
    EXECUTION_MODE_PAPER_CAPITAL,
    LEGACY_UNATTRIBUTED_STRATEGY_ID,
    shadow_paper_strategy_block_reason,
)


MIN_SAMPLE_SIZE = 50
RECOMMENDED_SAMPLE_SIZE = 100


@dataclass(frozen=True)
class PaperConfidenceConfig:
    state_db_path: Path
    strategy_id: str
    output_dir: Path = Path("reports/paper/confidence")
    run_id: str | None = None
    initial_capital_eur: float = 1_000.0
    bootstrap_iterations: int = 500
    seed: int = 7
    write_report: bool = True
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def resolved_run_id(self) -> str:
        if self.run_id:
            return self.run_id
        safe_strategy = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in self.strategy_id)
        return f"paper_confidence_{safe_strategy}_{self.generated_at.strftime('%Y%m%d_%H%M%S')}"


@dataclass(frozen=True)
class PaperConfidenceReport:
    run_id: str
    generated_at: str
    state_db_path: str
    strategy_id: str
    evidence_source: str
    trade_count: int
    paper_capital_trade_count: int
    shadow_trade_count: int
    quality_excluded_trade_count: int
    quality_exclusion_counts: dict[str, int]
    warning_counts: dict[str, int]
    net_pnl_eur: float
    gross_pnl_eur: float
    fees_eur: float
    slippage_eur: float
    net_profit_factor: float | None
    gross_profit_factor: float | None
    expectancy_eur: float | None
    winrate_net_pct: float | None
    bootstrap_net_pnl_ci_eur: dict[str, float] | None
    probability_positive_net_pnl: float | None
    confidence_level: str
    promotable: bool
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    safety_notes: tuple[str, ...]
    json_report_path: str | None = None
    markdown_report_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["blockers"] = list(self.blockers)
        data["warnings"] = list(self.warnings)
        data["safety_notes"] = list(self.safety_notes)
        return data


def build_paper_confidence_report(config: PaperConfidenceConfig) -> PaperConfidenceReport:
    if not config.strategy_id:
        raise ValueError("strategy_id is required")
    if config.initial_capital_eur <= 0.0:
        raise ValueError("initial_capital_eur must be positive")
    if config.bootstrap_iterations <= 0:
        raise ValueError("bootstrap_iterations must be positive")

    loaded = load_state_db_paper_ledger(config.state_db_path, include_decisions=True)
    raw_strategy_records = tuple(
        record
        for record in loaded.journal.records
        if record.strategy_id == config.strategy_id and record.strategy_id not in ("", LEGACY_UNATTRIBUTED_STRATEGY_ID)
    )
    quality_excluded_records = tuple(record for record in raw_strategy_records if has_critical_ledger_warning(record))
    all_records = tuple(record for record in raw_strategy_records if not has_critical_ledger_warning(record))
    paper_capital_records = tuple(record for record in all_records if _execution_mode(record) == EXECUTION_MODE_PAPER_CAPITAL)
    shadow_records = tuple(record for record in all_records if _execution_mode(record) != EXECUTION_MODE_PAPER_CAPITAL)
    evidence_records = paper_capital_records if paper_capital_records else shadow_records
    evidence_source = "paper_capital" if paper_capital_records else "shadow_paper_or_research"

    net_values = [record.net_pnl_eur for record in evidence_records]
    gross_values = [record.gross_pnl_eur for record in evidence_records]
    trade_count = len(evidence_records)
    net_pnl = sum(net_values)
    gross_pnl = sum(gross_values)
    net_pf = _profit_factor(net_values)
    gross_pf = _profit_factor(gross_values)
    expectancy = net_pnl / trade_count if trade_count else None
    bootstrap = _bootstrap_net_pnl(net_values, config.bootstrap_iterations, config.seed) if net_values else None
    blockers = _blockers(
        records=evidence_records,
        evidence_source=evidence_source,
        trade_count=trade_count,
        net_pnl=net_pnl,
        net_profit_factor=net_pf,
        expectancy=expectancy,
        bootstrap=bootstrap,
    )
    confidence_level = _confidence_level(blockers, trade_count, net_pnl, net_pf, expectancy, bootstrap)
    report = PaperConfidenceReport(
        run_id=config.resolved_run_id,
        generated_at=config.generated_at.isoformat(),
        state_db_path=str(config.state_db_path),
        strategy_id=config.strategy_id,
        evidence_source=evidence_source,
        trade_count=trade_count,
        paper_capital_trade_count=len(paper_capital_records),
        shadow_trade_count=len(shadow_records),
        quality_excluded_trade_count=len(quality_excluded_records),
        quality_exclusion_counts=critical_warning_counts(quality_excluded_records),
        warning_counts={
            **loader_warning_counts(loaded.warnings),
            **{f"critical_{key}": value for key, value in critical_warning_counts(raw_strategy_records).items()},
        },
        net_pnl_eur=net_pnl,
        gross_pnl_eur=gross_pnl,
        fees_eur=sum(record.fees_eur for record in evidence_records),
        slippage_eur=sum(record.slippage_eur for record in evidence_records),
        net_profit_factor=net_pf,
        gross_profit_factor=gross_pf,
        expectancy_eur=expectancy,
        winrate_net_pct=(sum(1 for value in net_values if value > 0.0) / trade_count * 100.0) if trade_count else None,
        bootstrap_net_pnl_ci_eur=bootstrap,
        probability_positive_net_pnl=bootstrap.get("probability_positive") if bootstrap else None,
        confidence_level=confidence_level,
        promotable=False,
        blockers=blockers,
        warnings=tuple(loaded.warnings),
        safety_notes=(
            "Research-only confidence report.",
            "No strategy is promoted by this command.",
            "Shadow evidence can inform research only and cannot allow paper/live promotion.",
            "Multiple-testing and walk-forward gates still apply outside this bootstrap summary.",
        ),
    )
    if not config.write_report:
        return report
    return write_paper_confidence_report(report, config.output_dir)


def write_paper_confidence_report(
    report: PaperConfidenceReport,
    output_dir: str | Path,
) -> PaperConfidenceReport:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    base = output / report.run_id
    json_path = base.with_suffix(".json")
    markdown_path = base.with_suffix(".md")
    report_with_paths = replace(report, json_report_path=str(json_path), markdown_report_path=str(markdown_path))
    json_path.write_text(json.dumps(report_with_paths.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(_markdown(report_with_paths), encoding="utf-8")
    return report_with_paths


def _execution_mode(record: TradeRecord) -> str:
    value = record.metadata.get("execution_mode")
    if value not in (None, ""):
        return str(value)
    for source_name in ("closing_leg", "opening_leg"):
        source = record.metadata.get(source_name)
        if isinstance(source, dict) and source.get("execution_mode") not in (None, ""):
            return str(source.get("execution_mode"))
    return ""


def _blockers(
    *,
    records: Sequence[TradeRecord],
    evidence_source: str,
    trade_count: int,
    net_pnl: float,
    net_profit_factor: float | None,
    expectancy: float | None,
    bootstrap: dict[str, float] | None,
) -> tuple[str, ...]:
    blockers: list[str] = []
    if evidence_source != "paper_capital":
        blockers.append("paper_capital_evidence_absent")
    if trade_count < MIN_SAMPLE_SIZE:
        blockers.append("insufficient_sample_size")
    elif trade_count < RECOMMENDED_SAMPLE_SIZE:
        blockers.append("below_recommended_sample_size")
    if net_pnl <= 0.0:
        blockers.append("non_positive_net_pnl")
    if net_profit_factor is None and net_pnl > 0.0:
        blockers.append("no_loss_sample_requires_review")
    elif net_profit_factor is None or net_profit_factor <= 1.0:
        blockers.append("net_profit_factor_not_above_1")
    if expectancy is None or expectancy <= 0.0:
        blockers.append("non_positive_expectancy")
    if bootstrap and bootstrap["p05"] <= 0.0:
        blockers.append("bootstrap_lower_ci_not_positive")
    if any(shadow_paper_strategy_block_reason(record.strategy_id) for record in records):
        blockers.append("strategy_policy_blocks_execution")
    if any(critical_ledger_warning_reason(record) for record in records):
        blockers.append("critical_ledger_warning")
    return tuple(dict.fromkeys(blockers))


def _confidence_level(
    blockers: Sequence[str],
    trade_count: int,
    net_pnl: float,
    net_profit_factor: float | None,
    expectancy: float | None,
    bootstrap: dict[str, float] | None,
) -> str:
    if trade_count < MIN_SAMPLE_SIZE:
        return "insufficient_data"
    hard_negative = net_pnl <= 0.0 or expectancy is None or expectancy <= 0.0
    if net_profit_factor is not None and net_profit_factor <= 1.0:
        hard_negative = True
    if hard_negative:
        return "rejected"
    if "paper_capital_evidence_absent" in blockers or trade_count < RECOMMENDED_SAMPLE_SIZE:
        return "early_signal"
    if bootstrap and bootstrap["p05"] <= 0.0:
        return "early_signal"
    return "usable"


def _bootstrap_net_pnl(values: Sequence[float], iterations: int, seed: int) -> dict[str, float]:
    rng = random.Random(seed)
    ordered_sums: list[float] = []
    count = len(values)
    for _ in range(iterations):
        sample_sum = sum(values[rng.randrange(count)] for _ in range(count))
        ordered_sums.append(sample_sum)
    ordered_sums.sort()
    return {
        "p05": _percentile(ordered_sums, 0.05),
        "p50": _percentile(ordered_sums, 0.50),
        "p95": _percentile(ordered_sums, 0.95),
        "mean": mean(ordered_sums),
        "probability_positive": sum(1 for value in ordered_sums if value > 0.0) / len(ordered_sums),
        "iterations": float(iterations),
    }


def _percentile(values: Sequence[float], q: float) -> float:
    if not values:
        return 0.0
    index = min(len(values) - 1, max(0, int(round((len(values) - 1) * q))))
    return float(values[index])


def _profit_factor(values: Sequence[float]) -> float | None:
    if not values:
        return None
    wins = sum(value for value in values if value > 0.0)
    losses = abs(sum(value for value in values if value < 0.0))
    if losses == 0.0:
        return None
    return wins / losses


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"


def _markdown(report: PaperConfidenceReport) -> str:
    lines = [
        f"# Paper Confidence - {report.strategy_id}",
        "",
        f"- Run: `{report.run_id}`",
        f"- Generated: `{report.generated_at}`",
        f"- Evidence source: `{report.evidence_source}`",
        f"- Confidence level: `{report.confidence_level}`",
        f"- Promotable: `{str(report.promotable).lower()}`",
        "",
        "## Metrics",
        "",
        f"- Trades: `{report.trade_count}`",
        f"- Paper capital trades: `{report.paper_capital_trade_count}`",
        f"- Shadow trades: `{report.shadow_trade_count}`",
        f"- Quality excluded trades: `{report.quality_excluded_trade_count}`",
        f"- Net PnL: `{report.net_pnl_eur:.2f}`",
        f"- Net PF: `{_fmt(report.net_profit_factor)}`",
        f"- Net expectancy: `{_fmt(report.expectancy_eur)}`",
        f"- Bootstrap positive probability: `{_fmt(report.probability_positive_net_pnl)}`",
        "",
        "## Blockers",
        "",
    ]
    lines.extend(f"- `{blocker}`" for blocker in report.blockers)
    lines.extend(["", "## Quality Exclusions", ""])
    if report.quality_exclusion_counts:
        lines.extend(f"- `{key}`: `{value}`" for key, value in report.quality_exclusion_counts.items())
    else:
        lines.append("- none")
    lines.extend(["", "## Safety", ""])
    lines.extend(f"- {note}" for note in report.safety_notes)
    return "\n".join(lines) + "\n"
