from __future__ import annotations

import ast
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

import pytest

from autobot.v2.contracts import AlphaSignal, MarketIdentity
from autobot.v2.research.backtest_alpha_adapter import cost_model_fingerprint
from autobot.v2.research.canonical_microstructure_profile import (
    CanonicalMicrostructureProfileReport,
    CanonicalMicrostructureSymbolProfile,
)
from autobot.v2.research.execution_cost_model import ExecutionCostConfig
from autobot.v2.research.execution_simulator import review_net_edge_scenarios
from autobot.v2.research.microstructure_cost_evidence import (
    MicrostructureCostEvidenceError,
    derive_microstructure_cost_evidence,
    write_microstructure_cost_evidence,
)


pytestmark = pytest.mark.unit


def _market() -> MarketIdentity:
    return MarketIdentity("kraken", "spot", "BTCEUR", "BTC", "EUR")


def _profile(*, symbol: str = "BTCEUR", quote_asset: str = "EUR") -> CanonicalMicrostructureSymbolProfile:
    return CanonicalMicrostructureSymbolProfile(
        symbol=symbol,
        base_asset="BTC",
        quote_asset=quote_asset,
        sample_count=120,
        distinct_utc_hours=20,
        first_event_time="2026-07-20T00:00:00+00:00",
        last_event_time="2026-07-21T12:00:00+00:00",
        observation_span_seconds=129_600.0,
        median_spread_bps=10.0,
        p75_spread_bps=12.0,
        p95_spread_bps=18.0,
        p99_spread_bps=22.0,
        median_bid_depth_eur=1_500.0,
        median_ask_depth_eur=1_300.0,
        p95_latency_ms=55.0,
        observed_research_spread_bps=12.0,
        observed_stress_spread_bps=22.0,
        calibration_status="RESEARCH_CALIBRATION_READY",
    )


def _report(*, status: str = "RESEARCH_CALIBRATION_READY", profiles: tuple[CanonicalMicrostructureSymbolProfile, ...] | None = None) -> CanonicalMicrostructureProfileReport:
    return CanonicalMicrostructureProfileReport(
        run_id="pytest_microstructure_profile",
        generated_at="2026-07-21T12:00:00+00:00",
        source_paths=("canonical/kraken_spot_microstructure.csv",),
        source_fingerprint=sha256(b"canonical-microstructure-fixture").hexdigest(),
        raw_row_count=120,
        accepted_row_count=120,
        duplicate_row_count=0,
        rejected_row_count=0,
        status=status,
        profiles=profiles or (_profile(),),
    )


def _base_cost_config() -> ExecutionCostConfig:
    return ExecutionCostConfig(
        taker_fee_bps=10.0,
        fallback_spread_bps=8.0,
        slippage_bps=4.0,
        latency_buffer_bps=1.0,
        max_liquidity_participation=0.05,
    )


def _signal(*, cost_fingerprint: str, evidence_fingerprint: str | None = None, market: MarketIdentity | None = None) -> AlphaSignal:
    at = datetime(2026, 7, 21, 12, tzinfo=timezone.utc)
    metadata = {"cost_model_fingerprint": cost_fingerprint}
    if evidence_fingerprint is not None:
        metadata["microstructure_cost_evidence_fingerprint"] = evidence_fingerprint
    return AlphaSignal(
        strategy_id="funding_basis",
        strategy_version="v1",
        signal_id="signal-microstructure-cost-evidence",
        market=market or _market(),
        direction="long",
        generated_at=at,
        available_at=at,
        feature_versions={"basis_bps": "1"},
        data_snapshot_id="snapshot-microstructure-cost-evidence",
        expected_edge_bps=100.0,
        metadata=metadata,
    )


