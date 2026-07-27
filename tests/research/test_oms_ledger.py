from __future__ import annotations

import ast
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

import pytest

from autobot.v2.contracts import (
    ExecutionEvidence,
    FeatureSnapshotReference,
    FillEvent,
    MarketIdentity,
    OrderEvent,
    OrderIntent,
    RiskDecision,
    RiskMandateReference,
    StrategyArtifactReference,
    contract_fingerprint,
    contract_to_dict,
)
from autobot.v2.research.oms_ledger import OMSLedgerError, ShadowOMSLedger, TransactionCostAnalysis


pytestmark = pytest.mark.unit


def _risk_mandate() -> RiskMandateReference:
    return RiskMandateReference(
        mandate_id="funding_basis_oms_mandate",
        strategy_id="funding_basis",
        fingerprint="risk-mandate-fingerprint-oms-fixture",
        mode_allowed="shadow",
        capital_max_eur=0.0,
        shadow_notional_max_eur=1_000.0,
        expires_at="2026-12-31T23:59:59+00:00",
        human_approved_required_for_risk_increase=True,
    )


def _intent(*, mode: str = "shadow", notional: float = 200.0) -> OrderIntent:
    timestamp = datetime(2026, 7, 11, 12, tzinfo=timezone.utc)
    return OrderIntent(
        decision_id="decision-oms",
        strategy_id="funding_basis",
        strategy_artifact=StrategyArtifactReference(
            artifact_id="strategy_artifact_oms_fixture",
            fingerprint="artifact-fingerprint-oms-fixture",
            strategy_id="funding_basis",
            strategy_version="v1",
            code_commit="oms-fixture-commit",
            data_snapshot_id="snapshot-1",
            feature_versions={"basis_bps": "1"},
            status="SHADOW",
            feature_snapshots=(
                FeatureSnapshotReference(
                    feature_snapshot_id="features_oms_fixture",
                    fingerprint="feature-fingerprint-oms-fixture",
                    snapshot_kind="FEATURE_SNAPSHOT",
                    source_snapshot_id="snapshot-1",
                    source_snapshot_fingerprint="source-fingerprint-oms-fixture",
                feature_registry_fingerprint="registry-fingerprint-oms-fixture",
                feature_versions={"basis_bps": "1"},
                runtime_parity_proven=True,
                material_verified=True,
                bundle_content_fingerprint="bundle-content-oms-fixture",
            ),
            ),
            risk_mandate=_risk_mandate(),
        ),
        market=MarketIdentity("kraken", "spot", "BTCEUR", "BTC", "EUR"),
        side="buy",
        target_notional=notional,
        created_at=timestamp,
        data_available_at=timestamp,
        execution_mode=mode,
        client_order_id=f"oms-{mode}-{notional}",
    )


def _acknowledge(ledger: ShadowOMSLedger, intent: OrderIntent) -> None:
    ledger.record_risk_decision(intent, _risk_decision(intent))
    at = intent.created_at
    assert ledger.record_order_event(OrderEvent(intent.client_order_id, "CREATED", at))
    assert ledger.record_order_event(OrderEvent(intent.client_order_id, "SUBMITTED", at + timedelta(seconds=1)))
    assert ledger.record_order_event(OrderEvent(intent.client_order_id, "ACKNOWLEDGED", at + timedelta(seconds=2)))


def _costs() -> dict[str, float]:
    return {"fee_eur": 0.16, "spread_cost_eur": 0.04, "slippage_eur": 0.05, "latency_cost_eur": 0.01}


def _risk_decision(
    intent: OrderIntent,
    *,
    approved: bool = True,
    decision_id: str | None = None,
    decided_at: datetime | None = None,
) -> RiskDecision:
    return RiskDecision(
        decision_id=decision_id or intent.decision_id,
        approved=approved,
        decided_at=decided_at or intent.created_at,
        reasons=() if approved else ("fixture_risk_rejected",),
    )


def _perpetual_market() -> MarketIdentity:
    return MarketIdentity("kraken", "perpetual", "PF_XBTUSD", "BTC", "USD")


