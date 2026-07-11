from datetime import datetime, timedelta, timezone

import pytest

from autobot.v2.research.fractal_features import build_fractal_volatility_features
from autobot.v2.research.market_data_repository import MarketBar
from autobot.v2.research.purged_cv import PurgedObservation, build_purged_cv_plan
from autobot.v2.research.robustness_experiments import (
    MonteCarloConfig,
    RobustnessExperimentConfig,
    bootstrap_trade_sequence,
    build_robustness_experiment_report,
    stress_trade_records,
)
from autobot.v2.research.trade_journal import TradeRecord


pytestmark = pytest.mark.unit


def _trades(count: int = 60) -> tuple[TradeRecord, ...]:
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    result = []
    for index in range(count):
        net = 2.0 if index % 3 else -1.0
        opened_at = start + timedelta(hours=index)
        result.append(
            TradeRecord(
                run_id="pytest_advanced",
                strategy_id="high_conviction_swing",
                symbol="TRXEUR",
                side="buy",
                opened_at=opened_at,
                closed_at=opened_at + timedelta(minutes=45),
                quantity=10.0,
                entry_price=1.0,
                exit_price=1.0 + net / 10.0,
                gross_pnl_eur=net + 0.25,
                net_pnl_eur=net,
                fees_eur=0.10,
                spread_cost_eur=0.05,
                slippage_eur=0.05,
                latency_cost_eur=0.05,
                regime="multi_timeframe_swing",
            )
        )
    return tuple(result)


def test_bootstrap_is_deterministic_and_never_promotes():
    trades = _trades()
    config = MonteCarloConfig(iterations=200, seed=7, min_trade_count=50)
    first = bootstrap_trade_sequence(trades, initial_capital_eur=500.0, config=config)
    second = bootstrap_trade_sequence(trades, initial_capital_eur=500.0, config=config)

    report = build_robustness_experiment_report(
        trades,
        RobustnessExperimentConfig(run_id="pytest_robustness", monte_carlo=config),
    )

    assert first == second
    assert first.status == "observation_ready"
    assert first.mean_trade_return_lower is not None
    assert first.mean_trade_return_p50 is not None
    assert first.mean_trade_return_upper is not None
    assert first.mean_trade_return_lower <= first.mean_trade_return_p50 <= first.mean_trade_return_upper
    assert first.mean_trade_return_unit == "fraction_of_initial_capital"
    assert report.research_only is True
    assert report.paper_candidate_allowed is False
    assert report.live_promotion_allowed is False


def test_bootstrap_return_interval_scales_with_initial_capital_without_changing_pnl_quantiles():
    trades = _trades()
    config = MonteCarloConfig(iterations=200, seed=7, min_trade_count=50, confidence_level=0.90)
    base = bootstrap_trade_sequence(trades, initial_capital_eur=500.0, config=config)
    doubled = bootstrap_trade_sequence(trades, initial_capital_eur=1000.0, config=config)

    assert doubled.net_pnl_p05_eur == pytest.approx(base.net_pnl_p05_eur)
    assert doubled.net_pnl_p50_eur == pytest.approx(base.net_pnl_p50_eur)
    assert doubled.mean_trade_return_lower == pytest.approx(base.mean_trade_return_lower / 2.0)
    assert doubled.mean_trade_return_upper == pytest.approx(base.mean_trade_return_upper / 2.0)


def test_stress_is_never_more_permissive_than_base_case():
    trades = _trades()
    report = build_robustness_experiment_report(
        trades,
        RobustnessExperimentConfig(run_id="pytest_stress", monte_carlo=MonteCarloConfig(iterations=100)),
    )
    base = report.stress_scenarios[0].metrics.total_net_pnl_eur
    severe = report.stress_scenarios[-1].metrics.total_net_pnl_eur

    assert severe <= base
    assert all(item.metrics.total_fees_eur >= 0.0 for item in report.stress_scenarios)
    assert stress_trade_records(trades, report.stress_scenarios[-1].scenario)[0].net_pnl_eur <= trades[0].net_pnl_eur


def test_purged_cv_removes_overlapping_labels_and_embargoes_future_rows():
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    observations = tuple(
        PurgedObservation(
            observation_id=f"trade-{index}",
            start_at=start + timedelta(hours=index),
            end_at=start + timedelta(hours=index + 2),
        )
        for index in range(12)
    )
    plan = build_purged_cv_plan(observations, folds=3, embargo_bars=1)
    by_id = {item.observation_id: item for item in observations}

    assert plan.status == "research_planning_only"
    assert plan.research_only is True
    for fold in plan.folds:
        test_rows = [by_id[item] for item in fold.test_observation_ids]
        test_start = min(item.start_at for item in test_rows)
        test_end = max(item.end_at for item in test_rows)
        for observation_id in fold.train_observation_ids:
            row = by_id[observation_id]
            assert not (row.start_at <= test_end and row.end_at >= test_start)
        assert set(fold.train_observation_ids).isdisjoint(fold.purged_observation_ids)
        assert set(fold.train_observation_ids).isdisjoint(fold.embargoed_observation_ids)


def test_fractal_features_are_descriptive_only():
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    price = 100.0
    bars = []
    for index in range(96):
        price *= 1.0 + (0.003 if index % 5 else -0.0015)
        bars.append(
            MarketBar(
                timestamp=start + timedelta(minutes=15 * index),
                open=price,
                high=price * 1.001,
                low=price * 0.999,
                close=price,
                volume=10.0,
                symbol="TRXEUR",
                timeframe="15m",
            )
        )

    features = build_fractal_volatility_features(bars)

    assert len(features) == 1
    assert features[0].observation_only is True
    assert features[0].return_count == 95
    assert features[0].hurst_exponent is not None


def test_purged_cv_rejects_invalid_configuration():
    with pytest.raises(ValueError, match="folds"):
        build_purged_cv_plan((), folds=1)
