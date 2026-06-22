from datetime import datetime, timedelta, timezone

import pytest

from autobot.v2.research.execution_cost_model import ExecutionCostConfig, execution_cost_config_for_profile
from autobot.v2.research.high_conviction_discovery import DiscoveryScenario, DiscoverySetup, DiscoveryTrade
from autobot.v2.research.high_conviction_portfolio import (
    HighConvictionPortfolioConfig,
    _Candidate,
    _PriceBook,
    _cost_breakdown,
    _run_portfolio_scenario,
)
from autobot.v2.research.market_data_repository import MarketBar


pytestmark = pytest.mark.unit


def _setup(entry_at: datetime, suffix: str) -> DiscoverySetup:
    return DiscoverySetup(
        setup_id=f"setup_{suffix}",
        family="breakout_1h_4h",
        symbol="TRXEUR",
        side="buy",
        detected_at=entry_at.isoformat(),
        entry_at=entry_at.isoformat(),
        entry_price=100.0,
        expected_move_bps=500.0,
        logical_stop_bps=100.0,
        risk_reward_estimate=3.0,
        trend_1h_bps=300.0,
        trend_4h_bps=400.0,
        atr_15m_bps=120.0,
        atr_1h_bps=350.0,
        support_bps=100.0,
        resistance_bps=500.0,
        timeframe_signal="5m",
        reason="pytest_high_conviction",
        features={},
    )


def _candidate(entry_at: datetime, exit_at: datetime, suffix: str) -> _Candidate:
    setup = _setup(entry_at, suffix)
    trade = DiscoveryTrade(
        setup_id=setup.setup_id,
        family=setup.family,
        symbol=setup.symbol,
        side="buy",
        entry_at=entry_at.isoformat(),
        exit_at=exit_at.isoformat(),
        entry_price=100.0,
        exit_price=103.0,
        gross_return_bps=300.0,
        cost_bps=0.0,
        net_return_bps=300.0,
        pnl_eur=0.0,
        mfe_bps=350.0,
        mae_bps=-80.0,
        mfe_mae_ratio=4.375,
        duration_minutes=(exit_at - entry_at).total_seconds() / 60.0,
        exit_reason="take_profit",
        expected_move_bps=500.0,
        logical_stop_bps=100.0,
    )
    return _Candidate(setup=setup, trade=trade, entry_at=entry_at, exit_at=exit_at)


def _price_book(start: datetime) -> _PriceBook:
    bars = [
        MarketBar(
            timestamp=start + timedelta(minutes=5 * index),
            open=100.0,
            high=103.0,
            low=99.0,
            close=100.0 + index,
            volume=1_000.0,
            symbol="TRXEUR",
            timeframe="5m",
        )
        for index in range(5)
    ]
    return _PriceBook({("TRXEUR", "5m"): bars})


def _config(tmp_path) -> HighConvictionPortfolioConfig:
    return HighConvictionPortfolioConfig(
        run_id="pytest_portfolio",
        data_paths=(tmp_path / "placeholder.csv",),
        initial_capital_eur=500.0,
        max_position_fraction=0.60,
        risk_per_trade_pct=0.50,
        max_global_exposure_pct=0.60,
        max_open_positions=3,
        cooldown_hours=1.0,
        max_daily_loss_pct=0.03,
        critical_drawdown_pct=0.12,
        drawdown_reduce_start_pct=0.05,
        min_drawdown_exposure_multiplier=0.35,
    )


def test_portfolio_replay_enforces_cash_exposure_and_one_position_per_symbol(tmp_path):
    start = datetime(2026, 6, 22, tzinfo=timezone.utc)
    config = _config(tmp_path)
    scenario = DiscoveryScenario(200.0, 2.0, 24.0, "fixed_tp_sl")
    candidates = (
        _candidate(start, start + timedelta(minutes=10), "first"),
        _candidate(start + timedelta(minutes=5), start + timedelta(minutes=15), "overlap"),
    )
    result = _run_portfolio_scenario(
        config,
        scenario,
        "pytest_zero_cost",
        "dynamic_scaling",
        candidates,
        _price_book(start),
        ExecutionCostConfig(
            taker_fee_bps=0.0,
            maker_fee_bps=0.0,
            fallback_spread_bps=0.0,
            slippage_bps=0.0,
            latency_buffer_bps=0.0,
        ),
    )

    assert result.trade_count == 1
    assert result.rejected_entries["one_position_per_symbol"] == 1
    assert result.max_allocated_exposure_pct <= 60.0 + 1e-6
    assert result.final_equity_eur == pytest.approx(509.0)
    assert result.status == "research_only"
    assert result.live_promotion_allowed is False
    assert "research_only_no_auto_promotion" in result.blockers
    assert "trade_records" not in result.to_dict()


def test_cost_breakdown_uses_selected_profile_not_hardcoded_values():
    fee, spread, slippage, latency = _cost_breakdown(execution_cost_config_for_profile("paper_current_taker"))

    assert fee == pytest.approx(80.0 / 94.0)
    assert spread == pytest.approx(8.0 / 94.0)
    assert slippage == pytest.approx(6.0 / 94.0)
    assert latency == pytest.approx(0.0)
    assert fee + spread + slippage + latency == pytest.approx(1.0)


def test_portfolio_config_rejects_critical_drawdown_below_reduction_start(tmp_path):
    with pytest.raises(ValueError, match="drawdown_reduce_start_pct"):
        HighConvictionPortfolioConfig(
            run_id="invalid_drawdown",
            data_paths=(tmp_path / "placeholder.csv",),
            critical_drawdown_pct=0.05,
            drawdown_reduce_start_pct=0.05,
        )