def _execution_evidence(
    intent: OrderIntent,
    *,
    risk_decision: RiskDecision | None = None,
    market: MarketIdentity | None = None,
    funding_cost_status: str | None = None,
    funding_cost_eur: float | None = None,
) -> ExecutionEvidence:
    evidence_market = market or intent.market
    observed_at = intent.created_at + timedelta(seconds=1)
    selected_risk = risk_decision or _risk_decision(intent)
    funding_status = funding_cost_status or (
        "NOT_APPLICABLE" if evidence_market.market_type == "spot" else "UNAVAILABLE"
    )
    return ExecutionEvidence(
        market=evidence_market,
        reference_price=100.0,
        arrival_price=100.0,
        bid=99.95,
        ask=100.05,
        event_time=observed_at,
        available_time=observed_at,
        ingestion_time=observed_at,
        source_snapshot_id="oms-shadow-snapshot-fixture",
        source_fingerprint=sha256(b"oms-shadow-source").hexdigest(),
        market_snapshot_fingerprint=sha256(b"oms-shadow-snapshot").hexdigest(),
        market_snapshot_sequence_fingerprint=sha256(b"oms-shadow-sequence").hexdigest(),
        cost_model_fingerprint=sha256(b"oms-shadow-cost-model").hexdigest(),
        scenario="central",
        intent_fingerprint=contract_fingerprint(intent),
        risk_decision_id=selected_risk.risk_decision_id,
        market_rules_fingerprint=None,
        market_rules_status="UNAVAILABLE",
        fee_eur=0.16,
        spread_cost_eur=0.04,
        slippage_eur=0.05,
        latency_cost_eur=0.01,
        funding_cost_eur=funding_cost_eur,
        funding_cost_status=funding_status,
    )


def test_oms_ledger_handles_partial_fill_duplicate_and_restart_reconstruction(tmp_path):
    path = tmp_path / "oms.sqlite3"
    ledger = ShadowOMSLedger(path)
    intent = _intent()
    assert ledger.register_intent(intent)
    _acknowledge(ledger, intent)

    first = FillEvent(intent.client_order_id, "fill-1", intent.created_at + timedelta(seconds=3), 1.0, 100.0, 0.16)
    second = FillEvent(intent.client_order_id, "fill-2", intent.created_at + timedelta(seconds=4), 1.0, 100.0, 0.16)
    assert ledger.record_fill(first, costs=_costs())
    assert ledger.record_fill(first, costs=_costs()) is False
    assert ledger.record_fill(second, costs=_costs())

    restarted = ShadowOMSLedger(path)
    positions = restarted.reconstruct_positions()
    assert len(positions) == 1
    assert positions[0].market.symbol == "BTCEUR"
    assert positions[0].quantity == pytest.approx(2.0)
    assert restarted.reconcile(observed_positions={"BTCEUR": 2.0}, observed_open_orders=()).status == "RECONCILED"


def test_oms_ledger_blocks_invalid_lifecycle_and_reconciliation_mismatch(tmp_path):
    ledger = ShadowOMSLedger(tmp_path / "oms.sqlite3")
    intent = _intent()
    assert ledger.register_intent(intent)
    assert ledger.record_risk_decision(intent, _risk_decision(intent))
    fill = FillEvent(intent.client_order_id, "fill-invalid", intent.created_at, 1.0, 100.0, 0.16)
    with pytest.raises(OMSLedgerError, match="fill requires"):
        ledger.record_fill(fill, costs=_costs())
    _acknowledge(ledger, intent)
    assert ledger.record_fill(fill, costs=_costs())
    report = ledger.reconcile(observed_positions={"BTCEUR": 0.0}, observed_open_orders=())

    assert report.status == "RECONCILIATION_REQUIRED"
    assert report.trading_halted is True
    assert "position_mismatch:BTCEUR" in report.reasons
    assert "open_order_mismatch" in report.reasons


