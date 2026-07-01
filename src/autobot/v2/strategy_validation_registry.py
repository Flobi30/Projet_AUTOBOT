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

from .strategy_runtime_policy import is_runtime_engine_retired


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
RUNTIME_STATUSES: tuple[str, ...] = (
    "experimental",
    "candidate",
    "paper",
    "disabled",
    "live_ready",
)
# Retired engines remain reproducible in explicit research commands, but cannot
# enter any promotion path from the runtime validation registry.
PROMOTABLE_STRATEGY_IDS = frozenset({"trend_momentum", "mean_reversion"})


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


@dataclass(frozen=True)
class StrategyRegistryRecord:
    """Runtime-facing view of one research strategy hypothesis.

    The research registry keeps detailed scientific status names. This compact
    record is the single shape that runtime-facing gates and dashboards can
    consume without inventing their own interpretation.
    """

    strategy_id: str
    family: str
    status: str
    last_profit_factor: float | None = None
    expectancy: float | None = None
    max_drawdown: float | None = None
    sample_size: int = 0
    last_validation_date: str | None = None
    paper_capital_enabled: bool = False
    reason_if_disabled: str | None = None
    runtime_enabled: bool = False
    validation_status: str = "learning"
    source_status: str = "learning"

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "family": self.family,
            "status": self.status,
            "last_profit_factor": self.last_profit_factor,
            "expectancy": self.expectancy,
            "max_drawdown": self.max_drawdown,
            "sample_size": self.sample_size,
            "last_validation_date": self.last_validation_date,
            "paper_capital_enabled": self.paper_capital_enabled,
            "reason_if_disabled": self.reason_if_disabled,
            "runtime_enabled": self.runtime_enabled,
            "validation_status": self.validation_status,
            "source_status": self.source_status,
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


def build_strategy_registry_records(
    payload: Mapping[str, Any],
    *,
    evidence_by_strategy_id: Mapping[str, Mapping[str, Any]] | None = None,
    criteria: StrategyAcceptanceCriteria | None = None,
) -> tuple[StrategyRegistryRecord, ...]:
    """Build normalized runtime-facing records from the research registry."""

    evidence_by_strategy_id = evidence_by_strategy_id or {}
    records: list[StrategyRegistryRecord] = []
    for entry in registry_entries(payload):
        strategy_id = _strategy_id(entry)
        metrics = evidence_by_strategy_id.get(strategy_id, {})
        records.append(normalize_strategy_record(entry, metrics=metrics, criteria=criteria))
    return tuple(records)


def normalize_strategy_record(
    entry: Mapping[str, Any],
    *,
    metrics: Mapping[str, Any] | None = None,
    criteria: StrategyAcceptanceCriteria | None = None,
) -> StrategyRegistryRecord:
    """Map a research hypothesis plus evidence into the canonical runtime view."""

    metrics = metrics or {}
    strategy_id = _strategy_id(entry)
    source_status = str(entry.get("validation_status") or "learning")
    family = str(entry.get("family") or entry.get("engine") or strategy_id or "unknown")

    if not strategy_id:
        return StrategyRegistryRecord(
            strategy_id="",
            family=family,
            status="disabled",
            reason_if_disabled="strategy_id_missing",
            validation_status=source_status,
            source_status=source_status,
        )

    decision = evaluate_paper_capital_gate(entry, metrics=metrics, criteria=criteria)
    validation_errors = validate_strategy_entry(entry, label=strategy_id)
    is_disabled_source = source_status in TERMINAL_STATUSES or is_runtime_engine_retired(strategy_id)
    is_candidate_source = source_status in {
        "candidate",
        "backtest_passed",
        "walk_forward_passed",
        "shadow_passed",
        "paper_validated",
    }

    if is_disabled_source or validation_errors:
        status = "disabled" if is_disabled_source else "experimental"
    elif decision.allowed and source_status == LIVE_ELIGIBLE_STATUS and can_request_live_review(entry):
        status = "live_ready"
    elif decision.allowed:
        status = "paper"
    elif is_candidate_source:
        status = "candidate"
    else:
        status = "experimental"

    paper_capital_enabled = status in {"paper", "live_ready"} and decision.allowed
    reasons = list(decision.reasons)
    if validation_errors:
        reasons.extend(validation_errors)
    if is_runtime_engine_retired(strategy_id):
        reasons.append("runtime_engine_retired")

    return StrategyRegistryRecord(
        strategy_id=strategy_id,
        family=family,
        status=status,
        last_profit_factor=_first_optional_float(
            metrics,
            "profit_factor",
            "paper_profit_factor",
            "shadow_profit_factor",
            "last_profit_factor",
        ),
        expectancy=_first_optional_float(metrics, "expectancy", "expectancy_eur"),
        max_drawdown=_first_optional_float(
            metrics,
            "max_drawdown_pct",
            "paper_max_drawdown_pct",
            "last_max_drawdown_pct",
        ),
        sample_size=int(
            _first_optional_float(metrics, "sample_size", "closed_trades", "trade_count", default=0.0) or 0
        ),
        last_validation_date=str(
            entry.get("last_validation_date") or entry.get("updated_at") or metrics.get("last_validation_date") or ""
        )
        or None,
        paper_capital_enabled=paper_capital_enabled,
        reason_if_disabled=";".join(dict.fromkeys(reasons)) or None,
        runtime_enabled=paper_capital_enabled,
        validation_status=source_status,
        source_status=source_status,
    )


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


