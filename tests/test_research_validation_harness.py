from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from autobot.v2.research_validation_harness import (
    MarketEvent,
    ReplayLedger,
    ReplayRiskConfig,
    ResearchValidationHarness,
    SignalEvent,
    SimulatedExecutionConfig,
    SimulatedExecutionEngine,
    SimulatedOrder,
    ValidationHarnessConfig,
)
from autobot.v2.opportunity_scoring import OpportunityResult


pytestmark = pytest.mark.integration


def _event(minute: int, price: float, *, liquidity_eur: float = 10_000.0, regime: str = "range") -> MarketEvent:
    return MarketEvent(
        timestamp=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc) + timedelta(minutes=minute),
        symbol="TRXEUR",
        price=price,
        volume=1_000.0,
        liquidity_eur=liquidity_eur,
        regime=regime,
    )


def _config(tmp_path, *, run_id: str = "pytest_replay") -> ValidationHarnessConfig:
    return ValidationHarnessConfig(
        run_id=run_id,
        strategy_id="trend_momentum",
        symbol="TRXEUR",
        dataset_id="pytest_inline",
        initial_capital_eur=1_000.0,
        hypothesis="pytest replay validation",
        output_dir=tmp_path,
        risk_config=ReplayRiskConfig(
            initial_capital_eur=1_000.0,
            risk_per_trade_pct=10.0,
            min_order_eur=5.0,
            max_order_eur=100.0,
        ),
        execution_config=SimulatedExecutionConfig(
            fee_bps=10.0,
            spread_bps=10.0,
            slippage_bps=5.0,
            min_liquidity_eur=1.0,
        ),
    )


class ChronologySpyStrategy:
    strategy_id = "chronology_spy"

    def __init__(self) -> None:
        self.seen: list[datetime] = []

    def on_market_event(self, event: MarketEvent) -> list[SignalEvent]:
        self.seen.append(event.timestamp)
        return []

    def on_fill(self, fill) -> None:
        return None


class RoundTripStrategy:
    strategy_id = "round_trip"

    def __init__(self, *, sell_on_event: int = 3, edge_bps: float = 90.0) -> None:
        self.count = 0
        self.sell_on_event = sell_on_event
        self.edge_bps = edge_bps

    def on_market_event(self, event: MarketEvent) -> list[SignalEvent]:
        self.count += 1
        if self.count == 1:
            return [self._signal(event, "buy")]
        if self.count == self.sell_on_event:
            return [self._signal(event, "sell")]
        return []

    def on_fill(self, fill) -> None:
        return None

    def _signal(self, event: MarketEvent, side: str) -> SignalEvent:
        return SignalEvent(
            run_id="pytest_replay",
            strategy_id="trend_momentum",
            symbol=event.symbol,
            side=side,
            price=event.price,
            quantity=0.0,
            reason=f"pytest_{side}",
            timestamp=event.timestamp,
            metadata={"expected_move_bps": self.edge_bps, "atr_pct": 0.02},
        )


class SignalEveryTickStrategy:
    strategy_id = "signal_every_tick"

    def on_market_event(self, event: MarketEvent) -> list[SignalEvent]:
        return [
            SignalEvent(
                run_id="pytest_replay",
                strategy_id="trend_momentum",
                symbol=event.symbol,
                side="buy",
                price=event.price,
                quantity=0.0,
                reason="pytest_every_tick",
                timestamp=event.timestamp,
                metadata={"expected_move_bps": 100.0, "atr_pct": 0.02},
            )
        ]

    def on_fill(self, fill) -> None:
        return None


class RecordingScorer:
    def __init__(self) -> None:
        self.history_lengths: list[int] = []
        self.max_history_timestamps: list[datetime] = []

    def score_signal(self, **kwargs) -> OpportunityResult:
        history = list(kwargs["price_history"])
        self.history_lengths.append(len(history))
        self.max_history_timestamps.append(max(timestamp for timestamp, _price in history))
        return OpportunityResult(
            symbol=kwargs["symbol"],
            score=100.0,
            status="tradable",
            reason="score_ok",
            gross_edge_bps=100.0,
            cost_bps=0.0,
            net_edge_bps=100.0,
        )


def test_replay_sorts_market_events_chronologically(tmp_path):
    strategy = ChronologySpyStrategy()
    harness = ResearchValidationHarness(_config(tmp_path, run_id="pytest_chronology"))

    harness.run(strategy=strategy, market_events=[_event(2, 101.0), _event(0, 100.0), _event(1, 100.5)])

    assert strategy.seen == sorted(strategy.seen)