def test_oms_ledger_recovers_unknown_order_and_reconstructs_cash_and_realized_pnl(tmp_path):
    ledger = ShadowOMSLedger(tmp_path / "oms.sqlite3")
    buy = _intent(notional=100.0)
    sell = replace(
        buy,
        decision_id="decision-oms-sell",
        side="sell",
        target_notional=110.0,
        client_order_id="oms-shadow-sell-110",
    )

    assert ledger.register_intent(buy)
    assert ledger.record_risk_decision(buy, _risk_decision(buy))
    created_at = buy.created_at
    assert ledger.record_order_event(OrderEvent(buy.client_order_id, "CREATED", created_at))
    assert ledger.record_order_event(OrderEvent(buy.client_order_id, "SUBMITTED", created_at + timedelta(seconds=1)))
    unknown = OrderEvent(buy.client_order_id, "UNKNOWN", created_at + timedelta(seconds=2), reason="ack_timeout")
    assert ledger.record_order_event(unknown)
    assert ledger.record_order_event(unknown) is False
    assert ledger.record_order_event(OrderEvent(buy.client_order_id, "ACKNOWLEDGED", created_at + timedelta(seconds=3)))
    assert ledger.record_fill(
        FillEvent(buy.client_order_id, "fill-buy", created_at + timedelta(seconds=4), 1.0, 100.0, 0.16),
        costs=_costs(),
    )

    assert ledger.register_intent(sell)
    assert ledger.record_risk_decision(sell, _risk_decision(sell))
    _acknowledge(ledger, sell)
    assert ledger.record_fill(
        FillEvent(sell.client_order_id, "fill-sell", created_at + timedelta(seconds=5), 1.0, 110.0, 0.16),
        costs=_costs(),
    )

    accounting = ledger.reconstruct_accounting()
    assert accounting.positions == ()
    assert accounting.cash_flow_by_quote_asset == {"EUR": pytest.approx(9.48)}
    assert accounting.realized_pnl_by_quote_asset == {"EUR": pytest.approx(9.48)}
    assert accounting.cost_completeness == "INCOMPLETE"
    assert accounting.incomplete_cost_fill_ids == ("fill-buy", "fill-sell")

    reconciled = ledger.reconcile(
        observed_positions={},
        observed_open_orders=(),
        baseline_cash_by_quote_asset={"EUR": 1_000.0},
        observed_cash_by_quote_asset={"EUR": 1_009.48},
    )
    assert reconciled.status == "RECONCILED"
    assert reconciled.expected_cash_balances == {"EUR": pytest.approx(1_009.48)}
    assert reconciled.realized_pnl_by_quote_asset == {"EUR": pytest.approx(9.48)}

    mismatched = ledger.reconcile(
        observed_positions={},
        observed_open_orders=(),
        baseline_cash_by_quote_asset={"EUR": 1_000.0},
        observed_cash_by_quote_asset={"EUR": 1_000.0},
    )
    assert mismatched.status == "RECONCILIATION_REQUIRED"
    assert mismatched.trading_halted is True
    assert "cash_balance_mismatch:EUR" in mismatched.reasons


def test_tca_requires_cost_evidence_and_remains_shadow_only(tmp_path):
    ledger = ShadowOMSLedger(tmp_path / "oms.sqlite3")
    intent = _intent(notional=100.0)
    assert ledger.register_intent(intent)
    tca = TransactionCostAnalysis(
        client_order_id=intent.client_order_id,
        fill_id="fill-tca",
        side="buy",
        signal_price=100.0,
        decision_price=100.1,
        arrival_price=100.2,
        fill_price=100.5,
        fee_eur=0.16,
        spread_cost_eur=0.04,
        slippage_eur=0.05,
        latency_cost_eur=0.01,
    )

    assert tca.implementation_shortfall_bps == pytest.approx(50.0)
    assert tca.total_cost_eur == pytest.approx(0.26)
    with pytest.raises(OMSLedgerError, match="matching approved risk decision"):
        ledger.record_tca(tca)
    assert ledger.record_risk_decision(intent, _risk_decision(intent))
    with pytest.raises(OMSLedgerError, match="recorded matching fill"):
        ledger.record_tca(tca)
    with pytest.raises(OMSLedgerError, match="fee evidence"):
        ledger.record_fill(
            FillEvent(intent.client_order_id, "fill-fee-mismatch", intent.created_at, 1.0, 100.0, 0.20),
            costs=_costs(),
        )
    at = intent.created_at
    assert ledger.record_order_event(OrderEvent(intent.client_order_id, "CREATED", at))
    assert ledger.record_order_event(OrderEvent(intent.client_order_id, "SUBMITTED", at + timedelta(seconds=1)))
    assert ledger.record_order_event(OrderEvent(intent.client_order_id, "ACKNOWLEDGED", at + timedelta(seconds=2)))
    assert ledger.record_fill(
        FillEvent(intent.client_order_id, "fill-tca", at + timedelta(seconds=3), 1.0, 100.5, 0.16),
        costs=_costs(),
    )
    assert ledger.record_tca(tca)
    assert ledger.record_tca(tca) is False
    with pytest.raises(OMSLedgerError, match="fill price"):
        ledger.record_tca(replace(tca, fill_price=100.6))
    with sqlite3.connect(tmp_path / "oms.sqlite3") as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("DELETE FROM oms_tca_fill_bindings")
    with pytest.raises(OMSLedgerError, match="shadow intents only"):
        ledger.register_intent(_intent(mode="paper"))


