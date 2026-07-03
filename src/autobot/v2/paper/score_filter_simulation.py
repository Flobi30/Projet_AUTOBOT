"""Read-only opportunity score filter simulations for shadow/paper evidence."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Mapping, Sequence

from autobot.v2.paper.ledger_quality import (
    critical_ledger_warning_reason,
    critical_warning_counts,
    has_critical_ledger_warning,
    loader_warning_counts,
)
from autobot.v2.paper.ledger_loader import load_state_db_paper_ledger
from autobot.v2.research.trade_journal import TradeRecord
from autobot.v2.strategy_runtime_policy import (
    LEGACY_UNATTRIBUTED_STRATEGY_ID,
    shadow_paper_strategy_block_reason,
)


SCORE_BUCKETS = ("high", "medium", "low", "missing")


@dataclass(frozen=True)
class ScoreFilterSimulationConfig:
    state_db_path: Path
    output_dir: Path = Path("reports/paper/score_filter_simulation")
    run_id: str | None = None
    initial_capital_eur: float = 1_000.0
    write_report: bool = True
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def resolved_run_id(self) -> str:
        if self.run_id:
            return self.run_id
        return f"score_filter_simulation_{self.generated_at.strftime('%Y%m%d_%H%M%S')}"


@dataclass(frozen=True)
class ScoreFilterScenario:
    name: str
    included_buckets: tuple[str, ...]
    trade_count: int
    gross_pnl_eur: float
    net_pnl_eur: float
    fees_eur: float
    slippage_eur: float
    gross_profit_factor: float | None
    net_profit_factor: float | None
    net_expectancy_eur: float | None
    winrate_net_pct: float | None
    max_drawdown_eur: float
    max_drawdown_pct: float
    confidence_level: str
    promotable: bool

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["included_buckets"] = list(self.included_buckets)
        return data


@dataclass(frozen=True)
class ScoreFilterSimulationReport:
    run_id: str
    generated_at: str
    state_db_path: str
    source: str
    total_trade_count: int
    eligible_trade_count: int
    legacy_excluded_trade_count: int
    policy_excluded_trade_count: int
    quality_excluded_trade_count: int
    exclusion_counts: dict[str, int]
    bucket_counts: dict[str, int]
    coverage_by_strategy: dict[str, dict[str, Any]]
    coverage_by_symbol: dict[str, dict[str, Any]]
    warning_counts: dict[str, int]
    scenarios: tuple[ScoreFilterScenario, ...]
    safety_notes: tuple[str, ...]
    warnings: tuple[str, ...] = ()
    json_report_path: str | None = None
    markdown_report_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "state_db_path": self.state_db_path,
            "source": self.source,
            "total_trade_count": self.total_trade_count,
            "eligible_trade_count": self.eligible_trade_count,
            "legacy_excluded_trade_count": self.legacy_excluded_trade_count,
            "policy_excluded_trade_count": self.policy_excluded_trade_count,
            "quality_excluded_trade_count": self.quality_excluded_trade_count,
            "exclusion_counts": dict(self.exclusion_counts),
            "bucket_counts": dict(self.bucket_counts),
            "coverage_by_strategy": self.coverage_by_strategy,
            "coverage_by_symbol": self.coverage_by_symbol,
            "warning_counts": dict(self.warning_counts),
            "scenarios": [item.to_dict() for item in self.scenarios],
            "safety_notes": list(self.safety_notes),
            "warnings": list(self.warnings),
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
        }


def build_score_filter_simulation_report(config: ScoreFilterSimulationConfig) -> ScoreFilterSimulationReport:
    if config.initial_capital_eur <= 0.0:
        raise ValueError("initial_capital_eur must be positive")
    loaded = load_state_db_paper_ledger(config.state_db_path, include_decisions=True)
    all_records = tuple(loaded.journal.records)
    policy_candidates = tuple(record for record in all_records if _is_policy_candidate(record))
    quality_excluded = tuple(record for record in policy_candidates if has_critical_ledger_warning(record))
    eligible = tuple(record for record in policy_candidates if not has_critical_ledger_warning(record))
    legacy = tuple(record for record in all_records if _is_legacy(record))
    policy_excluded = tuple(
        record for record in all_records if not _is_legacy(record) and not _is_policy_candidate(record)
    )
    by_bucket = _records_by_bucket(eligible)
    scenarios = tuple(
        _scenario(name, buckets, by_bucket, config.initial_capital_eur)
        for name, buckets in (
            ("all_scored", ("high", "medium", "low")),
            ("high_only", ("high",)),
            ("high_plus_medium", ("high", "medium")),
            ("exclude_low", ("high", "medium", "missing")),
            ("exclude_missing", ("high", "medium", "low")),
            ("missing_separate", ("missing",)),
            ("low_separate", ("low",)),
        )
    )
    report = ScoreFilterSimulationReport(
        run_id=config.resolved_run_id,
        generated_at=config.generated_at.isoformat(),
        state_db_path=str(config.state_db_path),
        source="post_p6_read_only_score_filter_simulation",
        total_trade_count=len(all_records),
        eligible_trade_count=len(eligible),
        legacy_excluded_trade_count=len(legacy),
        policy_excluded_trade_count=len(policy_excluded),
        quality_excluded_trade_count=len(quality_excluded),
        exclusion_counts=_exclusion_counts(legacy, policy_excluded, quality_excluded),
        bucket_counts={bucket: len(by_bucket[bucket]) for bucket in SCORE_BUCKETS},
        coverage_by_strategy=_coverage(policy_candidates, "strategy_id"),
        coverage_by_symbol=_coverage(policy_candidates, "symbol"),
        warning_counts={
            **loader_warning_counts(loaded.warnings),
            **{f"critical_{key}": value for key, value in critical_warning_counts(policy_candidates).items()},
        },
        scenarios=scenarios,
        safety_notes=(
            "Read-only simulation over existing attributed observations.",
            "No trade, order, paper capital, live flag, or strategy promotion is created.",
            "Simulation scenarios are not promotion gates and always return promotable=false.",
            "Grid/legacy/unattributed rows are excluded from executable conclusions.",
            "Rows with critical ledger quality warnings are counted but excluded from scenarios.",
        ),
        warnings=tuple(loaded.warnings),
    )
    if not config.write_report:
        return report
    return write_score_filter_simulation_report(report, config.output_dir)


def write_score_filter_simulation_report(
    report: ScoreFilterSimulationReport,
    output_dir: str | Path,
) -> ScoreFilterSimulationReport:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    base = output / report.run_id
    json_path = base.with_suffix(".json")
    markdown_path = base.with_suffix(".md")
    report_with_paths = replace(report, json_report_path=str(json_path), markdown_report_path=str(markdown_path))
    json_path.write_text(json.dumps(report_with_paths.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(_markdown(report_with_paths), encoding="utf-8")
    return report_with_paths


def _scenario(
    name: str,
    buckets: Sequence[str],
    by_bucket: Mapping[str, Sequence[TradeRecord]],
    initial_capital_eur: float,
) -> ScoreFilterScenario:
    records = tuple(record for bucket in buckets for record in by_bucket.get(bucket, ()))
    gross_values = [record.gross_pnl_eur for record in records]
    net_values = [record.net_pnl_eur for record in records]
    net_pnl = sum(net_values)
    count = len(records)
    pf_net = _profit_factor(net_values)
    expectancy = net_pnl / count if count else None
    max_dd_eur, max_dd_pct = _max_drawdown(records, initial_capital_eur)
    return ScoreFilterScenario(
        name=name,
        included_buckets=tuple(buckets),
        trade_count=count,
        gross_pnl_eur=sum(gross_values),
        net_pnl_eur=net_pnl,
        fees_eur=sum(record.fees_eur for record in records),
        slippage_eur=sum(record.slippage_eur for record in records),
        gross_profit_factor=_profit_factor(gross_values),
        net_profit_factor=pf_net,
        net_expectancy_eur=expectancy,
        winrate_net_pct=(sum(1 for value in net_values if value > 0.0) / count * 100.0) if count else None,
        max_drawdown_eur=max_dd_eur,
        max_drawdown_pct=max_dd_pct,
        confidence_level=_confidence_level(count, pf_net, expectancy, net_pnl),
        promotable=False,
    )


def _is_eligible(record: TradeRecord) -> bool:
    return _is_policy_candidate(record) and not has_critical_ledger_warning(record)


def _is_policy_candidate(record: TradeRecord) -> bool:
    if _is_legacy(record):
        return False
    return shadow_paper_strategy_block_reason(record.strategy_id) is None


def _is_legacy(record: TradeRecord) -> bool:
    return record.strategy_id in ("", LEGACY_UNATTRIBUTED_STRATEGY_ID)


def _records_by_bucket(records: Sequence[TradeRecord]) -> dict[str, tuple[TradeRecord, ...]]:
    grouped: dict[str, list[TradeRecord]] = {bucket: [] for bucket in SCORE_BUCKETS}
    for record in records:
        grouped[_score_bucket(record)].append(record)
    return {bucket: tuple(items) for bucket, items in grouped.items()}


def _exclusion_counts(
    legacy: Sequence[TradeRecord],
    policy_excluded: Sequence[TradeRecord],
    quality_excluded: Sequence[TradeRecord],
) -> dict[str, int]:
    counts: dict[str, int] = {
        "legacy_unattributed": len(legacy),
        "policy_blocked": len(policy_excluded),
        "quality_warning": len(quality_excluded),
    }
    for record in quality_excluded:
        reason = critical_ledger_warning_reason(record) or "unknown_quality_warning"
        counts[reason] = counts.get(reason, 0) + 1
    return dict(sorted(counts.items()))


def _coverage(records: Sequence[TradeRecord], field: str) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[TradeRecord]] = {}
    for record in records:
        key = record.strategy_id if field == "strategy_id" else record.symbol
        grouped.setdefault(str(key or "unknown"), []).append(record)
    return {key: _coverage_bucket(tuple(items)) for key, items in sorted(grouped.items())}


def _coverage_bucket(records: Sequence[TradeRecord]) -> dict[str, Any]:
    bucket_counts = {bucket: 0 for bucket in SCORE_BUCKETS}
    warning_counts = critical_warning_counts(records)
    for record in records:
        bucket_counts[_score_bucket(record)] += 1
    total = len(records)
    scored = total - bucket_counts["missing"]
    return {
        "total": total,
        "scored": scored,
        "score_coverage_pct": (scored / total * 100.0) if total else 0.0,
        "buckets": bucket_counts,
        "critical_warning_count": sum(warning_counts.values()),
        "critical_warning_counts": warning_counts,
    }


def _score_bucket(record: TradeRecord) -> str:
    explicit = record.metadata.get("score_bucket")
    if explicit in SCORE_BUCKETS:
        return str(explicit)
    score = _score(record)
    if score is None:
        return "missing"
    if score >= 70.0:
        return "high"
    if score >= 40.0:
        return "medium"
    return "low"


def _score(record: TradeRecord) -> float | None:
    return _score_from_mapping(record.metadata)


def _score_from_mapping(source: Any) -> float | None:
    if not isinstance(source, Mapping):
        return None
    for key in ("opportunity_score", "score", "final_score", "base_score"):
        try:
            if source.get(key) is not None:
                return float(source[key])
        except (TypeError, ValueError):
            continue
    for value in source.values():
        parsed = _score_from_mapping(value)
        if parsed is not None:
            return parsed
    return None


def _confidence_level(
    trade_count: int,
    net_profit_factor: float | None,
    expectancy: float | None,
    net_pnl: float,
) -> str:
    if trade_count < 50:
        return "insufficient_data"
    if net_pnl <= 0.0 or expectancy is None or expectancy <= 0.0 or net_profit_factor is None or net_profit_factor <= 1.0:
        return "rejected"
    if trade_count < 100:
        return "early_signal"
    return "usable"


def _profit_factor(values: Sequence[float]) -> float | None:
    if not values:
        return None
    wins = sum(value for value in values if value > 0.0)
    losses = abs(sum(value for value in values if value < 0.0))
    if losses == 0.0:
        return None
    return wins / losses


def _max_drawdown(records: Sequence[TradeRecord], initial_capital_eur: float) -> tuple[float, float]:
    equity = float(initial_capital_eur)
    peak = float(initial_capital_eur)
    max_drawdown = 0.0
    max_drawdown_pct = 0.0
    for record in sorted(records, key=lambda item: item.closed_at):
        equity += record.net_pnl_eur
        peak = max(peak, equity)
        drawdown = max(0.0, peak - equity)
        max_drawdown = max(max_drawdown, drawdown)
        if peak > 0.0:
            max_drawdown_pct = max(max_drawdown_pct, drawdown / peak * 100.0)
    return max_drawdown, max_drawdown_pct


def _fmt(value: float | None) -> str:
    if value is None or not math.isfinite(value):
        return "n/a"
    return f"{value:.4f}"


def _markdown(report: ScoreFilterSimulationReport) -> str:
    lines = [
        f"# Score Filter Simulation - {report.run_id}",
        "",
        f"- Generated: `{report.generated_at}`",
        f"- Eligible trades: `{report.eligible_trade_count}`",
        f"- Legacy excluded trades: `{report.legacy_excluded_trade_count}`",
        f"- Policy excluded trades: `{report.policy_excluded_trade_count}`",
        f"- Quality excluded trades: `{report.quality_excluded_trade_count}`",
        "",
        "## Bucket Counts",
        "",
    ]
    for bucket in SCORE_BUCKETS:
        lines.append(f"- `{bucket}`: `{report.bucket_counts.get(bucket, 0)}`")
    lines.extend(
        [
            "",
            "## Score Coverage By Strategy",
            "",
            "| Strategy | Total | Scored | Coverage | High | Medium | Low | Missing | Critical warnings |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for strategy, coverage in report.coverage_by_strategy.items():
        buckets = coverage.get("buckets", {})
        lines.append(
            "| {strategy} | {total} | {scored} | {coverage:.2f}% | {high} | {medium} | {low} | {missing} | {warnings} |".format(
                strategy=strategy,
                total=coverage.get("total", 0),
                scored=coverage.get("scored", 0),
                coverage=float(coverage.get("score_coverage_pct") or 0.0),
                high=buckets.get("high", 0),
                medium=buckets.get("medium", 0),
                low=buckets.get("low", 0),
                missing=buckets.get("missing", 0),
                warnings=coverage.get("critical_warning_count", 0),
            )
        )
    lines.extend(
        [
            "",
            "## Ledger Warnings",
            "",
        ]
    )
    if report.warning_counts:
        lines.extend(f"- `{key}`: `{value}`" for key, value in sorted(report.warning_counts.items()))
    else:
        lines.append("- none")
    lines.extend(["", "## Exclusions", ""])
    lines.extend(f"- `{key}`: `{value}`" for key, value in sorted(report.exclusion_counts.items()))
    lines.extend(
        [
            "",
            "## Scenarios",
            "",
            "| Scenario | Buckets | Trades | Net PnL | PF gross | PF net | Expectancy | Max DD | Confidence | Promotable |",
            "|---|---|---:|---:|---:|---:|---:|---:|---|---|",
        ]
    )
    for scenario in report.scenarios:
        lines.append(
            "| {name} | {buckets} | {trades} | {net:.2f} | {gpf} | {npf} | {exp} | {dd:.2f} | {conf} | {promo} |".format(
                name=scenario.name,
                buckets=",".join(scenario.included_buckets),
                trades=scenario.trade_count,
                net=scenario.net_pnl_eur,
                gpf=_fmt(scenario.gross_profit_factor),
                npf=_fmt(scenario.net_profit_factor),
                exp=_fmt(scenario.net_expectancy_eur),
                dd=scenario.max_drawdown_eur,
                conf=scenario.confidence_level,
                promo=str(scenario.promotable).lower(),
            )
        )
    lines.extend(["", "## Safety", ""])
    lines.extend(f"- {note}" for note in report.safety_notes)
    return "\n".join(lines) + "\n"
