import json
import sqlite3

import pytest

from autobot.v2 import cli
from autobot.v2.paper.forward_edge_simulation import LookaheadInputError
from autobot.v2.paper.opportunity_score_audit import (
    HIGH_THRESHOLD,
    OpportunityScoreAuditConfig,
    build_opportunity_score_audit_report,
    calculate_score_variant,
)
from autobot.v2.paper.opportunity_score_v2 import (
    SCORE_V2_VERSION,
    calculate_opportunity_score_v2,
)


pytestmark = pytest.mark.unit


def _create_state_db(path):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE trade_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id TEXT NOT NULL,
                position_id TEXT,
                instance_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                expected_price REAL,
                executed_price REAL NOT NULL,
                volume REAL NOT NULL,
                fees REAL DEFAULT 0,
                slippage_bps REAL,
                realized_pnl REAL,
                is_opening_leg INTEGER DEFAULT 0,
                is_closing_leg INTEGER DEFAULT 0,
                exchange_order_id TEXT,
                decision_id TEXT,
                signal_id TEXT,
                strategy_id TEXT,
                timeframe TEXT,
                signal_source TEXT,
                gross_pnl REAL,
                net_pnl REAL,
                regime TEXT,
                execution_liquidity TEXT,
                execution_mode TEXT,
                created_at TEXT NOT NULL
            )
            """
        )


def _insert_pair(
    conn,
    *,
    position_id,
    strategy="trend_momentum",
    symbol="TRXEUR",
    net=1.0,
    gross=None,
    score=None,
    metadata_extra=None,
    fee=0.1,
    slippage_bps=1.0,
    opened_at="2026-07-04T08:20:00+02:00",
    closed_at="2026-07-04T08:25:00+02:00",
):
    metadata = {"strategy_id": strategy, "execution_mode": "shadow_paper"}
    if score is not None:
        metadata["opportunity_score"] = score
        metadata["score_bucket"] = "high" if score >= 70 else "medium" if score >= 40 else "low"
    if metadata_extra:
        metadata.update(metadata_extra)
    encoded_metadata = json.dumps(metadata, sort_keys=True)
    gross = net + (2 * fee) if gross is None else gross
    rows = [
        (
            f"{position_id}-open",
            position_id,
            "inst",
            symbol,
            "buy",
            1.0,
            1.0,
            10.0,
            fee,
            slippage_bps,
            None,
            1,
            0,
            encoded_metadata,
            None,
            strategy,
            "5m",
            "pytest",
            None,
            None,
            "trend",
            "shadow_lab",
            "shadow_paper",
            opened_at,
        ),
        (
            f"{position_id}-close",
            position_id,
            "inst",
            symbol,
            "sell",
            1.0,
            1.0,
            10.0,
            fee,
            slippage_bps,
            net,
            0,
            1,
            encoded_metadata,
            None,
            strategy,
            "5m",
            "pytest",
            gross,
            net,
            "trend",
            "shadow_lab",
            "shadow_paper",
            closed_at,
        ),
    ]
    conn.executemany(
        """
        INSERT INTO trade_ledger
        (trade_id, position_id, instance_id, symbol, side, expected_price, executed_price,
         volume, fees, slippage_bps, realized_pnl, is_opening_leg, is_closing_leg,
         decision_id, signal_id, strategy_id, timeframe, signal_source, gross_pnl, net_pnl,
         regime, execution_liquidity, execution_mode, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def test_score_variant_rejects_post_trade_fields_and_keeps_threshold_constant():
    source = {
        "strategy_id": "high_conviction_swing",
        "symbol": "ADAEUR",
        "opportunity_score": 44.0,
        "expected_move_bps": 400.0,
        "estimated_total_cost_bps": 98.0,
        "estimated_net_edge_bps": 302.0,
        "risk_penalties_bps": 0.0,
    }

    assert HIGH_THRESHOLD == 70.0
    assert calculate_score_variant("current_score", source) == pytest.approx(44.0)
    assert calculate_score_variant("high_conviction_aware", source) >= HIGH_THRESHOLD

    with pytest.raises(LookaheadInputError):
        calculate_score_variant("recalibrated_v1", {**source, "net_pnl": 999.0})
    with pytest.raises(LookaheadInputError):
        calculate_score_variant("forward_edge_aware", {**source, "closing_leg": {"exit_price": 99.0}})


def test_opportunity_score_v2_is_forward_safe_and_reports_missing_components():
    source = {
        "strategy_id": "high_conviction_swing",
        "symbol": "BTCEUR",
        "opportunity_score": 44.0,
        "expected_move_bps": 500.0,
        "estimated_total_cost_bps": 90.0,
        "estimated_net_edge_bps": 410.0,
        "risk_reward_ratio": 3.0,
        "breakout_quality": 0.8,
        "trend_timeframe_alignment": 0.9,
        "volatility_expansion": 0.7,
        "support_strength": 0.6,
        "liquidity_score": 0.8,
        "pair_health_score": 0.75,
        "segment_health_score": 0.7,
    }

    assert HIGH_THRESHOLD == 70.0
    result = calculate_opportunity_score_v2(source)
    assert result.version == SCORE_V2_VERSION
    assert result.score is not None
    assert result.bucket == "high"
    assert result.promotable is False
    assert result.paper_capital_allowed is False
    assert result.live_allowed is False
    assert result.missing_components == ()

    sparse = calculate_opportunity_score_v2(
        {
            "strategy_id": "high_conviction_swing",
            "expected_move_bps": 500.0,
            "estimated_total_cost_bps": 90.0,
        }
    )
    assert "breakout_quality" in sparse.missing_components
    assert sparse.promotable is False

    with pytest.raises(LookaheadInputError):
        calculate_opportunity_score_v2({**source, "net_pnl": 12.0})


def test_opportunity_score_audit_explains_compressed_current_scores_and_high_conviction_gap(tmp_path):
    db_path = tmp_path / "state.db"
    _create_state_db(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_pair(
            conn,
            position_id="hc_positive",
            strategy="high_conviction_swing",
            symbol="ADAEUR",
            net=3.0,
            score=44.0,
                metadata_extra={
                    "expected_move_bps": 400.0,
                    "estimated_round_trip_cost_bps": 98.0,
                    "trend_context": "aligned",
                    "breakout_quality": 0.8,
                    "trend_timeframe_alignment": 0.9,
                    "volatility_expansion": 0.7,
                    "support_strength": 0.6,
                    "liquidity_score": 0.8,
                    "pair_health_score": 0.75,
                    "segment_health_score": 0.7,
                    "risk_reward_ratio": 3.0,
                },
        )
        _insert_pair(
            conn,
            position_id="trend_low",
            strategy="trend_momentum",
            symbol="XLMEUR",
            net=-1.0,
            score=15.0,
            metadata_extra={"expected_move_bps": 60.0, "estimated_round_trip_cost_bps": 98.0},
        )
        _insert_pair(conn, position_id="grid_excluded", strategy="dynamic_grid", symbol="TRXEUR", net=99.0, score=99.0)
        before = conn.execute("SELECT COUNT(*) FROM trade_ledger").fetchone()[0]

    report = build_opportunity_score_audit_report(
        OpportunityScoreAuditConfig(state_db_path=db_path, run_id="pytest_p12", write_report=False)
    ).to_dict()

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM trade_ledger").fetchone()[0] == before

    assert report["eligible_trade_count"] == 2
    assert report["current_distribution"]["bucket_counts"]["high"] == 0
    assert "current_score_compressed_below_high_threshold" in report["root_causes"]
    assert "positive_forward_edge_not_reflected_in_current_bucket" in report["root_causes"]

    hcs = report["high_conviction_analysis"]
    assert hcs["trade_count"] == 1
    assert hcs["positive_forward_edge_count"] == 1
    assert hcs["current_bucket_counts"]["medium"] == 1
    assert hcs["variant_distributions"]["high_conviction_aware"]["bucket_counts"]["high"] == 1
    assert hcs["promotable"] is False
    assert hcs["paper_capital_allowed"] is False
    assert hcs["live_allowed"] is False

    variants = {item["name"]: item for item in report["score_variants"]}
    assert variants["current_score"]["distribution"]["bucket_counts"]["high"] == 0
    assert variants["high_conviction_aware"]["distribution"]["bucket_counts"]["high"] == 1
    assert variants["opportunity_score_v2"]["distribution"]["bucket_counts"]["high"] == 1
    assert variants["opportunity_score_v2"]["correlations"]["score_vs_forward_safe_net_edge"]["sample_size"] >= 1
    assert all(item["promotable"] is False for item in report["score_variants"])
    assert report["opportunity_formula"]["score_v2"]["version"] == SCORE_V2_VERSION
    assert report["opportunity_formula"]["score_v2"]["bucket_thresholds"]["high"] == HIGH_THRESHOLD
    assert report["anti_lookahead_audit"]["decision_uses_post_trade_data"] is False


def test_opportunity_score_audit_reports_missing_components_without_inventing_scores(tmp_path):
    db_path = tmp_path / "state.db"
    _create_state_db(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_pair(
            conn,
            position_id="hc_sparse",
            strategy="high_conviction_swing",
            symbol="BCHEUR",
            net=1.0,
            score=12.0,
            metadata_extra={"expected_move_bps": 300.0, "estimated_round_trip_cost_bps": 98.0},
        )
        _insert_pair(conn, position_id="missing_score", strategy="mean_reversion", symbol="LINKEUR", net=-0.5)

    report = build_opportunity_score_audit_report(
        OpportunityScoreAuditConfig(state_db_path=db_path, run_id="pytest_missing", write_report=False)
    ).to_dict()

    hcs_missing = report["high_conviction_analysis"]["missing_pretrade_component_counts"]
    assert hcs_missing["breakout_quality"] == 1
    assert hcs_missing["risk_reward"] == 1
    assert report["current_distribution"]["bucket_counts"]["missing"] == 1
    variants = {item["name"]: item for item in report["score_variants"]}
    assert variants["current_score"]["distribution"]["bucket_counts"]["missing"] == 1


def test_opportunity_score_audit_cli_is_read_only(tmp_path, capsys):
    db_path = tmp_path / "state.db"
    _create_state_db(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_pair(
            conn,
            position_id="cli_hc",
            strategy="high_conviction_swing",
            symbol="AAVEEUR",
            net=2.0,
            score=44.0,
            metadata_extra={"expected_move_bps": 360.0, "estimated_round_trip_cost_bps": 98.0},
        )
        before = conn.execute("SELECT COUNT(*) FROM trade_ledger").fetchone()[0]

    assert cli.main(["opportunity-score-audit", "--state-db", str(db_path), "--no-write-report"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["score_variants"][0]["promotable"] is False
    assert payload["safety_notes"]

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM trade_ledger").fetchone()[0] == before
