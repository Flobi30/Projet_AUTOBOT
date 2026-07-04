import json
import sqlite3

import pytest

from autobot.v2 import cli
from autobot.v2.paper.db_integrity import DbIntegrityConfig, build_db_integrity_report
from autobot.v2.paper.forward_edge_simulation import (
    ForwardEdgeSimulationConfig,
    LookaheadInputError,
    build_forward_edge_simulation_report,
    estimate_forward_safe_net_edge,
    shadow_routing_allowed_by_forward_policy,
)
from autobot.v2.paper.forward_edge_validation import (
    ForwardEdgeValidationConfig,
    build_forward_edge_validation_report,
)
from autobot.v2.paper.official_performance import (
    OfficialPaperPerformanceConfig,
    build_official_paper_performance_report,
)
from autobot.v2.paper.paper_confidence import PaperConfidenceConfig, build_paper_confidence_report
from autobot.v2.paper.score_filter_simulation import (
    ScoreFilterSimulationConfig,
    build_score_filter_simulation_report,
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
    score_bucket=None,
    execution_mode="shadow_paper",
    fee=0.1,
    slippage_bps=1.0,
    metadata_extra=None,
    opened_at="2026-07-03T00:00:00+00:00",
    closed_at="2026-07-03T00:05:00+00:00",
):
    metadata = {}
    if score is not None:
        metadata["opportunity_score"] = score
    if score_bucket is not None:
        metadata["score_bucket"] = score_bucket
    if metadata_extra:
        metadata.update(metadata_extra)
    encoded_metadata = json.dumps(metadata) if metadata else None
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
            execution_mode,
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
            execution_mode,
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


