"""Research-only upstream expected-move diagnostics for shadow observations.

The report explains why shadow observations feed ``opportunity_score_v2`` with
zero or negative pre-trade edge. It is read-only: realized PnL is used only as
after-the-fact evaluation and never to create or promote a signal.
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Mapping, Sequence

from autobot.v2.paper.ledger_loader import load_state_db_paper_ledger
from autobot.v2.research.trade_journal import TradeRecord


SHADOW_STRATEGIES = ("trend_momentum", "mean_reversion", "high_conviction_swing")
EXECUTION_MODE_SHADOW = "shadow_paper"


@dataclass(frozen=True)
class ExpectedMoveDiagnosticsConfig:
    state_db_path: Path
    output_dir: Path = Path("reports/paper/expected_move_diagnostics")
    run_id: str | None = None
    since: str | None = None
    high_conviction_data_paths: tuple[Path, ...] = ()
    write_report: bool = True
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def resolved_run_id(self) -> str:
        if self.run_id:
            return self.run_id
        return f"expected_move_diagnostics_{self.generated_at.strftime('%Y%m%d_%H%M%S')}"


def build_expected_move_diagnostics(config: ExpectedMoveDiagnosticsConfig) -> dict[str, Any]:
    loaded = load_state_db_paper_ledger(config.state_db_path, include_decisions=True)
    cutoff = _parse_iso(config.since)
    records = [
        record
        for record in loaded.journal.records
        if _is_shadow_record(record)
        and record.strategy_id in SHADOW_STRATEGIES
        and (cutoff is None or (record.opened_at and record.opened_at >= cutoff))
    ]
    by_strategy = {
        strategy: _segment_summary([record for record in records if record.strategy_id == strategy])
        for strategy in SHADOW_STRATEGIES
    }
    by_pair = {
        key: _segment_summary(items)
        for key, items in sorted(_group(records, lambda row: f"{row.strategy_id}/{row.symbol}").items())
    }
    destructive = [
        {"segment": key, **summary}
        for key, summary in by_pair.items()
        if summary.get("decision") == "block_shadow_future"
    ]
    report = {
        "run_id": config.resolved_run_id,
        "generated_at": config.generated_at.isoformat(),
        "state_db_path": str(config.state_db_path),
        "cutoff": config.since,
        "scope": "research_only_shadow_expected_move_audit",
        "safety": {
            "live_allowed": False,
            "paper_capital_allowed": False,
            "promotable": False,
            "grid_runtime_enabled": False,
            "uses_future_data_for_expected_move": False,
            "realized_pnl_evaluation_only": True,
        },
        "total_trade_count": len(records),
        "by_strategy": by_strategy,
        "by_pair": by_pair,
        "destructive_segments": destructive[:50],
        "high_conviction": _high_conviction_diagnostic(
            [record for record in records if record.strategy_id == "high_conviction_swing"],
            config.high_conviction_data_paths,
        ),
        "conclusion": _conclusion(by_strategy),
        "recommendation_p16": _recommendation(by_strategy),
    }
    return report


def write_expected_move_diagnostics(report: Mapping[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = str(report.get("run_id") or "expected_move_diagnostics")
    json_path = output_dir / f"{run_id}.json"
    md_path = output_dir / f"{run_id}.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_markdown(report), encoding="utf-8")
    return json_path, md_path


def _is_shadow_record(record: TradeRecord) -> bool:
    metadata = record.metadata if isinstance(record.metadata, Mapping) else {}
    return str(metadata.get("execution_mode") or "").lower() == EXECUTION_MODE_SHADOW


def _segment_summary(records: Sequence[TradeRecord]) -> dict[str, Any]:
    expected = [_float_meta(record, "expected_move_bps") for record in records]
    costs = [_float_meta(record, "estimated_total_cost_bps") for record in records]
    net_edges = [_float_meta(record, "estimated_net_edge_bps") for record in records]
    risk_reward = [_float_meta(record, "risk_reward_ratio") for record in records]
    trend_quality = [_float_meta(record, "trend_quality") for record in records]
    breakout_quality = [_float_meta(record, "breakout_quality") for record in records]
    vol_expansion = [_float_meta(record, "volatility_expansion") for record in records]
    net_pnls = [float(record.net_pnl_eur or 0.0) for record in records]
    fees = [float(record.fees_eur or 0.0) for record in records]
    slippage = [float(record.slippage_eur or 0.0) for record in records]
    reasons = Counter(str(record.metadata.get("exit_reason") or record.exit_reason or "unknown") for record in records)
    symbols = Counter(str(record.symbol or "UNKNOWN") for record in records)
    variants = Counter(str(record.metadata.get("variant") or "unknown") for record in records)
    pf = _profit_factor(net_pnls)
    expectancy = (sum(net_pnls) / len(net_pnls)) if net_pnls else None
    missing_reasons = Counter()
    for record in records:
        missing = record.metadata.get("feature_missing_reason")
        if isinstance(missing, Mapping):
            for key, reason in missing.items():
                missing_reasons[f"{key}:{reason}"] += 1
    summary = {
        "trade_count": len(records),
        "expected_move_bps": _dist(expected),
        "estimated_total_cost_bps": _dist(costs),
        "estimated_net_edge_bps": _dist(net_edges),
        "risk_reward_ratio_coverage_pct": _coverage_pct(risk_reward),
        "trend_quality_coverage_pct": _coverage_pct(trend_quality),
        "breakout_quality_coverage_pct": _coverage_pct(breakout_quality),
        "volatility_expansion_coverage_pct": _coverage_pct(vol_expansion),
        "net_pnl_eur_evaluation_only": round(sum(net_pnls), 6),
        "fees_eur": round(sum(fees), 6),
        "slippage_eur": round(sum(slippage), 6),
        "net_profit_factor": pf,
        "net_expectancy_eur": round(expectancy, 6) if expectancy is not None else None,
        "top_exit_reasons": dict(reasons.most_common(5)),
        "top_symbols": dict(symbols.most_common(5)),
        "top_variants": dict(variants.most_common(5)),
        "missing_feature_reasons": dict(missing_reasons.most_common(8)),
    }
    summary["decision"] = _segment_decision(summary)
    summary["decision_reason"] = _decision_reason(summary)
    return summary


def _segment_decision(summary: Mapping[str, Any]) -> str:
    trade_count = int(summary.get("trade_count") or 0)
    if trade_count == 0:
        return "needs_rework"
    expected = summary.get("expected_move_bps") or {}
    net_edge = summary.get("estimated_net_edge_bps") or {}
    pf = summary.get("net_profit_factor")
    expected_max = _to_float(expected.get("max"))
    net_edge_median = _to_float(net_edge.get("median"))
    if expected_max is not None and expected_max <= 0.0:
        return "needs_rework"
    if trade_count >= 30 and net_edge_median is not None and net_edge_median <= 0.0 and (pf is None or float(pf) < 0.8):
        return "block_shadow_future"
    if trade_count >= 30 and (pf is None or float(pf) < 1.0):
        return "reduce_shadow"
    return "keep_shadow"


def _decision_reason(summary: Mapping[str, Any]) -> str:
    decision = str(summary.get("decision") or "")
    expected = summary.get("expected_move_bps") or {}
    net_edge = summary.get("estimated_net_edge_bps") or {}
    if decision == "needs_rework" and _to_float(expected.get("max")) == 0.0:
        return "expected_move_zero_pretrade"
    if decision == "block_shadow_future":
        return "negative_forward_edge_and_poor_net_pf"
    if decision == "reduce_shadow":
        return "net_pf_below_one_after_costs"
    return "continue_observation_only"


def _high_conviction_diagnostic(records: Sequence[TradeRecord], paths: Iterable[Path]) -> dict[str, Any]:
    path_rows = []
    for path in paths:
        path_rows.append({"path": str(path), "exists": path.exists()})
    if not paths:
        reason = "high_conviction_data_paths_missing"
    elif not any(row["exists"] for row in path_rows):
        reason = "configured_paths_do_not_exist"
    elif not records:
        reason = "paths_available_but_no_closed_setup_synced"
    else:
        reason = "closed_observations_available"
    return {
        "trade_count": len(records),
        "data_paths": path_rows,
        "diagnosis": reason,
        "action": "provide_daily_ohlcv_paths_to_shadow_sync" if reason.endswith("missing") else "keep_research_only",
    }


def _conclusion(by_strategy: Mapping[str, Mapping[str, Any]]) -> dict[str, str]:
    return {
        strategy: str(summary.get("decision_reason") or "unknown")
        for strategy, summary in by_strategy.items()
    }


def _recommendation(by_strategy: Mapping[str, Mapping[str, Any]]) -> str:
    trend = by_strategy.get("trend_momentum", {})
    mean = by_strategy.get("mean_reversion", {})
    if trend.get("decision") in {"block_shadow_future", "needs_rework"}:
        return "P16 should redesign or throttle trend_momentum expected-move generation before more shadow volume."
    if mean.get("decision") in {"reduce_shadow", "block_shadow_future"}:
        return "P16 should make mean_reversion more cost/selectivity aware before paper-capital consideration."
    return "Continue collecting, but keep all strategies shadow-only until expected move and net edge are positive."


def _group(records: Iterable[TradeRecord], key_fn) -> dict[str, list[TradeRecord]]:
    grouped: dict[str, list[TradeRecord]] = defaultdict(list)
    for record in records:
        grouped[key_fn(record)].append(record)
    return grouped


def _float_meta(record: TradeRecord, key: str) -> float | None:
    metadata = record.metadata if isinstance(record.metadata, Mapping) else {}
    return _to_float(metadata.get(key))


def _to_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _dist(values: Sequence[float | None]) -> dict[str, Any]:
    clean = sorted(float(value) for value in values if value is not None and math.isfinite(float(value)))
    if not clean:
        return {"count": 0, "coverage_pct": 0.0, "min": None, "median": None, "max": None}
    return {
        "count": len(clean),
        "coverage_pct": round((len(clean) / max(len(values), 1)) * 100.0, 3),
        "min": round(clean[0], 6),
        "median": round(float(median(clean)), 6),
        "max": round(clean[-1], 6),
    }


def _coverage_pct(values: Sequence[float | None]) -> float:
    if not values:
        return 0.0
    present = sum(1 for value in values if value is not None)
    return round((present / len(values)) * 100.0, 3)


def _profit_factor(values: Sequence[float]) -> float | None:
    wins = sum(value for value in values if value > 0.0)
    losses = abs(sum(value for value in values if value < 0.0))
    if losses > 0.0:
        return round(wins / losses, 6)
    if wins > 0.0:
        return None
    return 0.0 if values else None


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _markdown(report: Mapping[str, Any]) -> str:
    lines = [
        f"# Expected Move Diagnostics - {report.get('run_id')}",
        "",
        f"- Total shadow trades: {report.get('total_trade_count')}",
        "- Live/paper-capital/promotion: disabled",
        "",
        "## Strategy Summary",
        "",
        "| Strategy | Trades | Exp move median/max | Net edge median | Net PF | Decision | Reason |",
        "|---|---:|---:|---:|---:|---|---|",
    ]
    for strategy, summary in (report.get("by_strategy") or {}).items():
        expected = summary.get("expected_move_bps") or {}
        edge = summary.get("estimated_net_edge_bps") or {}
        lines.append(
            "| {strategy} | {trades} | {median}/{maxv} | {edge_median} | {pf} | {decision} | {reason} |".format(
                strategy=strategy,
                trades=summary.get("trade_count"),
                median=expected.get("median"),
                maxv=expected.get("max"),
                edge_median=edge.get("median"),
                pf=summary.get("net_profit_factor"),
                decision=summary.get("decision"),
                reason=summary.get("decision_reason"),
            )
        )
    lines.extend(["", "## High Conviction", "", "```json", json.dumps(report.get("high_conviction"), indent=2), "```"])
    return "\n".join(lines) + "\n"
