from __future__ import annotations

from types import SimpleNamespace

import pytest

from autobot.v2.opportunity_scoring import OpportunityConfig, OpportunityScorer
from autobot.v2.orchestrator_async import OrchestratorAsync
from autobot.v2.order_executor import OrderResult, OrderSide


pytestmark = pytest.mark.unit


class _Ledger:
    def __init__(self):
        self.rows = []

    async def append_trade_ledger(self, **kwargs):
        self.rows.append(kwargs)
        return True


class _Instance:
    id = "inst-xeth"
    config = SimpleNamespace(symbol="XETHZEUR")

    def __init__(self):
        self._persistence = _Ledger()
        self.close_calls = []

    def get_status(self):
        return {"last_price": 111.0}

    def get_positions_snapshot(self):
        return [
            {
                "id": "pos-1",
                "symbol": "XETHZEUR",
                "status": "open",
                "entry_price": 100.0,
                "volume": 0.5,
                "stop_loss": 95.0,
                "take_profit": 110.0,
                "stop_loss_txid": "sl-1",
                "metadata": {
                    "strategy_id": "trend_momentum",
                    "signal_source": "position_exit_test",
                    "regime": "trend",
                },
            }
        ]

    async def close_position(self, *args, **kwargs):
        self.close_calls.append((args, kwargs))
        return 5.35


class PaperTradingExecutor:
    def __init__(self):
        self.market_orders = []
        self.cancelled = []

    async def execute_market_order(self, symbol, side, volume, **kwargs):
        self.market_orders.append((symbol, side, volume, kwargs))
        return OrderResult(
            success=True,
            txid="sell-1",
            executed_volume=volume,
            executed_price=111.0,
            fees=0.20,
            liquidity="taker",
        )

    async def cancel_order(self, txid):
        self.cancelled.append(txid)
        return True


@pytest.mark.asyncio
async def test_paper_take_profit_executes_sell_and_writes_ledger():
    orch = object.__new__(OrchestratorAsync)
    orch.paper_mode = True
    orch.trailing_stops = {}
    orch._repeated_auto_actions = {}
    orch.order_executor = PaperTradingExecutor()
    instance = _Instance()

    closed = await orch._check_exit_conditions(instance)

    assert closed == 1
    assert orch.order_executor.market_orders == [
        (
            "XETHZEUR",
            OrderSide.SELL,
            0.5,
            {
                "price_hint": 111.0,
                "strategy_id": "trend_momentum",
                "signal_source": "position_exit",
                "decision_id": None,
                "signal_id": None,
                "regime": "trend",
            },
        )
    ]
    assert orch.order_executor.cancelled == ["sl-1"]
    assert instance.close_calls == [
        (("pos-1", 111.0), {"sell_txid": "sell-1", "sell_fee": 0.20})
    ]
    assert instance._persistence.rows[0]["is_closing_leg"] is True
    assert instance._persistence.rows[0]["realized_pnl"] == pytest.approx(5.35)
    assert instance._persistence.rows[0]["strategy_id"] == "trend_momentum"


def test_dynamic_paper_allocation_scales_with_edge_without_touching_live():
    scorer = OpportunityScorer(
        OpportunityConfig(
            min_score=60.0,
            min_gross_edge_bps=35.0,
            min_net_edge_bps=12.0,
            min_atr_bps=5.0,
            min_stability=0.40,
            paper_min_order_eur=10.0,
            paper_max_order_eur=80.0,
            paper_order_capital_pct=38.0,
            paper_min_order_capital_pct=12.0,
            paper_edge_boost_bps=140.0,
            paper_max_total_exposure_pct=80.0,
        )
    )
    common = {
        "expected_move_bps": 120.0,
        "total_cost_bps": 35.0,
        "adaptive_min_edge_bps": 20.0,
        "spread_bps": 1.0,
    }

    low_edge = scorer.score_signal(
        symbol="XETHZEUR",
        edge_context={**common, "net_edge_bps": 30.0},
        atr_pct=0.002,
        available_capital=200.0,
        total_capital=800.0,
        paper_mode=True,
    )
    high_edge = scorer.score_signal(
        symbol="XETHZEUR",
        edge_context={**common, "net_edge_bps": 150.0},
        atr_pct=0.002,
        available_capital=200.0,
        total_capital=800.0,
        paper_mode=True,
    )
    live = scorer.score_signal(
        symbol="XETHZEUR",
        edge_context={**common, "net_edge_bps": 150.0},
        atr_pct=0.002,
        available_capital=200.0,
        total_capital=800.0,
        paper_mode=False,
    )

    assert high_edge.recommended_order_eur > low_edge.recommended_order_eur
    assert high_edge.recommended_order_eur <= 80.0
    assert live.recommended_order_eur < high_edge.recommended_order_eur