def evaluate_paper_capital_gate(
    entry: Mapping[str, Any],
    *,
    metrics: Mapping[str, Any],
    criteria: StrategyAcceptanceCriteria | None = None,
) -> ValidationDecision:
    """Strict gate before a strategy can receive official paper capital."""

    criteria = criteria or StrategyAcceptanceCriteria()
    strategy_id = _strategy_id(entry)
    source_status = str(entry.get("validation_status") or "")
    checks: dict[str, Any] = {}
    reasons: list[str] = []

    if not entry.get("strategy_id"):
        reasons.append("strategy_id_missing")
    if not strategy_id:
        reasons.append("strategy_identifier_missing")
    elif strategy_id == "no_trade_baseline":
        reasons.append("no_trade_baseline_not_executable")
    elif is_runtime_engine_retired(strategy_id):
        reasons.append("runtime_engine_retired")

    validation_errors = validate_strategy_entry(entry, label=strategy_id or "strategy")
    if validation_errors:
        reasons.extend(validation_errors)

    checks["validation_status_execution_ready"] = source_status in EXECUTION_READY_STATUSES
    if not checks["validation_status_execution_ready"]:
        reasons.append("validation_status_not_execution_ready")

    sample_size = int(
        _first_optional_float(metrics, "sample_size", "closed_trades", "trade_count", default=0.0) or 0
    )
    profit_factor = _first_optional_float(metrics, "profit_factor", "paper_profit_factor", "shadow_profit_factor")
    expectancy = _first_optional_float(metrics, "expectancy", "expectancy_eur")
    net_pnl = _first_optional_float(metrics, "net_pnl_eur", "paper_net_pnl_eur", "shadow_net_pnl_eur")
    max_drawdown = _first_optional_float(metrics, "max_drawdown_pct", "paper_max_drawdown_pct")
    fees_present = bool(
        metrics.get("fees_included")
        or metrics.get("fees_model")
        or metrics.get("fee_bps") is not None
        or metrics.get("fees_eur") is not None
        or metrics.get("total_fees_eur") is not None
    )
    slippage_present = bool(
        metrics.get("slippage_included")
        or metrics.get("slippage_model")
        or metrics.get("slippage_bps") is not None
        or metrics.get("slippage_eur") is not None
        or metrics.get("total_slippage_eur") is not None
    )
    baseline_present = bool(metrics.get("baseline_comparison") or entry.get("baseline_comparison"))
    out_of_sample_periods = int(_first_optional_float(metrics, "out_of_sample_periods", default=0.0) or 0)

    checks["sample_size"] = sample_size >= criteria.min_closed_trades
    checks["profit_factor"] = profit_factor is not None and profit_factor > 1.0
    checks["expectancy"] = expectancy is not None and expectancy > 0.0
    checks["net_pnl_eur"] = net_pnl is not None and net_pnl > criteria.min_net_pnl_eur
    checks["max_drawdown_pct"] = max_drawdown is not None and max_drawdown <= criteria.max_drawdown_pct
    checks["fees_present"] = fees_present
    checks["slippage_present"] = slippage_present
    checks["baseline_comparison"] = baseline_present
    checks["out_of_sample_periods"] = out_of_sample_periods >= criteria.min_oos_periods

    if "walk_forward_positive_ratio" in metrics:
        checks["walk_forward_positive_ratio"] = _safe_float(metrics.get("walk_forward_positive_ratio")) >= 0.6
    if "robustness_passed" in metrics:
        checks["robustness_passed"] = bool(metrics.get("robustness_passed"))

    reasons.extend(name for name, passed in checks.items() if passed is False)

    return ValidationDecision(
        allowed=not reasons,
        target_status="paper",
        reasons=tuple(dict.fromkeys(reasons)),
        checks=checks,
    )


def can_execute_official_paper(entry: Mapping[str, Any]) -> bool:
    strategy_id = _strategy_id(entry)
    if strategy_id == "no_trade_baseline" or is_runtime_engine_retired(strategy_id):
        return False
    return not validate_strategy_entry(entry) and str(entry.get("validation_status") or "") in EXECUTION_READY_STATUSES


def can_request_live_review(entry: Mapping[str, Any]) -> bool:
    strategy_id = _strategy_id(entry)
    if strategy_id == "no_trade_baseline" or is_runtime_engine_retired(strategy_id):
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


def _first_optional_float(
    values: Mapping[str, Any],
    *names: str,
    default: float | None = None,
) -> float | None:
    for name in names:
        parsed = _optional_float(values.get(name))
        if parsed is not None:
            return parsed
    return default


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
