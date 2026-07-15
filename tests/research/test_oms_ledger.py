from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3

import pytest

from autobot.v2.contracts import (
    FeatureSnapshotReference,
    FillEvent,
    MarketIdentity,
    OrderEvent,
    OrderIntent,
    RiskMandateReference,
    StrategyArtifactReference,
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
    at = intent.created_at
    assert ledger.record_order_event(OrderEvent(intent.client_order_id, "CREATED", at))
    assert ledger.record_order_event(OrderEvent(intent.client_order_id, "SUBMITTED", at + timedelta(seconds=1)))
    assert ledger.record_order_event(OrderEvent(intent.client_order_id, "ACKNOWLEDGED", at + timedelta(seconds=2)))


def _costs() -> dict[str, float]:
    return {"fee_eur": 0.16, "spread_cost_eur": 0.04, "slippage_eur": 0.05, "latency_cost_eur": 0.01}


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


def test_tca_requires_cost_evidence_and_remains_shadow_only(tmp_path):
    ledger = ShadowOMSLedger(tmp_path / "oms.sqlite3")
    intent = _intent(notional=100.0)
    assert ledger.register_intent(intent)
    tca = TransactionCostAnalysis(
        client_order_id=intent.client_order_id,
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
    assert ledger.record_tca(tca)
    assert ledger.record_tca(tca) is False
    with pytest.raises(OMSLedgerError, match="shadow intents only"):
        ledger.register_intent(_intent(mode="paper"))


def test_oms_ledger_is_append_only_and_does_not_import_runtime_paths(tmp_path):
    path = tmp_path / "oms.sqlite3"
    ledger = ShadowOMSLedger(path)
    intent = _intent()
    ledger.register_intent(intent)
    with sqlite3.connect(path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("DELETE FROM oms_intents")

    root = Path(__file__).resolve().parents[2]
    tree = ast.parse((root / "src/autobot/v2/research/oms_ledger.py").read_text(encoding="utf-8"))
    forbidden = {"autobot.v2.order_router", "autobot.v2.signal_handler_async", "autobot.v2.paper_trading"}
    imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imports.update(node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module)
    assert imports.isdisjoint(forbidden)
