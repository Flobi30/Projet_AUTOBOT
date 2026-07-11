from datetime import datetime, timedelta, timezone

import pytest

from autobot.v2.contracts import (
    AlphaSignal,
    CanonicalMarketEvent,
    FeatureValue,
    LedgerEntry,
    MarketIdentity,
    ExecutionCommand,
    OrderIntent,
    RiskDecision,
    TargetPortfolio,
    contract_fingerprint,
    contract_to_dict,
)

pytestmark = pytest.mark.unit


def _market() -> MarketIdentity:
    return MarketIdentity("Kraken", "spot", "BTCZEUR", "BTC", "EUR")


def test_market_event_enforces_explicit_identity_and_point_in_time_ordering():
    event = datetime(2026, 7, 10, 12, tzinfo=timezone.utc)
    record = CanonicalMarketEvent(
        market=_market(),
        event_time=event,
        available_time=event + timedelta(seconds=1),
        ingestion_time=event + timedelta(seconds=2),
        source_snapshot_id="ohlcv_snapshot_1",
    )

    assert record.market.quote_asset == "EUR"
    assert record.ingestion_time.tzinfo == timezone.utc

    with pytest.raises(ValueError, match="available_time"):
        CanonicalMarketEvent(
            market=_market(),
            event_time=event,
            available_time=event - timedelta(seconds=1),
            ingestion_time=event,
            source_snapshot_id="bad",
        )


def test_feature_and_signal_reject_lookahead_timestamps():
    event = datetime(2026, 7, 10, 12, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="feature available_time"):
        FeatureValue(
            feature_id="atr",
            feature_version="1",
            market=_market(),
            timeframe="1h",
            event_time=event,
            available_time=event - timedelta(seconds=1),
            source_snapshot_id="snapshot",
            value=1.0,
        )

    with pytest.raises(ValueError, match="signal available_at"):
        AlphaSignal(
            strategy_id="research",
            strategy_version="1",
            signal_id="signal-1",
            market=_market(),
            direction="long",
            generated_at=event,
            available_at=event - timedelta(seconds=1),
            feature_versions={"atr": "1"},
            data_snapshot_id="snapshot",
        )


def test_target_portfolio_and_order_intent_keep_risk_boundary_explicit():
    now = datetime(2026, 7, 10, 12, tzinfo=timezone.utc)
    portfolio = TargetPortfolio(
        decision_id="decision-1",
        generated_at=now,
        target_weights={"BTCZEUR": 0.4},
        reserve_cash_weight=0.6,
    )
    assert portfolio.target_weights["BTCZEUR"] == 0.4

    intent = OrderIntent(
        decision_id="decision-1",
        strategy_id="research_strategy",
        market=_market(),
        side="buy",
        target_notional=25.0,
        created_at=now,
        data_available_at=now,
        execution_mode="shadow",
        client_order_id="client-1",
    )
    assert intent.execution_mode == "shadow"

    with pytest.raises(ValueError, match="cannot exceed"):
        TargetPortfolio(
            decision_id="bad",
            generated_at=now,
            target_weights={"BTCZEUR": 0.8},
            reserve_cash_weight=0.3,
        )


def test_risk_and_ledger_contracts_require_auditable_rejections():
    now = datetime(2026, 7, 10, 12, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="requires at least one reason"):
        RiskDecision(decision_id="decision-1", approved=False, decided_at=now)

    decision = RiskDecision(
        decision_id="decision-1",
        approved=False,
        decided_at=now,
        reasons=("spread_too_wide",),
    )
    entry = LedgerEntry(
        ledger_id="ledger-1",
        entry_type="RISK_REJECTED",
        occurred_at=now,
        strategy_id="research_strategy",
        decision_id=decision.decision_id,
        client_order_id=None,
        source="risk_manager",
        payload={"reasons": list(decision.reasons)},
    )
    assert entry.payload["reasons"] == ["spread_too_wide"]


def test_execution_command_requires_a_risk_boundary_and_contracts_are_stable():
    now = datetime(2026, 7, 10, 12, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="risk_decision_id is required"):
        ExecutionCommand(
            command_id="command-1",
            decision_id="decision-1",
            client_order_id="client-1",
            risk_decision_id="",
            issued_at=now,
            execution_mode="paper",
            approved_notional=25,
        )

    signal = AlphaSignal(
        strategy_id="research_strategy",
        strategy_version="1",
        signal_id="signal-1",
        market=_market(),
        direction="long",
        generated_at=now,
        available_at=now,
        feature_versions={"atr": "1"},
        data_snapshot_id="snapshot-1",
    )
    payload = contract_to_dict(signal)
    assert payload["generated_at"] == "2026-07-10T12:00:00+00:00"
    assert contract_fingerprint(signal) == contract_fingerprint(signal)