def test_evidence_raises_cost_floors_and_binds_all_fingerprints(tmp_path):
    evidence = derive_microstructure_cost_evidence(
        _report(),
        market=_market(),
        base_cost_config=_base_cost_config(),
        generated_at=datetime(2026, 7, 21, 12, tzinfo=timezone.utc),
    )
    json_path, markdown_path = write_microstructure_cost_evidence(evidence, tmp_path / "reports")

    assert evidence.central_cost_config.fallback_spread_bps == pytest.approx(12.0)
    assert evidence.stress_cost_config.fallback_spread_bps == pytest.approx(22.0)
    assert evidence.central_cost_model_fingerprint == cost_model_fingerprint(evidence.central_cost_config.to_dict())
    assert evidence.stress_cost_model_fingerprint == cost_model_fingerprint(evidence.stress_cost_config.to_dict())
    assert evidence.research_only is True
    assert evidence.runtime_parity_proven is False
    assert evidence.execution_eligible is False
    assert evidence.paper_capital_allowed is False
    assert evidence.live_allowed is False
    assert json_path.exists() and markdown_path.exists()
    assert "does not update global cost profiles" in markdown_path.read_text(encoding="utf-8")


def test_evidence_rejects_unready_or_wrong_market_profile():
    with pytest.raises(MicrostructureCostEvidenceError, match="profile_not_research_calibration_ready"):
        derive_microstructure_cost_evidence(
            _report(status="WAITING_FOR_MORE_DATA"),
            market=_market(),
            base_cost_config=_base_cost_config(),
        )
    with pytest.raises(MicrostructureCostEvidenceError, match="market_missing"):
        derive_microstructure_cost_evidence(
            _report(profiles=(_profile(symbol="ETHEUR"),)),
            market=_market(),
            base_cost_config=_base_cost_config(),
        )
    with pytest.raises(MicrostructureCostEvidenceError, match="explicit Kraken spot EUR"):
        derive_microstructure_cost_evidence(
            _report(),
            market=MarketIdentity("kraken", "spot", "BTCUSD", "BTC", "USD"),
            base_cost_config=_base_cost_config(),
        )


def test_scenario_gate_requires_evidence_signal_market_and_cost_model_to_match():
    evidence = derive_microstructure_cost_evidence(
        _report(),
        market=_market(),
        base_cost_config=_base_cost_config(),
    )
    ready_signal = _signal(
        cost_fingerprint=evidence.central_cost_model_fingerprint,
        evidence_fingerprint=evidence.evidence_fingerprint,
    )
    ready = review_net_edge_scenarios(
        ready_signal,
        base_cost_config=evidence.central_cost_config,
        microstructure_cost_evidence=evidence,
    )
    missing = review_net_edge_scenarios(
        _signal(cost_fingerprint=evidence.central_cost_model_fingerprint),
        base_cost_config=evidence.central_cost_config,
        microstructure_cost_evidence=evidence,
    )
    wrong_cost = review_net_edge_scenarios(
        ready_signal,
        base_cost_config=_base_cost_config(),
        microstructure_cost_evidence=evidence,
    )
    wrong_market = review_net_edge_scenarios(
        replace(ready_signal, market=MarketIdentity("kraken", "spot", "ETHEUR", "ETH", "EUR")),
        base_cost_config=evidence.central_cost_config,
        microstructure_cost_evidence=evidence,
    )

    assert ready.status == "SCENARIO_EDGE_OK"
    assert ready.microstructure_cost_evidence_fingerprint == evidence.evidence_fingerprint
    assert missing.reason == "microstructure_cost_evidence_fingerprint_missing"
    assert wrong_cost.reason == "microstructure_cost_model_fingerprint_mismatch"
    assert wrong_market.reason == "microstructure_cost_market_identity_mismatch"


def test_cost_evidence_imports_no_runtime_or_order_paths():
    root = Path(__file__).resolve().parents[2]
    tree = ast.parse((root / "src/autobot/v2/research/microstructure_cost_evidence.py").read_text(encoding="utf-8"))
    imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imports.update(node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module)
    forbidden = {
        "autobot.v2.order_router",
        "autobot.v2.signal_handler_async",
        "autobot.v2.order_executor_async",
        "autobot.v2.paper_trading",
    }
    assert imports.isdisjoint(forbidden)
