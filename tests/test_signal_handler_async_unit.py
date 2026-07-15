from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from autobot.v2.order_executor import OrderResult, OrderStatus
from autobot.v2.research.shadow_governance import StrategyArtifact, feature_snapshot_reference_from_mapping
from autobot.v2.signal_handler_async import SignalHandlerAsync
from autobot.v2.strategies import SignalType, TradingSignal
from autobot.v2.validator import ValidationStatus


pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _enable_legacy_direct_execution_for_isolated_handler_tests(monkeypatch):
    """Keep legacy-path unit fixtures explicit; production defaults fail closed."""
    monkeypatch.setenv("AUTOBOT_LEGACY_DIRECT_EXECUTION_ENABLED", "true")


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


class _TracePersistence(_LedgerPersistence):
    def __init__(self):
        super().__init__()
        self.decision_events = []
        self.audit_events = []

    async def append_decision_ledger_event(self, **kwargs):
        self.decision_events.append(kwargs)
        return True

    async def append_audit_event(self, **kwargs):
        self.audit_events.append(kwargs)
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


class _CanonicalTraceOSM(_OSM):
    def __init__(self, persistence, accepted_status):
        self.persistence = persistence
        self.accepted_status = accepted_status
        self.new_order_calls = []
        self.transitions = []

    async def is_duplicate_active(self, *_args, **_kwargs):
        return False

    async def new_order(self, **kwargs):
        self.new_order_calls.append(kwargs)
        decision_id = kwargs.get("decision_id")
        signal_id = kwargs.get("signal_id")
        assert decision_id
        assert signal_id
        assert any(
            row.get("decision_id") == decision_id
            and row.get("signal_id") == signal_id
            and row.get("event_status") == self.accepted_status
            for row in self.persistence.decision_events
        )
        return SimpleNamespace(client_order_id=f"cid-{self.accepted_status}", userref=4242)

    async def transition(self, *args, **kwargs):
        self.transitions.append((args, kwargs))
        return True


class _SafeKillSwitch:
    tripped = False

    @staticmethod
    def is_globally_tripped():
        return False

    @staticmethod
    def record_api_success():
        return None

    @staticmethod
    async def record_api_failure(_reason):
        return None

    @staticmethod
    def mark_partial(*_args, **_kwargs):
        return None

    @staticmethod
    def clear_partial(*_args, **_kwargs):
        return None


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
async def test_execute_buy_and_cost_guard_with_explicit_legacy_test_opt_in(monkeypatch):
    monkeypatch.setenv("AUTOBOT_LEGACY_DIRECT_EXECUTION_ENABLED", "true")
    handler = SignalHandlerAsync(instance=_Instance(), order_executor=_Executor())
    handler.validator = _Validator()
    handler._osm = _OSM()
    handler._post_trade_reconcile = _noop_reconcile
    # This legacy-path test covers the cost guard only. Opportunity selection
    # has separate tests and may be enabled by production-like test fixtures.
    handler._opportunity_gate_applies = lambda: {"selection_applies_to_execution": False}

    signal = TradingSignal(
        type=SignalType.BUY,
        symbol="BTC/EUR",
        price=100.0,
        volume=0.2,
        reason="unit",
        timestamp=datetime.now(timezone.utc),
        metadata={
            "strategy_id": "trend_momentum",
            "strategy": "trend_momentum",
            "spread_bps": 10.0,
            "expected_move_bps": 160.0,
            "fee_bps": 20.0,
            "slippage_bps": 8.0,
        },
    )

    assert handler._passes_cost_guard(signal, atr_pct=0.01) is True

    await handler._execute_buy(signal)

    assert len(handler.instance.opened) == 1
    assert handler.instance.opened[0]["buy_txid"] == "buy-1"


@pytest.mark.asyncio
async def test_execute_buy_fails_closed_when_legacy_direct_execution_is_not_explicitly_enabled(monkeypatch):
    monkeypatch.delenv("AUTOBOT_LEGACY_DIRECT_EXECUTION_ENABLED", raising=False)
    executor = _Executor()
    handler = SignalHandlerAsync(instance=_Instance(), order_executor=executor)
    handler.validator = _Validator()
    handler._osm = _OSM()

    signal = TradingSignal(
        type=SignalType.BUY,
        symbol="BTC/EUR",
        price=100.0,
        volume=0.2,
        reason="unit fail closed",
        timestamp=datetime.now(timezone.utc),
        metadata={"strategy": "trend_momentum"},
    )

    await handler._execute_buy(signal)

    assert handler.instance.opened == []
    assert executor.market_calls == 0
    assert executor.limit_calls == 0
    assert handler._last_decision_event["reason"] == "legacy_direct_execution_disabled"
    assert handler._last_decision_event["shadow_contract_preview"]["status"] == "SHADOW_PREVIEW_REJECTED"
    assert handler._last_decision_event["shadow_contract_preview"]["execution_command_created"] is False


