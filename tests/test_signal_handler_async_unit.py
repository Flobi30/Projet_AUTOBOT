from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from autobot.v2.order_executor import OrderResult, OrderStatus
from autobot.v2.signal_handler_async import SignalHandlerAsync
from autobot.v2.strategies import SignalType, TradingSignal
from autobot.v2.validator import ValidationStatus


pytestmark = pytest.mark.unit


@dataclass
class _Config:
    max_positions: int = 5
    atr_sl_mult: float = 2.2
    tp_rr: float = 1.9
    fallback_atr_pct: float = 0.02
    max_spread_bps: float = 25.0
    min_edge_bps: float = 9.0
    risk_per_trade_pct: float = 1.5
    max_position_capital_pct: float = 20.0


class _SlottedConfig:
    __slots__ = ("api_key", "max_positions", "strategy", "symbol")

    def __init__(self):
        self.api_key = "secret-test-key"
        self.max_positions = 5
        self.strategy = "grid"
        self.symbol = "XXBTZEUR"


class _Instance:
    def __init__(self):
        self.id = "inst-unit"
        self.config = _Config()
        self.status = SimpleNamespace(value="running")
        self._strategy = None
        self._price_history = []
        self._last_price = 100.0
        self._persistence = SimpleNamespace(append_audit_event=lambda **_: None)
        self.opened = []

    def get_available_capital(self):
        return 1_000.0

    def get_positions_snapshot(self):
        return []

    async def open_position(self, **kwargs):
        self.opened.append(kwargs)
        return SimpleNamespace(id="pos-1")

    def get_current_capital(self):
        return 1_000.0

    def get_profit(self):
        return 0.0

    async def emergency_stop(self):
        return None


class _SellInstance(_Instance):
    def get_positions_snapshot(self):
        return [
            {
                "id": "pos-sell-1",
                "symbol": "XXRPZEUR",
                "volume": 2.0,
                "status": "open",
            }
        ]


class _LedgerPersistence:
    def __init__(self):
        self.ledger_rows = []

    async def append_trade_ledger(self, **kwargs):
        self.ledger_rows.append(kwargs)
        return True


class _SuccessfulSellInstance(_Instance):
    def __init__(self):
        super().__init__()
        self._persistence = _LedgerPersistence()
        self.close_calls = []

    def get_positions_snapshot(self):
        return [
            {
                "id": "pos-sell-1",
                "symbol": "XXRPZEUR",
                "buy_price": 100.0,
                "volume": 2.0,
                "status": "open",
                "metadata": {"buy_fee": 0.4},
            }
        ]

    async def close_position(self, *args, **kwargs):
        self.close_calls.append((args, kwargs))
        return 3.4


class _Validator:
    def validate(self, *_args, **_kwargs):
        return SimpleNamespace(status=ValidationStatus.GREEN, message="ok")


class _OSM:
    def is_duplicate_active(self, *_args, **_kwargs):
        return False

    def new_order(self, **_kwargs):
        return SimpleNamespace(client_order_id="cid-1")

    def transition(self, *_args, **_kwargs):
        return None


class _CountingOSM(_OSM):
    def __init__(self):
        self.new_order_calls = 0

    def new_order(self, **_kwargs):
        self.new_order_calls += 1
        return super().new_order(**_kwargs)


class _DuplicateSellOSM(_OSM):
    async def is_duplicate_active(self, _symbol, side):
        return side == "sell"


class _RecoverOSM(_OSM):
    def __init__(self):
        self.transitions = []

    async def recover_non_terminal(self):
        return [
            {
                "client_order_id": "cid-recover-1",
                "userref": 123,
                "exchange_order_id": "PAPER_FILLED",
                "symbol": "XXRPZEUR",
            }
        ]

    async def transition(self, *args, **kwargs):
        self.transitions.append((args, kwargs))
        return True


class _SuccessfulSellOSM(_OSM):
    async def is_duplicate_active(self, *_args, **_kwargs):
        return False

    async def new_order(self, **_kwargs):
        return SimpleNamespace(client_order_id="cid-sell-1", userref=4242)

    async def transition(self, *_args, **_kwargs):
        return True


