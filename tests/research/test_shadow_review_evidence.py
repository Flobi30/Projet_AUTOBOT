from __future__ import annotations

from copy import deepcopy
import ast
from hashlib import sha256
import json

import pytest

from autobot.v2.research.shadow_review_evidence import (
    ShadowReviewEvidenceError,
    parse_shadow_review_evidence,
    seal_shadow_review_evidence,
)


pytestmark = pytest.mark.unit


def _holdout() -> dict[str, object]:
    return {
        "verdict": "HOLDOUT_PASSED_RESEARCH_ONLY",
        "blockers": [],
        "trade_count": 50,
        "net_pnl_eur": 12.5,
        "provenance": _provenance("exp_research_fixture"),
        "research_only": True,
        "paper_capital_allowed": False,
        "live_allowed": False,
        "promotable": False,
    }


def _provenance(experiment_id: str) -> dict[str, object]:
    identity = {
        "schema_version": 1,
        "experiment_id": experiment_id,
        "partition_id": "holdout_fixture",
        "partition_fingerprint": "holdout-fixture-fingerprint",
        "holdout_snapshot_id": "holdout_snapshot_fixture",
        "holdout_snapshot_fingerprint": "holdout-snapshot-fixture-fingerprint",
        "source_snapshot_id": "source_snapshot_fixture",
        "source_snapshot_fingerprint": "source-snapshot-fixture-fingerprint",
        "code_commit": "fixture-commit",
        "feature_versions": {"basis_bps": "1.0.0"},
        "parameter_fingerprint": "parameters-fixture-fingerprint",
        "cost_model_fingerprint": "costs-fixture-fingerprint",
    }
    return {
        **identity,
        "fingerprint": sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
    }


def _statistical() -> dict[str, object]:
    return {
        "decision": "SHADOW_REVIEW_ELIGIBLE",
        "blockers": [],
        "shadow_review_eligible": True,
        "trade_count": 50,
        "trial_count": 9,
        "net_pnl_eur": 12.5,
        "out_of_sample_confirmed": True,
        "net_of_costs": True,
        "research_only": True,
        "paper_capital_allowed": False,
        "live_allowed": False,
        "promotable": False,
    }


def _evidence() -> dict[str, object]:
    return seal_shadow_review_evidence(
        experiment_id="exp_research_fixture",
        holdout_evaluation=_holdout(),
        statistical_gate_summary=_statistical(),
    )


def test_sealed_evidence_requires_agreeing_passed_research_only_outputs():
    parsed = parse_shadow_review_evidence(_evidence(), experiment_id="exp_research_fixture")

    assert parsed.trade_count == 50
    assert parsed.net_pnl_eur == pytest.approx(12.5)
    assert parsed.paper_capital_allowed is False
    assert parsed.live_allowed is False
    assert parsed.promotable is False


@pytest.mark.parametrize(
    ("path", "value", "message"),
    (
        (("holdout_evaluation", "verdict"), "REJECTED", "final holdout must pass"),
        (("statistical_gate_summary", "decision"), "RESEARCH_BLOCKED", "not eligible"),
        (("holdout_evaluation", "net_pnl_eur"), -1.0, "holdout net_pnl_eur"),
        (("statistical_gate_summary", "net_of_costs"), False, "costs and out-of-sample"),
        (("statistical_gate_summary", "paper_capital_allowed"), True, "cannot allow"),
    ),
)
def test_sealed_evidence_fails_closed_when_any_gate_is_weakened(path, value, message):
    payload = deepcopy(_evidence())
    payload[path[0]][path[1]] = value

    with pytest.raises(ShadowReviewEvidenceError, match=message):
        parse_shadow_review_evidence(payload, experiment_id="exp_research_fixture")


def test_sealed_evidence_rejects_mismatched_metrics_and_tampering():
    mismatched = deepcopy(_evidence())
    mismatched["statistical_gate_summary"]["trade_count"] = 49

    with pytest.raises(ShadowReviewEvidenceError, match="trade_count do not match"):
        parse_shadow_review_evidence(mismatched, experiment_id="exp_research_fixture")

    tampered = deepcopy(_evidence())
    tampered["holdout_evaluation"]["net_pnl_eur"] = 99.0
    tampered["statistical_gate_summary"]["net_pnl_eur"] = 99.0
    with pytest.raises(ShadowReviewEvidenceError, match="fingerprint"):
        parse_shadow_review_evidence(tampered, experiment_id="exp_research_fixture")


def test_shadow_review_evidence_stays_outside_runtime_execution_paths():
    from pathlib import Path

    module = Path(__file__).resolve().parents[2] / "src/autobot/v2/research/shadow_review_evidence.py"
    tree = ast.parse(module.read_text(encoding="utf-8"))
    imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imports.update(node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module)

    assert imports.isdisjoint(
        {"autobot.v2.order_router", "autobot.v2.paper_trading", "autobot.v2.signal_handler_async"}
    )
