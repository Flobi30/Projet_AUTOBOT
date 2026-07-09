from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from autobot.v2.cli import _build_parser
from autobot.v2.research.strategy_risk_mandates import (
    DECISION_ALLOW,
    DECISION_BLOCK,
    DECISION_HUMAN_REVIEW,
    DECISION_KILL,
    AutoKillDowngradeEngine,
    PreTradeAutonomyGate,
    PreTradeAutonomyRequest,
    StrategyHealthSnapshot,
    StrategyRiskMandateError,
    mandate_static_blockers,
    load_strategy_risk_mandates,
)


pytestmark = pytest.mark.unit


def test_strategy_risk_mandates_load_and_keep_capital_disabled():
    mandates = load_strategy_risk_mandates("docs/research/strategy_risk_mandates.json")

    mandate = mandates["volatility_breakout"]
    assert mandate.mode_allowed == "research"
    assert mandate.paper_capital_allowed is False
    assert mandate.live_allowed is False
    assert mandate.human_approved_required_for_risk_increase is True
    assert mandate_static_blockers(mandate) == [
        "mode_is_research_only",
        "capital_max_eur_is_zero",
        "paper_capital_allowed_false",
        "runtime_orders_not_allowed",
    ]


def test_pre_trade_gate_allows_within_explicit_test_mandate(tmp_path):
    mandate = _mandate(tmp_path, capital=100.0, symbols=["BCHEUR"], timeframes=["15m"], order_types=["market"])
    request = _request(notional_eur=25.0)

    decision = PreTradeAutonomyGate().evaluate(mandate, request, StrategyHealthSnapshot(rolling_pf=1.3, rolling_expectancy=0.2))

    assert decision.decision == DECISION_ALLOW
    assert decision.paper_capital_allowed is False
    assert decision.live_allowed is False


def test_pre_trade_gate_blocks_outside_mandate(tmp_path):
    mandate = _mandate(tmp_path, capital=100.0, symbols=["ADAEUR"], timeframes=["1h"], order_types=["limit"])

    decision = PreTradeAutonomyGate().evaluate(mandate, _request(), StrategyHealthSnapshot(rolling_pf=1.3, rolling_expectancy=0.2))

    assert decision.decision == DECISION_BLOCK
    assert "symbol_allowed" in decision.reasons
    assert "timeframe_allowed" in decision.reasons
    assert "order_type_allowed" in decision.reasons
    payload = decision.to_dict()
    assert "symbol_allowed" in payload["failed_checks"]
    assert "notional_within_limit" in payload["passed_checks"]
    assert "notional_within_limit" not in payload["blockers"]


def test_daily_loss_drawdown_spread_slippage_and_stale_data_block(tmp_path):
    mandate = _mandate(tmp_path, capital=100.0, symbols=["BCHEUR"], timeframes=["15m"], order_types=["market"])
    request = _request(daily_loss_eur=11.0, drawdown_pct=11.0, spread_bps=6.0, slippage_bps=6.0, data_age_seconds=999)

    decision = PreTradeAutonomyGate().evaluate(mandate, request, StrategyHealthSnapshot(rolling_pf=1.3, rolling_expectancy=0.2))

    assert decision.decision == DECISION_BLOCK
    assert "daily_loss_within_limit" in decision.reasons
    assert "drawdown_within_limit" in decision.reasons
    assert "spread_within_limit" in decision.reasons
    assert "slippage_within_limit" in decision.reasons
    assert "data_fresh" in decision.reasons


def test_research_only_mandate_reports_clear_static_blockers():
    mandate = load_strategy_risk_mandates("docs/research/strategy_risk_mandates.json")["volatility_breakout"]
    decision = PreTradeAutonomyGate().evaluate(mandate, _request(notional_eur=0.0), StrategyHealthSnapshot())
    payload = decision.to_dict()

    assert decision.decision == DECISION_BLOCK
    assert "mode_is_research_only" in payload["blockers"]
    assert "capital_max_eur_is_zero" in payload["blockers"]
    assert "paper_capital_allowed_false" in payload["blockers"]
    assert "runtime_orders_not_allowed" in payload["blockers"]
    assert "daily_loss_within_limit" in payload["passed_checks"]
    assert "daily_loss_within_limit" not in payload["blockers"]


