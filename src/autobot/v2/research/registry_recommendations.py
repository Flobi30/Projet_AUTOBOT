"""Human-review registry recommendations from research validation matrices.

This module deliberately does not mutate the strategy registry. It converts a
batch of isolated research results into conservative next-step suggestions that
can be reviewed by a human before any registry edit or execution change.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from autobot.v2.strategy_validation_registry import WORKFLOW_STATUSES, can_transition, entry_by_strategy_id

from .validation_matrix import MatrixCellResult, MatrixRunResult


STRATEGY_TO_REGISTRY_ID: dict[str, str] = {
    "grid": "dynamic_grid",
    "trend": "trend_momentum",
    "mean_reversion": "mean_reversion",
}


@dataclass(frozen=True)
class RegistryRecommendationCriteria:
    min_closed_trades: int = 30
    min_profit_factor: float = 1.25
    min_net_pnl_eur: float = 0.0
    max_drawdown_pct: float = 12.0
    min_passing_symbols: int = 1
    reject_profit_factor_below: float = 1.0


@dataclass(frozen=True)
class StrategyRecommendation:
    strategy: str
    registry_strategy_id: str
    current_status: str | None
    recommended_status: str
    decision: str
    reason: str
    evidence_status: str
    best_symbol: str | None
    evaluated_symbols: int
    passing_symbols: int
    total_closed_trades: int
    aggregate_net_pnl_eur: float
    best_profit_factor: float | None
    worst_drawdown_pct: float | None
    live_promotion_allowed: bool = False
    registry_update_applied: bool = False
    source_cells: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["source_cells"] = list(self.source_cells)
        return payload


@dataclass(frozen=True)
class RegistryRecommendationReport:
    matrix_run_id: str
    mode: str
    recommendations: tuple[StrategyRecommendation, ...]
    json_report_path: str | None = None
    markdown_report_path: str | None = None
    safety_notes: tuple[str, ...] = field(
        default=(
            "Research-only recommendation report.",
            "No strategy registry mutation is performed.",
            "No live trading permission is granted.",
        )
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "matrix_run_id": self.matrix_run_id,
            "mode": self.mode,
            "recommendations": [recommendation.to_dict() for recommendation in self.recommendations],
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
            "safety_notes": list(self.safety_notes),
        }


def load_matrix_result(path: str | Path) -> MatrixRunResult:
    """Load a matrix JSON report.

    Supports both the raw ``run_validation_matrix`` JSON and the combined
    ``validate-strategies`` workflow JSON, where the matrix payload is nested
    under the ``matrix`` key.
    """

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, Mapping) and isinstance(payload.get("matrix"), Mapping):
        payload = dict(payload["matrix"])
    results = tuple(
        MatrixCellResult(
            run_id=str(item["run_id"]),
            symbol=str(item["symbol"]),
            strategy=str(item["strategy"]),
            mode=str(item["mode"]),
            status=str(item["status"]),
            decision=item.get("decision"),
            reason=item.get("reason"),
            bar_count=int(item.get("bar_count") or 0),
            closed_trades=int(item.get("closed_trades") or 0),
            net_pnl_eur=_optional_float(item.get("net_pnl_eur")),
            total_return_pct=_optional_float(item.get("total_return_pct")),
            profit_factor=_optional_float(item.get("profit_factor")),
            max_drawdown_pct=_optional_float(item.get("max_drawdown_pct")),
            report_path=item.get("report_path"),
            error=item.get("error"),
        )
        for item in payload.get("results", [])
    )
    return MatrixRunResult(
        run_id=str(payload["run_id"]),
        mode=str(payload["mode"]),
        cell_count=int(payload.get("cell_count") or len(results)),
        success_count=int(payload.get("success_count") or sum(1 for result in results if result.status == "ok")),
        error_count=int(payload.get("error_count") or sum(1 for result in results if result.status == "error")),
        results=results,
        json_report_path=payload.get("json_report_path"),
        markdown_report_path=payload.get("markdown_report_path"),
    )


def recommend_from_matrix(
    matrix: MatrixRunResult,
    *,
    registry_payload: Mapping[str, Any] | None = None,
    criteria: RegistryRecommendationCriteria | None = None,
) -> RegistryRecommendationReport:
    """Summarize matrix cells into conservative registry next-step proposals."""

    criteria = criteria or RegistryRecommendationCriteria()
    grouped: dict[str, list[MatrixCellResult]] = {}
    for cell in matrix.results:
        grouped.setdefault(cell.strategy, []).append(cell)

    recommendations = tuple(
        _recommend_strategy(
            strategy=strategy,
            cells=tuple(cells),
            mode=matrix.mode,
            registry_payload=registry_payload,
            criteria=criteria,
        )
        for strategy, cells in sorted(grouped.items())
    )
    return RegistryRecommendationReport(
        matrix_run_id=matrix.run_id,
        mode=matrix.mode,
        recommendations=recommendations,
    )


def write_registry_recommendation_report(
    report: RegistryRecommendationReport,
    output_dir: str | Path,
) -> RegistryRecommendationReport:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / f"{report.matrix_run_id}_registry_recommendations.json"
    md_path = output_path / f"{report.matrix_run_id}_registry_recommendations.md"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(render_registry_recommendation_report(report), encoding="utf-8")
    return RegistryRecommendationReport(
        matrix_run_id=report.matrix_run_id,
        mode=report.mode,
        recommendations=report.recommendations,
        json_report_path=str(json_path),
        markdown_report_path=str(md_path),
        safety_notes=report.safety_notes,
    )


def render_registry_recommendation_report(report: RegistryRecommendationReport) -> str:
    lines = [
        f"# Registry Recommendations - {report.matrix_run_id}",
        "",
        f"Mode: `{report.mode}`",
        "",
        "## Recommendations",
        "",
        "| Strategy | Registry ID | Current | Recommended | Decision | Reason | Best Symbol | Passing Symbols | Trades | Net PnL | Best PF | Worst DD | Live Allowed |",
        "| --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in report.recommendations:
        lines.append(
            f"| {item.strategy} | {item.registry_strategy_id} | {item.current_status or ''} | "
            f"{item.recommended_status} | {item.decision} | {item.reason} | {item.best_symbol or ''} | "
            f"{item.passing_symbols}/{item.evaluated_symbols} | {item.total_closed_trades} | "
            f"{item.aggregate_net_pnl_eur:.6f} | {_fmt(item.best_profit_factor)} | "
            f"{_fmt(item.worst_drawdown_pct)} | {item.live_promotion_allowed} |"
        )
    lines.extend(
        [
            "",
            "## Safety",
            "",
        ]
    )
    lines.extend(f"- {note}" for note in report.safety_notes)
    lines.append("")
    return "\n".join(lines)


def _recommend_strategy(
    *,
    strategy: str,
    cells: Sequence[MatrixCellResult],
    mode: str,
    registry_payload: Mapping[str, Any] | None,
    criteria: RegistryRecommendationCriteria,
) -> StrategyRecommendation:
    registry_strategy_id = STRATEGY_TO_REGISTRY_ID.get(strategy, strategy)
    current_status = _current_status(registry_payload, registry_strategy_id)
    ok_cells = tuple(cell for cell in cells if cell.status == "ok")
    best_cell = _best_cell(ok_cells)
    passing_cells = tuple(cell for cell in ok_cells if _cell_passes(cell, mode=mode, criteria=criteria))
    total_closed_trades = sum(max(0, cell.closed_trades) for cell in ok_cells)
    aggregate_net_pnl = sum(cell.net_pnl_eur or 0.0 for cell in ok_cells)
    best_profit_factor = _max_optional(cell.profit_factor for cell in ok_cells)
    worst_drawdown = _max_optional(cell.max_drawdown_pct for cell in ok_cells)
    evidence_status = _target_status_for_mode(mode)

    if not ok_cells:
        decision = "insufficient_evidence"
        reason = "all_matrix_cells_failed"
        proposed_status = current_status or "learning"
    elif len(passing_cells) >= criteria.min_passing_symbols:
        decision = "promote_candidate"
        reason = f"{mode}_criteria_passed_for_human_review"
        proposed_status = evidence_status
    elif total_closed_trades < criteria.min_closed_trades:
        decision = "keep_testing"
        reason = "insufficient_closed_trades"
        proposed_status = "candidate" if aggregate_net_pnl > criteria.min_net_pnl_eur else (current_status or "learning")
    elif aggregate_net_pnl <= criteria.min_net_pnl_eur:
        decision = "reject"
        reason = "non_positive_aggregate_net_pnl"
        proposed_status = "rejected"
    elif best_profit_factor is not None and best_profit_factor < criteria.reject_profit_factor_below:
        decision = "reject"
        reason = "profit_factor_below_rejection_floor"
        proposed_status = "rejected"
    else:
        decision = "modify"
        reason = "matrix_criteria_not_met"
        proposed_status = "candidate"

    recommended_status = _workflow_safe_status(current_status, proposed_status)
    if recommended_status != proposed_status and proposed_status not in {current_status, None}:
        reason = f"{reason}; workflow_step_required_before_{proposed_status}"

    return StrategyRecommendation(
        strategy=strategy,
        registry_strategy_id=registry_strategy_id,
        current_status=current_status,
        recommended_status=recommended_status,
        decision=decision,
        reason=reason,
        evidence_status=evidence_status,
        best_symbol=best_cell.symbol if best_cell else None,
        evaluated_symbols=len({cell.symbol for cell in cells}),
        passing_symbols=len({cell.symbol for cell in passing_cells}),
        total_closed_trades=total_closed_trades,
        aggregate_net_pnl_eur=aggregate_net_pnl,
        best_profit_factor=best_profit_factor,
        worst_drawdown_pct=worst_drawdown,
        live_promotion_allowed=False,
        registry_update_applied=False,
        source_cells=tuple(cell.run_id for cell in cells),
    )


def _cell_passes(
    cell: MatrixCellResult,
    *,
    mode: str,
    criteria: RegistryRecommendationCriteria,
) -> bool:
    if cell.status != "ok":
        return False
    if mode == "walk_forward":
        return cell.decision == "walk_forward_passed" and (cell.net_pnl_eur or 0.0) > criteria.min_net_pnl_eur
    return (
        cell.decision == "promote_candidate"
        and cell.closed_trades >= criteria.min_closed_trades
        and (cell.net_pnl_eur or 0.0) > criteria.min_net_pnl_eur
        and cell.profit_factor is not None
        and cell.profit_factor >= criteria.min_profit_factor
        and cell.max_drawdown_pct is not None
        and cell.max_drawdown_pct <= criteria.max_drawdown_pct
    )


def _target_status_for_mode(mode: str) -> str:
    return "walk_forward_passed" if mode == "walk_forward" else "backtest_passed"


def _current_status(registry_payload: Mapping[str, Any] | None, strategy_id: str) -> str | None:
    if not registry_payload:
        return None
    entry = entry_by_strategy_id(registry_payload, strategy_id)
    if not entry:
        return None
    status = str(entry.get("validation_status") or "")
    return status if status in WORKFLOW_STATUSES else None


def _workflow_safe_status(current_status: str | None, proposed_status: str) -> str:
    if current_status is None:
        return proposed_status if proposed_status in {"learning", "candidate", "rejected"} else "candidate"
    if current_status == proposed_status:
        return current_status
    if can_transition(current_status, proposed_status):
        return proposed_status
    if current_status in {"rejected", "retired_from_execution", "paper_validated"}:
        return current_status
    if proposed_status == "rejected":
        return "rejected"
    current_index = WORKFLOW_STATUSES.index(current_status)
    next_status = WORKFLOW_STATUSES[current_index + 1]
    return next_status if next_status not in {"rejected", "retired_from_execution"} else current_status


def _best_cell(cells: Sequence[MatrixCellResult]) -> MatrixCellResult | None:
    if not cells:
        return None
    return max(cells, key=lambda cell: (cell.net_pnl_eur or float("-inf"), cell.closed_trades))


def _max_optional(values: Sequence[float | None] | Any) -> float | None:
    numeric = [float(value) for value in values if value is not None]
    return max(numeric) if numeric else None


def _optional_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt(value: float | None) -> str:
    return "" if value is None else f"{value:.6f}"