class _Executor:
    def __init__(self):
        self.market_calls = 0
        self.limit_calls = 0
        self.volumes = []

    async def execute_market_order(self, *args, **kwargs):
        self.market_calls += 1
        volume = kwargs.get("volume", args[2] if len(args) > 2 else 0.0)
        self.volumes.append(float(volume))
        return OrderResult(success=True, txid="buy-1", executed_volume=float(volume), executed_price=100.0)

    async def execute_limit_order(self, *args, **kwargs):
        self.limit_calls += 1
        volume = kwargs.get("volume", args[2] if len(args) > 2 else 0.0)
        self.volumes.append(float(volume))
        return OrderResult(success=True, txid="buy-1", executed_volume=float(volume), executed_price=100.0)

    async def execute_stop_loss_order(self, *_args, **_kwargs):
        return OrderResult(success=True, txid="sl-1")


class _SellExecutor(_Executor):
    async def execute_market_order(self, *args, **kwargs):
        self.market_calls += 1
        volume = kwargs.get("volume", args[2] if len(args) > 2 else 0.0)
        self.volumes.append(float(volume))
        return OrderResult(
            success=True,
            txid="sell-1",
            executed_volume=float(volume),
            executed_price=102.0,
            fees=0.2,
            liquidity="taker",
        )


class _RecoverExecutor(_Executor):
    async def get_order_status(self, txid):
        assert txid == "PAPER_FILLED"
        return OrderStatus(
            txid=txid,
            status="filled",
            volume=2.0,
            volume_exec=2.0,
            price=1.19,
            avg_price=1.19,
            fee=0.01,
        )


@pytest.mark.asyncio
async def test_execute_buy_and_cost_guard_without_external_injection():
    handler = SignalHandlerAsync(instance=_Instance(), order_executor=_Executor())
    handler.validator = _Validator()
    handler._osm = _OSM()
    handler._post_trade_reconcile = _noop_reconcile

    signal = TradingSignal(
        type=SignalType.BUY,
        symbol="BTC/EUR",
        price=100.0,
        volume=0.2,
        reason="unit",
        timestamp=datetime.now(timezone.utc),
        metadata={"spread_bps": 10.0, "expected_move_bps": 120.0, "fee_bps": 20.0, "slippage_bps": 8.0},
    )

    assert handler._passes_cost_guard(signal, atr_pct=0.01) is True

    await handler._execute_buy(signal)

    assert len(handler.instance.opened) == 1
    assert handler.instance.opened[0]["buy_txid"] == "buy-1"


@pytest.mark.asyncio
async def test_execute_buy_rounds_to_minimum_when_budget_and_opportunity_allow():
    executor = _Executor()
    osm = _CountingOSM()
    handler = SignalHandlerAsync(instance=_Instance(), order_executor=executor)
    handler.validator = _Validator()
    handler._osm = osm
    handler._post_trade_reconcile = _noop_reconcile
    handler._opportunity_gate_applies = lambda: {"selection_applies_to_execution": False}

    signal = TradingSignal(
        type=SignalType.BUY,
        symbol="BTC/EUR",
        price=65_000.0,
        volume=0.000044,
        reason="unit below min",
        timestamp=datetime.now(timezone.utc),
        metadata={"spread_bps": 1.0, "expected_move_bps": 200.0, "fee_bps": 10.0, "slippage_bps": 2.0},
    )

    await handler._execute_buy(signal)

    assert osm.new_order_calls == 1
    assert executor.volumes == [0.0001]
    assert len(handler.instance.opened) == 1
    assert handler._last_decision_event["reason"] == "all_guards_passed"
    assert handler._last_decision_event["order_size_adjustment"]["reason"] == "rounded_to_min_order_volume"