@pytest.mark.asyncio
async def test_execute_buy_records_ready_shadow_contract_preview_without_submitting_order(monkeypatch):
    monkeypatch.delenv("AUTOBOT_LEGACY_DIRECT_EXECUTION_ENABLED", raising=False)
    executor = _Executor()
    handler = SignalHandlerAsync(instance=_Instance(), order_executor=executor)
    handler.validator = _Validator()
    handler._osm = _OSM()

    signal = TradingSignal(
        type=SignalType.BUY,
        symbol="BTC/EUR",
        price=100.0,
        volume=0.2,
        reason="unit shadow preview",
        timestamp=datetime(2026, 7, 12, 10, tzinfo=timezone.utc),
        metadata={
            "strategy_id": "trend_momentum",
            "strategy_version": "trend-v3",
            "data_snapshot_id": "ohlcv_snapshot_1",
            "data_available_at": "2026-07-12T10:01:00+00:00",
            "net_expected_edge_bps": 24.0,
            "shadow_notional_eur": 20.0,
            "feature_versions": {"momentum": "v1"},
            "strategy_artifact": StrategyArtifact(
                strategy_id="trend_momentum",
                strategy_version="trend-v3",
                code_commit="handler-fixture-commit",
                data_snapshot_id="ohlcv_snapshot_1",
                feature_versions={"momentum": "v1"},
                parameters={"fixture": True},
                risk_mandate_fingerprint="handler-mandate-fixture",
                validation_manifest_fingerprint="handler-validation-fixture",
                feature_snapshots=(
                    feature_snapshot_reference_from_mapping(
                        {
                            "feature_snapshot_id": "features_handler_fixture",
                            "feature_snapshot_fingerprint": "feature-fingerprint-handler-fixture",
                            "snapshot_kind": "FEATURE_SNAPSHOT",
                            "source_snapshot_id": "ohlcv_snapshot_1",
                            "source_snapshot_fingerprint": "source-fingerprint-handler-fixture",
                            "feature_registry_fingerprint": "registry-fingerprint-handler-fixture",
                            "feature_versions": {"momentum": "v1"},
                            "feature_count": 20,
                            "parity_ok": True,
                            "runtime_parity_proven": True,
                            "ingestion_time_unknown_count": 0,
                        }
                    ),
                ),
                status="SHADOW",
                experiment_id="handler-experiment-fixture",
                experiment_fingerprint="handler-experiment-fingerprint",
                human_approval_reference="handler-human-approval",
            ).to_dict(),
            "market_identity": {
                "exchange": "kraken",
                "market_type": "spot",
                "symbol": "BTCEUR",
                "base_asset": "BTC",
                "quote_asset": "EUR",
            },
        },
    )

    await handler._execute_buy(signal)

    preview = handler._last_decision_event["shadow_contract_preview"]
    assert preview["status"] == "SHADOW_PREVIEW_READY"
    assert preview["order_intent"]["execution_mode"] == "shadow"
    assert preview["execution_command_created"] is False
    assert executor.market_calls == 0
    assert executor.limit_calls == 0
    assert handler.instance.opened == []