def test_score_filter_simulation_is_read_only_and_keeps_buckets_separate(tmp_path):
    db_path = tmp_path / "state.db"
    _create_state_db(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_pair(conn, position_id="high", net=2.0, score=90)
        _insert_pair(conn, position_id="medium", net=1.0, score=55)
        _insert_pair(conn, position_id="low", net=-1.0, score=20)
        _insert_pair(conn, position_id="missing", net=-0.5)
        _insert_pair(conn, position_id="grid", strategy="dynamic_grid", net=99.0, score=95)
        before = conn.execute("SELECT COUNT(*) FROM trade_ledger").fetchone()[0]

    report = build_score_filter_simulation_report(
        ScoreFilterSimulationConfig(state_db_path=db_path, run_id="pytest_score", write_report=False)
    ).to_dict()

    with sqlite3.connect(db_path) as conn:
        after = conn.execute("SELECT COUNT(*) FROM trade_ledger").fetchone()[0]

    assert before == after
    assert report["bucket_counts"] == {"high": 1, "medium": 1, "low": 1, "missing": 1}
    scenarios = {item["name"]: item for item in report["scenarios"]}
    assert scenarios["all_scored"]["trade_count"] == 3
    assert scenarios["missing_separate"]["trade_count"] == 1
    assert scenarios["low_separate"]["trade_count"] == 1
    assert scenarios["high_only"]["promotable"] is False
    assert all(item["promotable"] is False for item in report["cost_aware_scenarios"])
    assert all(item["paper_capital_allowed"] is False for item in report["shadow_segment_policy"])
    assert all(item["live_allowed"] is False for item in report["shadow_segment_policy"])


def test_score_filter_excludes_critical_ledger_warning_rows_from_scenarios(tmp_path):
    db_path = tmp_path / "state.db"
    _create_state_db(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_pair(conn, position_id="high_clean", net=2.0, score=90)
        _insert_pair(conn, position_id="high_bad_slippage", net=99.0, score=95, slippage_bps=250.0)

    report = build_score_filter_simulation_report(
        ScoreFilterSimulationConfig(state_db_path=db_path, run_id="pytest_score_quality", write_report=False)
    ).to_dict()

    assert report["quality_excluded_trade_count"] == 1
    assert report["exclusion_counts"]["slippage_bps_anomaly"] == 1
    assert report["coverage_by_strategy"]["trend_momentum"]["buckets"]["high"] == 2
    scenarios = {item["name"]: item for item in report["scenarios"]}
    assert scenarios["high_only"]["trade_count"] == 1
    assert scenarios["high_only"]["net_pnl_eur"] == pytest.approx(2.0)


def test_cost_aware_score_simulation_penalizes_fee_and_slippage_pressure_without_writing(tmp_path):
    db_path = tmp_path / "state.db"
    _create_state_db(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_pair(conn, position_id="good_high", net=2.0, gross=3.0, score=90, fee=0.1, slippage_bps=1.0)
        _insert_pair(conn, position_id="cost_eroded_high", net=-1.0, gross=0.25, score=90, fee=1.0, slippage_bps=20.0)
        before = conn.execute("SELECT COUNT(*) FROM trade_ledger").fetchone()[0]

    report = build_score_filter_simulation_report(
        ScoreFilterSimulationConfig(state_db_path=db_path, run_id="pytest_p9_cost", write_report=False)
    ).to_dict()

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM trade_ledger").fetchone()[0] == before

    scenarios = {item["name"]: item for item in report["cost_aware_scenarios"]}
    assert scenarios["current_score_high"]["selected_trade_count"] == 2
    assert scenarios["total_cost_adjusted_high"]["selected_trade_count"] < 2
    assert scenarios["expected_net_edge_adjusted_high"]["promotable"] is False
    assert scenarios["fee_adjusted_high"]["fees_eur"] >= 0.0
    assert scenarios["slippage_adjusted_high"]["slippage_eur"] >= 0.0


def test_shadow_segment_policy_blocks_destructive_low_and_keeps_watch_non_promotable(tmp_path):
    db_path = tmp_path / "state.db"
    _create_state_db(db_path)
    with sqlite3.connect(db_path) as conn:
        for index in range(12):
            _insert_pair(
                conn,
                position_id=f"low_bad_{index}",
                symbol="XLMEUR",
                net=-1.0,
                gross=-0.8,
                score=10,
            )
        for index in range(12):
            _insert_pair(
                conn,
                position_id=f"watch_high_{index}",
                symbol="BCHEUR",
                net=0.5,
                gross=1.0,
                score=85,
            )

    report = build_score_filter_simulation_report(
        ScoreFilterSimulationConfig(state_db_path=db_path, run_id="pytest_p9_policy", write_report=False)
    ).to_dict()

    policies = report["shadow_segment_policy"]
    low_policy = next(item for item in policies if item["key"]["score_bucket"] == "low")
    high_policy = next(item for item in policies if item["key"]["score_bucket"] == "high")
    assert low_policy["policy"] == "block_shadow_future"
    assert "low_bucket_non_promotable" in low_policy["reasons"]
    assert high_policy["policy"] == "watch"
    assert high_policy["promotable"] is False
    assert high_policy["paper_capital_allowed"] is False


def test_paper_confidence_blocks_low_sample_and_shadow_evidence(tmp_path):
    db_path = tmp_path / "state.db"
    _create_state_db(db_path)
    with sqlite3.connect(db_path) as conn:
        for index in range(10):
            _insert_pair(conn, position_id=f"t{index}", net=1.0, score=80)

    report = build_paper_confidence_report(
        PaperConfidenceConfig(
            state_db_path=db_path,
            strategy_id="trend_momentum",
            run_id="pytest_confidence",
            bootstrap_iterations=50,
            write_report=False,
        )
    ).to_dict()

    assert report["confidence_level"] == "insufficient_data"
    assert report["promotable"] is False
    assert "insufficient_sample_size" in report["blockers"]
    assert "paper_capital_evidence_absent" in report["blockers"]


def test_paper_confidence_excludes_critical_ledger_warning_rows(tmp_path):
    db_path = tmp_path / "state.db"
    _create_state_db(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_pair(conn, position_id="bad_warning", net=99.0, score=95, slippage_bps=250.0)

    report = build_paper_confidence_report(
        PaperConfidenceConfig(
            state_db_path=db_path,
            strategy_id="trend_momentum",
            run_id="pytest_confidence_quality",
            bootstrap_iterations=20,
            write_report=False,
        )
    ).to_dict()

    assert report["trade_count"] == 0
    assert report["quality_excluded_trade_count"] == 1
    assert report["quality_exclusion_counts"] == {"slippage_bps_anomaly": 1}
    assert report["confidence_level"] == "insufficient_data"
    assert report["promotable"] is False


def test_paper_confidence_never_promotes_positive_shadow_sample(tmp_path):
    db_path = tmp_path / "state.db"
    _create_state_db(db_path)
    with sqlite3.connect(db_path) as conn:
        for index in range(60):
            _insert_pair(conn, position_id=f"pos{index}", net=1.0, score=80)

    report = build_paper_confidence_report(
        PaperConfidenceConfig(
            state_db_path=db_path,
            strategy_id="trend_momentum",
            run_id="pytest_shadow_confidence",
            bootstrap_iterations=50,
            write_report=False,
        )
    ).to_dict()

    assert report["confidence_level"] == "early_signal"
    assert report["promotable"] is False
    assert "paper_capital_evidence_absent" in report["blockers"]


def test_official_performance_excludes_critical_ledger_warning_rows(tmp_path):
    db_path = tmp_path / "state.db"
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"hypotheses": []}), encoding="utf-8")
    _create_state_db(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_pair(conn, position_id="clean", net=1.0, score=80)
        _insert_pair(conn, position_id="warning", net=99.0, score=90, slippage_bps=250.0)

    report = build_official_paper_performance_report(
        OfficialPaperPerformanceConfig(
            state_db_path=db_path,
            registry_path=registry,
            run_id="pytest_official_quality",
        ),
        write_report=False,
    ).to_dict()

    assert report["legacy"]["quality_excluded_trade_count"] == 1
    assert report["legacy"]["quality_exclusion_counts"] == {"slippage_bps_anomaly": 1}
    trend = next(item for item in report["ranking"] if item["strategy_id"] == "trend_momentum")
    assert trend["metrics"]["closed_trade_count"] == 1
    assert trend["metrics"]["net_pnl_eur"] == pytest.approx(1.0)


def test_db_integrity_reports_snapshot_and_invalid_rows(tmp_path):
    db_path = tmp_path / "state.db"
    _create_state_db(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_pair(conn, position_id="bad-bucket", net=1.0, score_bucket="very_high")
        _insert_pair(conn, position_id="negative-cost", net=1.0, fee=-0.1)
        conn.execute(
            "INSERT INTO trade_ledger (trade_id, position_id, instance_id, symbol, side, executed_price, volume, "
            "fees, is_closing_leg, strategy_id, execution_mode, created_at) "
            "VALUES ('dup', 'p1', 'inst', 'TRXEUR', 'sell', 1, 1, 0, 1, 'trend_momentum', 'shadow_paper', '2026-07-03')"
        )
        conn.execute(
            "INSERT INTO trade_ledger (trade_id, position_id, instance_id, symbol, side, executed_price, volume, "
            "fees, is_closing_leg, strategy_id, execution_mode, created_at) "
            "VALUES ('dup', 'p2', 'inst', 'TRXEUR', 'sell', 1, 1, 0, 1, 'trend_momentum', 'shadow_paper', '2026-07-03')"
        )

    report = build_db_integrity_report(
        DbIntegrityConfig(
            state_db_path=db_path,
            snapshot_dir=tmp_path / "snapshots",
            run_id="pytest_integrity",
            write_report=False,
        )
    ).to_dict()

    assert report["source_mode"] == "snapshot"
    assert report["status"] == "FAIL"
    assert report["checks"]["duplicate_trade_id_groups"] == 1
    assert report["checks"]["negative_cost_rows"] >= 1
    assert report["checks"]["invalid_score_bucket_rows"] == 1
    assert report["checks"]["legacy_rows_used_by_official_metrics"] is False


def test_new_p6_cli_commands_are_read_only(tmp_path, capsys):
    db_path = tmp_path / "state.db"
    _create_state_db(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_pair(conn, position_id="high", net=2.0, score=90)
        row_count = conn.execute("SELECT COUNT(*) FROM trade_ledger").fetchone()[0]

    assert cli.main(["score-filter-simulation", "--state-db", str(db_path), "--no-write-report"]) == 0
    score_payload = json.loads(capsys.readouterr().out)
    assert score_payload["scenarios"][0]["promotable"] is False

    assert cli.main([
        "paper-confidence",
        "--state-db",
        str(db_path),
        "--strategy-id",
        "trend_momentum",
        "--bootstrap-iterations",
        "20",
        "--no-write-report",
    ]) == 0
    confidence_payload = json.loads(capsys.readouterr().out)
    assert confidence_payload["promotable"] is False

    assert cli.main(["check-db-integrity", "--state-db", str(db_path), "--no-write-report"]) == 0
    integrity_payload = json.loads(capsys.readouterr().out)
    assert integrity_payload["checks"]["legacy_rows_used_by_official_metrics"] is False

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM trade_ledger").fetchone()[0] == row_count


def test_forward_safe_net_edge_rejects_post_trade_fields_and_uses_costs():
    safe_input = {
        "strategy_id": "trend_momentum",
        "symbol": "BCHEUR",
        "opened_at": "2026-07-03T00:00:00+00:00",
        "score_bucket": "high",
        "opportunity_score": 82.0,
        "expected_move_bps": 240.0,
        "estimated_fees_bps": 80.0,
        "estimated_spread_cost_bps": 8.0,
        "estimated_slippage_bps": 6.0,
        "latency_buffer_bps": 0.0,
        "estimated_total_cost_bps": 94.0,
    }

    estimate = estimate_forward_safe_net_edge(safe_input)
    assert estimate.estimated_net_edge_bps == pytest.approx(146.0)
    assert estimate.confidence_level == "forward_edge_positive"
    assert estimate.promotable is False
    assert estimate.paper_capital_allowed is False
    assert estimate.live_allowed is False

    with pytest.raises(LookaheadInputError):
        estimate_forward_safe_net_edge({**safe_input, "net_pnl": 999.0})
    with pytest.raises(LookaheadInputError):
        estimate_forward_safe_net_edge({**safe_input, "closing_leg": {"gross_edge_bps": 999.0}})


def test_forward_edge_simulation_is_read_only_and_keeps_low_missing_separate(tmp_path):
    db_path = tmp_path / "state.db"
    _create_state_db(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_pair(
            conn,
            position_id="forward_high",
            symbol="BCHEUR",
            net=2.0,
            gross=3.0,
            score=88,
            metadata_extra={
                "expected_move_bps": 260.0,
                "estimated_round_trip_cost_bps": 96.0,
                "closing_leg": {"gross_edge_bps": 999.0},
                "mfe_bps": 500.0,
            },
        )
        _insert_pair(
            conn,
            position_id="forward_low",
            symbol="XLMEUR",
            net=-1.0,
            gross=-0.5,
            score=15,
            metadata_extra={"expected_move_bps": 80.0, "estimated_round_trip_cost_bps": 96.0},
        )
        _insert_pair(conn, position_id="forward_missing", symbol="LINKEUR", net=-0.5)
        _insert_pair(
            conn,
            position_id="grid_excluded",
            strategy="dynamic_grid",
            symbol="TRXEUR",
            net=99.0,
            score=99,
            metadata_extra={"expected_move_bps": 300.0, "estimated_round_trip_cost_bps": 80.0},
        )
        row_count = conn.execute("SELECT COUNT(*) FROM trade_ledger").fetchone()[0]

    report = build_forward_edge_simulation_report(
        ForwardEdgeSimulationConfig(state_db_path=db_path, run_id="pytest_forward", write_report=False)
    ).to_dict()

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM trade_ledger").fetchone()[0] == row_count

    assert report["bucket_counts"] == {"high": 1, "medium": 0, "low": 1, "missing": 1}
    assert report["input_audit"]["decision_uses_post_trade_data"] is False
    assert report["input_audit"]["forbidden_fields_used"] == []
    assert report["input_audit"]["raw_forbidden_fields_seen_count"] >= 1
    scenarios = {item["name"]: item for item in report["scenarios"]}
    assert scenarios["all_scored"]["trade_count"] == 2
    assert scenarios["forward_safe_net_edge_positive"]["trade_count"] == 1
    assert scenarios["forward_safe_net_edge_plus_score_high"]["trade_count"] == 1
    assert scenarios["opportunity_high_current"]["promotable"] is False
    assert all(item["paper_capital_allowed"] is False for item in report["scenarios"])
    assert all(item["live_allowed"] is False for item in report["scenarios"])


def test_forward_edge_segment_policies_never_promote_and_block_low_future_shadow(tmp_path):
    db_path = tmp_path / "state.db"
    _create_state_db(db_path)
    with sqlite3.connect(db_path) as conn:
        for index in range(12):
            _insert_pair(
                conn,
                position_id=f"low_forward_bad_{index}",
                symbol="XLMEUR",
                net=-1.0,
                gross=-0.6,
                score=12,
                metadata_extra={"expected_move_bps": 60.0, "estimated_round_trip_cost_bps": 96.0},
            )
        for index in range(12):
            _insert_pair(
                conn,
                position_id=f"watch_forward_{index}",
                symbol="BCHEUR",
                net=0.4,
                gross=1.0,
                score=86,
                metadata_extra={"expected_move_bps": 240.0, "estimated_round_trip_cost_bps": 96.0},
            )

    report = build_forward_edge_simulation_report(
        ForwardEdgeSimulationConfig(state_db_path=db_path, run_id="pytest_forward_policy", write_report=False)
    ).to_dict()

    policies = report["segment_policy"]
    low_policy = next(item for item in policies if item["key"]["score_bucket"] == "low")
    high_policy = next(item for item in policies if item["key"]["score_bucket"] == "high")
    assert low_policy["policy"] == "block_shadow_future"
    assert shadow_routing_allowed_by_forward_policy(low_policy) is False
    assert "low_bucket_non_promotable" in low_policy["reasons"]
    assert high_policy["policy"] == "forward_edge_watch"
    assert high_policy["promotable"] is False
    assert high_policy["paper_capital_allowed"] is False
    assert high_policy["live_allowed"] is False


def test_forward_edge_cli_is_read_only(tmp_path, capsys):
    db_path = tmp_path / "state.db"
    _create_state_db(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_pair(
            conn,
            position_id="forward_cli",
            net=1.0,
            score=90,
            metadata_extra={"expected_move_bps": 220.0, "estimated_round_trip_cost_bps": 96.0},
        )
        row_count = conn.execute("SELECT COUNT(*) FROM trade_ledger").fetchone()[0]

    assert cli.main(["forward-edge-simulation", "--state-db", str(db_path), "--no-write-report"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["scenarios"][0]["promotable"] is False
    assert payload["input_audit"]["decision_uses_post_trade_data"] is False

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM trade_ledger").fetchone()[0] == row_count


def test_forward_edge_validation_uses_only_post_cutoff_observations(tmp_path):
    db_path = tmp_path / "state.db"
    _create_state_db(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_pair(
            conn,
            position_id="pre_p10",
            net=10.0,
            score=90,
            metadata_extra={"expected_move_bps": 240.0, "estimated_round_trip_cost_bps": 96.0},
            opened_at="2026-07-04T07:50:00+02:00",
            closed_at="2026-07-04T07:55:00+02:00",
        )
        _insert_pair(
            conn,
            position_id="post_p10",
            net=1.0,
            score=90,
            metadata_extra={"expected_move_bps": 240.0, "estimated_round_trip_cost_bps": 96.0},
            opened_at="2026-07-04T08:10:00+02:00",
            closed_at="2026-07-04T08:15:00+02:00",
        )

    report = build_forward_edge_validation_report(
        ForwardEdgeValidationConfig(
            state_db_path=db_path,
            since_commit="85199ba235062d3cdc273d015ec67a573ad7d82e",
            run_id="pytest_forward_validation",
            write_report=False,
        )
    ).to_dict()

    assert report["pre_p10"]["eligible_trade_count"] == 1
    assert report["post_p10"]["eligible_trade_count"] == 1
    scenarios = {item["name"]: item for item in report["scenarios"]}
    assert scenarios["all_scored"]["trade_count"] == 1
    assert scenarios["all_scored"]["net_pnl_eur"] == pytest.approx(1.0)
    assert scenarios["forward_safe_net_edge_plus_score_high"]["trade_count"] == 1
    assert report["forward_only_result"]["promotable"] is False
    assert report["forward_only_result"]["paper_capital_allowed"] is False
    assert report["forward_only_result"]["live_allowed"] is False


def test_forward_edge_validation_keeps_insufficient_and_blocked_groups_separate(tmp_path):
    db_path = tmp_path / "state.db"
    _create_state_db(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_pair(
            conn,
            position_id="post_missing",
            symbol="LINKEUR",
            net=-0.5,
            opened_at="2026-07-04T08:20:00+02:00",
            closed_at="2026-07-04T08:25:00+02:00",
        )
        for index in range(12):
            _insert_pair(
                conn,
                position_id=f"post_low_bad_{index}",
                symbol="XLMEUR",
                net=-1.0,
                score=15,
                metadata_extra={"expected_move_bps": 60.0, "estimated_round_trip_cost_bps": 96.0},
                opened_at=f"2026-07-04T09:{index:02d}:00+02:00",
                closed_at=f"2026-07-04T09:{index:02d}:30+02:00",
            )

    report = build_forward_edge_validation_report(
        ForwardEdgeValidationConfig(
            state_db_path=db_path,
            since="2026-07-04T08:06:17+02:00",
            run_id="pytest_forward_validation_groups",
            write_report=False,
        )
    ).to_dict()

    assert report["post_p10"]["bucket_counts"]["missing"] == 1
    assert report["post_p10"]["bucket_counts"]["low"] == 12
    scenarios = {item["name"]: item for item in report["scenarios"]}
    assert scenarios["rejected_or_insufficient_data"]["trade_count"] >= 1
    assert scenarios["block_shadow_future"]["trade_count"] == 12
    assert scenarios["block_shadow_future"]["promotable"] is False
    assert all(item["paper_capital_allowed"] is False for item in report["segment_policy"])
    assert all(item["live_allowed"] is False for item in report["segment_policy"])


def test_forward_edge_validation_reconstructs_expected_move_from_pretrade_net_edge(tmp_path):
    db_path = tmp_path / "state.db"
    _create_state_db(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_pair(
            conn,
            position_id="post_net_edge",
            net=1.0,
            score=88,
            metadata_extra={"expected_net_edge_bps": 25.0, "estimated_round_trip_cost_bps": 96.0},
            opened_at="2026-07-04T08:20:00+02:00",
            closed_at="2026-07-04T08:25:00+02:00",
        )

    report = build_forward_edge_validation_report(
        ForwardEdgeValidationConfig(
            state_db_path=db_path,
            since="2026-07-04T08:06:17+02:00",
            run_id="pytest_forward_validation_coverage",
            write_report=False,
        )
    ).to_dict()

    assert report["post_p10"]["pretrade_coverage"]["expected_move_available"] == 1
    assert report["post_p10"]["pretrade_coverage"]["forward_edge_valid"] == 1
    scenarios = {item["name"]: item for item in report["scenarios"]}
    assert scenarios["forward_safe_net_edge_plus_score_high"]["trade_count"] == 1


def test_forward_edge_validation_cli_is_read_only(tmp_path, capsys):
    db_path = tmp_path / "state.db"
    _create_state_db(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_pair(
            conn,
            position_id="post_cli",
            net=1.0,
            score=90,
            metadata_extra={"expected_move_bps": 220.0, "estimated_round_trip_cost_bps": 96.0},
            opened_at="2026-07-04T08:20:00+02:00",
            closed_at="2026-07-04T08:25:00+02:00",
        )
        row_count = conn.execute("SELECT COUNT(*) FROM trade_ledger").fetchone()[0]

    assert cli.main([
        "forward-edge-validation",
        "--state-db",
        str(db_path),
        "--since-commit",
        "85199ba235062d3cdc273d015ec67a573ad7d82e",
        "--no-write-report",
    ]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["post_p10"]["eligible_trade_count"] == 1
    assert payload["forward_only_result"]["promotable"] is False

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM trade_ledger").fetchone()[0] == row_count
