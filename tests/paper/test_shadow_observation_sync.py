import json
import sqlite3
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from autobot.v2 import cli
from autobot.v2.paper import shadow_observation_sync
from autobot.v2.paper.official_performance import (
    OfficialPaperPerformanceConfig,
    build_official_paper_performance_report,
)
from autobot.v2.paper.ledger_loader import load_state_db_paper_ledger
from autobot.v2.paper.shadow_observation_sync import (
    ShadowPaperObservationSyncConfig,
    sync_shadow_paper_observations,
)
from autobot.v2.research.trade_journal import TradeRecord
from autobot.v2.strategy_runtime_policy import (
    EXECUTION_MODE_SHADOW_PAPER,
    shadow_paper_strategy_block_reason,
    trade_ledger_append_block_reason,
)


pytestmark = pytest.mark.unit


def _strategy_entry(strategy_id: str, status: str = "learning") -> dict:
    return {
        "strategy_id": strategy_id,
        "family": strategy_id,
        "hypothesis": "pytest",
        "market": "spot_crypto",
        "timeframe": "5m",
        "required_data": ["ohlcv"],
        "entry_logic": "pytest",
        "exit_logic": "pytest",
        "risk_model": "pytest",
        "fees_model": {"profile": "paper_current_taker"},
        "slippage_model": {"profile": "paper_current_taker"},
        "expected_market_regime": "range",
        "failure_modes": ["insufficient_edge"],
        "baseline_comparison": {"no_trade": "required"},
        "validation_status": status,
        "last_backtest_id": None,
        "paper_status": "shadow_only",
        "decision": "continue_testing",
        "decision_reason": "pytest",
    }