def test_evidence_bound_fill_is_append_only_and_does_not_double_debit_price_impact(tmp_path):
    path = tmp_path / "oms.sqlite3"
    ledger = ShadowOMSLedger(path)
    intent = _intent(notional=100.0)
    evidence = _execution_evidence(intent)
    fill = FillEvent(
        intent.client_order_id,
        "fill-evidence-bound",
        intent.created_at + timedelta(seconds=3),
        1.0,
        100.0,
        0.16,
        execution_evidence=evidence,
    )

    assert ledger.register_intent(intent)
    _acknowledge(ledger, intent)
    assert ledger.record_fill(fill, costs=_costs())
    with sqlite3.connect(path) as connection:
        stored = connection.execute(
            "SELECT fill_json FROM oms_fill_events WHERE fill_id = ?", (fill.fill_id,)
        ).fetchone()
    assert stored is not None
    assert json.loads(str(stored[0])) == contract_to_dict(fill)

    accounting = ShadowOMSLedger(path).reconstruct_accounting()
    assert accounting.positions[0].average_entry_price == pytest.approx(100.16)
    assert accounting.cash_flow_by_quote_asset == {"EUR": pytest.approx(-100.16)}
    assert accounting.cost_completeness == "COMPLETE"
    assert accounting.incomplete_cost_fill_ids == ()


def test_evidence_bound_fill_rejects_mismatched_intent_risk_and_costs(tmp_path):
    ledger = ShadowOMSLedger(tmp_path / "oms.sqlite3")
    intent = _intent(notional=100.0)
    assert ledger.register_intent(intent)
    _acknowledge(ledger, intent)
    occurrence = intent.created_at + timedelta(seconds=3)

    bad_intent = replace(_execution_evidence(intent), intent_fingerprint=sha256(b"different-intent").hexdigest())
    with pytest.raises(OMSLedgerError, match="intent fingerprint"):
        ledger.record_fill(
            FillEvent(intent.client_order_id, "fill-bad-intent", occurrence, 1.0, 100.0, 0.16, execution_evidence=bad_intent),
            costs=_costs(),
        )

    bad_market = _execution_evidence(intent, market=_perpetual_market())
    with pytest.raises(OMSLedgerError, match="market does not match"):
        ledger.record_fill(
            FillEvent(intent.client_order_id, "fill-bad-market", occurrence, 1.0, 100.0, 0.16, execution_evidence=bad_market),
            costs=_costs(),
        )

    bad_risk = replace(_execution_evidence(intent), risk_decision_id="risk_unbound")
    with pytest.raises(OMSLedgerError, match="risk decision"):
        ledger.record_fill(
            FillEvent(intent.client_order_id, "fill-bad-risk", occurrence, 1.0, 100.0, 0.16, execution_evidence=bad_risk),
            costs=_costs(),
        )

    bad_cost = replace(_execution_evidence(intent), spread_cost_eur=0.06)
    with pytest.raises(OMSLedgerError, match="spread_cost_eur"):
        ledger.record_fill(
            FillEvent(intent.client_order_id, "fill-bad-cost", occurrence, 1.0, 100.0, 0.16, execution_evidence=bad_cost),
            costs=_costs(),
        )


