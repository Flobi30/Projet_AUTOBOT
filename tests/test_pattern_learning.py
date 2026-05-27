import pytest

from autobot.v2.pattern_learning import PatternLearningConfig, PatternLearningEngine, extract_pattern_features


def _outcome(
    *,
    symbol="TRXEUR",
    engine="trend_momentum",
    net=55.0,
    gross=75.0,
    label="missed_profit",
    barrier="take_profit",
    source="decision_learning_triple_barrier",
    regime="trend",
    reason="opportunity_selection",
):
    return {
        "symbol": symbol,
        "engine": engine,
        "strategy": "grid",
        "rejection_reason": reason,
        "gross_return_bps": gross,
        "estimated_cost_bps": 16.0,
        "net_return_bps": net,
        "horizon_minutes": 60,
        "outcome_label": label,
        "source": source,
        "payload": {
            "barrier_touched": barrier,
            "decision_payload": {
                "atr_pct": 0.004,
                "opportunity": {
                    "status": "tradable",
                    "reason": "score_ok",
                    "spread_bps": 3.0,
                    "regime_context": {"regime": regime},
                    "health_context": {"status": "learning"},
                },
            },
        },
    }


@pytest.mark.unit
def test_pattern_features_are_interpretable_buckets():
    features = extract_pattern_features(_outcome())

    assert features["symbol"] == "TRXEUR"
    assert features["engine"] == "trend_momentum"
    assert features["regime"] == "trend"
    assert features["net_edge_bucket"] == "valid"
    assert features["atr_bucket"] == "tradable"
    assert features["spread_bucket"] == "normal"


@pytest.mark.unit
def test_pattern_learning_marks_reliable_positive_pattern():
    engine = PatternLearningEngine(PatternLearningConfig(min_samples=3))
    snapshot = engine.build_snapshot([_outcome() for _ in range(4)])

    assert snapshot["summary"]["reliable_patterns"] > 0
    assert snapshot["summary"]["positive_patterns"] > 0
    assert snapshot["top_positive"][0]["status"] == "positive_pattern"
    assert snapshot["safety"]["writes_orders"] is False
    assert snapshot["safety"]["changes_thresholds"] is False


@pytest.mark.unit
def test_pattern_learning_prefers_triple_barrier_when_available():
    proxy = _outcome(source="decision_learning_current_price_proxy", net=-80.0, label="saved_loss", barrier="stop_loss")
    triple = _outcome(source="decision_learning_triple_barrier", net=60.0, label="missed_profit", barrier="take_profit")
    engine = PatternLearningEngine(PatternLearningConfig(min_samples=2, prefer_triple_barrier=True))

    snapshot = engine.build_snapshot([proxy, proxy, triple, triple])

    assert snapshot["summary"]["outcomes_used"] == 2
    assert snapshot["summary"]["positive_patterns"] > 0
    assert not snapshot["top_negative"]
