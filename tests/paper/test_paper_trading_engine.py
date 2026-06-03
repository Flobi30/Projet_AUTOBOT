from datetime import date, datetime, timezone

import pytest

from autobot.v2.paper.paper_trading_engine import (
    PaperDailyConfig,
    PaperDecisionRecord,
    PaperTradingEngine,
)
from autobot.v2.research.trade_journal import TradeJournal, TradeRecord
from autobot.v2.risk.risk_manager_v2 import RiskDecision


pytestmark = pytest.mark.unit


REPORT_DATE = date(2026, 6, 3)


def _dt(hour):
    return datetime(2026, 6, 3, hour, tzinfo=timezone.utc)


def _trade(strategy_id="trend_momentum", net=4.0, gross=6.0, fees=1.0, spread=0.5, slippage=0.5):
    return TradeRecord(
        run_id="paper_daily_test",
        strategy_id=strategy_id,
        symbol="TRXEUR",
        side="buy",
        opened_at=_dt(9),
        closed_at=_dt(10),
        quantity=10.0,
        entry_price=1.0,
        exit_price=1.5,
        gross_pnl_eur=gross,
        net_pnl_eur=net,
        fees_eur=fees,
        spread_cost_eur=spread,
        slippage_eur=slippage,
        entry_reason="test_entry",
        exit_reason="test_exit",
    )


def _decision(strategy_id="trend_momentum", status="accepted", action="BUY", reason="approved", blockers=()):
    return PaperDecisionRecord(
        timestamp=_dt(8),
        strategy_id=strategy_id,
        symbol="TRXEUR",
        action=action,
        status=status,
        reason=reason,
        risk_blockers=tuple(blockers),
    )


def test_daily_report_uses_net_pnl_and_cost_components():
    journal = TradeJournal([_trade(net=4.0, gross=6.0), _trade(strategy_id="grid", net=-1.5, gross=-0.5)])
    engine = PaperTradingEngine(PaperDailyConfig(report_date=REPORT_DATE, initial_capital_eur=1_000.0))

    report = engine.build_daily_report(journal, [_decision(), _decision(action="HOLD")], write_report=False)

    assert report.mode == "paper"
    assert report.trade_count == 2
    assert report.metrics.total_net_pnl_eur == pytest.approx(2.5)
    assert report.metrics.total_gross_pnl_eur == pytest.approx(5.5)
    assert report.metrics.total_fees_eur == pytest.approx(2.0)
    assert report.metrics.total_spread_cost_eur == pytest.approx(1.0)
    assert report.metrics.total_slippage_eur == pytest.approx(1.0)
    assert report.hold_count == 1
    assert report.decision == "CONTINUE"
    assert report.decision_reason == "paper_within_daily_limits"


def test_daily_report_pauses_on_max_daily_loss():
    journal = TradeJournal([_trade(net=-31.0, gross=-29.0)])
    engine = PaperTradingEngine(PaperDailyConfig(report_date=REPORT_DATE, initial_capital_eur=1_000.0))

    report = engine.build_daily_report(journal, [], write_report=False)

    assert report.decision == "PAUSE"
    assert report.decision_reason == "max_daily_loss_reached"


def test_strategy_status_disables_strategy_on_daily_strategy_loss():
    journal = TradeJournal([_trade(strategy_id="mean_reversion", net=-25.0, gross=-23.0)])
    engine = PaperTradingEngine(PaperDailyConfig(report_date=REPORT_DATE, initial_capital_eur=1_000.0))

    report = engine.build_daily_report(journal, [], write_report=False)

    status = report.strategy_statuses[0]
    assert status.strategy_id == "mean_reversion"
    assert status.decision == "DISABLE_STRATEGY"
    assert status.reason == "strategy_daily_loss_limit_reached"
    assert report.decision == "DISABLE_STRATEGY"


def test_risk_rejections_are_counted_by_machine_reason():
    decisions = [
        _decision(status="risk_rejected", reason="spread_too_high", blockers=("spread_too_high",)),
        _decision(status="risk_rejected", reason="spread_too_high", blockers=("spread_too_high",)),
        _decision(status="risk_rejected", reason="insufficient_market_data", blockers=("insufficient_market_data",)),
    ]
    engine = PaperTradingEngine(
        PaperDailyConfig(report_date=REPORT_DATE, initial_capital_eur=1_000.0, max_strategy_risk_rejections=2)
    )

    report = engine.build_daily_report(TradeJournal(), decisions, write_report=False)

    assert report.risk_rejection_count == 3
    assert report.risk_rejection_reasons["spread_too_high"] == 2
    assert report.risk_rejection_reasons["insufficient_market_data"] == 1
    assert report.strategy_statuses[0].decision == "DISABLE_STRATEGY"
    assert report.strategy_statuses[0].reason == "strategy_risk_rejection_limit_reached"


def test_decision_record_can_be_created_from_risk_decision():
    risk_decision = RiskDecision(
        approved=False,
        reason="max_drawdown_reached",
        blockers=("max_drawdown_reached",),
        warnings=("requested_notional_reduced",),
    )

    record = PaperDecisionRecord.from_risk_decision(
        timestamp=_dt(7),
        strategy_id="grid",
        symbol="TRXEUR",
        action="BUY",
        decision=risk_decision,
    )

    assert record.status == "risk_rejected"
    assert record.reason == "max_drawdown_reached"
    assert record.risk_blockers == ("max_drawdown_reached",)
    assert record.risk_warnings == ("requested_notional_reduced",)


def test_report_writer_outputs_json_markdown_and_safety_notes(tmp_path):
    engine = PaperTradingEngine(
        PaperDailyConfig(report_date=REPORT_DATE, initial_capital_eur=1_000.0, output_dir=tmp_path)
    )

    report = engine.build_daily_report(TradeJournal([_trade()]), [_decision()], write_report=True)

    assert report.json_report_path
    assert report.markdown_report_path
    assert (tmp_path / "daily_2026-06-03.json").exists()
    markdown = (tmp_path / "daily_2026-06-03.md").read_text(encoding="utf-8")
    assert "No live trading permission is granted" in markdown
    assert "No orders are created by this reporting engine" in markdown
