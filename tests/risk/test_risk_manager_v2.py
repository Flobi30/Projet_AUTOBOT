import pytest

from autobot.v2.risk.risk_manager_v2 import (
    RiskManagerV2,
    RiskManagerV2Config,
    RiskPortfolioState,
    RiskTradeRequest,
)


pytestmark = pytest.mark.unit


def _state(**overrides):
    defaults = {
        "equity_eur": 1_000.0,
        "available_cash_eur": 800.0,
        "open_trade_count": 2,
        "global_exposure_eur": 100.0,
        "symbol_exposure_eur": 20.0,
        "daily_realized_pnl_eur": 0.0,
        "peak_equity_eur": 1_000.0,
        "consecutive_losses": 0,
        "validated_trade_count": 0,
        "spread_bps": 12.0,
        "volatility_bps": 80.0,
        "data_points": 100,
    }
    defaults.update(overrides)
    return RiskPortfolioState(**defaults)


def _request(**overrides):
    defaults = {
        "strategy_id": "trend_momentum",
        "symbol": "TRXEUR",
        "side": "long",
        "entry_price": 100.0,
        "stop_loss_price": 98.0,
        "requested_notional_eur": 250.0,
        "mode": "paper",
    }
    defaults.update(overrides)
    return RiskTradeRequest(**defaults)


def test_approves_and_resizes_to_risk_budget():
    manager = RiskManagerV2()

    decision = manager.evaluate(_request(requested_notional_eur=250.0), _state())

    assert decision.approved is True
    # default risk budget = 1000 * 0.5% = 5 EUR; stop distance 2%.
    # max risk notional is 250, but max_order_notional_pct caps to 100 EUR.
    assert decision.approved_notional_eur == pytest.approx(100.0)
    assert decision.approved_quantity == pytest.approx(1.0)
    assert decision.max_loss_eur == pytest.approx(2.0)
    assert decision.risk_pct == pytest.approx(0.005)
    assert "requested_notional_reduced" in decision.warnings


def test_requested_risk_is_capped_to_max_risk_per_trade():
    config = RiskManagerV2Config(
        max_order_notional_pct=1.0,
        max_symbol_exposure_pct=1.0,
        max_global_exposure_pct=1.0,
    )
    manager = RiskManagerV2(config)

    decision = manager.evaluate(
        _request(requested_notional_eur=None, requested_risk_pct=0.05),
        _state(global_exposure_eur=0.0, symbol_exposure_eur=0.0),
    )

    assert decision.approved is True
    # capped at 1% risk: 1000 * 1% / 2% stop = 500 EUR.
    assert decision.approved_notional_eur == pytest.approx(500.0)
    assert decision.risk_pct == pytest.approx(0.01)


@pytest.mark.parametrize(
    ("state_overrides", "blocker"),
    [
        ({"data_points": 12}, "insufficient_market_data"),
        ({"open_trade_count": 10}, "max_open_trades_reached"),
        ({"consecutive_losses": 5}, "consecutive_loss_pause"),
        ({"daily_realized_pnl_eur": -31.0}, "max_daily_loss_reached"),
        ({"equity_eur": 890.0, "available_cash_eur": 700.0, "peak_equity_eur": 1_000.0}, "max_drawdown_reached"),
        ({"spread_bps": 60.0}, "spread_too_high"),
        ({"volatility_bps": 450.0}, "volatility_too_high"),
    ],
)
def test_rejects_portfolio_and_market_risk_blockers(state_overrides, blocker):
    decision = RiskManagerV2().evaluate(_request(), _state(**state_overrides))

    assert decision.approved is False
    assert blocker in decision.blockers
    assert decision.reason == blocker


def test_rejects_live_without_human_approval():
    decision = RiskManagerV2().evaluate(_request(mode="live"), _state())

    assert decision.approved is False
    assert decision.reason == "live_requires_human_approval"
    assert "live_requires_human_approval" in decision.blockers


def test_rejects_leverage_by_default():
    decision = RiskManagerV2().evaluate(_request(leverage=2.0), _state())

    assert decision.approved is False
    assert "leverage_disabled" in decision.blockers


def test_rejects_add_to_losing_position_by_default():
    decision = RiskManagerV2().evaluate(
        _request(is_add_to_existing=True),
        _state(existing_position_unrealized_pnl_eur=-4.0),
    )

    assert decision.approved is False
    assert decision.reason == "add_to_losing_position_blocked"


def test_rejects_kelly_without_enough_validated_evidence():
    config = RiskManagerV2Config(kelly_enabled=True)
    manager = RiskManagerV2(config)

    decision = manager.evaluate(_request(use_kelly=True, kelly_fraction=0.10), _state(validated_trade_count=50))

    assert decision.approved is False
    assert decision.reason == "kelly_insufficient_evidence"


def test_rejects_too_small_approved_notional_after_exposure_caps():
    config = RiskManagerV2Config(max_order_notional_pct=1.0)
    manager = RiskManagerV2(config)

    decision = manager.evaluate(
        _request(requested_notional_eur=50.0),
        _state(global_exposure_eur=499.0, symbol_exposure_eur=199.0),
    )

    assert decision.approved is False
    assert decision.reason == "approved_notional_below_min_order"
    assert decision.approved_notional_eur == pytest.approx(1.0)


def test_rejects_invalid_stop_direction_for_long_and_short():
    manager = RiskManagerV2()

    long_decision = manager.evaluate(_request(side="long", stop_loss_price=101.0), _state())
    short_decision = manager.evaluate(_request(side="short", stop_loss_price=99.0), _state())

    assert long_decision.approved is False
    assert long_decision.reason == "invalid_stop_loss_for_side"
    assert short_decision.approved is False
    assert short_decision.reason == "invalid_stop_loss_for_side"


def test_allowed_live_still_only_returns_risk_decision_not_order():
    manager = RiskManagerV2(RiskManagerV2Config(live_human_approved=True))

    decision = manager.evaluate(_request(mode="live", requested_notional_eur=50.0), _state())

    assert decision.approved is True
    assert decision.reason == "approved"
    assert decision.to_dict()["approved_notional_eur"] == pytest.approx(50.0)
    assert "order_id" not in decision.to_dict()
