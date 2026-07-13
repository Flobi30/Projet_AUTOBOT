from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import time

import pytest

from autobot.v2.research.funding_basis_walk_forward import (
    FundingBasisWalkForwardConfig,
    build_funding_basis_walk_forward_report,
)
from autobot.v2.research.alpha_hypothesis_runner import (
    AlphaHypothesisRunnerConfig,
    _stress_placeholder,
    _walk_forward,
    load_alpha_autonomy_policy,
)

pytestmark = pytest.mark.unit


def test_funding_basis_walk_forward_keeps_oos_trades_inside_non_overlapping_windows(tmp_path):
    spot_dir = _spot_data(tmp_path)
    snapshot = _derivatives_snapshot(tmp_path, status="READY")

    report = build_funding_basis_walk_forward_report(
        FundingBasisWalkForwardConfig(
            run_id="pytest_funding_walk_forward",
            spot_data_paths=(spot_dir,),
            derivatives_feature_snapshot_manifest=snapshot,
            template=_template(),
            symbols=("BTCZEUR",),
            folds=3,
        )
    )

    assert len(report.folds) == 3
    assert report.diagnostics["fixed_template_only"] is True
    assert report.diagnostics["test_windows_non_overlapping"] is True
    for fold in report.folds:
        assert fold.train_end == fold.test_start
        assert fold.test_end > fold.test_start
    for trade in report.oos_trades:
        matching = [
            fold
            for fold in report.folds
            if trade.opened_at >= fold.test_start and trade.closed_at <= fold.test_end
        ]
        assert len(matching) == 1
        assert trade.signal_at >= matching[0].test_start
        assert trade.opened_at > trade.signal_at
        assert trade.metadata["implicit_usd_eur_price_conversion"] is False
    assert report.paper_capital_allowed is False
    assert report.live_allowed is False
    assert report.promotable is False


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


def _derivatives_snapshot(tmp_path: Path, *, status: str) -> Path:
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
            writer.writerow(
                {
                    "feature_id": "funding_rate_relative",
                    "futures_symbol": "PF_XBTUSD",
                    "event_time": event_time.isoformat(),
                    "available_time": event_time.isoformat(),
                    "value": "-0.004" if index % 12 == 4 else "-0.0002",
                    "status": "READY",
                }
            )
            writer.writerow(
                {
                    "feature_id": "basis_bps",
                    "futures_symbol": "PF_XBTUSD",
                    "event_time": event_time.isoformat(),
                    "available_time": event_time.isoformat(),
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
                "blockers": [],
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


def test_funding_basis_walk_forward_waiting_snapshot_never_simulates(tmp_path):
    spot_dir = _spot_data(tmp_path)
    snapshot = _derivatives_snapshot(tmp_path, status="WAITING_FOR_MORE_DATA")

    report = build_funding_basis_walk_forward_report(
        FundingBasisWalkForwardConfig(
            run_id="pytest_funding_walk_forward_waiting",
            spot_data_paths=(spot_dir,),
            derivatives_feature_snapshot_manifest=snapshot,
            template=_template(),
            symbols=("BTCZEUR",),
        )
    )

    assert report.decision == "INSUFFICIENT_DATA"
    assert report.folds == ()
    assert report.oos_trades == ()
    assert report.diagnostics["simulation_not_run"] is True
    assert report.paper_capital_allowed is False


def test_alpha_runner_uses_funding_basis_walk_forward_gate_research_only(tmp_path):
    spot_dir = _spot_data(tmp_path)
    snapshot = _derivatives_snapshot(tmp_path, status="READY")
    config = AlphaHypothesisRunnerConfig(
        run_id="pytest_funding_runner_walk_forward",
        hypothesis_id="funding_basis",
        mode="walk_forward",
        data_paths=(spot_dir,),
        derivatives_feature_snapshot_manifest=snapshot,
        template_id="funding_extreme_reversion",
        symbols=("BTCZEUR",),
        max_variants=1,
        max_symbols=1,
    )

    gate = _walk_forward(
        config,
        "funding_basis",
        load_alpha_autonomy_policy(config.autonomy_policy_path),
        time.perf_counter(),
        "test",
    )

    assert gate.gate == "WALK_FORWARD"
    assert gate.status in {"KEEP_RESEARCH", "REJECTED", "INSUFFICIENT_DATA"}
    assert gate.artifacts["diagnostics"]["fixed_template_only"] is True
    assert gate.safety["paper_capital_allowed"] is False
    assert gate.safety["live_allowed"] is False


def test_alpha_runner_statistical_gate_stays_blocked_without_walk_forward_pass(tmp_path):
    spot_dir = _spot_data(tmp_path)
    snapshot = _derivatives_snapshot(tmp_path, status="READY")
    config = AlphaHypothesisRunnerConfig(
        run_id="pytest_funding_runner_statistical",
        hypothesis_id="funding_basis",
        mode="full_research",
        data_paths=(spot_dir,),
        derivatives_feature_snapshot_manifest=snapshot,
        template_id="funding_extreme_reversion",
        symbols=("BTCZEUR",),
        max_variants=1,
        max_symbols=1,
    )

    gate = _stress_placeholder(
        config,
        "funding_basis",
        load_alpha_autonomy_policy(config.autonomy_policy_path),
        time.perf_counter(),
    )

    assert gate.gate == "STRESS_MONTE_CARLO"
    assert gate.status == "REJECTED"
    assert "walk_forward_gate_not_passed" in gate.reasons
    assert gate.safety["paper_capital_allowed"] is False
    assert gate.safety["live_allowed"] is False