def test_cost_guard_counts_exit_fee_for_round_trip():
    handler = SignalHandlerAsync(instance=_Instance(), order_executor=_Executor())
    signal = TradingSignal(
        type=SignalType.BUY,
        symbol="BTC/EUR",
        price=100.0,
        volume=0.2,
        reason="unit",
        timestamp=datetime.now(timezone.utc),
        metadata={
            "spread_bps": 0.0,
            "expected_move_bps": 64.0,
            "fee_bps": 25.0,
            "exit_fee_bps": 40.0,
            "slippage_bps": 0.0,
        },
    )
    risk = {
        "atr_sl_mult": 1.0,
        "tp_rr": 1.0,
        "min_edge_bps": 1.0,
        "cost_buffer_mult": 0.0,
        "volatility_edge_weight": 0.0,
    }

    edge = handler._estimate_edge_context(signal, atr_pct=0.0, risk_params=risk)

    assert edge["estimated_round_trip_fee_bps"] == 65.0
    assert edge["net_edge_bps"] == -1.0
    assert handler._passes_cost_guard(edge) is False


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
async def test_execute_buy_blocks_symbol_that_monopolizes_official_paper(tmp_path):
    db = tmp_path / "state.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE trade_ledger (symbol TEXT, side TEXT, created_at TEXT)")
        for _ in range(3):
            conn.execute(
                "INSERT INTO trade_ledger(symbol, side, created_at) VALUES (?, ?, ?)",
                ("TRXEUR", "buy", datetime.now(timezone.utc).isoformat()),
            )
        conn.commit()

    instance = _Instance()
    instance.config.symbol = "TRXEUR"
    instance.config.paper_symbol_concentration_action = "block"
    instance._persistence = SimpleNamespace(db_path=str(db), append_audit_event=lambda **_: None)
    instance.orchestrator = SimpleNamespace(
        paper_mode=True,
        _instances={
            "trx": SimpleNamespace(config=SimpleNamespace(symbol="TRXEUR")),
            "atom": SimpleNamespace(config=SimpleNamespace(symbol="ATOMEUR")),
            "avax": SimpleNamespace(config=SimpleNamespace(symbol="AVAXEUR")),
        },
    )
    executor = _Executor()
    handler = SignalHandlerAsync(instance=instance, order_executor=executor)
    handler.validator = _Validator()
    handler._osm = _CountingOSM()
    handler._post_trade_reconcile = _noop_reconcile
    handler._opportunity_gate_applies = lambda: {"selection_applies_to_execution": False}

    signal = TradingSignal(
        type=SignalType.BUY,
        symbol="TRXEUR",
        price=0.31,
        volume=40.0,
        reason="unit concentration",
        timestamp=datetime.now(timezone.utc),
        metadata={"spread_bps": 1.0, "expected_move_bps": 220.0, "fee_bps": 10.0, "exit_fee_bps": 10.0, "slippage_bps": 2.0},
    )

    await handler._execute_buy(signal)

    assert executor.market_calls == 0
    assert executor.limit_calls == 0
    assert handler._last_decision_event["reason"] == "paper_symbol_concentration_guard"
    assert handler._last_decision_event["concentration_guard"]["recent_symbol_buys"] == 3


@pytest.mark.asyncio
async def test_execute_buy_observes_concentration_without_blocking_by_default(tmp_path):
    db = tmp_path / "state.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE trade_ledger (symbol TEXT, side TEXT, created_at TEXT)")
        for _ in range(3):
            conn.execute(
                "INSERT INTO trade_ledger(symbol, side, created_at) VALUES (?, ?, ?)",
                ("TRXEUR", "buy", datetime.now(timezone.utc).isoformat()),
            )
        conn.commit()

    instance = _Instance()
    instance.config.symbol = "TRXEUR"
    instance._persistence = SimpleNamespace(db_path=str(db), append_audit_event=lambda **_: None)
    instance.orchestrator = SimpleNamespace(
        paper_mode=True,
        _instances={
            "trx": SimpleNamespace(config=SimpleNamespace(symbol="TRXEUR")),
            "atom": SimpleNamespace(config=SimpleNamespace(symbol="ATOMEUR")),
        },
    )
    executor = _Executor()
    handler = SignalHandlerAsync(instance=instance, order_executor=executor)
    handler.validator = _Validator()
    handler._osm = _CountingOSM()
    handler._post_trade_reconcile = _noop_reconcile
    handler._opportunity_gate_applies = lambda: {"selection_applies_to_execution": False}

    signal = TradingSignal(
        type=SignalType.BUY,
        symbol="TRXEUR",
        price=0.31,
        volume=40.0,
        reason="unit concentration observe",
        timestamp=datetime.now(timezone.utc),
        metadata={"spread_bps": 1.0, "expected_move_bps": 220.0, "fee_bps": 10.0, "exit_fee_bps": 10.0, "slippage_bps": 2.0},
    )

    await handler._execute_buy(signal)

    assert executor.market_calls + executor.limit_calls == 1
    assert handler._last_decision_event["reason"] == "all_guards_passed"
    assert handler._last_decision_event["concentration_guard"]["reason"] == "symbol_buy_cap_reached"
    assert handler._last_decision_event["concentration_guard"]["action"] == "observe"


