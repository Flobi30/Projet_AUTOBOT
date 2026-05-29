"""Validation workflow for AUTOBOT strategy research records.

This module is deliberately pure and dependency-free. It turns the research
registry into a technical contract that can be checked by tests and reused by
promotion gates without touching live trading.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence


WORKFLOW_STATUSES: tuple[str, ...] = (
    "learning",
    "candidate",
    "backtest_passed",
    "walk_forward_passed",
    "shadow_passed",
    "paper_validated",
    "rejected",
    "retired_from_execution",
)

REQUIRED_STRATEGY_FIELDS: tuple[str, ...] = (
    "strategy_id",
    "hypothesis",
    "market",
    "timeframe",
    "required_data",
    "entry_logic",
    "exit_logic",
    "risk_model",
    "fees_model",
    "slippage_model",
    "expected_market_regime",
    "failure_modes",
    "baseline_comparison",
    "validation_status",
    "last_backtest_id",
    "paper_status",
    "decision",
    "decision_reason",
)

TERMINAL_STATUSES = {"rejected", "retired_from_execution"}
EXECUTION_READY_STATUSES = {"shadow_passed", "paper_validated"}
LIVE_ELIGIBLE_STATUS = "paper_validated"
PROMOTABLE_STRATEGY_IDS = frozenset({"dynamic_grid", "trend_momentum", "mean_reversion"})


class StrategyValidationError(ValueError):
    """Raised when a strategy registry or promotion request is invalid."""


@dataclass(frozen=True)
class StrategyAcceptanceCriteria:
    """Objective thresholds used by the research guard.

    Values are intentionally modest and configurable by callers. Passing these
    checks is not live approval; it only means the evidence is strong enough for
    the requested validation stage.
    """

    min_closed_trades: int = 30
    min_shadow_closed_trades: int = 30
    min_paper_closed_trades: int = 100
    min_profit_factor: float = 1.25
    min_paper_profit_factor: float = 1.20
    min_net_pnl_eur: float = 0.0
    max_drawdown_pct: float = 12.0
    max_paper_drawdown_pct: float = 10.0
    min_sharpe: float = 0.25
    min_sortino: float = 0.0
    min_oos_periods: int = 1
    min_baseline_delta_eur: float = 0.0
    require_costs: bool = True
    require_fees: bool = True
    require_slippage: bool = True
    require_baseline: bool = True
    require_out_of_sample: bool = True


@dataclass(frozen=True)
class ValidationDecision:
    allowed: bool
    target_status: str
    reasons: tuple[str, ...] = ()
    checks: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "target_status": self.target_status,
            "reasons": list(self.reasons),
            "checks": dict(self.checks),
        }


def load_registry(path: str | Path) -> dict[str, Any]:
    registry_path = Path(path)
    with registry_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise StrategyValidationError("strategy registry root must be an object")
    return payload


def registry_entries(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    entries = payload.get("hypotheses")
    if not isinstance(entries, list):
        raise StrategyValidationError("strategy registry must contain a hypotheses list")
    return [entry for entry in entries if isinstance(entry, Mapping)]


def entry_by_strategy_id(payload: Mapping[str, Any], strategy_id: str) -> Mapping[str, Any] | None:
    for entry in registry_entries(payload):
        if str(entry.get("strategy_id") or entry.get("id") or "") == strategy_id:
            return entry
    return None


def validate_registry(payload: Mapping[str, Any]) -> list[str]:
    """Return all registry contract errors without raising."""

    errors: list[str] = []
    statuses = payload.get("decision_statuses")
    if tuple(statuses or ()) != WORKFLOW_STATUSES:
        errors.append("decision_statuses_must_match_workflow")

    if payload.get("live_auto_promotion_allowed") is not False:
        errors.append("live_auto_promotion_must_remain_false")

    try:
        entries = registry_entries(payload)
    except StrategyValidationError as exc:
        return [str(exc)]

    seen: set[str] = set()
    for index, entry in enumerate(entries):
        strategy_id = str(entry.get("strategy_id") or entry.get("id") or "")
        if not strategy_id:
            errors.append(f"hypotheses[{index}].strategy_id_missing")
        elif strategy_id in seen:
            errors.append(f"{strategy_id}:duplicate_strategy_id")
        seen.add(strategy_id)

        errors.extend(validate_strategy_entry(entry, label=strategy_id or str(index)))

    return errors


def assert_valid_registry(payload: Mapping[str, Any]) -> None:
    errors = validate_registry(payload)
    if errors:
        raise StrategyValidationError("; ".join(errors))


def validate_strategy_entry(entry: Mapping[str, Any], *, label: str | None = None) -> list[str]:
    """Return contract errors for one strategy hypothesis entry."""

    errors: list[str] = []
    strategy_id = label or str(entry.get("strategy_id") or entry.get("id") or "strategy")
    for field_name in REQUIRED_STRATEGY_FIELDS:
        if field_name not in entry:
            errors.append(f"{strategy_id}:{field_name}_missing")

    status = str(entry.get("validation_status") or "")
    if status not in WORKFLOW_STATUSES:
        errors.append(f"{strategy_id}:invalid_validation_status:{status}")

    baseline = entry.get("baseline_comparison")
    if baseline in (None, "", [], {}):
        errors.append(f"{strategy_id}:baseline_comparison_missing")

    fees_model = entry.get("fees_model")
    slippage_model = entry.get("slippage_model")
    if fees_model in (None, "", [], {}):
        errors.append(f"{strategy_id}:fees_model_missing")
    if slippage_model in (None, "", [], {}):
        errors.append(f"{strategy_id}:slippage_model_missing")
    return errors


def can_transition(current_status: str, target_status: str) -> bool:
    current = str(current_status)
    target = str(target_status)
    if current not in WORKFLOW_STATUSES or target not in WORKFLOW_STATUSES:
        return False
    if current == target:
        return True
    if target in TERMINAL_STATUSES:
        return True
    if current in TERMINAL_STATUSES:
        return False
    current_index = WORKFLOW_STATUSES.index(current)
    target_index = WORKFLOW_STATUSES.index(target)
    return target_index == current_index + 1


def assert_can_transition(current_status: str, target_status: str) -> None:
    if not can_transition(current_status, target_status):
        raise StrategyValidationError(
            f"invalid strategy status transition: {current_status!r} -> {target_status!r}"
        )


def evaluate_promotion(
    *,
    current_status: str,
    target_status: str,
    metrics: Mapping[str, Any],
    criteria: StrategyAcceptanceCriteria | None = None,
) -> ValidationDecision:
    """Evaluate whether evidence allows promotion to the requested status."""

    criteria = criteria or StrategyAcceptanceCriteria()
    checks: dict[str, Any] = {}
    reasons: list[str] = []

    if not can_transition(current_status, target_status):
        return ValidationDecision(
            allowed=False,
            target_status=target_status,
            reasons=(f"invalid_transition:{current_status}->{target_status}",),
            checks={},
        )

    if target_status in {"learning", "candidate", *TERMINAL_STATUSES}:
        return ValidationDecision(True, target_status, (), {"workflow_transition": True})

    checks.update(_common_metric_checks(metrics, criteria))
    reasons.extend(name for name, passed in checks.items() if passed is False)

    if target_status in {"walk_forward_passed", "shadow_passed", "paper_validated"}:
        oos = int(_safe_float(metrics.get("out_of_sample_periods"), 0.0))
        checks["out_of_sample_periods"] = oos >= criteria.min_oos_periods
        if not checks["out_of_sample_periods"]:
            reasons.append("out_of_sample_periods")

    if target_status in {"shadow_passed", "paper_validated"}:
        shadow_closed = int(_safe_float(metrics.get("shadow_closed_trades"), 0.0))
        shadow_pf = _optional_float(metrics.get("shadow_profit_factor"))
        shadow_net = _safe_float(metrics.get("shadow_net_pnl_eur"), 0.0)
        checks["shadow_closed_trades"] = shadow_closed >= criteria.min_shadow_closed_trades
        checks["shadow_profit_factor"] = shadow_pf is not None and shadow_pf >= criteria.min_profit_factor
        checks["shadow_net_pnl_eur"] = shadow_net > criteria.min_net_pnl_eur
        reasons.extend(
            name
            for name in ("shadow_closed_trades", "shadow_profit_factor", "shadow_net_pnl_eur")
            if checks[name] is False
        )

    if target_status == "paper_validated":
        paper_closed = int(_safe_float(metrics.get("paper_closed_trades"), 0.0))
        paper_pf = _optional_float(metrics.get("paper_profit_factor"))
        paper_net = _safe_float(metrics.get("paper_net_pnl_eur"), 0.0)
        paper_dd = _optional_float(metrics.get("paper_max_drawdown_pct"))
        checks["paper_closed_trades"] = paper_closed >= criteria.min_paper_closed_trades
        checks["paper_profit_factor"] = paper_pf is not None and paper_pf >= criteria.min_paper_profit_factor
        checks["paper_net_pnl_eur"] = paper_net > criteria.min_net_pnl_eur
        checks["paper_max_drawdown_pct"] = paper_dd is not None and paper_dd <= criteria.max_paper_drawdown_pct
        reasons.extend(
            name
            for name in (
                "paper_closed_trades",
                "paper_profit_factor",
                "paper_net_pnl_eur",
                "paper_max_drawdown_pct",
            )
            if checks[name] is False
        )

    return ValidationDecision(
        allowed=not reasons,
        target_status=target_status,
        reasons=tuple(dict.fromkeys(reasons)),
        checks=checks,
    )


def can_execute_official_paper(entry: Mapping[str, Any]) -> bool:
    if _strategy_id(entry) == "no_trade_baseline":
        return False
    return not validate_strategy_entry(entry) and str(entry.get("validation_status") or "") in EXECUTION_READY_STATUSES


def can_request_live_review(entry: Mapping[str, Any]) -> bool:
    if _strategy_id(entry) == "no_trade_baseline":
        return False
    return not validate_strategy_entry(entry) and str(entry.get("validation_status") or "") == LIVE_ELIGIBLE_STATUS


def _strategy_id(entry: Mapping[str, Any]) -> str:
    return str(entry.get("strategy_id") or entry.get("id") or "")


def _common_metric_checks(
    metrics: Mapping[str, Any],
    criteria: StrategyAcceptanceCriteria,
) -> dict[str, bool]:
    closed = int(_safe_float(metrics.get("closed_trades"), 0.0))
    profit_factor = _optional_float(metrics.get("profit_factor"))
    net_pnl = _safe_float(metrics.get("net_pnl_eur"), 0.0)
    max_dd = _optional_float(metrics.get("max_drawdown_pct"))
    sharpe = _optional_float(metrics.get("sharpe"))
    sortino = _optional_float(metrics.get("sortino"))
    baseline_delta = _optional_float(metrics.get("baseline_delta_eur"))

    checks = {
        "closed_trades": closed >= criteria.min_closed_trades,
        "profit_factor": profit_factor is not None and profit_factor >= criteria.min_profit_factor,
        "net_pnl_eur": net_pnl > criteria.min_net_pnl_eur,
        "max_drawdown_pct": max_dd is not None and max_dd <= criteria.max_drawdown_pct,
        "sharpe": sharpe is not None and sharpe >= criteria.min_sharpe,
        "sortino": sortino is not None and sortino >= criteria.min_sortino,
    }
    if criteria.require_fees or criteria.require_costs:
        checks["fees_included"] = bool(metrics.get("fees_included"))
    if criteria.require_slippage or criteria.require_costs:
        checks["slippage_included"] = bool(metrics.get("slippage_included"))
    if criteria.require_baseline:
        checks["baseline_comparison"] = bool(metrics.get("baseline_comparison"))
        checks["baseline_delta_eur"] = baseline_delta is not None and baseline_delta >= criteria.min_baseline_delta_eur
    if criteria.require_out_of_sample:
        oos = int(_safe_float(metrics.get("out_of_sample_periods"), 0.0))
        checks["out_of_sample_periods"] = oos >= criteria.min_oos_periods
    return checks


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _optional_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
