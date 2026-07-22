from __future__ import annotations

import csv
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from autobot.v2.research.funding_basis_research_adapter import (
    ADAPTER_ID,
    FundingBasisResearchConfig,
    run_funding_basis_research_smoke,
)
from autobot.v2.research.alpha_hypothesis_runner import (
    AlphaHypothesisRunnerConfig,
    build_alpha_hypothesis_runner_report,
)


pytestmark = pytest.mark.unit


def test_adapter_uses_same_quote_derivatives_context_but_calculates_net_pnl_on_spot_eur(tmp_path):
    spot_dir = _spot_data(tmp_path)
    snapshot = _derivatives_snapshot(tmp_path, status="READY")

    result = run_funding_basis_research_smoke(
        FundingBasisResearchConfig(
            run_id="pytest_funding_basis",
            spot_data_paths=(spot_dir,),
            derivatives_feature_snapshot_manifest=snapshot,
            template=_template(),
            symbols=("BTCZEUR",),
            min_funding_observations=10,
        )
    )

    assert result.adapter_id == ADAPTER_ID
    assert result.availability.available is True
    assert result.availability.futures_to_spot == {"PF_XBTUSD": "BTCZEUR"}
    assert result.metrics.trade_count > 0
    assert result.metrics.total_cost_bps > 0.0
    assert result.metrics.total_funding_carry_eur == 0.0
    assert result.metrics.net_pnl_eur <= result.metrics.gross_pnl_eur
    first = result.primary_trades[0]
    assert first.gross_pnl_eur - first.net_pnl_eur == pytest.approx(
        first.fees_eur + first.spread_cost_eur + first.slippage_eur + first.latency_cost_eur
    )
    assert first.entry_price > 0.0
    assert first.exit_price > 0.0
    assert first.funding_carry_eur == 0.0
    assert first.metadata["funding_carry_attribution"] == {
        "applicable": False,
        "funding_carry_eur": 0.0,
        "reason": "spot_only_directional_context_no_perpetual_position",
        "funding_rate_used_as_feature_only": True,
    }
    assert result.paper_capital_allowed is False
    assert result.live_allowed is False
    assert result.promotable is False
    assert all(row["status"] == "research_only" for row in result.variants)


def test_adapter_requires_feature_availability_before_signal_and_enters_on_next_spot_bar(tmp_path):
    spot_dir = _spot_data(tmp_path)
    snapshot = _derivatives_snapshot(tmp_path, status="READY", availability_delay_hours=2)

    result = run_funding_basis_research_smoke(
        FundingBasisResearchConfig(
            run_id="pytest_funding_basis_timing",
            spot_data_paths=(spot_dir,),
            derivatives_feature_snapshot_manifest=snapshot,
            template=_template(),
            symbols=("BTCZEUR",),
            min_funding_observations=10,
        )
    )

    assert result.metrics.trade_count > 0
    first = result.primary_trades[0]
    assert first.opened_at > first.signal_at
    assert datetime.fromisoformat(first.metadata["funding_available_time"]) <= first.signal_at
    assert datetime.fromisoformat(first.metadata["basis_available_time"]) <= first.signal_at
    assert first.metadata["implicit_usd_eur_price_conversion"] is False


def test_adapter_rejects_nonzero_funding_carry_for_spot_only_trade(tmp_path):
    spot_dir = _spot_data(tmp_path)
    snapshot = _derivatives_snapshot(tmp_path, status="READY")
    result = run_funding_basis_research_smoke(
        FundingBasisResearchConfig(
            run_id="pytest_funding_basis_carry",
            spot_data_paths=(spot_dir,),
            derivatives_feature_snapshot_manifest=snapshot,
            template=_template(),
            symbols=("BTCZEUR",),
            min_funding_observations=10,
        )
    )

    with pytest.raises(ValueError, match="spot-only"):
        replace(result.primary_trades[0], funding_carry_eur=0.01)


def test_adapter_preserves_waiting_status_without_simulation(tmp_path):
    spot_dir = _spot_data(tmp_path)
    snapshot = _derivatives_snapshot(
        tmp_path,
        status="WAITING_FOR_MORE_DATA",
        blockers=["BASIS_HISTORY_WAITING", "OPEN_INTEREST_HISTORY_WAITING"],
    )

    result = run_funding_basis_research_smoke(
        FundingBasisResearchConfig(
            run_id="pytest_funding_basis_waiting",
            spot_data_paths=(spot_dir,),
            derivatives_feature_snapshot_manifest=snapshot,
            template=_template(),
            symbols=("BTCZEUR",),
            min_funding_observations=10,
        )
    )

    assert result.decision == "INSUFFICIENT_DATA"
    assert result.metrics.trade_count == 0
    assert result.availability.status == "WAITING_FOR_MORE_DATA"
    assert "BASIS_HISTORY_WAITING" in result.reasons
    assert result.paper_capital_allowed is False
    assert result.live_allowed is False
    assert result.promotable is False


