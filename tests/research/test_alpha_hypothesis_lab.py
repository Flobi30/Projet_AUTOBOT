import json

import pytest

from autobot.v2.research.alpha_hypothesis_lab import (
    AlphaHypothesisError,
    CANONICAL_RESEARCH_STAGES,
    default_pipeline_payload,
    evaluate_research_gate,
    load_alpha_hypotheses,
    next_research_stage,
    normalize_research_stage,
    validate_alpha_hypotheses,
)


pytestmark = pytest.mark.unit


def test_alpha_hypotheses_registry_is_research_only():
    payload = load_alpha_hypotheses("docs/research/alpha_hypotheses.json")

    assert payload["research_only"] is True
    assert payload["paper_capital_allowed"] is False
    assert payload["live_allowed"] is False
    assert payload["auto_promotion_allowed"] is False
    assert len(payload["hypotheses"]) == 5
    assert {item["id"] for item in payload["hypotheses"]} == {
        "funding_basis",
        "liquidation_cascade",
        "volatility_breakout",
        "cross_momentum",
        "long_trend",
    }
    for hypothesis in payload["hypotheses"]:
        assert hypothesis["promotable"] is False
        assert hypothesis["paper_capital_allowed"] is False
        assert hypothesis["live_allowed"] is False


def test_alpha_hypothesis_validation_rejects_live_or_paper_enabled():
    payload = load_alpha_hypotheses("docs/research/alpha_hypotheses.json")
    bad = json.loads(json.dumps(payload))
    bad["hypotheses"][0]["paper_capital_allowed"] = True

    with pytest.raises(AlphaHypothesisError, match="cannot allow paper capital or live"):
        validate_alpha_hypotheses(bad)


def test_alpha_hypothesis_validation_rejects_missing_required_field():
    payload = load_alpha_hypotheses("docs/research/alpha_hypotheses.json")
    bad = json.loads(json.dumps(payload))
    del bad["hypotheses"][0]["kill_rules"]

    with pytest.raises(AlphaHypothesisError, match="missing fields"):
        validate_alpha_hypotheses(bad)


def test_default_pipeline_is_non_promotable():
    pipeline = default_pipeline_payload()

    assert [step["name"] for step in pipeline] == [
        "data_check",
        "quick_net_test",
        "walk_forward",
        "monte_carlo_stress",
        "shadow_observation",
    ]
    assert all(step["promotable"] is False for step in pipeline)
    assert all(step["paper_capital_allowed"] is False for step in pipeline)
    assert all(step["live_allowed"] is False for step in pipeline)


def test_canonical_research_stages_normalize_legacy_aliases_and_enforce_order():
    assert CANONICAL_RESEARCH_STAGES == (
        "DATA_CHECK",
        "NET_SMOKE",
        "WALK_FORWARD",
        "STRESS_MONTE_CARLO",
        "SHADOW_REVIEW",
    )
    assert normalize_research_stage("quick_net_test") == "NET_SMOKE"
    assert normalize_research_stage("FAST_NET_EDGE_TEST") == "NET_SMOKE"
    assert next_research_stage(None) == "DATA_CHECK"
    assert next_research_stage("NET_SMOKE") == "WALK_FORWARD"
    with pytest.raises(AlphaHypothesisError, match="pipeline is complete"):
        next_research_stage("SHADOW_REVIEW")


def test_research_gate_blocks_missing_costs_and_weak_metrics():
    result = evaluate_research_gate(
        current_step="quick_net_test",
        metrics={
            "trade_count": 12,
            "profit_factor_net": 0.95,
            "expectancy_net": -0.01,
            "max_drawdown_pct": 4.0,
            "fees_present": False,
            "slippage_present": False,
            "baseline_present": False,
        },
    )

    assert result["passed"] is False
    assert result["promotable"] is False
    assert result["paper_capital_allowed"] is False
    assert result["live_allowed"] is False
    assert "sample_size_insufficient" in result["reasons"]
    assert "fees_missing" in result["reasons"]
    assert "slippage_missing" in result["reasons"]
    assert "baseline_missing" in result["reasons"]


def test_research_gate_can_pass_but_still_never_promotes():
    result = evaluate_research_gate(
        current_step="walk_forward",
        metrics={
            "trade_count": 120,
            "profit_factor_net": 1.4,
            "expectancy_net": 0.12,
            "max_drawdown_pct": 6.0,
            "fees_present": True,
            "slippage_present": True,
            "baseline_present": True,
        },
    )

    assert result["passed"] is True
    assert result["reasons"] == []
    assert result["promotable"] is False
    assert result["paper_capital_allowed"] is False
    assert result["live_allowed"] is False