@pytest.mark.asyncio
async def test_execute_buy_can_upsize_small_paper_signal_to_opportunity_budget():
    executor = _Executor()
    osm = _CountingOSM()
    handler = SignalHandlerAsync(instance=_Instance(), order_executor=executor)
    handler.validator = _Validator()
    handler._osm = osm
    handler._post_trade_reconcile = _noop_reconcile
    handler._is_paper_mode = lambda: True
    handler._opportunity_gate_applies = lambda: {"selection_applies_to_execution": True}
    handler._build_opportunity_result = lambda *_args, **_kwargs: SimpleNamespace(
        status="tradable",
        recommended_order_eur=40.0,
        reason="score_ok",
        score=90.0,
        to_dict=lambda: {"recommended_order_eur": 40.0, "score": 90.0, "status": "tradable"},
    )

    signal = TradingSignal(
        type=SignalType.BUY,
        symbol="BTC/EUR",
        price=100.0,
        volume=0.01,
        reason="unit tiny paper signal",
        timestamp=datetime.now(timezone.utc),
        metadata={"spread_bps": 1.0, "expected_move_bps": 200.0, "fee_bps": 10.0, "slippage_bps": 2.0},
    )

    await handler._execute_buy(signal)

    assert osm.new_order_calls == 1
    assert executor.volumes == [0.4]
    assert handler._last_decision_event["opportunity_size_adjustment"]["reason"] == "paper_opportunity_upsized"


@pytest.mark.asyncio
async def test_execute_buy_blocks_order_below_minimum_when_budget_too_small():
    instance = _Instance()
    instance.get_available_capital = lambda: 4.0
    executor = _Executor()
    osm = _CountingOSM()
    handler = SignalHandlerAsync(instance=instance, order_executor=executor)
    handler.validator = _Validator()
    handler._osm = osm
    handler._post_trade_reconcile = _noop_reconcile
    handler._opportunity_gate_applies = lambda: {"selection_applies_to_execution": False}

    signal = TradingSignal(
        type=SignalType.BUY,
        symbol="BTC/EUR",
        price=65_000.0,
        volume=0.000044,
        reason="unit below min",
        timestamp=datetime.now(timezone.utc),
        metadata={"spread_bps": 1.0, "expected_move_bps": 200.0, "fee_bps": 10.0, "slippage_bps": 2.0},
    )

    await handler._execute_buy(signal)

    assert osm.new_order_calls == 0
    assert executor.volumes == []
    assert handler.instance.opened == []
    assert handler._last_decision_event["reason"] == "order_size_below_minimum"
    assert handler._last_decision_event["min_volume"] == 0.0001


@pytest.mark.asyncio
async def test_execute_sell_records_duplicate_idempotency_rejection():
    executor = _Executor()
    handler = SignalHandlerAsync(instance=_SellInstance(), order_executor=executor)
    handler._osm = _DuplicateSellOSM()
    handler._passes_order_size_guard = lambda **_kwargs: True

    signal = TradingSignal(
        type=SignalType.SELL,
        symbol="XXRPZEUR",
        price=1.19,
        volume=2.0,
        reason="unit duplicate sell",
        timestamp=datetime.now(timezone.utc),
        metadata={},
    )

    await handler._execute_sell(signal)

    assert executor.market_calls == 0
    assert handler._last_decision_event["event"] == "sell_rejected"
    assert handler._last_decision_event["reason"] == "duplicate_active_order"
    assert handler._last_decision_event["blocking_condition"] == "idempotency_guard"


@pytest.mark.asyncio
async def test_execute_sell_records_realized_pnl_from_close_result():
    instance = _SuccessfulSellInstance()
    executor = _SellExecutor()
    handler = SignalHandlerAsync(instance=instance, order_executor=executor)
    handler._osm = _SuccessfulSellOSM()
    handler._passes_order_size_guard = lambda **_kwargs: True
    handler._post_trade_reconcile = _noop_reconcile

    signal = TradingSignal(
        type=SignalType.SELL,
        symbol="XXRPZEUR",
        price=101.5,
        volume=2.0,
        reason="unit close",
        timestamp=datetime.now(timezone.utc),
        metadata={},
    )

    await handler._execute_sell(signal)

    assert instance.close_calls[0][1]["sell_fee"] == pytest.approx(0.2)
    assert instance._persistence.ledger_rows[0]["realized_pnl"] == pytest.approx(3.4)
    assert handler._last_order_event["realized_pnl"] == pytest.approx(3.4)


