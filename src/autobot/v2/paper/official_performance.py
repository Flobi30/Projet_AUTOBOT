"""Official post-P0 paper performance summaries.

This module reads the immutable paper ``trade_ledger`` and builds strategy
metrics that are safe for governance. Legacy rows without ``strategy_id`` are
kept visible as audit counts, but never enter official strategy metrics.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from autobot.v2.paper.ledger_loader import load_state_db_paper_ledger
from autobot.v2.research.metrics_engine import MetricsEngine
from autobot.v2.research.trade_journal import TradeRecord
from autobot.v2.strategy_runtime_policy import (
    LEGACY_UNATTRIBUTED_STRATEGY_ID,
    official_paper_strategy_block_reason,
)
from autobot.v2.strategy_validation_registry import (
    StrategyAcceptanceCriteria,
    build_strategy_registry_records,
    entry_by_strategy_id,
    evaluate_paper_capital_gate,
    load_registry,
    registry_entries,
)


@dataclass(frozen=True)
class OfficialPaperPerformanceConfig:
    state_db_path: Path
    registry_path: Path = Path("docs/research/strategy_hypotheses.json")
    output_dir: Path = Path("reports/paper/official_performance")
    run_id: str | None = None
    initial_capital_eur: float = 1_000.0
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def resolved_run_id(self) -> str:
        if self.run_id:
            return self.run_id
        return f"official_paper_performance_{self.generated_at.strftime('%Y%m%d_%H%M%S')}"


@dataclass(frozen=True)
class PaperMetricBucket:
    key: dict[str, str]
    metrics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"key": dict(self.key), "metrics": dict(self.metrics)}


@dataclass(frozen=True)
class StrategyPaperSummary:
    strategy_id: str
    registry_status: str
    runtime_status: str
    paper_capital_enabled: bool
    promotable: bool
    decision: str
    reason: str
    metrics: dict[str, Any]
    best_pairs: tuple[PaperMetricBucket, ...] = ()
    worst_pairs: tuple[PaperMetricBucket, ...] = ()
    blockers: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "registry_status": self.registry_status,
            "runtime_status": self.runtime_status,
            "paper_capital_enabled": self.paper_capital_enabled,
            "promotable": self.promotable,
            "decision": self.decision,
            "reason": self.reason,
            "metrics": dict(self.metrics),
            "best_pairs": [item.to_dict() for item in self.best_pairs],
            "worst_pairs": [item.to_dict() for item in self.worst_pairs],
            "blockers": list(self.blockers),
        }


@dataclass(frozen=True)
class OfficialPaperPerformanceReport:
    run_id: str
    generated_at: str
    source: str
    state_db_path: str
    registry_path: str
    initial_capital_eur: float
    legacy: dict[str, Any]
    baseline: dict[str, Any]
    ranking: tuple[StrategyPaperSummary, ...]
    blocked_strategies: tuple[StrategyPaperSummary, ...]
    by_strategy: tuple[PaperMetricBucket, ...]
    by_strategy_symbol: tuple[PaperMetricBucket, ...]
    by_strategy_symbol_timeframe: tuple[PaperMetricBucket, ...]
    by_strategy_symbol_timeframe_regime: tuple[PaperMetricBucket, ...]
    warnings: tuple[str, ...] = ()
    json_report_path: str | None = None
    markdown_report_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "source": self.source,
            "state_db_path": self.state_db_path,
            "registry_path": self.registry_path,
            "initial_capital_eur": self.initial_capital_eur,
            "legacy": dict(self.legacy),
            "baseline": dict(self.baseline),
            "ranking": [item.to_dict() for item in self.ranking],
            "blocked_strategies": [item.to_dict() for item in self.blocked_strategies],
            "by_strategy": [item.to_dict() for item in self.by_strategy],
            "by_strategy_symbol": [item.to_dict() for item in self.by_strategy_symbol],
            "by_strategy_symbol_timeframe": [item.to_dict() for item in self.by_strategy_symbol_timeframe],
            "by_strategy_symbol_timeframe_regime": [
                item.to_dict() for item in self.by_strategy_symbol_timeframe_regime
            ],
            "warnings": list(self.warnings),
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
            "safety_notes": [
                "Official post-P0 paper performance report only.",
                "Legacy unattributed trades are excluded from strategy metrics.",
                "No orders are created by this report.",
                "No live trading permission is granted.",
            ],
        }


def build_official_paper_performance_report(
    config: OfficialPaperPerformanceConfig,
    *,
    write_report: bool = True,
) -> OfficialPaperPerformanceReport:
    if config.initial_capital_eur <= 0.0:
        raise ValueError("initial_capital_eur must be positive")

    loaded = load_state_db_paper_ledger(config.state_db_path, include_decisions=False)
    all_records = tuple(loaded.journal.records)
    official_records = tuple(record for record in all_records if _is_official_attributed(record))
    legacy_unattributed_records = tuple(record for record in all_records if _is_legacy_unattributed(record))
    excluded_non_official_records = tuple(record for record in all_records if not _is_official_attributed(record))

    registry_warnings: list[str] = []
    try:
        registry_payload = load_registry(config.registry_path)
    except Exception as exc:
        registry_payload = {"hypotheses": []}
        registry_warnings.append(f"registry_unavailable:{type(exc).__name__}")
    registry_evidence = _evidence_by_strategy(official_records, config.initial_capital_eur)
    registry_records = build_strategy_registry_records(
        registry_payload,
        evidence_by_strategy_id=registry_evidence,
        criteria=StrategyAcceptanceCriteria(),
    )
    registry_by_id = {record.strategy_id: record for record in registry_records}
    entry_by_id = {
        str(entry.get("strategy_id") or entry.get("id") or ""): entry for entry in registry_entries(registry_payload)
    }
    strategy_ids = sorted({record.strategy_id for record in registry_records} | {trade.strategy_id for trade in official_records})

    strategy_summaries: list[StrategyPaperSummary] = []
    pair_buckets = _group_metrics(
        official_records,
        config.initial_capital_eur,
        ("strategy_id", "symbol"),
    )
    pairs_by_strategy: dict[str, list[PaperMetricBucket]] = defaultdict(list)
    for bucket in pair_buckets:
        pairs_by_strategy[bucket.key["strategy_id"]].append(bucket)

    for strategy_id in strategy_ids:
        records = tuple(trade for trade in official_records if trade.strategy_id == strategy_id)
        metrics = _metrics_dict(records, config.initial_capital_eur)
        entry = entry_by_strategy_id(registry_payload, strategy_id)
        registry_record = registry_by_id.get(strategy_id)
        summary = _strategy_summary(
            strategy_id,
            entry,
            registry_record,
            metrics,
            pairs_by_strategy.get(strategy_id, []),
        )
        strategy_summaries.append(summary)

    ranking = tuple(sorted(strategy_summaries, key=_ranking_key))
    blocked = tuple(item for item in ranking if item.decision in {"blocked", "disabled", "insufficient_data"})

    generated = config.generated_at.isoformat()
    report = OfficialPaperPerformanceReport(
        run_id=config.resolved_run_id,
        generated_at=generated,
        source="official_post_p0_trade_ledger",
        state_db_path=str(config.state_db_path),
        registry_path=str(config.registry_path),
        initial_capital_eur=float(config.initial_capital_eur),
        legacy={
            "legacy_unattributed_trade_count": len(legacy_unattributed_records),
            "non_official_excluded_trade_count": len(excluded_non_official_records),
            "official_attributed_trade_count": len(official_records),
            "legacy_strategy_id": LEGACY_UNATTRIBUTED_STRATEGY_ID,
            "excluded_from_official_metrics": True,
        },
        baseline={
            "strategy_id": "no_trade_baseline",
            "status": "reference_only",
            "net_pnl_eur": 0.0,
            "profit_factor": None,
            "expectancy_eur": None,
            "promotable": False,
            "reason": "baseline_reference_not_alpha_strategy",
        },
        ranking=ranking,
        blocked_strategies=blocked,
        by_strategy=_group_metrics(official_records, config.initial_capital_eur, ("strategy_id",)),
        by_strategy_symbol=pair_buckets,
        by_strategy_symbol_timeframe=_group_metrics(
            official_records,
            config.initial_capital_eur,
            ("strategy_id", "symbol", "timeframe"),
        ),
        by_strategy_symbol_timeframe_regime=_group_metrics(
            official_records,
            config.initial_capital_eur,
            ("strategy_id", "symbol", "timeframe", "regime"),
        ),
        warnings=tuple([*loaded.warnings, *registry_warnings]),
    )
    if write_report:
        return write_official_paper_performance_report(report, config.output_dir)
    return report


def write_official_paper_performance_report(
    report: OfficialPaperPerformanceReport,
    output_dir: str | Path,
) -> OfficialPaperPerformanceReport:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    base = output / report.run_id
    json_path = base.with_suffix(".json")
    md_path = base.with_suffix(".md")
    json_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_markdown(report), encoding="utf-8")
    return replace(report, json_report_path=str(json_path), markdown_report_path=str(md_path))


def _is_official_attributed(record: TradeRecord) -> bool:
    strategy_id = str(record.strategy_id or "").strip()
    if not strategy_id or strategy_id == LEGACY_UNATTRIBUTED_STRATEGY_ID:
        return False
    return official_paper_strategy_block_reason(strategy_id) is None


def _is_legacy_unattributed(record: TradeRecord) -> bool:
    strategy_id = str(record.strategy_id or "").strip()
    return not strategy_id or strategy_id == LEGACY_UNATTRIBUTED_STRATEGY_ID


def _metric_key(record: TradeRecord, fields: Sequence[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for field in fields:
        if field == "strategy_id":
            value = record.strategy_id
        elif field == "symbol":
            value = record.symbol
        elif field == "timeframe":
            value = _trade_metadata_value(record, "timeframe") or "unknown"
        elif field == "regime":
            value = record.regime or _trade_metadata_value(record, "regime") or "unknown"
        else:
            value = "unknown"
        result[field] = str(value or "unknown")
    return result


def _trade_metadata_value(record: TradeRecord, key: str) -> str | None:
    for source_name in ("closing_leg", "opening_leg", "position", "closing_decision", "opening_decision"):
        source = record.metadata.get(source_name)
        if isinstance(source, Mapping):
            value = source.get(key)
            if value not in (None, ""):
                return str(value)
    return None


def _group_metrics(
    records: Sequence[TradeRecord],
    initial_capital_eur: float,
    fields: Sequence[str],
) -> tuple[PaperMetricBucket, ...]:
    groups: dict[tuple[tuple[str, str], ...], list[TradeRecord]] = defaultdict(list)
    for record in records:
        key = _metric_key(record, fields)
        groups[tuple(sorted(key.items()))].append(record)
    buckets = [
        PaperMetricBucket(dict(key), _metrics_dict(tuple(group_records), initial_capital_eur))
        for key, group_records in groups.items()
    ]
    return tuple(
        sorted(
            buckets,
            key=lambda item: (
                _safe_float(item.metrics.get("net_pnl_eur")),
                tuple(item.key.get(field, "") for field in fields),
            ),
            reverse=True,
        )
    )


def _metrics_dict(records: Sequence[TradeRecord], initial_capital_eur: float) -> dict[str, Any]:
    metrics = MetricsEngine().calculate(
        tuple(records),
        initial_capital_eur=initial_capital_eur,
        baseline_name="no_trade_baseline",
        baseline_return_pct=0.0,
    )
    data = metrics.to_dict()
    data["fees_included"] = _fees_evidence(records)
    data["slippage_included"] = _slippage_evidence(records)
    data["sample_size"] = data["closed_trade_count"]
    data["net_pnl_eur"] = data["total_net_pnl_eur"]
    data["gross_pnl_eur"] = data["total_gross_pnl_eur"]
    data["fees_eur"] = data["total_fees_eur"]
    data["slippage_eur"] = data["total_slippage_eur"]
    data["expectancy"] = data["expectancy_eur"]
    return data


def _fees_evidence(records: Sequence[TradeRecord]) -> bool:
    if not records:
        return False
    for record in records:
        closing = record.metadata.get("closing_leg")
        if not isinstance(closing, Mapping) or closing.get("fees") is None:
            return False
    return True


def _slippage_evidence(records: Sequence[TradeRecord]) -> bool:
    if not records:
        return False
    for record in records:
        closing = record.metadata.get("closing_leg")
        if not isinstance(closing, Mapping) or closing.get("slippage_bps") is None:
            return False
    return True


def _evidence_by_strategy(
    records: Sequence[TradeRecord],
    initial_capital_eur: float,
) -> dict[str, Mapping[str, Any]]:
    evidence: dict[str, Mapping[str, Any]] = {}
    for strategy_id in sorted({record.strategy_id for record in records}):
        evidence[strategy_id] = _metrics_dict(
            tuple(record for record in records if record.strategy_id == strategy_id),
            initial_capital_eur,
        )
    return evidence


def _strategy_summary(
    strategy_id: str,
    entry: Mapping[str, Any] | None,
    registry_record: Any,
    metrics: Mapping[str, Any],
    pair_buckets: Sequence[PaperMetricBucket],
) -> StrategyPaperSummary:
    if entry is None:
        blockers = ("strategy_not_in_registry",)
        return StrategyPaperSummary(
            strategy_id=strategy_id,
            registry_status="missing",
            runtime_status="disabled",
            paper_capital_enabled=False,
            promotable=False,
            decision="blocked",
            reason="strategy_not_in_registry",
            metrics=dict(metrics),
            best_pairs=_top_pairs(pair_buckets, reverse=True),
            worst_pairs=_top_pairs(pair_buckets, reverse=False),
            blockers=blockers,
        )

    decision = evaluate_paper_capital_gate(entry, metrics=metrics)
    runtime_status = registry_record.status if registry_record else "unknown"
    paper_capital_enabled = bool(registry_record and registry_record.paper_capital_enabled)
    registry_status = str(entry.get("validation_status") or "learning")
    if strategy_id == "no_trade_baseline":
        current_decision = "reference"
        reason = "baseline_reference_not_alpha_strategy"
    elif registry_status in {"rejected", "retired_from_execution"}:
        current_decision = "disabled"
        reason = registry_record.reason_if_disabled if registry_record else registry_status
    elif not metrics.get("closed_trade_count"):
        current_decision = "insufficient_data"
        reason = "no_official_post_p0_trades"
    elif decision.allowed:
        current_decision = "candidate"
        reason = "paper_gate_passed_requires_human_review"
    else:
        current_decision = "blocked"
        reason = ";".join(decision.reasons) or "paper_gate_blocked"

    blockers = tuple(decision.reasons)
    return StrategyPaperSummary(
        strategy_id=strategy_id,
        registry_status=registry_status,
        runtime_status=runtime_status,
        paper_capital_enabled=paper_capital_enabled,
        promotable=False,
        decision=current_decision,
        reason=reason or "insufficient_data",
        metrics=dict(metrics),
        best_pairs=_top_pairs(pair_buckets, reverse=True),
        worst_pairs=_top_pairs(pair_buckets, reverse=False),
        blockers=blockers,
    )


def _top_pairs(pair_buckets: Sequence[PaperMetricBucket], *, reverse: bool) -> tuple[PaperMetricBucket, ...]:
    return tuple(
        sorted(
            pair_buckets,
            key=lambda item: (
                _safe_float(item.metrics.get("net_pnl_eur")),
                _safe_float(item.metrics.get("profit_factor"), -1.0),
            ),
            reverse=reverse,
        )[:5]
    )


def _ranking_key(summary: StrategyPaperSummary) -> tuple[int, float, float, int]:
    decision_rank = {
        "candidate": 0,
        "blocked": 1,
        "insufficient_data": 2,
        "reference": 3,
        "disabled": 4,
    }.get(summary.decision, 5)
    metrics = summary.metrics
    return (
        decision_rank,
        -_safe_float(metrics.get("net_pnl_eur")),
        -_safe_float(metrics.get("profit_factor"), -1.0),
        -int(_safe_float(metrics.get("closed_trade_count"))),
    )


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _markdown(report: OfficialPaperPerformanceReport) -> str:
    lines = [
        f"# Official Paper Performance - {report.run_id}",
        "",
        f"- Generated: `{report.generated_at}`",
        f"- Source: `{report.source}`",
        f"- State DB: `{report.state_db_path}`",
        f"- Registry: `{report.registry_path}`",
        f"- Initial capital: `{report.initial_capital_eur:.2f} EUR`",
        f"- Official attributed trades: `{report.legacy['official_attributed_trade_count']}`",
        f"- Legacy unattributed trades excluded: `{report.legacy['legacy_unattributed_trade_count']}`",
        "",
        "## Strategy Ranking",
        "",
        "| Strategy | Registry | Runtime | Trades | Net PnL | PF net | Expectancy | Max DD % | Decision | Reason |",
        "|---|---|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for item in report.ranking:
        metrics = item.metrics
        lines.append(
            "| {strategy} | {registry} | {runtime} | {trades} | {net:.2f} | {pf} | {exp} | {dd:.2f} | {decision} | {reason} |".format(
                strategy=item.strategy_id,
                registry=item.registry_status,
                runtime=item.runtime_status,
                trades=int(_safe_float(metrics.get("closed_trade_count"))),
                net=_safe_float(metrics.get("net_pnl_eur")),
                pf=_fmt_optional(metrics.get("profit_factor")),
                exp=_fmt_optional(metrics.get("expectancy_eur")),
                dd=_safe_float(metrics.get("max_drawdown_pct")),
                decision=item.decision,
                reason=item.reason,
            )
        )
    lines.extend(
        [
            "",
            "## Baseline",
            "",
            "`no_trade_baseline` is a reference only, not an alpha strategy and not promotable.",
            "",
            "## Safety",
            "",
            "- No orders are created by this report.",
            "- Legacy unattributed trades are excluded from official strategy metrics.",
            "- `promotable` remains false; any promotion still requires human review.",
        ]
    )
    return "\n".join(lines) + "\n"


def _fmt_optional(value: Any) -> str:
    parsed = _safe_float(value, default=float("nan"))
    if parsed != parsed:
        return "n/a"
    return f"{parsed:.4f}"
