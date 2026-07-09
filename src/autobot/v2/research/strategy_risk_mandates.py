"""Research-only strategy risk mandate and autonomy checks.

P18C deliberately keeps this layer detached from runtime order execution.  It
models the future pre-trade envelope, reports what would be allowed, and can
only reduce/block risk automatically.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from autobot.v2.strategy_runtime_policy import GRID_RUNTIME_RETIRED_REASON, is_runtime_engine_retired


AUTO_ALLOWED = "AUTO_ALLOWED"
HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"
DECISION_ALLOW = "ALLOW"
DECISION_REDUCE = "REDUCE"
DECISION_BLOCK = "BLOCK"
DECISION_KILL = "KILL"
DECISION_HUMAN_REVIEW = "HUMAN_REVIEW_REQUIRED"
VALID_MODES = {"research", "shadow", "paper_limited", "paper_full", "live_disabled"}
RESEARCH_ONLY_FLAGS = {"paper_capital_allowed": False, "live_allowed": False, "promotable": False}
RESEARCH_ONLY_BLOCKERS = (
    "mode_is_research_only",
    "capital_max_eur_is_zero",
    "paper_capital_allowed_false",
    "runtime_orders_not_allowed",
)


class StrategyRiskMandateError(ValueError):
    """Raised when a mandate file or request is invalid."""


@dataclass(frozen=True)
class StrategyRiskMandate:
    mandate_id: str
    strategy_id: str
    mode_allowed: str
    capital_max_eur: float
    max_daily_loss_eur: float
    max_drawdown_pct: float
    max_position_eur: float
    max_symbol_exposure_eur: float
    max_total_exposure_eur: float
    max_trades_per_day: int
    max_orders_per_minute: int
    max_fees_per_day_eur: float
    max_slippage_bps: float
    max_spread_bps: float
    allowed_symbols: tuple[str, ...]
    allowed_timeframes: tuple[str, ...]
    allowed_order_types: tuple[str, ...]
    cooldown_after_losses: int
    rolling_pf_min: float
    rolling_expectancy_min: float
    min_edge_to_cost_ratio: float
    data_freshness_max_seconds: int
    expires_at: str
    human_approved_required_for_risk_increase: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "StrategyRiskMandate":
        required = {
            "mandate_id",
            "strategy_id",
            "mode_allowed",
            "capital_max_eur",
            "max_daily_loss_eur",
            "max_drawdown_pct",
            "max_position_eur",
            "max_symbol_exposure_eur",
            "max_total_exposure_eur",
            "max_trades_per_day",
            "max_orders_per_minute",
            "max_fees_per_day_eur",
            "max_slippage_bps",
            "max_spread_bps",
            "allowed_symbols",
            "allowed_timeframes",
            "allowed_order_types",
            "cooldown_after_losses",
            "rolling_pf_min",
            "rolling_expectancy_min",
            "min_edge_to_cost_ratio",
            "data_freshness_max_seconds",
            "expires_at",
        }
        missing = sorted(required - set(payload))
        if missing:
            raise StrategyRiskMandateError(f"mandate missing fields: {', '.join(missing)}")
        mandate = cls(
            mandate_id=str(payload["mandate_id"]).strip(),
            strategy_id=str(payload["strategy_id"]).strip(),
            mode_allowed=str(payload["mode_allowed"]).strip(),
            capital_max_eur=_float(payload["capital_max_eur"]),
            max_daily_loss_eur=_float(payload["max_daily_loss_eur"]),
            max_drawdown_pct=_float(payload["max_drawdown_pct"]),
            max_position_eur=_float(payload["max_position_eur"]),
            max_symbol_exposure_eur=_float(payload["max_symbol_exposure_eur"]),
            max_total_exposure_eur=_float(payload["max_total_exposure_eur"]),
            max_trades_per_day=_int(payload["max_trades_per_day"]),
            max_orders_per_minute=_int(payload["max_orders_per_minute"]),
            max_fees_per_day_eur=_float(payload["max_fees_per_day_eur"]),
            max_slippage_bps=_float(payload["max_slippage_bps"]),
            max_spread_bps=_float(payload["max_spread_bps"]),
            allowed_symbols=tuple(str(item).strip().upper() for item in payload["allowed_symbols"] if str(item).strip()),
            allowed_timeframes=tuple(str(item).strip().lower() for item in payload["allowed_timeframes"] if str(item).strip()),
            allowed_order_types=tuple(str(item).strip().lower() for item in payload["allowed_order_types"] if str(item).strip()),
            cooldown_after_losses=_int(payload["cooldown_after_losses"]),
            rolling_pf_min=_float(payload["rolling_pf_min"]),
            rolling_expectancy_min=_float(payload["rolling_expectancy_min"]),
            min_edge_to_cost_ratio=_float(payload["min_edge_to_cost_ratio"]),
            data_freshness_max_seconds=_int(payload["data_freshness_max_seconds"]),
            expires_at=str(payload["expires_at"]).strip(),
            human_approved_required_for_risk_increase=bool(
                payload.get("human_approved_required_for_risk_increase", True)
            ),
            paper_capital_allowed=bool(payload.get("paper_capital_allowed", False)),
            live_allowed=bool(payload.get("live_allowed", False)),
        )
        mandate.validate()
        return mandate

    def validate(self) -> None:
        if not self.mandate_id or not self.strategy_id:
            raise StrategyRiskMandateError("mandate_id and strategy_id are required")
        if self.mode_allowed not in VALID_MODES:
            raise StrategyRiskMandateError(f"invalid mode_allowed: {self.mode_allowed}")
        if is_runtime_engine_retired(self.strategy_id):
            raise StrategyRiskMandateError(GRID_RUNTIME_RETIRED_REASON)
        if self.live_allowed:
            raise StrategyRiskMandateError("live_allowed must remain false in research mandates")
        if self.paper_capital_allowed and self.mode_allowed == "research":
            raise StrategyRiskMandateError("research mandate cannot allow paper capital")
        if not self.human_approved_required_for_risk_increase:
            raise StrategyRiskMandateError("risk increases must require human approval")
        numeric_fields = (
            self.capital_max_eur,
            self.max_daily_loss_eur,
            self.max_drawdown_pct,
            self.max_position_eur,
            self.max_symbol_exposure_eur,
            self.max_total_exposure_eur,
            self.max_fees_per_day_eur,
            self.max_slippage_bps,
            self.max_spread_bps,
            self.rolling_pf_min,
            self.min_edge_to_cost_ratio,
        )
        if any(value < 0 for value in numeric_fields):
            raise StrategyRiskMandateError("mandate numeric limits must not be negative")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["allowed_symbols"] = list(self.allowed_symbols)
        payload["allowed_timeframes"] = list(self.allowed_timeframes)
        payload["allowed_order_types"] = list(self.allowed_order_types)
        return payload


@dataclass(frozen=True)
class PreTradeAutonomyRequest:
    strategy_id: str
    symbol: str
    timeframe: str
    order_type: str
    notional_eur: float
    symbol_exposure_eur: float
    total_exposure_eur: float
    daily_loss_eur: float
    drawdown_pct: float
    trades_today: int
    orders_last_minute: int
    fees_today_eur: float
    slippage_bps: float
    spread_bps: float
    estimated_edge_bps: float
    estimated_total_cost_bps: float
    data_age_seconds: int
    kill_switch_active: bool = False
    requested_risk_increase: bool = False
    reactivation_after_kill: bool = False


@dataclass(frozen=True)
class StrategyHealthSnapshot:
    rolling_pf: float | None = None
    rolling_expectancy: float | None = None
    consecutive_losses: int = 0
    killed: bool = False
    paper_backtest_divergence: float | None = None
    ledger_errors: int = 0


@dataclass(frozen=True)
class AutonomyDecision:
    decision: str
    reasons: tuple[str, ...]
    mandate_id: str | None
    strategy_id: str
    autonomy_level: str
    risk_direction: str
    requires_human_approval: bool
    checks: dict[str, Any]
    paper_capital_allowed: bool = False
    live_allowed: bool = False
    promotable: bool = False

    def to_dict(self) -> dict[str, Any]:
        classified = classify_autonomy_decision(self)
        return {
            "decision": self.decision,
            "final_decision": self.decision,
            "reasons": list(self.reasons),
            "passed_checks": classified["passed_checks"],
            "failed_checks": classified["failed_checks"],
            "blockers": classified["blockers"],
            "warnings": classified["warnings"],
            "mandate_id": self.mandate_id,
            "strategy_id": self.strategy_id,
            "autonomy_level": self.autonomy_level,
            "risk_direction": self.risk_direction,
            "requires_human_approval": self.requires_human_approval,
            "checks": self.checks,
            "paper_capital_allowed": self.paper_capital_allowed,
            "live_allowed": self.live_allowed,
            "promotable": self.promotable,
        }


def load_strategy_risk_mandates(path: str | Path) -> dict[str, StrategyRiskMandate]:
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    mandates = payload.get("mandates")
    if not isinstance(mandates, list) or not mandates:
        raise StrategyRiskMandateError("strategy_risk_mandates.json must contain mandates")
    parsed: dict[str, StrategyRiskMandate] = {}
    for item in mandates:
        mandate = StrategyRiskMandate.from_mapping(item)
        if mandate.strategy_id in parsed:
            raise StrategyRiskMandateError(f"duplicate mandate for strategy_id: {mandate.strategy_id}")
        parsed[mandate.strategy_id] = mandate
    return parsed


def classify_autonomy_decision(decision: AutonomyDecision) -> dict[str, list[str]]:
    passed = sorted(name for name, check in decision.checks.items() if bool(check.get("passed")))
    failed = sorted(name for name, check in decision.checks.items() if not bool(check.get("passed")))
    blockers = list(failed)
    warnings: list[str] = []
    if decision.decision == DECISION_HUMAN_REVIEW:
        blockers.append("human_review_required")
    if decision.decision in {DECISION_BLOCK, DECISION_KILL}:
        for reason in decision.reasons:
            if reason not in blockers:
                blockers.append(reason)
    if decision.decision == DECISION_BLOCK and not blockers:
        blockers.append("blocked_by_policy")
    return {
        "passed_checks": passed,
        "failed_checks": failed,
        "blockers": blockers,
        "warnings": warnings,
    }


def mandate_static_blockers(mandate: StrategyRiskMandate | None) -> list[str]:
    if mandate is None:
        return ["mandate_missing"]
    blockers: list[str] = []
    if mandate.mode_allowed == "research":
        blockers.append("mode_is_research_only")
    if mandate.capital_max_eur <= 0.0:
        blockers.append("capital_max_eur_is_zero")
    if mandate.mode_allowed == "research" and not mandate.paper_capital_allowed:
        blockers.append("paper_capital_allowed_false")
    if not mandate.allowed_order_types or mandate.max_trades_per_day <= 0 or mandate.max_orders_per_minute <= 0:
        blockers.append("runtime_orders_not_allowed")
    return blockers


class PreTradeAutonomyGate:
    """Side-effect free future pre-trade risk envelope evaluator."""

    def evaluate(
        self,
        mandate: StrategyRiskMandate | None,
        request: PreTradeAutonomyRequest,
        health: StrategyHealthSnapshot | None = None,
    ) -> AutonomyDecision:
        health = health or StrategyHealthSnapshot()
        checks: dict[str, Any] = {}
        reasons: list[str] = []
        if mandate is None:
            return _decision(
                DECISION_HUMAN_REVIEW,
                ["mandate_missing"],
                None,
                request.strategy_id,
                checks,
                risk_direction="increase",
            )
        if request.requested_risk_increase or request.reactivation_after_kill:
            return _decision(
                DECISION_HUMAN_REVIEW,
                ["risk_increase_requires_human_review"],
                mandate,
                request.strategy_id,
                checks,
                risk_direction="increase",
            )
        static_blockers = mandate_static_blockers(mandate)
        if request.strategy_id != mandate.strategy_id:
            reasons.append("strategy_not_authorized_by_mandate")
        if is_runtime_engine_retired(request.strategy_id):
            reasons.append(GRID_RUNTIME_RETIRED_REASON)
        _check(checks, reasons, "symbol_allowed", request.symbol.upper() in mandate.allowed_symbols, request.symbol)
        _check(checks, reasons, "timeframe_allowed", request.timeframe.lower() in mandate.allowed_timeframes, request.timeframe)
        _check(checks, reasons, "order_type_allowed", request.order_type.lower() in mandate.allowed_order_types, request.order_type)
        _check(checks, reasons, "notional_within_limit", request.notional_eur <= mandate.max_position_eur, request.notional_eur)
        _check(
            checks,
            reasons,
            "symbol_exposure_within_limit",
            request.symbol_exposure_eur + request.notional_eur <= mandate.max_symbol_exposure_eur,
            request.symbol_exposure_eur,
        )
        _check(
            checks,
            reasons,
            "total_exposure_within_limit",
            request.total_exposure_eur + request.notional_eur <= mandate.max_total_exposure_eur,
            request.total_exposure_eur,
        )
        _check(checks, reasons, "daily_loss_within_limit", request.daily_loss_eur <= mandate.max_daily_loss_eur, request.daily_loss_eur)
        _check(checks, reasons, "drawdown_within_limit", request.drawdown_pct <= mandate.max_drawdown_pct, request.drawdown_pct)
        _check(checks, reasons, "trades_per_day_within_limit", request.trades_today < mandate.max_trades_per_day, request.trades_today)
        _check(
            checks,
            reasons,
            "orders_per_minute_within_limit",
            request.orders_last_minute < mandate.max_orders_per_minute,
            request.orders_last_minute,
        )
        _check(checks, reasons, "fees_within_limit", request.fees_today_eur <= mandate.max_fees_per_day_eur, request.fees_today_eur)
        _check(checks, reasons, "slippage_within_limit", request.slippage_bps <= mandate.max_slippage_bps, request.slippage_bps)
        _check(checks, reasons, "spread_within_limit", request.spread_bps <= mandate.max_spread_bps, request.spread_bps)
        _check(
            checks,
            reasons,
            "data_fresh",
            request.data_age_seconds <= mandate.data_freshness_max_seconds,
            request.data_age_seconds,
        )
        edge_ratio = request.estimated_edge_bps / max(request.estimated_total_cost_bps, 1e-9)
        _check(checks, reasons, "edge_to_cost_ratio", edge_ratio >= mandate.min_edge_to_cost_ratio, edge_ratio)
        if request.kill_switch_active or health.killed:
            reasons.append("kill_switch_active")
        if health.rolling_pf is not None and health.rolling_pf < mandate.rolling_pf_min:
            return _decision(DECISION_KILL, ["rolling_pf_below_mandate"], mandate, request.strategy_id, checks)
        if health.rolling_expectancy is not None and health.rolling_expectancy < mandate.rolling_expectancy_min:
            return _decision(DECISION_KILL, ["rolling_expectancy_below_mandate"], mandate, request.strategy_id, checks)
        if health.ledger_errors > 0:
            return _decision(DECISION_KILL, ["ledger_errors_detected"], mandate, request.strategy_id, checks)
        combined_reasons = [*static_blockers, *reasons]
        if combined_reasons:
            return _decision(DECISION_BLOCK, combined_reasons, mandate, request.strategy_id, checks)
        return _decision(DECISION_ALLOW, ["within_research_mandate"], mandate, request.strategy_id, checks)


class AutoKillDowngradeEngine:
    """Side-effect free kill/downgrade classifier."""

    def evaluate(self, mandate: StrategyRiskMandate, health: StrategyHealthSnapshot) -> AutonomyDecision:
        reasons: list[str] = []
        if health.killed:
            reasons.append("already_killed")
        if health.rolling_pf is not None and health.rolling_pf < mandate.rolling_pf_min:
            reasons.append("rolling_pf_below_mandate")
        if health.rolling_expectancy is not None and health.rolling_expectancy < mandate.rolling_expectancy_min:
            reasons.append("rolling_expectancy_below_mandate")
        if health.consecutive_losses >= mandate.cooldown_after_losses:
            reasons.append("cooldown_after_losses_triggered")
        if health.ledger_errors > 0:
            reasons.append("ledger_errors_detected")
        if health.paper_backtest_divergence is not None and health.paper_backtest_divergence > 0.35:
            reasons.append("paper_backtest_divergence_too_high")
        if reasons:
            return _decision(DECISION_KILL, reasons, mandate, mandate.strategy_id, {"health": asdict(health)})
        return _decision(DECISION_ALLOW, ["health_within_mandate"], mandate, mandate.strategy_id, {"health": asdict(health)})


def build_default_request(strategy_id: str) -> PreTradeAutonomyRequest:
    return PreTradeAutonomyRequest(
        strategy_id=strategy_id,
        symbol="BCHEUR",
        timeframe="15m",
        order_type="market",
        notional_eur=0.0,
        symbol_exposure_eur=0.0,
        total_exposure_eur=0.0,
        daily_loss_eur=0.0,
        drawdown_pct=0.0,
        trades_today=0,
        orders_last_minute=0,
        fees_today_eur=0.0,
        slippage_bps=0.0,
        spread_bps=0.0,
        estimated_edge_bps=0.0,
        estimated_total_cost_bps=1.0,
        data_age_seconds=0,
    )


def _decision(
    decision: str,
    reasons: Sequence[str],
    mandate: StrategyRiskMandate | None,
    strategy_id: str,
    checks: dict[str, Any],
    *,
    risk_direction: str = "reduce",
) -> AutonomyDecision:
    human = decision == DECISION_HUMAN_REVIEW
    return AutonomyDecision(
        decision=decision,
        reasons=tuple(reasons),
        mandate_id=mandate.mandate_id if mandate else None,
        strategy_id=strategy_id,
        autonomy_level=HUMAN_REVIEW_REQUIRED if human else AUTO_ALLOWED,
        risk_direction="increase" if human else risk_direction,
        requires_human_approval=human,
        checks=checks,
        **RESEARCH_ONLY_FLAGS,
    )


def _check(checks: dict[str, Any], reasons: list[str], name: str, passed: bool, value: Any) -> None:
    checks[name] = {"passed": bool(passed), "value": value}
    if not passed:
        reasons.append(name)


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise StrategyRiskMandateError(f"expected numeric value, got {value!r}") from exc


def _int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError) as exc:
        raise StrategyRiskMandateError(f"expected integer value, got {value!r}") from exc