def test_risk_increase_and_reactivation_require_human_review(tmp_path):
    mandate = _mandate(tmp_path, capital=100.0, symbols=["BCHEUR"], timeframes=["15m"], order_types=["market"])

    decision = PreTradeAutonomyGate().evaluate(mandate, _request(requested_risk_increase=True), StrategyHealthSnapshot())

    assert decision.decision == DECISION_HUMAN_REVIEW
    assert decision.requires_human_approval is True
    decision = PreTradeAutonomyGate().evaluate(mandate, _request(reactivation_after_kill=True), StrategyHealthSnapshot())
    assert decision.decision == DECISION_HUMAN_REVIEW


def test_auto_kill_downgrade_triggers_on_bad_health(tmp_path):
    mandate = _mandate(tmp_path, capital=100.0, symbols=["BCHEUR"], timeframes=["15m"], order_types=["market"])

    decision = AutoKillDowngradeEngine().evaluate(mandate, StrategyHealthSnapshot(rolling_pf=0.5))

    assert decision.decision == DECISION_KILL
    assert "rolling_pf_below_mandate" in decision.reasons


def test_grid_mandate_is_rejected(tmp_path):
    payload = _payload("grid", capital=100.0, symbols=["BCHEUR"], timeframes=["15m"], order_types=["market"])
    path = tmp_path / "mandates.json"
    path.write_text(json.dumps({"mandates": [payload]}), encoding="utf-8")

    with pytest.raises(StrategyRiskMandateError):
        load_strategy_risk_mandates(path)


def test_strategy_autonomy_cli_is_registered():
    parser = _build_parser()
    args = parser.parse_args(
        [
            "strategy-autonomy-check",
            "--strategy-id",
            "volatility_breakout",
            "--state-db",
            "data/autobot_state.db",
            "--mandates",
            "docs/research/strategy_risk_mandates.json",
        ]
    )

    assert args.command == "strategy-autonomy-check"
    assert args.strategy_id == "volatility_breakout"


def _mandate(tmp_path: Path, *, capital: float, symbols: list[str], timeframes: list[str], order_types: list[str]):
    payload = _payload("volatility_breakout", capital=capital, symbols=symbols, timeframes=timeframes, order_types=order_types)
    path = tmp_path / "mandates.json"
    path.write_text(json.dumps({"mandates": [payload]}), encoding="utf-8")
    return load_strategy_risk_mandates(path)["volatility_breakout"]


def _payload(strategy_id: str, *, capital: float, symbols: list[str], timeframes: list[str], order_types: list[str]) -> dict:
    return {
        "mandate_id": f"{strategy_id}_test",
        "strategy_id": strategy_id,
        "mode_allowed": "paper_limited",
        "capital_max_eur": capital,
        "max_daily_loss_eur": 10.0,
        "max_drawdown_pct": 10.0,
        "max_position_eur": 50.0,
        "max_symbol_exposure_eur": 50.0,
        "max_total_exposure_eur": 100.0,
        "max_trades_per_day": 5,
        "max_orders_per_minute": 2,
        "max_fees_per_day_eur": 2.0,
        "max_slippage_bps": 5.0,
        "max_spread_bps": 5.0,
        "allowed_symbols": symbols,
        "allowed_timeframes": timeframes,
        "allowed_order_types": order_types,
        "cooldown_after_losses": 3,
        "rolling_pf_min": 1.0,
        "rolling_expectancy_min": 0.0,
        "min_edge_to_cost_ratio": 1.2,
        "data_freshness_max_seconds": 120,
        "expires_at": "2026-12-31T23:59:59+00:00",
        "human_approved_required_for_risk_increase": True,
        "paper_capital_allowed": False,
        "live_allowed": False
    }


def _request(**overrides) -> PreTradeAutonomyRequest:
    request = PreTradeAutonomyRequest(
        strategy_id="volatility_breakout",
        symbol="BCHEUR",
        timeframe="15m",
        order_type="market",
        notional_eur=25.0,
        symbol_exposure_eur=0.0,
        total_exposure_eur=0.0,
        daily_loss_eur=0.0,
        drawdown_pct=0.0,
        trades_today=0,
        orders_last_minute=0,
        fees_today_eur=0.0,
        slippage_bps=1.0,
        spread_bps=1.0,
        estimated_edge_bps=30.0,
        estimated_total_cost_bps=10.0,
        data_age_seconds=10,
    )
    return replace(request, **overrides)