@pytest.mark.asyncio
async def test_execute_buy_can_upsize_small_paper_signal_to_opportunity_budget():
    executor = _Executor()
    osm = _CountingOSM()
    handler = SignalHandlerAsync(instance=_Instance(), order_executor=executor)
    handler.validator = _Validator()
    handler._osm = osm
    handler._kill_switch = _SafeKillSwitch()
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
async def test_buy_signal_persists_canonical_decision_before_order_and_trade():
    persistence = _TracePersistence()
    instance = _Instance()
    instance._persistence = persistence
    executor = _Executor()
    osm = _CanonicalTraceOSM(persistence, "buy_accepted")
    handler = SignalHandlerAsync(instance=instance, order_executor=executor)
    handler.validator = _Validator()
    handler._osm = osm
    handler._kill_switch = _SafeKillSwitch()
    handler._post_trade_reconcile = _noop_reconcile
    handler._opportunity_gate_applies = lambda: {"selection_applies_to_execution": False}
    handler._passes_microstructure_hard_filter = lambda _signal: True

    signal = TradingSignal(
        type=SignalType.BUY,
        symbol="BTC/EUR",
        price=100.0,
        volume=0.2,
        reason="unit canonical buy trace",
        timestamp=datetime.now(timezone.utc),
        metadata={"spread_bps": 1.0, "expected_move_bps": 200.0, "fee_bps": 10.0, "slippage_bps": 2.0},
    )

    await handler._on_signal(signal)

    decision_id = handler._last_decision_event["decision_id"]
    signal_id = signal.metadata["signal_id"]
    assert any(row.get("event_status") == "signal_received" and row.get("signal_id") == signal_id for row in persistence.decision_events)
    assert osm.new_order_calls[0]["decision_id"] == decision_id
    assert osm.new_order_calls[0]["signal_id"] == signal_id
    assert persistence.ledger_rows[0]["decision_id"] == decision_id
    assert persistence.ledger_rows[0]["signal_id"] == signal_id
    assert persistence.ledger_rows[0]["exchange_order_id"] == "buy-1"


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
async def test_execute_sell_records_realized_pnl_from_close_result(monkeypatch):
    monkeypatch.delenv("AUTOBOT_LEGACY_DIRECT_EXECUTION_ENABLED", raising=False)
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


@pytest.mark.asyncio
async def test_sell_signal_persists_canonical_decision_before_order_and_trade():
    persistence = _TracePersistence()
    instance = _SuccessfulSellInstance()
    instance._persistence = persistence
    executor = _SellExecutor()
    osm = _CanonicalTraceOSM(persistence, "sell_accepted")
    handler = SignalHandlerAsync(instance=instance, order_executor=executor)
    handler._osm = osm
    handler._kill_switch = _SafeKillSwitch()
    handler._passes_order_size_guard = lambda **_kwargs: True
    handler._post_trade_reconcile = _noop_reconcile

    signal = TradingSignal(
        type=SignalType.SELL,
        symbol="XXRPZEUR",
        price=101.5,
        volume=2.0,
        reason="unit canonical sell trace",
        timestamp=datetime.now(timezone.utc),
        metadata={},
    )

    await handler._on_signal(signal)

    decision_id = handler._last_decision_event["decision_id"]
    signal_id = signal.metadata["signal_id"]
    assert any(row.get("event_status") == "signal_received" and row.get("signal_id") == signal_id for row in persistence.decision_events)
    assert osm.new_order_calls[0]["decision_id"] == decision_id
    assert osm.new_order_calls[0]["signal_id"] == signal_id
    assert persistence.ledger_rows[0]["decision_id"] == decision_id
    assert persistence.ledger_rows[0]["signal_id"] == signal_id
    assert persistence.ledger_rows[0]["realized_pnl"] == pytest.approx(3.4)


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