def test_alpha_runner_routes_funding_basis_smoke_to_the_research_only_adapter(tmp_path):
    spot_dir = _spot_data(tmp_path)
    snapshot = _derivatives_snapshot(tmp_path, status="READY")
    spot_manifest = tmp_path / "spot_features.json"
    spot_manifest.write_text(
        json.dumps(
            {
                "status": "READY",
                "parity_ok": True,
                "feature_count": 1,
                "feature_snapshot_id": "spot_features_test",
                "fingerprint": "spot-fingerprint",
                "source_snapshot_id": "spot-source",
                "source_snapshot_fingerprint": "spot-source-fingerprint",
                "feature_registry_fingerprint": "spot-registry",
                "feature_versions": {"return_1_bps": "1.0.0"},
                "ingestion_time_unknown_count": 0,
                "runtime_parity_proven": True,
            }
        ),
        encoding="utf-8",
    )

    report = build_alpha_hypothesis_runner_report(
        AlphaHypothesisRunnerConfig(
            run_id="pytest_funding_runner",
            hypothesis_id="funding_basis",
            mode="smoke",
            data_paths=(spot_dir,),
            feature_snapshot_manifest=spot_manifest,
            derivatives_feature_snapshot_manifest=snapshot,
            template_id="funding_extreme_reversion",
            symbols=("BTCZEUR",),
            max_variants=1,
            max_symbols=1,
        ),
        commit="test",
    )

    assert [gate.gate for gate in report.gates] == ["DATA_CHECK", "FAST_NET_EDGE_TEST"]
    assert report.gates[-1].metrics["adapter_id"] == ADAPTER_ID
    assert report.gates[-1].metrics["availability"]["futures_to_spot"] == {"PF_XBTUSD": "BTCZEUR"}
    assert report.paper_capital_allowed is False
    assert report.live_allowed is False
    assert report.promotable is False


def test_adapter_has_no_runtime_or_order_path_imports():
    source = Path("src/autobot/v2/research/funding_basis_research_adapter.py").read_text(encoding="utf-8")

    for forbidden in ("order_router", "paper_trading", "signal_handler", "kraken_client", "create_order"):
        assert forbidden not in source


def _template() -> dict[str, object]:
    return {
        "template_id": "funding_extreme_reversion",
        "minimum_sample_size": 30,
        "allowed_parameter_ranges": {
            "funding_percentile": [10],
            "max_hold_hours": [4],
        },
    }


def _spot_data(tmp_path: Path) -> Path:
    directory = tmp_path / "spot"
    directory.mkdir(parents=True)
    path = directory / "BTCZEUR_1h.csv"
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["timestamp", "open", "high", "low", "close", "volume", "symbol", "timeframe"],
        )
        writer.writeheader()
        price = 100.0
        for index in range(160):
            open_price = price
            close = open_price * (1.003 if index % 12 in {5, 6, 7, 8} else 1.0002)
            writer.writerow(
                {
                    "timestamp": (start + timedelta(hours=index)).isoformat(),
                    "open": f"{open_price:.8f}",
                    "high": f"{max(open_price, close) * 1.001:.8f}",
                    "low": f"{min(open_price, close) * 0.999:.8f}",
                    "close": f"{close:.8f}",
                    "volume": "1000",
                    "symbol": "BTCZEUR",
                    "timeframe": "1h",
                }
            )
            price = close
    return directory


def _derivatives_snapshot(
    tmp_path: Path,
    *,
    status: str,
    blockers: list[str] | None = None,
    availability_delay_hours: int = 0,
) -> Path:
    features = tmp_path / "features.csv"
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with features.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["feature_id", "futures_symbol", "event_time", "available_time", "value", "status"],
        )
        writer.writeheader()
        for index in range(120):
            event_time = start + timedelta(hours=index)
            available_time = event_time + timedelta(hours=availability_delay_hours)
            funding = -0.004 if index % 12 == 4 else -0.0002
            writer.writerow(
                {
                    "feature_id": "funding_rate_relative",
                    "futures_symbol": "PF_XBTUSD",
                    "event_time": event_time.isoformat(),
                    "available_time": available_time.isoformat(),
                    "value": str(funding),
                    "status": "READY",
                }
            )
            writer.writerow(
                {
                    "feature_id": "basis_bps",
                    "futures_symbol": "PF_XBTUSD",
                    "event_time": event_time.isoformat(),
                    "available_time": available_time.isoformat(),
                    "value": "-8.0",
                    "status": "READY",
                }
            )
    snapshot = tmp_path / "derivatives_snapshot.json"
    snapshot.write_text(
        json.dumps(
            {
                "snapshot_kind": "DERIVATIVES_POINT_IN_TIME",
                "status": status,
                "feature_count": 240,
                "feature_ids": ["funding_rate_relative", "basis_bps"],
                "parity_ok": True,
                "runtime_parity_proven": False,
                "blockers": blockers or [],
                "paper_capital_allowed": False,
                "live_allowed": False,
                "promotable": False,
                "basis_contract": {
                    "same_quote_required": True,
                    "accepted_confidence_status": "MARK_INDEX_SAME_QUOTE",
                    "implicit_usd_eur_conversion_allowed": False,
                },
                "market_mappings": [
                    {
                        "futures_symbol": "PF_XBTUSD",
                        "base_asset": "BTC",
                        "quote_asset": "USD",
                        "autobot_spot_symbol": "BTCZEUR",
                    }
                ],
                "files": [{"futures_symbol": "PF_XBTUSD", "csv_path": str(features)}],
            }
        ),
        encoding="utf-8",
    )
    return snapshot
