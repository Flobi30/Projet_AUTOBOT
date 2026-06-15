import pytest

from autobot.v2.research.batch_strategy_validation import decide_strategy_batch
from autobot.v2.research.validation_matrix import MatrixCellResult, MatrixRunResult


pytestmark = pytest.mark.unit


def _matrix(run_id, *cells):
    return MatrixRunResult(
        run_id=run_id,
        mode="backtest",
        cell_count=len(cells),
        success_count=sum(1 for cell in cells if cell.status == "ok"),
        error_count=sum(1 for cell in cells if cell.status == "error"),
        results=tuple(cells),
        cost_config={"taker_fee_bps": 16.0, "fallback_spread_bps": 8.0, "slippage_bps": 4.0},
    )


def _cell(
    symbol,
    strategy,
    *,
    net,
    trades=150,
    pf=1.5,
    dd=5.0,
    beats_no_trade=None,
    beats_buy_and_hold=None,
    beats_random=None,
    mfe_to_cost=None,
    exit_capture=None,
):
    return MatrixCellResult(
        run_id=f"{symbol}_{strategy}",
        symbol=symbol,
        strategy=strategy,
        mode="backtest",
        status="ok",
        closed_trades=trades,
        net_pnl_eur=net,
        profit_factor=pf,
        max_drawdown_pct=dd,
        beats_no_trade=beats_no_trade,
        beats_buy_and_hold=beats_buy_and_hold,
        beats_random_signal_same_frequency=beats_random,
        average_mfe_to_cost_ratio=mfe_to_cost,
        average_exit_capture_bps=exit_capture,
    )


def test_positive_cells_remain_research_only_without_baselines_and_mfe_evidence():
    decisions = decide_strategy_batch(
        (
            _matrix("full", _cell("TRXEUR", "grid", net=12.0)),
            _matrix("late", _cell("TRXEUR", "grid", net=8.0)),
        ),
        ("grid",),
        min_closed_trades=100,
        min_profit_factor=1.2,
        max_drawdown_pct=12.0,
    )

    decision = decisions[0]
    assert decision.status == "research_only"
    assert "baseline_no_trade_unavailable" in decision.blockers
    assert "mfe_to_cost_unavailable" in decision.blockers
    assert "exit_capture_unavailable" in decision.blockers
    assert decision.overfit_risk == "high"


def test_unprofitable_strategy_is_blocked_by_net_pnl_and_samples():
    decisions = decide_strategy_batch(
        (_matrix("full", _cell("XLMZEUR", "trend", net=-5.0, trades=12, pf=0.8)),),
        ("trend",),
        min_closed_trades=30,
        min_profit_factor=1.2,
        max_drawdown_pct=12.0,
    )

    decision = decisions[0]
    assert decision.status == "research_only"
    assert "non_positive_total_net_pnl" in decision.blockers
    assert "insufficient_total_closed_trades" in decision.blockers
    assert decision.sample_size_warning is not None


def test_unknown_or_failed_strategy_defaults_to_research_only():
    decisions = decide_strategy_batch(
        (_matrix("full"),),
        ("mean_reversion",),
        min_closed_trades=30,
        min_profit_factor=1.2,
        max_drawdown_pct=12.0,
    )

    assert decisions[0].status == "research_only"
    assert decisions[0].blockers == ("no_successful_cells",)


def test_strategy_can_only_become_shadow_candidate_with_complete_evidence():
    evidence = {
        "beats_no_trade": True,
        "beats_buy_and_hold": True,
        "beats_random": True,
        "mfe_to_cost": 2.0,
        "exit_capture": 12.0,
    }
    decisions = decide_strategy_batch(
        (
            _matrix(
                "full",
                _cell("TRXEUR", "trend", net=12.0, **evidence),
                _cell("BTCZEUR", "trend", net=11.0, **evidence),
            ),
            _matrix(
                "late",
                _cell("TRXEUR", "trend", net=8.0, **evidence),
                _cell("BTCZEUR", "trend", net=9.0, **evidence),
            ),
        ),
        ("trend",),
        min_closed_trades=100,
        min_profit_factor=1.2,
        max_drawdown_pct=12.0,
    )

    decision = decisions[0]
    assert decision.status == "shadow_candidate"
    assert decision.blockers == ()


def test_strategy_remains_research_only_when_buy_and_hold_wins():
    decisions = decide_strategy_batch(
        (
            _matrix(
                "full",
                _cell(
                    "TRXEUR",
                    "trend",
                    net=12.0,
                    beats_no_trade=True,
                    beats_buy_and_hold=False,
                    beats_random=True,
                    mfe_to_cost=2.0,
                    exit_capture=12.0,
                ),
                _cell(
                    "BTCZEUR",
                    "trend",
                    net=11.0,
                    beats_no_trade=True,
                    beats_buy_and_hold=True,
                    beats_random=True,
                    mfe_to_cost=2.0,
                    exit_capture=12.0,
                ),
            ),
        ),
        ("trend",),
        min_closed_trades=100,
        min_profit_factor=1.2,
        max_drawdown_pct=12.0,
    )

    decision = decisions[0]
    assert decision.status == "research_only"
    assert "does_not_beat_buy_and_hold" in decision.blockers