def test_build_execution_plan_prefers_post_only_in_paper_when_edge_buffer_is_healthy():
    class _FakeOfi:
        def get_snapshot(self, _symbol):
            return {
                "has_book": True,
                "bid": 99.98,
                "ask": 100.02,
                "spread_bps": 4.0,
                "buy_adverse_selection_risk": 0.12,
            }

    instance = _Instance()
    instance.orchestrator = SimpleNamespace(paper_mode=True, ofi=_FakeOfi())
    handler = SignalHandlerAsync(instance=instance, order_executor=None)
    signal = TradingSignal(
        type=SignalType.BUY,
        symbol="XXBTZEUR",
        price=100.0,
        volume=0.5,
        reason="unit paper maker preference",
        timestamp=datetime.now(timezone.utc),
        metadata={"urgency": 0.2, "limit_price": 100.0},
    )

    plan = handler._build_execution_plan(
        signal,
        volume=0.5,
        edge_ctx={"net_edge_bps": 62.0, "adaptive_min_edge_bps": 50.0, "spread_bps": 4.0},
    )

    assert plan["order_type"] == "limit"
    assert plan["post_only"] is True
    assert plan["reason"] == "paper_post_only_cost_control"
    assert plan["price"] == pytest.approx(99.98)


def test_microstructure_filter_requires_valid_book_before_ofi_block():
    class _FakeOfi:
        def get_snapshot(self, _symbol):
            return {"has_book": False, "reason": "invalid_book", "bid": 100.1, "ask": 99.9}

        def is_unbalanced_against(self, _symbol, _side):
            return True

        def get_ofi_score(self, _symbol):
            return -1.0

    instance = _Instance()
    instance.orchestrator = SimpleNamespace(ofi=_FakeOfi())
    handler = SignalHandlerAsync(instance=instance, order_executor=None)
    signal = TradingSignal(
        type=SignalType.BUY,
        symbol="XXBTZEUR",
        price=100.0,
        volume=0.5,
        reason="unit invalid book",
        timestamp=datetime.now(timezone.utc),
        metadata={"spread_bps": 5.0, "expected_slippage_bps": 4.0},
    )

    assert handler._passes_microstructure_hard_filter(signal) is False
    reasons = handler._last_microstructure_reject_context["rejection_reasons"]
    assert "microstructure_book_unavailable:invalid_book" in reasons
    assert not any(str(reason).startswith("OFI_BLOCK") for reason in reasons)


def test_paper_maker_rejections_are_local_validation_not_api_failures():
    assert SignalHandlerAsync._is_local_order_validation_error("paper_maker_book_unavailable") is True
    assert SignalHandlerAsync._is_local_order_validation_error("paper_maker_adverse_selection") is True
    assert SignalHandlerAsync._is_local_order_validation_error("paper_post_only_would_take_liquidity") is True
    assert SignalHandlerAsync._is_local_order_validation_error("EAPI:Invalid nonce") is False


@pytest.mark.asyncio
async def test_on_signal_links_signal_and_decision_with_same_signal_id():
    handler = SignalHandlerAsync(instance=_Instance(), order_executor=None)
    handler._cooldown_seconds = 0
    handler._kill_switch = SimpleNamespace(tripped=False, is_globally_tripped=lambda: False)
    signal = TradingSignal(
        type=SignalType.BUY,
        symbol="XXBTZEUR",
        price=100.0,
        volume=0.5,
        reason="unit trace",
        timestamp=datetime.now(timezone.utc),
        metadata={"strategy": "grid"},
    )

    await handler._on_signal(signal)

    signal_id = signal.metadata["signal_id"]
    assert handler._last_signal_event["signal_id"] == signal_id
    assert handler._last_decision_event["signal_id"] == signal_id
    assert handler._last_decision_event["event"] == "signal_rejected"


@pytest.mark.asyncio
async def test_execute_buy_keeps_existing_trace_ids_on_rejection():
    handler = SignalHandlerAsync(instance=_Instance(), order_executor=None)
    handler._osm = _OSM()
    signal = TradingSignal(
        type=SignalType.BUY,
        symbol="XXBTZEUR",
        price=100.0,
        volume=0.5,
        reason="unit trace",
        timestamp=datetime.now(timezone.utc),
        metadata={"strategy": "grid", "signal_id": "sig-known", "decision_id": "dec-known"},
    )

    await handler._execute_buy(signal)

    assert handler._last_error_event["signal_id"] == "sig-known"
    assert handler._last_error_event["decision_id"] == "dec-known"
    assert handler._last_error_event["reason"] == "order_executor_missing"


async def _noop_reconcile():
    return None
