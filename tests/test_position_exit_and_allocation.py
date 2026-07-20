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
        self.orders = []
        self.transitions = []

    async def upsert_order(self, **kwargs):
        self.orders.append(dict(kwargs))
        return True

    async def transition_order_state(self, **kwargs):
        self.transitions.append(dict(kwargs))
        for order in self.orders:
            if order.get("client_order_id") == kwargs.get("client_order_id"):
                order["status"] = kwargs.get("to_status")
        return True

    async def get_non_terminal_orders(self):
        terminal = {"FILLED", "CANCELED", "REJECTED", "EXPIRED"}
        return [order for order in self.orders if order.get("status") not in terminal]

    async def append_trade_ledger(self, **kwargs):
        self.rows.append(kwargs)
        return True


class _Instance:
    id = "inst-xeth"
    config = SimpleNamespace(symbol="XETHZEUR")

    def __init__(self):
        self._persistence = _Ledger()
        self.close_calls = []
        self.close_reservations = []
        self.close_releases = []

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
                    "decision_id": "dec-position-1",
                    "signal_id": "sig-position-1",
                    "regime": "trend",
                },
            }
        ]

    async def close_position(self, *args, **kwargs):
        self.close_calls.append((args, kwargs))
        return 5.35

    async def reserve_position_close(self, position_id):
        self.close_reservations.append(position_id)
        return True

    async def release_position_close(self, position_id):
        self.close_releases.append(position_id)
        return True


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
                "decision_id": "dec-position-1",
                "signal_id": "sig-position-1",
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
    assert instance._persistence.rows[0]["decision_id"] == "dec-position-1"
    assert instance._persistence.rows[0]["signal_id"] == "sig-position-1"
    assert instance._persistence.rows[0]["execution_mode"] == "shadow_paper"
    assert instance._persistence.orders[0]["strategy_id"] == "trend_momentum"
    assert instance._persistence.orders[0]["decision_id"] == "dec-position-1"
    assert instance._persistence.orders[0]["signal_id"] == "sig-position-1"
    assert [row["to_status"] for row in instance._persistence.transitions] == ["SENT", "ACK", "FILLED"]


@pytest.mark.asyncio
async def test_paper_take_profit_without_trace_is_blocked_before_executor():
    orch = object.__new__(OrchestratorAsync)
    orch.paper_mode = True
    orch.trailing_stops = {}
    orch._repeated_auto_actions = {}
    orch.order_executor = PaperTradingExecutor()
    instance = _Instance()
    position = instance.get_positions_snapshot()[0]
    position["metadata"].pop("decision_id")

    closed = await orch._execute_position_exit(
        instance,
        position,
        111.0,
        reason="take_profit",
        trigger_price=110.0,
    )

    assert closed is False
    assert orch.order_executor.market_orders == []
    assert instance._persistence.orders == []
    assert instance._persistence.rows == []
    assert instance.close_calls == []


@pytest.mark.asyncio
async def test_paper_take_profit_is_blocked_when_oms_send_transition_fails():
    orch = object.__new__(OrchestratorAsync)
    orch.paper_mode = True
    orch.trailing_stops = {}
    orch._repeated_auto_actions = {}
    orch.order_executor = PaperTradingExecutor()
    instance = _Instance()

    async def reject_transition(**_kwargs):
        return False

    instance._persistence.transition_order_state = reject_transition
    closed = await orch._check_exit_conditions(instance)

    assert closed == 0
    assert orch.order_executor.market_orders == []
    assert len(instance._persistence.orders) == 1
    assert instance._persistence.rows == []
    assert instance.close_calls == []


class _ReservationRejectedInstance(_Instance):
    async def reserve_position_close(self, position_id):
        self.close_reservations.append(position_id)
        return False


@pytest.mark.asyncio
async def test_paper_take_profit_is_blocked_before_executor_when_close_reservation_fails():
    orch = object.__new__(OrchestratorAsync)
    orch.paper_mode = True
    orch.trailing_stops = {}
    orch._repeated_auto_actions = {}
    orch.order_executor = PaperTradingExecutor()
    instance = _ReservationRejectedInstance()

    closed = await orch._check_exit_conditions(instance)

    assert closed == 0
    assert instance.close_reservations == ["pos-1"]
    assert instance.close_calls == []
    assert instance._persistence.rows == []
    assert orch.order_executor.market_orders == []
    assert [row["to_status"] for row in instance._persistence.transitions] == ["SENT", "REJECTED"]


class _RejectedPaperTradingExecutor(PaperTradingExecutor):
    async def execute_market_order(self, symbol, side, volume, **kwargs):
        self.market_orders.append((symbol, side, volume, kwargs))
        return OrderResult(success=False, error="simulated rejected sell")


@pytest.mark.asyncio
async def test_paper_take_profit_releases_close_reservation_after_known_rejection():
    orch = object.__new__(OrchestratorAsync)
    orch.paper_mode = True
    orch.trailing_stops = {}
    orch._repeated_auto_actions = {}
    orch.order_executor = _RejectedPaperTradingExecutor()
    instance = _Instance()

    closed = await orch._check_exit_conditions(instance)

    assert closed == 0
    assert instance.close_reservations == ["pos-1"]
    assert instance.close_releases == ["pos-1"]
    assert instance.close_calls == []
    assert instance._persistence.rows == []
    assert [row["to_status"] for row in instance._persistence.transitions] == ["SENT", "REJECTED"]