def test_unavailable_derivative_funding_blocks_tca_and_marks_accounting_incomplete(tmp_path):
    ledger = ShadowOMSLedger(tmp_path / "oms.sqlite3")
    intent = replace(
        _intent(notional=100.0),
        market=_perpetual_market(),
        client_order_id="oms-shadow-perpetual-100",
    )
    fill = FillEvent(
        intent.client_order_id,
        "fill-derivative-funding-unavailable",
        intent.created_at + timedelta(seconds=3),
        1.0,
        100.0,
        0.16,
        execution_evidence=_execution_evidence(intent, funding_cost_status="UNAVAILABLE"),
    )
    assert ledger.register_intent(intent)
    _acknowledge(ledger, intent)
    assert ledger.record_fill(fill, costs=_costs())

    tca = TransactionCostAnalysis(
        client_order_id=intent.client_order_id,
        fill_id=fill.fill_id,
        side="buy",
        signal_price=100.0,
        decision_price=100.0,
        arrival_price=100.0,
        fill_price=100.0,
        fee_eur=0.16,
        spread_cost_eur=0.04,
        slippage_eur=0.05,
        latency_cost_eur=0.01,
    )
    with pytest.raises(OMSLedgerError, match="unavailable funding"):
        ledger.record_tca(tca)

    accounting = ledger.reconstruct_accounting()
    assert accounting.cost_completeness == "INCOMPLETE"
    assert accounting.incomplete_cost_fill_ids == (fill.fill_id,)


def test_oms_ledger_is_append_only_and_does_not_import_runtime_paths(tmp_path):
    path = tmp_path / "oms.sqlite3"
    ledger = ShadowOMSLedger(path)
    intent = _intent()
    ledger.register_intent(intent)
    ledger.record_risk_decision(intent, _risk_decision(intent))
    with sqlite3.connect(path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("DELETE FROM oms_intents")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("DELETE FROM oms_risk_decisions")

    root = Path(__file__).resolve().parents[2]
    tree = ast.parse((root / "src/autobot/v2/research/oms_ledger.py").read_text(encoding="utf-8"))
    forbidden = {"autobot.v2.order_router", "autobot.v2.signal_handler_async", "autobot.v2.paper_trading"}
    imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imports.update(node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module)
    assert imports.isdisjoint(forbidden)


def test_oms_ledger_requires_one_matching_approved_risk_decision_before_order_evidence(tmp_path):
    ledger = ShadowOMSLedger(tmp_path / "oms.sqlite3")
    intent = _intent()
    assert ledger.register_intent(intent)

    with pytest.raises(OMSLedgerError, match="matching approved risk decision"):
        ledger.record_order_event(OrderEvent(intent.client_order_id, "CREATED", intent.created_at))
    with pytest.raises(OMSLedgerError, match="approved risk decisions only"):
        ledger.record_risk_decision(intent, _risk_decision(intent, approved=False))
    with pytest.raises(OMSLedgerError, match="must match intent decision_id"):
        ledger.record_risk_decision(intent, _risk_decision(intent, decision_id="other-decision"))

    decision = _risk_decision(intent)
    assert ledger.record_risk_decision(intent, decision)
    assert ledger.record_risk_decision(intent, decision) is False
    with pytest.raises(OMSLedgerError, match="immutable approved risk decision"):
        ledger.record_risk_decision(
            intent,
            _risk_decision(intent, decided_at=intent.created_at + timedelta(seconds=1)),
        )
    assert ledger.record_order_event(OrderEvent(intent.client_order_id, "CREATED", intent.created_at))


def test_oms_ledger_rejects_order_event_when_risk_decision_is_future_dated(tmp_path):
    ledger = ShadowOMSLedger(tmp_path / "oms.sqlite3")
    intent = _intent()
    assert ledger.register_intent(intent)
    assert ledger.record_risk_decision(
        intent,
        _risk_decision(intent, decided_at=intent.created_at + timedelta(seconds=1)),
    )

    with pytest.raises(OMSLedgerError, match="risk decision must be recorded before order event"):
        ledger.record_order_event(OrderEvent(intent.client_order_id, "CREATED", intent.created_at))