def test_replay_price_history_is_past_and_current_only(tmp_path):
    scorer = RecordingScorer()
    events = [_event(2, 102.0), _event(0, 100.0), _event(1, 101.0)]
    harness = ResearchValidationHarness(_config(tmp_path, run_id="pytest_no_lookahead"), scorer=scorer)

    harness.run(strategy=SignalEveryTickStrategy(), market_events=events, write_report=False)

    sorted_events = sorted(events, key=lambda item: item.timestamp)
    assert scorer.history_lengths == [1, 2, 3]
    assert scorer.max_history_timestamps == [event.timestamp for event in sorted_events]


def test_simulated_execution_applies_fees_spread_and_slippage():
    engine = SimulatedExecutionEngine(
        SimulatedExecutionConfig(fee_bps=10.0, spread_bps=20.0, slippage_bps=5.0, min_liquidity_eur=1.0)
    )
    event = _event(0, 100.0)
    order = SimulatedOrder(
        order_id="order-1",
        run_id="pytest",
        strategy_id="trend_momentum",
        symbol="TRXEUR",
        side="buy",
        order_type="market",
        requested_price=100.0,
        requested_quantity=1.0,
        notional_eur=100.0,
        timestamp=event.timestamp,
    )

    fill = engine.execute(order, event)

    assert fill.filled
    assert fill.execution_price > event.price
    assert fill.fee_eur > 0
    assert fill.slippage_eur > 0
    assert fill.spread_cost_eur > 0


def test_harness_generates_ledger_metrics_baselines_and_report(tmp_path):
    harness = ResearchValidationHarness(_config(tmp_path, run_id="pytest_report"))
    events = [_event(0, 100.0), _event(1, 104.0), _event(2, 110.0)]

    result = harness.run(strategy=RoundTripStrategy(sell_on_event=3), market_events=events)

    assert result.metrics.trade_count == 1
    assert result.metrics.total_fees_eur > 0
    assert result.metrics.total_slippage_eur > 0
    assert len(result.ledger) == 2
    assert {baseline.name for baseline in result.baselines} == {
        "no_trade_baseline",
        "buy_and_hold",
        "random_signal_baseline",
    }
    assert result.decision.status == "keep_testing"
    assert result.decision.live_promotion_allowed is False
    assert (tmp_path / "pytest_report.md").exists()


def test_harness_rejects_when_metrics_are_insufficient_for_promotion(tmp_path):
    harness = ResearchValidationHarness(_config(tmp_path, run_id="pytest_insufficient"))
    events = [_event(0, 100.0), _event(1, 102.0), _event(2, 101.0)]

    result = harness.run(strategy=RoundTripStrategy(sell_on_event=3), market_events=events, write_report=False)

    assert result.metrics.trade_count < result.decision.checks["min_closed_trades"]
    assert result.decision.reason == "insufficient_closed_trades"
    assert result.registry_update_proposal["live_auto_promotion_allowed"] is False
    assert result.registry_update_proposal["proposed_validation_status"] == "candidate"


def test_execution_can_reject_insufficient_liquidity():
    engine = SimulatedExecutionEngine(SimulatedExecutionConfig(min_liquidity_eur=10.0))
    event = _event(0, 100.0, liquidity_eur=20.0)
    order = SimulatedOrder(
        order_id="order-2",
        run_id="pytest",
        strategy_id="trend_momentum",
        symbol="TRXEUR",
        side="buy",
        order_type="market",
        requested_price=100.0,
        requested_quantity=1.0,
        notional_eur=100.0,
        timestamp=event.timestamp,
    )

    fill = engine.execute(order, event)

    assert not fill.filled
    assert fill.reason == "insufficient_liquidity"


def test_ledger_exports_json_and_csv(tmp_path):
    harness = ResearchValidationHarness(_config(tmp_path, run_id="pytest_exports"))
    events = [_event(0, 100.0), _event(1, 103.0), _event(2, 106.0)]

    result = harness.run(strategy=RoundTripStrategy(sell_on_event=3), market_events=events, write_report=False)
    json_path = tmp_path / "ledger.json"
    csv_path = tmp_path / "ledger.csv"
    replay_ledger = ReplayLedger("pytest_exports", "trend_momentum", 1_000.0)
    replay_ledger.entries.extend(result.ledger)
    replay_ledger.export_json(json_path)
    replay_ledger.export_csv(csv_path)

    assert json_path.exists()
    assert csv_path.exists()
    assert "position_id" in csv_path.read_text(encoding="utf-8")


def test_validation_harness_never_authorizes_live_promotion(tmp_path):
    harness = ResearchValidationHarness(_config(tmp_path, run_id="pytest_live_block"))
    events = [_event(0, 100.0), _event(1, 110.0), _event(2, 120.0)]

    result = harness.run(strategy=RoundTripStrategy(sell_on_event=3, edge_bps=200.0), market_events=events)

    assert result.decision.live_promotion_allowed is False
    assert result.registry_update_proposal["live_auto_promotion_allowed"] is False
    assert result.decision.checks["live_promotion_allowed"] is False