@pytest.mark.asyncio
async def test_paper_take_profit_is_blocked_when_oms_ack_transition_fails():
    orch = object.__new__(OrchestratorAsync)
    orch.paper_mode = True
    orch.trailing_stops = {}
    orch._repeated_auto_actions = {}
    orch.order_executor = PaperTradingExecutor()
    instance = _Instance()
    original_transition = instance._persistence.transition_order_state

    async def reject_ack(**kwargs):
        if kwargs.get("to_status") == "ACK":
            instance._persistence.transitions.append(dict(kwargs))
            return False
        return await original_transition(**kwargs)

    instance._persistence.transition_order_state = reject_ack
    closed = await orch._check_exit_conditions(instance)

    assert closed == 0
    assert instance.close_calls == []
    assert instance._persistence.rows == []
    assert [row["to_status"] for row in instance._persistence.transitions] == ["SENT", "ACK"]

    second_attempt = await orch._check_exit_conditions(instance)

    assert second_attempt == 0
    assert len(orch.order_executor.market_orders) == 1


@pytest.mark.asyncio
async def test_paper_take_profit_is_blocked_when_oms_fill_transition_fails():
    orch = object.__new__(OrchestratorAsync)
    orch.paper_mode = True
    orch.trailing_stops = {}
    orch._repeated_auto_actions = {}
    orch.order_executor = PaperTradingExecutor()
    instance = _Instance()
    original_transition = instance._persistence.transition_order_state

    async def reject_fill(**kwargs):
        if kwargs.get("to_status") == "FILLED":
            instance._persistence.transitions.append(dict(kwargs))
            return False
        return await original_transition(**kwargs)

    instance._persistence.transition_order_state = reject_fill
    closed = await orch._check_exit_conditions(instance)

    assert closed == 0
    assert instance.close_calls == []
    assert instance._persistence.rows == []
    assert [row["to_status"] for row in instance._persistence.transitions] == ["SENT", "ACK", "FILLED"]

    second_attempt = await orch._check_exit_conditions(instance)

    assert second_attempt == 0
    assert len(orch.order_executor.market_orders) == 1


class _TimeoutPaperTradingExecutor(PaperTradingExecutor):
    async def execute_market_order(self, symbol, side, volume, **kwargs):
        self.market_orders.append((symbol, side, volume, kwargs))
        raise TimeoutError("simulated executor timeout")


@pytest.mark.asyncio
async def test_paper_take_profit_timeout_is_quarantined_without_closing_position():
    orch = object.__new__(OrchestratorAsync)
    orch.paper_mode = True
    orch.trailing_stops = {}
    orch._repeated_auto_actions = {}
    orch.order_executor = _TimeoutPaperTradingExecutor()
    instance = _Instance()

    closed = await orch._check_exit_conditions(instance)

    assert closed == 0
    assert instance.close_calls == []
    assert instance._persistence.rows == []
    assert [row["to_status"] for row in instance._persistence.transitions] == ["SENT", "UNKNOWN"]

    second_attempt = await orch._check_exit_conditions(instance)

    assert second_attempt == 0
    assert len(orch.order_executor.market_orders) == 1


class _MissingPricePaperTradingExecutor(PaperTradingExecutor):
    async def execute_market_order(self, symbol, side, volume, **kwargs):
        self.market_orders.append((symbol, side, volume, kwargs))
        return OrderResult(
            success=True,
            txid="missing-price-sell-1",
            executed_volume=volume,
            executed_price=0.0,
            fees=0.20,
            liquidity="taker",
        )


@pytest.mark.asyncio
async def test_paper_take_profit_missing_fill_price_is_quarantined_without_pnl():
    orch = object.__new__(OrchestratorAsync)
    orch.paper_mode = True
    orch.trailing_stops = {}
    orch._repeated_auto_actions = {}
    orch.order_executor = _MissingPricePaperTradingExecutor()
    instance = _Instance()

    closed = await orch._check_exit_conditions(instance)

    assert closed == 0
    assert instance.close_calls == []
    assert instance._persistence.rows == []
    assert [row["to_status"] for row in instance._persistence.transitions] == ["SENT", "ACK", "UNKNOWN"]


class _PartialPaperTradingExecutor(PaperTradingExecutor):
    async def execute_market_order(self, symbol, side, volume, **kwargs):
        self.market_orders.append((symbol, side, volume, kwargs))
        return OrderResult(
            success=True,
            txid="partial-sell-1",
            executed_volume=volume / 2.0,
            executed_price=111.0,
            fees=0.10,
            liquidity="taker",
        )


@pytest.mark.asyncio
async def test_paper_take_profit_partial_fill_blocks_full_position_close():
    orch = object.__new__(OrchestratorAsync)
    orch.paper_mode = True
    orch.trailing_stops = {}
    orch._repeated_auto_actions = {}
    orch.order_executor = _PartialPaperTradingExecutor()
    instance = _Instance()

    closed = await orch._check_exit_conditions(instance)

    assert closed == 0
    assert instance.close_calls == []
    assert instance._persistence.rows == []
    assert [row["to_status"] for row in instance._persistence.transitions] == ["SENT", "ACK", "PARTIAL"]

    second_attempt = await orch._check_exit_conditions(instance)

    assert second_attempt == 0
    assert len(orch.order_executor.market_orders) == 1
    assert len(instance._persistence.orders) == 1


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