def test_compute_close_realized_pnl_fallback_uses_position_metadata_fee():
    handler = SignalHandlerAsync(instance=_Instance(), order_executor=None)

    pnl = handler._compute_close_realized_pnl(
        {"buy_price": 100.0, "volume": 2.0, "metadata": {"buy_fee": 0.4}},
        sell_price=102.0,
        sell_fee=0.2,
        volume=2.0,
    )

    assert pnl == pytest.approx(3.4)


@pytest.mark.asyncio
async def test_recover_marks_filled_paper_order_terminal_not_ack():
    osm = _RecoverOSM()
    handler = SignalHandlerAsync(instance=_Instance(), order_executor=_RecoverExecutor())
    handler._osm = osm

    await handler.recover()

    assert len(osm.transitions) == 1
    args, kwargs = osm.transitions[0]
    assert args[:3] == ("cid-recover-1", "FILLED", "recovered_terminal_from_exchange")
    assert kwargs["exchange_order_id"] == "PAPER_FILLED"
    assert kwargs["filled_qty"] == pytest.approx(2.0)
    assert kwargs["avg_fill_price"] == pytest.approx(1.19)


def test_init_loads_env_and_clamps_invalid_ranges():
    import os

    env_backup = {k: os.environ.get(k) for k in ("ATR_SL_MULT", "TP_RR", "FALLBACK_ATR_PCT", "MAX_SPREAD_BPS", "MIN_EDGE_BPS")}
    try:
        os.environ["ATR_SL_MULT"] = "-4"  # invalid -> fallback then clamp
        os.environ["TP_RR"] = "0"  # invalid -> fallback
        os.environ["FALLBACK_ATR_PCT"] = "10"  # valid but clamped to safe range
        os.environ["MAX_SPREAD_BPS"] = "0"  # invalid -> fallback
        os.environ["MIN_EDGE_BPS"] = "20000"  # clamped

        handler = SignalHandlerAsync(instance=_Instance(), order_executor=None)

        assert handler._atr_sl_mult > 0
        assert handler._tp_rr > 0
        assert 0.001 <= handler._fallback_atr_pct <= 0.25
        assert 1.0 <= handler._max_spread_bps <= 1000.0
        assert 1.0 <= handler._min_edge_bps <= 1000.0
    finally:
        for key, value in env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_config_hash_supports_slotted_configs_and_redacts_secrets():
    instance = _Instance()
    instance.config = _SlottedConfig()
    handler = SignalHandlerAsync(instance=instance, order_executor=None)

    payload = handler._config_payload_for_audit(instance.config)

    assert payload["api_key"] == "<redacted>"
    assert payload["max_positions"] == 5
    assert payload["strategy"] == "grid"
    assert len(handler._config_hash()) == 64


def test_build_execution_plan_places_post_only_buy_on_bid():
    class _FakeOfi:
        def get_snapshot(self, _symbol):
            return {
                "has_book": True,
                "bid": 100.0,
                "ask": 100.05,
                "spread_bps": 5.0,
                "buy_adverse_selection_risk": 0.1,
            }

    instance = _Instance()
    instance.config.force_maker_only = True
    instance.orchestrator = SimpleNamespace(ofi=_FakeOfi())
    handler = SignalHandlerAsync(instance=instance, order_executor=None)
    signal = TradingSignal(
        type=SignalType.BUY,
        symbol="XXBTZEUR",
        price=100.04,
        volume=0.5,
        reason="unit maker",
        timestamp=datetime.now(timezone.utc),
        metadata={"limit_price": 100.04, "urgency": 0.0},
    )

    plan = handler._build_execution_plan(
        signal,
        volume=0.5,
        edge_ctx={"net_edge_bps": 50.0, "adaptive_min_edge_bps": 10.0, "spread_bps": 5.0},
    )

    assert plan["order_type"] == "limit"
    assert plan["post_only"] is True
    assert plan["price"] == pytest.approx(100.0)
    assert plan["microstructure"]["has_book"] is True


async def _noop_reconcile():
    return None
