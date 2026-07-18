from __future__ import annotations

import ast
import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from autobot.v2.research.holdout_evaluator import (
    BaselineOutcome,
    ClosedResearchTrade,
    HoldoutEvaluationConfig,
    HoldoutEvaluatorError,
    HoldoutProvenance,
    VERDICT_INSUFFICIENT_DATA,
    VERDICT_PASSED,
    VERDICT_REJECTED,
    evaluate_sealed_holdout,
)
from autobot.v2.research.holdout_partition import HoldoutPartitionConfig, materialize_holdout_partition


pytestmark = pytest.mark.unit


def test_valid_sealed_holdout_result_is_deterministic_and_research_only(tmp_path):
    partition = _partition(tmp_path)
    result = evaluate_sealed_holdout(
        partition=partition,
        provenance=_provenance(partition),
        closed_trades=_trades(),
        baselines=_baselines(),
        config=HoldoutEvaluationConfig(min_closed_trades=6, max_positive_pnl_concentration=0.75),
    )

    assert result.verdict == VERDICT_PASSED
    assert result.net_pnl_eur == pytest.approx(6.0)
    assert result.paper_capital_allowed is False
    assert result.live_allowed is False
    assert result.promotable is False
    assert result.concentration["symbol"]["status"] == "ASSESSED"
    assert result.to_dict()["baseline_outcomes"]["no_trade"]["net_pnl_eur"] == 0.0


def test_missing_required_baseline_fails_closed_with_a_rejected_artifact(tmp_path):
    partition = _partition(tmp_path)
    result = evaluate_sealed_holdout(
        partition=partition,
        provenance=_provenance(partition),
        closed_trades=_trades(),
        baselines=_baselines()[:-1],
        config=HoldoutEvaluationConfig(min_closed_trades=6, max_positive_pnl_concentration=0.75),
    )

    assert result.verdict == VERDICT_REJECTED
    assert "required_baseline_missing:placebo" in result.blockers


def test_malformed_provenance_cannot_be_used_for_a_sealed_partition(tmp_path):
    partition = _partition(tmp_path)
    valid = _provenance(partition)
    with pytest.raises(HoldoutEvaluatorError, match="fingerprint does not match"):
        HoldoutProvenance(
            **{**valid.__dict__, "partition_id": "another_partition", "fingerprint": valid.fingerprint}
        )


def test_insufficient_closed_holdout_data_is_not_presented_as_a_pass(tmp_path):
    partition = _partition(tmp_path)
    result = evaluate_sealed_holdout(
        partition=partition,
        provenance=_provenance(partition),
        closed_trades=_trades()[:2],
        baselines=_baselines(),
        config=HoldoutEvaluationConfig(min_closed_trades=6),
    )

    assert result.verdict == VERDICT_INSUFFICIENT_DATA
    assert "insufficient_closed_trade_count" in result.blockers


def test_symbol_concentration_rejects_evidence_even_when_aggregate_pnl_is_positive(tmp_path):
    partition = _partition(tmp_path)
    concentrated = tuple(
        ClosedResearchTrade(f"trade-{index}", 1.0, "BTCEUR" if index < 5 else "ETHEUR", "2026-07", "trend")
        for index in range(6)
    )
    result = evaluate_sealed_holdout(
        partition=partition,
        provenance=_provenance(partition),
        closed_trades=concentrated,
        baselines=_baselines(),
        config=HoldoutEvaluationConfig(min_closed_trades=6, max_positive_pnl_concentration=0.70),
    )

    assert result.verdict == VERDICT_REJECTED
    assert "concentration_symbol_above_0.7000" in result.blockers


def test_missing_concentration_metadata_fails_closed(tmp_path):
    partition = _partition(tmp_path)
    incomplete = tuple(
        ClosedResearchTrade(
            f"trade-{index}",
            1.0,
            "BTCEUR" if index else None,
            "2026-07",
            "trend",
        )
        for index in range(6)
    )
    result = evaluate_sealed_holdout(
        partition=partition,
        provenance=_provenance(partition),
        closed_trades=incomplete,
        baselines=_baselines(),
        config=HoldoutEvaluationConfig(min_closed_trades=6),
    )

    assert result.verdict == VERDICT_REJECTED
    assert "concentration_symbol_metadata_missing" in result.blockers


def test_duplicate_trade_identity_is_rejected(tmp_path):
    partition = _partition(tmp_path)
    with pytest.raises(HoldoutEvaluatorError, match="trade_ids must be unique"):
        evaluate_sealed_holdout(
            partition=partition,
            provenance=_provenance(partition),
            closed_trades=(
                ClosedResearchTrade("same", 1.0),
                ClosedResearchTrade("same", 1.0),
            ),
            baselines=_baselines(),
        )


def test_evaluator_remains_isolated_from_execution_paper_live_and_kraken_modules():
    root = Path(__file__).resolve().parents[2]
    tree = ast.parse((root / "src/autobot/v2/research/holdout_evaluator.py").read_text(encoding="utf-8"))
    forbidden = {
        "autobot.v2.order_router",
        "autobot.v2.paper_trading",
        "autobot.v2.signal_handler_async",
        "autobot.v2.kraken_client",
        "autobot.v2.kraken_service",
    }
    imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imports.update(node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module)

    assert imports.isdisjoint(forbidden)


def _provenance(partition):
    return HoldoutProvenance.from_partition(
        partition,
        experiment_id="exp_holdout_fixture",
        code_commit="fixture-commit",
        feature_versions={"momentum_20": "1.0.0", "funding_z": "1.0.0"},
        parameter_fingerprint="parameters-fixture",
        cost_model_fingerprint="costs-fixture",
    )


def _trades():
    return (
        ClosedResearchTrade("trade-1", 1.0, "BTCEUR", "2026-06", "trend"),
        ClosedResearchTrade("trade-2", 1.0, "ETHEUR", "2026-06", "trend"),
        ClosedResearchTrade("trade-3", 1.0, "SOLEUR", "2026-06", "range"),
        ClosedResearchTrade("trade-4", 1.0, "BTCEUR", "2026-07", "range"),
        ClosedResearchTrade("trade-5", 1.0, "ETHEUR", "2026-07", "trend"),
        ClosedResearchTrade("trade-6", 1.0, "SOLEUR", "2026-07", "range"),
    )


def _baselines():
    return (
        BaselineOutcome("no_trade", 0.0, 0),
        BaselineOutcome("buy_and_hold", 1.0, 1),
        BaselineOutcome("placebo", 0.5, 6),
    )


def _partition(tmp_path):
    source = tmp_path / "canonical.csv"
    fields = ("event_time", "available_time", "ingestion_time", "symbol", "close")
    origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index in range(8):
            event = origin + timedelta(hours=index + 1)
            writer.writerow(
                {
                    "event_time": event.isoformat(),
                    "available_time": event.isoformat(),
                    "ingestion_time": event.isoformat(),
                    "symbol": "BTCEUR",
                    "close": "100",
                }
            )
    manifest = tmp_path / "canonical.json"
    manifest.write_text(
        json.dumps(
            {
                "snapshot_id": "fixture_snapshot",
                "fingerprint": "fixture-source-fingerprint",
                "market_type": "spot",
                "files": [{"csv_path": str(source)}],
            }
        ),
        encoding="utf-8",
    )
    return materialize_holdout_partition(
        HoldoutPartitionConfig(
            run_id="pytest_holdout_evaluator",
            source_snapshot_manifest=manifest,
            holdout_start_at=origin + timedelta(hours=4),
            output_dir=tmp_path / "partitions",
        )
    )