def _write_registry(path: Path) -> None:
    payload = {
        "decision_statuses": [
            "learning",
            "candidate",
            "backtest_passed",
            "walk_forward_passed",
            "shadow_passed",
            "paper_validated",
            "rejected",
            "retired_from_execution",
        ],
        "live_auto_promotion_allowed": False,
        "hypotheses": [
            _strategy_entry("trend_momentum", "learning"),
            _strategy_entry("mean_reversion", "learning"),
            _strategy_entry("high_conviction_swing", "learning"),
            _strategy_entry("opportunity_scoring", "learning"),
            _strategy_entry("dynamic_grid", "retired_from_execution"),
            _strategy_entry("no_trade_baseline", "paper_validated"),
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_shadow_db(path: Path, table: str) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            f"""
            CREATE TABLE {table} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                variant TEXT NOT NULL,
                position_id TEXT NOT NULL,
                entry_price REAL NOT NULL,
                exit_price REAL NOT NULL,
                volume REAL NOT NULL,
                notional REAL NOT NULL,
                fees REAL NOT NULL,
                realized_pnl REAL NOT NULL,
                reason TEXT NOT NULL,
                opened_at TEXT NOT NULL,
                closed_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            f"""
            INSERT INTO {table}
            (symbol, variant, position_id, entry_price, exit_price, volume,
             notional, fees, realized_pnl, reason, opened_at, closed_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "TRXEUR",
                "balanced",
                "shadow_pos_1",
                1.00,
                1.08,
                100.0,
                100.0,
                1.50,
                6.50,
                "take_profit",
                "2026-07-01T01:00:00+00:00",
                "2026-07-01T03:00:00+00:00",
                "2026-07-01T03:00:01+00:00",
            ),
        )


def _write_scored_shadow_db(path: Path, table: str) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            f"""
            CREATE TABLE {table} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                variant TEXT NOT NULL,
                position_id TEXT NOT NULL,
                entry_price REAL NOT NULL,
                exit_price REAL NOT NULL,
                volume REAL NOT NULL,
                notional REAL NOT NULL,
                fees REAL NOT NULL,
                realized_pnl REAL NOT NULL,
                reason TEXT NOT NULL,
                opened_at TEXT NOT NULL,
                closed_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                opportunity_score REAL,
                opportunity_status TEXT,
                opportunity_reason TEXT,
                opportunity_components TEXT,
                regime TEXT,
                timeframe TEXT,
                signal_source TEXT
            )
            """
        )
        conn.execute(
            f"""
            INSERT INTO {table}
            (symbol, variant, position_id, entry_price, exit_price, volume,
             notional, fees, realized_pnl, reason, opened_at, closed_at, created_at,
             opportunity_score, opportunity_status, opportunity_reason, opportunity_components,
             regime, timeframe, signal_source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "XLMEUR",
                "score-aware",
                "shadow_pos_score",
                1.00,
                1.05,
                100.0,
                100.0,
                1.00,
                4.00,
                "take_profit",
                "2026-07-01T01:00:00+00:00",
                "2026-07-01T03:00:00+00:00",
                "2026-07-01T03:00:01+00:00",
                72.5,
                "tradable",
                "score_above_threshold",
                json.dumps({"edge": 0.8}),
                "trend",
                "5m",
                "pytest_score",
            ),
        )


def _write_decision_ledger_router_score(
    path: Path,
    *,
    symbol: str = "TRXEUR",
    strategy: str = "observation_only",
    engine: str = "trend_momentum",
    created_at: str = "2026-07-01T00:55:00+00:00",
    score: float = 82.0,
) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS decision_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT,
                decision_id TEXT,
                signal_id TEXT,
                instance_id TEXT,
                symbol TEXT,
                strategy TEXT,
                engine TEXT,
                event_type TEXT,
                event_status TEXT,
                reason TEXT,
                source TEXT,
                payload_json TEXT,
                created_at TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO decision_ledger
            (event_id, decision_id, signal_id, instance_id, symbol, strategy, engine,
             event_type, event_status, reason, source, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"pytest_event_{created_at}",
                f"pytest_decision_{created_at}",
                None,
                "pytest",
                symbol,
                strategy,
                engine,
                "governance_block",
                "blocked",
                "research_only_no_runtime_promotion",
                "strategy_router",
                json.dumps(
                    {
                        "decision": "keep_shadow_learning",
                        "selected_engine": engine,
                        "selected_variant": "pytest_variant",
                        "router_score": score,
                        "router_action": "watch_best_engine",
                        "router_reason": "pytest_router_score",
                        "live_promotion_allowed": False,
                    }
                ),
                created_at,
            ),
        )


def _high_conviction_record(strategy_id: str = "high_conviction_swing") -> TradeRecord:
    return TradeRecord(
        run_id="pytest_high_conviction",
        strategy_id=strategy_id,
        symbol="BTCEUR",
        side="buy",
        opened_at=datetime(2026, 7, 1, 1, tzinfo=timezone.utc),
        closed_at=datetime(2026, 7, 1, 8, tzinfo=timezone.utc),
        quantity=0.01,
        entry_price=50_000.0,
        exit_price=51_000.0,
        gross_pnl_eur=10.0,
        net_pnl_eur=7.5,
        fees_eur=1.5,
        spread_cost_eur=0.4,
        slippage_eur=0.5,
        latency_cost_eur=0.1,
        entry_reason="pytest_high_conviction_setup",
        exit_reason="fixed_tp",
        regime="trend",
        metadata={
            "family": "breakout_1h_4h",
            "policy": "conservative",
            "expected_move_bps": 500,
            "logical_stop_bps": 180,
            "mfe_bps": 220,
            "mae_bps": 60,
            "cost_bps": 90,
        },
    )


def test_learning_strategy_can_write_shadow_paper_observation_with_strategy_id(tmp_path):
    state_db = tmp_path / "state.db"
    registry = tmp_path / "strategy_hypotheses.json"
    trend_db = tmp_path / "trend_shadow_lab.db"
    mean_db = tmp_path / "mean_reversion_shadow_lab.db"
    _write_registry(registry)
    _write_shadow_db(trend_db, "trend_shadow_trades")

    report = sync_shadow_paper_observations(
        ShadowPaperObservationSyncConfig(
            state_db_path=state_db,
            registry_path=registry,
            trend_shadow_db_path=trend_db,
            mean_reversion_shadow_db_path=mean_db,
            output_dir=tmp_path / "reports",
            run_id="pytest_shadow_sync",
        )
    ).to_dict()

    trend = next(item for item in report["source_results"] if item["strategy_id"] == "trend_momentum")
    assert trend["inserted_trade_count"] == 1
    assert trend["duplicate_trade_count"] == 0

    with sqlite3.connect(state_db) as conn:
        rows = conn.execute(
            """
            SELECT strategy_id, execution_mode, is_opening_leg, is_closing_leg, net_pnl, gross_pnl
            FROM trade_ledger
            ORDER BY id ASC
            """
        ).fetchall()
    assert len(rows) == 2
    assert {row[0] for row in rows} == {"trend_momentum"}
    assert {row[1] for row in rows} == {EXECUTION_MODE_SHADOW_PAPER}
    assert rows[-1][3] == 1
    assert rows[-1][4] == pytest.approx(6.50)
    assert rows[-1][5] == pytest.approx(8.00)


def test_shadow_sync_preserves_opportunity_score_metadata(tmp_path):
    state_db = tmp_path / "state.db"
    registry = tmp_path / "strategy_hypotheses.json"
    trend_db = tmp_path / "trend_shadow_lab.db"
    _write_registry(registry)
    _write_scored_shadow_db(trend_db, "trend_shadow_trades")

    report = sync_shadow_paper_observations(
        ShadowPaperObservationSyncConfig(
            state_db_path=state_db,
            registry_path=registry,
            trend_shadow_db_path=trend_db,
            mean_reversion_shadow_db_path=tmp_path / "missing_mean.db",
            output_dir=tmp_path / "reports",
            run_id="pytest_scored_shadow_sync",
        )
    ).to_dict()

    loaded = load_state_db_paper_ledger(state_db)
    trade = loaded.journal.records[0]
    assert trade.metadata["opportunity_score"] == pytest.approx(72.5)
    assert trade.metadata["score_bucket"] == "high"
    assert trade.metadata["opportunity_metadata_origin"] == "source"
    assert trade.metadata["opportunity_status"] == "tradable"
    assert trade.metadata["opportunity_reason"] == "score_above_threshold"
    assert trade.metadata["opportunity_components"] == {"edge": 0.8}
    trend = next(item for item in report["source_results"] if item["strategy_id"] == "trend_momentum")
    assert trend["inserted_score_coverage"]["buckets"]["high"] == 1
    assert trend["inserted_score_coverage"]["score_coverage_pct"] == pytest.approx(100.0)
    assert trend["score_origin_counts"] == {"source": 1}


def test_shadow_sync_enriches_missing_score_from_prior_decision_ledger(tmp_path):
    state_db = tmp_path / "state.db"
    registry = tmp_path / "strategy_hypotheses.json"
    trend_db = tmp_path / "trend_shadow_lab.db"
    _write_registry(registry)
    _write_shadow_db(trend_db, "trend_shadow_trades")
    _write_decision_ledger_router_score(state_db, score=82.0)

    sync_shadow_paper_observations(
        ShadowPaperObservationSyncConfig(
            state_db_path=state_db,
            registry_path=registry,
            trend_shadow_db_path=trend_db,
            mean_reversion_shadow_db_path=tmp_path / "missing_mean.db",
            output_dir=tmp_path / "reports",
            run_id="pytest_router_score_shadow_sync",
        )
    )

    loaded = load_state_db_paper_ledger(state_db)
    trade = loaded.journal.records[0]
    assert trade.metadata["opportunity_score"] == pytest.approx(82.0)
    assert trade.metadata["opportunity_score_source"] == "router_score"
    assert trade.metadata["opportunity_metadata_origin"] == "decision_ledger_lookup"
    assert trade.metadata["score_bucket"] == "high"
    assert trade.metadata["opportunity_status"] == "watch_best_engine"
    assert trade.metadata["opportunity_reason"] == "pytest_router_score"
    assert trade.metadata["opportunity_event_type"] == "governance_block"
    assert trade.metadata["opportunity_match_delta_seconds"] == pytest.approx(300.0)


def test_shadow_sync_does_not_enrich_from_future_decision_ledger(tmp_path):
    state_db = tmp_path / "state.db"
    registry = tmp_path / "strategy_hypotheses.json"
    trend_db = tmp_path / "trend_shadow_lab.db"
    _write_registry(registry)
    _write_shadow_db(trend_db, "trend_shadow_trades")
    _write_decision_ledger_router_score(
        state_db,
        created_at="2026-07-01T01:05:00+00:00",
        score=95.0,
    )

    sync_shadow_paper_observations(
        ShadowPaperObservationSyncConfig(
            state_db_path=state_db,
            registry_path=registry,
            trend_shadow_db_path=trend_db,
            mean_reversion_shadow_db_path=tmp_path / "missing_mean.db",
            output_dir=tmp_path / "reports",
            run_id="pytest_no_lookahead_shadow_sync",
        )
    )

    loaded = load_state_db_paper_ledger(state_db)
    trade = loaded.journal.records[0]
    assert trade.metadata["score_bucket"] == "missing"
    assert "opportunity_score" not in trade.metadata


def test_high_conviction_shadow_sync_writes_closed_replay_records_only(tmp_path, monkeypatch):
    state_db = tmp_path / "state.db"
    registry = tmp_path / "strategy_hypotheses.json"
    data_path = tmp_path / "ohlcv.csv"
    data_path.write_text("timestamp,symbol,timeframe,open,high,low,close,volume\n", encoding="utf-8")
    _write_registry(registry)
    record = _high_conviction_record()
    fake_result = SimpleNamespace(
        cost_profile="research_stress",
        policy="conservative",
        scenario={
            "min_expected_move_bps": 500.0,
            "risk_reward_ratio": 2.0,
            "max_hold_hours": 72.0,
            "exit_mode": "fixed_tp_sl",
        },
        trade_records=(record,),
    )
    fake_report = SimpleNamespace(portfolio_results=(fake_result,))
    captured_output: dict[str, Path] = {}
    monkeypatch.setattr(shadow_observation_sync, "build_high_conviction_portfolio_report", lambda _config: fake_report)

    def _fake_write(report, output):
        captured_output["path"] = Path(output)
        return report

    monkeypatch.setattr(shadow_observation_sync, "write_high_conviction_portfolio_report", _fake_write)

    report = sync_shadow_paper_observations(
        ShadowPaperObservationSyncConfig(
            state_db_path=state_db,
            registry_path=registry,
            trend_shadow_db_path=tmp_path / "missing_trend.db",
            mean_reversion_shadow_db_path=tmp_path / "missing_mean.db",
            high_conviction_data_paths=(data_path,),
            output_dir=tmp_path / "reports",
            run_id="pytest_high_conviction_shadow_sync",
        )
    ).to_dict()

    high_conviction = next(
        item for item in report["source_results"] if item["strategy_id"] == "high_conviction_swing"
    )
    assert high_conviction["inserted_trade_count"] == 1
    assert high_conviction["source_trade_count"] == 1
    assert captured_output["path"] == (
        Path("data/research/high_conviction_shadow_sync") / "pytest_high_conviction_shadow_sync"
    )
    loaded = load_state_db_paper_ledger(state_db)
    trade = loaded.journal.records[0]
    assert trade.strategy_id == "high_conviction_swing"
    assert trade.metadata["execution_mode"] == EXECUTION_MODE_SHADOW_PAPER
    assert trade.metadata["score_bucket"] == "missing"
    assert trade.metadata["family"] == "breakout_1h_4h"
    assert trade.net_pnl_eur == pytest.approx(7.5)


def test_shadow_sync_commits_before_high_conviction_replay(tmp_path, monkeypatch):
    state_db = tmp_path / "state.db"
    registry = tmp_path / "strategy_hypotheses.json"
    trend_db = tmp_path / "trend_shadow_lab.db"
    data_path = tmp_path / "ohlcv.csv"
    data_path.write_text("timestamp,symbol,timeframe,open,high,low,close,volume\n", encoding="utf-8")
    _write_registry(registry)
    _write_shadow_db(trend_db, "trend_shadow_trades")

    def _fake_build(_config):
        with sqlite3.connect(state_db, timeout=0.1) as probe:
            probe.execute("CREATE TABLE IF NOT EXISTS lock_probe (id INTEGER PRIMARY KEY)")
            probe.execute("INSERT INTO lock_probe DEFAULT VALUES")
        return SimpleNamespace(portfolio_results=())

    monkeypatch.setattr(shadow_observation_sync, "build_high_conviction_portfolio_report", _fake_build)
    monkeypatch.setattr(shadow_observation_sync, "write_high_conviction_portfolio_report", lambda report, _output: report)

    report = sync_shadow_paper_observations(
        ShadowPaperObservationSyncConfig(
            state_db_path=state_db,
            registry_path=registry,
            trend_shadow_db_path=trend_db,
            mean_reversion_shadow_db_path=tmp_path / "missing_mean.db",
            high_conviction_data_paths=(data_path,),
            output_dir=tmp_path / "reports",
            run_id="pytest_commit_before_high_conviction",
            write_report=False,
        )
    ).to_dict()

    trend = next(item for item in report["source_results"] if item["strategy_id"] == "trend_momentum")
    high_conviction = next(
        item for item in report["source_results"] if item["strategy_id"] == "high_conviction_swing"
    )
    assert trend["inserted_trade_count"] == 1
    assert high_conviction["reason_counts"] == {"no_closed_high_conviction_shadow_trades": 1}


def test_high_conviction_shadow_sync_is_idempotent_across_replay_run_ids(tmp_path, monkeypatch):
    state_db = tmp_path / "state.db"
    registry = tmp_path / "strategy_hypotheses.json"
    data_path = tmp_path / "ohlcv.csv"
    data_path.write_text("timestamp,symbol,timeframe,open,high,low,close,volume\n", encoding="utf-8")
    _write_registry(registry)
    replay_run_id = {"value": "pytest_replay_a"}

    def _fake_build(_config):
        fake_result = SimpleNamespace(
            cost_profile="research_stress",
            policy="conservative",
            scenario={
                "min_expected_move_bps": 500.0,
                "risk_reward_ratio": 2.0,
                "max_hold_hours": 72.0,
                "exit_mode": "fixed_tp_sl",
            },
            trade_records=(replace(_high_conviction_record(), run_id=replay_run_id["value"]),),
        )
        return SimpleNamespace(portfolio_results=(fake_result,))

    monkeypatch.setattr(shadow_observation_sync, "build_high_conviction_portfolio_report", _fake_build)
    monkeypatch.setattr(shadow_observation_sync, "write_high_conviction_portfolio_report", lambda report, _output: report)

    base_config = dict(
        state_db_path=state_db,
        registry_path=registry,
        trend_shadow_db_path=tmp_path / "missing_trend.db",
        mean_reversion_shadow_db_path=tmp_path / "missing_mean.db",
        high_conviction_data_paths=(data_path,),
        output_dir=tmp_path / "reports",
        write_report=False,
    )
    first = sync_shadow_paper_observations(
        ShadowPaperObservationSyncConfig(**base_config, run_id="pytest_high_conviction_first")
    ).to_dict()
    replay_run_id["value"] = "pytest_replay_b"
    second = sync_shadow_paper_observations(
        ShadowPaperObservationSyncConfig(**base_config, run_id="pytest_high_conviction_second")
    ).to_dict()

    first_result = next(item for item in first["source_results"] if item["strategy_id"] == "high_conviction_swing")
    second_result = next(item for item in second["source_results"] if item["strategy_id"] == "high_conviction_swing")
    assert first_result["inserted_trade_count"] == 1
    assert second_result["inserted_trade_count"] == 0
    assert second_result["duplicate_trade_count"] == 1
    with sqlite3.connect(state_db) as conn:
        assert conn.execute(
            """
            SELECT COUNT(*)
            FROM trade_ledger
            WHERE strategy_id='high_conviction_swing'
            """
        ).fetchone()[0] == 2


def test_high_conviction_without_strategy_id_is_rejected(tmp_path):
    state_db = tmp_path / "state.db"
    with sqlite3.connect(state_db) as conn:
        shadow_observation_sync._ensure_trade_ledger_schema(conn)
        with pytest.raises(ValueError, match="strategy_id=high_conviction_swing"):
            shadow_observation_sync._insert_trade_record_pair(
                conn,
                _high_conviction_record(strategy_id=""),
                source_id="pytest_bad_high_conviction",
                source_name="pytest",
                generated_at="2026-07-01T00:00:00+00:00",
            )


def test_high_conviction_negative_costs_are_rejected(tmp_path):
    state_db = tmp_path / "state.db"
    with sqlite3.connect(state_db) as conn:
        shadow_observation_sync._ensure_trade_ledger_schema(conn)
        with pytest.raises(ValueError, match="costs cannot be negative"):
            shadow_observation_sync._insert_trade_record_pair(
                conn,
                replace(_high_conviction_record(), fees_eur=-1.0),
                source_id="pytest_negative_cost_high_conviction",
                source_name="pytest",
                generated_at="2026-07-01T00:00:00+00:00",
            )


def test_high_conviction_missing_data_paths_reports_diagnostic(tmp_path):
    state_db = tmp_path / "state.db"
    registry = tmp_path / "strategy_hypotheses.json"
    _write_registry(registry)

    report = sync_shadow_paper_observations(
        ShadowPaperObservationSyncConfig(
            state_db_path=state_db,
            registry_path=registry,
            trend_shadow_db_path=tmp_path / "missing_trend.db",
            mean_reversion_shadow_db_path=tmp_path / "missing_mean.db",
            output_dir=tmp_path / "reports",
            run_id="pytest_high_conviction_missing_paths",
            write_report=False,
        )
    ).to_dict()

    high_conviction = next(
        item for item in report["source_results"] if item["strategy_id"] == "high_conviction_swing"
    )
    assert high_conviction["inserted_trade_count"] == 0
    assert high_conviction["reason_counts"] == {"high_conviction_data_paths_missing": 1}


def test_high_conviction_missing_data_path_reports_diagnostic(tmp_path):
    state_db = tmp_path / "state.db"
    registry = tmp_path / "strategy_hypotheses.json"
    _write_registry(registry)

    report = sync_shadow_paper_observations(
        ShadowPaperObservationSyncConfig(
            state_db_path=state_db,
            registry_path=registry,
            trend_shadow_db_path=tmp_path / "missing_trend.db",
            mean_reversion_shadow_db_path=tmp_path / "missing_mean.db",
            high_conviction_data_paths=(tmp_path / "missing_ohlcv.csv",),
            output_dir=tmp_path / "reports",
            run_id="pytest_high_conviction_missing_path",
            write_report=False,
        )
    ).to_dict()

    high_conviction = next(
        item for item in report["source_results"] if item["strategy_id"] == "high_conviction_swing"
    )
    assert high_conviction["inserted_trade_count"] == 0
    assert high_conviction["reason_counts"] == {"high_conviction_data_path_missing": 1}
    assert high_conviction["warnings"][0].startswith("missing:")


def test_high_conviction_no_closed_trades_reports_diagnostic(tmp_path, monkeypatch):
    state_db = tmp_path / "state.db"
    registry = tmp_path / "strategy_hypotheses.json"
    data_path = tmp_path / "ohlcv.csv"
    data_path.write_text("timestamp,symbol,timeframe,open,high,low,close,volume\n", encoding="utf-8")
    _write_registry(registry)
    fake_result = SimpleNamespace(
        cost_profile="research_stress",
        policy="conservative",
        scenario={
            "min_expected_move_bps": 500.0,
            "risk_reward_ratio": 2.0,
            "max_hold_hours": 72.0,
            "exit_mode": "fixed_tp_sl",
        },
        trade_records=(),
    )
    fake_report = SimpleNamespace(portfolio_results=(fake_result,))
    monkeypatch.setattr(shadow_observation_sync, "build_high_conviction_portfolio_report", lambda _config: fake_report)
    monkeypatch.setattr(shadow_observation_sync, "write_high_conviction_portfolio_report", lambda report, _output: report)

    report = sync_shadow_paper_observations(
        ShadowPaperObservationSyncConfig(
            state_db_path=state_db,
            registry_path=registry,
            trend_shadow_db_path=tmp_path / "missing_trend.db",
            mean_reversion_shadow_db_path=tmp_path / "missing_mean.db",
            high_conviction_data_paths=(data_path,),
            output_dir=tmp_path / "reports",
            run_id="pytest_high_conviction_no_closed",
            write_report=False,
        )
    ).to_dict()

    high_conviction = next(
        item for item in report["source_results"] if item["strategy_id"] == "high_conviction_swing"
    )
    assert high_conviction["inserted_trade_count"] == 0
    assert high_conviction["reason_counts"] == {"no_closed_high_conviction_shadow_trades": 1}


def test_opportunity_score_bucket_boundaries():
    assert shadow_observation_sync._score_bucket(70.0) == "high"
    assert shadow_observation_sync._score_bucket(69.999) == "medium"
    assert shadow_observation_sync._score_bucket(40.0) == "medium"
    assert shadow_observation_sync._score_bucket(39.999) == "low"
    assert shadow_observation_sync._score_bucket(None) == "missing"


def test_shadow_sync_is_idempotent_and_does_not_duplicate_ledger_rows(tmp_path):
    state_db = tmp_path / "state.db"
    registry = tmp_path / "strategy_hypotheses.json"
    trend_db = tmp_path / "trend_shadow_lab.db"
    _write_registry(registry)
    _write_shadow_db(trend_db, "trend_shadow_trades")

    config = ShadowPaperObservationSyncConfig(
        state_db_path=state_db,
        registry_path=registry,
        trend_shadow_db_path=trend_db,
        mean_reversion_shadow_db_path=tmp_path / "missing_mean.db",
        run_id="pytest_shadow_sync",
        output_dir=tmp_path / "reports",
    )
    sync_shadow_paper_observations(config)
    second = sync_shadow_paper_observations(config).to_dict()

    trend = next(item for item in second["source_results"] if item["strategy_id"] == "trend_momentum")
    assert trend["inserted_trade_count"] == 0
    assert trend["duplicate_trade_count"] == 1
    with sqlite3.connect(state_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM trade_ledger").fetchone()[0] == 2


def test_shadow_sync_enriches_existing_missing_score_without_duplicate_rows(tmp_path):
    state_db = tmp_path / "state.db"
    registry = tmp_path / "strategy_hypotheses.json"
    trend_db = tmp_path / "trend_shadow_lab.db"
    _write_registry(registry)
    _write_shadow_db(trend_db, "trend_shadow_trades")

    config = ShadowPaperObservationSyncConfig(
        state_db_path=state_db,
        registry_path=registry,
        trend_shadow_db_path=trend_db,
        mean_reversion_shadow_db_path=tmp_path / "missing_mean.db",
        run_id="pytest_shadow_sync",
        output_dir=tmp_path / "reports",
    )
    sync_shadow_paper_observations(config)
    _write_decision_ledger_router_score(state_db, score=84.0)

    second = sync_shadow_paper_observations(config).to_dict()
    trend = next(item for item in second["source_results"] if item["strategy_id"] == "trend_momentum")
    assert trend["inserted_trade_count"] == 0
    assert trend["duplicate_trade_count"] == 1
    assert trend["enriched_trade_count"] == 1
    assert trend["enriched_score_coverage"]["buckets"]["high"] == 1
    assert trend["score_origin_counts"] == {"decision_ledger_lookup": 1}
    assert trend["score_coverage"]["buckets"]["high"] == 1

    with sqlite3.connect(state_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM trade_ledger").fetchone()[0] == 2
    loaded = load_state_db_paper_ledger(state_db)
    trade = loaded.journal.records[0]
    assert trade.metadata["opportunity_score"] == pytest.approx(84.0)
    assert trade.metadata["score_bucket"] == "high"
    assert trade.metadata["opportunity_metadata_enriched"] is True


def test_learning_shadow_observations_are_not_promotable_paper_capital(tmp_path):
    state_db = tmp_path / "state.db"
    registry = tmp_path / "strategy_hypotheses.json"
    trend_db = tmp_path / "trend_shadow_lab.db"
    _write_registry(registry)
    _write_shadow_db(trend_db, "trend_shadow_trades")
    sync_shadow_paper_observations(
        ShadowPaperObservationSyncConfig(
            state_db_path=state_db,
            registry_path=registry,
            trend_shadow_db_path=trend_db,
            mean_reversion_shadow_db_path=tmp_path / "missing_mean.db",
            run_id="pytest_shadow_sync",
            output_dir=tmp_path / "reports",
        )
    )

    assert (
        trade_ledger_append_block_reason("trend_momentum", execution_mode="paper_capital")
        == "paper_capital_requires_promotion_gate"
    )
    summary = build_official_paper_performance_report(
        OfficialPaperPerformanceConfig(
            state_db_path=state_db,
            registry_path=registry,
            run_id="pytest_summary",
        ),
        write_report=False,
    ).to_dict()
    trend = next(item for item in summary["ranking"] if item["strategy_id"] == "trend_momentum")
    assert trend["decision"] == "keep_observing"
    assert trend["promotable"] is False
    assert trend["paper_capital_metrics"]["closed_trade_count"] == 0
    assert trend["shadow_paper_metrics"]["closed_trade_count"] == 1
    assert summary["legacy"]["shadow_paper_trade_count"] == 1
    assert summary["legacy"]["paper_capital_trade_count"] == 0


def test_rejected_retired_and_grid_strategies_cannot_write_shadow_paper():
    assert shadow_paper_strategy_block_reason("dynamic_grid") == "grid_retired_research_only"
    assert shadow_paper_strategy_block_reason("grid") == "grid_retired_research_only"
    assert shadow_paper_strategy_block_reason("relative_value") == "shadow_paper_strategy_not_allowed"


def test_metrics_distinguish_shadow_paper_and_paper_capital(tmp_path):
    state_db = tmp_path / "state.db"
    registry = tmp_path / "strategy_hypotheses.json"
    trend_db = tmp_path / "trend_shadow_lab.db"
    _write_registry(registry)
    _write_shadow_db(trend_db, "trend_shadow_trades")
    sync_shadow_paper_observations(
        ShadowPaperObservationSyncConfig(
            state_db_path=state_db,
            registry_path=registry,
            trend_shadow_db_path=trend_db,
            mean_reversion_shadow_db_path=tmp_path / "missing_mean.db",
            run_id="pytest_shadow_sync",
            output_dir=tmp_path / "reports",
        )
    )
    with sqlite3.connect(state_db) as conn:
        conn.execute(
            """
            INSERT INTO trade_ledger
            (trade_id, position_id, instance_id, symbol, side, expected_price, executed_price,
             volume, fees, slippage_bps, realized_pnl, is_opening_leg, is_closing_leg,
             strategy_id, timeframe, signal_source, gross_pnl, net_pnl, regime,
             execution_liquidity, execution_mode, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "paper_close",
                "paper_pos",
                "inst",
                "XLMEUR",
                "sell",
                1.10,
                1.10,
                10.0,
                0.2,
                1.0,
                0.8,
                0,
                1,
                "trend_momentum",
                "5m",
                "pytest",
                1.0,
                0.8,
                "trend",
                "taker",
                "paper_capital",
                "2026-07-01T04:00:00+00:00",
            ),
        )
        conn.execute(
            """
            INSERT INTO trade_ledger
            (trade_id, position_id, instance_id, symbol, side, expected_price, executed_price,
             volume, fees, slippage_bps, realized_pnl, is_opening_leg, is_closing_leg,
             strategy_id, timeframe, signal_source, gross_pnl, net_pnl, regime,
             execution_liquidity, execution_mode, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "paper_open",
                "paper_pos",
                "inst",
                "XLMEUR",
                "buy",
                1.00,
                1.00,
                10.0,
                0.2,
                1.0,
                None,
                1,
                0,
                "trend_momentum",
                "5m",
                "pytest",
                None,
                None,
                "trend",
                "taker",
                "paper_capital",
                "2026-07-01T03:00:00+00:00",
            ),
        )

    summary = build_official_paper_performance_report(
        OfficialPaperPerformanceConfig(
            state_db_path=state_db,
            registry_path=registry,
            run_id="pytest_summary",
        ),
        write_report=False,
    ).to_dict()
    by_mode = {bucket["key"]["execution_mode"]: bucket for bucket in summary["by_strategy_execution_mode"]}
    assert by_mode["shadow_paper"]["metrics"]["closed_trade_count"] == 1
    assert by_mode["paper_capital"]["metrics"]["closed_trade_count"] == 1
    trend = next(item for item in summary["ranking"] if item["strategy_id"] == "trend_momentum")
    assert trend["metrics"]["closed_trade_count"] == 2
    assert trend["shadow_paper_metrics"]["closed_trade_count"] == 1
    assert trend["paper_capital_metrics"]["closed_trade_count"] == 1


def test_cli_shadow_paper_observations_syncs_and_reports(tmp_path, capsys):
    state_db = tmp_path / "state.db"
    registry = tmp_path / "strategy_hypotheses.json"
    trend_db = tmp_path / "trend_shadow_lab.db"
    output_dir = tmp_path / "shadow_reports"
    _write_registry(registry)
    _write_shadow_db(trend_db, "trend_shadow_trades")

    exit_code = cli.main(
        [
            "shadow-paper-observations",
            "--state-db",
            str(state_db),
            "--registry-path",
            str(registry),
            "--trend-shadow-db",
            str(trend_db),
            "--mean-reversion-shadow-db",
            str(tmp_path / "missing_mean.db"),
            "--run-id",
            "pytest_cli_shadow",
            "--output-dir",
            str(output_dir),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["execution_mode"] == "shadow_paper"
    trend = next(item for item in payload["source_results"] if item["strategy_id"] == "trend_momentum")
    assert trend["inserted_trade_count"] == 1
    assert (output_dir / "pytest_cli_shadow.md").exists()


def test_cli_shadow_paper_observations_accepts_high_conviction_paths(tmp_path, capsys, monkeypatch):
    state_db = tmp_path / "state.db"
    registry = tmp_path / "strategy_hypotheses.json"
    data_path = tmp_path / "ohlcv.csv"
    output_dir = tmp_path / "shadow_reports"
    high_output_dir = tmp_path / "high_conviction_reports"
    data_path.write_text("timestamp,symbol,timeframe,open,high,low,close,volume\n", encoding="utf-8")
    _write_registry(registry)
    fake_result = SimpleNamespace(
        cost_profile="research_stress",
        policy="conservative",
        scenario={
            "min_expected_move_bps": 500.0,
            "risk_reward_ratio": 2.0,
            "max_hold_hours": 72.0,
            "exit_mode": "fixed_tp_sl",
        },
        trade_records=(_high_conviction_record(),),
    )
    fake_report = SimpleNamespace(portfolio_results=(fake_result,))
    monkeypatch.setattr(shadow_observation_sync, "build_high_conviction_portfolio_report", lambda _config: fake_report)
    monkeypatch.setattr(shadow_observation_sync, "write_high_conviction_portfolio_report", lambda report, _output: report)

    exit_code = cli.main(
        [
            "shadow-paper-observations",
            "--state-db",
            str(state_db),
            "--registry-path",
            str(registry),
            "--trend-shadow-db",
            str(tmp_path / "missing_trend.db"),
            "--mean-reversion-shadow-db",
            str(tmp_path / "missing_mean.db"),
            "--high-conviction-data-paths",
            str(data_path),
            "--high-conviction-output-dir",
            str(high_output_dir),
            "--run-id",
            "pytest_cli_high_conviction_shadow",
            "--output-dir",
            str(output_dir),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    high_conviction = next(
        item for item in payload["source_results"] if item["strategy_id"] == "high_conviction_swing"
    )
    assert high_conviction["inserted_trade_count"] == 1
    assert (output_dir / "pytest_cli_high_conviction_shadow.md").exists()
    loaded = load_state_db_paper_ledger(state_db)
    assert loaded.journal.records[0].strategy_id == "high_conviction_swing"
